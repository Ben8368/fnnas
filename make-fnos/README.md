# fnOS ARM64 镜像移植

`make-fnos/` 是原生 fnOS 移植的构建目录。官方原始 ARM64 镜像提供 Debian 用户态、
`/usr/trim` 和 fnOS 服务。镜像文件作为只读输入，按版本和归档 SHA-256 固定。
目录和覆盖顺序参考 [FnNAS renas](https://github.com/ophub/fnnas/blob/main/renas)。

| 路径 | 职责 |
| --- | --- |
| [`sources/fnos-arm64.lock`](sources/fnos-arm64.lock) | 官方镜像来源、版本、校验值，采用 TOML |
| [`boards/xiaomi-umi.yml`](boards/xiaomi-umi.yml) | Umi 目标板信息及待确认的 RootFS 文件系统 |
| [`fnos-files/`](fnos-files/README.md) | Common → Qualcomm SM8250 → Xiaomi Umi 的 RootFS 文件层 |
| [`kernel/`](kernel/) | Linux 6.18.60 配置、Umi DTB 源码、ABL 补丁、CSOT 配置和 Debian 打包工具 |
| [`tools/legacy/boot/abl-android-v2/`](boot/abl-android-v2/) | ABL 基线、overlay、v2 打包工具、诊断和测试 |
| [`scripts/`](scripts/) | 获取、审计、提取、覆盖、构建、组装和校验 |

旧版 Debian/Armbian 构建和发布材料集中在 [tools/legacy/](../tools/legacy/)，供复现和硬件回归。
CSOT 构建配置位于 `kernel/config/csot/`，固定源码快照位于 `sources/`。

GitHub Actions 的 `ci.yml` 运行仓库检查，`build-kernel.yml` 构建 Umi 内核并可手动选择复现 Debian，
`build-fnos.yml` 使用官方底包锁和仓库密钥 `FNOS_SIGNED_URL` 执行审计与提取。
复合 Action [`.github/actions/prepare-fnos-base`](../.github/actions/prepare-fnos-base/action.yml) 可在安装了 libguestfs 的 Linux runner 上审计本地镜像，并可选导出 RootFS tar。

## PR 0 · 官方底包审计

候选输入选用飞牛 ARM 下载页的 **1.2.1011 Radxa ROCK 5B 原始磁盘镜像**。
锁文件记录了原始地址和官网公布的 MD5。官网确认下载后会签发临时链接，原始地址返回 HTTP 403。
拿到归档后应先对照官网 MD5，再计算并记录归档的 SHA-256。当前 SHA-256 待填。
[飞牛 ARM 下载页](https://fnnas.com/download-arm)

从仓库根目录运行。Ubuntu 24.04 使用系统 Python 及 libguestfs；Linux 需要有可读的本机内核镜像供 libguestfs 启动。

```bash
sudo apt-get install -y python3-guestfs btrfs-progs curl
FNOS_PYTHON=/usr/bin/python3 ./refnos inspect /path/to/fnos-arm64.img.gz
FNOS_PYTHON=/usr/bin/python3 ./refnos inspect /path/to/fnos-arm64.img \
    --sha256 <该文件的SHA-256> --output out/base-image-report-checked
```

当锁文件完成后，可将官网签发的链接交给 `./refnos download out/base/fnos-arm64.img.gz --url "$FNOS_SIGNED_URL"` 下载并校验锁定归档。
`--sha256` 应使用实际传入文件的校验值，压缩归档和解压后的磁盘镜像各有自己的 SHA-256。

审计支持 raw 磁盘镜像及 gzip/xz 压缩归档。libguestfs 使用只读磁盘、只读挂载和独立的
虚拟设备读取 GPT/MBR 及文件系统，不运行镜像内的程序。扫描 ext4/Btrfs 中同时包含
`/usr/trim` 和 dpkg 状态库的系统根；Btrfs 优先检查默认子卷，随后查找其他子卷。
有多个候选时可用 `--root-partition N` 及 `--root-subvolume ID` 选择。
压缩镜像需要能容纳解压后完整镜像的临时空间，可通过 `TMPDIR` 指定目录。

默认输出到新的 `out/base-image-report/`，包含 `image-info.json`、`partitions.json`、
`packages.txt`、`services.txt`、`modules.txt` 和 `rootfs-report.txt`。
该报告用于确认底包布局、Debian 版本、ARM64 ELF、内核模块、系统服务和容量。

## 原生镜像构建步骤

| 脚本 | 输入与产物 |
| --- | --- |
| `download-base.sh` | 使用锁文件验证官网下载的归档 |
| `inspect-base.sh` | 生成分区、子卷、软件包和服务审计报告 |
| `extract-rootfs.sh` | 只读导出已校验的 ARM64 RootFS 为 tar，保留数字 UID/GID、ACL 和扩展属性 |
| `apply-files.sh` | 将 Common → SM8250 → Xiaomi Umi 依序复制到独立的 RootFS 工作目录 |
| `build-kernel.sh` | 从固定内核与已校验的 Umi Boot 基线构建内核、模块和 DTB，入口为 `rekernel-umi` |
| `build-initramfs.sh` | 用同版本模块和指定 RootFS 中的固件重建 Umi 基线 initramfs |
| `build-boot.sh` | 打包内核、DTB、initramfs 和 RootFS UUID，生成 Android Boot Header v2 镜像 |
| `assemble-rootfs.sh` | 使用明确指定的 ext4 或 Btrfs 格式，将已准备的工作树组装为新镜像 |
| `verify-release.sh` | 核对 Boot 版本、RootFS UUID、内核、DTB 和 initramfs 模块版本 |

```bash
FNOS_PYTHON=/usr/bin/python3 ./refnos extract /path/to/fnos-arm64.img.gz out/rootfs.tar \
    --sha256 <该文件的SHA-256>
```

归档导出记录所选根目录的文件树。Btrfs 快照关系和独立子卷布局需要依据审计报告另行处理。
目标 UFS 文件系统等取得官方底包后验证子卷、快照和系统升级依赖，再确定
板级文件的安装策略和正式组装流程。现有 Umi initramfs 的早期用户态继承 Debian 发布基线。
原生 fnOS 首启和升级仍须实包及真机验收。

复现现有 Debian 镜像见[基线构建指南](../tools/legacy/rootfs-build/BUILD.md)。
