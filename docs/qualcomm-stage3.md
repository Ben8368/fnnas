# Qualcomm SM8250 第三阶段：运行与验收

## CI 与发布职责

- `main` 保持为默认分支，只与 `ophub/fnnas/main` 快进同步。分支专用的工作流不放到 `main`。GitHub 要求 `workflow_dispatch` 文件先存在于默认分支，因此 Umi 工作流运行入口为 `codex/qualcomm-sm8250` 和 `pr/qualcomm-*` 的 `push`。要对同一 SHA 重试，使用 `gh run rerun RUN_ID -R Ben8368/fnnas`，并记录新的 Attempt。`pr/qualcomm-*` 能跑 CI，不是授权发布分支。
- `Build Umi kernel` 默认 `release`（CSOT 60 Hz）及 `locked`（6.18.60）。仓库维护者可在下一次相关文件推送前设置 Actions Variables `UMI_KERNEL_PROFILE`、`UMI_KERNEL_VERSION`；它们不是发布授权。`auto` 解析 kernel.org 上最高正式 6.18.y 标签；也支持具体版本。每次核对解析到的实际提交和 `kernel-source.tsv`，不要只记 `auto`。补丁必须零 fuzz，或者反向应用检查证明已存在；另外只允许名称及摘要均匹配的有理由的跳过。未知冲突停止，不能被目录范围内的自动跳过掩盖。Armbian `0021` 只调整 Makefile 上下文，未更改驱动内容。
- 构建 job 只有 `contents: read`。删除旧的 `publish-umi-kernel.yml`；不再修改共用的 `kernel_fnnas` Release。新标签形如 `umi-kernel-6.18.60-csot60-<40位源码SHA>`，直指源码提交。发布只接受 `Ben8368/fnnas:codex/qualcomm-sm8250` 上 workflow 路径、指定 full SHA、Run ID、Attempt、profile 均吻合且成功的 push 构建；发布权限在本机维护者凭据中。`--publish` 前默认只审查，不写远端。

## 内核真机验收与提升

1. 下载 `umi-<profile>-<RunID>-<Attempt>` Actions artifact 并保存摘要。不用历史探针或相似版本替代本次构建。运行 `bash make-fnnas/qualcomm/sm8250/scripts/acceptance-probe.sh DONOR_BOOT KERNEL_PACKAGE NEW_PROBE.img`。产生的镜像仅供 RAM 启动；核对该探针的 DTB 与**设备当前** DTBO 的 preflight 再运行，参见 [无刷写验收](04-真机无刷写验收.md)。设备没有恢复 Android、无法取得当次 USB 报告、或 overlay 校验失败，都不能提升。探针 PID 1 不挂载 Android 数据分区。
2. 收集未经合成的当次 USB 报告、面板/DTBO 核对结果、Probe SHA-256，以及恢复 Android 的 `sys.boot_completed=1`。将实际观测到的恢复结果记为 `Android sys.boot_completed=1` 行；报告应含 `UMI_PROBE: PID1 kernel=...`、`UMI_PROBE: artifact_sha256=...` 和 `UMI_PROBE_REPORT_END`。去除设备序列号等个人标识，再对最终报告计算 SHA-256。
3. 验收 JSON 包含 `source_commit`、`linux_commit`、`profile`、整数 `run_id`、整数 `run_attempt`、`package_sha256`、`evidence_sha256`、`operator`、`tested_at`，以及 `device: "xiaomi-umi"`、`scope: "kernel"`、`method: "fastboot-boot"`、`result: "pass"`。维护者需人工审查报告；工具核对身份与字节，不能独立证明物理观测真伪。

```bash
python3 make-fnnas/qualcomm/sm8250/scripts/kernel-release.py promote \
  --source "$FULL_SHA" --profile release --run-id "$RUN_ID" --run-attempt "$ATTEMPT" \
  --acceptance acceptance.json --evidence device-evidence.log
```

仅在核对测试和许可后，加 `--publish`。工具先建指向准确 SHA 的轻量标签，上传草稿，然后用 GitHub API 核对上传 SHA-256 和标签，最后才公开；失败保留草稿供人工检查，不会覆盖既有标签/资产。公开 Release 的 JSON 说明及实际验收日志是正式镜像选版的依据。没有合格 Release 时镜像构建应当失败，不允许将 CI 包或 Debian 基线当作替代。

