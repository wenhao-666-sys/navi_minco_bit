# A04 / A11：Foxglove 接入与数据复盘手册

更新：2026-09-28。适用：Ubuntu 22.04、ROS 2 Humble、NUC、双 MID-360；Windows 作为远程观察端。项目静态核对版本：`6dba3a5`。

**当前状态：手册与源码接口已核对；NUC 尚未构建，以下安装、连接、录制、回放命令均未在你的硬件上实测。** 本文是后续课程操作指导，不代表已经部署成功。除明确标为 Windows PowerShell 的代码块，其余终端命令都在将来的 NUC Bash 中执行。

课程前置：A03 完成工作空间构建与环境核对。A04 可先用已有仿真或录包完成连接与界面练习；双雷达相关验收在 A06—A08 有实际输入后补齐；完整规划与控制布局在 A10 有数据后验收。不要因为某个下游功能尚未启动，就把空面板判定成 Foxglove 故障。

## 1. 连接关系与本课产物

```text
NUC 上的 ROS 节点和自定义消息包
            │ ROS 2 通信
       foxglove_bridge
            │ TCP / WebSocket，端口 8765
            ├── NUC 本机 Foxglove：ws://localhost:8765
            └── Windows Foxglove：ws://NUC可达地址:8765

NUC rosbag2 录制 → MCAP 文件 → 本机或 Windows Foxglove 离线打开
```

Windows 在此方案中只需客户端及到 NUC 的网络通路，不需要承担 ROS 2 DDS 跨机发现。雷达 IP、NUC 雷达接收网卡 IP、Windows 访问 NUC 的 IP 是三个概念；NUC 可以用有线口接雷达、另一网口或 Wi-Fi 接 Windows。后者地址不能直接照抄雷达配置中的 `192.168.1.47`。

本课要留下：软件版本、实际连接地址、话题与类型清单、一份可离线打开的短录包、三套布局的导出文件及导入验证记录。布局目前只有下面的配置配方，**状态均为“待连接实际数据后导出并验证”**；不把手写的未经导入测试的 JSON 当作可用布局交付。

## 2. NUC 环境和 bridge 启动

### 2.1 先确认工作空间环境

将 `NAVI_WS` 改成 NUC 上已构建的独立导航仓库根目录。它与 Windows 的 `E:\RM学习\navi_minco_bit` 不是同一个路径。

```bash
# 将来在 NUC 新终端执行；路径示例需与 A03 一致
NAVI_WS="$HOME/navi_minco_bit"
source /opt/ros/humble/setup.bash
test -f "$NAVI_WS/install/setup.bash"
```

最后一条必须返回成功；若文件不存在，回到 A03 完成构建。不要跳过它继续猜测包是否安装。

```bash
# 将来在 NUC 执行，前一检查成功后
source "$NAVI_WS/install/setup.bash"
printenv ROS_DISTRO
printenv ROS_DOMAIN_ID
printenv RMW_IMPLEMENTATION
ros2 pkg prefix livox_ros_driver2
ros2 pkg prefix ros_interfaces
ros2 interface show livox_ros_driver2/msg/CustomMsg
ros2 interface show ros_interfaces/msg/MpcPositionCommand
```

预期：ROS 发行版是 `humble`，两个自定义包来自本工作空间，消息定义能展开。`ROS_DOMAIN_ID` / `RMW_IMPLEMENTATION` 为空可以表示使用默认值，关键是 bridge 与业务节点的环境一致。仅 source `/opt/ros/humble/setup.bash` 不会自动加载本工程自定义消息。bridge、录包、检查命令所在终端都需要相同 overlay 环境。

### 2.2 安装并记录版本

以下是到 A04 时在 NUC 进行的安装步骤；本次编写手册没有执行安装。

```bash
sudo apt update
sudo apt install ros-humble-foxglove-bridge ros-humble-rosbag2-storage-mcap
dpkg-query -W ros-humble-foxglove-bridge ros-humble-rosbag2-storage-mcap
ros2 pkg prefix foxglove_bridge
ros2 launch foxglove_bridge foxglove_bridge_launch.xml --show-args
```

