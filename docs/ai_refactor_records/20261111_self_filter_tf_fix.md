# 车体点云过滤器 TF 并发与字段保留改造记录

> 本记录按执行顺序保留两轮修改。当前最终实现为双线程、最多 3 帧的非阻塞等待队列和 5 ms 检查周期；50 ms 等待预算保持不变。首轮双线程阻塞查询的历史验证结果不代表最终队列已通过真实负载验收。

## User Intent

用户确认“就这么改”：按已讨论建议修复车体过滤器等待 TF 导致输出稀少的问题，并保留原始点云字段。采用最小修改，先验证现有等待时间，不新增等待队列。

## Scope

odom / pointcloud、过滤器自身 executor 调度；修改 Python 过滤器、增加必要测试、同步已安装的 Python 脚本副本。用户明确授权过滤器双线程调整，不涉及导航容器或其他节点调度。

## Out of Scope

不改 Point-LIO/GICP、planner/MPC、比赛参数、launch、topic、frame、QoS、裁剪盒或等待时间。不开车、不重启正在运行的导航、不发送导航目标。不构建、不执行 Git 写操作。

## Explorer Findings

### Files inspected

- 仓库 AGENTS.md、cpp-incremental-task-executor/SKILL.md。
- src/navigation/navi2_bringup/scripts/pointcloud_self_filter.py。
- navi2_bringup 的 navigation2.launch.py 与 CMakeLists.txt 中安装规则。
- 本机 ROS Humble tf2_ros 的 transform_listener.py、buffer.py，以及 sensor_msgs_py 点云实现。
- install/navi2/lib/navi2/pointcloud_self_filter 的文件类型与内容。

### Active logic path

navigation2 启动独立 Python 过滤节点。输入 /cloud_registered_full，经 camera_init→body 的点云同时间戳变换判断裁剪范围，输出 /cloud_registered_filtered，ROGMap 与 STVL 使用该输出。

### Data flow

旧过滤器由默认单线程 rclpy.spin 调度。点云回调执行带超时的 TF 查询，本机实现通过 sleep 轮询等待缓存，而监听器的订阅回调也需要执行器运行。TF 监听器已有 ReentrantCallbackGroup，旧执行器仍只有一个线程，等待期间不能处理随后到达的 TF。失败后曾用有限时间差的 latest TF 回退。

旧输出通过 create_cloud_xyz32 重建，仅有 XYZ；源 intensity、其他字段与每点填充字节被丢弃。

### Risk notes

- 之前实测 12 秒完整点云 168 帧、过滤输出 1 帧。并发修复通过合成测试验证，不等于已验证真实导航负载下的输出率。
- TF 若确实晚到超过等待时间，仍丢弃该帧；本次不放宽容差或采用旧姿态。
- 双线程仅使 TF 回调可以并发；点云订阅仍在默认互斥组，保持逐帧串行处理。
- 移除 latest 回退是已确认流程的有意改变：只使用点云指定时刻可查询的 TF（包括 TF 库正常插值），不使用任意更新时刻的最新姿态替代。

### Recommended modification boundary

只改过滤器执行器、TF 查询路径与输出打包；暂不新增队列/定时器/参数，不触及规划控制策略。

## Modifier Changes

### Files changed

- src/navigation/navi2_bringup/scripts/pointcloud_self_filter.py。
- src/navigation/navi2_bringup/test/test_pointcloud_self_filter.py（新增）。
- .gitignore（仅追加本次测试与记录的精确例外，保留原有忽略规则和用户修改）。
- install/navi2/lib/navi2/pointcloud_self_filter（生成目录中的既有 Python 副本，同步源码）。
- 本记录。

### Key changes

- 主入口使用 MultiThreadedExecutor(num_threads=2)，复用 TF 监听器已有的独立回调组；退出先关闭执行器，再销毁节点，处理 KeyboardInterrupt/ExternalShutdownException。
- 按 header.stamp 查询 TF，沿用 transform_timeout=0.05；不再用 latest TF 回退。
- 先计算有限 XYZ 点的车体裁剪掩码，再从原消息中复制完整点记录；支持组织点云的 row padding，保留大小端、fields、point_step、每点填充字节、原坐标/header。输出为紧凑 height=1 点云，row_step 按保留点数计算；is_dense 保守沿用输入。
- 去除 .tolist()/create_cloud_xyz32 重建路径，不再丢弃 intensity 等额外字段。
- 同步安装脚本采用纯文件复制，没有配置、编译、链接或代码生成。已核对源与副本逐字节相同；运行中的进程没有被重启。

