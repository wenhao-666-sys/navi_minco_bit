# A01：项目总览与文件结构

教材核对日期：2026-09-28。适用对象：有 ROS 使用经验、尚未在 NUC 编译运行本工程的学习者。

本课对应 [学习路线](../ROADMAP.md) 的 A01。文件级查询使用 [项目索引](../PROJECT_INDEX.md)，学习证据记入 [进度记录](../PROGRESS.md)。本课提供的是源码静态核对结果；教材准备完成不代表你已完成操作或通过验收。

## 1. 本课结束后，你要能做什么

你需要能沿两条线讲清项目：一条是“传感器数据怎样变成机器人位姿和障碍物地图”，另一条是“导航目标怎样变成底盘运动”。遇到故障时，能够选择下一项检查，而不是从任意 YAML 开始调参数。

本课的具体产物是：一张你自己画的模块图、一张实际启动清单、三道故障题的解释。当前只读源码即可完成前两项，不需要连接雷达、启动机器人或编译工程。运行时只读命令留给 NUC 环境准备好以后使用；没有运行环境时明确记为“待实操”。

建议将本课分成三次：目录与职责约 25 分钟；启动与接口约 30 分钟；文件跟读与验收约 25 分钟。遇到陌生的 C++ 语法先记下来，本课先理解职责和连接关系。

## 2. 先建立六组源码目录的地图

在仓库根目录打开 `src`，应看到下面六组目录。树中括号内是 `package.xml` 声明的 ROS 包名；名称不是凭目录猜的。

```text
navi_minco_bit/
├── start.bash / build.bash / clean.bash / play.bash / simlation.bash
├── scripts/                         环境、时间同步、诊断、保存数据等工具
└── src/
    ├── perception/
    │   ├── livox_ros_driver2/        (livox_ros_driver2)
    │   ├── dual_lidar_calibration/   (dual_lidar_calibration)
    │   ├── Point-LIO/                (point_lio)
    │   ├── icp_relocalization/       (icp_relocalization)
    │   ├── rog_map/                  (rog_map)
    │   ├── msg_convert/              (msg_convert)
    │   └── dbscan_cluster/           (dbscan_cluster)
    ├── navigation/
    │   ├── navi2_bringup/            (navi2)
    │   ├── minco_planner/            (minco_planner)
    │   ├── minco_controller/         (minco_controller)
    │   └── communication/            (communication)
    ├── decision/
    │   └── bt_manager/              (bt_manager)
    ├── ros_interfaces/              (ros_interfaces)
    ├── simulation/
    │   └── sentry_simulation/        (sentry_simulation)
    └── utils/
        ├── pcd2pgm/                 (pcd2pgm)
        ├── pcd2ele/                 (pcd2ele)
        ├── pcd2esdf/                (pcd2esdf)
        └── pcd_trans/               普通工具目录，不计入上述 ROS 包
```

这六组目录中共 17 个 ROS 包。`perception`、`navigation` 等属于组织目录，不是另外的 ROS 包。未来新增或删除包时，应重新查 `package.xml`，不要把这个数量当永久不变的常量。

### 2.1 17 个包各自回答什么问题

