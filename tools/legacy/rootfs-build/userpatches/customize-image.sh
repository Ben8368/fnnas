#!/bin/bash
#
# Armbian 镜像定制脚本 —— 小米10 (umi) 无头服务器
#
# 由 armbian/build 在「目标 rootfs 的 chroot 内」执行，紧挨着镜像打包之前。
# 所以这里的命令直接作用于目标系统，不需要 chroot_sdcard 前缀。
#
# 参数：$1=RELEASE  $2=LINUXFAMILY  $3=BOARD  $4=BUILD_DESKTOP
#
set -e

RELEASE="${1:-}"
LINUXFAMILY="${2:-}"
BOARD="${3:-}"
BUILD_DESKTOP="${4:-no}"

echo "### umi 镜像定制：RELEASE=${RELEASE} BOARD=${BOARD} DESKTOP=${BUILD_DESKTOP}"

# ---------------------------------------------------------------------------
# 1. 首启和管理所需工具
# ---------------------------------------------------------------------------
# 安装失败不能交付缺少登录工具的镜像。
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y --no-install-recommends openssh-server sudo

# ---------------------------------------------------------------------------
# 2. 确保是纯命令行（万一被构建成了桌面版）
# ---------------------------------------------------------------------------
systemctl set-default multi-user.target 2>/dev/null || true
systemctl disable gdm3 lightdm sddm 2>/dev/null || true
echo "### 默认启动目标 = multi-user.target（纯命令行）"

# ---------------------------------------------------------------------------
# 3. 服务器常用工具
#
# ⚠️ apt 的批量 install 是"全有或全无"：只要有一个包名在当前 release 里不存在，
#    整批都不会装（E: Unable to locate package xxx）。
#    所以这里先批量试，失败就退化成逐个装 + 跳过缺失的。
#    （真实踩过的坑：Debian 里没有 libva-utils 这个包名，叫 vainfo）
# ---------------------------------------------------------------------------
PKGS="htop tmux ncdu tree usbutils pciutils i2c-tools v4l-utils \
device-tree-compiler ethtool lm-sensors curl wget git rsync \
parted gdisk e2fsprogs iw rfkill ffmpeg vainfo gpiod"

if apt-get install -y --no-install-recommends $PKGS; then
	echo "### 工具批量安装成功"
else
	echo "### 批量安装失败（多半是某个包名在该 release 不存在），改为逐个安装"
	for pkg in $PKGS; do
		if apt-get install -y --no-install-recommends "$pkg" >/dev/null 2>&1; then
			echo "###   OK   $pkg"
		else
			echo "###   跳过 $pkg（该 release 没有这个包）"
		fi
	done
fi

# ---------------------------------------------------------------------------
# 4. 安装首启认证策略及 overlay 工具
#     （overlay 目录在 chroot 里是 /tmp/overlay）
# ---------------------------------------------------------------------------
bash /tmp/overlay/usr/local/lib/umi/configure-login-image

install_overlay_file() {
	local rel="$1" mode="${2:-644}"
	if [ -f "/tmp/overlay/$rel" ]; then
		install -Dm"$mode" "/tmp/overlay/$rel" "/$rel"
		echo "###   装 /$rel"
	else
		echo "###   警告：overlay 里缺 $rel"
	fi
}

# WiFi 连接向导
install_overlay_file "root/wifi-connect.sh" 755

install_overlay_file "etc/udev/rules.d/80-umi-csot-backlight.rules" 644

# 充电上限
install_overlay_file "usr/local/bin/battery-charge-limit" 755

# systemd 单元
install_overlay_file "etc/systemd/system/battery-charge-limit.service" 644

# 充电上限的默认阈值（用户可改这个文件）
if [ ! -f /etc/default/battery-charge-limit ]; then
	mkdir -p /etc/default
	cat > /etc/default/battery-charge-limit <<'EOF'
# 充电上限配置 —— 改完执行 systemctl restart battery-charge-limit
# 电量到 UPPER% 停止充电，掉到 LOWER% 再恢复
UPPER=70
LOWER=65
# 轮询间隔（秒），仅用户态兜底路径用到
INTERVAL=30
EOF
	echo "###   写 /etc/default/battery-charge-limit（UPPER=70 LOWER=65）"
fi

# ---------------------------------------------------------------------------
# 5. 关掉休眠/挂起（服务器不该睡）
# ---------------------------------------------------------------------------
systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target 2>/dev/null || true

