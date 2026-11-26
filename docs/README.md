# 文档索引

> 项目：**`fnos-xiaomi-umi`** —— 小米 10（`umi`）原生飞牛系统（fnOS）适配项目。
> 从哪开始看？**先读 [`../README.umi.md`](../README.umi.md) 了解项目背景、来源声明与 fnOS 适配架构，再按需查阅下表。**

| 文档 | 给谁看 | 内容 |
|---|---|---|
| [`../README.umi.md`](../README.umi.md) | **所有人，必读** | 项目定位、来源与参考声明、fnOS 适配架构、基线能力矩阵、引导硬约束与安全红线 |
| [`01-快速开始.md`](01-快速开始.md) | **要刷机验证的人** | 前置检查、备份基带、刷 tools/legacy/boot/dtbo/rootfs、首启加固、验收清单与回滚 |
| [`02-使用指南.md`](02-使用指南.md) | **已经刷上系统的人** | 串口 / USB 网卡 / WiFi、充电上限、GPU、硬编解、服务清单、保命机制与故障排查 |
| [`03-自行构建.md`](03-自行构建.md) | **要开发/构建的人** | 重建 boot、从零构建 rootfs、内核 6.18 LTS 切换与 fnOS 适配构建说明 |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | **要提交改动的人** | 本地检查、提交规范、PR 内容与真机验收记录 |
| [`04-发布与下载.md`](04-发布与下载.md) | **要发版的人** | Release 产物清单与校验、拆包上传、发布前检查清单 |
| [`RELEASE-NOTES.md`](RELEASE-NOTES.md) | 发 Release 时 | UMI 的 GitHub Release 正文模板 |

## 来源与技术参考文档

| 文档 | 内容 |
|---|---|
| [`../NOTICE.md`](../NOTICE.md) | 版权声明、`misaka-link/umi-linux` 起点声明、参考仓库列表与 GPL-2.0 合规声明 |
| [`../LICENSE.umi`](../LICENSE.umi) | GPL-2.0-only 许可证全文（含本项目与起点基线的版权声明） |
| [历史 Boot 构建](../tools/legacy/boot-build/BUILD.md) | boot 构建链技术细节（ABL 锚点、`dts.patch` 改动、v0→v2 重打包） |
| [Debian 基线构建](../tools/legacy/rootfs-build/BUILD.md) | Armbian 构建框架的 `umi` 移植说明与 `6.18.60` 内核目标说明 |

## CI / 持续集成

本仓库的 GitHub Actions 工作流（[`.github/workflows/ci.yml`](../.github/workflows/ci.yml)）包含以下检查：

| Job | 触发条件 | 内容 |
|---|---|---|
| `repository` | PR、推送到 `main` | 在 Ubuntu、macOS、Windows 上跑 boot 工具测试，在 Ubuntu 上安装 DTC 并跑 rootfs DTB 测试 |
| `checks` | PR、推送到 `main` | 在 Ubuntu 上检查 Shell 语法，并跑 ABL/DTBO、串口设密和充电限流回归测试 |
| `base-image-audit` | PR、推送到 `main` | 生成并审计 ext4 和 Btrfs 测试镜像 |

[`build-kernel.yml`](../.github/workflows/build-kernel.yml) 在 UMI 构建文件推送到 `main` 时编译内核，也支持手动选择构建配置和复现 Debian 基线。