| 包与源码入口 | 负责的问题 | 第一课需要记住的边界 |
|---|---|---|
| [livox_ros_driver2](../../src/perception/livox_ros_driver2) | 怎样从 MID-360 收取点云和 IMU，并发布 ROS 消息？ | 当前混合配置启用驱动内部双雷达融合；它还不负责定位 |
| [dual_lidar_calibration](../../src/perception/dual_lidar_calibration) | 两台雷达之间的刚体变换怎样标定？ | 标定工具；`start.bash` 没有单独启动它 |
| [point_lio](../../src/perception/Point-LIO) | 机器人相对于启动时局部参考系怎样运动？ | 用点云和 IMU 估计连续位姿、维护局部地图并输出配准点云 |
| [icp_relocalization](../../src/perception/icp_relocalization) | 当前局部参考系应放在先验地图的什么位置？ | 通过 GICP 建立地图对齐关系；与连续局部里程计职责不同 |
| [rog_map](../../src/perception/rog_map) | 哪些空间被占据，地形如何投影，距障碍还有多远？ | 当前规划器内创建 `ROGMapROS` 对象，不能靠寻找同名独立进程判断是否工作 |
| [msg_convert](../../src/perception/msg_convert) | 怎样转换或过滤点云消息？ | 包内工具按具体 launch 使用；根启动脚本中的独立裁剪入口当前注释关闭 |
| [dbscan_cluster](../../src/perception/dbscan_cluster) | 怎样对点云分组、表达聚类结果？ | 辅助感知；是否运行要追实际启动路径，目录存在不等于默认启用 |
| [navi2](../../src/navigation/navi2_bringup) | 怎样把 Nav2 服务、插件、地图、参数和 RViz 组织起来？ | 本地包名是 `navi2`，还依赖外部 `nav2_bringup` 等官方包 |
| [minco_planner](../../src/navigation/minco_planner) | 从当前位置到目标，怎样搜索并生成可跟踪的轨迹？ | Nav2 规划插件，内部还有 FSM、搜索与轨迹优化流程 |
| [minco_controller](../../src/navigation/minco_controller) | 根据当前状态和参考轨迹，应给出什么速度？ | Nav2 控制插件；使用 MPC 预测与约束求解，不等于底盘驱动 |
| [communication](../../src/navigation/communication) | 怎样把控制、行为与状态接入下位机协议？ | 接收 MPC 速度和行为消息，组织串口收发；实际电机执行在下位机 |
| [bt_manager](../../src/decision/bt_manager) | 比赛状态下何时去哪、执行什么策略？ | 上层比赛行为树，与 Nav2 自身的导航行为树分清 |
| [ros_interfaces](../../src/ros_interfaces) | 不同模块交换的数据结构是什么？ | 自定义 `.msg` 定义；接口包本身不代表一个持续运行的节点 |
| [sentry_simulation](../../src/simulation/sentry_simulation) | 怎样用仿真传感器和底盘验证导航链？ | 提供模型、桥接、运动学与真值；不能替代硬件网络和标定验证 |
| [pcd2pgm](../../src/utils/pcd2pgm) | 怎样由点云得到二维栅格地图材料？ | 离线地图工具，不在默认实车启动链逐帧执行 |
| [pcd2ele](../../src/utils/pcd2ele) | 怎样由点云生成高程相关地图材料？ | 先看其参数、源码和输出，别与实时障碍地图混用 |
| [pcd2esdf](../../src/utils/pcd2esdf) | 怎样读取地图 YAML 及其图像，生成距离场点云文件？ | 当前输入是二维地图，输出为 PCD；不能仅凭包名推断输入是点云，也要与实时 ROGMap 中的 ESDF 处理区分 |

先用一句话复述每个大环节：驱动获取数据；里程计估计运动；重定位对齐先验；地图表达环境；规划给轨迹；控制给速度；通信让下位机收到命令；决策选择任务。

### 2.2 面对一个陌生包，按什么顺序看文件

| 文件类别 | 要回答的问题 | 判断时注意 |
|---|---|---|
| `package.xml` | 包名、构建方式、依赖是什么？ | 包名可与目录名不同 |
| `CMakeLists.txt` | 编译哪些源文件、产出什么库/程序、安装哪些资源？ | 源文件存在，不代表在当前目标里编译 |
| `launch/` | 创建什么节点/组件，包含哪个 launch，传哪些参数？ | 注释和条件分支要分清 |
| `config/`、`params/` 的 YAML/JSON | 当前算法和设备采用哪些配置？ | 要证明 launch 真正加载了该文件，还要检查覆盖项 |
| `include/`、`src/` | 数据结构、接口声明、算法实现在哪里？ | 模板或内联实现也可能全部在头文件内 |
| 插件 XML、组件注册 | 上层通过什么名称加载这段实现？ | YAML 中插件名称要对应导出注册 |
| `.msg` | 数据有哪些字段、单位由谁约定？ | `Twist` 没有 header，不能仅靠类型知道坐标系 |
| `maps/`、`pcd/`、模型和 RViz 配置 | 运行使用哪些资源？ | 文件路径、坐标系和场地版本要一致 |
| `third_party/`、第三方头文件目录 | 使用哪些外部算法库？ | 第一遍掌握调用边界，不要求逐行背完第三方实现 |
| 文档、测试、历史备份 | 设计说明、检查入口、旧方案是什么？ | 文档和 `.bak` 都不能替代当前生效源码的证据 |

