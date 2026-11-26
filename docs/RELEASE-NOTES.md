# fnos-xiaomi-umi Release 正文模板 —— 小米 10 原生飞牛系统（fnOS）

> 用于 GitHub Release 的正文（`gh release create --notes-file docs/RELEASE-NOTES.md`）。
> 仓库：<https://github.com/Ben8368/fnnas>　｜　许可：GPL-2.0-only
> 源码基线声明：硬件与引导链基线源自 [`misaka-link/umi-linux`](https://github.com/misaka-link/umi-linux)（独立起点，不跟随上游更新）；fnOS 适配架构参考 [`oneder32/fnos-k20pro-raphael`](https://github.com/oneder32/fnos-k20pro-raphael)。

---

## Xiaomi Mi 10（umi / SM8250）原生飞牛系统（fnOS）适配

当前小米 10（`umi`）CSOT 镜像使用 **Debian 13 ARM64 用户态和 Linux 6.18.60 LTS 内核**，直接运行在手机上。fnOS 专有用户态与 WebUI 尚未集成。

### 附件（发版前替换为实际产物与 SHA256）

| 附件 | 大小 | sha256 |
|---|---|---|
| `<boot 镜像名>.img` | — | `<待填>` |
| 根文件系统（当前构建为 `.img`，旧基线为 `.tar.gz`） | — | `<待填>` |
| `SHA256SUMS.txt` | — | 全量清单，`sha256sum -c` 自检 |

### 核心硬件能力（继承并扩展自基线）

- **继承的硬件能力**包括 WiFi 6（QCA6390）、USB 有线网卡（NCM，Windows 免驱）与 USB 串口控制台、Adreno 650 GPU（Vulkan 1.3 / OpenGL 4.6 / GLES 3.2）、Venus 视频硬编解、PM8150B 电量计与充电区间控制。
- **CSOT 原生显示**提供独立的 60 Hz 和 90 Hz 配置。两档均有横屏控制台的 Fastboot RAM 启动记录。见[真机显示记录](https://github.com/Ben8368/fnos-xiaomi-umi/blob/d5bc9fbf25ed2cffd0f0b5d499e02112eef931dd/rootfs-build/csot-lab/README.md#fnos-ram-boot-on-2026-11-25)。

### ⚠️ 刷机前必读

1. 确认面板为 **CSOT**、BootLoader 已解锁，并使用同次构建配套的 boot 与 ext4 rootfs 镜像。
2. **必须保留原厂 `dtbo.img`**：`fastboot flash dtbo <你底包里的>images/dtbo.img`，不能换、不能空。
3. **绝不碰基带分区**：`modemst1/2`、`fsg`、`fsc`、`persist`、`mdm1m9kefs*`。
4. 继承的 `v2026-09-27` 基线使用 `*.tar.gz` 根文件系统包，需要在 TWRP 中解包。当前 CSOT 构建生成 ext4 `*.img`。

### ⚠️ 首启必做

1. 当前 CSOT 镜像的 root 初始锁定，SSH 默认禁用。用 USB 串口连接设备（`115200 8N1`，关闭流控），按提示设置本机 root 密码，再用该密码登录串口。
2. 如需 SSH，在串口创建普通管理员并安装电脑的 SSH 公钥，再生成本机 SSH 主机密钥、校验配置、解除屏蔽并启用 `ssh.service`。具体命令见[首次开机步骤](https://github.com/Ben8368/fnos-xiaomi-umi/blob/d5bc9fbf25ed2cffd0f0b5d499e02112eef931dd/rootfs-build/BUILD.md#七首次开机后必做)。
3. 登录后按首启指南扩容根文件系统，需要无线网络时运行 `bash /root/wifi-connect.sh`。

使用继承的 `v2026-09-27` 基线镜像时，请按[旧基线的账号加固步骤](https://github.com/Ben8368/fnos-xiaomi-umi/blob/main/docs/01-快速开始.md#31-先说清楚这个镜像里有哪些账号)处理公开默认密码和主机密钥。

### 已知限制

- 原生显示适用于 CSOT 面板，触摸屏尚未接入。
- **无蜂窝基带**（不能打电话 / 短信 / SIM 上网）、无摄像头 / 指纹 / NFC
- USB 默认是 **gadget**（网卡 + 串口），外接存储需配合切换 host 角色
- **不休眠**（sleep/suspend 被主动 mask，保证 NAS 常在线）

项目状态见仓库 `README.md`。旧基线的刷机流程和使用手册见 `docs/01-快速开始.md` 和 `docs/02-使用指南.md`。
