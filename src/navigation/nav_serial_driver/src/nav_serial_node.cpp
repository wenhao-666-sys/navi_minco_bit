#include <array>
#include <chrono>
#include <cmath>
#include <limits>
#include <memory>
#include <stdexcept>

#include "geometry_msgs/msg/twist.hpp"
#include "nav_serial_driver/msg/serial_receive_data.hpp"
#include "nav_serial_driver/msg/serial_send_data.hpp"
#include "nav_serial_driver/qyg_protocol.hpp"
#include "nav_serial_driver/uart_transporter.hpp"
#include "rclcpp/rclcpp.hpp"

namespace qyg = qd::serial_driver::protocol::qyg;
using Clock = std::chrono::steady_clock;

class NavSerialNode : public rclcpp::Node
{
public:
  NavSerialNode() : Node("nav_serial_driver")
  {
    const auto port = declare_parameter<std::string>("port_name", "/dev/rm_nav0");
    const auto baud = declare_parameter<int>("baud_rate", 921600);
    timeout_ = declare_parameter<double>("command_timeout", 0.25);
    if (!std::isfinite(timeout_) || timeout_ <= 0) throw std::invalid_argument("Invalid command_timeout");
    if (baud != 921600 && baud != 115200 && baud != 19200 && baud != 9600 &&
        baud != 4800 && baud != 2400 && baud != 1200 && baud != 300)
      throw std::invalid_argument("Unsupported baud_rate");
    uart_ = std::make_unique<qd::serial_driver::UartTransporter>(port, baud);
    tx_pub_ = create_publisher<nav_serial_driver::msg::SerialSendData>("/nav/serial/send", rclcpp::SensorDataQoS());
    rx_pub_ = create_publisher<nav_serial_driver::msg::SerialReceiveData>("/nav/serial/receive", rclcpp::SensorDataQoS());
    actual_pub_ = create_publisher<geometry_msgs::msg::Twist>("/cmd_vel_real", rclcpp::SensorDataQoS());
    command_sub_ = create_subscription<geometry_msgs::msg::Twist>(
      "/cmd_vel_mpc", rclcpp::SensorDataQoS(), [this](geometry_msgs::msg::Twist::ConstSharedPtr msg) {
        last_command_ = Clock::now();
        have_command_ = true;
        latest_ = *msg;
        if (!valid(latest_.linear.x) || !valid(latest_.linear.y) || !valid(latest_.angular.z)) {
          latest_ = geometry_msgs::msg::Twist();
          RCLCPP_WARN_THROTTLE(get_logger(), *get_clock(), 2000, "Invalid velocity; sending zero");
        }
        send(latest_);
      });
    // 所有串口收发与重连仅由单线程执行器调用。
    timer_ = create_wall_timer(std::chrono::milliseconds(5), [this] { tick(); });
    RCLCPP_INFO(get_logger(), "Navigation UART: %s, %d baud, 8N1, no flow control", port.c_str(), static_cast<int>(baud));
  }

  ~NavSerialNode() override
  {
    // ROS 上下文可能已经关闭；退出时仅尽力写零帧，不发布观测话题。
    if (uart_->isOpen()) {
      const auto zero = makeFrame(geometry_msgs::msg::Twist());
      uart_->write(&zero, sizeof(zero));
      uart_->close();
    }
  }

private:
  static bool valid(double value)
  {
    return std::isfinite(value) && std::abs(value) <= std::numeric_limits<float>::max();
  }

  static qyg::QygSendFrame makeFrame(const geometry_msgs::msg::Twist & velocity)
  {
    return qyg::makeSendFrame(static_cast<float>(velocity.linear.x),
      static_cast<float>(velocity.linear.y), static_cast<float>(velocity.angular.z));
  }

  void disconnect()
  {
    uart_->close();
    parser_ = qyg::QygStreamParser();
    next_open_ = Clock::now() + std::chrono::seconds(1);
    RCLCPP_WARN_THROTTLE(get_logger(), *get_clock(), 2000, "Navigation UART unavailable: %s", uart_->errorMessage().c_str());
  }

  bool connect()
  {
    if (uart_->isOpen()) return true;
    if (Clock::now() < next_open_) return false;
    if (!uart_->open()) { disconnect(); return false; }
    RCLCPP_INFO(get_logger(), "Navigation UART connected");
    return true;
  }

  void send(const geometry_msgs::msg::Twist & velocity)
  {
    if (!connect()) return;
    const auto frame = makeFrame(velocity);
    if (uart_->write(&frame, sizeof(frame)) != static_cast<int>(sizeof(frame))) {
      disconnect();
      return;
    }
    nav_serial_driver::msg::SerialSendData msg;
    msg.header.stamp = now();
    msg.linear_x = frame.linear_x;
    msg.linear_y = frame.linear_y;
    msg.angular_z = frame.angular_z;
    tx_pub_->publish(msg);
  }

  void tick()
  {
    const auto time = Clock::now();
    if (!have_command_ || std::chrono::duration<double>(time - last_command_).count() > timeout_) {
      if (time >= next_zero_) {
        send(geometry_msgs::msg::Twist());
        next_zero_ = time + std::chrono::milliseconds(50);
      }
    }
    if (!connect()) return;
    std::array<uint8_t, 512> bytes{};
    // 限制每次回调工作量，避免连续反馈挤占指令和看门狗。
    for (int i = 0; i < 8; ++i) {
      const int length = uart_->read(bytes.data(), bytes.size());
      if (length < 0) { disconnect(); return; }
      if (length == 0) break;
      parser_.append(bytes.data(), static_cast<size_t>(length));
      while (const auto frame = parser_.popFrame()) publishFeedback(*frame);
    }
  }

  void publishFeedback(const qyg::QygReceiveFrame & frame)
  {
    nav_serial_driver::msg::SerialReceiveData msg;
    msg.header.stamp = now();
    msg.chassis_vx = frame.chassis_vx;
    msg.chassis_vy = frame.chassis_vy;
    msg.chassis_wz = frame.chassis_wz;
    msg.big_yaw = frame.big_yaw;
    rx_pub_->publish(msg);
    geometry_msgs::msg::Twist velocity;
    velocity.linear.x = frame.chassis_vx;
    velocity.linear.y = frame.chassis_vy;
    velocity.angular.z = frame.chassis_wz;
    actual_pub_->publish(velocity);
  }

  std::unique_ptr<qd::serial_driver::UartTransporter> uart_;
  qyg::QygStreamParser parser_;
  double timeout_;
  bool have_command_{false};
  Clock::time_point last_command_{}, next_zero_{}, next_open_{};
  geometry_msgs::msg::Twist latest_;
  rclcpp::TimerBase::SharedPtr timer_;
  rclcpp::Subscription<geometry_msgs::msg::Twist>::SharedPtr command_sub_;
  rclcpp::Publisher<nav_serial_driver::msg::SerialSendData>::SharedPtr tx_pub_;
  rclcpp::Publisher<nav_serial_driver::msg::SerialReceiveData>::SharedPtr rx_pub_;
  rclcpp::Publisher<geometry_msgs::msg::Twist>::SharedPtr actual_pub_;
};

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  try {
    rclcpp::spin(std::make_shared<NavSerialNode>());
  } catch (const std::exception & error) {
    RCLCPP_ERROR(rclcpp::get_logger("nav_serial_driver"), "%s", error.what());
    if (rclcpp::ok()) rclcpp::shutdown();
    return 1;
  }
  if (rclcpp::ok()) rclcpp::shutdown();
  return 0;
}