`build/`、`install/`、`log/` 是之后构建与运行产生的目录。ROS 在已经 source 的安装环境里查包；编辑 `src` 中的文件后，必须核对安装资源与运行进程实际读取哪份内容。这会在 A02 展开。

## 3. 根脚本不是同一种“启动按钮”

本课阅读下表中的脚本，不执行它们。特别是 `start.bash` 会调用 PTP、启动导航与通信；它不是只读检查命令。

| 文件 | 源码中的真实行为 | 当前状态或需要记下的前提 |
|---|---|---|
| [start.bash](../../start.bash) | 切目录、加载安装环境，依次开启 PTP、双雷达与 Point-LIO、GICP、Nav2、比赛决策、通信终端 | 硬编码 `cd ~/2027-sentry-navi`，使用 `gnome-terminal`；不是按本仓库名字自动定位路径 |
| [build.bash](../../build.bash) | source Humble，关键包按列表逐个构建，其余包并行构建 | 内存监视只输出使用量；脚本中的“预算”不是操作系统强制内存隔离。本课不运行构建 |
| [clean.bash](../../clean.bash) | 删除当前工作目录下的 `build/ install/ log/` | 会删除生成物，且依赖当前目录；不是故障排查首步 |
| [play.bash](../../play.bash) | source 当前 `install/setup.bash`，启动 `navi2 navigation2.launch.py` | 文件名含 play，但没有 `ros2 bag play`；不自动提供雷达、里程计或回放时钟 |
| [simlation.bash](../../simlation.bash) | 检查环境后启动仿真入口，可指定底盘和场景 | 文件名就是 `simlation`；默认 `omni / rmuc_2025`；具体可用场景和闭环验证放到 A05 |
| [scripts/ptp_sync.bash](../../scripts/ptp_sync.bash) | 配置并启动 PTP 时间同步 | 默认网卡 `enp86s0`；脚本会停止时间同步服务、清理旧 PTP 进程，本课仅阅读 |
| [scripts/pcd.bash](../../scripts/pcd.bash) | 打开独立驱动与 Point-LIO launch | 仍使用 `~/2025-sentry-navi`；是否保存 PCD 还要看 Point-LIO 配置 |
| [scripts/savemap.bash](../../scripts/savemap.bash) | 调用 map saver 保存二维地图，可周期保存 | 默认读 `/map`，默认输出前缀是工作空间下 `pgm/slam`；不是保存原始雷达数据 |
| [scripts/setup_env.bash](../../scripts/setup_env.bash) | 配置 VS Code 格式化快捷键和设置 | 不是 ROS 依赖安装脚本；会写用户及工作区设置 |
| [scripts/monitor_livox_network.sh](../../scripts/monitor_livox_network.sh)、[monitor_odom_rogmap.py](../../scripts/monitor_odom_rogmap.py)、[diag](../../scripts/diag) | 网络、频率、时间同步或进程崩溃诊断工具 | 按单个工具的参数和实现使用；不能把工具存在当作监测已开启 |
| [scripts/autopush.sh](../../scripts/autopush.sh) | 自动处理仓库推送相关操作 | 不属于导航运行链；本课程不通过它自动提交或推送 |

### 3.1 逐行还原 start.bash 的默认启动清单

```text
切到 ~/2027-sentry-navi，source ./install/setup.bash
  → sudo scripts/ptp_sync.bash
  → point_lio / mixed_livox_pointlio_intra_process.launch.py
  → icp_relocalization / gicp_relocalization.launch.py
  → navi2 / navigation2.launch.py
  → bt_manager / bt_manager.launch.py
  → communication / com.launch.py
```

启动之间有固定 `sleep`，这只是等待，不是“已经就绪”的证明。今后部署要用消息、TF、生命周期和日志验证就绪。

以下内容在根脚本中被注释：单雷达替代入口、独立 `msg_convert` 裁剪节点、`navi2 slam.launch.py` 替代入口、真正执行录包的命令，以及 Foxglove bridge 命令。`ROSBAG_TOPICS` 数组存在，只代表列好了话题，当前不会自动录包。数组里的原始 `/livox/lidar` 和前雷达 IMU 也被注释，因此以后仅沿用这份数组不能默认得到可重新运行里程计的原始数据集。

