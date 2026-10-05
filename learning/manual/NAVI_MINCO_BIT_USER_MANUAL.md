# navi_minco_bit 导航部署与功能使用手册

Ubuntu 22.04 · ROS 2 Humble · NUC · 双 MID-360 · 舵轮底盘

版本：1.0 / 2026-10-04。依据本地仓库提交 `6dba3a53bf20848ac92dc1fb0fdfdaf9e8376a44` 与当前工作区静态核查编写。本文提供部署操作、模块入口、配置位置、成功判据及故障排查；本次没有在 NUC 编译、运行或接入硬件，命令属于待实机验证的操作流程。网络、外参、地图和下位机协议必须按实际设备填写。

独立仓库：`wenhao-666-sys/navi_minco_bit`；上游来源：`Walker152/navi_minco_bit`。本手册与 USV 工程分开存放。

**阅读方式：首次部署从第 01 节顺序执行；日常使用看第 13、14、21 节；故障查第 22 节；调用某个功能看第 23 节。** 文中的命令在 NUC 的 Ubuntu Bash 终端执行，不在 Windows PowerShell 执行。代码默认值是原车样例，不是你的硬件标定值。

## 01｜首次部署路线与验收门槛

先完成配置再运行。每一步达到“通过”条件后才进入下一步，避免一次启动所有模块后无法定位问题。

| 顺序 | 操作章节 | 通过条件 |
|---|---|---|
| 1 | 03 填设备表；04-06 下载、依赖、构建 | 关键包可以找到，插件库安装成功 |
| 2 | 07 网络；08 驱动和融合；09 时间同步 | 两个雷达均参与融合，主 IMU 数据连续且时间合理 |
| 3 | 10 Point-LIO 和 TF | 静止、平移、旋转时 odom 与点云合理 |
| 4 | 11 地图；12 GICP | 正确地图与实测点云对齐，确认不是超时回退 |
| 5 | 13 Nav2；14 目标与取消 | 生命周期激活，目标产生轨迹和控制输出 |
| 6 | 15 舵轮接口和通信 | 电控确认坐标与单位，完成低速方向、停止测试 |
| 7 | 16 比赛行为树 | 基础导航通过后再接入裁判数据与策略 |
| 8 | 18-21 可视化、录包、复现 | 重启后可恢复，证据和配置可追溯 |

**首次部署不直接执行 `start.bash`。** 它会启动比赛策略和串口，且使用旧工作目录、固定等待时间和特定 PTP 网卡。先按本文分终端启动，确认每层，再决定是否调整脚本。

最小实车计算链（先不启动通信和比赛行为树）：

```bash
# 每个新终端先执行；这里假设工作空间放在此目录
export NAVI_WS="$HOME/navi_minco_bit"
cd "$NAVI_WS"
source /opt/ros/humble/setup.bash
source "$NAVI_WS/install/setup.bash"

# 终端 1：时间同步，见 09；网卡先核实
# 终端 2：驱动与 Point-LIO，配置完成后启动
ros2 launch point_lio mixed_livox_pointlio_intra_process.launch.py
# 终端 3：GICP，先完成地图和初值配置
ros2 launch icp_relocalization gicp_relocalization.launch.py
# 终端 4：Nav2，见 13
ros2 launch navi2 navigation2.launch.py
```

不要在同一终端连续粘贴四个启动命令：launch 会占用前台。先确认 Point-LIO 正常，再启动 GICP，再启动导航。通信未启动时，ROS 侧导航计算不会自动驱动真实底盘；这不等于完整实车导航已验收。

## 02｜模块地图、进程与文件入口

主链：双雷达点云/IMU → Livox 融合 → Point-LIO → GICP 对齐与 ROGMap 环境表示 → MINCO → MPC → communication → MCU。行为树选择任务并调用 Nav2。

| 模块 | 目录 / ROS 包名 | 主要职责 |
|---|---|---|
| 雷达驱动 | `src/perception/livox_ros_driver2` | SDK 接收、IMU 发布、双雷达融合 |
| 双雷达标定 | `src/perception/dual_lidar_calibration` | 离线求后雷达到前雷达外参 |
| 里程计 | `src/perception/Point-LIO` / `point_lio` | IMU 与点云运动估计、去畸变、局部地图 |
| 重定位 | `src/perception/icp_relocalization` | PCD 匹配、`map → camera_init` |
| 环境地图 | `src/perception/rog_map` | 概率占据、地形投影、ESDF |
| 辅助感知 | `msg_convert`、`dbscan_cluster` | 裁剪过滤、障碍聚类与跟踪 |
| 导航组织 | `src/navigation/navi2_bringup` / `navi2` | Nav2 launch、参数、二维地图和导航树 |
| 规划 / 控制 | `minco_planner`、`minco_controller` | 搜索、轨迹优化、MPC 跟踪 |
| 串口 | `src/navigation/communication` | 协议解析、命令打包、裁判状态 |
| 决策 | `src/decision/bt_manager` | 比赛行为树与 blackboard |
| 接口 | `src/ros_interfaces` | 自定义轨迹、行为和比赛消息 |
| 地图工具 | `pcd2pgm`、`pcd2ele`、`pcd2esdf` | 栅格、高程、距离场转换 |
| 普通工具 | `src/utils/pcd_trans` | CloudLab 浏览器地图处理，不是 ROS 包 |
| 仿真 | `src/simulation/sentry_simulation` | Fortress 模型、传感器与速度适配 |

上述共 17 个 ROS 包。完整逐文件索引见 `learning/PROJECT_INDEX.md`，完整关系图见 `learning/NAVI_MINCO_BIT_FLOWCHART.mmd` 及其 SVG/PNG 渲染。

| 进程边界 | 实际包含的内容 |
|---|---|
| `/livox_pointlio_container` | 多线程组件容器；`/livox_driver_node`、`/laserMapping`；导航启动时再加载 `/planner_server` |
| 规划器内部 | MINCO 插件持有 ROGMap 与地图查询对象；不是额外启动一个独立 ROGMap 节点 |
| 独立节点进程 | GICP；默认非组合启动的 controller、BT navigator、smoother 等 Nav2 节点 |
| 另外启动 | communication、比赛 bt_manager、Foxglove bridge、录包 |

容器启动、组件加载、生命周期激活是三个不同检查。当前 planner 的进程内通信选项为 false；同进程不代表所有消息都会零拷贝。

## 03｜部署前填写表与配置关联

| 项目 | 原代码样例 | 本车填写值 |
|---|---|---|
| NUC 工作空间绝对路径 | 原脚本 `~/2027-sentry-navi` | __________________ |
| 雷达网卡 | `enp86s0` | __________________ |
| NUC 雷达网卡 IPv4 / 掩码 | `192.168.1.47` / 本文样例 `/24` | __________________ |
| 前雷达 IP / 主 IMU | `192.168.1.135` | __________________ |
| 后雷达 IP | `192.168.1.122` | __________________ |
| 后雷达 → 前雷达外参 | 第 08 节样例 | __________________ |
| LiDAR → IMU 外参、车体安装偏移 | 第 10、15 节样例 | __________________ |
| 当前场地 PCD / PGM / YAML | 原比赛地图 | __________________ |
| 启动初始位置、朝向与误差范围 | 原比赛启动点 | __________________ |
| 串口 / 波特率 / 帧协议 | `/dev/ttyACM0` / 115200 | __________________ |
| MCU 接收 vx、vy 坐标系 | 尚未确认 | 车体系 / 世界系：________ |
| 正方向与单位 / 命令超时停车 | 尚未确认 | __________________ |
| Windows 到 NUC 的可达地址 | 与雷达地址可不同 | __________________ |

**一项硬件变更可能关联多份配置。** 换前雷达 IP：JSON 的设备 IP + 融合 YAML 的 `merge_front_ip` + Point-LIO launch 的 IMU 话题。换 NUC IP：JSON 的五个主机接收地址 + 网卡配置。换场地：GICP PCD + Nav2 map YAML + ROGMap projection prior + 初值/默认位姿 + 策略中的区域/目标点。

关键配置入口：

| 配置 | 路径（相对仓库根目录） |
|---|---|
| 网络 | `src/perception/livox_ros_driver2/config/mixed_MID360_config.json` |
| 双雷达融合 | `src/perception/livox_ros_driver2/config/mixed_MID360_component.yaml` |
| LIO | `src/perception/Point-LIO/config/mid360.yaml` |
| LIO launch 覆盖 | `src/perception/Point-LIO/launch/mixed_livox_pointlio_intra_process.launch.py` |
| GICP | `src/perception/icp_relocalization/config/gicp_relocalization.yaml` |
| 导航、MPC、ROGMap | `src/navigation/navi2_bringup/params/sentry1.yaml` |
| 串口设备 | `src/navigation/communication/src/com.cpp` |
| 底盘打包与字段 | `communication/include/com_interface_ros.hpp`、`include/utils/custom_protocol.hpp` |

## 04｜下载、系统与 ROS 环境

