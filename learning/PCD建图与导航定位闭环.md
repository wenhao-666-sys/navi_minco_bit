# PCD 建图与导航定位闭环

`icp_relocalization`、`navi2` 已构建通过，并通过独立 ROS 域中的合成点云定位、连续纠偏、重新初定位验证。下一步按下列命令实际建图、验收；隔离测试不代表实车场景已通过。旧的默认 AMCL 导航、slam_toolbox 建图不变。

## 实现和 fwh 的关系

参考了 `~/fwh/ros_ws/src/pb2025_sentry_nav` 的 Point-LIO + PCD + GICP 定位方式，以及 RViz `/initialpose` 的处理。当前仓库已有 GICP 的质量门限、连续匹配、稳定窗口检查，继续使用这些代码，不复制一套 fwh 导航。

新增流程：

```text
PTP → 双 MID360 驱动 → Point-LIO
                         ├─ /aft_mapped_to_init → camera_init 下的里程计
                         └─ /cloud_registered_full（去畸变、camera_init 世界坐标）
                              ↓ 建图时独立进程以 2 Hz 采样、5 cm 体素累积
                         map.pcd → 按离地高度截取 → map.pgm + map.yaml
                              └─ map_bundle.json：坐标约定、导出设置和 SHA256

导航时：实时完整点云 + map.pcd → GICP → map → camera_init
        map.yaml → map_server → 规划器；Point-LIO 继续提供连续局部里程计
        MPC → /cmd_vel_mpc → vel_rotate → /cmd_vel_rotate → 串口 → 电控
```

PCD 模式建图固定 `map → camera_init` 为单位变换，栅格直接投影同一 PCD。不会把 slam_toolbox 回环优化后的栅格与未优化的原始 Point-LIO PCD 混用。默认 slam_toolbox 模式仍只导出原有二维地图；此前只有 PGM/YAML 的目录不能直接用于新 GICP 入口。

截图中的 `odom_to_lidar_odom` 用于对齐原始雷达地图与底盘参考系。这里订阅的不是原始雷达坐标点，而是已经由 Point-LIO 变换到重力对齐世界系的点；因此不再把安装 roll 重复旋转到整张 PCD 上。地面高度仍使用现有安装参数和雷达—IMU 外参计算（当前约为 camera_init 下 z=-0.37711 m）。原点 XY 不平移，栅格原点记录到 YAML。

## 每个普通终端的环境

```bash
cd ~/2027-sentry-navi
source /opt/ros/humble/setup.bash
source ~/QD_Vision26/install/setup.bash
source ~/2027-sentry-navi/install/setup.bash
source ~/fwh/install/pointcloud_to_laserscan/share/pointcloud_to_laserscan/local_setup.bash
export ROS_DOMAIN_ID=0
export ROS_LOCALHOST_ONLY=0
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export FASTRTPS_DEFAULT_PROFILES_FILE="$HOME/2027-sentry-navi/src/navigation/vel_rotate/config/fastdds_udp.xml"
export FASTDDS_DEFAULT_PROFILES_FILE="$FASTRTPS_DEFAULT_PROFILES_FILE"
```

只加载 fwh 的点云转 scan 功能包，不整体加载 fwh 工作空间，以免覆盖本仓库 Point-LIO、驱动等包。

## 建图并导出

终端 1 启动 PTP，并保持运行：

```bash
sudo bash /home/robomaster/mid360-ptp/start.sh enp2s0
```

终端 2 加载上面的环境，再运行：

```bash
ros2 launch navi2 dual_lidar_mapping.launch.py \
  map_backend:=pcd \
  output_dir:="$HOME/maps/pcd_site_20261024"
```

选择一个新的输出目录。该命令包含双雷达驱动、Point-LIO、地面投影、PCD/栅格导出、RViz；不再单独启动驱动或 Point-LIO。这个建图入口仍需要终端 1 的 PTP。

