# FnNAS 许可与出处声明

仓库根目录的 [GPL-2.0 许可证](LICENSE) 沿用 `ophub/fnnas`。小米 10 适配自有代码沿用原有的 GPL-2.0-only 授权，并引用同一份 GPL v2 正文。带有独立 SPDX 标识或随附许可的文件适用各自的许可条款。

---

## 一、版权与来源

### 1.1 FnNAS 上游与下游适配

- FnNAS 由 OPHUB 及贡献者维护。`Ben8368/fnnas` 是 `ophub/fnnas` 的 Fork，`main` 用于同步上游，Qualcomm SM8250 / 小米 10 适配在开发分支维护。[FnNAS 上游](https://github.com/ophub/fnnas)
- 小米 10 适配导入自 `Ben8368/fnos-xiaomi-umi`。该适配项目的版权声明为 `Copyright (C) 2026 Ben8368`。[适配源码](https://github.com/Ben8368/fnos-xiaomi-umi)

### 1.2 起点源码来源

- Xiaomi UMI 的硬件适配与引导基线来自 `misaka-link/umi-linux` 的 `v2026-09-27`，保留其 `Copyright (C) 2026 misaka-link` 声明及 GPL v2 条款。[基线发布](https://github.com/misaka-link/umi-linux/releases/tag/v2026-09-27)

### 1.3 核心适配架构来源

- Qualcomm SM8250 的项目结构、平台接入方式及构建入口直接对齐 FnNAS 上游 [`ophub/fnnas`](https://github.com/ophub/fnnas)，并在本 Fork 的 `make-fnnas`、`renas` 和 `rekernel` 中实现小米 10（UMI）板级适配。

### 1.4 内核与硬件参考仓库

- [`colorgarden/umi-mainline`](https://github.com/colorgarden/umi-mainline)：小米 10（`umi`）主线内核驱动（面板、背光、ST FTS 触摸、充电/热敏电阻等）与设备树参考。
- [`LineageOS/android_kernel_xiaomi_sm8250`](https://github.com/LineageOS/android_kernel_xiaomi_sm8250)：小米 SM8250 平台 Android 下游内核源码与硬件引脚/电源/外设定义参考。

### 1.5 上游 Linux 内核基线

- UMI 支持从 Linux Stable 选择 `6.18.y` 源码。锁定的历史复现版本为 `6.18.60`，提交 `f45ed76d6791cf72ff1265ee93511175bbbc2f18`。[内核版本规则](make-fnnas/qualcomm/sm8250/README.md#umi-内核选版)

---

## 二、按内容分类与许可

| 内容 | 仓库位置 | 出处 | 许可 |
|---|---|---|---|
| FnNAS 原有构建与文档 | `renas`、`rekernel`、`action.yml`、`make-fnnas/` 内原有平台文件、`README.md`、`README.cn.md` | `ophub/fnnas`，保留原有版权与贡献者声明 | [GPL-2.0](LICENSE) |
| 内核目标与 DTS/DTB | `tools/legacy/dtb/`、`make-fnnas/qualcomm/sm8250/boot/abl-android-v2/baseline/`、`tools/legacy/boot-build/dts.patch`、`make-fnnas/qualcomm/sm8250/kernel/` | Linux 主线 / Armbian `sm8250` family，经 `misaka-link/umi-linux` 基线修改 | **GPL-2.0** |
| Armbian SM8250 6.18 补丁快照 | `make-fnnas/qualcomm/sm8250/sources/armbian-34f4924/patch/kernel/archive/sm8250-6.18/` | Armbian build commit `34f492406aed63269c88a5e0063cbac6a029e6a3` | [随附 GPL v2 文本](make-fnnas/qualcomm/sm8250/sources/armbian-34f4924/LICENSE) |
| `qca6390-pmu` / `pwrseq_qcom_wcn` 配方 | `tools/legacy/boot-build/dts.patch` 中相关改动 | 上游 `sm8250-xiaomi-elish` 补丁（Jianhua Lu）、Linux 主线 `drivers/power/sequencing/` | **GPL-2.0** |
| CSOT 原生显示适配（面板、DCS 时序与背光） | `make-fnnas/qualcomm/sm8250/kernel/config/csot/`、内核 `panel-xiaomi-umi-csot.c` | 参考 [`colorgarden/umi-mainline`](https://github.com/colorgarden/umi-mainline) 的小米 10 主线显示适配，本项目针对 CSOT 配置继续适配 | **GPL-2.0** |
| 原生显示构建与验证源码 | `make-fnnas/qualcomm/sm8250/sources/` 下的 `display-60/`、`display-90/`、`board-lab/` | 固定源码快照，保留逐文件 SPDX 标识和第三方版权声明 | AGPL-3.0-only、GPL-2.0-only、BSD-3-Clause 等，以随附声明为准。[AGPL-3.0 全文](make-fnnas/qualcomm/sm8250/sources/LICENSES-AGPL-3.0.txt) |
| UMI 板级移植与构建脚本 | `make-fnnas/qualcomm/sm8250/` 中的构建脚本、`tools/legacy/rootfs-build/`、`tools/legacy/boot-build/build-boot.sh` 和 `tools/*.sh` | 源自 `misaka-link/umi-linux` 基线，由适配项目继续维护 | GPL v2，逐文件声明优先 |
| 系统服务与脚本 | `battery-charge-limit`、`umi-venus-enable`、`wifi-connect.sh`、`umi-gpu-maxfreq` 等 | 源自 `misaka-link/umi-linux` 基线并由本项目继续维护 | **GPL-2.0** |
| UMI CI 工作流 | `build-fnos.yml`、`build-kernel.yml`、`ci.yml` | 本项目原创 | **GPL-2.0** |
| UMI 专用文档 | `docs/qualcomm/sm8250/xiaomi-umi/` | 继承 `misaka-link/umi-linux` 的硬件与引导资料，现按 FnNAS 目录维护 | GPL v2 |
| Mesa / Turnip / Freedreno | 镜像内（不在仓库） | freedreno 上游 | MIT 系 |
| QCA6390 固件 | 镜像内（不在仓库） | `kvalo/ath11k-firmware` / linux-firmware | 见其自带许可 |
| Debian / fnOS 用户态组件 | 未来 fnOS 适配镜像内 | Debian 项目 / 飞牛私有云（fnOS）官方 ARM64 底包 | 各自开源许可 / 专有组件许可 |
| 小米厂商二进制（`dtbo.img`、`a650_zap.mbn` 等） | 使用者从对应来源取得 | 厂商固件 | 适用各自的分发条款 |

---

## 三、合规与再分发约束

1. UMI 源码不附带 `dtbo.img`、`a650_zap.mbn` 等厂商固件。按各自条款从对应来源取得。
2. **遵守 GPL-2.0**：Linux 内核及设备树衍生修改在再分发时须遵守 GPL-2.0，附上对应的设备树/内核源码或补丁。
3. **fnOS 官方用户态说明**：飞牛系统（fnOS）为基于 Debian 的 NAS 系统，其专有组件（如 `/usr/trim` 相关服务）版权归飞牛官方所有；本项目仅提供硬件适配层、内核/DTB 方案与适配脚本，不宣称拥有 fnOS 官方软件著作权。
4. **商标声明**：Xiaomi、Mi 10、Qualcomm、Snapdragon、Adreno、fnOS（飞牛私有云）等为其各自所有者的注册商标或商标；本项目为社区开源适配项目，与上述厂商无隶属或背书关系。
5. **显示适配出处**：本项目的 CSOT 显示适配参考 [`colorgarden/umi-mainline`](https://github.com/colorgarden/umi-mainline) 项目中的小米 10 主线显示实现，并针对本项目的 CSOT 面板配置进行适配与调试。相关内核代码按 GPL-2.0 发布。

---

## 四、给再分发者的检查清单

- [ ] 保留根目录的 [LICENSE](LICENSE)、本文件及随附件提供的版权和许可声明
- [ ] 不要将 `dtbo.img` / `a650_zap.mbn` 等厂商专有二进制打进源码仓库或非授权发行包
- [ ] 修改了 DTS / 内核源码或补丁时，一并提供对应源码或 patch
- [ ] 在 Release 说明中记录镜像的实际首启账号策略，以及保留基带分区和原厂 DTBO 的要求
- [ ] 发布镜像时附上对应的 SHA-256 校验清单和校验方法
- [ ] 确保发布镜像中不含个人信息（WiFi 凭据、SSH 私钥、设备序列号等）
