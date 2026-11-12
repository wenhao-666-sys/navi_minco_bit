#include <gtest/gtest.h>
#include <array>
#include <cstring>
#include "nav_serial_driver/qyg_protocol.hpp"
namespace qyg = qd::serial_driver::protocol::qyg;
TEST(Protocol, LayoutAndCrc)
{
  EXPECT_EQ(sizeof(qyg::QygSendFrame), 16U);
  EXPECT_EQ(sizeof(qyg::QygReceiveFrame), 20U);
  const auto *text = reinterpret_cast<const uint8_t *>("123456789");
  EXPECT_EQ(qyg::crc16(text, 9), 0x6f91);
  auto frame = qyg::makeSendFrame(1.25, -2.5, 0.75);
  EXPECT_FLOAT_EQ(frame.linear_x, 1.25);
  EXPECT_FLOAT_EQ(frame.linear_y, -2.5);
  EXPECT_FLOAT_EQ(frame.angular_z, 0.75);
  EXPECT_EQ(frame.crc16, qyg::crc16(reinterpret_cast<const uint8_t *>(&frame), 14));
}
TEST(Protocol, FragmentsNoiseCorruptionAndConcatenation)
{
  qyg::QygReceiveFrame frame;
  frame.big_yaw = 123.5;
  frame.crc16 = qyg::crc16(reinterpret_cast<const uint8_t *>(&frame), 18);
  const auto *bytes = reinterpret_cast<const uint8_t *>(&frame);
  qyg::QygStreamParser parser;
  const std::array<uint8_t, 5> noise{0xff, 0, 'G', 'D', 0xff};
  parser.append(noise.data(), noise.size());
  auto bad = frame;
  bad.crc16 ^= 1;
  parser.append(reinterpret_cast<const uint8_t *>(&bad), sizeof(bad));
  parser.append(bytes, 9);
  EXPECT_FALSE(parser.popFrame());
  parser.append(bytes + 9, sizeof(frame) - 9);
  parser.append(bytes, sizeof(frame));
  auto first = parser.popFrame();
  ASSERT_TRUE(first);
  EXPECT_FLOAT_EQ(first->big_yaw, 123.5);
  EXPECT_TRUE(parser.popFrame());
  EXPECT_FALSE(parser.popFrame());
}