独立裁剪 launch 被注释不等于系统完全没有裁剪：规划器集成的 ROGMap 路径也有相关配置与实现。判断某个处理是否存在，要追到具体调用者。

## 4. 两条数据流：先讲职责，再看接口

### 4.1 传感器如何变成位置和可规划环境

```text
两台 MID-360
  │ 网络接收、时间配对、后雷达到前雷达的外参变换
  ▼
livox_ros_driver2（当前启用内部融合）
  ├─ /livox/lidar：融合 CustomMsg ─────────┐
  └─ /livox/imu_192_168_1_135：主 IMU ────┤
                                        ▼
                                  point_lio
                        ┌───────────────┴────────────────┐
                        │                                │
             /aft_mapped_to_init              /cloud_registered_full
             连续局部位姿和速度                完整配准点云
                        │                        ├─→ GICP + 先验 PCD
                        │                        │     → map 到 camera_init 的 TF
                        └─────────┬──────────────┘
                                  ▼
                      规划器内部的 ROGMapROS
                    占据、投影、距离场与地图查询
                                  ▼
                          搜索与轨迹优化
```

里程计回答“从启动处走了多远、怎么转动”，重定位回答“这个局部世界应该放到先验地图的哪里”。本项目 GICP 默认使用先验 PCD 与完整配准点云对齐，并有超时默认位姿。**已经有 `map → camera_init` TF，不足以证明点云匹配成功**：要区分匹配质量门槛通过与超时回退，查看日志及结果，再检查可视化重合程度。

### 4.2 目标如何变成底盘命令

```text
RViz 等任务客户端，或 bt_manager 的比赛决策
  → Nav2 NavigateToPose action
  → Nav2 导航执行逻辑 / planner_server
  → MincoPlanner::createPlan() 接收目标
  → 内部 MincoFSM 调度搜索、优化与重规划
  → /opt_path（自定义轨迹）
  → controller_server 加载的 MincoMpcController
       同时读取里程计、TF，计算预测控制
  → /cmd_vel_mpc（项目约定的世界系线速度）
  → communication（还接收比赛行为指令与里程计）
  → 串口协议、下位机、底盘执行
```

`NavigateToPose` 是 action：它有目标、反馈和结果，不是单纯发布一个普通话题。MINCO 的 `createPlan()` 是 Nav2 入口，但轨迹优化由内部 FSM 继续推进。想读懂重规划，不能读完 `createPlan()` 就认为读完规划器。

MPC 速度要继续追 [com_interface_ros.hpp](../../src/navigation/communication/include/com_interface_ros.hpp) 与 [com_interface_ros.cpp](../../src/navigation/communication/src/com_interface_ros.cpp) 中的缓存、字段单位换算及打包，再核对坐标旋转在哪一端完成。消息类型叫 `Twist`，不代表可以不核对坐标系直接发给任意底盘。实际设备的方向、单位、模式位和执行责任在 A10 验证。

### 4.3 当前 TF 有项目特定约定

依据 [laserMapping.cpp](../../src/perception/Point-LIO/src/laserMapping.cpp) 的 `publish_odometry()`，在 `tf_send_en` 打开时，Point-LIO 发布以下三个分支：

```text
map ──GICP──> camera_init
                 ├──> body       里程计位置 + 完整姿态
                 ├──> base_link  加入 yaw 旋转后的 (0, 0.20, 0) 偏移，旋转为恒等
                 └──> slambase   里程计位置 + 仅 yaw 旋转
```

这三个子坐标系不能画成 `body → base_link → slambase` 串联。`base_link` 的当前旋转是 `(x,y,z,w)=(0,0,0,1)`；用于计算其平移偏移的 yaw 不代表它最后发布了 yaw 旋转。`slambase` 才保留该 yaw，`body` 保留完整姿态。YAML 的历史注释未必描述当前实现，TF 以源码与运行结果共同确认。本课先认识这个事实，A08 再分析它对显示、规划和控制的意义。

## 5. 包、节点、组件、插件、库：分清五种名字

