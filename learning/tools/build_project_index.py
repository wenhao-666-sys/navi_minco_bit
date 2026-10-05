#!/usr/bin/env python3
"""Build/check a Chinese learning index using only Python 3.9 stdlib and read-only Git.

The output is intended for <repo>/learning/PROJECT_INDEX.md. It can be generated
in staging; links always refer to the eventual location under learning/.
"""

import argparse
from collections import Counter
import hashlib
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from urllib.parse import quote, unquote
import xml.etree.ElementTree as ET


EXCLUDED = ("learning/", "docs/ai_refactor_records/")
REVIEWED_COMMIT = "6dba3a53bf20848ac92dc1fb0fdfdaf9e8376a44"

# Package roles and learning entrypoints, not a claim that every file is active.
PACKAGE_INFO = {
    "bt_manager": ("比赛策略、共享 blackboard、目标与姿态协调", "launch/bt_manager.launch.py", "start.bash 启动；内部 XML 的分支还需按注册与 tick 路径核对"),
    "communication": ("ROS 指令与串口协议、底盘及裁判状态接口", "launch/com.launch.py", "start.bash 启动；实际串口与下位机协议待实机核对"),
    "minco_controller": ("Nav2 控制器插件、MPC 参考与 QP 求解", "src/minco_mpc_controller.cpp", "sentry1.yaml 的 FollowPath 选择 MincoMpcController"),
    "minco_planner": ("Nav2 规划插件、搜索、MINCO、FSM 与恢复", "src/minco_core/minco_planner.cpp", "sentry1.yaml 选择 MincoPlanner；内部创建 ROGMap 并运行 FSM"),
    "navi2": ("Nav2 启动编排、生命周期、参数、地图与导航行为树", "launch/navigation2.launch.py", "start.bash 启动；默认 params/sentry1.yaml 与 2026/rmuc2026.yaml"),
    "point_lio": ("LiDAR–IMU 局部里程计、去畸变与稠密点云", "launch/mixed_livox_pointlio_intra_process.launch.py", "start.bash 使用双雷达组合入口；与驱动同容器"),
    "dbscan_cluster": ("点云聚类与卡尔曼目标跟踪", "launch/dbscan_cluster.launch.py", "有独立 launch；start.bash 未启动，接入关系待按引用核对"),
    "dual_lidar_calibration": ("离线双雷达时间配对、去畸变、外参估计与聚合", "src/main.cpp", "离线工具；不在 start.bash 默认在线链路中"),
    "icp_relocalization": ("局部点云与先验 PCD 的 GICP 重定位", "launch/gicp_relocalization.launch.py", "start.bash 在 Point-LIO 后启动；匹配与回退需区别"),
    "livox_ros_driver2": ("Livox 接收、点云/IMU 消息、驱动侧双雷达融合", "src/driver_node.cpp", "由 Point-LIO 组合 launch 装载；mixed 配置为默认双雷达输入"),
    "msg_convert": ("已配准点云的裁剪与过滤", "launch/cloud_registered_crop_filter.launch.py", "start.bash 中独立启动行被注释；ROGMap 另有内部过滤实现"),
    "rog_map": ("三维概率占据、投影、先验融合、ESDF 与查询接口", "include/rog_map_ros/rog_map_ros2.hpp", "以库在 MincoPlanner 内创建；不能假设存在独立地图节点"),
    "ros_interfaces": ("轨迹、比赛状态、行为与聚类结果的自定义消息", "CMakeLists.txt", "构建时生成接口；本包不是一个需要单独启动的节点"),
    "sentry_simulation": ("Gazebo 仿真、传感器适配、运动学与真值", "launch/simulation.launch.py", "simlation.bash 单独启动；默认 omni / rmuc_2025"),
    "pcd2ele": ("PCD 转高程栅格", "launch/pcd2ele.launch.py", "离线地图工具；start.bash 未启动"),
    "pcd2esdf": ("二维地图 YAML/图像转 ESDF 点云文件", "launch/pcd2esdf.launch.py", "离线地图工具；start.bash 未启动；当前输入不是 PCD"),
    "pcd2pgm": ("PCD 转二维 PGM/YAML 栅格地图", "launch/pcd2pgm.launch.py", "离线地图工具；start.bash 未启动"),
}