安装入口和连接 URL 采用 [Foxglove 官方 ROS 2 接入文档](https://docs.foxglove.dev/docs/getting-started/frameworks/ros2?modality=live)。记录安装版本与 `--show-args` 输出：网页最新 bridge 功能可能早于或晚于 Humble 的已安装二进制版本，不据网页默认值推断本机行为。

在 NUC 与 Windows 安装官方 [Foxglove 客户端](https://foxglove.dev/download)，或使用官方网页端。先用桌面客户端做本机和局域网连通性基线；记录客户端版本，便于日后复现界面及布局导入问题。

### 2.3 按顺序开启终端

| 终端 | 用途 | 核对事项 |
|---|---|---|
| T1 | 按 A05 或 A06—A10 启动当前课程需要的 ROS 节点 | 保留启动日志；本课不替换业务 launch |
| T2 | 启动 bridge | source 与 T1 一致的 ROS 和工作空间环境 |
| T3 | 检查话题、TF 或录包 | source 同一环境；需要持续录包时另开终端 |

```bash
# 将来在 NUC 的 T2 执行；先按 2.1 source 环境
ros2 launch foxglove_bridge foxglove_bridge_launch.xml
```

保持 T2 运行。在 T3 查看监听端口与图信息：

```bash
ss -ltnp 'sport = :8765'
ros2 node list
ros2 topic list -t
```

首次先连接 NUC 本机 `ws://localhost:8765`。客户端选择 **Open connection → Foxglove WebSocket**，选择的数据源要与 bridge 协议一致。

bridge 的 `address`、`port`、话题筛选、QoS、能力配置见 [官方 bridge 说明](https://github.com/foxglove/foxglove-sdk/blob/main/ros/src/foxglove_bridge/README.md)。若 `ss` 表明只监听 `127.0.0.1`，而需要 Windows 访问，先核对 `--show-args` 是否提供 `address` / `port`，再停止 T2 并使用下面命令；不要同时启动两个抢占同一端口的 bridge。

```bash
# 将来在 NUC 的 T2 执行，仅在已确认参数受支持后
ros2 launch foxglove_bridge foxglove_bridge_launch.xml address:=0.0.0.0 port:=8765
```

本课添加的是观察通路，不改本工程消息、话题、frame、QoS 或比赛参数。先只观察；不要在 Parameters 面板里尝试修改参数，也不要直接用 Teleop / Publish 面板驱动底盘。

## 3. Windows 远程连接与分层排查

NUC 上确认客户端可达的地址与路由：

```bash
# 将来在 NUC 执行
ip -br address
ip route
ss -ltnp 'sport = :8765'
```

Windows PowerShell 将占位符替换为上述可达的 NUC 地址，不填雷达地址：

```powershell
# 将来在 Windows PowerShell 执行
$NucIp = '替换为NUC的实际局域网IPv4地址'
Test-NetConnection -ComputerName $NucIp -Port 8765
```

`TcpTestSucceeded` 为 `True` 后，Windows 客户端连接 `ws://实际NUC地址:8765`。若网页客户端报告本地网络权限或浏览器连接限制，记录错误并用桌面客户端复核，区分浏览器限制与 ROS 数据链问题。

| 层级 | 现象 | 检查与结论 |
|---|---|---|
| 1. 节点 | NUC 的 `ros2 topic list -t` 就没有目标话题 | 查业务 launch、组件状态和环境；此时连接客户端无法补出数据 |
| 2. bridge 进程 | `ss` 没有 8765 监听 | 查 T2 首个错误、包来源、端口冲突；先恢复监听 |
| 3. 本机连接 | NUC 客户端也连不上 | 核对协议、端口和 bridge 日志；暂不归因于 Windows 网络 |
| 4. 远程 TCP | 本机可连，Windows TCP 测试失败 | 核对 NUC IP、监听地址、两端路由、AP 客户端隔离、防火墙；有需要时查看 `sudo ufw status verbose`，按网络实际策略处理 |
| 5. 话题发现 | 已连接但没有业务话题 | 核对 T1/T2 的 domain、RMW、overlay 及 bridge 话题筛选；先在 NUC 命令行复核 |
| 6. 消息解码 | 有话题却提示类型未知 | 核对 bridge 启动终端是否 source 自定义消息包，并重新启动 bridge |
| 7. 消息传输 | 列表有话题，但没有消息增长 | 用 `ros2 topic info -v` 核对发布者、订阅者和 QoS；检查业务节点是否只在激活、收到目标或存在订阅后发布 |
| 8. 三维显示 | Raw Messages 在更新，3D 空白 | 依次查类型支持、点数、`header.frame_id`、时间戳、TF、显示 frame、视角和显示开关 |

不要用“能 ping 通”代替 TCP 端口验证，也不要用“WebSocket 已连接”代替传感器输入验证。

## 4. 从源码确认的话题清单

以下为无额外命名空间、无 remap 的项目话题。现场以 `ros2 topic list -t`、`ros2 topic info -v` 及实际启动参数为准。表中的存在性是静态接口结论，不是当前硬件上已经有消息的结论。

| 话题 | 消息类型 | 用途与生效条件 |
|---|---|---|
| `/livox/lidar` | `livox_ros_driver2/msg/CustomMsg` | 双雷达融合输出；看 `point_num`、`timebase`、`points`，不当作标准点云直接显示 |
| `/livox/imu_192_168_1_135` | `sensor_msgs/msg/Imu` | 仓库前雷达配置样例；实际后缀随 IP 和驱动输出改变 |
| `/livox/imu_192_168_1_122` | `sensor_msgs/msg/Imu` | 仓库后雷达样例；不代表 Point-LIO 同时使用两路 IMU |
| `/cloud_registered` | `sensor_msgs/msg/PointCloud2` | Point-LIO 世界系点云，`camera_init`；适合先显示这一支 |
| `/cloud_registered_full` | `sensor_msgs/msg/PointCloud2` | 完整去畸变世界系点云；更大，是否输出受实际配置和运行状态影响 |
| `/cloud_registered_body` | `sensor_msgs/msg/PointCloud2` | 机体系点云，`body`；需要到显示 frame 的 TF |
| `/aft_mapped_to_init` | `nav_msgs/msg/Odometry` | 位姿 frame 为 `camera_init`，child 为 `body`；本实现线速度转到 `body` 后写入 twist |
| `/path` | `nav_msgs/msg/Path` | Point-LIO 轨迹，受发布设置影响 |
| `/Laser_map` | `sensor_msgs/msg/PointCloud2` | Point-LIO 地图输出；有初始化/累积发布条件，并非必定持续更新 |
| `/gicp_relocalization_node/debug/source_aligned` | `sensor_msgs/msg/PointCloud2` | 默认节点名下 GICP 对齐点云，依赖可视化开关与处理进度 |
| `/gicp_relocalization_node/debug/target_raw` | `sensor_msgs/msg/PointCloud2` | 默认节点名下先验目标点云；同样不是无条件持续发布 |
| `/rog_map/occupied`、`/rog_map/inflated_occupied` | `sensor_msgs/msg/PointCloud2` | 占据及膨胀结果；要求 ROGMap 可视化启用，许多输出按订阅需求生成 |
| `/rog_map/layer_value`、`/rog_map/layer_type` | `nav_msgs/msg/OccupancyGrid` | 投影数值与类别；类别不是自动等同于普通占据概率 |
| `/rog_map/field` | `sensor_msgs/msg/PointCloud2` | 距离场相关可视化，要求该功能有效且有订阅 |
| `/astar_path_vis`、`/opt_path_vis` | `nav_msgs/msg/Path` | 搜索引导路径、优化轨迹可视化；要求规划功能已经有结果 |
| `/opt_path` | `ros_interfaces/msg/MpcPositionCommand` | 控制使用的自定义轨迹，含 `cmds`、`mpc_horizon`、`command_flag` |
| `/mpc_predict_path`、`/mpc_real_path` | `nav_msgs/msg/Path` | MPC 预测和历史路径可视化，受控制器运行状态影响 |
| `/cmd_vel_mpc` | `geometry_msgs/msg/Twist` | 本工程 MPC 原始指令；Twist 没有 header，不能从消息自身得知坐标系 |
| `/tf`、`/tf_static` | `tf2_msgs/msg/TFMessage` | 动态与静态坐标关系；离线三维显示需要与数据时间段匹配 |
| `/rosout` | `rcl_interfaces/msg/Log` | ROS 日志；直接写 stdout 的内容不会自动变成该话题 |
| `/clock` | `rosgraph_msgs/msg/Clock` | 仿真或受控回放时的 ROS 时间源，普通实机运行不要求有这个话题 |

源码依据：[Livox 消息](../../src/perception/livox_ros_driver2/msg/CustomMsg.msg)、[双雷达配置](../../src/perception/livox_ros_driver2/config/mixed_MID360_component.yaml)、[Point-LIO 发布逻辑](../../src/perception/Point-LIO/src/laserMapping.cpp)、[GICP 接口](../../src/perception/icp_relocalization/src/gicp_ros_interface.cpp)、[ROGMap 发布器](../../src/perception/rog_map/src/rog_map/rog_map_visualizer.cpp)、[规划器可视化](../../src/navigation/minco_planner/src/minco_core/visualizer.cpp)、[MPC 接口](../../src/navigation/minco_controller/src/minco_mpc_controller.cpp)、[轨迹消息](../../src/ros_interfaces/msg/minco_traj/MpcPositionCommand.msg)。

## 5. 三套布局配置配方

创建个人布局后逐个添加面板；先以少量话题连通，再增加大点云。三个布局的命名、配置和导出目标如下，都是后续实操产物。

### L1：传感器与定位

布局名 `A04_sensor_localization`，将来导出 `sensor_localization.json`。

| 面板 | 配置 | 要能回答的问题 |
|---|---|---|
| 3D（左侧约 2/3） | 显示 frame 先选 `camera_init`；只开启 `/cloud_registered`，再按需开启 `/path`、完整点云 | 静止时墙面是否稳定，转弯时是否重影？ |
| Transform Tree | 查看 `camera_init`、`body`、`base_link`、`slambase`，重定位后再加入 `map` | 当前变换树是谁发布的，哪条边缺失？ |
| Raw Messages | 先 `/livox/lidar`，观察 `point_num`、`timebase` 和 `header`；点数组只展开少量 | 有原始点、时间在增长吗？ |
| Plot | `/aft_mapped_to_init.pose.pose.position.x`、`.y`、`.z` | 静止漂移与位置连续性如何？ |
| Plot | 选择实际前 IMU 的 `angular_velocity.z`、`linear_acceleration.x/y/z` | 转动响应、静止噪声与重力分量是否合理？ |
| Log | `/rosout`，按当前定位节点筛选 | 是否在等待 IMU、初始化失败或输入中断？ |

Plot 中每条字段路径使用完整话题前缀；例如 `/livox/imu_192_168_1_135.angular_velocity.z` 仅适用于该样例话题确实存在时。用字段选择器选出路径，可避免手输错误。

`CustomMsg` 中的 `points` 不是 Foxglove 3D 标准 `PointCloud2` schema。A04 先在 Raw Messages 观察原始输入，空间显示使用已有 Point-LIO 输出；没有 Point-LIO 输出时，就如实标记三维定位部分未完成，不为显示方便改掉驱动接口。

### L2：地图与规划

布局名 `A04_map_planning`，将来导出 `map_planning.json`。

| 面板 | 配置 | 要能回答的问题 |
|---|---|---|
| 3D | 先用 `camera_init` 看局部数据；确认 `map → camera_init` 有效后切换 `map` | 局部环境与先验地图是否一致？ |
| 3D 话题 | `/rog_map/occupied`、`/rog_map/layer_value`；按需加 `layer_type`、`field` | 障碍、地形类别和距离场分别说明什么？ |
| 3D 路径 | `/astar_path_vis`、`/opt_path_vis`，采用不同颜色 | 搜索路径与最终平滑轨迹有什么区别？ |
| 3D 先验 | 现场存在且类型正确的 `/map`；或 GICP `target_raw` 与 `source_aligned` | 地图与点云错位是整体变换问题还是局部几何问题？ |
| Raw Messages | `/opt_path`，查看 `command_flag`、`mpc_horizon`、`cmds` 与 header | 有没有可供控制器读取的轨迹命令？ |
| Log | `/rosout`，筛选 planner、GICP 或地图相关消息 | 没出轨迹的原因在哪一层？ |

`/opt_path` 是控制消息，`/opt_path_vis` 是几何显示路径，不能用后者证明全部控制字段都正确。ROGMap 可视化还受功能开关、订阅数量、有效地图和生命周期影响；先检查其实际条件，再判断空显示。

Foxglove 3D 需要在消息时间戳处存在从数据 frame 到显示 frame 的变换链，详见 [3D 官方说明](https://docs.foxglove.dev/docs/visualization/panels/3d)。因此“把显示 frame 改成 map”不能创造重定位结果。已有 TF 也不能单独证明 GICP 匹配成功：本工程有超时回退路径，必须同时查看结果记录与日志。

本课不配置默认点击发目标。后续 A10 核对实际消息类型、frame、订阅者与 Nav2 action 路径后再启用。不能假定向 `/initialpose` 发布消息就能触发本工程 GICP；当前 GICP 初值配置从其 YAML 读取，须按实际代码确认交互接口。

### L3：控制与性能

布局名 `A04_control_performance`，将来导出 `control_performance.json`。

| 面板 | 配置 | 要能回答的问题 |
|---|---|---|
| Plot：指令 | `/cmd_vel_mpc.linear.x`、`.linear.y`、`.angular.z` | 指令是否抖动，停车时有没有归零？ |
| Plot：估计速度 | `/aft_mapped_to_init.twist.twist.linear.x/y/z` | 估计速度变化是否连续？ |
| 3D | `/opt_path_vis`、`/mpc_predict_path`、`/mpc_real_path` | 预测和实际运动与规划的偏差发生在哪里？ |
| Raw Messages | `/opt_path` 和 `/aft_mapped_to_init` | 输入有没有中断或时间异常？ |
| Log | `/rosout`，筛选 MPC/规划器性能与失败信息 | 求解失败、截止时间和输入异常是否相关？ |

**不要直接把上述指令 x/y 与 odometry twist x/y 相减当作跟踪误差。** 本项目 `/cmd_vel_mpc` 的线速度采用项目世界系约定，而 Point-LIO 把线速度旋转到 `body` 后写入 odometry；C09 会逐项确认控制 frame 与角速度含义。严谨比较要先统一坐标系、采样时刻和参考点，再定义误差。Twist 没有时间戳，也不能仅靠该消息算端到端延迟。

这里没有虚构 `/mpc_error` 或 `/planner_latency` 话题。仓库的性能监测主要通过已有日志及可选 CSV 完成；参数启用方法归入 B01/B02。Foxglove Plot 先查看真实数值消息，CSV 的耗时分布在对应实验报告中统计。新版 bridge 若提供系统统计，也应先确认安装版本和消息类型再选用。

三种时间要区分：消息传感器 stamp、录制/接收时间、算法内部单调时钟计时。历史 bag 的 stamp 距今天系统时间很大，不是算法处理耗时；播放倍率、WebSocket 网络和渲染也会改变观察端延迟。算法优化使用内部计时或经过同步设计的测量。

ROGMap 有按订阅需求生成可视化的逻辑。开启一个点云面板可能同时增加数据构造、传输和绘制开销。对比实验必须记录 Foxglove 客户端数、启用话题、RViz、录包、`topic hz` 等观察负载；基线与改动版本保持一致。

### 5.4 保存与跨机验证

按 [官方布局说明](https://docs.foxglove.dev/docs/visualization/layouts) 使用布局菜单的 Export 导出 JSON，再在另一客户端使用 Import from file 导入。当前官方页面说明编辑布局受账号席位能力影响，A04 现场核对账号可用功能；若不可编辑，在进度中如实记录，不标布局验收通过。

| 布局 | 已配置实际数据 | 已导出 | Windows 导入通过 | 离线包显示通过 |
|---|---|---|---|---|
| `sensor_localization.json` | ☐ | ☐ | ☐ | ☐ |
| `map_planning.json` | ☐ | ☐ | ☐ | ☐ |
| `control_performance.json` | ☐ | ☐ | ☐ | ☐ |

导出文件保存到本目录。记录客户端版本、源码版本、话题 remap、使用的显示 frame 和验证 bag；JSON 不应包含访问凭据。面板能够导入但全空，不算“数据验证通过”。

## 6. A11：录制 MCAP 与离线打开

### 6.1 先定义要复盘的问题

| 目的 | 必要数据 | 不能遗漏的上下文 |
|---|---|---|
| 复看定位结果 | `/aft_mapped_to_init`、一种配准点云、`/tf`、`/tf_static`、相关日志 | 原参数、frame、地图与启动方式 |
| 重新计算 Point-LIO | 算法实际消费的 `/livox/lidar` 与前 IMU 原始输入 | 时间戳、预处理、外参与模型参数；只录处理后点云不够 |
| 排查双雷达融合或重新标定 | 融合前各雷达点云、需要的两路 IMU | 现场实际话题；融合后的单路输入不能完全还原融合过程 |
| 分析地图和规划 | 点云、里程计、TF、地图版本、目标/任务输入、规划结果 | 地图文件单独归档，目标接口按 A10 实际链路录制 |
| 分析控制 | 实际轨迹消息、里程计、指令、底盘反馈与必要状态 | 坐标/单位/时基、CSV；指令不等于真实执行反馈 |

不要一开始就 `-a` 录全系统大点云。首包先静止录 10—20 秒，确认能正常结束和打开，再扩大场景。录包保存在仓库外的数据目录，学习记录保留路径、摘要和参数版本。

### 6.2 实机定位短包示例

下面采用源码样例的 IMU 话题；在现场用 A06 已确认的实际话题替换变量。执行前 source 本工程环境，检查 topic 类型存在且有发布者。

```bash
# 将来在 NUC 执行；NAVI_WS 按 2.1 设置并已 source
NAVI_FRONT_IMU_TOPIC='/livox/imu_192_168_1_135'
ros2 topic info -v "$NAVI_FRONT_IMU_TOPIC"
ros2 topic info -v /livox/lidar
ros2 topic info -v /aft_mapped_to_init
ros2 bag record --help
```

```bash
# 将来在 NUC 执行；确认上述话题为当前实机数据后
NAVI_BAG_ROOT="$HOME/navi_data/bags"
mkdir -p "$NAVI_BAG_ROOT"
NAVI_BAG_OUT="$NAVI_BAG_ROOT/A11_static_$(date +%Y%m%d_%H%M%S)"
ros2 bag record -s mcap -o "$NAVI_BAG_OUT" \
  /livox/lidar "$NAVI_FRONT_IMU_TOPIC" \
  /aft_mapped_to_init /cloud_registered /tf /tf_static /rosout
```

用 Ctrl+C 正常结束，等待 recorder 关闭文件，然后：

```bash
# 将来在同一个 NUC 终端执行
ros2 bag info "$NAVI_BAG_OUT"
find "$NAVI_BAG_OUT" -maxdepth 1 -type f
```

查看 storage 是否为 MCAP、持续时长、话题类型和消息数量。同时确认 `/tf_static` 已录到所需静态变换；有些运行路径本来就没有静态边，此时记录实际依赖，而不是补造变换。消息数量为零或缺类型定义时先修正录制，再做长实验。

Humble 默认 `.db3` 不携带自定义消息定义；MCAP 可保存这些 schema。录制端必须加载 `livox_ros_driver2` 和 `ros_interfaces` 等实际依赖。旧 `.db3` 转换也必须提供匹配版本的消息定义，详见 [Foxglove ROS 2 录制与转换说明](https://docs.foxglove.dev/docs/getting-started/frameworks/ros2?modality=live)。仅改扩展名无法转换格式。

### 6.3 仿真时间与 TF

实机通常使用系统/传感器时钟，不能因为要录包就给全系统启用 `use_sim_time`。仿真中先确认 `/clock` 在更新，消费者使用相同 ROS 时间，再将 recorder 设为仿真时间，并把 `/clock` 作为需要归档的话题。

```bash
# 将来在 NUC 仿真课程执行；不用于没有 /clock 的普通实机录制
ros2 topic echo /clock --once
ros2 bag record --use-sim-time -s mcap -o "$NAVI_BAG_ROOT/A11_sim_$(date +%Y%m%d_%H%M%S)" \
  /clock /tf /tf_static /aft_mapped_to_init /cloud_registered /rosout
```

这只是“结果复看”的最小样例，不是可重算所有算法的完整仿真输入集。`--use-sim-time` 让 recorder 使用 `/clock`，不等于自动给其他节点设置 `use_sim_time`；只把 `/clock` 放进话题列表也不等于 recorder 已使用它。相关行为参见 [rosbag2 Humble 官方说明](https://github.com/ros2/rosbag2/tree/humble)。

### 6.4 Foxglove 离线复看

把完整录制目录传到 Windows 留作归档；Foxglove 用 Open local file(s) 打开其中 `.mcap`，分片时一起选择同一录制的分片。此步骤不需要 NUC bridge 在线。

操作顺序：选对应布局 → 播放开头静止段 → 检查消息数量和类型 → 检查 TF → 暂停到异常时刻 → 对照 Raw Messages、Plot 与 3D → 把截图或时间点写入实验记录。没有 schema 时，不能因 3D 中某一路标准点云可见就断言 CustomMsg 也能解码；分别检查 `/livox/lidar` 和 `/opt_path`。

## 7. 离线查看与重新跑算法是两件事

| 操作 | 实际发生的事 | 能回答的问题 |
|---|---|---|
| Foxglove 打开旧 MCAP | 显示过去已经产生的结果 | 当时的位姿、轨迹和指令发生了什么？ |
| ROS 重放原始输入，启动新算法 | 算法重新消费相同数据、产生新结果 | 改参数或改代码后，结果是否改善？ |

重新计算要到 A11/B02 确定回放 launch 和时钟方案后执行。准备顺序固定为：保留旧包 → 停止实机输入和与回放冲突的节点 → 只启动待评估算法及必要依赖 → 让所有相关节点使用一致时间 → 回放所需原始输入 → 另录新输出。不要把旧里程计和正在重新计算的里程计同时发布到同一话题，也不要把旧 `/tf` 混进新估计链。

以下只演示“向 ROS 重放 Point-LIO 原始输入”的 player 命令。前提是已完成 A11 的节点、参数、时间与输出隔离核对；它不包含启动算法和硬件准备，不能单独视为完整回放流程。

```bash
# 将来在 NUC 执行，先设置实际 bag 路径和 IMU 话题
NAVI_INPUT_BAG='/替换为/已核验的/录包目录'
NAVI_FRONT_IMU_TOPIC='/替换为/该包实际的前雷达IMU话题'
ros2 bag info "$NAVI_INPUT_BAG"
ros2 bag play --help
ros2 bag play "$NAVI_INPUT_BAG" --clock --topics /livox/lidar "$NAVI_FRONT_IMU_TOPIC"
```

此命令选出的原始输入不包含旧 `/clock`，由 player 生成时钟；如果改为回放包内 `/clock`，则必须另行设计并保持唯一时间源。`--clock` 不会自动给算法打开 `use_sim_time`。首轮在 1 倍速检查完整性，之后的加速回放不能直接用于与实机处理间隔作等价比较。

## 8. 本课验收和应留下的记录

- [ ] 能画出“ROS 节点 → bridge → NUC / Windows 客户端”的连接关系。
- [ ] 在 NUC 确认 overlay、自定义消息和 bridge 版本；留存连接信息。
- [ ] NUC 本机能连接并看到当前课程已启动模块的数据。
- [ ] Windows TCP 检查通过；能远程看到与 NUC 同一数据源。
- [ ] 能说明 CustomMsg 与 PointCloud2、`/opt_path` 与 `/opt_path_vis` 的用途差异。
- [ ] 能定位一次“有消息而 3D 不显示”的原因，而不是随意改变 TF。
- [ ] 三套布局在各自依赖课程完成后导出，Windows 导入，短包验证。
- [ ] 首个 MCAP 短包可打开，自定义字段与必要 TF 完整。
- [ ] 能解释为什么播放旧结果不等于验证了算法新版本。
- [ ] 知道坐标不统一不能直接减速度，历史 stamp 的 wall-age 不能当算法耗时。

将下面内容填入 [课程进度](../PROGRESS.md)，连接与录包没实际完成前保持未验收。

```text
课程编号：A04 / A11
日期与源码提交：
NUC 工作空间路径、ROS domain 与 RMW：
bridge 版本 / Foxglove 客户端版本：
NUC 可达 IP / 本机与远程连接结果：
已验证话题、消息类型、显示 frame：
布局导出文件 / 跨机导入结果：
录包路径 / 时长 / 话题数 / MCAP 与自定义消息验证：
开启的点云面板、客户端数、RViz 与录制负载：
发现的问题 / 排查证据 / 尚未完成的验收项：
下一步：
```

本手册已核对本地源码和官方文档链接；未进行 NUC 安装、编译、连接或录包实测。代码构建和后续硬件课程按实际环境单独验收。
