# MID-360 PTP 时间同步原理与官方文档

更新日期：2026-10-04。  
适用场景：Ubuntu 22.04 / ROS 2 Humble / NUC / 双 MID-360，结合本仓库的驱动、双雷达融合和离线外参标定理解。  
状态：官方资料与本地实现已静态核对；实际网口、PHC、固件、PTP 精度和硬件运行尚未验证。

本文以自己的说明、推导和例子解释原理，官方资料在对应段落和末尾给出。设备实际行为以型号、固件、抓包及测量为准。操作顺序另见[可逐步骤实现的双雷达外参标定](可逐步骤实现的双雷达外参标定.md)。

## 1．PTP 在 MID-360 上解决什么问题

**PTP 校准设备之间的时钟，让不同设备的测量时间可以比较。**

假设在同一真实时刻，前雷达的时钟显示 10.000 s，后雷达显示 10.020 s。它们相差 20 ms；如果算法把两个数字都当作同一个正确时间，就会误判测量的先后关系。

还要考虑时钟走速。即便某一瞬间对齐，两台设备的振荡器走速略有不同，也会逐渐偏离。PTP 会持续交换同步报文，估计偏差并跟踪时钟，而不是只在启动时设置一次时间。

对于本项目，同步是后续时间配对、IMU 插值和点云运动补偿的前提。它不会求解雷达安装位置，不会修复网络丢包，也不会清除算法队列积压。

