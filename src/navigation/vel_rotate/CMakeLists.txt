cmake_minimum_required(VERSION 3.8)
project(vel_rotate)

find_package(ament_cmake REQUIRED)

install(PROGRAMS vel_rotate/vel_rotate_node.py
  DESTINATION lib/${PROJECT_NAME}
  RENAME vel_rotate_node)

ament_package()