ROOT_ROLES = {
    "start.bash": ("实车启动脚本", "依次安排 PTP、双雷达+Point-LIO、GICP、Nav2、行为树、通信；固定 sleep 不代表节点已就绪", "已读有效命令；录包、Foxglove、独立裁剪与单雷达行被注释"),
    "play.bash": ("辅助启动脚本", "加载 install 环境并启动 Nav2", "已读全文件：没有 ros2 bag play，不是录包回放器"),
    "build.bash": ("构建脚本", "ROS Humble 环境、关键包串行及其余包并行 colcon 构建；内存监视", "只读；尚未执行构建"),
    "clean.bash": ("清理脚本", "删除当前目录的 build/install/log 构建产物", "已读；会删除目录，学习中不直接执行"),
    "simlation.bash": ("仿真入口", "检查 ROS overlay 后启动 sentry_simulation；默认 omni / rmuc_2025", "已读：--check 仅前置检查；文件名原本拼为 simlation"),
    "scripts/setup_env.bash": ("编辑器配置脚本", "设置 VS Code clang-format、快捷键与任务；不是 ROS 环境安装脚本", "已读：注释 Usage 使用旧脚本名"),
    "scripts/ptp_sync.bash": ("时间同步脚本", "配置 ptp4l/phc2sys、停止 NTP 服务并操作既有进程", "start.bash 调用；默认网卡 enp86s0，部署前核对"),
    "scripts/pcd.bash": ("独立建图入口", "分别启动双 Livox 驱动与 point_lio.launch.py", "已读：工作空间路径仍为 ~/2025-sentry-navi"),
    "scripts/savemap.bash": ("保存地图脚本", "调用 map_saver_cli 将占据栅格话题保存为地图 YAML/图像", "已读：支持单次或周期保存；不是 PCD 保存接口"),
    "scripts/autopush.sh": ("版本同步脚本", "自动 Git 操作脚本；具体远端和改动范围使用前检查", "辅助工具；本次未执行"),
    "scripts/monitor_livox_network.sh": ("网络诊断工具", "查看 Livox 网络链路与接收状态", "辅助工具；目标网卡与输出项按脚本核对"),
    "scripts/monitor_odom_rogmap.py": ("性能观察工具", "观察里程计与 ROGMap 相关运行数据", "辅助工具；实际订阅与额外负载需运行时记录"),
    "scripts/diag/ptp_sync_checker.py": ("时间诊断工具", "检查 PTP/传感器时间同步相关数据", "辅助工具；不能仅凭频率判定时间对齐"),
    "scripts/diag/watch_component_coredump.sh": ("崩溃诊断工具", "观察组件进程 core dump 以辅助故障定位", "诊断时使用；不在导航计算主链"),
    "AGENTS.md": ("协作规范", "本仓库 Agent 工作边界、静态检查与改造记录要求", "编辑前读取；用户当前任务与上级指令优先"),
    "README.md": ("项目文档", "跨模块架构、安装、硬件配置和参数索引", "阅读入口；与当前源码/launch 交叉核对"),
    "CONTRIBUTING.md": ("贡献文档", "项目贡献与工作流说明", "人工阅读；不等同于运行参数"),
    "NUC_DOWNLOAD.md": ("迁移文档", "另一台 NUC 下载本仓库的操作说明", "迁移入口；账号权限和本机环境另行核对"),
    "LICENSE": ("许可证", "项目使用、修改及分发的许可文本", "法律文本；不是运行代码"),
    ".gitmodules": ("Git 配置", "子模块配置文件；实际内容决定是否定义子模块", "不要由文件存在推断依赖已拉取"),
    ".gitignore": ("Git 配置", "未跟踪文件的忽略规则", "已被 Git 跟踪的文件仍出现在索引中"),
    ".gitattributes": ("Git 配置", "文本属性与行尾等 Git 规则", "仓库元数据"),
    ".clang-format": ("格式配置", "C/C++ 自动格式化规则", "开发工具使用"),
    ".clang-format-ignore": ("格式配置", "格式化排除规则", "开发工具使用"),
}

