#!/usr/bin/env bash
# check-rootfs-integrity.sh —— 校验 rootfs.img 的文件系统完整性与校验值
#
# 用法: OUT=<镜像目录> bash check-rootfs-integrity.sh
#       （OUT 默认取当前目录；镜像名可用 IMG 指定）
set -euo pipefail

OUT="${OUT:-$PWD}"
IMG="${IMG:-$OUT/rootfs-umi-csot-${CSOT_REFRESH:-60}hz-6.18.60.img}"

[ -f "$IMG" ] || { echo "找不到 rootfs 镜像: $IMG"; echo "请用 IMG=<路径> 或 OUT=<目录> 指定"; exit 1; }

echo "=== 1. 文件系统完整性（只读检查，不修改）==="
e2fsck -fn "$IMG"
echo "e2fsck 通过"

echo
echo "=== 2. 校验配套 boot 与 rootfs 的 SHA-256 ==="
(cd "$OUT"; sha256sum -c SHA256SUMS.txt)

echo
echo "=== 3. 确认关键文件确实在新镜像里 ==="
MNT=$(mktemp -d)
cleanup() {
    if mountpoint -q "$MNT"; then umount "$MNT" || return 1; fi
    rmdir "$MNT"
}
trap cleanup EXIT
mount -o loop,ro,noload "$IMG" "$MNT"
ls -l "$MNT/usr/local/bin/battery-charge-limit" \
      "$MNT/etc/udev/rules.d/80-umi-csot-backlight.rules" \
      "$MNT/root/wifi-connect.sh"
echo "--- battery-charge-limit 是否含新版 decide() ---"
grep -c '^decide()' "$MNT/usr/local/bin/battery-charge-limit"
echo "--- 自启链接 ---"
ls -l "$MNT/etc/systemd/system/multi-user.target.wants/" | grep 'battery-charge-limit'