| 名词 | 可以怎样理解 | 本仓库例子 |
|---|---|---|
| 包 package | 可被构建、安装、查找的一组代码与资源 | `point_lio` 的源目录是 `Point-LIO` |
| 节点 node | ROS 图里的通信实体，有节点名、话题和参数 | Point-LIO 组件的节点名为 `laserMapping` |
| 组件 component | 可以装进容器进程的节点实现 | `point_lio::LaserMappingNode` 和 `livox_ros::DriverNode` |
| 插件 plugin | 上层通过约定接口加载的算法实现 | `minco_planner/MincoPlanner`、`minco_controller::MincoMpcController` |
| 库 library / 对象 | 被其他程序链接或创建的一段实现 | 规划器内部创建 `rog_map::ROGMapROS` |

当前双雷达入口把驱动和 Point-LIO 组件装入 `livox_pointlio_container`，程序是 `rclcpp_components` 的 `component_container_mt`。一个进程可以包含多个 ROS 节点；一个节点也可以持有多个库对象。Nav2 启动文件还会将规划服务器组件加载到该容器，形成 Point-LIO 到 ROGMap 的进程内点云路径。实际运行时可用 `ros2 component list` 核对，而不能仅看任务管理器进程数。

`minco_planner` 和 `minco_controller` 的参数出现在服务器的参数文件里，算法由插件承载。找不到一个叫 `/minco_planner` 的独立节点，不足以判定规划器没有启动。当前默认配置的插件映射见 [sentry1.yaml](../../src/navigation/navi2_bringup/params/sentry1.yaml)。

## 6. 第一批必须认识的话题

下表是当前默认配置及源码下的关键连接。运行时仍需核对 remap、namespace 和最终参数，表中名字不是对所有启动方式的保证。消费者列只列主要使用者，不代表完整订阅列表。

| 话题 | 消息类型 | 生产者 | 主要消费者 / 用途 |
|---|---|---|---|
| `/livox/lidar` | `livox_ros_driver2/msg/CustomMsg` | Livox 驱动内部融合输出 | Point-LIO 的 Livox 回调 |
| `/livox/imu_192_168_1_135` | `sensor_msgs/msg/Imu` | 前雷达 IMU 发布链 | Point-LIO；名字由当前设备 IP 配置关联 |
| `/aft_mapped_to_init` | `nav_msgs/msg/Odometry` | Point-LIO | GICP、ROGMap、规划器、MPC、行为树与通信 |
| `/cloud_registered` | `sensor_msgs/msg/PointCloud2` | Point-LIO | 配准点云观察及具体地图消费者；不是原始 CustomMsg |
| `/cloud_registered_full` | `sensor_msgs/msg/PointCloud2` | Point-LIO | 当前 GICP 与 ROGMap 输入；完整点云路径要与稀疏输出区分 |
| `/opt_path` | `ros_interfaces/msg/MpcPositionCommand` | MINCO 规划器 | MPC、行为树；携带自定义轨迹序列 |
| `/opt_path_vis` | `nav_msgs/msg/Path` | MINCO 可视化模块 | RViz、Foxglove 路径显示 |
| `/astar_path_vis` | `nav_msgs/msg/Path` | MINCO 可视化模块 | 搜索路径显示 |
| `/mpc_predict_path` | `nav_msgs/msg/Path` | MPC | 预测轨迹显示 |
| `/cmd_vel_mpc` | `geometry_msgs/msg/Twist` | MPC | 通信和行为树；世界系线速度约定需与协议配合 |
| `/sentry/behaivor_send` | `ros_interfaces/msg/Behavior` | `bt_manager` ROS 接口 | 通信；`behaivor` 是当前实际拼写 |
| `/tf`、`/tf_static` | `tf2_msgs/msg/TFMessage` | Point-LIO、GICP 及启动的其他 TF 发布者 | TF 缓冲区、导航、显示工具 |

打开 [MpcPositionCommand.msg](../../src/ros_interfaces/msg/minco_traj/MpcPositionCommand.msg) 和 [PositionCommand.msg](../../src/ros_interfaces/msg/minco_traj/PositionCommand.msg)。先找 header、序列及每条命令的字段，再与普通 `nav_msgs/Path` 对照。**看到 `/opt_path_vis` 上有线，不能证明 `/opt_path` 当前有有效、新鲜且被控制器接受的轨迹。**

