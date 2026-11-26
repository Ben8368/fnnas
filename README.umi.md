# FnNAS Qualcomm SM8250 · 小米 10（UMI）

本页记录 FnNAS 对 Qualcomm SM8250 的适配。首个目标设备为小米 10，板级 ID 为 `xiaomi-umi`，手机代号为 `umi`。有关 Amlogic、Allwinner 和 Rockchip 的安装与构建，请参阅 [FnNAS 中文主文档](README.cn.md)。

`Ben8368/fnnas` 的 `main` 跟随 `ophub/fnnas`，UMI 开发位于 `codex/qualcomm-sm8250`。通过 `renas -b xiaomi-umi` 处理镜像，通过 `rekernel -b xiaomi-umi` 查询和编译 Linux `6.18.y`。`locked` 用于复现 `6.18.60`。[FnNAS 许可证](LICENSE) · [源码与版权声明](NOTICE.md)

---

## 项目与源码来源

UMI 适配来自 `Ben8368/fnos-xiaomi-umi`，硬件与引导基线来自 `misaka-link/umi-linux` 的 `v2026-09-27`。适配代码沿用 FnNAS 的目录和构建入口，并保留小米 10 的 ABL v2、DTBO、内核及 initramfs 处理逻辑。[适配来源](https://github.com/Ben8368/fnos-xiaomi-umi) · [硬件基线](https://github.com/misaka-link/umi-linux/releases/tag/v2026-09-27)

### 核心参考项目

| 参考仓库 | 参考方向与用途 |
|---|---|
| [`oneder32/fnos-k20pro-raphael`](https://github.com/oneder32/fnos-k20pro-raphael) | 飞牛系统（fnOS ARM64）在骁龙手机上的整体适配架构：主线内核 + 设备树 + initramfs 手机启用层 + fnOS Debian 用户态与 `/usr/trim` 服务集成（WebUI 端口 `5666`） |
| [`misaka-link/umi-linux`](https://github.com/misaka-link/umi-linux) | **本项目起点基线**：已真机验证的小米 10 Debian 13 引导链（ABL `__symbols__` + `/abl_ovf` 锚点、`qcom,kona` compatible 修复）、QCA6390 WiFi 6、USB NCM/ACM 双通道、Adreno 650 GPU、Venus 硬编解、PM8150B 充电控制与息屏服务 |
| [`colorgarden/umi-mainline`](https://github.com/colorgarden/umi-mainline) | 小米 10（`umi`）主线内核适配参考：DSI 面板显示、背光控制、ST FTS 触摸屏、电池/热敏电阻与设备树改进 |
| [`LineageOS/android_kernel_xiaomi_sm8250`](https://github.com/LineageOS/android_kernel_xiaomi_sm8250) | 小米 SM8250 下游内核与板级硬件定义参考（GPIO、电源域、传感器、面板时序与外设参数核对） |

---

## 原生 fnOS 适配架构

`renas -b xiaomi-umi` 支持官方 ARM64 底包审计和 RootFS 提取。经审查的覆盖文件按 SM8250 平台、小米 10 机型的顺序应用。镜像组装从已准备的 RootFS 出发，使用已发布的 UMI 内核和同版模块生成 ABL v2 Boot 与 RootFS 配套镜像。[构建命令](docs/03-自行构建.md)

当前 Debian 基线使用 ext4。原生 fnOS 的目标文件系统等底包审计和升级兼容性验证后确定。
```
上电 → BootROM / XBL → 小米 ABL（需已解锁 BootLoader）
  │
  ├──→ boot 分区   （Android boot header v2）
  │       ├─ Linux 6.18.y 内核（含 qcom,kona 适配补丁）
  │       ├─ umi DTB（带 __symbols__ 与 /abl_ovf 锚点树，仅 CSOT 原生面板）
  │       └─ initramfs（挂载根分区 + 手机启用层注入：模块 / 固件 / 高通服务）
  │
  ├──→ dtbo 分区   （★ 必须保留小米原厂 dtbo.img，供 ABL 叠加 overlay）
  │
  └──→ UFS userdata 分区（Debian 基线为 ext4）
          └─ Debian 基线或待组装的 fnOS ARM64 根文件系统
                └──→ fnOS 集成后提供 NAS WebUI（端口 5666）
```

### 当前进度与状态区分

- **Debian 复现基线**采用 Linux `6.18.60`，支持 1080×2340 CSOT 60 Hz 和 90 Hz 两种独立构建。两档均有 RAM 启动记录。电池与充电区间控制、WiFi、USB NCM/ACM、GPU、Venus 和 Docker 的验证范围见下文。[真机显示记录](make-fnnas/qualcomm/sm8250/kernel/config/csot/README.md#fnos-ram-boot-on-2026-11-25)
- **Linux `6.18.65` 候选**于 2026-11-26 在 CSOT 60 Hz 设备上进行 RAM 探针测试，确认进入 PID 1、USB ACM 出现及 1080×2340 @ 60 Hz 显示状态。记录属于 RAM 探针验收。[真机无刷写验收](docs/04-真机无刷写验收.md)
- **🧪 可选实验内核（`lab-60` / `lab-90`）**：已适配有线固定 PD、BQ25970 PPS 充电路径及其 30 秒硬件 watchdog 驱动、SN100T NFC（Linux NFC/NCI）。实验 profile 不打包 rootfs，也不属于默认发布镜像；PD/PPS 保护、watchdog 超时恢复和 NFC 仍需在目标 fnOS 系统上分别验收。细节见[实验配置记录](make-fnnas/qualcomm/sm8250/kernel/config/csot/README.md)。
- **fnOS 系统集成**已具备底包审计、RootFS 提取和样本组装入口。官方底包的 SHA-256 尚待补齐，Btrfs 子卷、首次启动、WebUI 和 OTA 仍待真实底包和真机验证。[底包审计与组装](make-fnnas/qualcomm/sm8250/README.md)

---

## 一、基线能力矩阵（现有硬件支持情况）

以下按默认发布配置与可选实验配置分别列出能力和验证状态。除特别标注外，目标系统为 Debian 13 + Linux 6.18.60；这些结果不代表 fnOS 用户态已集成。

### ✅ 已验证可用

| 子系统 | 状态 |
|---|---|
| **CPU / 内存** | 8 核（4×A55 1.80 GHz + 3×A77 2.42 GHz + 1×A77 2.84 GHz）+ LPDDR5。默认 `schedutil`，可切 `performance` |
| **UFS 存储** | 整盘可用，`resize2fs` 后可将 `userdata`（`/dev/sda34`）全部空间提供给系统 |
| **WiFi（QCA6390 / ath11k）** | **WiFi 6（802.11ax，2.4/5 GHz）**，`wlan0`，支持修改 MAC |
| **USB 有线网卡（NCM）** | 插上电脑即出网卡，**Windows 免驱**（自带 `usbncm.inf`），设备侧 `172.16.42.1`，实测 **426 Mbps** |
| **USB 串口控制台（ACM）** | 同一根 USB 线提供串口（115200）。当前镜像在串口首次设置 root 密码，之后凭密码登录。`v2026-09-27` 基线镜像支持免密串口。 |
| **GPU（Adreno 650）** | `/dev/dri/renderD128` + `card1`；**Vulkan 1.3**（Turnip）、**OpenGL 4.6 Core**、**GLES 3.2**；支持 devfreq 多档调频 |
| **视频编解码（Venus）** | `/dev/video0`（解码）+ `/dev/video1`（编码）；**H.264 / HEVC 硬解、H.264 硬编**（NV12）；适合 NAS 媒体转码场景 |
| **电池 / 充电保护** | PM8150B 电量计 + SMB2 充电器；电量可读、**充电区间滞回可控**（默认充到 70% 停、掉到 65% 复充，适合长插电 NAS） |
| **屏幕显示（CSOT）** | 原生 DRM/DSI 显示，1080×2340 @ **60 Hz 或 90 Hz**（构建时选择）；两档均已在 CSOT 真机 Fastboot RAM 启动，看到横屏控制台。显示适配参考 [`colorgarden/umi-mainline`](https://github.com/colorgarden/umi-mainline) |
| **屏幕息屏** | 原生显示版屏蔽历史 GPIO `panel-off` 服务，使用 `consoleblank=60` 关闭控制台显示，避免旧服务抢占面板 |
| **Docker / 容器** | 内核选项完备（含 AppArmor 进 `CONFIG_LSM`） |
| **异常兜底** | `umi-bcb-early` 写 `misc` 分区，异常重启/崩溃自动落 TWRP；开机自动采集诊断快照到 `/data/diag/` |

### 🧪 可选实验内核（非默认发布配置）

| 能力 | 状态 |
|---|---|
| **有线固定 PD / BQ25970 PPS** | 实验 DTS 与内核驱动已集成；目标机的 PD/PPS 保护、温度与恢复行为尚待验收 |
| **充电泵硬件 watchdog** | PPS 驱动使用 BQ25970 的 30 秒硬件计时器；主机回归覆盖超时锁存读取需返回 `-ETIME`。目标机上的超时、停止和恢复尚未验证；不是系统 watchdog 或 SMB5 bark 中断 |
| **NFC（SN100T）** | 实验配置接入 I²C1 与 Linux NFC/NCI；读取实体 MIFARE 卡的记录来自参考设备，目标机上的完整 NFC 使用流程尚待验收 |

### ❌ 当前未启用 / 已知限制

| 能力 | 原因 |
|---|---|
| **蜂窝基带（通话 / 短信 / 流量）** | 未启用，**基带分区严禁擦除** |
| **触摸屏** | 当前显示构建未接入触摸驱动 |
| **摄像头 / 指纹 / 红外 / 音频** | 当前未启用 |
| **NFC** | 仅集成在可选实验内核，默认发布配置未启用 |
| **USB Host（外接硬盘 / 键鼠）** | USB 口默认被用作 **gadget**（网卡 + 串口）。内核已开启 `CONFIG_USB_ROLE_SWITCH`，用于 NAS 外接存储时需配合切换 Host 角色（或禁用 gadget 服务） |
| **休眠 / 深度待机** | 主动 mask `sleep/suspend` 与关闭 WiFi 省电，保障 NAS/服务器 7×24 在线 |
| **GPU 超频档过热保护** | 基线超频至 800/900 MHz 时无 GPU cooling device 降频保护；NAS 长跑建议保持原厂 587 MHz 或做好散热 |

---

## 二、三个必须知道的“引导硬约束”

1. **DTB 必须带 `__symbols__` 与 `/abl_ovf` 锚点树**
   小米 ABL 会把原厂 `dtbo` 中的 overlay 叠加到 base DTB 上，依赖符号表定位。基础 DTB 内包含 **152 个 `/abl_ovf` 占位锚点**（按原厂 dtbo fixups 列表生成）。缺失会导致 **设备秒进 fastboot**，无法进入内核。`tools/legacy/boot-build/build-boot.sh` 会自动校验这一点。
2. **内核 Image 中的 `qcom,kona` 等长补丁**
   ABL 会将根节点 compatible 覆写为 `qcom,kona*`，而内核 `ubwc_config.c` 原表仅登记了 `qcom,sm8250`，会导致匹配失败（`EINVAL`）进而影响 mdss / GPU 初始化。基线通过在内核中将 `"qcom,sm8250"` 等长替换为 `"qcom,kona"`（或直接在源码修改 `ubwc_config.c`）来解决，这也是后续切到 `6.18.60` 源码编译时必须保留的修复。
3. **`dtbo` 分区必须保留原厂镜像**
   `dtbo.img` 提供 ABL 所需的板级 overlay。本仓库**不包含**任何厂商专有二进制，需从你自己的官方底包中保留或刷回。

---

## 三、⚠️ 安全与禁忌（刷机前必读）

### 绝对不要擦除的分区

**只写 `boot` 和 `userdata`（或规划的 Linux/fnOS 目标分区）。** 以下分区一旦擦除，**基带 / IMEI / WiFi 出厂 MAC 会永久丢失且无法恢复**：

```text
modemst1  modemst2  fsg  fsc  persist  mdm1m9kefs1  mdm1m9kefs2  mdm1m9kefs3
```

- 刷机工具请使用 **MiFlash2020 自带的新版 fastboot**（避免旧版 fastboot 的 sparse 截断问题）。
- **不要读取 `/sys/bus/nvmem/devices/qfprom0/nvmem`（efuse）** 或其他已断电外设的 MMIO，否则可能触发异步 SError 导致 Kernel panic。

### 现有 Debian 基线镜像的安全提醒

- 若你当前使用的是来自起点基线的 `v2026-09-27` 测试镜像，镜像内 `root`（`umi10linux`）和 `armbian`（`armbian`，具备 `sudo` + `docker` 权限）默认密码为公开值，且 USB 串口支持免密 root 登录。**联网前务必执行**：
  ```bash
  passwd
  passwd -l armbian
  rm -f /etc/ssh/ssh_host_* && ssh-keygen -A && systemctl restart ssh
  bash /root/wifi-connect.sh
  ```

---

## 四、目录结构与构建链

```text
fnnas/
├── .github/actions/prepare-fnos-base/action.yml
├── .github/workflows/{build-fnos.yml,build-kernel.yml,ci.yml}
├── make-fnnas/
│   ├── boards/xiaomi-umi.yml
│   ├── fnnas-files/
│   │   ├── platform-files/qualcomm/sm8250/
│   │   └── different-files/xiaomi-umi/
│   └── qualcomm/sm8250/
│       ├── kernel/{config,patches/sm8250-6.18,dts,packaging}/
│       ├── boot/abl-android-v2/{baseline,overlays,tools,tests}/
│       ├── scripts/
│       └── sources/fnos-arm64.lock
├── renas
├── rekernel
├── refnos
├── rekernel-umi
├── tools/                            # tools/legacy/ 存放旧版复现入口
├── docs/
├── out/                              # 本地报告和工作产物
├── LICENSE
├── NOTICE.md
└── README.umi.md
```

[原生 fnOS 构建目录与审计说明](make-fnnas/qualcomm/sm8250/README.md)记录了底包来源、层级及组装边界。
用 `./renas -b xiaomi-umi --help` 查看镜像操作，用 `./rekernel -b xiaomi-umi query` 查询可编译的 Linux 源码版本。
现有 Debian 60/90 Hz 镜像按[基线构建指南](tools/legacy/rootfs-build/BUILD.md)复现，
2026-09-27 Boot 复现命令见[历史 Boot 构建记录](tools/legacy/boot-build/BUILD.md)。

---

## 五、文档索引

| 文档 | 内容 |
|---|---|
| [`docs/01-快速开始.md`](docs/01-快速开始.md) | 刷机前检查与备份、刷 tools/legacy/boot/dtbo/rootfs、首启安全加固与验收清单 |
| [`docs/02-使用指南.md`](docs/02-使用指南.md) | USB 串口/网卡、WiFi 配置、充电上限、GPU 频率、Venus 硬编解与故障排查 |
| [`docs/03-自行构建.md`](docs/03-自行构建.md) | 统一入口、6.18.y 选版、镜像组装和历史构建 |
| [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md) | 本地检查、提交规范与 PR 验收记录 |
| [`docs/04-发布与下载.md`](docs/04-发布与下载.md) | Release 产物清单、拆分、校验与发布流程 |
| [`docs/RELEASE-NOTES.md`](docs/RELEASE-NOTES.md) | GitHub Release 正文模板 |
| [`NOTICE.md`](NOTICE.md) | 版权声明、源码出处、参考项目与 GPL-2.0 合规声明 |

---

## 六、下载说明

FnNAS Fork 已提供 CSOT Debian 基线的复现流程。UMI 发布内核包和原生 fnOS 成品状态见 [发布与下载](docs/04-发布与下载.md)。

- 仓库内大体积二进制镜像（`tools/legacy/boot/*.img`、`tools/legacy/rootfs/*.tar.gz`）不进 Git，后续发布使用 [FnNAS Fork 的 Releases](https://github.com/Ben8368/fnnas/releases)。导入前的产物见 [UMI 来源仓库的 Releases](https://github.com/Ben8368/fnos-xiaomi-umi/releases)
- 如需先体验本项目所继承的纯 Debian 13 基线成品镜像（`v2026-09-27`），可参见原基线发布页 [`misaka-link/umi-linux` Releases](https://github.com/misaka-link/umi-linux/releases/tag/v2026-09-27) 及 [`tools/legacy/boot/README.md`](tools/legacy/boot/README.md)、[`tools/legacy/rootfs/README.md`](tools/legacy/rootfs/README.md)。
