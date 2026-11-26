# FnNAS 小米 10（UMI）历史 Debian / Armbian 构建

继承自 `misaka-link/umi-linux` 的 `armbian/build` umi 板级配置 + 设备树 + BSP 脚本 + 镜像定制。
**目标内核**：Linux **6.18.60 LTS**（上游 Commit SHA：`f45ed76d6791cf72ff1265ee93511175bbbc2f18`）。
**目标环境**：无桌面、带 Docker、GPU 启用、电池启用、CSOT 原生显示，作为小米 10 原生飞牛系统（fnOS）适配的底层构建基线。

## 原生显示构建

按 [BUILD.md](BUILD.md) 准备已校验的输入和 Linux 工具链。默认 CSOT 60 Hz，`CSOT_REFRESH=90` 生成另一套独立的 Boot 与 RootFS；不构建 SMS 或无头镜像。下面关于旧 Armbian 移植的内容仅作来源记录。

## 目录结构

```
config/boards/xiaomi-umi.conf                     板级配置（family / 内核 / cmdline / BSP 钩子）
../../../make-fnnas/qualcomm/sm8250/kernel/dts/
    sm8250-xiaomi-umi-common.dtsi                 主设备树（已修复，含 USB OTG）
    sm8250-xiaomi-umi-csot.dts                    CSOT 面板变体（本机是这种）
    sm8250-xiaomi-umi-sms.dts                     三星面板变体
packages/bsp/xiaomi-umi/
    zz-update-abl-kernel                          内核升级后重建 ABL boot 镜像
../../../make-fnnas/fnnas-files/different-files/xiaomi-umi/rootfs/
userpatches/
    extensions/umi-usb-host.sh                    打开 USB host 内核选项（关键：USB_ROLE_SWITCH）
    extensions/umi-firstboot.sh                   兼容旧构建参数的空扩展
    customize-image.sh                            chroot 内：安装首启认证策略和常用工具
gen-dts.py                                        从原始设备树生成修复版的脚本
apply-umi-port.sh                                 一键应用到 armbian/build
build-in-wsl.sh                                   WSL 里的一键构建脚本
wsl-setup.md                                      WSL2 环境搭建（磁盘固定在 E:\WSL2）
```

## 镜像默认行为

| 项 | 默认 |
|---|---|
| SSH | 首次开机时关闭，配置普通管理员公钥后手动启用 |
| 账号 | 无默认密码；通过 USB 串口设置 root 密码，按需创建自己的管理员 |
| 桌面 | 无（`multi-user.target`） |
| 屏幕 | CSOT DRM 1080×2340，横屏大字控制台，背光初始设置为 1500/2047 |
| USB 键鼠 | 插 OTG 转接头即用 |
| USB 网卡和串口 | 插电脑出现 NCM 网卡和 ACM 串口 |
| Docker | 已装 |
| 休眠 | 已 mask |

## 本包相对原始版本的修复

原始 umi 支持来自 `Archfx/armbian-build-bpi`（armbian/build 的 fork，官方已移除 umi）。
共 16 项改动，主要有：

1. **GPU**：`&gpu { tatus = "okay"; }` → `status = "okay"`（一个字母的笔误让 Adreno 650 静默禁用）
2. **GPU 固件**：zap shader 路径改为主线通用 `qcom/sm8250/a650_zap.mbn`
3. **电池**：取消 `battery` 节点注释，参数从"平板5 的值"修正为小米10 规格；新增 `&pm8150b_charger` / `&pm8150b_fg`
4. **USB 键鼠**：新增 `&pm8150b_typec` + connector + `&pm8150b_vbus` + dwc3 端点，并打开 `CONFIG_USB_ROLE_SWITCH`
5. **显示**：原生模式使用仓库内固定的 ABL framebuffer、DSI 和 framebuffer 控制台源码
6. **SSH / root**：按 [首次开机步骤](BUILD.md#七首次开机后必做) 通过 USB 串口设密，再按需启用公钥 SSH
7. **板级配置**：改用官方 `sm8250` family（才能吃到 `qcom_fg` / `pm8150b_charger` 补丁），并加 initrd 固件 hook

改动逐条对照见 BUILD.md 第十节。

## 已验证 / 待验证

| 项 | 状态 |
|---|---|
| 设备树语法（花括号平衡、无 `tatus` 残留） | ✅ 已校验（127/127） |
| 依赖的内核补丁（0027/0029/0037/0038）在 6.18 补丁集里存在 | ✅ 已核对 |
| 内核配置 `CONFIG_CHARGER_QCOM_SMB5` / `CONFIG_BATTERY_QCOM_FG` 已是 `y` | ✅ 已核对 |
| `&pm8150b_charger` 写法 | ✅ 照抄补丁 0037 的 oneplus 示例 |
| USB OTG 配置 | ✅ 照抄补丁 0038 的 oneplus 实现 |
| 所有 shell 脚本语法 | ✅ `bash -n` 全过 |
| **`&pm8150b_fg`（PM8150B 内置电量计）** | ⚠️ **待实机验证** —— 没有现成的 Armbian sm8250 设备用过它 |
| **整体能否成功构建并启动** | ⚠️ **未验证** —— 需要跑一次构建 |

**上机第一件事**：在现有 MIUI 上确认电量计型号
```bash
adb shell ls /sys/bus/i2c/devices/
adb shell cat /sys/class/power_supply/*/name
```
如果是外挂芯片（如 `bq27z561`），要改成照 Armbian 补丁 `0022` 的写法挂 i2c 节点。

## 相关文档

- [项目主页](../../../README.umi.md) — 项目主页（能力矩阵 / 启动链 / 做了什么）
- [`../docs/02-使用指南.md`](../../../docs/02-使用指南.md) — 刷完怎么用（WiFi / 串口 / 充电上限 / GPU）
- [`../docs/03-自行构建.md`](../../../docs/03-自行构建.md) — 构建总指南（含 boot 链）
- [BUILD.md](BUILD.md) — 本构建包的完整参数说明与 16 项改动对照
- [wsl-setup.md](wsl-setup.md) — 在 Windows 上用 WSL2 搭构建环境
