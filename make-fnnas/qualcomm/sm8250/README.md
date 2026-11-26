# FnNAS Qualcomm SM8250 构建

使用 `renas -b xiaomi-umi` 处理镜像，使用 `rekernel -b xiaomi-umi` 选择并编译内核。本目录提供 Qualcomm SM8250 的 ABL v2、内核、底包审计和组装实现。操作示例见 [UMI 构建指南](../../../docs/03-自行构建.md)。

| 路径 | 职责 |
| --- | --- |
| [`sources/fnos-arm64.lock`](sources/fnos-arm64.lock) | 官方镜像来源、版本、校验值，采用 TOML |
| [`boards/xiaomi-umi.yml`](../../boards/xiaomi-umi.yml) | Umi 目标板信息及待确认的 RootFS 文件系统 |
| [`fnnas-files/`](docs/rootfs-overlays.md) | Qualcomm SM8250 和 Xiaomi Umi 的 RootFS 文件层 |
| [`kernel/`](kernel/) | Linux 6.18.y 版本选择、Umi DTB 源码、ABL 补丁、CSOT 配置和 Debian 打包工具 |
| [`boot/abl-android-v2/`](boot/abl-android-v2/) | ABL 基线、overlay、v2 打包工具、诊断和测试 |
| [`scripts/`](scripts/) | 获取、审计、提取、覆盖、构建、组装和校验 |

旧版 Debian/Armbian 构建和发布材料集中在 [tools/legacy/](../../../tools/legacy/)，供复现和硬件回归。
CSOT 构建配置位于 `kernel/config/csot/`，固定源码快照位于 `sources/`。

GitHub Actions 的 `ci.yml` 运行仓库检查，`build-kernel.yml` 构建 Umi 内核并可手动选择复现 Debian，
`build-fnos.yml` 使用官方底包锁和仓库密钥 `FNOS_SIGNED_URL` 执行审计与提取。
复合 Action [`.github/actions/prepare-fnos-base`](../../../.github/actions/prepare-fnos-base/action.yml) 可在安装了 libguestfs 的 Linux runner 上审计本地镜像，并可选导出 RootFS tar。

## Umi 内核选版

`Build Umi kernel` 和本地 `rekernel -b xiaomi-umi` 默认查询 Linux Stable 最新的 `6.18.y` 正式标签。
可选择 `locked` 复现 `6.18.60`，也可填写具体的 `6.18.x`。构建记录实际版本和源码提交，
并用 Umi 配置和 DTB 检查验证候选版本。

构建新版本时保留 Linux Stable 的 DSI 和 FastRPC 驱动。Armbian 补丁已被合入时跳过，
仅与上游驱动改动冲突时保留上游实现并记录跳过的补丁。Umi 专用适配或设备树出现冲突时构建会失败，
供确认上游改动是否已覆盖板级需求。

```bash
./rekernel -b xiaomi-umi query
./rekernel -b xiaomi-umi /path/to/donor-boot.img /path/to/new-kernel-work
```

`release`、`csot-60`、`csot-90` 构建会生成含 Image、DTB 和同版模块的候选附件。
需要准备真机测试用的 Boot 和 RAM probe 时，可在构建中启用 `with_debian_baseline`。
`Publish verified Umi kernel` 目前仅接受来自默认分支的成功构建。镜像端从 `kernel_fnnas` 标签读取按版本和刷新率发布的内核包。默认发布仓库的状态与工作流限制见 [发布与下载](../../../docs/04-发布与下载.md)。

镜像侧默认取 Release 中对应刷新率的最新已发布内核。用 `--version 6.18.x` 可指定已发布的版本，
用 `--repo OWNER/REPO` 可指定其他发布仓库。在发布首个对应刷新率的内核包之前，查询会报出缺失信息。

```bash
./renas -b xiaomi-umi -k 6.18.y -a true kernel query --refresh 90
./renas -b xiaomi-umi kernel fetch out/umi-kernel --refresh 90
./renas -b xiaomi-umi -k 6.18.60 -a false boot /path/to/donor-boot.img /path/to/prepared-rootfs "$ROOT_UUID" out/umi-boot --refresh 90
```