# Explicit study descriptions; entry state remains separate from source purpose.
KEY_ROLES = {
    "point_lio": {
        "src/laserMapping.cpp": "Point-LIO 组件、回调/同步、主处理、地图维护与输出的首要阅读入口",
        "src/IMU_Processing.cpp": "IMU 初始化/传播及运动补偿相关实现",
        "src/Estimator.cpp": "滤波估计与观测模型实现",
        "src/preprocess.cpp": "点云格式转换、筛选及时间信息预处理",
        "src/parameters.cpp": "参数声明和读取；排查 YAML 是否真正生效的入口",
        "src/li_initialization.cpp": "LiDAR–IMU 初始化相关实现",
        "src/runtime_statistics.cpp": "运行期性能统计实现",
        "include/time_batching.h": "按传感器时间组织 batch 的辅助逻辑",
        "include/sensor_time_rate_limiter.h": "基于传感器时间的发布限频辅助逻辑",
        "include/ivox/ivox3d.h": "iVox 地图维护与邻域查询接口/实现",
        "include/ivox/ivox3d_node.hpp": "iVox 单元内部点存储与查询结构",
        "config/mid360.yaml": "Point-LIO MID-360 输入、滤波、噪声、外参与输出参数",
        "launch/mixed_livox_pointlio_intra_process.launch.py": "双雷达组合入口；传 mixed 驱动参数并覆盖 IMU 为 livox/imu_192_168_1_135",
        "launch/single_livox_pointlio_intra_process.launch.py": "单雷达组合备选入口；不是 start.bash 当前有效启动行",
        "launch/livox_pointlio_intra_process.launch.py": "通用 Livox+Point-LIO 组件容器装配与参数覆盖",
        "launch/point_lio.launch.py": "独立 Point-LIO 启动入口；与组合入口区别阅读",
    },
    "livox_ros_driver2": {
        "src/driver_node.cpp": "ROS 驱动组件入口及参数/数据发布协调",
        "src/internal_lidar_merger.cpp": "驱动内前后雷达时间配对、外参变换及合并输出",
        "src/lddc.cpp": "LiDAR 数据分发与 ROS 消息发布路径",
        "src/lds_lidar.cpp": "SDK LiDAR 数据源与设备管理",
        "src/lds.cpp": "驱动数据源基础逻辑",
        "src/livox_ros_driver2.cpp": "驱动独立可执行程序入口；和组件入口对照",
        "config/mixed_MID360_config.json": "双雷达设备地址、主机接收 IP/端口配置",
        "config/mixed_MID360_component.yaml": "双雷达组件参数、前后雷达 IP 与 back→front 融合外参",
        "config/single_MID360_component.yaml": "单雷达组件参数；备选配置",
        "msg/CustomMsg.msg": "Livox 自定义一帧点云容器，非 PointCloud2",
        "msg/CustomPoint.msg": "Livox 单点字段与时间偏移格式",
    },
    "icp_relocalization": {
        "src/gicp_node.cpp": "GICP 重定位节点入口",
        "src/gicp_ros_interface.cpp": "订阅、配置、匹配触发与 TF/结果发布接口",
        "src/gicp_filter.cpp": "GICP 滤波/配准核心逻辑",
        "src/gicp_utils.cpp": "重定位辅助计算",
        "src/pcd_sanitize_tool.cpp": "独立 PCD 清洗辅助工具",
        "config/gicp_relocalization.yaml": "先验点云、初值、配准判据与回退配置",
    },
    "minco_planner": {
        "src/minco_core/minco_planner.cpp": "Nav2 插件生命周期、目标入口、内嵌 ROGMap 与规划协调",
        "src/minco_core/minco_fsm.cpp": "规划/跟踪/停止/恢复状态流与重规划调度",
        "src/minco_core/astar.cpp": "栅格 A* 路径搜索实现",
        "src/minco_core/components/global_path_searcher.cpp": "全局路径搜索组织与地图查询使用",
        "src/minco_core/components/local_path_processor.cpp": "全局路径的局部裁剪与处理",
        "src/minco_core/components/trajectory_safety_checker.cpp": "轨迹安全检查逻辑",
        "src/minco_core/components/recovery_behaivor.cpp": "规划恢复行为实现（文件名原拼写）",
        "src/minco_core/components/map_query_adapters.cpp": "规划地图查询适配",
        "src/minco_core/components/planner_mode_context.cpp": "不同规划模式的上下文处理",
        "src/traj_opt/minco_optimizer.cpp": "MINCO 轨迹优化、代价与约束实现",
        "src/traj_opt/yaw_traj_opt.cpp": "航向轨迹优化实现",
        "src/traj_opt/backup_traj_optimizer_s4.cpp": "保留的 backup 轨迹优化实现；存在不表示当前 FSM 启用",
        "src/utils/minco.cpp": "MINCO 多项式与导数相关底层计算",
        "src/smac_search/smac_planner_2d_simple.cpp": "SMAC 风格二维搜索实现",
        "global_planner_plugin.xml": "向 Nav2/pluginlib 导出 MincoPlanner 类型",
    },
    "minco_controller": {
        "src/minco_mpc_controller.cpp": "Nav2 控制器插件、轨迹参考、补偿与世界系速度输出",
        "src/mpc_solver.cpp": "MPC 优化问题构造及 qpOASES 求解",
        "include/minco_controller/mpc_types.hpp": "MPC 数据结构、状态与控制量定义",
        "minco_controller.xml": "向 Nav2/pluginlib 导出 MincoMpcController 类型",
    },
    "navi2": {
        "launch/navigation2.launch.py": "实车 Nav2 总入口；包含自定义 navigation_launch 与官方 localization_launch",
        "launch/navigation_launch.py": "导航节点/组件、重映射、生命周期和 planner 容器装配",
        "launch/slam.launch.py": "建图用备选 Nav2 入口；start.bash 中被注释",
        "params/sentry1.yaml": "当前默认实车参数；MPC、MINCO、ROGMap、costmap 均在此追踪",
        "params/nav2_params.yaml": "另存的 Nav2 配置；当前 navigation2 默认不选择它",
        "params/slam.yaml": "SLAM 工具参数；需经建图入口加载",
    },
    "bt_manager": {
        "src/main.cpp": "比赛策略进程入口与主调度",
        "src/bt_manager.cpp": "行为节点注册、加载树与各树 tick 调度",
        "src/ros_interface.cpp": "ROS 订阅/发布与 blackboard 数据交换",
        "src/param_manager.cpp": "行为树相关参数管理",
        "src/area_visualizer.cpp": "策略区域的可视化 Marker",
        "include/bt_manager/blackboard.hpp": "共享策略状态/blackboard 定义",
        "tree/nav_tree.xml": "导航任务行为树；构造器加载并作为主树",
        "tree/tactical_tree.xml": "战术模式树；构造器加载，具体分支按有效 XML 阅读",
        "tree/stance_tree.xml": "底盘姿态树；构造器加载",
        "tree/gimbal_tree.xml": "云台相关树；构造器加载",
        "tree/resource_tree.xml": "资源管理树；构造器加载",
        "tree/recovery_tree.xml": "保留的恢复树资源；当前构造器未创建此文件对应的树",
    },
    "communication": {
        "src/main.cpp": "通信可执行节点入口",
        "src/com.cpp": "通信组织、收发及协议处理",
        "src/com_interface_ros.cpp": "ROS 速度/行为/状态与通信数据的转换",
        "src/csv_recorder.cpp": "通信性能/数据 CSV 记录",
        "include/utils/custom_protocol.hpp": "项目自定义通信协议定义",
        "include/utils/protocol.hpp": "通信协议字段及结构定义",
        "include/utils/crc.hpp": "通信帧校验辅助逻辑",
    },
    "rog_map": {
        "include/rog_map_ros/rog_map_ros2.hpp": "ROGMap ROS 2 接口；由 MincoPlanner 构造而非单独 ros2 run",
        "include/rog_map/rog_map_core/config.hpp": "ROGMap 配置定义及 ROS 参数读取",
        "src/rog_map/rog_map.cpp": "ROGMap 主要地图处理流程",
        "src/rog_map/prob_map.cpp": "概率占据更新与状态维护",
        "src/rog_map/projection_layer.cpp": "二维地形投影与列状态处理",
        "src/rog_map/prior_map.cpp": "先验地图载入与融合",
        "src/rog_map/esdf_map.cpp": "ESDF 距离场更新与查询",
        "src/rog_map/sliding_map.cpp": "地图滑动窗口维护",
        "src/rog_map/map_query_interface.cpp": "面向规划等调用者的地图查询接口实现",
        "src/rog_map/query_adapter.cpp": "查询坐标/接口适配",
        "src/rog_map/field_layer.cpp": "二维场层计算与维护",
        "src/rog_map_ros/cloud_registered_crop_filter.cpp": "ROGMap 内部点云裁剪逻辑；区别于 msg_convert 独立节点",
        "src/rog_map_ros/rog_map_ros1.cpp": "历史命名的 ROS 桥接源；当前参与方式以 CMake 与条件宏核对",
    },
    "sentry_simulation": {
        "launch/simulation.launch.py": "仿真世界、机器人、桥接、Point-LIO/GICP/Nav2 启动装配",
        "src/pointcloud_adapter.cpp": "仿真点云转导航输入的组件实现",
        "sentry_simulation/cmd_vel_adapter.py": "控制速度到仿真底盘命令的适配",
        "sentry_simulation/kinematics.py": "仿真底盘运动学辅助计算",
        "sentry_simulation/imu_filter.py": "仿真 IMU 输入过滤处理",
        "config/worlds.yaml": "仿真世界资源配置；还需满足脚本与 launch 支持范围",
        "config/ros_gz_bridge.yaml": "ROS 与 Gazebo 话题桥接规则",
        "config/nav2_sim.yaml": "仿真导航参数",
        "config/point_lio_sim.yaml": "仿真里程计参数",
        "config/gicp_sim.yaml": "仿真重定位参数",
        "plugins/mecanum_drive2/MecanumDrive2.cc": "仿真麦克纳姆驱动插件实现",
    },
    "msg_convert": {"src/cloud_registered_crop_filter.cpp": "独立点云裁剪过滤节点实现"},
    "dbscan_cluster": {
        "src/dbscan_cluster_node.cpp": "聚类节点入口",
        "src/dbscan_cluster.cpp": "DBSCAN 点云聚类算法实现",
        "src/kalman_tracker.cpp": "聚类目标跟踪状态估计",
        "src/ros_interface.cpp": "聚类模块 ROS 数据交换",
    },
    "dual_lidar_calibration": {
        "src/main.cpp": "离线标定工具入口/参数组织",
        "src/offline_calibrator.cpp": "离线双雷达标定流程组织",
        "src/bag_reader.cpp": "读取标定 bag 的传感器数据",
        "src/frame_synchronizer.cpp": "前后雷达帧时间同步/配对",
        "src/deskewer.cpp": "标定用点云去畸变",
        "src/frame_calibrator.cpp": "单组配对帧外参计算",
        "src/extrinsic_aggregator.cpp": "多帧外参结果聚合",
        "src/imu_rotation_estimator.cpp": "基于 IMU 的旋转估计",
        "src/result_writer.cpp": "保存标定结果",
    },
    "ros_interfaces": {
        "msg/minco_traj/MpcPositionCommand.msg": "MPC 轨迹消息定义；字段与普通 Path 不同",
        "msg/minco_traj/PositionCommand.msg": "轨迹位置/导数/航向命令格式；发布订阅以源码追踪",
        "msg/Behavior.msg": "比赛行为命令字段；注意项目 topic 的原拼写",
    },
}