想核对表格的证据，可在以下文件搜索 `create_publisher`、`create_subscription` 及对应话题名：

- [Point-LIO laserMapping.cpp](../../src/perception/Point-LIO/src/laserMapping.cpp)
- [GICP gicp_ros_interface.cpp](../../src/perception/icp_relocalization/src/gicp_ros_interface.cpp)
- [MINCO minco_planner.cpp](../../src/navigation/minco_planner/src/minco_core/minco_planner.cpp)
- [MPC minco_mpc_controller.cpp](../../src/navigation/minco_controller/src/minco_mpc_controller.cpp)
- [行为树 ros_interface.cpp](../../src/decision/bt_manager/src/ros_interface.cpp)

## 7. 跟读一次真正的 launch → YAML → 源码

### 7.1 双雷达与 Point-LIO

依次打开这些文件，并在纸上画箭头：

1. [start.bash](../../start.bash)：找到未注释的 `mixed_livox_pointlio_intra_process.launch.py`。
2. [mixed_livox_pointlio_intra_process.launch.py](../../src/perception/Point-LIO/launch/mixed_livox_pointlio_intra_process.launch.py)：它包含通用容器 launch，同时指定两个参数文件和主 IMU 话题。
3. [livox_pointlio_intra_process.launch.py](../../src/perception/Point-LIO/launch/livox_pointlio_intra_process.launch.py)：找到两个 `ComposableNode`，分别记录 package、plugin、name、parameters。
4. [mixed_MID360_component.yaml](../../src/perception/livox_ros_driver2/config/mixed_MID360_component.yaml)：当前 `enable_internal_lidar_merge: true`，前后雷达为 `.135/.122`，融合输出 `livox/lidar`；其 `user_config_path` 指向 [mixed_MID360_config.json](../../src/perception/livox_ros_driver2/config/mixed_MID360_config.json)。
5. [mid360.yaml](../../src/perception/Point-LIO/config/mid360.yaml)：找到 `common.lid_topic`、`common.imu_topic`、`preprocess.lidar_type`。之后看 launch 的 `{"common.imu_topic": pointlio_imu_topic}`，识别它对 YAML 的覆盖。
6. [laserMapping.cpp](../../src/perception/Point-LIO/src/laserMapping.cpp)：搜索 `create_subscription`，确认 Livox 分支接收 `CustomMsg`，IMU 分支接收 `Imu`；再搜索 `RCLCPP_COMPONENTS_REGISTER_NODE` 验证组件注册。
7. [Point-LIO CMakeLists.txt](../../src/perception/Point-LIO/CMakeLists.txt)：定位上述源文件、组件注册和资源安装，解释 ROS 为什么能找到 launch 与类。

到这一步，你应能回答：如果只修改 YAML 的 IMU 名称而 launch 又覆盖它，最终订阅值由谁决定？这也是 A06 为什么要同时核对 IP、驱动 JSON、融合 YAML 和 launch 的原因。

### 7.2 Nav2 到算法插件

阅读 [navigation2.launch.py](../../src/navigation/navi2_bringup/launch/navigation2.launch.py)：默认使用 `params/sentry1.yaml`、`maps/2026/rmuc2026.yaml`，包括本地 [navigation_launch.py](../../src/navigation/navi2_bringup/launch/navigation_launch.py) 和官方定位 launch，并启动 RViz。接着在 [sentry1.yaml](../../src/navigation/navi2_bringup/params/sentry1.yaml) 找 `planner_plugins`、`controller_plugins` 和对应 `plugin` 字符串，最后跳到规划器和控制器源码。

这条链说明“启动 navi2”实际会牵涉多个外部包、服务器和本地算法插件。另一个常见误解是“包含了官方定位 launch，因此实际定位一定是 AMCL”。本工程已经有 GICP 的地图对齐链，真正使用的节点、输入和 TF 发布权需要按启动结果核对，不能仅由 include 名称下结论。

## 8. 自己动手：两套只读核对命令

下面命令不编译、不改参数、不启动导航、不发送运动目标。窗口路径不同就先替换路径；不要把 Windows 命令直接粘贴到 NUC Bash。

### 8.1 Windows PowerShell：源码目录核对

