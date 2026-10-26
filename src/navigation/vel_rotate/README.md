# vel_rotate

导航主机上的速度转换节点。订阅 `/cmd_vel_mpc` (`geometry_msgs/msg/Twist`) 和
`/serial/receive` (`rm_interfaces/msg/SerialReceiveData`)，读取其中的 `big_yaw`（度），
发布 `/cmd_vel_rotate` (`geometry_msgs/msg/Twist`) 给 Docker 中的 QYG 串口驱动。
QoS 均采用 ROS sensor data 配置，兼容 QYG 串口反馈和订阅端。

## Foxglove 速度对比（机器人主机）

保持导航和串口运行，在另一个普通终端执行（无需构建）：

```bash
bash ~/2027-sentry-navi/src/navigation/vel_rotate/scripts/foxglove_velocity.bash
```

在主机的 Foxglove 中连接 `ws://127.0.0.1:8765`，通过 Layouts → Import from file 导入：

```text
/home/robomaster/2027-sentry-navi/src/navigation/vel_rotate/config/foxglove_velocity.json
```

三个速度图分别比较 X/Y 线速度（m/s）和 Z 角速度（rad/s）：

- 蓝色：`/cmd_vel_rotate`，导航转换后的底盘指令。
- 橙色：`/serial/send` 的 linear_x/linear_y/angular_z，串口驱动打包的发送值。
- 绿色：`/cmd_vel_real`，从电控 chassis_vx/chassis_vy/chassis_wz 原值发布的反馈；
  用户于 2026-10-24 确认这些是编码器计算的实际速度。

第四图显示 `/serial/receive.big_yaw`（度）。不要直接用转换前 `/cmd_vel_mpc` 的
X/Y 分量与底盘坐标系的编码器 X/Y 比较。

所有曲线统一使用接收时间（Log/Receive time）。实测 `/serial/send.header.stamp`
为零，不能用它作时间轴；接收时间也不能用于精确测量执行器延迟。
发送值只表示驱动准备打包的指令，不是电控接收回执。
静止时这些速度应接近零；只有正常运动的非零指令样本才能评价跟随误差和滞后。

