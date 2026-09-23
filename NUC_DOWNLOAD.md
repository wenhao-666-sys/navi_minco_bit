# NUC 下载与源码来源

这是独立的 `wenhao-666-sys/navi_minco_bit` 仓库，与 USV-navigation 分开管理。

## 在 NUC 上下载

```bash
git clone https://github.com/wenhao-666-sys/navi_minco_bit.git
cd navi_minco_bit
```

私有仓库需要使用有权限的 GitHub 账号认证。已配置 SSH 密钥时，可以改用 `git@github.com:wenhao-666-sys/navi_minco_bit.git`。

后续在此目录执行 `git pull --ff-only` 获取已推送的修改。仿真源码已完整包含，不需要初始化子模块。

## 来源与固定版本

- 导航来源：https://github.com/Walker152/navi_minco_bit
- 上游分支：`master`
- 导航提交：`8288b7520ecb635bb27f16b0d49e3cf304f37a72`
- 仿真来源：https://github.com/Walker152/nav-simulation
- 仿真提交：`be40e3dbf0c493db17e5d6f019697c2399546fa0`
- 下载日期：2026-09-22；独立仓库整理日期：2026-09-23。

本仓库以源码快照建立独立历史。986 个上游文件的内容与上述提交完全一致，378 个文件保留上游可执行权限，原许可证保留。`src/simulation` 已展开为普通文件，原 `.gitmodules` 仅作为上游来源记录保留。`origin` 指向你的独立仓库，`upstream` 指向原作者仓库；请不要直接把两个无共同历史的仓库合并。

## 构建入口

使用 Ubuntu 22.04 / ROS 2 Humble，按照原始 [README.md](README.md) 安装依赖，在本仓库根目录执行 `bash build.bash`。本次只下载、保存和同步源码，未执行构建或运行验证。

原始 `start.bash` 写死了 `cd ~/2027-sentry-navi`，启动前需改成 NUC 上的实际路径。README 中部分克隆示例引用旧分支或旧目录，下载时以本文为准。