开始静止数秒，缓慢覆盖场地，尤其扫完整墙、拐角和可通行区域。地图约每 10 秒刷新并保存，结束时 Ctrl+C 会从本进程缓存补存。等待进程退出后检查：

```bash
ls -lh "$HOME/maps/pcd_site_20261024/"{map.pcd,map.pgm,map.yaml,map_bundle.json}
```

四个文件是一套，迁移时整体复制。强制 kill / 掉电只能保留此前完成的检查点。

此栅格采用 pcd2pgm 的投影语义：矩形包围范围内，没有障碍投影的格子设为 free，**不表示这些格子都经过激光可见性验证**。使用前检查墙面是否连贯、门洞是否保留，不能仅凭 free 颜色认定所有区域都可通行。高度带沿用 `params/dual_lidar_mapping.yaml`：离地 0.10–1.20 m，分辨率 0.05 m。没有独立的二维 SLAM 回环优化。

## 使用这组 PCD 导航

确认建图进程已经全部退出。终端 1 的 PTP 如果还在运行，终端 2 使用：

```bash
ros2 launch navi2 navigation2.launch.py \
  localization:=gicp \
  map:="$HOME/maps/pcd_site_20261024/map.yaml" \
  start_ptp:=false
```

如果已经中断了所有程序，加载环境后改用：

```bash
sudo -v
ros2 launch navi2 navigation2.launch.py \
  localization:=gicp \
  map:="$HOME/maps/pcd_site_20261024/map.yaml"
```

后一条命令会一起启动 PTP、双驱动、Point-LIO、map_server、GICP、完整导航、vel_rotate、RViz。串口仍单独启动：

```bash
bash ~/2027-sentry-navi/src/navigation/vel_rotate/scripts/qd_bridge.bash serial
```

这个串口入口与已有视觉/串口启动方式二选一，避免同时打开同一个串口设备。

GICP 模式不启动 AMCL，不额外发布静态 `map → camera_init`；这条 TF 由 GICP 独占。启动时校验 PCD/PGM/YAML 的 SHA256，混用文件会在硬件启动前报错。GICP 参数位于 `src/navigation/navi2_bringup/params/gicp_navigation.yaml`，旧的比赛 GICP 配置保持不变。

## 初始定位和漂移恢复

1. 先保持机器人静止。在 RViz 点 **2D Pose Estimate**，在地图上的实际位置拖出正确朝向。朝向对应 `mapping_ground`（随云台雷达的 yaw），不要混成未建模的底盘朝向。
2. 看到 `Initial pose accepted as a seed` 只是收到初值。等待 `Localization confirmed from 3 independent windows`，再观察墙面叠合，之后才能发导航目标。
3. GICP 按 2 Hz 持续匹配 PCD，修正 `map → camera_init`，Point-LIO 的局部里程计不断开。检查 `/tmp/gicp_navigation_results.csv` 的 `localized`、`quality_accepted` 和匹配误差。
4. 严重漂移或日志提示 `Tracking lost`：先取消导航目标并停车，再重新给 2D Pose Estimate。该操作会清除旧匹配窗口，以新初值重新验证。新模式不会因为超时就发布以前写死的比赛起点。

这里实现的是**导航时基于先验 PCD 的持续定位纠偏**，没有新增自动全局搜索或建图轨迹回环优化。若建图本身已经双墙、拉伸，PCD 会保留这些误差，不能靠导航时匹配一张坏地图解决。云台与底盘之间的完整动态 TF、初始安装高度/roll 的最终实测复核不在本次修改范围内。

## 首次验收

先只验定位，不发送运动目标：确认 `/amcl` 不存在、GICP 和 map_server 在运行，`map → camera_init` 只有 GICP 发布；给初值后确认连续多窗口通过。然后低速走一个小闭环，观察返回同一墙角时位置和朝向是否一致，再人为给一个偏移的初值并重新纠正，验证恢复路径。同步查看实际速度曲线；本次代码和离线导出检查不能替代这一步。
