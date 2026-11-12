"""主机导航独立串口；不需要 QD 工作区或容器。"""
import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PythonExpression
from launch_ros.actions import Node


def generate_launch_description():
    config = os.path.join(get_package_share_directory('nav_serial_driver'), 'config', 'serial.yaml')
    return LaunchDescription([
        DeclareLaunchArgument('port_name', default_value='/dev/rm_nav0'),
        DeclareLaunchArgument('start_serial', default_value='true'),
        DeclareLaunchArgument('use_sim_time', default_value='false'),
        Node(package='nav_serial_driver', executable='nav_serial_node', name='nav_serial_driver',
             parameters=[config, {'port_name': LaunchConfiguration('port_name')}], output='screen',
             condition=IfCondition(PythonExpression([
                 "'", LaunchConfiguration('start_serial'), "'.lower() == 'true' and '",
                 LaunchConfiguration('use_sim_time'), "'.lower() != 'true'"])))
    ])