### Behavior preserved

输入/输出话题、SensorDataQoS、body frame、裁剪范围、50 ms 等待配置不变。XYZ 非有限点继续删除；输出点仍在原始世界坐标系。其他用户工作区改动保留。

### Behavior intentionally adjusted

等待 TF 时允许 TF 回调继续执行；超时不再回退旧 TF；过滤输出保留完整点字段。

### Notes

本次不涉及修改比赛策略。新增测试直接执行，不新增构建依赖或 CMake 注册。未使用多 Agent；没有 Git 提交类操作。

## Auditor Review

### Checks performed

- [x] 关键路径检查：TF 独立回调组、点云回调互斥、按时间戳匹配、掩码与字节索引一致。
- [x] diff 检查：源码仅过滤器改动；未改 launch、参数、规划控制模块。
- [x] grep 检查：旧 XYZ-only 发布及 latest 查询路径移除；保留 input/output/body/timeout 配置。
- [x] XML / launch / yaml 检查：本轮未改这些文件；过滤器与测试 Python AST 解析通过。
- [x] 用户允许范围内的测试或静态检查：5 项离线测试、隔离 ROS 并发测试、git diff --check。
- [ ] 如需构建，已取得用户明确许可：本轮无构建需要，未执行构建。

验证命令与结果：

1. `source /opt/ros/humble/setup.bash` 后执行 `PYTHONDONTWRITEBYTECODE=1 python3 src/navigation/navi2_bringup/test/test_pointcloud_self_filter.py -v`：5 项测试通过。覆盖小端/大端、组织点云行填充、intensity/ring/tag 与每点填充字节、NaN 删除、车体坐标裁剪但保留世界坐标、按时间戳拒绝旧 TF、空输出、截断输入拒绝。
2. 独立 ROS_DOMAIN_ID=174、ROS_LOCALHOST_ONLY=1、/tmp 日志下运行 `/tmp/validate_self_filter_delayed_tf.py`。只启动源码过滤器与合成点云/TF 发布订阅端，不连接实车。每帧先提供 80 ms 前的明显不同姿态，再发布点云，20 ms 后提供正确时刻姿态：30/30 帧正确输出，只删除正确姿态下的车体点，intensity 字节保留。观测输出延迟 21.2–41.8 ms。缺少同时间戳 TF 的额外帧被拒绝，随后有效帧恢复；过滤器 SIGINT 退出码 0。
3. 安装副本与源码逐字节一致，SHA256 为 `a289633d2b7ddefa62bda96b25738e62a5d04b98c383bf7b331cc30041555861`。

### Issues found

本次隔离测试未发现失败。仍需重启实际过滤器/导航后复测前后点云帧率、延迟和车体裁剪效果；没有声称已修复此前独立的速度坐标转换、冷启动策略或导航 action 超时问题。

未执行构建：AGENTS.md 禁止在未获用户明确许可前运行构建命令。Python 脚本已同步安装目录，下次启动即可加载；无需为本次脚本变更执行编译。

### Final result

NEEDS_FIX（源码、离线和隔离 ROS 测试通过；随后真实运行观测到输出仍明显不足，见下文）。

## 用户重启后的运行复测

用户截图显示完整点云约 15.4 Hz、过滤输出约 11.3 Hz，后者最大接收间隔约 0.621 秒。截图未显示命令名，话题对应按此前两个命令的顺序理解；接收间隔不等于单帧处理延迟。

进一步只读同时订阅 12 秒：输入观测 183 帧（15.25 Hz）、输出 80 帧（6.67 Hz）；输入时间戳有 73 个在输出中匹配。匹配帧在本诊断节点上的输入/输出接收时间差中位 59.44 ms、P95 88.25 ms、最大 179.22 ms。输出时间戳年龄中位 78.64 ms、P95 115.16 ms、最大 223.11 ms。两路均为 SensorDataQoS 观测，窗口边界、订阅端丢包与额外监测负载可能影响计数，不能将比例直接当作过滤器内部精确丢弃率。

输出字段含 x/y/z/intensity/normal_x/normal_y/normal_z/curvature，字段保留修复已在真实输入上生效。新日志仍有按点云时间戳查询 TF 的超时。