MID-360 中文用户手册确认支持 IEEE 1588-2008（PTP v2）和 GPS 同步；PTP 使用以太网进行时钟同步。参见[用户手册第 14 页，PDF 第 16 页](https://terra-1-g.djicdn.com/851d20f7b9f64838a34cd02351370894/Livox/Livox_Mid-360_User_Manual_CHS.pdf#page=16)。

## 2．谁提供时间，谁跟随时间

在你的部署中，可以让 NUC 提供时间，两台 MID-360 跟随它。

硬件时间戳模式的关系可以表示为：

```text
NUC 系统时间 CLOCK_REALTIME
        │
        ├── phc2sys ── 网口 1 的 PHC ── ptp4l / PTP ── 前 MID-360
        │
        └── phc2sys ── 网口 2 的 PHC ── ptp4l / PTP ── 后 MID-360
```

| 名称 | 含义 | 此处作用 |
|---|---|---|
| 主时钟，Master / Grandmaster | 提供网络同步参考的时钟 | 此处由 NUC 的同步方案提供 |
| 从时钟，Slave | 根据同步报文跟随参考时钟 | MID-360 |
| `CLOCK_REALTIME` | Linux 的系统墙上时间 | ROS 实机时间通常以系统时间为基础 |
| PHC，PTP Hardware Clock | 网卡提供的硬件时钟 | 在硬件模式下为网络时间戳提供时基 |
| `ptp4l` | 处理 PTP 协议交换的程序 | 通过相应网口与设备进行同步 |
| `phc2sys` | 同步主机内部时钟的程序 | 此场景下使 PHC 跟随选定的系统参考，兼顾时间尺度 |

图中两个网口的 PHC 可能是不同设备，也可能实际共享一个。若共享，不能给同一硬件时钟同时运行两套调整程序。软件时间戳模式直接依赖系统时钟，其结构与上图不同。

Livox 官方说明设备在 PTP 中作为从时钟，并在网络提供正常主时钟后自动进行同步。参考[时间同步说明中的 PTP 章节](https://livox-wiki-cn.readthedocs.io/zh-cn/latest/tutorials/new_product/common/time_sync.html)。

双网口直连时，两条独立链路可以由同一系统参考派生同步服务；不能让两个未对齐的网卡时钟独立作为参考。同一雷达链路上也应避免出现互相竞争的时间源。

## 3．四个时间戳怎样算出时钟偏差

下面解释 Livox 官方 PTP 原理章节给出的两步（two-step）、端到端请求响应模型。gPTP 的链路延迟交换不同，不把两套流程混在一起。原理来源见[Livox 官方同步说明](https://livox-wiki-cn.readthedocs.io/zh-cn/latest/tutorials/new_product/common/time_sync.html)。

### 3.1 报文与时间点

```text
主时钟 / NUC                                      从时钟 / MID-360
     │                                                 │
 t1  │──────────── Sync ───────────────────────────────>│ t2
     │                                                 │
     │──────────── Follow_Up：给出实际 t1 ─────────────>│
     │                                                 │
 t4  │<─────────── Delay_Req ───────────────────────────│ t3
     │                                                 │
     │──────────── Delay_Resp：给出实际 t4 ────────────>│
     │                                                 │
```

| 时间 | 在哪台设备上记录 | 表示什么 |
|---|---|---|
| `t1` | 主时钟 | Sync 实际发出的时间 |
| `t2` | 雷达时钟 | Sync 实际收到的时间 |
| `t3` | 雷达时钟 | Delay_Req 实际发出的时间 |
| `t4` | 主时钟 | Delay_Req 实际收到的时间 |

`Follow_Up` 的作用是携带前一条 Sync 的实际发送时间。它不是把自己的发送时间当作 `t1`。`Delay_Resp` 同理，回传的是主时钟记录的 `t4`。

### 3.2 明确符号，再推导

设雷达时钟比主时钟快 `θ`，两个方向传输延迟都为 `d`。暂时忽略一次交换期间很小的走速变化：

```text
t2 - t1 = d + θ
t4 - t3 = d - θ
```

将两式相加，得到延迟估计：

```text
d = [(t2 - t1) + (t4 - t3)] / 2
```

将两式相减，得到时钟偏差：

```text
θ = [(t2 - t1) - (t4 - t3)] / 2
```

这里 `θ > 0` 表示雷达时钟快于主时钟。上述延迟式与官方资料中的 `[(t4 - t1) - (t3 - t2)] / 2` 等价。

由此可见，不能把收到 Sync 时的 `t2 - t1` 全部当成时钟偏差；其中还包含传输时间。

### 3.3 自建数值例子

下面只是解释数学的例子，不是 MID-360 实测参数。四个时间单位均为微秒：

```text
t1 = 1000
t2 = 1120
t3 = 2000
t4 = 2080
```

因此：

```text
正向观测差 = 1120 - 1000 = 120 μs
反向观测差 = 2080 - 2000 =  80 μs

单向延迟估计 d = (120 + 80) / 2 = 100 μs
时钟偏差估计 θ = (120 - 80) / 2 =  20 μs
```

这个例子中雷达时钟快 20 μs；扣除估计偏差后，才能与主时钟对齐。持续同步还需要跟踪时钟走速，不能只做这一次减法。

### 3.4 为什么网络不对称会影响精度

如果正向延迟是 `d_f`，反向是 `d_r`，按上面的对称模型计算会得到：

```text
估计偏差 θ_hat = 真实偏差 θ + (d_f - d_r) / 2
```

所以不对称延迟会混入偏差估计。硬件时间戳可以减少部分主机软件抖动，但不能自动消除所有链路不对称。这是对上述公式的推论。

## 4．为什么同步要持续运行

时钟偏差可以粗略写成：

```text
θ(t) ≈ 初始偏差 + 相对走速误差 × 经过时间
```

例如，仅用于理解的 20 ppm 相对走速误差，经过 60 s 会累计约 1.2 ms；这个数不是 MID-360 的硬件规格。

实际同步程序利用多次观测和时钟控制环跟踪变化。启动阶段应先等待同步状态稳定，再采集；采集和算法运行期间保持同步服务，避免主动改变时基。

与网络报文有关的时钟控制和日志含义可进一步查看 [ptp4l 官方说明](https://www.linuxptp.org/documentation/ptp4l/)。

## 5．硬件时间戳和软件时间戳的区别

同步计算需要的是报文实际发送、接收时刻。若时间点记录得晚或抖动大，估计值也会受到影响。

| 方式 | 时间戳记录位置 | 对理解精度的意义 |
|---|---|---|
| 软件时间戳 | 主机软件/内核网络处理位置 | 更容易受到调度、排队和软件处理抖动影响 |
| 硬件时间戳 | 网卡支持的硬件位置 | 可减少主机软件路径对时间点的影响，但仍需正确时基与链路配置 |

linuxptp 的 `-H` 选择硬件模式，`-S` 选择软件模式。多端口硬件模式还涉及 PHC 是否一致；不同 PHC 的方案需要额外同步这些时钟。参见 [ptp4l 的时间戳选项及多 PHC 说明](https://www.linuxptp.org/documentation/ptp4l/)。

**协议时间戳以 ns 表示，不等于实际同步误差达到 1 ns。** 时间表示分辨率、时钟同步误差和传感器采样误差是三个不同概念。此处不替你的设备预设未经测量的精度。

## 6．PTP 怎样进入 MID-360 数据和 ROS 消息

### 6.1 设备协议中的时间类型

MID-360 协议的数据头有 `time_type` 和 `timestamp`。类型含义如下，时间数值为无符号 64 位纳秒：

| `time_type` | 时基含义 |
|---|---|
| `0` | 未使用同步源，设备上电后计时 |
| `1` | 使用 PTP/gPTP 的主时钟时间 |
| `2` | GPS 同步 |

原始点云包的时间戳对应首点；包内还有采样时间间隔信息。官方协议的同一章也说明 IMU 数据类型。查阅[点云与 IMU 数据协议 → 时间戳](https://livox-wiki-cn.readthedocs.io/zh-cn/latest/tutorials/new_product/mid360/livox_eth_protocol_mid360.html)。

不要套用旧 Mid-40 等产品协议的 GPS 枚举值；以 MID-360 对应协议为准。

### 6.2 本项目的 `CustomMsg`

驱动把雷达数据组成 ROS 消息，一条消息包含一段时间内的多个点。关键字段是：

```text
CustomMsg.header.stamp
CustomMsg.timebase
CustomMsg.points[i].offset_time
```

在当前驱动实现中，消息起始时间用于 `timebase` 和 `header.stamp`；点偏移根据该点时间与消息基准时间之差生成。因此单点采样时间的重建方式是：

```text
t_point_i_ns = timebase + points[i].offset_time
```

这是本地源码结论，参见 [`lddc.cpp`](../src/perception/livox_ros_driver2/src/lddc.cpp) 的 `InitCustomMsg` 及点字段填写过程，以及 [`CustomMsg.msg`](../src/perception/livox_ros_driver2/msg/CustomMsg.msg)。

点云不是所有点在同一瞬间采样。即使一帧有一个 `header.stamp`，也仍要使用每个点的时间信息进行运动补偿。

### 6.3 IMU 采样时间

当前驱动将设备 IMU 时间写入 `sensor_msgs/Imu.header.stamp`，位置在 [`lddc.cpp`](../src/perception/livox_ros_driver2/src/lddc.cpp) 的 `InitImuMsg`。

所以算法要对照点的采样时间与 IMU 时间。它们的网络到达顺序不一定相同；收到某帧点云时，覆盖帧末尾所需的 IMU 也可能还在路上。

### 6.4 当前驱动有一个必须知道的回退

在 [`pub_handler.cpp`](../src/perception/livox_ros_driver2/src/comm/pub_handler.cpp) 的 `GetEthPacketTimestamp` 中：

```text
PTP/gPTP 或 GPS 类型：使用设备数据包内时间
其他类型：返回主机高分辨率时钟的当前计数
```

因此未同步时，ROS 时间戳也可能看起来接近电脑当前时间。**不能仅凭这种现象证明 PTP 成功。** 主机接收路径上的时间也不能等同于设备真实采样时间。

检查数据包时基类型、实际同步交互和 ROS 数据连续性，要一起进行。`CustomMsg` 本身没有公开 `time_type` 字段，不能直接对这个 ROS 消息执行一个字段查看命令来读取它；需要 Viewer 或底层数据包检查。

## 7．时钟同步不等于两台雷达同时采样

把两块钟校准后，两台设备可以用同一时基描述采样时刻，但它们仍可能在不同的物理时刻采样、按不同边界组成消息、经历不同的传输延迟。

例如统一时基下，前雷达某帧参考时间是 10.000 s，后雷达是 10.003 s。这可能是实际采样或组帧差异，不足以单独断言两块钟有 3 ms 偏差。

本项目后续仍需处理：

```text
PTP：校准时钟
        ↓
驱动组帧：用时间信息组织点云
        ↓
双雷达配对：选择参考时间接近的两帧
        ↓
IMU 插值与运动补偿：处理帧内及帧间的运动
        ↓
外参变换或 Point-LIO 估计
```

[`offline_calibrator.cpp`](../src/perception/dual_lidar_calibration/src/offline_calibrator.cpp) 会按 `sync_tolerance_ns` 配对帧，并检查各自 IMU 的时间覆盖，再将两帧补偿到共同参考时间。

`sync_tolerance_ms: 5.0` 是配对窗口，不是 PTP 校准参数；扩大它不会修复时钟偏差，反而可能接受时间距离更大的测量。

## 8．为什么时间误差会表现为点云错位

对移动中的刚性组件，一阶近似可以帮助判断量级：

```text
直线运动位置差 ≈ 速度 v × 时间差 Δt
转动角度差     ≈ 角速度 ω × 时间差 Δt
距离 r 处的横向差 ≈ r × ω × Δt
```

例如用来理解的 `r = 10 m`、`ω = 1 rad/s`、`Δt = 5 ms`，转动项可产生约 0.05 m 的横向差。不是说每个场景一定出现 5 cm 误差，而是说明时间问题可以在运动中转化为几何问题。

由此推断，静止时较好、转动时重影，需要同时检查时间与运动补偿；静止时也有固定错层，则更应优先检查外参、前后身份和变换方向。两类故障可能同时存在，不能仅凭单一现象定论。

## 9．PTP、gPTP、UTC 和本项目参数的边界

### 9.1 PTP 与 gPTP 的配置不能仅按传输方式判断

MID-360 当前官方协议列有 IEEE 1588v2.0 UDP/IP 和 gPTP L2，并说明不要混用相关模式；协议也明确不支持 IEEE 1588v2.1。具体以设备型号、固件和对应协议为准。[MID-360 通信协议时间戳章节](https://livox-wiki-cn.readthedocs.io/zh-cn/latest/tutorials/new_product/mid360/livox_eth_protocol_mid360.html)

linuxptp 的 `-4` 选择 UDP/IPv4，`-2` 选择二层传输。`-2` 本身不等于已经完整配置正确的 gPTP profile；延迟机制、协议字段和配置文件还要匹配。仓库脚本采用 `-2`，解释或调整它时需检查整套配置，不能仅替换一个开关就宣称验证通过。[ptp4l 参数说明](https://www.linuxptp.org/documentation/ptp4l/)

### 9.2 `-O 0` 不是通用的时基正确性保证

Livox 官方时间同步示例使用 `phc2sys -c eth0 -s CLOCK_REALTIME -O 0`；这是官方示例和本仓库采用的设置。[Livox 官方同步示例](https://livox-wiki-cn.readthedocs.io/zh-cn/latest/tutorials/new_product/common/time_sync.html)

另一方面，linuxptp 官方说明硬件模式的 PTP 时间尺度与系统 UTC 之间可能需要整秒偏移，`phc2sys` 用相关信息维护它。[phc2sys 的 TIME SCALE USAGE](https://www.linuxptp.org/documentation/phc2sys/)

因此此前教学给出的零偏移命令应理解为待核验的设备接入示例，**不是已经证明对你的网卡、固件和 ROS 时基正确的最终方案**。也不能只看见资料中的另一个整秒值就直接替换。实际部署应核对同步配置、设备输出时基与系统/ROS 时间的一致性。

### 9.3 三种不同的“时间差”

| 项目 | 含义 | 不能用什么替代验证 |
|---|---|---|
| 时钟偏差 | 同一真实时刻，不同时钟的读数差 | 两个不同采样时刻的消息时间差 |
| 采样/帧参考时间差 | 数据实际在何时测得、何时组帧 | 主机收到消息的先后顺序 |
| 处理滞后 | 算法处理的测量落后当前真实时间多久 | 单次算法计算耗时 |

`common.time_diff_lidar_to_imu`、双雷达配对窗口、PTP 时钟设置各有含义，不能将它们当成同一种调参旋钮。

## 10．怎样证明部署后的同步可用

分层保留证据，而不是只截一条进程日志：

| 层次 | 建议证据 | 能支持的结论 |
|---|---|---|
| 主机内部时钟 | 网口 PHC 能力、phc2sys 的稳定偏差日志 | 主机选定时钟之间的同步情况 |
| PTP 协议链路 | 各接口持续的同步与延迟交换、主时钟身份、错误日志 | 该链路确实在运行预期协议 |
| 雷达时基 | Viewer 的 Sync Type、设备数据头 `time_type` | 设备输出采用哪种时基 |
| ROS 数据 | 四路时间戳连续性、覆盖情况、实际数据源 | 下游是否获得可配对的数据 |
| 应用结果 | 固定数据的配对统计、运动中的重影、重复标定结果 | 同步配置与整个算法链是否满足任务需求 |

`ptp4l` 主机进入 MASTER 不等于已经测量出雷达残余同步误差；`phc2sys` 的小偏差是主机时钟之间的证据，也不是雷达误差。类型为 `1` 同样不独立证明具体精度或后续所有时刻的链路健康。

先做只读调查，网口名称替换为实际接口：

```bash
ip -br link
ip -br addr
ethtool -T enp1s0
ethtool -T enp2s0
ptp4l -v
timedatectl
```

确认接口和时钟能力后再形成适合这台 NUC 的启动配置。本文件没有运行 PTP，也没有测量或保证任何具体同步精度。

## 11．官方文档阅读顺序

| 顺序 | 文档 | 重点阅读 |
|---|---|---|
| 1 | [Livox 中文时间同步说明](https://livox-wiki-cn.readthedocs.io/zh-cn/latest/tutorials/new_product/common/time_sync.html) | 四时间戳、同步状态检查、主时钟配置示例 |
| 2 | [MID-360 中文用户手册 PDF](https://terra-1-g.djicdn.com/851d20f7b9f64838a34cd02351370894/Livox/Livox_Mid-360_User_Manual_CHS.pdf#page=16) | 印刷第 14 页 / PDF 第 16 页：时间戳与 IMU；第 20 页：规格 |
| 3 | [MID-360 中文通信协议](https://livox-wiki-cn.readthedocs.io/zh-cn/latest/tutorials/new_product/mid360/livox_eth_protocol_mid360.html) | 点云与 IMU 数据协议 → 时间戳，查看 `time_type` 和数据头 |
| 4 | [ptp4l 官方手册](https://www.linuxptp.org/documentation/ptp4l/) | 传输、时间戳模式、PHC 和延迟机制 |
| 5 | [phc2sys 官方手册](https://www.linuxptp.org/documentation/phc2sys/) | 时钟源/目标、同步方向与 TIME SCALE USAGE |
| 6 | [Livox 官方 MID-360 下载页](https://www.livoxtech.com/cn/mid-360/downloads) | 更新手册、Viewer 和固件资料的入口 |

中文用户手册核对版本为 2024.04 v1.2；在线协议和软件手册会更新，不能直接假定所有新参数已存在于 NUC 的安装版本。

项目内对应阅读：

- [`scripts/ptp_sync.bash`](../scripts/ptp_sync.bash)：目前单接口的同步方案。
- [`pub_handler.cpp`](../src/perception/livox_ros_driver2/src/comm/pub_handler.cpp)：设备时基选择与未同步回退。
- [`lddc.cpp`](../src/perception/livox_ros_driver2/src/lddc.cpp)：ROS 点云和 IMU 时间字段。
- [`bag_reader.cpp`](../src/perception/dual_lidar_calibration/src/bag_reader.cpp)：离线工具如何重建点采样时间。
- [`offline_calibrator.cpp`](../src/perception/dual_lidar_calibration/src/offline_calibrator.cpp)：配对与 IMU 覆盖检查。
- [双雷达外参标定逐步指南](可逐步骤实现的双雷达外参标定.md)：采集和标定的实际顺序。

## 12．仓库有没有“一键部署”，PTP 是什么代码

**仓库提供统一启动入口；使用前仍须完成环境和设备配置。PTP 是时间同步协议，由系统程序与雷达固件共同执行。**

| 层次 | 对应内容 | 在本项目中的职责 |
|---|---|---|
| 协议 | PTP / IEEE 1588 | 规定时钟同步报文和时间计算方法 |
| 系统程序 | linuxptp 的 `ptp4l`、`phc2sys` | 运行在 Ubuntu，处理网络同步和主机时钟关系 |
| 仓库脚本 | `scripts/ptp_sync.bash` | 调用已安装的程序，设置接口、日志与进程管理 |
| 雷达固件 | MID-360 内部同步实现 | 跟随主时钟，把同步后的时间写入测量数据 |
| ROS 驱动与算法 | Livox 驱动、融合、Point-LIO | 读取测量时间，执行配对、运动补偿与估计 |

### 12.1 统一入口怎样调用它

[`start.bash`](../start.bash) 第 2 行进入原作者的 `~/2027-sentry-navi`，第 3 行加载 `install/setup.bash`，第 6 行新建终端执行同步脚本。当前启用顺序是：

```text
start.bash
    → scripts/ptp_sync.bash
    → 双雷达驱动 + Point-LIO
    → GICP 重定位
    → Nav2 导航
    → 行为树
    → 串口通信
```

这属于配置和构建完成后的统一启动。该入口不会安装依赖、编译工程、配置网卡 IP、获取设备地址或求解外参；Foxglove 和录包行当前为注释。它使用固定 `sleep` 间隔，PTP 后等待 8 秒，并没有以雷达同步成功作为后续启动条件。

### 12.2 同步脚本实际执行什么

[`scripts/ptp_sync.bash`](../scripts/ptp_sync.bash) 当前固定 `INTERFACE="enp86s0"`。核心命令按源码列出如下，只用于阅读；运行部署时先核对真实设备配置：

```bash
ptp4l -i enp86s0 -2 -m -l 6
phc2sys -c enp86s0 -s CLOCK_REALTIME -O 0
```

源码还为这些命令加了输出缓冲和实时调度包装，将日志写入 `/tmp/ptp4l_enp86s0.log`、`/tmp/phc2sys_enp86s0.log`。第一条处理指定接口上的 PTP 交换；第二条以系统时钟为源，使该接口对应的 PHC 跟随它，采用脚本指定的零偏移。`-2`、硬件能力和时间尺度的核对见第 5、9 节。

脚本要求 sudo，查找本机已有可执行程序，并会停止 NTP/time sync 服务、结束已有 `ptp4l` 和 `phc2sys` 进程。它没有安装 linuxptp 的操作；打印“已启动”也不代表程序健康或雷达已经同步。

### 12.3 你的双网口直连需要先完成哪些配置

1. 获取 NUC 上两个真实接口名，确认每个接口对应哪台雷达及其 PHC 能力。
2. 确定两条链路采用的协议模式，核对设备固件、传输方式和主机/雷达时间尺度。
3. 安装并核对 linuxptp，依据 PHC 是否共享选择同步方案。
4. 适配单接口脚本的接口与进程管理。原脚本有全局 `killall -9`，直接运行两份会互相终止同步进程。
5. 修正 `start.bash` 的工作目录，完成依赖、编译、驱动 IP、外参等部署配置。
6. 独立验证 PTP 链路和数据时基，再验证驱动与算法，最后使用统一启动入口复现。

无需在 Point-LIO 中重新实现 PTP 协议。该问题的配置入口主要在同步脚本与系统服务，算法端仍需正确使用时间戳；现有代码不能替代实机同步验证。

## 13．学习核对

- [ ] 能解释为什么 `t2 - t1` 不是纯粹的时钟偏差。
- [ ] 能说明 `t1/t4` 来自主时钟、`t2/t3` 来自雷达时钟。
- [ ] 能解释 PHC、ptp4l、phc2sys 各自的职责。
- [ ] 能区分 PTP 协议、Ubuntu 系统程序、仓库脚本和统一启动入口。
- [ ] 能从 `timebase + offset_time` 得到单点采样时间。
- [ ] 能区分时钟同步、帧配对和算法处理滞后。
- [ ] 知道当前驱动的未同步回退为何不能作为 PTP 成功证据。
- [ ] 能解释配对窗口 5 ms 与实际同步精度的区别。
- [ ] 对真实网口、固件、时间尺度和同步效果完成实机验证后，再记录具体结论。

未执行构建：AGENTS.md 禁止在未获用户明确许可前运行构建命令。本次只创建原理与资料文档，不改运行配置，不将设备实操标记为完成。