以下从已经安装 Ubuntu 22.04 的 NUC 开始。已安装 ROS 2 Humble 时跳过软件源设置，直接确认环境。首次安装参照 [ROS 2 Humble 官方 Ubuntu 安装说明](https://docs.ros.org/en/humble/Installation/Ubuntu-Install-Debs.html)。

### 首次设置 ROS 软件源

先 `locale` 确认已有 UTF-8 locale；中文 UTF-8 环境无需改成英文。没有 UTF-8 时按官方说明安装 locales 并生成 en_US.UTF-8。先更新 Ubuntu 基础系统，再安装 ROS；不要跳过官方关于 Jammy 初期 systemd/udev 更新的要求。

下面依据 [ROS 官方软件源步骤](https://raw.githubusercontent.com/ros2/ros2_documentation/humble/source/Installation/_Apt-Repositories.rst)，仅适用于 Ubuntu 22.04 Jammy。已有旧 ROS 源时先按官方迁移说明核对，避免重复源和签名冲突。

```bash
sudo apt update
sudo apt upgrade
sudo apt install -y software-properties-common curl python3
sudo add-apt-repository universe
NAVI_ROS_APT_VERSION=$(curl -fsSL \
  https://api.github.com/repos/ros-infrastructure/ros-apt-source/releases/latest \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["tag_name"])')
curl -fL -o /tmp/ros2-apt-source.deb \
  "https://github.com/ros-infrastructure/ros-apt-source/releases/download/${NAVI_ROS_APT_VERSION}/ros2-apt-source_${NAVI_ROS_APT_VERSION}.jammy_all.deb"
sudo dpkg -i /tmp/ros2-apt-source.deb
```

下载或解析失败先修复网络，不能继续安装空文件。已安装 Humble 的设备无需重新做这组操作。

ROS 软件源已配置后：

```bash
sudo apt update
sudo apt install -y ros-humble-desktop ros-dev-tools \
  python3-colcon-common-extensions python3-rosdep git \
  build-essential cmake pkg-config
source /opt/ros/humble/setup.bash
lsb_release -ds
uname -m
printenv ROS_DISTRO
which ros2
```

预期 Ubuntu 22.04、NUC 通常为 x86_64、`ROS_DISTRO=humble`。检查未通过时先修环境，不继续运行算法。

下载自己的独立仓库：

```bash
git clone https://github.com/wenhao-666-sys/navi_minco_bit.git \
  "$HOME/navi_minco_bit"
export NAVI_WS="$HOME/navi_minco_bit"
cd "$NAVI_WS"
git status --short
git rev-parse HEAD
git remote -v
```

私有仓库需有权限的 GitHub 登录或 SSH。Windows 尚未推送的学习文件不会自动出现在 NUC；可单独复制文档。本次不替你提交或推送。保留仓库来源与版本记录，不混入 USV 工作空间。

后文每个新终端统一执行：

```bash
export NAVI_WS="$HOME/navi_minco_bit"
cd "$NAVI_WS"
source /opt/ros/humble/setup.bash
# 构建成功后才执行下一行
source "$NAVI_WS/install/setup.bash"
```

`NAVI_WS` 是本文选择的路径变量，可改为你的实际目录。不要在一个终端加载多个含同名包的旧导航工作空间。检查 `ROS_DOMAIN_ID`、`RMW_IMPLEMENTATION` 是否一致；本文不强制切换 DDS 实现。

## 05｜依赖安装与首次构建

本节命令供你在 NUC 执行；本次文档制作没有执行 ROS 或 C++ 构建。系统依赖与 CMake 检查共同决定是否能编译，`rosdep` 不能补齐所有未声明的头文件库。

```bash
sudo apt install -y libeigen3-dev libpcl-dev libyaml-cpp-dev \
  libgoogle-glog-dev libunwind-dev libfmt-dev libopencv-dev \
  libomp-dev libapr1-dev linuxptp ethtool tcpdump \
  ros-humble-navigation2 ros-humble-nav2-bringup \
  ros-humble-backward-ros ros-humble-pcl-ros \
  ros-humble-pcl-conversions ros-humble-ament-cmake-auto \
  ros-humble-behaviortree-cpp-v3 \
  ros-humble-spatio-temporal-voxel-layer
cd "$NAVI_WS"
sudo rosdep init
rosdep update
rosdep install --from-paths src --ignore-src -r -y
```

`rosdep init` 仅首次执行，已初始化时跳过。若 rosdep 报仿真依赖缺失，安装第 17 节的仿真依赖，或在构建范围中明确排除 `sentry_simulation`；不要忽略错误后直接宣称依赖已完整。

Livox SDK2 是 C/C++ SDK；按 [官方安装说明](https://github.com/Livox-SDK/Livox-SDK2) 安装：

```bash
mkdir -p "$HOME/navi_deps"
cd "$HOME/navi_deps"
git clone https://github.com/Livox-SDK/Livox-SDK2.git
cmake -S Livox-SDK2 -B Livox-SDK2/build
cmake --build Livox-SDK2/build -j2
sudo cmake --install Livox-SDK2/build
sudo ldconfig
```

GICP 使用 small_gicp 头文件。按 [small_gicp C++ 官方说明](https://github.com/koide3/small_gicp#installation) 安装，不能用同名 Python 包代替：

```bash
cd "$HOME/navi_deps"
git clone https://github.com/koide3/small_gicp.git
cmake -S small_gicp -B small_gicp/build -DCMAKE_BUILD_TYPE=Release
cmake --build small_gicp/build -j2
sudo cmake --install small_gicp/build
sudo ldconfig
```

当前 small_gicp 官方仓库包含 Sophus。项目 README 还要求系统 Sophus；若编译提示 `sophus/...` 找不到，先检查 small_gicp 安装是否已包含，再安装 [原版 Sophus](https://github.com/strasdat/Sophus) 的 C++ 头文件。不要改用 Sophus2 或 Rust 版本。记录实际依赖提交，避免每次拉取不同版本后比较性能。

```bash
# 仅在缺少所需 Sophus 头文件时执行；本例禁用其测试和 Python绑定
cd "$HOME/navi_deps"
git clone https://github.com/strasdat/Sophus.git
cmake -S Sophus -B Sophus/build -DBUILD_SOPHUS_TESTS=OFF \
  -DBUILD_PYTHON_BINDINGS=OFF
cmake --build Sophus/build -j2
sudo cmake --install Sophus/build
```

这些是上游源码安装示例，不是已验证的依赖版本锁。记录仓库提交，若版本兼容问题先保留日志，再核对项目所需 API。

```bash
cd "$NAVI_WS"
source /opt/ros/humble/setup.bash
MEM_LIMIT_GB=12 MEM_PER_WORKER_GB=2 bash build.bash
source install/setup.bash
colcon list
ros2 pkg prefix point_lio
ros2 pkg prefix navi2
ros2 pkg prefix minco_planner
```

脚本先串行编译核心包，再编译剩余包。`MEM_LIMIT_GB` 主要用于估算并行包数和打印系统内存告警，不是 cgroup 的硬内存上限；单包内部编译也可能占满内存。内存紧张时使用 `CMAKE_BUILD_PARALLEL_LEVEL=2` 限制构建工具并行。

失败时查看 `log/latest_build/<包名>/stderr.log` 和 `stdout_stderr.log`，找第一个有效错误。`killed cc1plus` 常见于内存不足；`package not found` 查包安装与环境；`header not found` 查系统头文件路径；插件库不存在先确认对应包构建、安装成功。不要执行 `clean.bash` 删除证据来掩盖原因。

## 06｜参数、安装目录和路径规则

`ros2 launch` 从当前环境中的包安装目录读取 launch。`get_package_share_directory()` / `FindPackageShare()` 查的是该目录；不是自动使用你当前打开的源码文件。

```bash
ros2 pkg prefix --share navi2
ros2 pkg prefix --share point_lio
ros2 pkg prefix --share livox_ros_driver2
ros2 launch navi2 navigation2.launch.py --show-args
```

`navigation2.launch.py` 默认导航参数是 `params/sentry1.yaml`。`nav2_params.yaml` 不是默认生效文件。导航 launch 会重写 `use_sim_time`、`autostart` 等参数后传给节点。

为避免误读安装副本，部署时可明确指定源码参数：

```bash
ros2 launch navi2 navigation2.launch.py \
  params_file:="$NAVI_WS/src/navigation/navi2_bringup/params/sentry1.yaml" \
  map:="$NAVI_WS/src/navigation/navi2_bringup/maps/2026/rmuc2026.yaml"
```

地图路径这里只演示原仓库资源；部署到你的场地时替换成自建地图。Point-LIO 可直接使用通用 launch 指定文件和主 IMU，见第 10 节。

GICP PCD、ROGMap 先验、Nav2 行为树 XML 等默认路径含 `src/...`，依赖运行时工作目录。因此本文要求每个终端先 `cd "$NAVI_WS"`。部署配置更适合改为绝对路径；YAML 普通字符串中的 `$HOME` 不会自动展开。

**修改文件、节点参数变化、算法实际采用新值，是三件事。** 初始化缓存的参数通常需要重启或重新配置。查询示例：

```bash
ros2 param get /laserMapping common.imu_topic
ros2 param get /planner_server MincoPlanner.plugin
ros2 param get /controller_server FollowPath.dt
ros2 param dump /controller_server
```

不要把 `ros2 param set` 的成功返回当作算法支持动态调参的证明。源码、launch 或插件注册修改需要重新构建；配置文件使用符号链接时可能直接更新，但仍需核对节点实际读取路径。

## 07｜雷达网络：主机 IP、设备 IP 与 UDP

接线建议：NUC 有线网卡 → 千兆交换机 → 两台 MID-360，按雷达说明提供电源。Windows 远程显示可走另一网口或 Wi-Fi；不要求与雷达接收网卡使用同一地址。

```bash
ip -br link
ip -br addr
ip route
nmcli device status
nmcli connection show
```

先选实际雷达网卡，再确定是否由 NetworkManager 管理。下例创建一个仅用于雷达的配置，网卡名和 IP 必须替换；激活可能中断该网口当前连接，首次在 NUC 本地操作：

```bash
NAVI_IFACE=enp86s0
NAVI_HOST_CIDR=192.168.1.47/24
sudo nmcli connection add type ethernet ifname "$NAVI_IFACE" \
  con-name navi-lidar ipv4.method manual \
  ipv4.addresses "$NAVI_HOST_CIDR" ipv4.never-default yes \
  ipv6.method disabled
sudo nmcli connection up navi-lidar
```

已有 `navi-lidar` 配置时用 `nmcli connection modify`，不要重复创建。雷达专用网络通常不需要默认网关；互联网由其他连接承担。按实际设备网段填写掩码，不能把 `/24` 当作已知硬件事实。

编辑 `mixed_MID360_config.json`：`host_net_info` 的 `cmd_data_ip`、`push_msg_ip`、`point_data_ip`、`imu_data_ip`、`log_data_ip` 全部填 NUC 雷达网卡地址；`lidar_configs[].ip` 填各自雷达真实地址。

当前 JSON 中设备/主机对应端口均为 56100、56200、56300、56400、56500。端口先保持该配置，使用抓包核对实际目的端口；不要根据其他教程或监测脚本默认值猜端口。协议参见 [Livox MID-360 官方通信说明](https://livox-wiki-en.readthedocs.io/en/latest/tutorials/new_product/mid360/livox_eth_protocol_mid360.html)。改 JSON 不会把雷达设备自身 IP 自动改成你填写的值；设备 IP 变更应按 Livox 工具/协议操作。

```bash
ping -c 3 192.168.1.135
ping -c 3 192.168.1.122
ip route get 192.168.1.135
sudo tcpdump -ni "$NAVI_IFACE" \
  'udp and (host 192.168.1.135 or host 192.168.1.122)'
ss -lunp
```

通过条件：路由走正确网卡；两台雷达都有持续 UDP；启动驱动后接收到有效点云与 IMU。ping 仅证明一部分连通性，不能证明 UDP、消息或时间同步正确。没有数据时检查电源、网线、设备 IP、主机目的地址、端口、现有防火墙规则及端口占用，不直接关闭整机防火墙。

## 08｜驱动与双雷达融合、外参标定

实车主入口使用 `mixed_MID360_component.yaml`；驱动独立 launch `msg_mixed_MID360.launch.py` 还有另一套写在 Python 中的参数。两者不能混用配置来源。

当前组件配置：

```yaml
enable_internal_lidar_merge: true
merge_front_ip: 192.168.1.135
merge_back_ip: 192.168.1.122
merge_output_topic: livox/lidar
merge_max_interval_ms: 5.0
merge_extrinsic_back_to_front: [0.0, 0.38, -0.05, -0.36713, 0.0, 0.0]
```

外参数组为 `[x, y, z, roll, pitch, yaw]`，单位米/弧度，方向是 **后雷达 → 前雷达**。原 README 和独立 launch 的 `[0,0.4,0,-0.35453,0,0]` 与组件配置不同。以上仅抄录当前代码，不能直接当作你车的标定结果。

融合开启后，原始两路点云被驱动内部消耗，主输出 `/livox/lidar` 为 `livox_ros_driver2/msg/CustomMsg`。IMU 仍按设备 IP 分话题，例如 `/livox/imu_192_168_1_135`。不能因为融合输出有数据就断定两颗雷达都在贡献点；还要观察后/前雷达 UDP、融合诊断和相应视场。

如仅检查驱动、不启动 LIO，可运行组件节点：

```bash
ros2 run rclcpp_components component_container_mt \
  --ros-args -r __node:=sensor_check_container
# 另一个已 source 的终端
ros2 component load /sensor_check_container \
  livox_ros_driver2 livox_ros::DriverNode \
  --param-file "$HOME/navi_configs/driver_check.yaml"
```

上述 driver_check.yaml 是你先复制好的驱动配置。组件 load 的参数文件通常按普通 ROS 参数解析，不保证展开 `$(find-pkg-share ...)`。运行前创建 `$HOME/navi_configs`，将组件 YAML 复制为 driver_check.yaml，并将 `user_config_path` 改为 JSON 的绝对路径；主 launch 使用 `ParameterFile(..., allow_substs=True)` 才明确支持该替换。不要同时运行此驱动和主驱动。

外参不确定时，用 `dual_lidar_calibration` 离线标定。复制 `config/example.yaml`，填四个真实话题；采集时在驱动中关闭内部融合、保持 `multi_topic: 1`。记录两路未融合 CustomMsg 和两路 IMU，以有重叠特征、至少两个旋转轴的运动采样：

```bash
ros2 bag record -s mcap -o "$HOME/navi_data/calibration_motion" \
  /livox/lidar_192_168_1_135 /livox/lidar_192_168_1_122 \
  /livox/imu_192_168_1_135 /livox/imu_192_168_1_122
ros2 run dual_lidar_calibration calibrate \
  --bag "$HOME/navi_data/calibration_motion" \
  --config /absolute/path/calibration.yaml \
  --output "$HOME/navi_data/calibration_result"
```

MCAP 依赖见第 19 节。标定退出码 0 才表示质量门槛通过，2 表示完成但质量不通过，1 表示输入/运行错误。通过后检查 `summary.yaml`、`frame_results.csv` 和 `aligned_preview.pcd`，再将 `extrinsic.yaml` 中的数组写回驱动，恢复融合。只有单轴激励时可补 `--static-bag`，具体配置见该包 README。

## 09｜PTP、IMU 与点云时间同步

Point-LIO 需要 IMU 时间覆盖当前点云最后一点的时刻。最新 IMU 时间不足时等待后续 IMU；消息频率高不代表时间新、队列小或算法无延迟。

仓库 `scripts/ptp_sync.bash` 固定网卡 `enp86s0`，启动 `ptp4l` 和 `phc2sys`，并停止 NTP/chrony、清理原有 PTP 进程。先了解这些系统变更，再运行；它适用于有相应 PTP 能力的网卡和交换链路。

```bash
ethtool -T "$NAVI_IFACE"
timedatectl
pgrep -a ptp4l
pgrep -a phc2sys
# 将脚本 INTERFACE 改为实际网卡后，在单独终端
sudo bash scripts/ptp_sync.bash
```

检查 `/tmp/ptp4l_<网卡>.log`、`/tmp/phc2sys_<网卡>.log` 的端口状态、时钟同步和报错。进程存在不等于 MID-360 已锁定主时钟；还要查看雷达状态与实际消息时间戳。网卡不支持硬件时间戳时，先确认可行的软件同步配置，不能照抄原脚本认为已同步。

部署链先同步后启动传感器与算法，运行中避免突然调整系统时间。实机 `use_sim_time=false`；仿真和历史回放使用统一 `/clock`，两种时基不要混用。

```bash
ros2 topic echo /livox/lidar --once --field header \
  --qos-reliability best_effort
ros2 topic echo /livox/imu_192_168_1_135 --once --field header \
  --qos-reliability best_effort
ros2 param get /laserMapping common.time_diff_lidar_to_imu
```

`time_diff_lidar_to_imu` 是时间校准量，不用于掩盖网络延迟或积压。区分采样时间、回调到达时间、计算开始/结束时间。传感器最后点时间需要结合 CustomMsg `timebase/offset_time`，不能只看 header 秒数是否接近。

停止 PTP 后按原配置恢复 NTP/chrony，不要同时启动两个此前没有运行的授时服务。恢复操作应在导航已停止之后进行。

## 10｜Point-LIO：启动、输入验证与 TF

推荐换车时使用通用 launch，显式指定本车主 IMU，避免双雷达包装 launch 写死 `.135`：

```bash
ros2 launch point_lio livox_pointlio_intra_process.launch.py \
  driver_params_file:="$NAVI_WS/src/perception/livox_ros_driver2/config/mixed_MID360_component.yaml" \
  pointlio_params_file:="$NAVI_WS/src/perception/Point-LIO/config/mid360.yaml" \
  pointlio_imu_topic:=livox/imu_192_168_1_135 \
  container_name:=livox_pointlio_container
```

替换 IMU 话题中的 IP。驱动 YAML 内的 JSON 地址仍需正确设置。`common.imu_topic` 的 launch 字典在 YAML 后加载，会覆盖 YAML 值。

```bash
ros2 component list
ros2 node info /laserMapping
ros2 param get /laserMapping common.lid_topic
ros2 param get /laserMapping common.imu_topic
ros2 topic info /livox/lidar -v
ros2 topic hz /livox/lidar
ros2 topic hz /livox/imu_192_168_1_135
ros2 topic hz /aft_mapped_to_init
```

频率是观察结果；驱动配置 20 Hz、里程计上限 100 Hz，不保证实机一定达到。CLI 订阅也增加负载，QoS 不兼容时使用适配选项，先以 `topic info -v` 判断。

| 参数族 | 当前例子 | 部署用途 |
|---|---|---|
| 输入 | `common.lid_topic`、`common.imu_topic` | 对准实际消息 |
| 时间与预处理 | `preprocess.*`、`common.time_diff_lidar_to_imu` | 雷达类型、点时间单位、盲区、校时 |
| 估计 | `mapping.extrinsic_T/R`、噪声和匹配参数 | LiDAR-IMU 外参、运动估计 |
| 性能 | `point_filter_num`、`filter_size_surf/map`、batch | 点数、滤波与耗时 |
| 发布 / 保存 | `odometry.*`、`publish.*`、`pcd_save.*` | odom、点云、TF、地图保存 |

`use_imu_as_input: False` 不等于禁用 IMU；它是估计器的算法模式选择，IMU 是否启用看 `mapping.imu_en` 等真实逻辑。不要按参数名猜结论。

当前输出：`/aft_mapped_to_init` 是 Odometry，父 `camera_init`、子 `body`；`/cloud_registered_full` 是去畸变世界系完整 PointCloud2；`/cloud_registered` 是常规配准点云。

**项目 TF 并非通用机器人模板。** Point-LIO 分别发布 `camera_init → body`、`camera_init → base_link`、`camera_init → slambase`；`base_link` 使用安装偏移且姿态为单位旋转，`slambase` 使用 yaw。不要另外发布同名变换，也不要凭常见框架假设它们是 `body → base_link`。

```bash
ros2 run tf2_ros tf2_echo camera_init body
ros2 run tf2_ros tf2_echo camera_init base_link
ros2 run tf2_ros tf2_echo camera_init slambase
```

先静止初始化，再人工平移和旋转观察：位姿连续、点云无明显双层/拖影、静止漂移可接受。没有 odom 时依次检查组件、两路输入、时间覆盖、初始化条件、处理队列与估计参数。不能用 odom 频率判断位姿是否滞后。

## 11｜地图准备、PCD 保存与二维转换

| 文件 | 谁使用 | 应确认什么 |
|---|---|---|
| PCD | GICP；部分环境先验/离线工具 | 米制坐标、真实几何、静态结构 |
| PGM + YAML | Nav2 map_server | resolution、origin、阈值与图片路径 |
| projection prior YAML | ROGMap 内部先验投影 | 与 map 坐标一致、障碍语义正确 |

原比赛地图不适用于你的新场地。首次建图可先只运行驱动与 Point-LIO，开启 `pcd_save.pcd_save_en: true`，配置好间隔后重启。程序将点云写到编译时 `ROOT_DIR/PCD/`，通常对应 `src/perception/Point-LIO/PCD/`。

达到间隔保存 `scans_1.pcd` 等；正常退出时如还有未保存点，析构函数写 `scans.pcd`。后者可能仅为剩余段，不保证包含之前全部分段。`interval: -1` 可能累计大量内存；长时间建图更适合分段保存，再经可靠配准/处理得到完整静态地图。Ctrl+C 正常退出，强制杀进程可能丢失尾段。

### 方法 A：CloudLab 处理与导出

```bash
cd "$NAVI_WS"
python3 -m http.server 8080 --directory src/utils/pcd_trans
```

浏览器打开 `http://127.0.0.1:8080/visual_point_cloud_lab.html`。导入 PCD → 检查方向和单位 → 裁剪/去噪 → 标记地面、墙体和障碍 → 生成并检查二维地图 → 下载处理后 PCD、PGM/YAML 及工程参数。高级算法需要 Open3D 后端，见第 23 节。

### 方法 B：pcd2pgm 与地图保存

修改 `src/utils/pcd2pgm/config/pcd.yaml`：`file_directory` 填绝对目录并带末尾 `/`，`file_name` 填不含 `.pcd` 的文件名；选择高度过滤与 `map_resolution`。`pcd2pgm` 生成并发布 `/map`，另用 map_saver 保存。

```bash
ros2 launch pcd2pgm pcd2pgm.launch.py use_sim_time:=false
# 新终端：避免同时启动另一台发布 /map 的 map_server
mkdir -p "$NAVI_WS/maps/site_a"
ros2 run nav2_map_server map_saver_cli -t /map \
  -f "$NAVI_WS/maps/site_a/site_a" --fmt pgm
```

原 launch 的 `use_sim_time` 默认 true，离线实机转换显式设 false。保存成功产生同名前缀 PGM/YAML；检查 YAML 的 `image` 指向存在文件。

`resolution` 决定米/像素；`origin` 决定二维栅格在 map 中的位置和朝向。整体平移优先查 origin x/y，整体旋转查 yaw/生成坐标处理，尺寸不一致查 resolution。所有来源地图必须同坐标、同尺度；可选点三个有明确对应的墙角验证距离和方向。

配置本车地图时：GICP 的 `target_pcd_file` 指向处理后 PCD；Nav2 launch 的 `map` 指向本车 YAML；`sentry1.yaml` 中 `MincoPlanner.rog_map.projection.prior_map.yaml_path` 单独指向所需先验 YAML。**只修改 launch 的 map 参数不会自动替换 ROGMap 内嵌先验。**

## 12｜GICP：初始配准、回退与重新定位

编辑 `gicp_relocalization.yaml`：PCD 绝对路径、`initial_pose`、`default_pose_on_timeout`、裁剪范围与质量门槛必须依据本车。数组 `[x,y,z,roll,pitch,yaw]` 为米/弧度，描述 map 与局部坐标系的对齐；不是直接向机器人设置车体位姿。

```bash
ros2 launch icp_relocalization gicp_relocalization.launch.py \
  gicp_config:="$NAVI_WS/src/perception/icp_relocalization/config/gicp_relocalization.yaml"
ros2 node info /gicp_relocalization_node
ros2 run tf2_ros tf2_echo map camera_init
```

输入 `/cloud_registered_full`；输出 `map → camera_init` 的 TF。当前匹配频率配置 5 Hz、TF 发布 100 Hz；匹配还受累积窗口和状态机限制，两者不是同一个频率。

当前稳定性要求三个独立累积窗口一致，并有归一化误差、内点比例、重叠比例和初值修正范围检查。`initial_pose_guard` 当前限制初值附近 0.4 m、0.2 rad；初始猜测太远，即使找到别处的匹配也可能被拒绝。先确认地图、初值和点云，再根据数据调门槛。

| 状况 | 实际行为 | 验收判断 |
|---|---|---|
| 配准通过稳定性检查 | 日志 `Localization confirmed`；保存变换 | 再核对点云与地图重合 |
| 连续重定位关闭（默认） | 停匹配和点云订阅；继续发布保存的 TF | 数值不变正常，不自动纠正后续 LIO 漂移 |
| 初始化超时（配置 10 s） | 使用 YAML 默认位姿；停止匹配；继续发布 TF | 这是人工假设，不能作为定位成功 |
| 服务触发重定位 | 重置状态，切到 multi_guess 并恢复点云输入 | 返回成功不等于后续匹配已成功 |

当前 TF 发布辅助函数保留 x/y/yaw，z 为零，输出为平面定位语义。不要依靠它给坡道提供完整 6DoF 地图对齐。

```bash
ros2 service list -t
ros2 service call /gicp_recall std_srvs/srv/Trigger '{}'
```

调用前停止导航与运动，按当前 `multi_guess.search_rectangles` 检查搜索区域，等待确认日志。默认区域仍是原车配置；调用 recall 不等于自动改用本车 initial_pose。

debug 话题位于 `/gicp_relocalization_node/debug/`，包括 `source_raw`、`source_cropped`、`source_aligned`、`target_raw`、`target_cropped`。显示相同坐标系下的 source_aligned 与 target，核对墙、转角和地面，不能只凭 TF 存在判断正确。CSV 开关为 `results.enable`，记录路径确保可写。

## 13｜Nav2、ROGMap 与 MINCO 的启动验收

先确认 `/livox_pointlio_container` 存在、Point-LIO 正常、GICP 对齐已验证。导航会把 planner_server 加载到该容器；不能在没有这个容器时只启动导航并期待 planner 自动出现。

```bash
cd "$NAVI_WS"
ros2 launch navi2 navigation2.launch.py \
  use_sim_time:=false \
  params_file:="$NAVI_WS/src/navigation/navi2_bringup/params/sentry1.yaml" \
  map:="$NAVI_WS/maps/site_a/site_a.yaml"
```

本车地图尚未生成时，不能直接使用上述 site_a 路径。使用原地图仅做对应场地的源码/仿真检查。导航同时 include 官方 localization launch，启动 map_server、AMCL 等；AMCL 默认需要对应二维扫描输入，本仓库主链没有已核实的有效 scan 来源，不能把 AMCL 存在当作主定位工作正常。当前主定位由 Point-LIO + GICP 提供；检查是否出现重复 TF 发布者。

```bash
ros2 component list
ros2 lifecycle get /planner_server
ros2 lifecycle get /controller_server
ros2 lifecycle get /bt_navigator
ros2 lifecycle get /map_server
ros2 param get /planner_server planner_plugins
ros2 param get /planner_server MincoPlanner.plugin
ros2 action list -t
ros2 run tf2_ros tf2_echo map base_link
```

预期关键生命周期节点为 active，规划器列表包含 `MincoPlanner`，插件字符串 `minco_planner/MincoPlanner`，控制器插件 `minco_controller::MincoMpcController`。组件名、插件实例标识、注册类名称有区别，不要改成看起来相似的名称。

激活失败先看 lifecycle_manager 与首个失败节点日志，不对所有节点反复手动 activate。插件创建失败分“找不到类/库”和“初始化参数/资源失败”。后者常见于先验 YAML、PCD 或行为树 XML 路径无效。

ROGMap 是 MINCO 内部对象，配置在 `planner_server.ros__parameters.MincoPlanner.rog_map`。当前以 `/cloud_registered_full` 和 `/aft_mapped_to_init` 为输入，坐标 `camera_init`，分辨率 0.05 m、滑窗 10×10×1.5 m。`projection.prior_map` 提供静态二维障碍，在线占据与先验保守合并，先验不用于清除在线障碍。

主要显示：`/rog_map/occupied`、`/rog_map/layer_value`、`/rog_map/layer_height_delta`、`/rog_map/field`；类型与完整名称在实机 `ros2 topic list -t` 核实。部分可视化只在有订阅者时构造发布，没有订阅时不发不等于地图没更新。

默认 `PRIORMAP` 在 map 下搜索/输出，`EXPLORATION` 在 camera_init 下运行，不能只切换模式而忽略目标坐标、地图边界和对应配置。`/opt_path` 是自定义轨迹消息；`/opt_path_vis` 仅用于显示，不能代替控制输入。

## 14｜目标调用、规划验证与取消

基础导航先不启动比赛 bt_manager，避免它与人工目标竞争。确认目标位于可通行区域，frame 为 map。RViz 使用项目配置的导航目标工具；`2D Pose Estimate` 一般面向 AMCL，不等于给本项目 GICP 设置初值。

### 调用完整导航

```bash
ros2 action info /navigate_to_pose
ros2 action send_goal /navigate_to_pose nav2_msgs/action/NavigateToPose \
  '{pose: {header: {frame_id: map}, pose: {position: {x: 1.0, y: 1.0, z: 0.0}, orientation: {x: 0.0, y: 0.0, z: 0.0, w: 1.0}}}}' \
  --feedback
```

`(1,1)` 是语法示例，必须换成当前地图中实际可达目标。四元数 `(0,0,0,1)` 表示 yaw=0；平面 yaw 对应 z=sin(yaw/2)、w=cos(yaw/2)。默认目标朝向验收阈值较宽（`yaw_goal_tolerance: 6.28`），不能认为到达目标必然精确朝向给定 yaw。

### 检查规划与控制输出

```bash
ros2 topic echo /opt_path --once --field header
ros2 topic echo /opt_path_vis --once --field header
ros2 topic hz /cmd_vel_mpc
ros2 topic echo /cmd_vel_mpc
```

观察顺序：目标被 action 接受 → Nav2 获取当前位姿 → planner 搜索与 MINCO FSM 优化 → `/opt_path` 参考生成 → MPC 产生速度。仅看屏幕上的一条路径不能确认当前轨迹有效、时间匹配或控制已经执行。

只调用全局路径接口的示例：

```bash
ros2 action send_goal /compute_path_to_pose nav2_msgs/action/ComputePathToPose \
  '{goal: {header: {frame_id: map}, pose: {position: {x: 1.0, y: 1.0}, orientation: {w: 1.0}}}, planner_id: MincoPlanner, use_start: false}' \
  --feedback
```

这不启动完整 FollowPath；但本项目规划插件还有内部 FSM 与轨迹发布，不能把该接口当作绝对没有控制侧影响的纯离线计算。进行单模块测试时保持通信与底盘执行关闭。

### 取消与停止验证

通过 action 的 cancel 服务取消当前导航（该示例取消全部 navigate_to_pose 目标，不取消其他 action）：

```bash
ros2 service call /navigate_to_pose/_action/cancel_goal \
  action_msgs/srv/CancelGoal \
  '{goal_info: {goal_id: {uuid: [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]}, stamp: {sec: 0, nanosec: 0}}}'
```

核对 `goals_canceling`、action 结果和真实速度；返回成功不能代替停车测试。Ctrl+C 退出客户端不保证自动取消 action。当前 MCU 是否收到清零、断流后是否自动停车必须实测；通信缓存可能保留最后一次速度，停止 ROS 进程不是可靠急停。

## 15｜舵轮底盘：坐标、单位、串口与方向测试

已知你的底盘直接接收 vx、vy，但还未确认是车体系还是世界系，也未拿到电控协议。这是接车前必须确定的事实，不能只凭“接受 vx/vy”认定兼容。

当前计算链：`/opt_path` 在 map → MPC 转到局部 costmap 的 global_frame（默认 camera_init）→ `/cmd_vel_mpc` 为该世界系 vx、vy，角速度单位 rad/s。Twist 无 header，话题自身没有附带 frame；语义由项目约定决定。

源码 `communication/include/com_interface_ros.hpp` 直接读取 `linear.x/y`，未在打包处旋转 vx/vy；angular.z 乘 `60/(2π)` 得 rpm；odom yaw 转为度，再与 `delta_yaw` 等字段打包。`custom_protocol.hpp` 的 current_yaw 注释写 rad，与赋值实现的度不一致，联调以实际编码和 MCU 解码共同确认。

| 需要电控确认 | 本项目发送侧事实 | 本车协议 |
|---|---|---|
| vx、vy 坐标系 | camera_init 世界系 | __________ |
| 平移单位 | m/s | __________ |
| 旋转速度 | 打包后 rpm；ROS 侧 rad/s | __________ |
| current_yaw | 赋值为度 | __________ |
| delta_yaw 用途/符号 | 提供 odom 与底盘 IMU 的朝向偏差 | __________ |
| 字节序、字段排列、对齐、CRC、包号 | 当前协议结构与打包实现 | __________ |
| 超时停车、急停、速度限幅 | MCU 实现尚未提供 | __________ |

若 MCU 接收车体系，需要在确定的一层做一次转换：

```text
vx_body = cos(yaw) * vx_world + sin(yaw) * vy_world
vy_body = -sin(yaw) * vx_world + cos(yaw) * vy_world
```

这里 yaw 是车体相对该世界系的朝向。不能用 map yaw 去转换 camera_init 速度而忽略坐标旋转；不要在 NUC 与 MCU 两端重复转换。

### 串口接入

```bash
ls -l /dev/serial/by-id/
ls -l /dev/ttyACM*
id -nG
sudo usermod -aG dialout "$USER"
```

加入用户组后重新登录。当前 `/dev/ttyACM0`、115200 写在 `communication/src/com.cpp`，不是 YAML 参数。若设备名不同，应明确修改源码或制定稳定设备链接；修改源码后要重新构建。仅接串口不代表包协议兼容。

基础协议已确认后启动：

```bash
ros2 launch communication com.launch.py
ros2 node info /communication_sentry
ros2 topic echo /sentry/offline_info --once
```

launch 设置 respawn=true，故障会重启；用 Ctrl+C 结束整个 launch，不只杀子节点。缺少底盘 IMU/odom 时间匹配时，代码会提示 `delta_yaw is not initialized` 并压制平移；不是看到 cmd_vel 有值就保证能动。

### 低速方向与停止测试

关闭比赛树与导航目标、停止控制器输出，确认只有一个速度发布者；先在允许测试的场地以物理急停/MCU超时停车保护。每次只测一个轴，小速度如 0.1 m/s 和 0.2 rad/s，仅为测试样例，以本车最低稳定速度为准。

```bash
ros2 topic info /cmd_vel_mpc -v
# 在无人为/自动速度竞争且底盘保护就绪时，持续 2 秒
timeout 2s ros2 topic pub -r 20 /cmd_vel_mpc geometry_msgs/msg/Twist \
  '{linear: {x: 0.1, y: 0.0}, angular: {z: 0.0}}'
# 随后持续发布零；真正停止仍需确认 MCU 执行
timeout 2s ros2 topic pub -r 20 /cmd_vel_mpc geometry_msgs/msg/Twist '{}'
```

分别测试 +X、+Y、正转，记录世界系方向、车头方向和 MCU 接收值；车体旋转 90° 后重复测试，确认世界/车体语义一致。再验证取消、掉线和重启的停止行为。未确认坐标与看门狗前，不接入自动导航。

## 16｜比赛行为树：何时启动、如何调用

比赛 `bt_manager` 与 Nav2 内部导航行为树是两层：前者选择战术与任务，后者执行一次导航目标。基础部署和人工目标测试不必启动比赛树。

入口：`src/decision/bt_manager/launch/bt_manager.launch.py`；运行代码加载 tree 目录中的 tactical、nav、stance、resource、gimbal XML。blackboard 共享比赛状态、目标、姿态与资源指令；当前 XML 中注释掉的策略不等于运行功能。

```bash
ros2 launch bt_manager bt_manager.launch.py \
  bt_debug_logs:=true bt_debug_log_to_file:=false \
  publish_area_markers:=true
ros2 node info /bt_manager_node
ros2 topic echo /sentry/game_info --once
ros2 topic echo /sentry/behaivor_send --once
```

`behaivor_send` 是代码中的实际拼写，不能自行改成 behavior_send 后期待已有订阅能接收。比赛树依赖裁判/通信输入、区域与任务点，换场地要核对相关坐标和 map→minimap。导航 launch 里的静态 map→minimap 是原赛场设置，不能直接用于新场地。

使用步骤：先验证 communication 接收状态 → 核对 blackboard 对应值 → 观察状态变化日志与区域 Marker → 确认发送的目标和行为指令 → 再允许底盘执行。人工发目标前暂停/退出策略源，避免它持续覆盖你的目标。停止树不保证取消已提交 Nav2 action，需要按第 14 节取消并核实停车。

可编辑入口：tree/*.xml 定义条件和优先级；注册的 C++ action/condition 定义实际行为；`ros_interface` 写入状态。不要只改 XML 名称或话题；枚举、blackboard、协议字段和 MCU 接收要同步核对。

## 17｜仿真：无硬件验证导航闭环

仿真可先验证算法链和调用方式，但当前 omni 模型是 Fortress MecanumDrive，并不是舵轮转向动力学模型；不能代替舵轮执行延迟与机构约束测试。

```bash
sudo apt install -y ros-humble-ros-gz ignition-fortress \
  libignition-gazebo6-dev
source /opt/ros/humble/setup.bash
source "$NAVI_WS/install/setup.bash"
ros2 pkg prefix ros_gz_sim
ros2 pkg prefix ros_gz_bridge
ign gazebo --versions
cd "$NAVI_WS"
bash simlation.bash omni rmuc_2025 --check
bash simlation.bash omni rmuc_2025
```

`--check` 仅检查依赖和环境，不启动、不验证闭环。所有包仍须先构建成功。支持脚本参数 omni/diff，world 当前脚本只接受 rmuc_2024、rmul_2024、rmuc_2025、rmul_2025。README 声称可传 rmuc_2026，但这个 shell 脚本会拒绝；2026 资源与 launch 配置存在，完整几何及导航质量未在本次验收。

```bash
# 无界面但保留算法闭环
bash simlation.bash omni rmuc_2025 --headless --no-rviz
# 如需指定关闭 ICP，直接使用 launch
ros2 launch sentry_simulation simulation.launch.py \
  chassis_type:=omni world:=rmuc_2025 use_icp:=false
```

脚本检查 package 并设置模型资源路径。仿真使用独立 `config/nav2_sim.yaml`、`point_lio_sim.yaml`、`gicp_sim.yaml`，修改实车 sentry1.yaml 不会自动改变它们。

主链：模拟双雷达/IMU → bridge 与 CustomMsg 适配 → Point-LIO → 重定位 → Nav2/MINCO/MPC → 仿真速度适配器 → 模型。不会启动真实 communication、裁判链或真车下位机。

验收：`/clock` 前进、算法节点使用 sim time、输入存在、Point-LIO 位姿更新、导航 action 被接受、轨迹与控制产生、模型运动。`/sim/ground_truth/odom` 只用于误差评价，不替代定位输入。用第 14 节目标与取消命令，目标坐标按仿真地图填写。

不要同时启动实机 Livox 和仿真传感器，避免同名话题混合；关闭仿真速度适配器不能当作真实 MCU 停车测试。

## 18｜Foxglove：本机、Windows 远程和三套面板

按 [Foxglove ROS 2 官方接入说明](https://docs.foxglove.dev/docs/getting-started/frameworks/ros2) 安装 bridge。NUC 已 source 本工程后：

```bash
sudo apt install -y ros-humble-foxglove-bridge
ros2 launch foxglove_bridge foxglove_bridge_launch.xml \
  port:=8765 address:=0.0.0.0
ss -ltnp | rg 8765
```

本机客户端连接 `ws://localhost:8765`；Windows 连接 `ws://NUC可达IP:8765`。Windows 无需另装 ROS 来使用 WebSocket。PowerShell 用 `Test-NetConnection NUC地址 -Port 8765` 检查；确保在同一可达局域网，按已有防火墙策略仅允许所需连接。

| 布局 | 面板与数据 | 用途 |
|---|---|---|
| 传感器 / 定位 | Raw CustomMsg/IMU，3D cloud_registered_full，TF，odom Plot | 输入、时间、外参、漂移 |
| 地图 / 规划 | 3D PCD/ROGMap，opt_path_vis、astar_path_vis，日志 | 对齐、障碍表达与轨迹 |
| 控制 / 性能 | cmd_vel_mpc 与 odom 速度曲线，预测路径、CSV | 跟踪、延迟、抖动、超调 |

Raw Messages 看 `/livox/lidar` 的字段；3D 优先显示标准 PointCloud2 `/cloud_registered_full`。自定义 `/opt_path` 不直接等同 Path，显示用 `/opt_path_vis`。odom twist 的体轴速度与 cmd_vel 的世界系速度不能未经转换直接逐轴比较。

有点云却看不见：先启用该话题、确认 frame_id，再用 camera_init 参考系显示；局部显示成功、切 map 失败，检查 GICP TF 与时间戳。数据离屏、裁剪、尺寸、颜色设置也可能影响显示。旧回放时间与实时 TF 混用会造成查不到变换。

布局通过客户端导出保存到 `learning/foxglove/`，记录实际话题和参考系。发目标先核对发布面板类型、frame 及订阅端，不默认所有点击工具都等价于 RViz Nav2 action。更多设置见 `learning/foxglove/README.md`。

CloudLab 后端也默认占用 8765（HTTP），与 bridge WebSocket 端口冲突；不要在同一主机同端口同时启动，必要时将 bridge 改为 8766 并同步修改客户端 URL。

## 19｜MCAP 录制、离线查看与证据保存

Humble 默认 db3 不保存完整自定义消息定义，Foxglove 离线查看自定义消息更适合 MCAP。安装和格式说明见 [Foxglove 官方录制说明](https://docs.foxglove.dev/docs/getting-started/frameworks/ros2)；录制程序必须先 source 本工程。

```bash
sudo apt install -y ros-humble-rosbag2-storage-mcap
mkdir -p "$HOME/navi_data/bags"
ros2 bag record -s mcap \
  -o "$HOME/navi_data/bags/run_$(date +%Y%m%d_%H%M%S)" \
  /tf /tf_static /aft_mapped_to_init /cloud_registered_full \
  /opt_path /opt_path_vis /cmd_vel_mpc
```

需要重新计算定位时，再加入 `/livox/lidar` 与实际主 IMU 话题；两路外参标定需要未融合的两路点云和两路 IMU。仿真额外录 `/clock`、`/sim/ground_truth/odom`，录制节点使用 `--use-sim-time`，先确认 `/clock` 已到达。

Ctrl+C 正常结束 recorder，确认 metadata.yaml 和 mcap 文件完整：

```bash
ros2 bag info /absolute/path/to/bag_directory
```

打开 `.mcap` 到 Foxglove，可以查看已经录下的结果。这不等于重新跑算法。重新计算流程见第 20 节。稠密点云录制会增加磁盘和 CPU 负载，实验必须记录录包/可视化是否启用，避免观察工具改变性能比较条件。

每次保存：源码提交、依赖版本、参数副本、地图校验、路线/初始状态、硬件外参、实验结论。大包放在 `$HOME/navi_data` 等独立目录，仓库只记录路径，不把数 GB 数据直接放 learning。

## 20｜传感器回放：让算法重新计算

目标是使用固定原始传感器数据验证参数或算法。先断开底盘执行、退出真实 Livox 驱动和比赛策略，不把历史控制话题直接重放到真实底盘。

1. 从 `ros2 bag info` 确认 CustomMsg 与主 IMU 已录制，话题类型与名称正确。
2. 复制 Point-LIO 配置，在 `ros__parameters` 中设 `use_sim_time: true`，话题指向 bag 原始输入；复制 GICP 配置同样设置 sim time。
3. 检查独立 Point-LIO launch 的输入覆盖逻辑；用它启动 LIO，避免主组合 launch 同时启动真实驱动。

```bash
ros2 launch point_lio point_lio.launch.py --show-args
ros2 launch point_lio point_lio.launch.py \
  point_lio_cfg_dir:="$HOME/navi_configs/point_lio_replay.yaml" \
  rviz:=false
```

当前独立 launch 支持 `point_lio_cfg_dir`，运行 `pointlio_mapping`，只启动 LIO，不启动真实驱动。上面的 replay.yaml 是提前复制并修改好的配置；直接写 `use_sim_time:=true` 到 launch 命令并不会替代未声明的参数，需在该 YAML 里配置。节点名与组件入口可能不同，用 `ros2 node list` 核实。

随后只播放原始输入，并由 bag 提供 ROS 时钟：

```bash
ros2 bag play /absolute/path/to/raw_bag --clock \
  --topics /livox/lidar /livox/imu_192_168_1_135
```

不要同时播放旧 `/aft_mapped_to_init`、旧点云输出和旧 `/tf`，否则它们会与新计算结果混合。需要导航回放时使用 `use_sim_time:=true` 启动导航，所有节点必须采用同一时基，禁用真实通信。

传感器 QoS 不兼容时先查看订阅/播放 QoS，按 [rosbag2 Humble 官方说明](https://github.com/ros2/rosbag2/tree/humble) 使用 override 文件。比较结果必须使用同一播放速度、同一初值、同一数据及参数。系统当前时间减历史 header 时间，不是算法延迟。

## 21｜每天启动、停止、重启与版本记录

### 每次开机

1. 检查供电、急停和下位机状态；确认本车设备表与配置一致。
2. 打开各终端，source Humble 与唯一正确工作空间，cd 到仓库根目录。
3. 确认网卡地址、两颗雷达 UDP 和时钟策略；启动时间同步。
4. 启动驱动/LIO，静止初始化；检查消息与局部点云。
5. 启动 GICP，确认正确配准且未回退；检查 map→base_link。
6. 启动导航，确认 lifecycle active 和目标链。
7. 底盘协议已验收后启动 communication；确认 yaw 匹配与反馈。
8. 按任务启动 Foxglove/录包；最后才启动比赛树。

### 正常停止

先暂停策略目标源，取消导航 action，确认速度清零和实车停止；然后结束策略、导航、communication、GICP、LIO、录包与 PTP。必须依赖下位机看门狗/物理急停处理断流，不能只关闭终端。保存 PCD 时需等待 LIO 正常析构；录包正常 Ctrl+C 保存 metadata。

### 一键脚本的使用边界

`start.bash` 固定 `cd ~/2027-sentry-navi`，GNOME 桌面开多个终端；固定 sleep 不验证节点 ready，且会自动启动比赛树和通信。首次部署完成后，可自己备份并调整工作路径、PTP 网卡、地图/参数入口和启动顺序。不在无桌面 SSH 环境直接使用该脚本。

当前 start 的 cloud crop、Foxglove 和 rosbag 命令被注释，不会自动运行。`scripts/pcd.bash`、`play.bash` 含旧工作目录和另一套驱动入口，不作为本文推荐部署入口。

### 保存可复现记录

```bash
mkdir -p "$HOME/navi_data/deployment_$(date +%Y%m%d)"
git rev-parse HEAD
git diff --stat
ros2 pkg prefix --share navi2
ros2 param dump /laserMapping
ros2 param dump /planner_server
ros2 param dump /controller_server
sha256sum /absolute/path/site_a.pcd /absolute/path/site_a.pgm \
  /absolute/path/site_a.yaml
```

把输出与参数副本、设备表、bag 路径一起保存。只记录提交号而不记录未提交配置，会遗漏真实运行版本。后续更新源码前保留工作区修改，不用覆盖本车配置的命令“恢复默认”。

## 22｜故障速查：从现象定位模块

| 现象 | 首先检查 | 后续证据与处理 |
|---|---|---|
| 雷达 ping 不通 | 供电、网卡、掩码、路由和真实 IP | ip route get；设备工具确认 IP |
| ping 通但无点云 | JSON 主机接收 IP、UDP、端口占用 | tcpdump、ss、驱动日志；ping 不是全链验收 |
| 合并点云缺一侧 | 两路 UDP、配对时间、融合诊断 | IP 选错、丢包或窗口不足；不要只看合并频率 |
| 点云正常无 odom | 组件、主 IMU 订阅、时间覆盖和初始化 | node info、param get、时间戳、队列 |
| odom 有频率但机器人位置滞后 | 输入到达、同步等待、计算耗时与队列 | 平均/p95/p99、状态时间；频率不代表新鲜 |
| 旋转时点云重影 | 双雷达外参、时间与去畸变 | 同场景静止/旋转对照，不先调规划权重 |
| 局部点云清晰但整片地图错位 | GICP 地图、初值、回退 | 确认日志、source_aligned/target 和 CSV |
| map TF 一直有但位置错误 | 是否默认位姿、配准质量 | TF 存在只说明坐标链可查询 |
| TF future/past extrapolation | 请求时间、发布时钟、缓存范围 | 检查 sim time、历史 bag、变换更新时间 |
| PCD 对齐但 PGM 平移 | 二维 YAML origin x/y | 不调整 resolution 去补平移 |
| PGM 尺寸与 PCD 不一致 | resolution 与地图生成尺度 | 核对已知墙角距离 |
| planner 不在节点列表 | 目标容器、组件插件与安装环境 | component list、加载日志 |
| planner 存在但 unconfigured | 规划插件、资源路径、初始化错误 | YAML 插件与注册 XML 一致；首个错误 |
| 目标被拒绝 / 不产生轨迹 | 生命周期、action、TF、可通行目标 | 看 ComputePath 与 FSM，地图输入超时 |
| 有 opt_path_vis 但无 cmd_vel_mpc | 实际 opt_path、MPC 状态、TF、求解 | 不能拿显示消息代替控制参考 |
| cmd_vel 有值底盘不动 | 通信订阅、串口反馈、delta_yaw | 打包结果、MCU 解码/使能、协议一致性 |
| 速度方向与车头不符 | 世界/车体约定、yaw 符号、重复旋转 | 固定轴、车体转90°、单轴低速测试 |
| 取消后仍运动 | 目标是否取消、最后命令缓存、MCU看门狗 | 物理停止后查发送零与断流行为 |
| Foxglove 连不上 | bridge监听、IP路由、端口和冲突 | ss、Windows Test-NetConnection、CloudLab8765 |
| 录包自定义消息看不到 | source正确工程、MCAP schema | 不仅是文件后缀问题 |

网络诊断脚本示例（按当前 JSON 的主机点云端口 56300 覆盖脚本默认 56301）：

```bash
sudo bash scripts/monitor_livox_network.sh \
  --lidar-ip 192.168.1.122 --interface "$NAVI_IFACE" \
  --host-point-port 56300 --duration 60
```

Point-LIO 性能开关 `runtime_pos_log_enable`，路径默认 `/tmp/point_lio_log`；MINCO、ROGMap、MPC 的 performance 参数分别在自身命名空间中。通信诊断可单独运行 `ros2 run communication communication --ros-args -p communication.enable_performance_diagnostics:=true`，不要与已有通信 launch 重复启动。

## 23｜辅助功能调用卡

每张卡按“输入/配置 → 调用 → 输出 → 核对”使用。不是所有工具都位于默认主链中。

### 点云裁剪过滤：msg_convert

输入 `/cloud_registered`，默认输出 `/cloud_registered_filtered`；配置 `src/perception/msg_convert/config/cloud_registered_crop_filter.yaml`。默认 box 与 map 坐标来自原比赛场地，先替换区域，再运行：

```bash
ros2 launch msg_convert cloud_registered_crop_filter.launch.py
ros2 topic info /cloud_registered_filtered -v
```

检查 remove_inside、position_frame、z_offset、盒子 Marker。仅启动过滤节点不会自动让规划器改订阅 filtered；需要明确修改所需下游配置。ROGMap 内部 cloud_filter 是另一处理入口，当前默认关闭，不要无意双重过滤。

### DBSCAN 障碍聚类：dbscan_cluster

配置 `config/dbscan_cluster.params.yaml`，默认输入 `/cloud_registered`，输出 `/clustered_obstacles`。高度范围、簇尺寸和动态阈值是原车值。

```bash
ros2 launch dbscan_cluster dbscan_cluster.launch.py
ros2 node info /dbscan_cluster_node
ros2 topic info /clustered_obstacles -v
```

观察分簇、关联和丢失帧；本次未确认该输出已经接入 MINCO 主链，不把启动聚类当作自动获得规划动态障碍功能。

### 高程图：pcd2ele

修改 `config/pcd2ele.yaml` 的 pcd_file_path、output_folder、output_name、resolution 与过滤参数，输出目录先创建：

```bash
ros2 launch pcd2ele pcd2ele.launch.py use_sim_time:=false
```

检查实际生成的高程文件与日志。该 launch 默认 sim time true；本节显式覆盖。不把离线高程工具当作正在导航的 ROGMap 地形投影。

### 二维距离场：pcd2esdf

虽然包名叫 pcd2esdf，当前节点 `pgm2esdf_generator` 从地图 YAML/图片生成 ESDF PCD。改 `config/pcd2esdf.yaml` 的 map_yaml、output_pcd、占据阈值和 unknown 策略：

```bash
ros2 launch pcd2esdf pcd2esdf.launch.py
```

核对输出路径与距离值符号、截断范围；它与规划器内部实时 ESDF 是不同生成路径，不会因导出文件自动替换在线距离场。

### CloudLab 高级处理

基础页面见第 11 节。高级后端需要 NumPy、Open3D；推荐使用单独 Python 虚拟环境，避免污染 ROS Python：

```bash
python3 -m venv "$HOME/navi_deps/cloudlab_env"
source "$HOME/navi_deps/cloudlab_env/bin/activate"
python -m pip install numpy open3d
python src/utils/pcd_trans/point_cloud_lab_server.py
```

缺少 venv 时安装 python3-venv。压缩 PCD、去噪、聚类、动态残影和网格处理按页面入口使用；STEP 额外需要 FreeCAD。后端默认127.0.0.1:8765，仅本机；处理结果需要页面确认下载，不自动修改导航配置。

### 在线二维地图保存

```bash
bash scripts/savemap.bash /map maps/site_a/site_a_snapshot
```

`/map` 必须有真实 OccupancyGrid 发布者。脚本按指定话题保存，不会自动从 Point-LIO 完整点云生成二维地图；先运行 pcd2pgm 或其他已验证栅格发布器。

## 24｜调参入口、真实生效方式与当前陷阱

| 模块 | 优先参数族 | 指标 |
|---|---|---|
| Point-LIO | 点滤波、体素、batch、噪声与 iVox | 漂移、点云重影、耗时、队列 |
| GICP | 初值、裁剪、体素、质量与稳定窗口 | 成功率、时间、误接受、回退 |
| ROGMap | 分辨率、滑窗、概率、衰减与投影 | 障碍出现/清除、通道、耗时 |
| MINCO | 速度/加速度、安全距离、前视、代价 | 到达率、距离、规划耗时、失败 |
| MPC | dt、lookahead_time、R、约束与补偿 | 跟踪误差、指令抖动、超调、求解耗时 |

当前 MPC：`dt=0.05`、`lookahead_time=0.5`；内部 `horizon=ceil(lookahead_time/dt)=10`。源码虽声明 horizon 参数，但实际由公式产生。`/opt_path.mpc_horizon` 则是参考采样数量，不是控制器求解步数。

**Q 配置与实现存在差异：** YAML 的 Q 被读取为三元向量，但 `mpc_solver.cpp` 平面代价使用 `mpc_types.hpp` 中 `q_along=3`、`q_cross=12`，当前未见它们由 YAML Q 前两项赋值或作为 ROS 参数加载；yaw 使用 `Q.z()`。因此修改 Q 前两项不能据此认为平面权重改变。此前课堂将其理解为 Q 前两项是过度简化，部署以此处源码核查为准。R 用于输出控制与参考速度/角速度的偏差，不是直接惩罚相邻控制变化。

控制目标100 Hz，与模型 dt=50 ms不同。加速度约束约束预测步间速度差，不能直接当作每10 ms发送命令严格变化上限。`vx/vy ±3` 是分轴界限，不等于合速度≤3；同时两轴3时合速度约4.24 m/s。舵轮本车约束必须按合速度和机构能力核对。

首次接车建议建立自己的低速配置副本，同时限制 planner 的 `MincoPlanner.minco_optimizer.max_velocity/max_acceleration/max_yaw_dot` 与 controller 的 `FollowPath.vx/vy/omega`、加速度约束。原 `min_turn_vel=0.7`、`recovery_server.escape_speed=0.5` 等也要与低速测试一致；不要只把其中一个上限改小却保留更高的恢复速度。本文不替你修改运行参数，不给未经测试的“最优参数”。

ROGMap `projection.scan_z_*_abs` 是绝对 Z，ground/step/tunnel 的 height_delta 是高度差；三维 decay 的 keep/clear 时间与二维 obstacle_hold_time 不同。MPC 的安装偏移与 Point-LIO base_link 偏移必须一致，外参和时间单位先校准，不能作为优化旋钮试错。

固定路线重复至少三次，每次只改一个参数族，保存旧值/新值、单位、是否重启、预期与代价。一起看平均误差、尾部耗时、队列、停止距离和失败样本；平均变好不代表整体优化成功。

## 25｜接口速查与源码定位

| 接口 | 类型 / frame | 发布与消费 |
|---|---|---|
| `/livox/lidar` | livox_ros_driver2/msg/CustomMsg / livox_frame | 驱动融合 → Point-LIO |
| `/livox/imu_<ip>` | sensor_msgs/msg/Imu | 驱动 → 选定主 IMU 的 LIO |
| `/aft_mapped_to_init` | nav_msgs/msg/Odometry / camera_init、body | LIO → 规划、控制、通信 |
| `/cloud_registered_full` | sensor_msgs/msg/PointCloud2 / camera_init | LIO → GICP、ROGMap |
| `/cloud_registered` | PointCloud2 / camera_init | LIO → STVL/辅助处理 |
| `/opt_path` | ros_interfaces/msg/MpcPositionCommand / 默认 map | MINCO → MPC |
| `/opt_path_vis` | nav_msgs/msg/Path | MINCO → 显示 |
| `/cmd_vel_mpc` | geometry_msgs/msg/Twist / 约定 camera_init | MPC → communication |
| `/mpc_predict_path` | nav_msgs/msg/Path | MPC → 显示/记录 |
| `/tf`、`/tf_static` | tf2_msgs/msg/TFMessage | 坐标发布 → TF查询 |
| `/gicp_recall` | std_srvs/srv/Trigger | 外部调用 → 重定位状态重置 |
| `/navigate_to_pose` | nav2_msgs/action/NavigateToPose | 人工/策略 → Nav2 |
| `/compute_path_to_pose` | nav2_msgs/action/ComputePathToPose | Nav2/外部 → planner |
| `/sentry/behaivor_send` | ros_interfaces/msg/Behavior | bt_manager → communication |
| `/sentry/*_info` | ros_interfaces 自定义消息，实机查类型 | communication → bt_manager |

完整 QoS 用 `ros2 topic info <话题> -v` 查看；不是所有接口都 reliable，传感器与高频里程计需要特别核对。调试不要默认添加第二个同名发布者。

### 源码定位

| 想读的行为 | 源码位置 |
|---|---|
| 主 launch 覆盖 IMU | `Point-LIO/launch/livox_pointlio_intra_process.launch.py` |
| IMU/点云回调、sync_packages | `Point-LIO/src/li_initialization.cpp` |
| LIO 处理、TF、PCD 保存 | `Point-LIO/src/laserMapping.cpp` |
| GICP 状态机、回退和 recall | `icp_relocalization/src/gicp_ros_interface.cpp` |
| GICP 平面 TF 输出 | `icp_relocalization/src/gicp_utils.cpp` |
| 规划模式与坐标 | `minco_planner/src/minco_core/components/planner_mode_context.cpp` |
| MINCO 主流程/FSM | `minco_planner/src/minco_core/minco_planner.cpp` |
| 轨迹消息采样发布 | `minco_planner/src/minco_core/minco_utils.cpp` |
| MPC 输入、参考与发布 | `minco_controller/src/minco_mpc_controller.cpp` |
| MPC QP 与约束 | `minco_controller/src/mpc_solver.cpp` |
| MPC 默认配置 | `minco_controller/include/minco_controller/mpc_types.hpp` |
| 串口、速度字段打包 | `communication/src/com.cpp`、`include/com_interface_ros.hpp` |
| 比赛树装载 | `bt_manager/src/bt_manager.cpp`、`tree/*.xml` |

本表路径的包目录见第 02 节，均相对 src 下对应模块；可用全文件索引直接打开。

在仓库根目录按函数或接口搜索，可从“谁发布、谁订阅”追到具体实现：

```bash
rg -n 'publishOptimizedTrajectory|/opt_path' src/navigation
rg -n 'transformPathToOdom|cmd_vel_mpc' src/navigation/minco_controller
rg -n 'sync_packages|imu_cbk' src/perception/Point-LIO/src
rg -n 'publishDefaultPose|gicp_recall' src/perception/icp_relocalization
```

查到函数定义后先读调用入口、输入类型和参数，再读算法内部。注册 XML 与 CMake 负责插件发现/安装；节点名字并不总与目录名字一致。README 讲用途，源文件和实际 launch 决定当前运行行为。

## 26｜已确认的文档差异与部署待办

本手册以本地静态代码为准，保留原源码和比赛参数，没有为了说明书修改算法。

| 差异 / 未确认项 | 本手册处理 |
|---|---|
| README 的旧克隆分支/目录 | 下载以自己的独立仓库为准 |
| README 说 start 自动录包 | 当前录包与 Foxglove 行被注释，需单独启动 |
| README 与 start 工作目录不同 | 实际 start 为 ~/2027-sentry-navi |
| 融合外参多套值 | 主组合入口以 component YAML 为准 |
| IMU YAML 被 launch 覆盖 | 用实际 launch 参数明确主 IMU |
| GICP TF 存在不等于成功 | 核对 confirmed、回退与几何对齐 |
| README 描述通信坐标转换 | 打包处直接 vx/vy + yaw/delta，MCU责任未核实 |
| current_yaw 注释 rad、赋值度 | 接口必须与 MCU 联调确认 |
| Q 前两项与平面权重不同 | 标出源码 q_along/q_cross，不宣称参数生效 |
| 仿真 README 含 rmuc_2026 | shell入口当前拒绝，默认用rmuc_2025 |
| 实车 TF 有特殊 base_link 实现 | 明确当前姿态/偏移，不套用一般模板 |
| 默认导航 include AMCL | 未确认 scan链有效，避免重复定位TF |
| start固定 sleep | 不视作就绪检测 |
| 本机无 NUC/hardware 验证 | 所有运行门槛保留待实操 |

完成清单：填写设备表；确认依赖版本；构建并检查插件；网络与双雷达标定；静止/旋转LIO；制作同源地图；GICP正确配准；导航action/取消；舵轮坐标与MCU看门狗；低速实机路线；录包与重启复现。每项记录日期、版本、日志/数据位置和未解决问题。

学习上下文保持：课堂停在 MPC 预测时域、权重和约束；A03 构建与 A04 Foxglove 被用户暂时跳过，仍为待实操。本手册完成不代表这些课已验收。

## 27｜依据、更新方式与查阅入口

本地依据：root `start.bash/build.bash`；各包 CMake/package.xml；实车和仿真 launch；驱动 JSON/YAML；Point-LIO、GICP、MINCO/MPC、ROGMap 与 communication 的实际输入输出代码；工具配置和 README。源文件优先于 README 中的过期示例。

外部说明核对于 2026-10-03 至 2026-10-04。下列链接用于安装和通用工具说明；算法和实车接口结论来自本地源码，不从外部教程推断本车协议。

| 来源 | 查阅用途 |
|---|---|
| [ROS 2 Humble 官方安装](https://docs.ros.org/en/humble/Installation/Ubuntu-Install-Debs.html) | ROS 软件源与基础安装；并核对官方文档原文 |
| [Livox SDK2](https://github.com/Livox-SDK/Livox-SDK2) | SDK C++ 安装 |
| [Livox MID-360 协议](https://livox-wiki-en.readthedocs.io/en/latest/tutorials/new_product/mid360/livox_eth_protocol_mid360.html) | 网络、数据与时钟字段 |
| [small_gicp C++](https://github.com/koide3/small_gicp#installation) | C++ 头文件与依赖安装 |
| [Sophus](https://github.com/strasdat/Sophus) | 原版 C++ 几何库 |
| [Foxglove ROS 2](https://docs.foxglove.dev/docs/getting-started/frameworks/ros2) | bridge、WebSocket、MCAP |
| [rosbag2 Humble](https://github.com/ros2/rosbag2/tree/humble) | 录制、播放、QoS与时钟 |

维护时修改 `learning/manual/NAVI_MINCO_BIT_USER_MANUAL.md`；PDF 为查阅快照。新版本必须重新核对 launch、话题、frame、协议和路径，并更新封面日期与源码版本。部署成功后填入自己的运行证据，保留失败案例。

配套资料：`learning/ROADMAP.md` 学习路线；`learning/PROGRESS.md` 课程证据；`learning/PROJECT_INDEX.md` 全文件索引；`learning/NAVI_MINCO_BIT_FLOWCHART.md` 完整架构；`learning/templates/EXPERIMENT_RECORD.md` 调参记录。
