"""Dual Livox + Point-LIO mapping; optional matching PCD/grid export.

Can be launched by its absolute source path without building navi2.
"""
from datetime import datetime
import math
import os
from pathlib import Path
import sys
import sysconfig

import numpy as np
import yaml
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, IncludeLaunchDescription, LogInfo, OpaqueFunction
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def launch_mapping(context):
    # Check dependencies before starting the hardware container.
    for dependency in ('pointcloud_to_laserscan', 'slam_toolbox', 'tf2_ros'):
        get_package_share_directory(dependency)
    package_dir = Path(__file__).resolve().parents[1]
    backend = LaunchConfiguration('map_backend').perform(context)
    if backend not in ('slam_toolbox', 'pcd'):
        raise ValueError('map_backend must be slam_toolbox or pcd')
    if backend == 'pcd':
        output = Path(LaunchConfiguration('output_dir').perform(context)).expanduser()
        if (output / 'map.yaml').exists() and not (output / 'map_bundle.json').is_file():
            raise ValueError('PCD mapping requires a new output_dir; do not overwrite an existing SLAM map.')
    settings = yaml.safe_load(Path(LaunchConfiguration('mapping_config').perform(context)).read_text())
    pointlio_file = Path(LaunchConfiguration('pointlio_params_file').perform(context))
    pointlio = yaml.safe_load(pointlio_file.read_text())['/**']['ros__parameters']
    height, roll = float(settings['lidar_height']), float(settings['lidar_roll_rad'])
    low, high = float(settings['obstacle_min_height']), float(settings['obstacle_max_height'])
    resolution, interval = float(settings['resolution']), float(settings['save_interval'])
    if backend == 'pcd':
        max_range = float(settings['max_mapping_range'])
        if not math.isfinite(max_range) or max_range <= 0:
            raise ValueError('max_mapping_range must be finite and positive.')
    if not all(math.isfinite(v) for v in (height, roll, low, high, resolution, interval)):
        raise ValueError('Mapping height, angle, bounds, resolution and save interval must be finite.')
    if not (height > 0 and 0 <= low < high and resolution > 0 and interval > 0):
        raise ValueError('Require height > 0, 0 <= obstacle_min_height < obstacle_max_height, resolution > 0, save_interval > 0.')
    if pointlio['mapping']['extrinsic_est_en'] or not pointlio['publish']['tf_send_en']:
        raise ValueError('This mapping entry requires fixed lidar/IMU extrinsics and Point-LIO TF output.')
    # p_I = R_I_L p_L + T_I_L. R_W_L is the measured x-axis mounting
    # rotation; slambase has the IMU position and keeps only world yaw.
    r_i_l = np.asarray(pointlio['mapping']['extrinsic_R'], dtype=float).reshape(3, 3)
    t_i_l = np.asarray(pointlio['mapping']['extrinsic_T'], dtype=float)
    if t_i_l.shape != (3,) or not np.all(np.isfinite(t_i_l)) or not np.all(np.isfinite(r_i_l)):
        raise ValueError('Invalid fixed lidar/IMU extrinsics.')
    if not np.allclose(r_i_l.T @ r_i_l, np.eye(3), atol=1e-5) or not math.isclose(np.linalg.det(r_i_l), 1.0, abs_tol=1e-5):
        raise ValueError('extrinsic_R must be a proper rotation matrix.')
    r_w_l = np.array([[1, 0, 0], [0, math.cos(roll), -math.sin(roll)], [0, math.sin(roll), math.cos(roll)]])
    imu_height = height - float((r_w_l @ r_i_l.T @ t_i_l)[2])
    if imu_height <= 0:
        raise ValueError('Computed IMU height must be positive; check height and mounting convention.')
    library_env = {'LD_LIBRARY_PATH': os.pathsep.join(filter(None, (
        os.path.join('/usr/lib', sysconfig.get_config_var('MULTIARCH')),
        os.environ.get('LD_LIBRARY_PATH', ''),
    )))}
    saver = package_dir / 'scripts' / 'mapping_grid_saver.py'
    actions = [
        LogInfo(msg=f'Mapping: lidar height={height:.5f}m, IMU height={imu_height:.5f}m, ground obstacle band=[{low}, {high}]m. Verify mounting sign and housing-center offset.'),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(str(Path(get_package_share_directory('point_lio')) / 'launch' / 'livox_pointlio_intra_process.launch.py')),
            launch_arguments={
                'driver_params_file': LaunchConfiguration('driver_params_file'),
                'pointlio_params_file': str(pointlio_file),
                'pointlio_imu_topic': 'livox/imu_192_168_1_100',
            }.items(),
            condition=IfCondition(LaunchConfiguration('start_sensors')),
        ),
        # A dedicated ground projection frame, not a replacement for base_link.
        Node(package='tf2_ros', executable='static_transform_publisher',
             name='mapping_ground_transform', arguments=[
                 '--x', '0', '--y', '0', '--z', str(-imu_height),
                 '--roll', '0', '--pitch', '0', '--yaw', '0',
                 '--frame-id', 'slambase', '--child-frame-id', 'mapping_ground'],
             parameters=[{'use_sim_time': LaunchConfiguration('use_sim_time')}]),
        Node(package='pointcloud_to_laserscan', executable='pointcloud_to_laserscan_node',
             name='pointcloud_to_laserscan', output='screen', additional_env=library_env,
             parameters=[{
                 'target_frame': 'mapping_ground', 'transform_tolerance': 0.05,
                 'queue_size': 5, 'min_height': low, 'max_height': high,
                 'angle_min': -math.pi, 'angle_max': math.pi, 'angle_increment': 0.0087,
                 'scan_time': 0.05, 'range_min': 0.4, 'range_max': 10.0,
                 'use_inf': True, 'inf_epsilon': 1.0,
                 'use_sim_time': LaunchConfiguration('use_sim_time'),
             }], remappings=[('cloud_in', '/cloud_registered_filtered'), ('scan', '/scan')]),
        Node(package='navi2', executable='pointcloud_self_filter',
             name='mapping_pointcloud_self_filter', output='screen',
             parameters=[{
                 'input_topic': '/cloud_registered_full',
                 'output_topic': '/cloud_registered_filtered',
                 'body_frame': 'body',
                 'min_x': -0.45, 'max_x': 0.45,
                 'min_y': -0.45, 'max_y': 0.45,
                 'min_z': -0.30, 'max_z': 1.20,
             }]),
    ]
    if backend == 'pcd':
        actions.extend([
            Node(package='tf2_ros', executable='static_transform_publisher',
                 name='pcd_mapping_origin', arguments=[
                     '--frame-id', 'map', '--child-frame-id', 'camera_init'],
                 parameters=[{'use_sim_time': LaunchConfiguration('use_sim_time')}]),
            ExecuteProcess(cmd=[sys.executable, str(package_dir / 'scripts' / 'pcd_map_saver.py'),
                                '--output', LaunchConfiguration('output_dir'),
                                '--input-topic', '/cloud_registered_filtered',
                                '--interval', str(interval), '--resolution', str(resolution),
                                '--ground-z', str(-imu_height), '--min-height', str(low),
                                '--max-height', str(high), '--max-range', str(max_range),
                                '--use-sim-time', LaunchConfiguration('use_sim_time')],
                           output='screen', sigterm_timeout='30', sigkill_timeout='10'),
        ])
    else:
        actions.extend([
            Node(package='slam_toolbox', executable='async_slam_toolbox_node',
                 name='slam_toolbox', output='screen', additional_env=library_env,
                 parameters=[str(package_dir / 'params' / 'slam.yaml'), {
                     'use_sim_time': LaunchConfiguration('use_sim_time'),
                     'base_frame': 'mapping_ground', 'odom_frame': 'camera_init',
                     'map_frame': 'map', 'scan_topic': '/scan', 'resolution': resolution,
                 }]),
            ExecuteProcess(cmd=[sys.executable, str(saver),
                                '--output', LaunchConfiguration('output_dir'),
                                '--input-topic', '/cloud_registered_filtered',
                                '--interval', str(interval)], output='screen'),
        ])
    actions.extend([
        Node(package='rviz2', executable='rviz2', name='mapping_rviz',
             arguments=['-d', str(package_dir / 'config' / 'dual_lidar_mapping.rviz')],
             parameters=[{'use_sim_time': LaunchConfiguration('use_sim_time')}],
             condition=IfCondition(LaunchConfiguration('rviz'))),
    ])
    return actions


