import math
import hashlib
import json
import os
import subprocess
import sysconfig
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import yaml
import launch
import launch_ros
from ament_index_python.packages import PackageNotFoundError, get_package_prefix, get_package_share_directory
from launch.launch_description_sources import PythonLaunchDescriptionSource
from nav2_common.launch import RewrittenYaml


def navigation_runtime_environment():
    # Private executor library: never export this directory as a workspace overlay.
    runtime_dir = Path(get_package_prefix('navi2')) / 'lib' / 'navi2' / 'runtime'
    stvl = Path(get_package_prefix('spatio_temporal_voxel_layer')) / 'lib' / 'libspatio_temporal_voxel_layer_core.so'
    for library in (runtime_dir / 'librclcpp.so', stvl):
        if not library.is_file():
            raise RuntimeError(f'Navigation shutdown runtime is missing: {library}. See {runtime_dir / "README.md"}.')
    version = ET.parse(Path(get_package_share_directory('rclcpp')) / 'package.xml').findtext('version')
    if version != '16.0.18':
        raise RuntimeError(f'Private navigation runtime requires rclcpp 16.0.18; found {version}. Revalidate before upgrading.')
    return {
        'LD_LIBRARY_PATH': os.pathsep.join(filter(None, (
            os.path.join('/usr/lib', sysconfig.get_config_var('MULTIARCH')),
            str(runtime_dir), os.environ.get('LD_LIBRARY_PATH', ''),
            os.path.expanduser('~/.local/livox-sdk2/lib'),
        ))),
        'LD_PRELOAD': ' '.join(filter(None, (str(stvl), os.environ.get('LD_PRELOAD', '')))),
    }


def launch_navigation_scan(context):
    # 与建图使用同一安装测量、雷达—IMU外参和地面截取范围。
    try:
        get_package_share_directory('pointcloud_to_laserscan')
    except PackageNotFoundError as error:
        raise RuntimeError(
            'Load the scan converter first: source /home/robomaster/fwh/install/'
            'pointcloud_to_laserscan/share/pointcloud_to_laserscan/local_setup.bash') from error
    settings = yaml.safe_load(Path(launch.substitutions.LaunchConfiguration(
        'projection_config').perform(context)).read_text())
    pointlio_file = Path(get_package_share_directory('point_lio')) / 'config' / 'mid360.yaml'
    pointlio = yaml.safe_load(pointlio_file.read_text())['/**']['ros__parameters']
    height, roll = float(settings['lidar_height']), float(settings['lidar_roll_rad'])
    low, high = float(settings['obstacle_min_height']), float(settings['obstacle_max_height'])
    if not all(math.isfinite(value) for value in (height, roll, low, high)) or not (
            height > 0 and 0 <= low < high):
        raise ValueError('Require finite mounting values, height > 0 and 0 <= min_height < max_height.')
    if pointlio['mapping']['extrinsic_est_en'] or not pointlio['publish']['tf_send_en']:
        raise ValueError('Ground projection requires fixed lidar/IMU extrinsics and Point-LIO TF.')
    r_i_l = np.asarray(pointlio['mapping']['extrinsic_R'], dtype=float).reshape(3, 3)
    t_i_l = np.asarray(pointlio['mapping']['extrinsic_T'], dtype=float)
    if t_i_l.shape != (3,) or not np.all(np.isfinite(t_i_l)) or not np.all(np.isfinite(r_i_l)):
        raise ValueError('Invalid fixed lidar/IMU extrinsics.')
    if not np.allclose(r_i_l.T @ r_i_l, np.eye(3), atol=1e-5) or not math.isclose(
            np.linalg.det(r_i_l), 1.0, abs_tol=1e-5):
        raise ValueError('extrinsic_R must be a proper rotation matrix.')
    r_w_l = np.array([[1, 0, 0], [0, math.cos(roll), -math.sin(roll)],
                      [0, math.sin(roll), math.cos(roll)]])
    imu_height = height - float((r_w_l @ r_i_l.T @ t_i_l)[2])
    if imu_height <= 0:
        raise ValueError('Computed IMU height must be positive; check mounting configuration.')
    use_sim_time = launch.substitutions.LaunchConfiguration('use_sim_time')
    library_env = {'LD_LIBRARY_PATH': os.pathsep.join(filter(None, (
        os.path.join('/usr/lib', sysconfig.get_config_var('MULTIARCH')),
        os.environ.get('LD_LIBRARY_PATH', ''),
    )))}
    return [
        launch_ros.actions.Node(
            package='tf2_ros', executable='static_transform_publisher',
            name='navigation_ground_transform', arguments=[
                '--x', '0', '--y', '0', '--z', str(-imu_height),
                '--roll', '0', '--pitch', '0', '--yaw', '0',
                '--frame-id', 'slambase', '--child-frame-id', 'mapping_ground'],
            parameters=[{'use_sim_time': use_sim_time}]),
        launch_ros.actions.Node(
            package='pointcloud_to_laserscan', executable='pointcloud_to_laserscan_node',
            name='pointcloud_to_laserscan', output='screen', additional_env=library_env,
            parameters=[{
                'target_frame': 'mapping_ground', 'transform_tolerance': 0.05,
                'queue_size': 5, 'min_height': low, 'max_height': high,
                'angle_min': -math.pi, 'angle_max': math.pi, 'angle_increment': 0.0087,
                'scan_time': 0.05, 'range_min': 0.4, 'range_max': 10.0,
                'use_inf': True, 'inf_epsilon': 1.0, 'use_sim_time': use_sim_time,
            }], remappings=[('cloud_in', '/cloud_registered_filtered'), ('scan', '/scan')]),
    ]