def git(repo, *args):
    return subprocess.check_output(
        ["git", "-c", "safe.directory=" + str(repo), "-C", str(repo), *args],
        stderr=subprocess.PIPE,
    )


def link(path, label=None):
    return "[{}](../{})".format(label or path, quote(path, safe="/._-"))


def cell(value):
    return str(value).replace("|", "&#124;").replace("\n", " ")


def tracked_inventory(repo):
    files = sorted(set(p for p in git(repo, "ls-files", "-z").decode("utf-8").split("\0")
                       if p and not p.startswith(EXCLUDED)))
    missing = [p for p in files if not (repo / p).is_file()]
    if missing:
        raise ValueError("Tracked files missing from worktree: " + ", ".join(missing[:10]))
    packages = {}
    for path in files:
        if PurePosixPath(path).name == "package.xml":
            name = ET.parse(repo / path).findtext("name")
            if not name or name in packages:
                raise ValueError("Missing/duplicate ROS package name in " + path)
            packages[name] = str(PurePosixPath(path).parent)
    return files, packages


def owner_of(path, packages):
    candidates = [(name, root) for name, root in packages.items() if path.startswith(root + "/")]
    return max(candidates, key=lambda item: len(item[1])) if candidates else ("工程/普通工具", "")


def category(path):
    p = PurePosixPath(path)
    name, suffix = p.name.lower(), p.suffix.lower()
    if "__pycache__" in p.parts or suffix == ".pyc":
        return "已跟踪缓存"
    if suffix == ".bak":
        return "备份文件"
    if any(part in p.parts for part in ("3rdparty", "third_party", "cereal", "fmt", "IKFoM")):
        if any(part in p.parts for part in ("examples", "testing", "tests", "interfaces", "doc")):
            return "第三方示例/接口/资料"
        return "第三方库"
    if name in ("license", "copying", "license.txt") or "third_party_notices" in name:
        return "许可证"
    if suffix in (".md", ".rst", ".pdf", ".dox"):
        return "文档"
    if name == "package.xml":
        return "ROS 包清单"
    if name == "cmakelists.txt" or suffix in (".cmake", ".mk") or name == "makefile":
        return "构建配置"
    if suffix == ".msg":
        return "消息接口"
    if any(part in p.parts for part in ("test", "tests")):
        return "测试"
    if ".launch." in name or "launch" in p.parts or "launch_ROS2" in p.parts:
        return "启动配置"
    if suffix == ".pcd":
        return "点云地图/资源"
    if suffix in (".pgm", ".png", ".jpg", ".jpeg"):
        return "地图图像/纹理"
    if suffix in (".stl", ".dae", ".sdf", ".config"):
        return "仿真模型/场景"
    if suffix == ".yaml" and "maps" in p.parts:
        return "栅格地图元数据"
    if suffix in (".yaml", ".yml", ".json", ".cfg", ".rviz", ".in"):
        return "参数/可视化/环境配置"
    if suffix == ".xml":
        return "行为树/插件配置"
    if suffix in (".h", ".hpp", ".hh", ".ipp"):
        return "头文件/模板"
    if suffix in (".cpp", ".cc", ".c"):
        return "C/C++ 实现"
    if suffix in (".py", ".bash", ".sh", ".html"):
        return "脚本/界面"
    if suffix in (".csv", ".dat", ".mat", ".mdl"):
        return "数据资源"
    return "其他配置/资源"


