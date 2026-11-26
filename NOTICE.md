# NOTICE —— 许可与出处声明

> 小米 10 适配代码以 **GPL-2.0-only** 许可发布（见 [`LICENSE.umi`](LICENSE.umi)）。
> 以下明确声明本项目的起点源码来源、后续参考仓库、各组成模块的许可归属，以及再分发时的合规要求。

---

## 一、版权与来源

### 1.1 本项目

```
fnos-xiaomi-umi —— 小米 10（umi / SM8250）原生飞牛系统（fnOS）适配项目
Copyright (C) 2026 Ben8368
https://github.com/Ben8368/fnos-xiaomi-umi
许可：GPL-2.0-only
```

### 1.2 起点源码来源

- 本仓库初始源码与硬件适配基线来自 [`misaka-link/umi-linux`](https://github.com/misaka-link/umi-linux)（`v2026-09-27` 开源版本，Copyright © 2026 misaka-link，GPL-2.0）。
- 本项目将其作为独立起点继续开发，**不跟随原仓库后续更新，也不与原仓库保持 Git 上游绑定关系**。

### 1.3 核心适配架构参考

- [`oneder32/fnos-k20pro-raphael`](https://github.com/oneder32/fnos-k20pro-raphael)：参考其在高通骁龙手机（Redmi K20 Pro / SM8150）上原生适配 **飞牛系统（fnOS ARM64）** 的引导链组织、initramfs 手机启用层与根文件系统适配方案。
- 参考 [ophub/fnnas](https://github.com/ophub/fnnas) 的 ARM64 底包准备、三层文件覆盖和构建目录。

### 1.4 内核与硬件参考仓库

- [`colorgarden/umi-mainline`](https://github.com/colorgarden/umi-mainline)：小米 10（`umi`）主线内核驱动（面板、背光、ST FTS 触摸、充电/热敏电阻等）与设备树参考。
- [`LineageOS/android_kernel_xiaomi_sm8250`](https://github.com/LineageOS/android_kernel_xiaomi_sm8250)：小米 SM8250 平台 Android 下游内核源码与硬件引脚/电源/外设定义参考。

### 1.5 上游 Linux 内核基线

- 目标内核基于 **Linux 6.18 LTS**（`https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git`，目标版本 `6.18.60`，Commit SHA：`f45ed76d6791cf72ff1265ee93511175bbbc2f18`）。

---

## 二、按内容分类与许可

| 内容 | 仓库位置 | 出处 | 许可 |
|---|---|---|---|
| 内核目标与 DTS/DTB | `tools/legacy/dtb/`、`make-fnos/boot/abl-android-v2/baseline/`、`tools/legacy/boot-build/dts.patch`、`make-fnos/kernel/` | Linux 主线 / Armbian `sm8250` family，经 `misaka-link/umi-linux` 基线修改 | **GPL-2.0** |
| Armbian SM8250 6.18 补丁快照 | `make-fnos/sources/armbian-34f4924/patch/kernel/archive/sm8250-6.18/` | Armbian build commit `34f492406aed63269c88a5e0063cbac6a029e6a3`；原目录及 `LICENSE` 一并保留 | **GPL-2.0** |
| `qca6390-pmu` / `pwrseq_qcom_wcn` 配方 | `tools/legacy/boot-build/dts.patch` 中相关改动 | 上游 `sm8250-xiaomi-elish` 补丁（Jianhua Lu）、Linux 主线 `drivers/power/sequencing/` | **GPL-2.0** |
| CSOT 原生显示适配（面板、DCS 时序与背光） | `make-fnos/kernel/config/csot/`、内核 `panel-xiaomi-umi-csot.c` | 参考 [`colorgarden/umi-mainline`](https://github.com/colorgarden/umi-mainline) 的小米 10 主线显示适配，本项目针对 CSOT 配置继续适配 | **GPL-2.0** |
| 原生显示构建与验证源码 | `make-fnos/sources/display-60/`、`display-90/`、`board-lab/` | 本项目维护的固定源码快照；保留逐文件 SPDX 标识和第三方版权声明 | **混合许可**：AGPL-3.0-only、GPL-2.0-only、BSD-3-Clause 等，以文件标记为准；AGPL 文本见 `make-fnos/sources/LICENSES-AGPL-3.0.txt` |
| 板级移植与构建脚本 | `make-fnos/`、`tools/legacy/rootfs-build/`、`make-fnos/boot/abl-android-v2/tools/*.py`、`tools/legacy/boot-build/build-boot.sh`、`tools/*.sh` | 源自 `misaka-link/umi-linux` 基线并由本项目继续维护 | **GPL-2.0** |
| 系统服务与脚本 | `battery-charge-limit`、`umi-venus-enable`、`wifi-connect.sh`、`umi-gpu-maxfreq` 等 | 源自 `misaka-link/umi-linux` 基线并由本项目继续维护 | **GPL-2.0** |
| UMI CI 工作流 | `build-fnos.yml`、`build-kernel.yml`、`ci.yml` | 本项目原创 | **GPL-2.0** |
| 文档 | `README.md`、`docs/*`、`NOTICE.md` | 在 `misaka-link/umi-linux` 文档基础上针对 `fnos-xiaomi-umi` 重拟更新 | **GPL-2.0** |
| Mesa / Turnip / Freedreno | 镜像内（不在仓库） | freedreno 上游 | MIT 系 |
| QCA6390 固件 | 镜像内（不在仓库） | `kvalo/ath11k-firmware` / linux-firmware | 见其自带许可 |
| Debian / fnOS 用户态组件 | 未来 fnOS 适配镜像内 | Debian 项目 / 飞牛私有云（fnOS）官方 ARM64 底包 | 各自开源许可 / 专有组件许可 |
| **小米厂商二进制**（`dtbo.img`、`a650_zap.mbn` 等） | **不在本仓库内** | 小米官方 | **未包含 / 不可再分发** |

---

## 三、合规与再分发约束

1. **本仓库不含任何厂商专有镜像**：`dtbo.img`、`a650_zap.mbn` 等厂商固件需由使用者自行从官方底包中提取或保留，切勿提交至仓库。
2. **遵守 GPL-2.0**：Linux 内核及设备树衍生修改在再分发时须遵守 GPL-2.0，附上对应的设备树/内核源码或补丁。
3. **fnOS 官方用户态说明**：飞牛系统（fnOS）为基于 Debian 的 NAS 系统，其专有组件（如 `/usr/trim` 相关服务）版权归飞牛官方所有；本项目仅提供硬件适配层、内核/DTB 方案与适配脚本，不宣称拥有 fnOS 官方软件著作权。
4. **商标声明**：Xiaomi、Mi 10、Qualcomm、Snapdragon、Adreno、fnOS（飞牛私有云）等为其各自所有者的注册商标或商标；本项目为社区开源适配项目，与上述厂商无隶属或背书关系。
5. **显示适配出处**：本项目的 CSOT 显示适配参考 [`colorgarden/umi-mainline`](https://github.com/colorgarden/umi-mainline) 项目中的小米 10 主线显示实现，并针对本项目的 CSOT 面板配置进行适配与调试。相关内核代码按 GPL-2.0 发布。

---

## 四、给再分发者的检查清单

- [ ] 保留本文件（`NOTICE.md`）与 `LICENSE`
- [ ] 不要将 `dtbo.img` / `a650_zap.mbn` 等厂商专有二进制打进源码仓库或非授权发行包
- [ ] 修改了 DTS / 内核源码或补丁时，一并提供对应源码或 patch
- [ ] 在 Release 说明中明确标注安全提示（首启修改默认密码、勿擦除基带分区、保留原厂 `dtbo.img`）
- [ ] 发布镜像时同步更新 `SHA256SUMS.txt` 并说明校验方法
- [ ] 确保发布镜像中不含个人信息（WiFi 凭据、SSH 私钥、设备序列号等）
