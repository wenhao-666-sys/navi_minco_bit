// Adapted from QD_Vision26 rm_serial_driver for host navigation.
// Copyright (C) 2021 RoboMaster-OSS
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
//
// Additional modifications and features by Chengfu Zou, 2023.
//
// Copyright (C) FYT Vision Group. All rights reserved.

#include "nav_serial_driver/uart_transporter.hpp"
// System
#include <chrono>
#include <errno.h>  /*错误号定义*/
#include <fcntl.h>  /*文件控制定义*/
#include <poll.h>
#include <stdio.h>  /*标准输入输出定义*/
#include <stdlib.h> /*标准函数库定义*/
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <termios.h> /*PPSIX 终端控制定义*/
#include <unistd.h>  /*Unix 标准函数定义*/

namespace qd::serial_driver {

bool UartTransporter::setParam(int speed, int flow_ctrl, int databits, int stopbits, int parity) {
  // 设置串口数据帧格式
  int speed_arr[] = {B921600, B115200, B19200, B9600, B4800, B2400, B1200, B300};
  int name_arr[] = {921600, 115200, 19200, 9600, 4800, 2400, 1200, 300};
  bool supported = false;
  for (const int value : name_arr) supported = supported || speed == value;
  if (!supported) { error_message_ = "Unsupported baud rate"; return false; }
  struct termios options;
  // tcgetattr(fd,&options)得到与fd指向对象的相关参数，并将它们保存于options,该函数还可以测试配置是否正确，
  // 该串口是否可用等。若调用成功，函数返回值为0，若调用失败，函数返回值为1.
  if (tcgetattr(fd_, &options) != 0) {
    error_message_ = "Setup Serial err";
    return false;
  }
  // 设置串口输入波特率和输出波特率
  for (size_t i = 0; i < sizeof(speed_arr) / sizeof(int); i++) {
    if (speed == name_arr[i]) {
      cfsetispeed(&options, speed_arr[i]);
      cfsetospeed(&options, speed_arr[i]);
    }
  }
  // 修改控制模式，保证程序不会占用串口
  options.c_cflag |= CLOCAL;
  // 修改控制模式，使得能够从串口中读取输入数据
  options.c_cflag |= CREAD;
  // 设置数据流控制
  switch (flow_ctrl) {
    case 0:  // 不使用流控制
      options.c_cflag &= ~CRTSCTS;
      break;
    case 1:  // 使用硬件流控制
      options.c_cflag |= CRTSCTS;
      break;
    case 2:  // 使用软件流控制
      options.c_cflag |= IXON | IXOFF | IXANY;
      break;
  }
  // 设置数据位
  // 屏蔽其他标志位
  options.c_cflag &= ~CSIZE;
  switch (databits) {
    case 5:
      options.c_cflag |= CS5;
      break;
    case 6:
      options.c_cflag |= CS6;
      break;
    case 7:
      options.c_cflag |= CS7;
      break;
    case 8:
      options.c_cflag |= CS8;
      break;
    default:
      error_message_ = "Unsupported data size";
      return false;
  }
  // 设置校验位
  switch (parity) {
    case 'n':
    case 'N':  // 无奇偶校验位。
      options.c_cflag &= ~PARENB;
      options.c_iflag &= ~INPCK;
      break;
    case 'o':
    case 'O':  // 设置为奇校验
      options.c_cflag |= (PARODD | PARENB);
      options.c_iflag |= INPCK;
      break;
    case 'e':
    case 'E':  // 设置为偶校验
      options.c_cflag |= PARENB;
      options.c_cflag &= ~PARODD;
      options.c_iflag |= INPCK;
      break;
    case 's':
    case 'S':  // 设置为空格
      options.c_cflag &= ~PARENB;
      options.c_cflag &= ~CSTOPB;
      break;
    default:
      error_message_ = "Unsupported parity";
      return false;
  }
  // 设置停止位
  switch (stopbits) {
    case 1:
      options.c_cflag &= ~CSTOPB;
      break;
    case 2:
      options.c_cflag |= CSTOPB;
      break;
    default:
      error_message_ = "Unsupported stop bits";
      return false;
  }

  // 修改输出模式，原始数据输出
  options.c_oflag &= ~OPOST;
  options.c_lflag &= ~(ICANON | ECHO | ECHOE | ISIG);
  // 传输特殊字符，否则特殊字符0x0d,0x11,0x13会被屏蔽或映射。
  options.c_iflag &= ~(IGNBRK | BRKINT | PARMRK | ICRNL | INLCR | IGNCR | INPCK | ISTRIP | IXON | IXOFF | IXANY);

  // 设置等待时间和最小接收字符
  options.c_cc[VTIME] = 0;  // 不等待字符
  options.c_cc[VMIN] = 0;   // 允许无数据立即返回
  tcflush(fd_, TCIFLUSH);

  // 激活配置 (将修改后的termios数据设置到串口中）
  if (tcsetattr(fd_, TCSANOW, &options) != 0) {
    error_message_ = "com set error";
    return false;
  }
  return true;
}

bool UartTransporter::open() {
  if (is_open_) {
    return true;
  }
  fd_ = ::open(device_path_.c_str(), O_RDWR | O_NOCTTY | O_NDELAY);
  if (-1 == fd_) {
    error_message_ = "can't open uart device: " + device_path_;
    return false;
  }
  // 单线程执行器中使用非阻塞读取和有限等待写入。
  if (fcntl(fd_, F_SETFL, O_NONBLOCK) < 0) {
    error_message_ = "fcntl failed";
    ::close(fd_);
    fd_ = -1;
    return false;
  }
  // 测试是否为终端设备
  // 避免自启动无法读取数据
  // if (0 == isatty(STDIN_FILENO)) {
  //   error_message_ = "standard input is not a terminal device";
  //   return false;
  // }
  // 设置串口数据帧格式
  if (!setParam(speed_, flow_ctrl_, databits_, stopbits_, parity_)) {
    ::close(fd_);
    fd_ = -1;
    return false;
  }
  is_open_ = true;
  return true;
}

void UartTransporter::close() {
  if (!is_open_) {
    return;
  }
  ::close(fd_);
  fd_ = -1;
  is_open_ = false;
}

bool UartTransporter::isOpen() { return is_open_; }

int UartTransporter::read(void *buffer, size_t len) {
  if (fd_ < 0) {
    error_message_ = "uart is not open";
    return -1;
  }

  pollfd poll_fd{fd_, POLLIN, 0};
  constexpr int READ_TIMEOUT_MS = 0;
  const int poll_result = ::poll(&poll_fd, 1, READ_TIMEOUT_MS);
  if (poll_result == 0) {
    return 0;
  }
  if (poll_result < 0) {
    if (errno == EINTR) {
      return 0;
    }
    error_message_ = ::strerror(errno);
    return -1;
  }
  if ((poll_fd.revents & (POLLERR | POLLHUP | POLLNVAL)) != 0) {
    error_message_ = "uart poll failed";
    return -1;
  }
  const int count = ::read(fd_, buffer, len);
  if (count < 0 && (errno == EAGAIN || errno == EINTR)) return 0;
  if (count < 0) error_message_ = ::strerror(errno);
  return count;
}

int UartTransporter::write(const void *buffer, size_t len) {
  const auto *bytes = static_cast<const unsigned char *>(buffer);
  size_t sent = 0;
  const auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(100);
  while (sent < len && std::chrono::steady_clock::now() < deadline) {
    const int remaining = static_cast<int>(std::chrono::duration_cast<std::chrono::milliseconds>(
      deadline - std::chrono::steady_clock::now()).count());
    pollfd descriptor{fd_, POLLOUT, 0};
    const int ready = ::poll(&descriptor, 1, remaining > 0 ? remaining : 0);
    if (ready < 0 && errno == EINTR) continue;
    if (ready <= 0 || (descriptor.revents & (POLLERR | POLLHUP | POLLNVAL))) break;
    const auto count = ::write(fd_, bytes + sent, len - sent);
    if (count < 0 && (errno == EAGAIN || errno == EINTR)) continue;
    if (count <= 0) break;
    sent += static_cast<size_t>(count);
  }
  if (sent != len) error_message_ = "UART write failed or exceeded 100 ms";
  return static_cast<int>(sent);
}

}  // namespace qd::serial_driver