def describe(path, owner, root):
    if path in ROOT_ROLES:
        return ROOT_ROLES[path]
    rel = path[len(root) + 1:] if root else path
    kind = category(path)
    info = PACKAGE_INFO.get(owner)
    entry = link(root + "/" + info[1], "包阅读入口") if info else "普通工具；手动入口待核对"
    source_evidence = entry + "；本文件启用/调用待按 CMake、include 和引用追踪"
    if rel in KEY_ROLES.get(owner, {}):
        return kind, KEY_ROLES[owner][rel], source_evidence
    stem = PurePosixPath(path).stem
    if kind.startswith("第三方"):
        library = next((part for part in PurePosixPath(path).parts if part in
                        ("qpOASES", "rapidjson", "cereal", "fmt", "IKFoM")), "随包附带依赖")
        return kind, library + " 的库文件/附带材料（类别级说明，未逐行审计）", "以所属包 CMake/include 为准；附带示例不等于导航运行代码"
    if kind == "已跟踪缓存":
        return kind, "Python 编译缓存；优先阅读同名 .py 源码（类别级说明）", "因已被 Git 跟踪而列入；不作为源码阅读入口"
    if kind == "备份文件":
        return kind, "保留备份；不能由命名推断仍在使用", "待查当前 include/构建引用"
    if kind == "ROS 包清单":
        return kind, "声明实际 ROS 包名、版本、依赖与构建类型", "已由 XML 解析纳入本页包名映射"
    if kind == "构建配置":
        return kind, "定义构建目标、依赖、安装与导出（类别级说明）", "A02：静态阅读 add_library/add_executable/install 等"
    if kind == "消息接口":
        return kind, stem + " 消息字段契约；发布者/订阅者待按类型搜索", link(root + "/CMakeLists.txt", "接口生成配置")
    if kind == "测试":
        return kind, stem + " 测试/检查用例（类别级说明）", "按测试代码及 CMake/测试入口执行；不属于默认运行链"
    if kind in ("文档", "许可证"):
        return kind, stem + " 说明/许可材料；内容需与实现交叉核对", "阅读资料；不证明节点或参数已启用"
    if kind in ("点云地图/资源", "地图图像/纹理", "仿真模型/场景", "栅格地图元数据", "数据资源"):
        return kind, stem + " 资源（类别级说明）；场景/坐标/尺度需匹配配置", "是否加载以 launch/YAML/SDF 的实际路径引用为准"
    if kind == "启动配置":
        return kind, stem + " 节点/组件装配入口（类别级说明）", entry + "；与 start.bash 或仿真入口对照，未逐项确认启用"
    if kind == "参数/可视化/环境配置":
        return kind, stem + " 配置（类别级说明）；读取端与覆盖优先级待追踪", entry + "；文件存在不代表已加载"
    if kind == "行为树/插件配置":
        return kind, stem + " XML 定义（类别级说明）", "按 launch、插件导出、树注册及有效 XML 分支核对"
    if kind in ("C/C++ 实现", "头文件/模板"):
        scope_roles = {
            "/action/": "行为树动作实现/声明", "/condition/": "行为树条件实现/声明",
            "/smac_search/": "路径搜索辅助结构/实现", "/traj_opt/": "轨迹优化辅助结构/实现",
            "/performance/": "性能统计辅助结构/实现", "/ivox/": "iVox 空间索引辅助结构/实现",
            "/MyUtils/": "通信包的网络/线程/计时辅助库", "/parse_cfg_file/": "Livox 配置解析",
            "/call_back/": "Livox SDK 回调接口", "/comm/": "驱动队列/数据交换辅助逻辑",
            "/utils/": "模块数学/数据结构/通用辅助逻辑", "/super_utils/": "格式/颜色/计时等公共辅助逻辑",
        }
        purpose = next((role for pattern, role in scope_roles.items() if pattern in path),
                       (info[0] if info else "工具模块") + "相关实现/声明")
        return kind, stem + "：" + purpose + "（类别级说明）", source_evidence
    if "src/utils/pcd_trans/" in path:
        return kind, stem + "：点云编辑/转换/本地界面工具（类别级说明）", "普通工具目录，无 package.xml；先读该目录 README"
    if "src/utils/bt_editor/" in path:
        return kind, "浏览器行为树编辑界面", "普通 HTML 工具；不在 ROS 默认启动链"
    if "src/utils/data_analyzer/" in path:
        return kind, "导航性能数据离线分析脚本", "普通工具；输入列与采样时基先核对"
    if "src/utils/rotmat_cal/" in path:
        return kind, "旋转矩阵计算辅助脚本", "普通工具；旋转约定需与外参定义核对"
    return kind, stem + "：按目录归属分类，具体行为待源码核对", source_evidence


