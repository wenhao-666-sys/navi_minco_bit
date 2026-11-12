# 主机导航串口移植 改造记录

> 最新协议以文末“导航协议精简修订”为准；前文记录首次移植的历史状态。

## User Intent

把 QD QYG 串口协议移植到当前导航工作区，在主机运行，删除 vel_rotate。
导航原值发送 /cmd_vel_mpc 的 vx/vy/wz，接收 big_yaw 和同坐标系实际速度，供 Foxglove 对照。
交付已编译的软件与电控协议文档，不做实车验证。
用户明确要求实施已确认方案，已授权相关包构建。

## Scope

launch / communication、串口包、相关参数、Foxglove 和交付文档。
采用单 agent 自行探索、修改、审计，未启用多 agent。
本次修改涉及比赛验证逻辑，采用最小改动策略。

## Out of Scope

不修改 QD_Vision26，不改变 MPC/planner/行为树/地图/里程计/仿真逻辑，
不迁移视觉控制，不创建系统 udev 规则，不做实车验证，不暂存、不提交、不推送。
已有 MPC、planner、仿真及 Foxglove 仿真未提交修改均保留。

## Explorer Findings

### Files inspected

- 旧 vel_rotate/scripts/qd_bridge.bash、vel_rotate_node.py、Foxglove 配置。
- QD rm_serial_driver 的 QYG 帧定义/打包/流式解析、UART、节点、CMake、package.xml。
- QD rm_bringup/config/node_params/serial_driver_params.yaml 与 QYG_PROTOCOL.md。
- navi2_bringup 的 navigation2.launch.py、sentry1.yaml、package.xml、CMakeLists.txt。
- 当前 MPC 的 /cmd_vel_mpc 发布路径；现有 communication 包和仿真入口。

### Active logic path

旧路径：MPC → /cmd_vel_mpc → 主机 vel_rotate → /cmd_vel_rotate → Docker QYG UART。
旧 vel_rotate 由 navigation2.launch.py 启动；使用 big_yaw 做旋转、叠加 cmd_spin，并检查指令/反馈超时。
新路径：MPC → 主机 nav_serial_driver → 独立 /dev/rm_nav0 → 电控。
视觉使用另一根物理串口，保持原仓库和链路。

### Data flow

- 唯一导航输入 /cmd_vel_mpc，SensorData QoS 接收，消息到达立即发送。
- /nav/serial/send：完整写入成功后发布，含主机时间，不能作为电控 ACK。
- /nav/serial/receive：完整 CRC 正确帧的原始反馈，含主机接收时间及 MCU 原始时间。
- /nav/cmd_vel_real：反馈 vx/vy/wz 映射到 Twist。
- 不订阅云台/旧 cmd_chassis/cmd_spin，不发布旧视觉同名话题。
- 无视觉服务、TF 广播或相机依赖。所有串口操作由单线程执行器串行执行，无共享全局控制状态。
- 参数来自新包 config/serial.yaml；独立 launch 提供 port_name、start_serial、use_sim_time，
  导航入口提供 serial_port、start_serial 并传递 use_sim_time。

### Risk notes

- 原 UART 继承 PARMRK 等输入标志会破坏二进制；旧脚本曾临时清除 PARMRK。
- 容器与主机同 ROS 域中旧 /serial 等话题可能混流，故新导航统一 /nav 前缀。
- 两串口电控需分别管理云台和底盘；导航 mode=0 时仍应执行底盘速度。
- 真实 USB 标识、坐标轴正方向、反馈来源和采样频率尚需联调确认。
- 发现未修改的历史 params/nav2_params.yaml 的 robot_base_frame:"" 缺少冒号后空格，
  YAML 解析失败；当前默认入口使用 sentry1.yaml，后者检查通过。未扩大修改范围。

### Recommended modification boundary

复用线协议与 UART，新增纯导航 ROS 适配层；仅替换旧转换包对应的启动和参数。

## Modifier Changes

### Files changed