## 官方底包和原生镜像

上游 `build-fnnas-image.yml` 支持明确 URL；没指定 URL 时从 `ophub/fnnas` 的 `fnnas_base_image` Release 中按平台名称和资产更新时间选择 `.img.xz`。这里重用其公开 Release 和平台候选，不复制发布工作流、也不自动跟随资产变化。`sources/fnos-upstream.lock` 固定到真实下载并校验的 `rockchip_1253`，记录 URL、大小及 SHA-256；`sources/fnos-arm64.lock` 仍只是待独立下载核验的官网签名 URL 选项，不能用于原生构建。libguestfs 只读检查，保留数字 UID/GID、ACL、xattrs 并可在同一次只读审计中导出。

```bash
bash renas -b xiaomi-umi download /path/to/fnos.img.xz
sudo env FNOS_PYTHON=/usr/bin/python3 LIBGUESTFS_BACKEND=direct LIBGUESTFS_BACKEND_SETTINGS=force_tcg \
  bash renas -b xiaomi-umi inspect /path/to/fnos.img.xz --sha256 locked \
    --output /path/to/audit --rootfs-archive /path/to/rootfs.tar
sudo bash renas -b xiaomi-umi -k 6.18.60 -a false native \
  /path/to/fnos.img.xz /path/to/umi-boot-donor.img /path/to/firmware.tar "$FIRMWARE_SHA256" \
  /path/to/new-output --refresh 60
```

`native` 的底包位置可为 `-`（自动获取锁定包），输入需为可重读文件，工作目录用原生 Linux 文件系统。要求 `python3-guestfs`、可用的 appliance 内核、`btrfs-progs`、`rsync`、`mkbootimg`、`cpio`、`kmod`、`initramfs-tools-core`、`uuid-runtime`。固件 tar 仅放用户有权取得的 `qcom/`、`ath11k/` 下的常规文件，至少包含 `qcom/sm8250/a650_zap.mbn`、`qcom/a650_gmu.bin` 和 `qcom/a650_sqe.fw`；这些不是全量外设验收清单。固件 tar 整体摘要及每文件摘要都会保留。`action.yml` 的 `fnnas_board: xiaomi-umi` 使用同一入口，新增 `umi_boot_donor`、`umi_firmware_tar`、`umi_firmware_sha256`、`umi_refresh`。其他三个平台仍走原有 action 步骤。

不复制 donor `/boot` 分区，不套用上游的 U-Boot/分区扩容逻辑。该 donor 是 Btrfs 顶层 ID 5，无独立子卷；新镜像只有一个 Btrfs 文件系统，UUID 同步到 ABL 命令行、initramfs 及 RootFS fstab。只接受这个已审计的布局；将来有不同子卷或挂载点的底包需重新审核。清理旧模块、旧头文件和 boot 残余，阻断 Debian 例行自动升级和旧平台自动扩容，APT pin 禁止旧内核包升级，保留真实 dpkg 元数据；**这些不是禁用 fnOS 专有 OTA 的证明**。`trim_main` 等仍存在，原生 fnOS 首启、实际数据盘、OTA 的平台依赖须另验，不允许尝试生产升级。

## 拆分和许可边界

PR 主题按顺序：`pr/qualcomm-routing`（通用参数/Action 路由）、`pr/qualcomm-base-audit`（只读底包解析与审计）、`pr/qualcomm-sm8250`（板级文件、内核和 ABL），每个自干净的 `upstream/main` 或已接受前置 PR 起步。Fork CI、发布门禁及历史验证日志留在开发仓库，不作为通用上游功能。本次提交按功能分开；不把整个开发分支用作上游 PR。签名 URL、专有 fnOS 用户态、DTBO、固件以及历史 Debian 成品均不得混入上游源码 PR。

Armbian 补丁保留原始作者和随附 GPL 文本；对本地适配单独记录。MiSeed 快照含 GPL-2.0-only 驱动与独立 AGPL-3.0-only 工具/救援程序；在 PR 中拆分、逐文件校验拷贝及生成内容，不把 AGPL-only C 并入 GPL-2.0-only 内核。当前 `apply_display_port.py` 是独立构建工具，不能据此推断其生成内容或整份快照都可重许可。最终发布内核前需要对应源码/配置和完整许可归属检查；底包与 GPU/无线固件另按厂商条款处理。参见 [NOTICE](../NOTICE.md)。
