# 导航专用退出运行库

本目录保存经过隔离回放验证的 rclcpp 16.0.18 补丁和本机生成的 `librclcpp.so`。
用户于 2026-10-24 明确允许接入正式导航入口。系统 `/opt/ros` 不替换。

`navi2` 构建时将本目录安装到 `install/navi2/lib/navi2/runtime`。它不提供 rclcpp
的 ament 索引，也不通过环境 hook 导出；正常 source 工作区仍使用系统 rclcpp。
只有 `navigation2.launch.py` 启动的 Point-LIO/规划器容器通过进程环境优先加载它。
导航进程同时预加载系统 STVL，以使其代码在回调引用释放之前保持加载。
单独启动 Point-LIO 或建图入口不自动加载本库。

修复包括等待期间持有回调组，以及移除节点时清理已过期的回调组条目。
还需要 `rog_map_ros2.hpp` 中的地图回调析构保护；这三个部分共同构成候选组合。
完整静止 bag 回放不能替代实车动态导航验收。

`manifest.json` 记录官方归档、补丁和本机库的 SHA256。`LICENSE.rclcpp` 是上游许可。
二进制不纳入 Git；新机器或本地库丢失时，需要先重建专用库，再构建 navi2：

```bash
# 以下会编译，Agent 执行前必须取得用户明确授权。
bash src/navigation/navi2_bringup/runtime/rebuild.bash
source /opt/ros/humble/setup.bash
source install/setup.bash
colcon build --packages-select navi2 --symlink-install
```

重建脚本仅在新建的 `/tmp/nav-rclcpp.*` 目录下载、打补丁和编译，最后复制产物回本目录。
不安装系统包、不修改 `/opt/ros`，也不自动运行构建后的导航。
请勿全局 source 临时 rclcpp overlay 或向用户 shell 导出本库路径。
ROS 升级后应重新核验；当前入口明确要求 rclcpp 16.0.18，不静默回退到未验证版本。

若使用 `start_sensors:=false`，已有容器不会被替换；必须事先按同一专用环境启动，
且应保证 global_costmap 进程参数一致。常规使用建议由导航入口新建容器。