- 新增 src/navigation/nav_serial_driver：CMake、package、协议/UART/节点、消息、launch、config、
  Foxglove、协议单测、伪终端集成脚本、README、第三方来源声明。
- 修改 navi2_bringup/launch/navigation2.launch.py、package.xml、params/sentry1.yaml。
- 删除 src/navigation/vel_rotate 整包，仅清理 build/vel_rotate 和 install/vel_rotate。
- 新增 docs/串口通信（导航）.md 和本记录。
- .gitignore 添加精确例外，保证本次文档和新包测试不被现有 docs/test_* 忽略规则隐藏。

### Key changes

保持原 34/43 字节布局、小端 float32 和 CRC；主机独立构建，无 QD overlay 依赖。
UART 二进制透明、非阻塞接收、100 ms 有限写等待、失败资源回收及约 1 s 重连。
无串口数据时 5 ms 定时检查，不忙等；单回调读取量受限。
指令超时使用单调时间；0.25 s 后约 20 Hz 零帧。NaN/Inf/float32 溢出归零。
仅 UART 完整 write 成功才发布发送观测。

### Behavior preserved

QYG 帧头、字段偏移/长度/单位、CRC 和原串口 921600/8N1/无流控约定。
原导航算法、传感器启动、视觉仓库、现有 communication 包和用户已有工作区修改。

### Behavior intentionally adjusted

取消 big_yaw 速度旋转、自转叠加及反馈超时阻断，直接传输 MPC vx/vy/wz。
设备独立为 /dev/rm_nav0；ROS 反馈/观测使用 /nav 前缀。
仿真时禁止真实串口启动，真实导航启动默认自动运行新串口。

### Notes

源码来源和原许可声明保留；见新包 THIRD_PARTY_NOTICES.md。
未创建 Git checkpoint，遵守 AGENTS.md 禁止版本控制写操作要求。

## Auditor Review

### Checks performed

- [x] 关键路径检查：MPC 发布、launch 替换、独立串口和消息映射。
- [x] diff 检查：无越界算法改动，保留已有修改。
- [x] grep 检查：新代码/导航入口无旧 vel_rotate、cmd_vel_rotate、Docker 或 rm_interfaces 依赖。
- [x] XML / launch / YAML / JSON 检查：本次改动全部解析通过；历史未修改 YAML 问题单独记录。
- [x] 用户允许范围内的测试或静态检查：协议单测、伪终端集成、bash -n、git diff --check。
- [x] 如需构建，已取得用户明确许可：用户要求交付编译产物并明确要求实施。

构建命令：

```bash
source /opt/ros/humble/setup.bash
colcon build --packages-select nav_serial_driver navi2 --symlink-install --parallel-workers 2 --cmake-args -DBUILD_TESTING=ON
```

最终结果：2 packages finished，零编译警告。主机执行，未使用 Docker。
初次配置在测试文件尚未写完时启动，因 test/test_protocol.cpp 尚不存在失败；
补齐文件后构建成功。首轮构建的 baud 日志格式警告已修复并重新构建验证。

```bash
source install/setup.bash
colcon test --packages-select nav_serial_driver --return-code-on-test-failure
colcon test-result --test-result-base build/nav_serial_driver --verbose
ROS_LOG_DIR=/tmp/nav-serial-ros-log ROS_DOMAIN_ID=88 ROS_LOCALHOST_ONLY=1 python3 src/navigation/nav_serial_driver/test/test_pty_integration.py
```

协议测试：2 个 gtest 用例；colcon 汇总含包装执行条目共 3 tests，0 errors、0 failures、0 skipped。
覆盖编译期帧偏移断言、CRC 0x6F91、速度打包、分片/粘包、噪声、坏 CRC、0xff 和重新同步。
伪终端集成：PASS，覆盖启动零帧、原值下发、无反馈也可发送、写入观测、全部速度/角度反馈、
指令超时、NaN/float32 溢出、终端标志、二进制 0xff、坏帧丢弃、视觉话题隔离、
发送失败无成功观测、重新连接和正常 SIGINT 退出零帧。

