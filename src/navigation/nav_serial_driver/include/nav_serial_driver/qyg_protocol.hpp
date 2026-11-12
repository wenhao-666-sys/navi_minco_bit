// Adapted from QD_Vision26 rm_serial_driver for host navigation.
#ifndef RM_SERIAL_DRIVER__PROTOCOL__QYG_PROTOCOL_HPP_
#define RM_SERIAL_DRIVER__PROTOCOL__QYG_PROTOCOL_HPP_

#include <cstddef>
#include <cstdint>
#include <limits>
#include <optional>
#include <vector>

namespace qd::serial_driver::protocol::qyg
{
#pragma pack(push, 1)
/** @brief 导航回传帧：实际速度及大云台角。 */
struct QygReceiveFrame
{
  uint8_t header[2]{'G', 'D'};
  float chassis_vx{0.0F};  // m/s，与指令同坐标系
  float chassis_vy{0.0F};  // m/s，与指令同坐标系
  float chassis_wz{0.0F};  // rad/s
  float big_yaw{0.0F};     // 度
  uint16_t crc16{0};
};

/** @brief 导航下发帧：vx、vy、wz。 */
struct QygSendFrame
{
  uint8_t header[2]{'Q', 'Y'};
  float linear_x{0.0F};   // m/s
  float linear_y{0.0F};   // m/s
  float angular_z{0.0F};  // rad/s
  uint16_t crc16{0};
};
#pragma pack(pop)

static_assert(sizeof(float) == 4, "Protocol requires 32-bit float");
static_assert(std::numeric_limits<float>::is_iec559, "Protocol requires IEEE-754 float");
static_assert(sizeof(QygReceiveFrame) == 20, "Receive frame must be 20 bytes");
static_assert(offsetof(QygReceiveFrame, chassis_vx) == 2, "Invalid vx offset");
static_assert(offsetof(QygReceiveFrame, chassis_vy) == 6, "Invalid vy offset");
static_assert(offsetof(QygReceiveFrame, chassis_wz) == 10, "Invalid wz offset");
static_assert(offsetof(QygReceiveFrame, big_yaw) == 14, "Invalid big_yaw offset");
static_assert(offsetof(QygReceiveFrame, crc16) == 18, "Invalid receive CRC offset");
static_assert(sizeof(QygSendFrame) == 16, "Send frame must be 16 bytes");
static_assert(offsetof(QygSendFrame, linear_x) == 2, "Invalid vx offset");
static_assert(offsetof(QygSendFrame, linear_y) == 6, "Invalid vy offset");
static_assert(offsetof(QygSendFrame, angular_z) == 10, "Invalid wz offset");
static_assert(offsetof(QygSendFrame, crc16) == 14, "Invalid send CRC offset");

/** @brief 计算 CRC：初值 0xFFFF，反射多项式 0x8408，无最终异或。 */
uint16_t crc16(const uint8_t * data, size_t length);

/** @brief 原值打包 vx/vy/wz 并计算 CRC；任一非有限值使三项归零。 */
QygSendFrame makeSendFrame(float linear_x, float linear_y, float angular_z);

/**
 * @brief 校验并解析一帧 QYG 回传数据。
 * @param data 串口数据缓冲区。
 * @param length 缓冲区长度。
 * @return 校验成功时返回回传帧，否则返回空值。
 */
std::optional<QygReceiveFrame> parseReceiveFrame(const uint8_t * data, size_t length);

/** @brief 从可能包含噪声和分片数据的字节流中提取 QYG 回传帧。 */
class QygStreamParser
{
public:
  /** @brief 追加一段串口数据到解析缓存。 */
  void append(const uint8_t * data, size_t length);
  /** @brief 弹出下一帧完整且 CRC 正确的回传帧。 */
  std::optional<QygReceiveFrame> popFrame();
  /** @brief 返回当前缓存中的字节数。 */
  size_t bufferedSize() const;

private:
  std::vector<uint8_t> buffer_;
};

}  // namespace qd::serial_driver::protocol::qyg

#endif  // RM_SERIAL_DRIVER__PROTOCOL__QYG_PROTOCOL_HPP_