另一次 10 秒仅订阅完整点云和 TF 的观测：147 帧点云、681 条 body TF；点数 14,823–16,437，最大消息 788,976 字节。第一个时间戳可覆盖点云的 body TF，相对点云在该诊断节点上的接收时间差：中位 42.32 ms、P95 47.03 ms、最大 54.11 ms，约 3.4% 超过 50 ms。这证明许多帧查询所需 TF 在点云之后才可用，且等待时间接近当前上限；不能据此把所有输出差额都归因于超过 50 ms。不同节点的回调调度和处理耗时仍需区分。

源码核对：Point-LIO 高频 odom/TF 由成功点组更新按 time_current 限频发布，完整点云在扫描结束后按 lidar_end_time 发布，时间戳并不保证逐帧相同。需等待后续覆盖时刻的 TF，不能把旧姿态伪装为同时间戳结果。

本轮仅观测并补充记录，未继续改源码、增加队列或调整参数，未构建。真实负载验收未通过；下一步需核对等待/计算/调度耗时，并评估此前讨论的小容量非阻塞等待队列。

## 第二轮：非阻塞有界等待队列

### User Intent / Scope

用户继续反馈 TF 超时、Large velocity error 与 UART unavailable 日志。本轮延续其此前“就这么改”确认的流程，其中包含“如仍因 TF 到达较晚丢帧，再增加小容量等待队列”。仅继续修改过滤器及其测试；不改 50 ms 预算、裁剪范围、QoS、话题、规划控制或串口设置。

### Explorer Findings

短时订阅真实输入、仅输出到独立诊断话题的旧实现耗时探针：155 次点云回调、133 次发布；回调中位 47.26 ms、P95 66.55 ms；TF 查询中位 41.22 ms、P95 62.67 ms；回调减去 TF 查询的剩余耗时中位 3.64 ms、P95 10.49 ms；publish 调用中位 0.62 ms。说明该切片中同步 TF 等待是主要耗时。临时探针不修改生产节点，不发送运动命令，结束后退出。

用户日志中的 /dev/rm_nav0 无法打开是独立的运动链路问题。不能把轨迹速度偏差全部归为过滤器；本轮没有推断实车实际是否由其他链路驱动。

### Modifier Changes

- 点云回调只把消息引用和单调时间加入最多 3 帧的队列，然后尝试处理。队列满时 deque 丢弃最旧待处理帧，内存占用有界。
- 新增节点内部 5 ms 定时检查，使用无等待的同时间戳 TF 查询；TF 尚未可用就立即让出回调。继续保留双线程及 TF 的独立回调组。
- 点云入队与定时处理同属默认互斥回调组，队列访问、过滤和发布保持串行；按队列顺序输出。
- 队列等待使用原有 transform_timeout=0.05 和单调时间，过期帧丢弃，即便其 TF 后来已经可用也不补发过期帧。timeout=0 时维持只尝试立即查询、不排队等待的语义。
- 独立 _filter_cloud 复用首轮的完整字段/原始坐标/时间戳保留逻辑。没有添加运行统计或高频性能日志，沿用告警抑制状态。
- 测试新增延后 TF 恢复、队列满丢最旧并保持顺序、过期帧不复活及后续有效帧恢复，累计 8 项离线测试。

### Auditor Review

- Python AST、目标文件 git diff --check 通过；8 项离线测试全部通过。
- 独立 ROS 域验证最终 5 ms 定时周期：TF 延后 20 ms，30/30 帧正确输出；观测输出延迟 21.8–26.4 ms。缺少 TF 的帧被拒绝，后续有效帧恢复；SIGINT 退出码 0。
- 针对实测等待约 41 ms，另以 `SELF_FILTER_TEST_TF_DELAY=0.040` 执行同一隔离脚本：TF 延后 40 ms 时 30/30 帧正确输出，观测输出延迟 41.9–46.7 ms；超时拒绝/后续恢复通过，退出码 0。
- 新实现真实输入探针的 12 秒窗口没有收到点云，故未获得新队列在真实负载下的吞吐/延迟对比，不将该探针记为真实负载通过。
- 本轮仍未构建、未重启用户导航或发送运动命令，未执行 Git 写操作。最终同步安装脚本与源码后，下次启动才加载新实现。
- 最终源码 SHA256：`be125d6fe9d6cd7e050062e539d108713aef4221fac478c1ec236b47fd26706b`。首轮哈希为历史记录。

### Final result

NEEDS_FIX（离线与隔离 ROS 验证通过，真实负载验收仍待重启复测；串口设备问题独立未解决）。