工作目录：本机独立仓库 `E:\RM学习\navi_minco_bit`。

```powershell
Set-Location -LiteralPath 'E:\RM学习\navi_minco_bit'
Get-ChildItem -LiteralPath '.\src' -Directory
Get-Content -LiteralPath '.\start.bash' -Encoding UTF8

# 从 XML 读取真实包名，不按目录名猜。
Get-ChildItem -LiteralPath '.\src' -Recurse -Filter 'package.xml' | ForEach-Object {
    [xml]$packageDoc = Get-Content -LiteralPath $_.FullName -Encoding UTF8
    '{0} => {1}' -f $_.DirectoryName, $packageDoc.package.name
}

Select-String -LiteralPath '.\src\perception\Point-LIO\launch\livox_pointlio_intra_process.launch.py' -Pattern 'ComposableNode','plugin=','parameters=','common.imu_topic'
Select-String -LiteralPath '.\src\navigation\navi2_bringup\params\sentry1.yaml' -Pattern 'planner_plugins','controller_plugins','plugin:'
Select-String -LiteralPath '.\src\perception\Point-LIO\src\laserMapping.cpp' -Pattern 'child_frame_id','create_subscription','create_publisher'
```

预期结果：六组源码目录、17 条包声明、两个组件类、实际插件字符串和 TF 子坐标系。如果数量不同，先记录当前版本和新增目录，再更新索引，不能为凑数量删除文件。

### 8.2 NUC Bash：未构建也能做的源码核对

工作目录：NUC 上你实际克隆的仓库根目录。下面以 `~/navi_minco_bit` 为例，若放在其他目录，只改第一行路径。不要求安装 `rg`。

```bash
cd ~/navi_minco_bit
pwd
find src -mindepth 1 -maxdepth 1 -type d
find src -name package.xml -type f -print
sed -n '1,140p' start.bash
grep -nE 'ComposableNode|plugin=|parameters=|common.imu_topic' \
  src/perception/Point-LIO/launch/livox_pointlio_intra_process.launch.py
grep -nE 'planner_plugins|controller_plugins|plugin:' \
  src/navigation/navi2_bringup/params/sentry1.yaml
grep -nE 'child_frame_id|create_subscription|create_publisher' \
  src/perception/Point-LIO/src/laserMapping.cpp
```

### 8.3 NUC Bash：已有运行系统时的只读检查

这一小节是后续课程的预览，需要系统已由你正确构建并启动。没有运行系统就跳过，记录“运行时检查待实操”，不影响 A01 的源码练习验收。这是待办描述，不是新增课程状态。这些命令不负责启动系统。

工作目录仍为实际仓库根目录；先加载 Humble，再加载这个仓库的安装环境。

```bash
cd ~/navi_minco_bit
source /opt/ros/humble/setup.bash
source ./install/setup.bash
ros2 pkg prefix point_lio
ros2 pkg prefix navi2
ros2 node list
ros2 component list
ros2 topic list -t
ros2 topic type /livox/lidar
ros2 topic info /livox/lidar --verbose
ros2 topic type /opt_path
ros2 topic type /opt_path_vis
ros2 interface show ros_interfaces/msg/MpcPositionCommand
ros2 param get /laserMapping common.imu_topic
ros2 lifecycle get /planner_server
ros2 lifecycle get /controller_server
ros2 action list -t
```

用终端输出核对：包来自哪个安装前缀、节点实际叫什么、组件装入哪个容器、话题两端类型及 QoS、参数当前值、服务器生命周期是否 active。如果命令找不到包，首先检查环境 source 与工作空间；如果节点名不同，以 `ros2 node list` 的输出为准。

本课不把“topic 在列表里”当作数据正确。后续部署课程还要检查频率、时间戳、有效点数、TF 和是否持续更新。运行观察也会产生订阅与少量负载，性能实验时应记录开启了哪些观察工具。

## 9. 本课的记录与验收

把下面模板填写到自己的课程记录中，不预先勾选完成：

```text
课程：A01
学习日期：
本次源码版本/快照：
实际源码路径：
我画的两条数据流图位置：
17 个包核对输出位置：
start.bash 默认启动清单：
当前未启用的入口：
我跟读的 launch → YAML → 源码链：
已做源码检查：
运行时检查：已做 / 待实操（填写原因）
仍不理解的名词或文件：
下面三道题的回答：
```

