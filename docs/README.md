# FnNAS 文档索引

从 [FnNAS 中文主文档](../README.cn.md) 查看平台列表、安装和构建入口。以下指南用于 Qualcomm SM8250 的小米 10（`xiaomi-umi`）适配。

| 文档 | 给谁看 | 内容 |
|---|---|---|
| [小米 10 机型说明](../README.umi.md) | 小米 10 用户和开发者 | 适配架构、硬件状态、源码来源和引导约束 |
| [`01-快速开始.md`](01-快速开始.md) | 使用 Debian 旧基线的人 | 前置检查、备份、首启加固和回滚 |
| [`02-使用指南.md`](02-使用指南.md) | **已经刷上系统的人** | 串口 / USB 网卡 / WiFi、充电上限、GPU、硬编解、服务清单、保命机制与故障排查 |
| [`03-自行构建.md`](03-自行构建.md) | 开发和构建人员 | `renas`、`rekernel`、内核 6.18.y 选版、fnOS 样本组装和历史构建 |
| [真机无刷写验收](04-真机无刷写验收.md) | 内核和启动链验证人员 | DTBO 预检、临时启动、RAM 探针及真机记录 |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | **要提交改动的人** | 本地检查、提交规范、PR 内容与真机验收记录 |
| [`04-发布与下载.md`](04-发布与下载.md) | **要发版的人** | Release 产物清单与校验、拆包上传、发布前检查清单 |
| [`RELEASE-NOTES.md`](RELEASE-NOTES.md) | 发 Release 时 | UMI 的 GitHub Release 正文模板 |

## 来源与技术参考文档

| 文档 | 内容 |
|---|---|
| [NOTICE](../NOTICE.md) | FnNAS 和 UMI 的版权、来源与组件许可 |
| [LICENSE](../LICENSE) | FnNAS 根许可证，GPL v2 全文 |
| [历史 Boot 构建](../tools/legacy/boot-build/BUILD.md) | boot 构建链技术细节（ABL 锚点、`dts.patch` 改动、v0→v2 重打包） |
| [Debian 基线构建](../tools/legacy/rootfs-build/BUILD.md) | Armbian 构建框架的 `umi` 移植说明与 `6.18.60` 内核目标说明 |

## CI / 持续集成

本仓库的 GitHub Actions 工作流（[`.github/workflows/ci.yml`](../.github/workflows/ci.yml)）包含以下检查：

| Job | 触发条件 | 内容 |
|---|---|---|
| `repository` | PR、推送到 `main` | 在 Ubuntu、macOS、Windows 上跑 boot 工具测试，在 Ubuntu 上安装 DTC 并跑 rootfs DTB 测试 |
| `checks` | PR、推送到 `main` | 在 Ubuntu 上检查 Shell 语法、统一入口、内核选版和发布包，以及 ABL/DTBO、串口设密和充电限流 |
| `base-image-audit` | PR、推送到 `main` | 生成并审计 ext4 和 Btrfs 测试镜像 |

[`build-kernel.yml`](../.github/workflows/build-kernel.yml) 支持按构建配置编译 UMI 内核，也可选复现 Debian 基线。表中的触发条件来自工作流文件。开发分支和默认分支的发布限制见 [发布与下载](04-发布与下载.md)。