def start_navigation_hardware(context):
    start_ptp = launch.conditions.IfCondition(
        launch.substitutions.LaunchConfiguration('start_ptp')).evaluate(context)
    start_sensors = launch.conditions.IfCondition(
        launch.substitutions.LaunchConfiguration('start_sensors')).evaluate(context)
    sensor_actions = []
    if start_sensors:
        running = subprocess.run(
            ['pgrep', '-f', '[c]omponent_container_mt.*__node:=livox_pointlio_container'],
            stdout=subprocess.DEVNULL, check=False)
        if running.returncode == 0:
            raise RuntimeError('Point-LIO container already runs. Stop it or pass start_sensors:=false.')
        sensor_launch = os.path.join(get_package_share_directory('point_lio'),
                                     'launch', 'mixed_livox_pointlio_intra_process.launch.py')
        if not os.path.isfile(sensor_launch):
            raise RuntimeError(f'Point-LIO launch not found: {sensor_launch}')
        runtime_env = navigation_runtime_environment()
        sensor_actions.append(launch.actions.IncludeLaunchDescription(
            PythonLaunchDescriptionSource(sensor_launch),
            launch_arguments={
                'container_library_path': runtime_env['LD_LIBRARY_PATH'],
                'container_preload': runtime_env['LD_PRELOAD'],
            }.items()))

    if not start_ptp:
        return sensor_actions
    for process in ('ptp4l', 'phc2sys'):
        running = subprocess.run(['pgrep', '-x', process],
                                 stdout=subprocess.DEVNULL, check=False)
        if running.returncode == 0:
            raise RuntimeError('PTP already runs. Stop it or pass start_ptp:=false to reuse it.')
    script = launch.substitutions.LaunchConfiguration('ptp_script').perform(context)
    interface = launch.substitutions.LaunchConfiguration('ptp_interface').perform(context)
    if not os.path.isfile(script):
        raise RuntimeError(f'PTP script not found: {script}')
    # 密码在用户终端由 sudo -v 输入；禁止让 launch 子进程等待不可见的密码提示。
    authenticated = subprocess.run(['sudo', '-n', '-v'],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                    check=False)
    if authenticated.returncode != 0:
        raise RuntimeError('PTP needs sudo credentials. Run sudo -v in this terminal, then launch again.')
    ptp = launch.actions.ExecuteProcess(
        cmd=['sudo', '-n', 'bash', script, interface], output='screen',
        sigterm_timeout='5', sigkill_timeout='5')
    actions = [
        launch.actions.RegisterEventHandler(launch.event_handlers.OnProcessExit(
            target_action=ptp,
            on_exit=[launch.actions.EmitEvent(event=launch.events.Shutdown(
                reason='PTP process exited; stopping navigation.'))])),
    ]
    if sensor_actions:
        actions.append(launch.actions.RegisterEventHandler(launch.event_handlers.OnProcessStart(
            target_action=ptp, on_start=sensor_actions)))
    return actions + [ptp]