验收清单：

- [ ] 我能从目录结构找到 17 个包，并解释两个“目录名与包名不同”的例子。
- [ ] 我能说明包、节点、组件、插件和库的区别。
- [ ] 我能还原默认启动顺序，并指出 Foxglove 和录包命令当前被注释。
- [ ] 我能沿 launch 找到实际参数文件和 IMU 覆盖项。
- [ ] 我能分别解释局部里程计、先验地图对齐、实时障碍地图的职责。
- [ ] 我能说明 `/opt_path` 与 `/opt_path_vis` 的类型及用途差异。
- [ ] 我能画对 `camera_init` 下三个 TF 分支，并说明 `base_link` 的当前旋转。
- [ ] 我已经独立回答下面三道题，再对照提示修正理解。

先回答再展开文末提示。每道题用“检查哪个模块 → 查哪条输入/输出 → 什么结果支持判断 → 下一步”组织答案，不要求第一步就猜中根因。

1. 雷达点云正常，但机器人位姿不更新：你先查哪几项？怎样区分 Point-LIO 没收到输入、等待同步/初始化、已经输出但显示错误？
2. 局部里程计正常，但先验地图与实时点云错位：你沿哪条链查？为什么看到 `map → camera_init` 也不能马上判定 GICP 成功？
3. 已有规划轨迹，但底盘不动：如何从控制器追到下位机？你说的“已有轨迹”是哪个话题、什么类型、是否新鲜？

完成源码查找练习并能独立解释上述问题后，可将 A01 记为“已验收”。本课程统一使用“未开始、学习中、已实操、已验收、待复习”五个状态；对 A01，“已实操”指已经完成源码查找练习。NUC 运行系统检查属于后续课程预览，未执行时记录待实操，不作为 A01 的通过门槛。下一课是 **A02：工程运行机制**，按 [ROADMAP](../ROADMAP.md) 继续，把 `package.xml → CMake → install → launch → YAML → 节点/插件` 串起来。

<details>
<summary>验收题提示：请先独立回答，再展开</summary>

**第 1 题：先区分消息存在与输入可用。** 先确认当前点云真的是 Point-LIO 订阅的 `/livox/lidar`、类型为 `CustomMsg`，有实际发布者和订阅者，QoS 能匹配。再核对主 IMU 的实际 IP 话题与 launch 覆盖参数、IMU 是否持续更新、点云/IMU 时间关系是否允许同步以及初始化日志。随后看 `/aft_mapped_to_init` 是否更新；若该消息正常而画面不动，就转查显示固定坐标系、TF 和时间，而不是立刻改滤波噪声。若无里程计输出，再沿回调、同步、初始化和滤波更新向内追。

**第 2 题：重点是局部参考系到先验地图的对齐链。** 查 GICP 是否启动、是否收到配置指定的 `/cloud_registered_full` 与里程计、先验 PCD 路径是否从正确工作目录解析、地图是否对应当前场地、初值/裁剪是否合理。检查匹配质量、稳定窗口与日志，再核对 `map → camera_init`。配置存在 `timeout_seconds` 和 `default_pose_on_timeout`，超时也可能发布默认对齐，因此 TF 存在只证明有变换，不证明 GICP 收敛。还要区分先验 PCD 与 Nav2 二维地图的原点和版本问题。

**第 3 题：把可视化、控制输入、控制输出和执行分开。** 先分清 `/opt_path_vis` 只是 `nav_msgs/Path` 显示，MPC 的主要轨迹输入是自定义 `/opt_path`。确认轨迹新鲜有效、控制服务器 active、导航任务与 FollowPath 正在推进、里程计及 TF 可用，然后查 `/cmd_vel_mpc` 是否有合理非零输出。若始终为零，查目标距离、参考接收、求解及停止条件；若已有合理命令而车不动，继续查 communication 是否订阅、协议转换与串口发送、模式/状态/使能、下位机接收与执行。不能把手工发布非零速度作为本课只读排查步骤，也不能仅凭 `/cmd_vel` 的状态推断这条 `/cmd_vel_mpc` 链。

</details>