def generate_launch_description():
    package_dir = Path(__file__).resolve().parents[1]
    return LaunchDescription([
        DeclareLaunchArgument('map_backend', default_value='slam_toolbox',
                              description='pcd exports matching map.pcd + map.pgm + map.yaml from Point-LIO; slam_toolbox keeps the existing 2D SLAM.'),
        DeclareLaunchArgument('mapping_config', default_value=str(package_dir / 'params' / 'dual_lidar_mapping.yaml')),
        DeclareLaunchArgument('driver_params_file', default_value=str(Path(get_package_share_directory('livox_ros_driver2')) / 'config' / 'mixed_MID360_component.yaml')),
        DeclareLaunchArgument('pointlio_params_file', default_value=str(Path(get_package_share_directory('point_lio')) / 'config' / 'mid360.yaml')),
        DeclareLaunchArgument('output_dir', default_value=str(Path.home() / 'maps' / datetime.now().strftime('mapping_%Y%m%d_%H%M%S'))),
        DeclareLaunchArgument('rviz', default_value='true'),
        DeclareLaunchArgument('start_sensors', default_value='true', description='False only when replaying a bag or using an existing driver/Point-LIO.'),
        DeclareLaunchArgument('use_sim_time', default_value='false'),
        OpaqueFunction(function=launch_mapping),
    ])
