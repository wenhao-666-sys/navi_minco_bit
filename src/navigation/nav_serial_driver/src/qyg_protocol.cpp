// Adapted from QD_Vision26 rm_serial_driver for host navigation.
#include "nav_serial_driver/qyg_protocol.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstring>
#include <iterator>

namespace qd::serial_driver::protocol::qyg
{

uint16_t crc16(const uint8_t * data, size_t length)
{
  uint16_t crc = 0xFFFF;
  for (size_t i = 0; i < length; ++i) {
    crc ^= data[i];
    for (int bit = 0; bit < 8; ++bit) {
      crc = (crc & 0x0001U) != 0U ? static_cast<uint16_t>((crc >> 1U) ^ 0x8408U)
                                  : static_cast<uint16_t>(crc >> 1U);
    }
  }
  return crc;
}

QygSendFrame makeSendFrame(float linear_x, float linear_y, float angular_z)
{
  QygSendFrame frame;
  if (std::isfinite(linear_x) && std::isfinite(linear_y) && std::isfinite(angular_z)) {
    frame.linear_x = linear_x;
    frame.linear_y = linear_y;
    frame.angular_z = angular_z;
  }
  frame.crc16 = crc16(reinterpret_cast<const uint8_t *>(&frame), sizeof(frame) - 2);
  return frame;
}

std::optional<QygReceiveFrame> parseReceiveFrame(const uint8_t * data, size_t length)
{
  if (data == nullptr || length < sizeof(QygReceiveFrame) || data[0] != 'G' || data[1] != 'D') {
    return std::nullopt;
  }

  QygReceiveFrame frame;
  std::memcpy(&frame, data, sizeof(frame));
  const auto expected_crc = crc16(data, sizeof(frame) - 2);
  if (frame.crc16 != expected_crc) {
    return std::nullopt;
  }
  return frame;
}

void QygStreamParser::append(const uint8_t * data, size_t length)
{
  if (data == nullptr || length == 0) {
    return;
  }
  buffer_.insert(buffer_.end(), data, data + length);
  if (buffer_.size() > 4096) {
    buffer_.erase(buffer_.begin(), buffer_.end() - 1024);
  }
}

std::optional<QygReceiveFrame> QygStreamParser::popFrame()
{
  constexpr std::array<uint8_t, 2> HEADER{'G', 'D'};
  while (buffer_.size() >= HEADER.size()) {
    const auto start = std::search(buffer_.begin(), buffer_.end(), HEADER.begin(), HEADER.end());
    if (start == buffer_.end()) {
      const bool keep_g = buffer_.back() == 'G';
      buffer_.clear();
      if (keep_g) {
        buffer_.push_back('G');
      }
      return std::nullopt;
    }

    buffer_.erase(buffer_.begin(), start);
    if (buffer_.size() < sizeof(QygReceiveFrame)) {
      return std::nullopt;
    }

    const auto frame = parseReceiveFrame(buffer_.data(), buffer_.size());
    if (frame.has_value()) {
      buffer_.erase(buffer_.begin(), std::next(buffer_.begin(), sizeof(QygReceiveFrame)));
      return frame;
    }
    // 假帧头或 CRC 错误时仅丢一个字节，然后重新搜索 GD。
    buffer_.erase(buffer_.begin());
  }
  return std::nullopt;
}

size_t QygStreamParser::bufferedSize() const { return buffer_.size(); }

}  // namespace qd::serial_driver::protocol::qyg