def render(repo, files, packages):
    commit = git(repo, "rev-parse", "HEAD").decode("ascii").strip()
    digest = hashlib.sha256("\0".join(files).encode("utf-8")).hexdigest()
    rows = []
    counts = Counter()
    for path in files:
        owner, root = owner_of(path, packages)
        kind, role, evidence = describe(path, owner, root)
        counts[kind] += 1
        rows.append((path, owner, kind, role, evidence))
    out = [
        "# navi_minco_bit 全文件与模块索引", "",
        "本页用于 A01 定位文件，并贯穿 A02–O04。由 `tools/build_project_index.py` 生成；不要直接改生成表，需更新工具中的分类或阅读映射。", "",
        "## 基线与核查边界", "",
        "- 当前 Git HEAD：`" + commit + "`。",
        "- 清单来源：`git -c safe.directory=<repo> ls-files -z`，共 **{} 个文件、{} 个 ROS 包**。".format(len(files), len(packages)),
        "- 排除教学目录 `learning/` 与事后记录 `docs/ai_refactor_records/`，避免索引自引用；其余已跟踪文件全部列入，包括缓存、备份、资源和第三方文件。",
        "- 文件清单 SHA-256：`" + digest + "`（路径清单校验，不是源码内容校验）。",
        "- 包名从每个 `package.xml` 解析，所属包按最近上级包目录确定；目录名不等于 ROS 包名。",
        "- 关键入口/配置经过静态阅读；其余用途为明确标注的类别级说明。覆盖所有文件不代表逐行审计，也不代表已在 NUC 构建、运行或验收。",
        "- 人工语义核对基线：`" + REVIEWED_COMMIT + "`。更新源码后需重核启用关系；`--check` 检查清单、链接及生成结果一致性，不能自动证明算法说明仍正确。", "",
        "## 六组源码与 ROS 包", "",
        "| 源码组 | 职责 |", "|---|---|",
        "| decision | 比赛行为树、状态与策略 |",
        "| navigation | Nav2 编排、规划、控制、底盘通信 |",
        "| perception | 雷达驱动、标定、里程计、重定位、地图和感知工具 |",
        "| ros_interfaces | 跨模块自定义消息 |",
        "| simulation | 仿真链路、模型、传感器与真值 |",
        "| utils | 地图转换、点云编辑、数据分析；其中仅部分目录是 ROS 包 |", "",
        "| ROS 包名 | 实际目录 | 职责 | 学习入口与启用证据 |", "|---|---|---|---|",
    ]
    if commit != REVIEWED_COMMIT:
        out.insert(12, "- **源码版本已不同于人工核对基线，启用关系与文档差异需要复核。**")
    for name, root in sorted(packages.items(), key=lambda item: item[1]):
        info = PACKAGE_INFO.get(name, ("新增包：职责待核对", "package.xml", "启用关系待核对"))
        out.append("| {} | {} | {} | {}；{} |".format(name, link(root), info[0], link(root + "/" + info[1], info[1]), info[2]))
    out.extend([
        "", "`pcd_trans`、`bt_editor`、`data_analyzer`、`rotmat_cal` 是普通工具目录；不能直接用目录名推断 `ros2 launch` 包名。", "",
        "## 当前启动链与参数追踪", "",
        "1. " + link("start.bash") + " 加载工作空间并安排 PTP → 双雷达+Point-LIO → GICP → Nav2 → 比赛行为树 → communication。它使用固定等待时间；仍需检查节点、生命周期和有效输出。",
        "2. " + link("src/perception/Point-LIO/launch/mixed_livox_pointlio_intra_process.launch.py") + " 包含通用组合 launch，选择 mixed_MID360_component.yaml、mid360.yaml，且显式覆盖主 IMU 话题。IP 配置不能只改一个 JSON。",
        "3. " + link("src/navigation/navi2_bringup/launch/navigation2.launch.py") + " 默认选 params/sentry1.yaml；该 YAML 的 MINCO/MPC 插件及内嵌 ROGMap 参数才是当前实车调参起点。",
        "4. " + link("src/navigation/minco_planner/src/minco_core/minco_planner.cpp") + " 内创建 ROGMapROS，并通过内部 FSM 推进规划；createPlan() 只看一部分流程。",
        "5. " + link("src/decision/bt_manager/src/bt_manager.cpp") + " 加载资源、战术、姿态、云台与导航树；比赛树和 Nav2 导航执行树是不同层。某 XML 文件存在不意味着它被实例化。", "",
        "```text",
        "双 MID-360 → Livox 驱动/融合 → Point-LIO → 局部 odom 与配准点云",
        "                                  ├→ GICP + 先验 PCD → 地图对齐",
        "                                  └→ 规划器内 ROGMap → 查询/投影/ESDF",
        "比赛策略 / 用户目标 → Nav2 → 搜索 + MINCO/FSM → /opt_path → MPC",
        "                                                 MPC → /cmd_vel_mpc → 通信 → 底盘",
        "```", "",
        "以上是职责图；精确话题、frame、时间戳、QoS 和并行关系在后续课程按发布/订阅源码核对。", "",
        "## 已确认的文档与命名差异", "",
        "| 线索 | 当前可核对的事实 | 学习时如何处理 |", "|---|---|---|",
        "| play.bash 文件名 | 只加载环境并启动 Nav2，没有 bag play | 算法回放另行准备输入话题、时钟和启动链 |",
        "| 工作空间名称 | start.bash 为 ~/2027-sentry-navi，scripts/pcd.bash 为 ~/2025-sentry-navi | 部署前按 NUC 实际路径核对，不直接运行整车脚本 |",
        "| scripts/setup_env.bash | 实际配置 VS Code clang-format，注释 Usage 使用另一个脚本名 | 不作为 ROS 依赖安装器 |",
        "| simlation.bash | 原文件名如此；默认 omni / rmuc_2025，参数校验只接受四个 2024/2025 世界 | 存在 2026 模型不等于该入口支持 2026 |",
        "| 录包和 Foxglove | start.bash 中对应启动行被注释 | 需要在相应课程单独配置与验证 |",
        "| ROGMap | 在 MINCO 插件内创建并共享查询接口 | ros2 node list 不一定出现独立 rog_map 节点 |",
        "| 双雷达 IP 与 IMU | 组合 launch 显式指定 livox/imu_192_168_1_135 | 联查 JSON、组件 YAML、launch 覆盖和实际发布话题 |",
        "| 完整云裁剪 | start 中 msg_convert 被注释；ROGMap 有内部裁剪实现 | 区分独立节点和内嵌处理 |",
        "| 缓存及备份 | Git 清单包含 .pyc 与 .bak | 保留索引，优先阅读对应源码，不自动清理 |", "",
        "## 文件类别统计", "",
        "| 类别 | 文件数 |", "|---|---:|",
    ])
    out.extend("| {} | {} |".format(kind, count) for kind, count in sorted(counts.items()))
    out.extend([
        "", "## 逐文件索引", "",
        "表中每个路径只出现一条索引记录，可在浏览器/编辑器中搜索文件名。`包阅读入口` 是追踪起点，不等于该文件已被调用；“待核对”会随源码课程逐步缩小。", "",
        "<!-- FILE_INDEX_BEGIN -->",
        "| 文件 | 所属包 | 类别 | 用途 | 入口/启用证据或核对边界 |", "|---|---|---|---|---|",
    ])
    out.extend("| {} | {} | {} | {} | {} |".format(link(path), cell(owner), cell(kind), cell(role), cell(evidence))
               for path, owner, kind, role, evidence in rows)
    out.extend([
        "<!-- FILE_INDEX_END -->", "", "## 更新与检查", "",
        "在仓库根目录执行（只读取 Git；生成命令仅写指定 Markdown）：", "", "```bash",
        "python3 learning/tools/build_project_index.py --repo . --output learning/PROJECT_INDEX.md",
        "python3 learning/tools/build_project_index.py --repo . --output learning/PROJECT_INDEX.md --check",
        "```", "",
        "`--check` 不改文件；缺失/重复记录、无效源路径或生成结果过期均返回非零。可将 --output 指向临时目录，最终放到 learning/ 后相对链接仍正确。新增源码未纳入 Git 跟踪前不在清单中。", "",
    ])
    return "\n".join(out)