`renas -b xiaomi-umi boot` 在工作目录的 `boot/` 生成 Android v2 Boot 镜像，`kernel/lib/modules/` 含
同版模块，用于组装配套的 RootFS。构建 RootFS 镜像时使用相同的 `ROOT_UUID`。
原有的 `refnos` 和 `rekernel-umi` 命令仍可使用。

## PR 0 · 官方底包审计

候选输入选用飞牛 ARM 下载页的 **1.2.1011 Radxa ROCK 5B 原始磁盘镜像**。
锁文件记录了原始地址和官网公布的 MD5。官网确认下载后会签发临时链接，原始地址返回 HTTP 403。
拿到归档后应先对照官网 MD5，再计算并记录归档的 SHA-256。当前 SHA-256 待填。
[飞牛 ARM 下载页](https://fnnas.com/download-arm)

从仓库根目录运行。Ubuntu 24.04 使用系统 Python 及 libguestfs；Linux 需要有可读的本机内核镜像供 libguestfs 启动。

```bash
sudo apt-get install -y python3-guestfs btrfs-progs curl
FNOS_PYTHON=/usr/bin/python3 ./renas -b xiaomi-umi inspect /path/to/fnos-arm64.img.gz --sha256 "$ARCHIVE_SHA256"
FNOS_PYTHON=/usr/bin/python3 ./renas -b xiaomi-umi inspect /path/to/fnos-arm64.img \
    --sha256 "$DISK_SHA256" --output out/base-image-report-checked
```

当锁文件完成后，可将官网签发的链接交给 `./renas -b xiaomi-umi download out/base/fnos-arm64.img.gz --url "$FNOS_SIGNED_URL"` 下载并校验锁定归档。
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
| `apply-files.sh` | 由 `renas -b xiaomi-umi overlay` 将 SM8250 和 Xiaomi Umi 文件依序复制到独立的 RootFS 工作目录 |
| `build-kernel.sh` | 以选定的 Linux Stable 版本和已校验的 Umi Boot 基线构建内核、模块和 DTB |
| `build-initramfs.sh` | 用同版本模块和指定 RootFS 中的固件重建 Umi 基线 initramfs |
| `build-boot.sh` | 打包内核、DTB、initramfs 和 RootFS UUID，生成 Android Boot Header v2 镜像 |
| `assemble-rootfs.sh` | 使用明确指定的 ext4 或 Btrfs 格式，将已准备的工作树组装为新镜像 |
| `verify-release.sh` | 核对 Boot 版本、RootFS UUID、内核、DTB 和 initramfs 模块版本 |

```bash
FNOS_PYTHON=/usr/bin/python3 ./renas -b xiaomi-umi extract /path/to/fnos-arm64.img.gz out/rootfs.tar \
    --sha256 <该文件的SHA-256>
```

准备好 RootFS、板级固件和对应 UUID 的挂载配置后，可组装配套的启动镜像和文件系统镜像。
构建复制暂存目录，装入与 Boot 相同版本的模块，并校验 UUID、内核、DTB 和 initramfs。

```bash
sudo ./renas -b xiaomi-umi -k 6.18.y -a true build \
    /path/to/donor-boot.img /path/to/prepared-rootfs btrfs "$ROOT_UUID" out/umi-image --refresh 90
```

产物为 `boot.img`、`rootfs.img` 和 `SHA256SUMS`。按需先审查板级覆盖文件，再运行 `overlay`。
Btrfs 组装生成单个文件系统，官方子卷、默认子卷和 OTA 布局仍待实包验证。

归档导出记录所选根目录的文件树。Btrfs 快照关系和独立子卷布局需要依据审计报告另行处理。
目标 UFS 文件系统等取得官方底包后验证子卷、快照和系统升级依赖，再确定
板级文件的安装策略和正式组装流程。现有 Umi initramfs 的早期用户态继承 Debian 发布基线。
原生 fnOS 首启和升级仍须实包及真机验收。

复现现有 Debian 镜像见[基线构建指南](../../../tools/legacy/rootfs-build/BUILD.md)。