# ---------------------------------------------------------------------------
# 5b. 启用充电上限
#     battery-charge-limit  电量到 70% 停止充电，掉到 65% 恢复
# ---------------------------------------------------------------------------
systemctl enable battery-charge-limit.service 2>/dev/null \
	&& echo "### 已启用 battery-charge-limit.service（限充 70%）" \
	|| echo "### 警告：battery-charge-limit.service 启用失败"

# ---------------------------------------------------------------------------
# 6. 放一份上手说明
# ---------------------------------------------------------------------------
cat > /root/README-mi10.md <<'EOF'
# 小米10 (umi) Linux 服务器 — 快速上手

## 登录
- 没有默认密码，也没有 `armbian` 备用账号。首次通过 USB 串口（115200 8N1）按回车，设置本机独立的 root 密码，再在串口登录。
- USB 同时提供 NCM 网卡。SSH 默认关闭；先在串口创建普通管理员并安装 SSH 公钥，再生成本机 SSH 主机密钥并启用 SSH。
- SSH 只允许普通账号使用公钥；串口保留密码登录用于恢复。

## 连 WiFi —— 直接用向导
    sudo wifi-connect

会扫描并列出 WiFi（编号 1、2、3…），选一个、输密码，自动用 DHCP 连上。
配置写进 `/etc/wpa_supplicant/wpa_supplicant-wlan0.conf`，重启后自动重连。

> 注意：这套镜像用的是 **systemd-networkd + wpa_supplicant**，
> **没有 NetworkManager，所以没有 nmcli**。手工连的话：
>
>     wpa_cli -i wlan0 status
>     networkctl status wlan0

## CSOT 屏幕

使用内核 DRM 面板驱动和 Linux 标准背光接口。

    cat /sys/class/backlight/ae94000.dsi.0/{brightness,max_brightness}

## 充电上限 —— 默认停在 75%
开机自动跑 `battery-charge-limit.service`：
**电量到 75% 就停止充电，掉到 70% 再恢复**（中间区间维持现状，避免反复通断）。

    systemctl status battery-charge-limit --no-pager
    journalctl -u battery-charge-limit -n 30 --no-pager   # 看日志

改阈值：编辑 `/etc/default/battery-charge-limit`（UPPER / LOWER），然后

    sudo systemctl restart battery-charge-limit

想临时恢复充满：

    sudo systemctl stop battery-charge-limit
    echo 1 | sudo tee /sys/class/power_supply/*/charging_enabled

> 实现上优先用内核原生的 `charge_control_end_threshold`；没有的话退化成
> 轮询 `charging_enabled` 通断充电（Armbian 的 qcom_pm8150b_charger 驱动提供该属性）。
> 如果日志说两个属性都找不到，把 `ls /sys/class/power_supply/*/` 发我。

## USB 接口
- **接键鼠 / U 盘**：插 USB-C 转 A 母口的 OTG 转接头 → 自动切 host 模式
- **接电脑**：自动切 device 模式，出现 NCM 网卡和 ACM 串口

查看当前角色：

    cat /sys/class/usb_role/*/role 2>/dev/null
    dmesg | grep -iE "dwc3|typec"

## 视频编解码 (Venus)
内核已启用 `VIDEO_QCOM_VENUS`，模块 `venus-dec/venus-enc/venus-core` 已装，
固件 `qcom/sm8250/xiaomi/elish/venus.mbn` 已就位。

    dmesg | grep -i venus
    v4l2-ctl --list-devices

硬解 H.264：

    ffmpeg -hwaccel v4l2m2m -c:v h264_v4l2m2m -i in.mp4 -f null -

硬解 H.265：

    ffmpeg -hwaccel v4l2m2m -c:v hevc_v4l2m2m -i in.mp4 -f null -

> Jellyfin 官方不支持 V4L2，要用 VA-API 桥接（`venus-vaapi-driver`）；
> 且该驱动目前只实现了 H.264，H.265 仍需软解。

## 验收命令
    # GPU（应出现 renderD128）
    ls -l /dev/dri/
    dmesg | grep -iE "adreno|msm|zap"

    # 电池
    ls /sys/class/power_supply/
    cat /sys/class/power_supply/*/capacity 2>/dev/null

    # WiFi
    lspci -nn | grep -i qualcomm
    dmesg | grep -i ath11k

    # Docker
    docker version

## 注意
设备树里没有充电策略驱动，无法限充。长期插电建议放通风阴凉处，
定期检查后盖是否鼓起。
EOF

echo "### 已写入 /root/README-mi10.md"
echo "### umi 镜像定制完成"