桥仅绑定本机、只开放五个速度相关话题，客户端不具备发布控制消息或调用服务的能力。
本机已安装 foxglove_bridge 3.4.2，实测使用 `foxglove.sdk.v1` 协议；
需要支持该协议的 Foxglove 客户端，可使用当前 Web 版。
若桥已运行，直接连接，不要再次执行脚本占用同一端口。
官方说明：[导入布局](https://docs.foxglove.dev/docs/visualization/layouts)、
[Plot 面板](https://docs.foxglove.dev/docs/visualization/panels/plot)。

## 主机与 Docker 的固定启动方式（2026-10-23 联调）

每条命令在一个主机普通终端运行，无需先执行 `rv`，无需重新构建：

```bash
# 终端 1：按原 bringup_SingleProcess.launch.py 启动完整视觉与串口，附带 UDP 修复
bash ~/2027-sentry-navi/src/navigation/vel_rotate/scripts/qd_bridge.bash vision

# 仅需单独调试串口时，用 serial 替代 vision，二者不能同时运行
bash ~/2027-sentry-navi/src/navigation/vel_rotate/scripts/qd_bridge.bash serial

# 终端 2：主机速度转换。若导航 launch 已启动 vel_rotate，不再执行此条
bash ~/2027-sentry-navi/src/navigation/vel_rotate/scripts/qd_bridge.bash rotate

# 终端 3：查看电控反馈角度
bash ~/2027-sentry-navi/src/navigation/vel_rotate/scripts/qd_bridge.bash yaw

# 终端 4：查看串口驱动准备发送的协议值
bash ~/2027-sentry-navi/src/navigation/vel_rotate/scripts/qd_bridge.bash send
```

默认容器名为 `rv_devel_`，QD 工作区为 `/home/robomaster/QD_Vision26`；
可分别通过 `QD_CONTAINER`、`QD_WORKSPACE` 环境变量指定。
全部中断后重新运行以上命令；脚本会阻止重复启动串口或独立转换节点。
`vision` 原样调用完整视觉 launch；`serial` 单独运行相同驱动与串口参数，
仅关闭依赖视觉服务的模式同步，避免无视觉服务时等待。
两者互斥，保证只有一个进程占用串口。脚本统一使用 ROS domain 0，与原 launch 一致。

脚本将 Fast DDS 的这一条通信链路固定为 UDPv4。对照实验中默认传输在容器内
收不到主机 20 Hz 速度；仅改变 UDP 配置后，12 秒收到 241 条，并恢复串口写入。
配置仅作用于由脚本启动的进程，不改 topic、QoS、控制算法或点云通信配置。
`--no-daemon` 用来避免 CLI 缓存干扰，不能替代 UDP 传输配置。

启动 `vision` 或 `serial` 前，脚本还会按串口 YAML 中的 `port_name` 清除
继承的 `PARMRK` 标志，保留其他串口设置。实测该标志会把反馈里的 `0xFF`
变成两个字节，使 43 字节 QYG 帧长度与 CRC 失配。关闭后曾实测 4 秒收到
4000 条真实反馈；电控自身需要开启周期反馈发送。

`/serial/send` 在调用 UART write 之前发布，只证明进入发送回调；
只有写入返回值等于帧长（当前 34 字节）才能证明驱动已将整帧交给串口设备，
电控成功接收和解析仍需电控侧确认。
若 `/serial/receive` 没数据，即使 `/cmd_vel_rotate` 持续为零也不代表反馈正常，
这是缺少角度或 MPC 输入时的超时保护。

通信顺序：

```text
电控 TX → USB 串口 RX → Docker serial_driver → /serial/receive.big_yaw
                                               ↓ UDP
主机 MPC → /cmd_vel_mpc → vel_rotate（使用 big_yaw）→ /cmd_vel_rotate
                                                       ↓ UDP
电控 RX ← USB 串口 TX ← Docker serial_driver（按原值打包）
                              └→ /serial/send（发送前的观测话题）
```

2026-10-23 早期对照结果：完整 launch 与独立串口启动均有发送，但反馈为 0。
串口描述符连续 `poll(POLLIN, 100ms)` 超时，驱动没有读到反馈字节；
这发生在 QYG 帧解析之前，不能据此归咎于 ROS 消息定义或 big_yaw 字段。
确认电控已上电后，应从电控 TX 的周期发送、TX/RX/GND 接线、实际端口与
921600/8N1 参数核对；不能由主机单方面证明电控已发送或已解析导航指令。
底盘方向是否正确仍需有真实反馈后的单独实车验证。
后续电控开启反馈后，已读取到 GD 帧头，发现上述 PARMRK 转义问题并恢复真实反馈。

平移按 `x'=x cosθ-y sinθ`、`y'=x sinθ+y cosθ` 转换，`θ=big_yaw`。
例如 `+90°` 时 `(1,0)` 变为 `(0,1)`。输出角速度是 MPC 的 `angular.z`
加上 `init_spin_speed`，也可以由 `/cmd_spin` (`example_interfaces/msg/Float32`)
在运行时更新附加角速度。`init_spin_speed` 默认 `0.0 rad/s`。
这沿用 fake_vel_transform 的自旋叠加语义，舵轮的平移和自转仍是独立控制量。

`sentry1.yaml` 的 `vel_rotate.ros__parameters` 可设置 `init_spin_speed` 和
`timeout_sec`。当反馈或 MPC 指令超过 `timeout_sec`（默认 0.25 s）未更新、
`big_yaw` 或速度非有限值时，节点发零速度。节点运行中会每 50 ms 检查一次超时。

主机需要能加载 QD 工作区的 `rm_interfaces`：

完整导航还需要本仓库的 `rog_map`、`ros_interfaces`、`minco_planner` 和
`minco_controller` 已构建安装；这四包已于 2026-10-23 经用户授权构建通过。
STVL 和 OpenVDB 运行依赖已于 2026-10-23 安装并验证加载成功。其他主机若尚未安装，执行一次：

```bash
sudo apt-get install --no-install-recommends ros-humble-spatio-temporal-voxel-layer
```

它会同时安装 OpenVDB 运行依赖，不需要重新编译导航。本机后续隔离回放已使用
正式安装包，不再依赖此前解包到 `/tmp` 的临时 STVL 二进制库。

```bash
cd /home/robomaster/2027-sentry-navi
source /opt/ros/humble/setup.bash
source /home/robomaster/QD_Vision26/install/setup.bash
source /home/robomaster/2027-sentry-navi/install/setup.bash
# 仅加载现有转换单包，保留本仓库的雷达驱动和 Point-LIO。
source /home/robomaster/fwh/install/pointcloud_to_laserscan/share/pointcloud_to_laserscan/local_setup.bash
export ROS_DOMAIN_ID=0
export ROS_LOCALHOST_ONLY=0
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export FASTRTPS_DEFAULT_PROFILES_FILE="$PWD/src/navigation/vel_rotate/config/fastdds_udp.xml"
export FASTDDS_DEFAULT_PROFILES_FILE="$FASTRTPS_DEFAULT_PROFILES_FILE"
# 在本终端输入密码，供 launch 内的非交互 sudo 使用；ROS 节点仍以普通用户运行。
sudo -v
ros2 launch navi2 navigation2.launch.py \
  map:="$HOME/maps/mapping_20261020_224258/map.yaml"
```

这个导航入口现在默认同时启动：PTP（`sudo -n bash
/home/robomaster/mid360-ptp/start.sh enp2s0`）、mixed 双雷达驱动 + Point-LIO、
地面投影和 `/scan`、AMCL/地图服务、导航/RViz，以及一个速度转换节点。
PTP 脚本退出时结束导航；
PTP 启动事件之后再提交传感器启动动作，并不表示雷达已达到时间同步精度。
退出时由 launch 通知 sudo/PTP 脚本清理其子进程，未对全机 PTP 执行 killall。
串口仍单独使用本页的 `qd_bridge.bash serial`，不会自动重复启动。

如果 PTP 和传感器已经运行，在导航命令后加
`start_ptp:=false start_sensors:=false`；不要同时再启动原有 mixed launch。
这两个开关只复用已有进程，不校验其参数或健康状态；已有普通容器不会自动获得
本次专用执行器和预加载环境，建议退出旧容器后由导航入口重新启动。
网口、PTP 脚本可用 `ptp_interface:=enp2s0`、`ptp_script:=/实际路径/start.sh` 指定。
mixed 入口固定使用安装包中的 `mixed_MID360_component.yaml`、
`mixed_MID360_config.json`、`mid360.yaml`，主 IMU 覆盖为 `.100`；
Nav2 与速度转换共同读取 `params_file`（默认 `sentry1.yaml`）。
入口会将完整导航参数文件传给新建的容器进程，保证规划器内部的
`global_costmap` 也读取同一配置。单独启动的旧容器不会自动补传这份进程参数，
初次使用本入口请停止旧传感器 launch 后重新启动；复用模式未验收该配置传递。
ROGMap 的先验 YAML 随 `map:=...` 一起覆盖，PGM 由该 YAML 的 `image` 指定，
避免加载自建地图时仍叠加历史比赛地图；原参数文件的比赛值保留。
本入口不启动历史 crop_filter，局部 STVL 改订阅实际存在的
`/cloud_registered_full`，其余避障配置不调优。

二维地图定位现在由 `/cloud_registered_full` → 地面投影 `/scan` → AMCL 提供。
`projection_config` 默认读取与建图相同的 `dual_lidar_mapping.yaml`，结合实际
`mid360.yaml` 的雷达—IMU外参计算 `slambase → mapping_ground` 向下约
0.37711 m 的变换，沿用离地 0.10—1.20 m 截取范围。
AMCL 参数在 `sentry1.yaml`：`global_frame_id=map`、
`odom_frame_id=camera_init`、`base_frame_id=mapping_ground`，订阅 `/scan`，
采用支持横移的 `nav2_amcl::OmniMotionModel`，发布 `map → camera_init`。
这里只加载转换单包，不要 source 整个 fwh 工作区；也可由用户安装
`ros-humble-pointcloud-to-laserscan` 后替代该单包环境加载。

启动后在 RViz 的 `map` 坐标下，用 **2D Pose Estimate** 设置当前雷达地面投影
的大致位置和朝向，观察扫描与墙面吻合、定位稳定后再用 **Nav2 Goal** 设置近处目标。
AMCL 不会在启动时假定机器人位于地图原点；不要同时启动发布同一地图变换的建图/GICP。
已在独立 ROS 域回放静止 bag，确认 `/scan`、AMCL active、`/amcl_pose` 和
`map → camera_init` TF 接通；这不是实车动态导航或定位精度验收。
正式安装 STVL 后再次回放，九个生命周期节点均进入 active，
运行时确认两处地图路径一致以及局部 STVL 点云订阅存在；
退出回归采样收到 188 帧扫描、1 条 AMCL 位姿和 145 条地图 TF。
但规划器容器在 Ctrl+C / 生命周期清理时仍会崩溃，退出验收未通过；
不能据此宣称整套导航已通过实车验收，详见
`docs/ai_refactor_records/20261023_navigation_plugins_validation.md`。
后续已授权在 `/tmp` 构建同版 rclcpp 验证，构建成功但退出仍失败；
该临时库不应加入正式启动环境，系统 ROS 保持原状。证据见
`docs/ai_refactor_records/20261023_rclcpp_shutdown_validation.md`。
2026-10-24 后续组合验证通过后，已获用户授权接入正式导航入口：
地图析构保护、容器专用 rclcpp、导航进程预加载 STVL。专用库保存在本仓库并安装到
`install/navi2/lib/navi2/runtime/librclcpp.so`，普通 source 工作区仍使用系统 rclcpp。
**以上导航启动命令不变，无需手动导出库路径或 source /tmp overlay。**
单独 Point-LIO 和建图入口保持原来的环境；导航启动的新容器同时承载驱动、Point-LIO 和规划器。
全局加载临时 rclcpp 曾出现启动超时，因此专用库只供该容器使用。
正式安装路径的点云回放和原始 Livox/IMU → Point-LIO 回放均通过启动及两种退出检查，
仍需现场验证真实驱动、PTP、初始定位及动态导航。专用库复现方法见
`src/navigation/navi2_bringup/runtime/README.md`；本轮记录见
`docs/ai_refactor_records/20261024_navigation_shutdown_integration.md`。
安装 roll 正负和外壳中心到点云原点的小偏移仍沿用建图时的候选测量，需现场核验。
Point-LIO 原 `base_link` 仍使用历史 `(0, 0.20, 0)` 偏移，需按本车安装验证。

上面的导航 launch 会启动速度转换节点。若只想单独运行转换节点，不启动导航 launch：

```bash
ros2 run vel_rotate vel_rotate_node --ros-args \
  --params-file /home/robomaster/2027-sentry-navi/src/navigation/navi2_bringup/params/sentry1.yaml
```

同一时刻只运行一个转换节点。`start.bash` 还会启动旧 `communication`
串口进程；采用 QD Docker 串口链路时，应分别启动需要的模块，避免两套串口进程竞争设备。
QD 的 `qyg_sentry` 仍保留旧 `/cmd_chassis` 入口，联调时确认没有其他发布者。

`big_yaw` 只描述云台角度。若 MPC 世界系方向与底盘方向之间还包含车身转角或
固定安装角，这个单角变换不足以保证实车方向正确，必须先架空车轮或低速验证。
QD 新协议将 `/cmd_vel_rotate` 的 `linear.x`、`linear.y`、`angular.z`
直接写入 34 字节帧的 `linear_x`、`linear_y`、`angular_z`（偏移分别为
11、15、19），不再取反或限幅，仅转换为协议要求的 `float32`。
该修改需要构建 QD 的 `rm_serial_driver` 并重启原串口进程后生效。