def launch_localization(context):
    backend = launch.substitutions.LaunchConfiguration('localization').perform(context)
    use_sim_time = launch.substitutions.LaunchConfiguration('use_sim_time')
    map_path = launch.substitutions.LaunchConfiguration('map')
    params = launch.substitutions.LaunchConfiguration('params_file')
    if backend == 'amcl':
        return [launch.actions.IncludeLaunchDescription(
            PythonLaunchDescriptionSource(os.path.join(
                get_package_share_directory('nav2_bringup'), 'launch', 'localization_launch.py')),
            launch_arguments={'map': map_path, 'use_sim_time': use_sim_time,
                              'params_file': params, 'log_level': 'error'}.items())]
    if backend != 'gicp':
        raise ValueError('localization must be amcl or gicp')

    # Only use a verified pair exported together, never silently mix a legacy
    # SLAM-toolbox grid with a Point-LIO PCD in a different trajectory frame.
    map_file = Path(map_path.perform(context)).expanduser().resolve()
    bundle_file = map_file.parent / 'map_bundle.json'
    if not bundle_file.is_file():
        raise RuntimeError('GICP requires a matching PCD/grid bundle. Remap with map_backend:=pcd; '
                           f'missing {bundle_file}')
    bundle = json.loads(bundle_file.read_text())
    if bundle.get('format') != 'pointlio_pcd_projection_v1' or map_file.name != 'map.yaml':
        raise ValueError('Unsupported PCD/grid bundle or renamed map.yaml')
    for name in ('map.pcd', 'map.pgm', 'map.yaml'):
        path = map_file.parent / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != bundle['sha256'].get(name):
            raise ValueError(f'Incomplete or modified map bundle: {path}. Export the matching set again.')
    # Dependency/binary checks run before starting real hardware.
    prefix = Path(get_package_prefix('icp_relocalization'))
    if not (prefix / 'lib' / 'icp_relocalization' / 'gicp_node').is_file():
        raise RuntimeError('icp_relocalization/gicp_node is not installed; build it first.')
    config = Path(get_package_share_directory('navi2')) / 'params' / 'gicp_navigation.yaml'
    # PCL IO loads libusb; camera SDK copies in the inherited search path
    # lack libusb_set_option. Scope the system-library preference to GICP.
    library_env = {'LD_LIBRARY_PATH': os.pathsep.join(filter(None, (
        os.path.join('/usr/lib', sysconfig.get_config_var('MULTIARCH')),
        os.environ.get('LD_LIBRARY_PATH', ''),
    )))}
    return [
        launch.actions.LogInfo(msg='PCD localization: AMCL disabled. In RViz use 2D Pose Estimate, '
                                   'then wait for "Localization confirmed" before setting a goal.'),
        launch_ros.actions.Node(package='nav2_map_server', executable='map_server', name='map_server',
            parameters=[params, {'yaml_filename': str(map_file), 'use_sim_time': use_sim_time}], output='screen'),
        launch_ros.actions.Node(package='nav2_lifecycle_manager', executable='lifecycle_manager',
            name='lifecycle_manager_localization', parameters=[{
                'use_sim_time': use_sim_time, 'autostart': True, 'node_names': ['map_server']}]),
        launch_ros.actions.Node(package='icp_relocalization', executable='gicp_node',
            name='gicp_relocalization_node', output='screen', additional_env=library_env,
            parameters=[str(config), {
                'target_pcd_file': str(map_file.parent / 'map.pcd'), 'use_sim_time': use_sim_time}]),
    ]


