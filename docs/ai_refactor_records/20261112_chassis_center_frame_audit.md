# 车体中心坐标系核对记录

## User Intent

以车体旋转中心作为导航车体坐标系原点。车体原地转动时，理想情况下原点不移动、坐标轴随车体转动；仅云台转动时，车体坐标系原点和方向均应不变。

## Scope

只读核对 Point-LIO 位姿、base_link TF、导航参考点、速度补偿及串口云台角来源。此次只增加本记录。

## Out of Scope

不修改生产代码、比赛参数、TF 发布权、topic、launch 或串口协议；不运行实车、不构建、不执行 Git 写操作。

## Explorer Findings

### Files inspected

- `src/perception/Point-LIO/src/laserMapping.cpp`
- `src/perception/Point-LIO/config/mid360.yaml`
- `src/navigation/navi2_bringup/launch/navigation2.launch.py`
- `src/navigation/navi2_bringup/params/sentry1.yaml`
- `src/navigation/navi2_bringup/scripts/pointcloud_self_filter.py`
- `src/navigation/minco_controller/src/minco_mpc_controller.cpp`
- `src/navigation/minco_planner/src/minco_core/minco_planner.cpp`
- `src/navigation/nav_serial_driver/src/nav_serial_node.cpp`
- `src/navigation/nav_serial_driver/msg/SerialReceiveData.msg`
- `docs/串口通信（导航）.md`
- `docs/ai_refactor_records/20261024_navigation_drift_audit.md`

### Active logic path

Point-LIO 发布 camera_init→body 的 IMU 位姿，并单独发布 camera_init→base_link、camera_init→slambase。
base_link 位置等于 IMU 位置加按 IMU yaw 旋转的 `(0, 0.20, 0)` 米偏移；base_link 的方向固定为单位四元数。该计算未使用云台相对底盘角度。
slambase 与 IMU 共用位置、仅保留 yaw；mapping_ground 通过静态高度偏移连接 slambase，不是已标定的车体中心。

### Data flow

Nav2 使用 base_link。planner 和 MPC 读取 IMU 里程计，并根据独立配置的 lidar_offset_x/y 补偿速度。
MPC 当前实际调用 compensateLeverArm；全三维速度转换函数 extractGlobalVelocityAndYaw 的调用被注释。
点云过滤器当前在 body（IMU）坐标系内裁剪，尚未以实际车体中心及朝向建立裁剪框。
导航串口已发布 big_yaw，单位为度，但文档未确定相对参考、零点和正方向；反馈 header 使用主机接收处理时刻，未包含硬件采样时间。
历史记录确认两台雷达刚性安装在同一云台，使用主雷达内置 IMU。

后续用户确认：底盘与云台 yaw 轴重合，雷达不随 pitch 俯仰；给出从云台轴到雷达中心的 x=69.49、y=-232.15，尚待确认单位、坐标轴及是否为主雷达中心。big_yaw 是云台相对世界的角度，向左转增大，并非云台相对底盘角。
轴线重合且仅 yaw 运动时，可根据雷达自身位姿及固定安装偏移求共同轴线的水平位置，无需 big_yaw 或底盘航向。车体坐标轴若要求跟随底盘，仍需独立的底盘航向或云台相对底盘角，不能由云台世界角单独恢复。

### Risk notes

旧偏移是否适合当前实物尚待测量，不能仅凭源码断言它造成全部漂移。
固定偏移可正确补偿刚性安装，前提是几何和坐标轴准确；独立旋转的云台需要完整运动学关系。
不能将真实传感器绕轴运动强行归零，也不能以重命名 IMU body 代替几何转换。
位置、方向、速度、导航控制指令和裁剪框的坐标语义需要一致；避免重复补偿或直接改变现有 MPC 输出语义。
map→camera_init 的全局定位修正与局部参考点绕转应分开观察。正确几何不能消除估计误差。

### Recommended modification boundary

保留 Point-LIO 的 IMU 状态定义。先确定安装尺寸的单位和坐标轴；共同 yaw 轴的水平中心位置可直接根据雷达姿态与安装偏移计算，需衔接现有 IMU↔雷达外参。
若还要求坐标轴跟随底盘，待底盘航向来源或相对关节角确定后再计算完整车体位姿；不能因位置不需要关节角而推断底盘朝向也已知。
若 T_W_I 为 IMU 世界位姿，T_C_I(q) 为当前关节角下 IMU 在车体中心坐标系中的位姿，则 T_W_C = T_W_I · inverse(T_C_I(q))。
后续需要明确唯一 base_link 发布者，并核对对应中心速度及上下游接口；不能额外发布第二份同名 TF。

## Modifier Changes

### Files changed

仅本记录。

### Key changes

记录当前实现与目标语义的差异，并向用户询问云台轴位置、主雷达偏移、是否存在俯仰运动及 big_yaw 的参考和正方向。

### Behavior preserved

所有运行行为和工作区已有修改保持不变。

### Behavior intentionally adjusted

无。

### Notes

本次相关链路涉及比赛代码，采用最小改动策略。当前没有足够标定数据实施几何修复。

## Auditor Review

### Checks performed

- [x] 关键路径检查
- [x] diff / 工作区状态检查，保留已有修改
- [x] grep 检查
- [x] launch / yaml 生效项检查
- [x] 静态数学检查：假设二维刚性偏移，在四个 yaw 角度下用逆偏移恢复固定旋转中心，误差小于 1e-12
- [ ] 如需构建，已取得用户明确许可（本次不构建）

### Issues found

base_link 固定方向不符合用户期望的随车体旋转语义；几何偏移未经本车尺寸确认，且没有使用云台相对角进行底盘位姿换算。
用户已补充共同轴线、无俯仰及二维尺寸，但单位、尺寸坐标轴和中心坐标轴的目标方向仍待确认。离线数学示例不代表实车已验收。
未执行构建：AGENTS.md 禁止在未获用户明确许可前运行构建命令。

### Final result

NEEDS_FIX：源码核对完成，车体中心坐标系尚未修复或实车验证。
