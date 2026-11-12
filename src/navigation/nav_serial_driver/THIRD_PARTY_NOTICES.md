# 来源与许可说明

本包的 QYG 帧定义、CRC、流式解析与 UART 传输代码复制并适配自：

- `/home/robomaster/QD_Vision26/src/rm_hardware_driver/rm_serial_driver`
- 原 `include/rm_serial_driver/protocol/qyg_protocol.hpp`、`src/protocol/qyg_protocol.cpp`
- 原 `include/rm_serial_driver/{uart_transporter,transporter_interface}.hpp`
- 原 `src/transporter_driver/uart_transporter.cpp`

原包 package.xml 声明 MIT，maintainer/author 为 Chen Jun。
UART 文件另带 RoboMaster-OSS (2021)、Chengfu Zou (2023)、FYT Vision Group
来源声明和 Apache-2.0 头部；已原样保留这些文件中的许可与版权声明。
原 QYG 源文件未附独立许可头，本文件记录其来源及原包许可声明，不声称重新授权。

本次适配调整 include 路径、二进制终端设置、非阻塞读取、有限写等待与失败资源回收；
导航协议已精简为 16 字节下发、20 字节回传；帧头和 CRC 算法保留。新增主机节点、测试及启动配置为本项目实现。