初次集成因沙箱限制无法写默认 ROS 日志/创建本机通信套接字，改为 /tmp 日志并经沙箱审批
在主机独立 ROS 域运行。测试启动器原先使用 ros2 run 包装，无法正确向子进程转发测试信号；
改为直接启动安装后的节点二进制，最终测试通过。后续检查未发现遗留测试子进程。

独立 launch 和导航主 launch 的 --show-args 均通过。
独立 launch 的 use_sim_time:=true 与 start_serial:=false 实际执行均正常退出且不启动节点。
ROS 包可发现 nav_serial_node 与 foxglove_velocity.bash。

### Issues found

本次实现问题已修复。未改历史 nav2_params.yaml 语法问题，不影响当前默认 sentry1.yaml 路径。
未实车验证；设备别名和电控坐标/两串口分工仍需接线后确认，见协议文档。

### Final result

PASS（本次主机软件交付范围；不代表实车验收通过）。

## 导航协议精简修订（2026-11-11，当前生效）

### User Intent / Scope

用户明确要求删除导航用不到的字节，不留占位；电控文档只说明电控需要做什么。
本次修改仅限新导航包的协议、消息、节点映射、测试、README、来源说明及电控文档。
原 QD 视觉协议及其仓库不改；UART 配置、ROS 话题、直传、看门狗、启动行为不改。

### Explorer Findings

首次移植为兼容旧协议保留了模式、云台、目标、裁判状态、弹速及 MCU 时间等字段。
这些字段不在当前导航需求中。本次按用户新指令取消旧帧兼容，原移植记录中的
34/43 字节、mode=0、原始其余反馈字段说明均为历史状态，不适用于当前版本。

### Modifier Changes

- 下发：16 字节，QY + vx/vy/wz（各 float32）+ CRC；CRC 覆盖前 14 字节。
- 回传：20 字节，GD + 实际 vx/vy/wz/big_yaw（各 float32）+ CRC；CRC 覆盖前 18 字节。
- 删除所有其他线协议字段、视觉模式/云台辅助函数及节点映射；ROS 消息仅保留主机观测 header 和必要数据。
- 编译期断言更新全部字段偏移；单测与伪终端脚本同步改为新帧。
- 二进制透明性测试在有效 big_yaw 浮点载荷中包含连续 0xff。
- 电控文档压缩为任务要求、16/20 字节字段表、字节序与 CRC；去掉全部 ROS/Foxglove/主机命令和设备绑定说明。
- README 和 THIRD_PARTY_NOTICES.md 同步声明协议精简，不再声称旧布局兼容。

### Auditor Review

- [x] 重新检查节点收发映射、消息定义和全部帧偏移。
- [x] grep 确认无模式/云台/目标/状态/弹速/MCU 时间字段及其辅助函数残留。
- [x] Python 静态解析、新消息字段清单、16/20 字节独立 struct 长度检查、git diff --check 通过。
- [x] 使用会话中已授权的主机构建与软件测试，不连接真实串口、不使用容器。

构建：`colcon build --packages-select nav_serial_driver --symlink-install --cmake-args -DBUILD_TESTING=ON`。
结果：1 package finished，无编译错误或警告。
测试：`colcon test --packages-select nav_serial_driver --return-code-on-test-failure --ctest-args -R test_protocol`，
以及 `colcon test-result --test-result-base build/nav_serial_driver --verbose`。
结果：3 tests（含 gtest 包装条目），0 errors、0 failures、0 skipped。
伪终端集成测试：ROS 域 88，本机 localhost，临时串口；完整测试 PASS，
覆盖新帧速度收发、big_yaw、CRC/拆包/粘包/噪声、指令超时归零、非法数值、
0xff 透明传输、话题隔离、发送失败观测抑制、重连和退出零帧。

### Final result

PASS（主机软件范围）。电控必须使用新的 16/20 字节导航协议；尚未实车验证。