def validate_index(document, repo, files):
    try:
        section = document.split("<!-- FILE_INDEX_BEGIN -->", 1)[1].split("<!-- FILE_INDEX_END -->", 1)[0]
    except IndexError:
        raise ValueError("Missing file-index section markers")
    listed = [unquote(p) for p in re.findall(r"^\| \[[^\n]*?\]\(\.\./([^\n]*?)\) \|", section, re.MULTILINE)]
    counts = Counter(listed)
    missing, extra = sorted(set(files) - set(listed)), sorted(set(listed) - set(files))
    duplicates = sorted(p for p, count in counts.items() if count != 1)
    if missing or extra or duplicates:
        raise ValueError("Coverage mismatch: missing={!r}, extra={!r}, duplicates={!r}".format(missing[:5], extra[:5], duplicates[:5]))
    for encoded in re.findall(r"\]\(\.\./([^\n]*?)\)", document):
        path = unquote(encoded)
        if not (repo / path).exists():
            raise ValueError("Broken source link: " + path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path, help="Source Git working tree (read only)")
    parser.add_argument("--output", required=True, type=Path, help="Generated PROJECT_INDEX.md destination")
    parser.add_argument("--check", action="store_true", help="Check existing output; never write")
    args = parser.parse_args()
    try:
        repo = args.repo.resolve(strict=True)
        files, packages = tracked_inventory(repo)
        expected = render(repo, files, packages)
        validate_index(expected, repo, files)
        if args.check:
            existing = args.output.read_text(encoding="utf-8")
            validate_index(existing, repo, files)
            if existing != expected:
                raise ValueError("Index is stale or manually changed; regenerate with the same command without --check")
            print("PASS: {} tracked files, {} ROS packages; complete unique coverage and valid source links".format(len(files), len(packages)))
        else:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("w", encoding="utf-8", newline="\n") as stream:
                stream.write(expected)
            print("WROTE: {} ({} files, {} packages)".format(args.output, len(files), len(packages)))
    except (OSError, ValueError, ET.ParseError, subprocess.CalledProcessError) as error:
        detail = error.stderr.decode("utf-8", errors="replace").strip() if isinstance(error, subprocess.CalledProcessError) else str(error)
        print("FAIL: " + detail, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
