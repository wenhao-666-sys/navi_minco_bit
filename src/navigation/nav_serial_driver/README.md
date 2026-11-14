# 主机导航串口

无需 Docker、QD 工作区或 rm_interfaces。导航使用独立 `/dev/rm_nav0`，视觉使用另一条串口线。
导航协议下发 16 字节、回传 20 字节，仅保留速度及 big_yaw，不兼容原 34/43 字节帧。
输入 `/cmd_vel_mpc` 的 `linear.x/linear.y/angular.z` 原值发送，不使用 big_yaw 旋转。

```bash
cd ~/2027-sentry-navi
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 launch nav_serial_driver serial.launch.py
```

临时更换设备：追加 `port_name:=/dev/ttyUSB1`。
导航主入口 `ros2 launch navi2 navigation2.launch.py` 已自动启动串口，勿再重复启动。
主入口可用 `start_serial:=false` 关闭串口，或 `serial_port:=...` 更换设备。
`use_sim_time:=true` 会禁止新串口启动。

Foxglove：`ros2 run nav_serial_driver foxglove_velocity.bash`，连接 `ws://127.0.0.1:8765`，
导入本包 `config/foxglove_velocity.json`。远程访问可使用 SSH 端口转发。
详见仓库 `docs/串口通信（导航）.md`。

主机构建及测试：

```bash
colcon build --packages-select nav_serial_driver navi2 --symlink-install --parallel-workers 2 --cmake-args -DBUILD_TESTING=ON
source install/setup.bash
colcon test --packages-select nav_serial_driver --return-code-on-test-failure
colcon test-result --test-result-base build/nav_serial_driver --verbose
ROS_DOMAIN_ID=88 ROS_LOCALHOST_ONLY=1 python3 src/navigation/nav_serial_driver/test/test_pty_integration.py
```

伪终端测试仅使用临时设备，不连接实车；需要本机 ROS 通信套接字权限。
帧定义、打包、CRC 和 UART 分离，后续扩展需同步上下位机、测试与协议文档。

## 录制指令和实际速度

电控实际速度发布到 `/cmd_vel_real`（geometry_msgs/msg/Twist）：
`linear.x = 实际 vx`、`linear.y = 实际 vy`、`angular.z = 实际 wz`。
这里 z 是绕 z 轴角速度，不是 z 方向平移速度。

在已经 source 工作区的另一个终端执行：

```bash
mkdir -p ~/2027-sentry-navi/bags
ros2 bag record -o ~/2027-sentry-navi/bags/nav_velocity_$(date +%Y%m%d_%H%M%S) \
  /cmd_vel_mpc /nav/serial/send /cmd_vel_real
```

Ctrl+C 结束录制。`/cmd_vel_mpc` 是 MPC 输入，`/nav/serial/send` 是完整写入串口成功的值
（包含超时归零），`/cmd_vel_real` 是电控回传的实际速度。
实际跟随对比应以串口发送值和实际速度为主，同时保留 MPC 输入便于定位差异。

Foxglove 直接打开录制目录中的 `.db3`，导入本包 `config/foxglove_velocity.json`，
即可在 X/Y/角速度面板比较三条曲线。统一用接收时间轴，观察幅值、方向和响应延迟；
串口协议没有电控采样时间戳，不能据此精确计算电控内部控制延迟。
本命令未录制 big_yaw，因此第四个角度面板无数据；需要时在命令末尾加 `/nav/serial/receive`。
回看用 Foxglove 直接打开 bag；若向运行中的机器人回放 `/cmd_vel_mpc`，会再次触发运动指令。
