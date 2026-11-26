# FnNAS Qualcomm SM8250 构建

使用 `renas -b xiaomi-umi` 处理镜像，使用 `rekernel -b xiaomi-umi` 选择并编译内核。本目录提供 Qualcomm SM8250 的 ABL v2、内核、底包审计和组装实现。操作示例见 [UMI 构建指南](../../../docs/qualcomm/sm8250/xiaomi-umi/03-自行构建.md)。

| 路径 | 职责 |
| --- | --- |
| [`sources/fnos-upstream.lock`](sources/fnos-upstream.lock) | 实际验证过的上游公开 fnOS ARM64 归档 |
| [`boards/xiaomi-umi.yml`](../../boards/xiaomi-umi.yml) | Umi 目标板信息及待确认的 RootFS 文件系统 |
| [`fnnas-files/`](docs/rootfs-overlays.md) | Qualcomm SM8250 和 Xiaomi Umi 的 RootFS 文件层 |
| [`kernel/`](kernel/) | Linux 6.18.y 版本选择、Umi DTB 源码、ABL 补丁、CSOT 配置和 Debian 打包工具 |
| [`boot/abl-android-v2/`](boot/abl-android-v2/) | ABL 基线、overlay、v2 打包工具、诊断和测试 |
| [`scripts/`](scripts/) | 获取、审计、提取、覆盖、构建、组装和校验 |

旧版 Debian/Armbian 构建和发布材料集中在 [tools/legacy/](../../../tools/legacy/)，供复现和硬件回归。
CSOT 构建配置位于 `kernel/config/csot/`，固定源码快照位于 `sources/`。

[第三阶段运行与验收](../../../docs/qualcomm/sm8250/xiaomi-umi/qualcomm-stage3.md) 说明旁路 CI、Linux 6.18.y、公开锁定底包、本地提升及原生镜像组装。
历史 Debian 根文件系统只用于复现，不用于原生 fnOS。