def generate_launch_description():
    # 获取与拼接默认路径
    DreamChaser_dir = get_package_share_directory(
        'navi2')
    runtime_env = navigation_runtime_environment()
    rviz_config_dir = os.path.join(
        DreamChaser_dir,'config', 'our.rviz')
    
    # 创建 Launch 配置
    use_sim_time = launch.substitutions.LaunchConfiguration(
        'use_sim_time', default='False')
    
    map_yaml_path = launch.substitutions.LaunchConfiguration(
        'map', default=os.path.join(DreamChaser_dir, 'maps', '2026/rmuc2026.yaml'))
        # 'map', default=os.path.join(DreamChaser_dir, 'maps', '2026/rmul2026.yaml'))
        # 'map', default=os.path.join(DreamChaser_dir, 'maps', 'first_floor/first_floor.yaml'))
    nav2_param_path = launch.substitutions.LaunchConfiguration(
        'params_file', default=os.path.join(DreamChaser_dir, 'params', 'sentry1.yaml'))
    # 当前导航入口使用同一张地图；避免 ROGMap 继续叠加历史比赛场地先验。
    navigation_params = RewrittenYaml(
        source_file=nav2_param_path,
        param_rewrites={
            'use_sim_time': use_sim_time,
            'planner_server.ros__parameters.MincoPlanner.rog_map.projection.prior_map.yaml_path': map_yaml_path,
            'planner_server.ros__parameters.MincoPlanner.rog_map.projection.prior_map.pgm_path': '',
            'local_costmap.local_costmap.ros__parameters.stvl_layer.mid360.topic': '/cloud_registered_filtered',
            'global_costmap.global_costmap.ros__parameters.stvl_layer.mid360.topic': '/cloud_registered_filtered',
            # ROGMap and both STVL layers consume the same self-filtered cloud;
            # GICP intentionally keeps the original world cloud for registration.
            'planner_server.ros__parameters.MincoPlanner.rog_map.ros_callback.cloud_topic': '/cloud_registered_filtered',
        }, convert_types=True)

    return launch.LaunchDescription([
        # 静态TF: map -> camera_init
        # launch_ros.actions.Node(
        #     package='tf2_ros',
        #     executable='static_transform_publisher',
        #     name='static_tf_map_to_camera_init',
        #     # arguments=['1.73', '6.4', '0', '0.0', '0', '0.0', 'map', 'camera_init'],
        #     # arguments=['5', '7', '0', '0', '0', '0', 'map', 'camera_init'],
        #     # arguments=['1', '3', '0', '0', '0', '0', 'map', 'camera_init'],
        #     # arguments=['6.7', '4.0', '0', '0', '0', '0', 'map', 'camera_init'],
        #     # arguments=['9.0', '13.0', '0', '0', '0', '0', 'map', 'camera_init'],
        #     # 2026 rmuc
        #     # x坐标：台阶到基地边缘1655mm+基地长1881mm+车身y半长198.5mm+地图投影边缘300mm=4036mm
        #     # y坐标：场地y半长7500mm-半车宽191mm+场地偏差40～50cm=7709mm
        #     # 蓝方启动点
        #     arguments=['4.234', '7.1', '0', '0.04', '0', '0', 'map', 'camera_init'],
        #     output='screen'),

        # 静态TF: map -> minimap
        launch_ros.actions.Node(
            package='tf2_ros',
            executable='static_transform_publisher',
            name='static_tf_map_to_minimap',
            # 红方使用全0，蓝方使用28,15
            # arguments=['0.3', '0', '0', '0', '0', '0', 'map', 'minimap'],
            arguments=['28.7', '15', '0', '3.14', '0', '0', 'map', 'minimap'],
            output='screen'),

        # 静态TF: camera_init -> body
        # launch_ros.actions.Node(
        #     package='tf2_ros',
        #     executable='static_transform_publisher',
        #     name='static_tf_camera_init_to_body',
        #     arguments=['0', '0', '0', '0', '0', '0', 'camera_init', 'body'],
        #     output='screen'),

        # # 静态TF: body -> base_link
        # launch_ros.actions.Node(
        #     package='tf2_ros',
        #     executable='static_transform_publisher',
        #     name='static_tf_body_to_base_link',
        #     arguments=['0', '0.20', '0', '0', '0', '0', 'body', 'base_link'],
        #     output='screen'),
        # 声明新的 Launch 参数
        launch.actions.DeclareLaunchArgument('use_sim_time', default_value=use_sim_time,
                                             description='Use simulation (Gazebo) clock if true'),
        launch.actions.DeclareLaunchArgument('map', default_value=map_yaml_path,
                                             description='Full path to map file to load'),
        launch.actions.DeclareLaunchArgument('params_file', default_value=nav2_param_path,
                                             description='Full path to param file to load'),
        launch.actions.DeclareLaunchArgument('localization', default_value='amcl',
                                             description='amcl keeps the current 2D localization; gicp uses a verified map.pcd bundle.'),
        launch.actions.DeclareLaunchArgument('start_serial', default_value='true'),
        launch.actions.DeclareLaunchArgument('serial_port', default_value='/dev/rm_nav0'),
        launch.actions.DeclareLaunchArgument('start_ptp', default_value='true',
                                             description='Start the MID360 PTP helper; false reuses existing PTP.'),
        launch.actions.DeclareLaunchArgument('start_sensors', default_value='true',
                                             description='Start mixed Livox + Point-LIO; false reuses existing sensors.'),
        launch.actions.DeclareLaunchArgument('ptp_script',
                                             default_value='/home/robomaster/mid360-ptp/start.sh'),
        launch.actions.DeclareLaunchArgument('ptp_interface', default_value='enp2s0'),
        launch.actions.DeclareLaunchArgument('projection_config',
                                             default_value=os.path.join(DreamChaser_dir, 'params', 'dual_lidar_mapping.yaml'),
                                             description='Use the same mounting and height band as mapping.'),
        # PlannerServer 的内部 costmap 从容器进程的 ROS 参数文件读取配置。
        # 只给 ComposableNode 传参会丢失 global_costmap 节，退回 Nav2 默认值。
        launch_ros.actions.SetParametersFromFile(navigation_params),
        launch.actions.OpaqueFunction(function=launch_navigation_scan),
        launch.actions.OpaqueFunction(function=launch_localization),
        launch.actions.OpaqueFunction(function=start_navigation_hardware),
        launch_ros.actions.Node(
            package='navi2', executable='pointcloud_self_filter',
            name='pointcloud_self_filter', output='screen',
            parameters=[{
                'input_topic': '/cloud_registered_full',
                'output_topic': '/cloud_registered_filtered',
                'body_frame': 'body',
                'min_x': -0.45, 'max_x': 0.45,
                'min_y': -0.45, 'max_y': 0.45,
                'min_z': -0.30, 'max_z': 1.20,
            }]),

        launch.actions.GroupAction([
            # Keep STVL code loaded until these navigation processes exit.
            launch.actions.SetEnvironmentVariable('LD_PRELOAD', runtime_env['LD_PRELOAD']),
            launch.actions.IncludeLaunchDescription(
                PythonLaunchDescriptionSource(
                    [DreamChaser_dir, '/launch', '/navigation_launch.py']),
                # 使用 Launch 参数替换原有参数
                launch_arguments={
                    'map': map_yaml_path,
                    'use_sim_time': use_sim_time,
                    'params_file': navigation_params,
                    'log_level': 'info',
                    'planner_container_name': 'livox_pointlio_container'}.items(),
            ),
        ]),
        launch.actions.IncludeLaunchDescription(
            PythonLaunchDescriptionSource(os.path.join(
                get_package_share_directory('nav_serial_driver'), 'launch', 'serial.launch.py')),
            launch_arguments={
                'start_serial': launch.substitutions.LaunchConfiguration('start_serial'),
                'port_name': launch.substitutions.LaunchConfiguration('serial_port'),
                'use_sim_time': use_sim_time}.items()),
        launch_ros.actions.Node(
            package='rviz2',
            executable='rviz2',
            name='rviz2',
            arguments=['-d', rviz_config_dir],
            parameters=[{'use_sim_time': use_sim_time}],
            output='screen'),
            
    ])
