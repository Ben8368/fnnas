# 构建源码与外部输入锁定审计

本表区分版本固定和可用性控制权。Commit/SHA 固定可防止构建漂移，但不能保证外部仓库或 Release 永久在线。

| 依赖 | 当前锁定 | 获取 / 控制情况 | 建议 |
|---|---|---|---|
| 原生显示源码 | 60 Hz `3263cff0483f9cfa66c5ac693d759b4c7a6710d2`；90 Hz `774c0a40b65d5f240fc69cd02f797e0a9196fcbb`；实验 `fb5f76c7e6adef9bde55f93cd4e41f0beab953e9` | 已直接纳入 `make-fnnas/qualcomm/sm8250/sources/display-60/`、`display-90/` 和 `board-lab/`；构建时从工作树复制，不访问外部显示仓库。固定版本记录在 `sources/display-source-revisions.txt`。 | 已处理。更新显示代码时同步更新快照、版本清单和对应验收记录。文件中的 SPDX 标记优先；AGPL 文本随仓库提供。 |
| Umi 无线 RX | 项目内 `sources/board-lab/kernel/power/` 快照及 `CSOT_RX_PROFILE` 配置 | RX1619、LN8282、邮箱、输入仲裁与热策略已纳入仓库；lab 构建默认 `off`，`observe/link/epp/buck` 需显式选择，release 组装拒绝该 lab 内核。 | 已完成代码移植；尚未在本仓库构建、RAM 启动或进行无线充电真机验收。先完成隔离、限流、热故障和有线切换验证，再评估 `buck`。 |
| 内核配置 | 基线 boot SHA-256 `a7e4d341e35a663683bf41a8fe99d472bc6b8568aa1b54b05901dc7e9f2d842a`；基线配置 SHA-256 `a29b9bcfc0d70b4d48e75806fe26ba9766801ffd4915544d8fce483513bdac7e`；CSOT 90 Hz 最终配置 SHA-256 `557c702eb0ff89af6bde6d5a1e3f69987f78a292646945fd4e42b8b0d0ce9abf` | 基线保存于 `make-fnnas/qualcomm/sm8250/kernel/config/umi-6.18.60-base.config`，本次完整解析配置保存于 `make-fnnas/qualcomm/sm8250/kernel/config/umi-6.18.60-csot90.config`。构建会重新提取 base boot 的 IKCONFIG 并逐字节核对基线；Btrfs 和依赖通过 `make-fnnas/qualcomm/sm8250/kernel/config/csot/btrfs-built-in.config` 版本控制。 | 已处理。具体构建 profile 的完整 `.config` 也纳入仓库，变化由版本化配置片段表达。 |
| Linux stable 内核 | 标签 `v6.18.60`，构建脚本校验 commit `f45ed76d6791cf72ff1265ee93511175bbbc2f18` | 从 kernel.org 克隆；支持用 `KERNEL_BUNDLE` 指向本地 Git 源。当前 6.18.60 源码 Git 对象约 282 MiB。 | 不把整套 Linux Git 对象塞入主项目。官方上游和精确 SHA 足以满足常规构建；离线构建时单独保存 bundle。 |
| Armbian 构建补丁 | 配置仓库 commit `34f492406aed63269c88a5e0063cbac6a029e6a3` | 所需 `patch/kernel/archive/sm8250-6.18/`（约 760 KiB、74 项）及 GPL 许可证已纳入 `make-fnnas/qualcomm/sm8250/sources/armbian-34f4924/`；构建不再克隆 Armbian 全仓库。 | 已处理。更新补丁时应从新的精确 commit 重建该目录快照，并同步 `SOURCE.txt`。 |
| 基线 boot 与 rootfs 压缩包 | `misaka-link/umi-linux` Release `v2026-09-27`；boot SHA-256 `a7e4d341e35a663683bf41a8fe99d472bc6b8568aa1b54b05901dc7e9f2d842a`；rootfs tar SHA-256 `51f4b38d23b71d7d70b7472b3ef95e673c0e984f1f7c489c75305fc4fb2d645f` | Release 属于外部账号；rootfs tar 约 2.12 GB。SHA 校验保证内容完整，但不保证下载地址永久可用。`tools/ci-build.sh` 支持 `UMI_BASE_INPUT_DIR` 从本地缓存读取。 | 建议把两份原始输入复制到自己控制的 Release 资产或对象存储；通过 `UMI_BASE_INPUT_DIR` 使用，不要放进 Git。 |
| GitHub Actions | `checkout` 和 `setup-python` 均使用完整 action commit SHA | action 本身已锁定。CI 检查阶段通过 apt 安装 DTC，系统包版本随 Ubuntu 镜像更新。 | action 无需另建镜像；apt 版本漂移只影响检查环境，不是主镜像源码依赖。 |

## 复现边界

当前 release assembly 从 SHA 校验过的 Debian rootfs tar 展开，复用其中已有软件包；Linux 源码校验精确 commit，基线和最终内核配置、显示代码和 Armbian 补丁均已纳入仓库。要做到不依赖第三方保留的完整离线重建，仍需把 Linux 源码归档和两份基线输入存入项目所有者可控的 Release/对象存储。原始镜像和 Linux Git 对象都不适合复制进普通源码仓库。`KERNEL_BUNDLE` 和 `UMI_BASE_INPUT_DIR` 已支持从本地归档读取，上传动作待恢复 GitHub 发布权限后完成。
