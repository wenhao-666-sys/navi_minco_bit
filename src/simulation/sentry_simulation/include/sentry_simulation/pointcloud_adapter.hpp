#ifndef SENTRY_SIMULATION__POINTCLOUD_ADAPTER_HPP_
#define SENTRY_SIMULATION__POINTCLOUD_ADAPTER_HPP_

#include <cstddef>
#include <cstdint>
#include <deque>
#include <memory>
#include <string>
#include <vector>

#include <Eigen/Core>
#include <Eigen/Geometry>

#include "livox_ros_driver2/msg/custom_msg.hpp"
#include "nav_msgs/msg/odometry.hpp"
#include "rclcpp/rclcpp.hpp"
#include "sensor_msgs/msg/point_cloud2.hpp"

namespace sentry_simulation {

class PointCloudAdapter : public rclcpp::Node
{
public:
  explicit PointCloudAdapter(const rclcpp::NodeOptions & options);

private:
  struct PatternRay
  {
    double azimuth_rad;
    double elevation_rad;
  };

  struct TimedPose
  {
    std::int64_t stamp;
    Eigen::Vector3d position;
    Eigen::Quaterniond rotation;
  };

  static Eigen::Isometry3d make_sensor_transform(const std::vector<double> & pose);
  void ground_truth_callback(nav_msgs::msg::Odometry::ConstSharedPtr message);
  void left_front_cloud_callback(sensor_msgs::msg::PointCloud2::UniquePtr message);
  void left_rear_cloud_callback(sensor_msgs::msg::PointCloud2::UniquePtr message);
  void right_front_cloud_callback(sensor_msgs::msg::PointCloud2::UniquePtr message);
  void right_rear_cloud_callback(sensor_msgs::msg::PointCloud2::UniquePtr message);
  void publish_synchronized_clouds();
  void reset_clouds();
  Eigen::Isometry3d lidar_pose_at(std::int64_t stamp) const;

  std::vector<PatternRay> pattern_;
  std::size_t pattern_index_{0};
  int pattern_points_per_frame_{0};
  double vertical_min_rad_{0.0};
  double vertical_max_rad_{0.0};
  std::int64_t scan_period_ns_{0};
  std::int64_t sync_tolerance_ns_{0};
  std::int64_t last_scan_end_{-1};
  std::string output_frame_id_;
  std::string secondary_output_frame_id_;
  Eigen::Isometry3d lidar_pose_in_model_{Eigen::Isometry3d::Identity()};
  Eigen::Isometry3d left_transform_{Eigen::Isometry3d::Identity()};
  Eigen::Isometry3d right_transform_{Eigen::Isometry3d::Identity()};
  Eigen::Isometry3d left_inverse_transform_{Eigen::Isometry3d::Identity()};
  Eigen::Isometry3d right_inverse_transform_{Eigen::Isometry3d::Identity()};
  std::deque<TimedPose> pose_history_;
  sensor_msgs::msg::PointCloud2::UniquePtr left_front_cloud_;
  sensor_msgs::msg::PointCloud2::UniquePtr left_rear_cloud_;
  sensor_msgs::msg::PointCloud2::UniquePtr right_front_cloud_;
  sensor_msgs::msg::PointCloud2::UniquePtr right_rear_cloud_;
  rclcpp::Subscription<nav_msgs::msg::Odometry>::SharedPtr ground_truth_subscription_;
  rclcpp::Subscription<sensor_msgs::msg::PointCloud2>::SharedPtr left_front_subscription_;
  rclcpp::Subscription<sensor_msgs::msg::PointCloud2>::SharedPtr left_rear_subscription_;
  rclcpp::Subscription<sensor_msgs::msg::PointCloud2>::SharedPtr right_front_subscription_;
  rclcpp::Subscription<sensor_msgs::msg::PointCloud2>::SharedPtr right_rear_subscription_;
  rclcpp::Publisher<livox_ros_driver2::msg::CustomMsg>::SharedPtr publisher_;
  rclcpp::Publisher<livox_ros_driver2::msg::CustomMsg>::SharedPtr secondary_publisher_;
};

}  // namespace sentry_simulation

#endif  // SENTRY_SIMULATION__POINTCLOUD_ADAPTER_HPP_
