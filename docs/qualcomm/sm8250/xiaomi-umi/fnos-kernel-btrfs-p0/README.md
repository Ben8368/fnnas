# 飞牛内核适配摸底：Umi Btrfs P0 RAM 验收

## 范围

为后续适配 fnOS 用户空间，记录小米 10（umi）release 内核的 Btrfs 支持与实机验收。当前方案将 Btrfs 及其所需 crypto/RAID 依赖直接编入 Linux 6.18.60 内核，保留 ext4 rootfs，不写 Android 分区。

核心参考项目：

- [ophub/fnnas](https://github.com/ophub/fnnas)

## 验收结论

| 验收层级 | 结果 | 说明 |
| --- | --- | --- |
| 完整构建与静态检查 | 通过 | Linux `f45ed76d6791cf72ff1265ee93511175bbbc2f18`、CSOT 90 Hz kernel/rootfs 成功构建；核对 IKCONFIG、内置配置、模块树、initramfs、Boot 与 RootFS |
| RAM 真机验收 | 通过 | `fastboot boot` 临时启动；xxhash64、内置 Btrfs 注册、RAM loop 挂载、读写、ZSTD extent、子卷和只读快照均通过 |
| 全内核 RAM 硬件探针 | 部分通过 | 内核、CSOT DSI 90 Hz、背光和 USB ACM 通过；GPU 固件加载失败，PM8150B 充电器延迟 probe，见下文 |
| fnOS 用户空间验收 | 尚未进行 | 未启动 fnOS 用户空间；继续保留当前 ext4 rootfs 方案 |

待测内核 release：`6.18.60-csot90-sm8250`。测试镜像使用已验证的 CSOT 90Hz kernel 与 DTB；静态比较确认两段与 release boot.img 字节一致。设备返回 Android 后面板属性仍为 CSOT `0B` / DTBO `11`。

本轮只用 `fastboot boot`，没有执行 `fastboot flash`。RAM 脚本把内置 160 MiB Btrfs 测试卷复制到 `/run` tmpfs，再挂载 `/dev/loop0`；没有挂载或写入手机实际存储分区。

2026-11-26 用同次完整 release 构建产物完成 RAM 启动验证。USB ACM 记录了 `RESULT: PASS all RAM-only Btrfs P0 checks`；测试镜像随后自动重启。此前 2026-11-25 的模块模式验收仍作为历史记录保留在旧日志中。

可用 [build-btrfs-p0-ramdisk.sh](../../../../../make-fnnas/qualcomm/sm8250/boot/abl-android-v2/tools/build-btrfs-p0-ramdisk.sh) 从同次 release 构建生成 RAM 测试镜像。脚本检查内核配置中的 Btrfs/crypto/RAID 依赖均为 built-in、模块树与 initramfs 不包含 `btrfs.ko`，再从目标 rootfs 收集测试工具及共享库，生成并只读检查 160 MiB 测试卷并重打包 boot。生成的镜像只能用 `fastboot boot`。

## 配置与模块依赖

实际构建配置见[基线 kernel.config](../../../../../make-fnnas/qualcomm/sm8250/kernel/config/umi-6.18.60-base.config)和[CSOT 90 Hz 完整配置](artifacts/umi-6.18.60-csot90-sm8250-btrfs-builtin.config)。基线配置 SHA-256 为 `a29b9bcfc0d70b4d48e75806fe26ba9766801ffd4915544d8fce483513bdac7e`；构建会从固定 base boot 重新提取 IKCONFIG 并逐字节核对。最终配置关键项：

```text
CONFIG_BTRFS_FS=y
CONFIG_BTRFS_FS_POSIX_ACL=y
CONFIG_BLK_DEV_LOOP=y
CONFIG_ZSTD_COMPRESS=y
CONFIG_ZSTD_DECOMPRESS=y
CONFIG_CRYPTO_XXHASH=y
CONFIG_CRYPTO_BLAKE2B=y
CONFIG_CRYPTO_SHA256=y
CONFIG_CRYPTO_CRC32C=y
CONFIG_XOR_BLOCKS=y
CONFIG_RAID6_PQ=y
# CONFIG_MODVERSIONS is not set
```

构建会强制检查 Btrfs、xxhash、blake2b、XOR、RAID6 和 loop 为 `=y`，且 kernel 输出、release module tree 和 initramfs 都没有 `btrfs.ko`。因此更换用户空间后，Btrfs 文件系统和压缩所需内核支持仍然可用。

## RAM 真机结果

当前 built-in 验收的[USB ACM 日志](artifacts/usb-acm-btrfs-builtin.log)：

```text
PASS: xxhash64 crypto implementation is available
PASS: Btrfs is registered as a built-in filesystem
PASS: RAM image attached loop=/dev/loop0
PASS: Btrfs mounted with compress=zstd:1
PASS: Btrfs read/write and sync
PASS: on-disk extent metadata confirms ZSTD compression
PASS: subvolume create and read-only snapshot verified
RESULT: PASS all RAM-only Btrfs P0 checks
```

静态证据包括 [Btrfs 只读检查](artifacts/static-btrfs-check.log)、[boot 分段与 cmdline 核对](artifacts/static-verify.log)、[完整模块依赖](artifacts/btrfs.modprobe-deps.txt)、[`modules.dep`](artifacts/modules.dep)、[`modules.softdep`](artifacts/modules.softdep)、[initramfs 文件清单](artifacts/rebuilt-with-btrfs.list) 和 [SHA256 清单](artifacts/SHA256SUMS.txt)。

此前模块模式的配置差异、模块依赖和 USB 日志是历史验收材料；当前 built-in 镜像及配置哈希见[内置模式 SHA256 清单](artifacts/SHA256SUMS-btrfs-builtin.txt)。

boot.img 与测试卷本身作为本地/发布产物，不提交 Git；SHA256 与重建/测试脚本一并提交。pstore 原始日志未纳入公开 PR，因为日志包含设备启动标识；无设备序列号的完整验收步骤日志已由 USB ACM 保存。

## 全内核 RAM 启动与硬件探针

2026-11-26 从完整 CSOT 90 Hz release boot 生成 [RAM 硬件探针镜像](../../../../../make-fnnas/qualcomm/sm8250/boot/abl-android-v2/tools/make-ram-probe.py)，通过 `fastboot boot` 启动。镜像到达 Linux 6.18.60 诊断 PID 1，运行约 35 秒后按探针设计重启；Android 随后恢复且 `sys.boot_completed=1`。没有刷写分区、挂载或写入手机实际存储。

| 项目 | 结果 | 证据 / 限制 |
| --- | --- | --- |
| 内核启动与诊断 PID 1 | 通过 | `Linux 6.18.60-csot90-sm8250`；proc、sysfs 均成功挂载 |
| CSOT 显示与背光 | 通过，显示时序未作物理测量 | DSI connected/enabled，DRM 报告 `1080x2340@90`；背光设为并读回 `1500/2047`。驱动日志说明 90 Hz DCS 已编程，不等同于实测扫描频率 |
| USB gadget | 通过 | `dwc3`、QCOM DWC3 glue、USB PHY 已绑定；ACM 已配置，串口日志完整收集 |
| GPU | 未通过本探针 | Adreno 报告 `a650_zap.mbn` 初始化失败并出现 GMU OOB timeout。复核镜像确认 initramfs 已含同名固件，其内容与 release rootfs 中的版本不同 |
| PM8150B 充电器 | 未通过 | 设备树已声明 `usb_in_v_div_16` 通道。历史镜像把 ADC5 编为模块且未打包进 initramfs，导致充电器延迟探测 |
| SoundWire / GPI / I2C | 未通过或未完成 | 记录到 SoundWire interface clock 缺失、GPI event channel 分配失败及 I2C RX DMA channel 不可用；音频及相关外设不作通过判定 |
| 完整 Linux 用户空间 | 未测试 | 正式 root UUID 在设备块设备中不存在；探针只运行 RAM PID 1，因此 Docker、Wi-Fi、视频服务等 rootfs 功能不在本次验收范围 |

去重后的 [USB ACM 探针日志](artifacts/ram-kernel-probe-2026-11-26.usb-acm.log)记录内核版本、显示、背光、USB 状态、根 UUID 检查及 charger deferred probe；[ramoops 错误摘录](artifacts/ram-kernel-probe-2026-11-26-kernel-errors.txt)记录 GPU、充电器、SoundWire 和 I2C/GPI DMA 的内核错误。RAM 探针镜像本身不提交 Git；镜像与日志哈希见[清单](artifacts/SHA256SUMS-ram-kernel-probe.txt)。本次探针验证了内核可临时 RAM 启动，但不代表整套用户空间和所有硬件功能通过。

### 修复后复测（2026-11-26）

重编的 90 Hz 发布版把 ADC5 编入内核，并从经校验的 rootfs 打包小米签名的 ZAP 固件。真机经 DTBO index 11 预检和 `fastboot boot` 启动后，MSM 渲染节点返回芯片 ID `0x06050002`。PM8150B 报告 `online=1`、`status=Charging`，输入电压和电流分别约为 4.76 V 和 297 mA。显示复测通过，DRM 仍报告 `1080x2340@90`，背光读回 `1500/2047`，USB ACM 成功配置。

发布 DTB 停用了依赖 ADSP 的音频节点，以及仅连接 FTS 触屏的 I2C 控制器。音频和触屏仍待移植验收。本轮再次确认内置 Btrfs 注册，挂载验收沿用此前独立 RAM 测试。探针在约 35 秒后自动退出，Android 和 ADB 恢复，未刷写分区。

配套 ext4 镜像通过文件系统检查和 UUID 一致性校验。手机当前没有匹配的根盘，完整 Debian、Wi-Fi、Docker、GPU 渲染负载和限充策略仍待验收。

## Kernel 大小与 ABL 加载边界

Umi 的历史 RAM boot 尺寸探测在 LineageOS 23.2 官方 Android v2 boot 组件上，以官方配置、ramdisk、DTB 和加载地址为基线，仅递增 kernel `Image`。`128,958,488` 字节（`122.984 MiB`）的 kernel 已通过 `fastboot boot`，并进入 Android、完成启动且读到本地构建标记。该结果证明这一组组件可承载该尺寸；它不是 kernel 最大值，也不能直接外推到本 PR 的 Linux 6.18.60 内核、initramfs 或 ABL 条件。更大尺寸尚未形成成功边界，历史上的 ABL `Load Error` 原因也未确定。

`128 MiB` 是打包工具对完整 boot 镜像的限制，不是 kernel `Image` 的独立上限。当前 built-in Btrfs release boot 已按完整段布局打包，并在 Umi 上通过 `fastboot boot` 实测；该验证只覆盖本次 90 Hz kernel、ramdisk、DTB 与 ABL 组合。

## 后续事项

- 启动 fnOS 用户空间，单独验收 btrfs-progs、启动挂载、服务编排和升级流程。
- 将固定 Linux 源归档与两份大体积基线输入保存到项目所有者可控的 Release/对象存储；主仓库保留精确 SHA、配置与可复现脚本。
