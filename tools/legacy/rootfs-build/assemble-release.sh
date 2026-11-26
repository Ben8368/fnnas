#!/usr/bin/env bash
# Assemble a new boot + ext4 rootfs set from a verified base and rebuilt kernel.
set -euo pipefail
if (($# != 4 && $# != 6)) || ((EUID != 0)); then
    echo "Usage (as root on Linux): $0 MAIN_BOOT_IMG MAIN_ROOTFS_TAR BUILT_KERNEL_WORK NEW_WORK_DIR [ANDROID_DTBO_TABLE DTBO_INDEX]" >&2
    exit 2
fi
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
source "$repo/make-fnnas/qualcomm/sm8250/kernel/source.sh"
boot=$(realpath -e -- "$1")
archive=$(realpath -e -- "$2")
source_dir=$(realpath -e -- "$3")
if [[ -d "$source_dir/csot-out" ]]; then
    echo 'Refusing CSOT lab kernel: release requires the display-only kernel and unchanged power stack.' >&2
    exit 1
fi
work=$(realpath -m -- "$4")
dtbo_check=()
if (($# == 6)); then
    dtbo_check=("$(realpath -e -- "$5")" "$6")
fi
case "$work" in /mnt/*) echo 'Use a native Linux filesystem for rootfs permissions and xattrs.' >&2; exit 2 ;; esac
mkdir -- "$work"
cd -- "$work"
root=$work/rootfs
out=$work/images
p_image=$work/pkg-image
p_dtb=$work/pkg-dtb
export ARCH=arm64 CROSS_COMPILE=${CROSS_COMPILE:-aarch64-linux-gnu-}
export SYSTEMD_OFFLINE=1 DEBIAN_FRONTEND=noninteractive
# The release tarball deliberately omits /dev and /proc. Supply a minimal
# private /dev for target dpkg, account tools and sshd, not the host's devices.
prepare_chroot_dev() {
    install -d "$root/dev" "$root/proc" "$root/sys" "$root/run"
    mount -t tmpfs -o nosuid,mode=0755 tmpfs "$root/dev"
    trap 'umount "$root/dev"' EXIT
    mknod -m 666 "$root/dev/null" c 1 3
    mknod -m 666 "$root/dev/zero" c 1 5
    mknod -m 666 "$root/dev/random" c 1 8
    mknod -m 666 "$root/dev/urandom" c 1 9
    mknod -m 666 "$root/dev/tty" c 5 0
}

printf '%s  %s\n' "$umi_boot_donor_sha256" "$boot" \
    51f4b38d23b71d7d70b7472b3ef95e673c0e984f1f7c489c75305fc4fb2d645f "$archive" | sha256sum -c -
mkdir "$root" "$out"
pigz -dc -- "$archive" | tar -xpf - -C "$root" --numeric-owner --acls --xattrs --xattrs-include='*'
unpack_bootimg --boot_img "$boot" --out main-boot
old=6.18.52-current-sm8250
rate=$(cat "$source_dir/kernel-out/refresh")
[[ $rate == 60 || $rate == 90 ]]
version=$umi_linux_locked_version
commit=$umi_linux_locked_commit
if [[ -f $source_dir/kernel-out/kernel-source.tsv ]]; then
    read -r version commit < "$source_dir/kernel-out/kernel-source.tsv"
fi
[[ $version =~ ^6\.18\.(0|[1-9][0-9]*)$ && $commit =~ ^[0-9a-f]{40}$ ]]
new=$version-csot${rate}-sm8250
test "$(< "$source_dir/kernel-out/include/config/kernel.release")" = "$new"
test "$(git -C "$source_dir/linux" rev-parse HEAD)" = "$commit"
grep -Fxq CONFIG_BTRFS_FS=y "$source_dir/kernel-out/.config"
grep -Fxq CONFIG_BTRFS_FS_POSIX_ACL=y "$source_dir/kernel-out/.config"
grep -Fxq CONFIG_QCOM_SPMI_ADC5=y "$source_dir/kernel-out/.config"

inventory_packages() {
    dpkg-query --admindir="$root/var/lib/dpkg" -W -f='${db:Status-Abbrev}\t${Package}\t${Version}\n' |
        awk -F '\t' '$1 ~ /^[ih]i/ {print $2 "\t" $3}' | LC_ALL=C sort
}
inventory_packages > main-packages.tsv
find "$root/usr/lib/modules/$old/kernel" -type f -name '*.ko' -printf '%f\n' | LC_ALL=C sort -u > main-modules.txt
(cd "$root"; find usr/lib/firmware -type f -print0 | LC_ALL=C sort -z | xargs -0 -r sha256sum) > main-firmware.sha256

make -s -C "$source_dir/linux" O="$source_dir/kernel-out" LOCALVERSION="-csot${rate}-sm8250" \
    -j"${JOBS:-$(nproc)}" INSTALL_MOD_PATH="$p_image" INSTALL_MOD_STRIP=1 modules_install
rm -f "$p_image/lib/modules/$new/build" "$p_image/lib/modules/$new/source"
if find "$p_image/lib/modules/$new" -type f -name 'btrfs.ko*' -print -quit | grep -q .; then
    echo 'The release module tree contains btrfs.ko although Btrfs is configured built-in.' >&2
    exit 1
fi
depmod -b "$p_image" "$new"
while IFS= read -r module; do
    modprobe --dirname "$p_image" --set-version "$new" --ignore-install --show-depends "${module%.ko}" >/dev/null
done < main-modules.txt
printf 'Validated module names against the new tree: '
wc -l < main-modules.txt
kdir=$source_dir/kernel-out
install -Dm644 "$kdir/arch/arm64/boot/Image" "$p_image/boot/vmlinuz-$new"
install -Dm644 "$kdir/System.map" "$p_image/boot/System.map-$new"
install -Dm644 "$kdir/.config" "$p_image/boot/config-$new"
umi_uuid=$(cat /proc/sys/kernel/random/uuid)
export UMI_ROOT_UUID=$umi_uuid
bash "$repo/make-fnnas/qualcomm/sm8250/scripts/build-initramfs.sh" main-boot/ramdisk "$p_image" "$new" "$root" "$work/initramfs" "$work/initrd.img"
bash "$repo/make-fnnas/qualcomm/sm8250/scripts/build-boot.sh" "$boot" "$kdir" "$work/initrd.img" "$umi_uuid" "$work/boot-build" "${dtbo_check[@]}"
install -Dm644 "$work/initrd.img" "$p_image/boot/initrd.img-$new"
ln -s "vmlinuz-$new" "$p_image/boot/Image"
ln -s "boot/vmlinuz-$new" "$p_image/vmlinuz"
ln -s "boot/initrd.img-$new" "$p_image/initrd.img"
install -Dm644 "$kdir/boot-csot.dtb" "$p_dtb/boot/dtb-$new/qcom/sm8250-xiaomi-umi-csot.dtb"
ln -s "dtb-$new" "$p_dtb/boot/dtb"

package() {
    local name=$1 staging=$2 ver
    ver=$(awk -v name="$name" '$1==name {print $2}' main-packages.tsv)
    test -n "$ver"
    bash "$repo/make-fnnas/qualcomm/sm8250/kernel/packaging/build-deb.sh" \
        "$name" "$ver+umi$version.1" "$staging" "$root/tmp/$name.deb"
}
# The baseline archive omits /tmp. Ordinary users and apt need a sticky, writable directory.
install -d -m 1777 "$root/tmp"
prepare_chroot_dev
package linux-image-current-sm8250 "$p_image"
package linux-dtb-current-sm8250 "$p_dtb"
chroot "$root" dpkg -i /tmp/linux-image-current-sm8250.deb /tmp/linux-dtb-current-sm8250.deb
# A stock unattended kernel update would leave a mismatched Android boot partition.
printf '%s hold\n' linux-image-current-sm8250 linux-dtb-current-sm8250 | chroot "$root" dpkg --set-selections
rm -f "$root/tmp/"linux-{image,dtb}-current-sm8250.deb
# Remove generated backups/indices not tracked by the old packages.
rm -rf -- "$root/usr/lib/modules/$old" "$root/boot/dtb-$old"
rm -f -- "$root/boot/initrd.img-$old" "$root/boot/uInitrd-$old" "$root/boot/uInitrd" \
    "$root/vmlinuz.old" "$root/initrd.img.old" "$root/var/lib/initramfs-tools/$old"
install -Dm644 /dev/null "$root/var/lib/initramfs-tools/$new"
sed -i "s/02232280-925f-4edc-984f-24e466d3b6f1/$umi_uuid/g" "$root/etc/fstab"
sed -i "s/^rootdev=UUID=.*/rootdev=UUID=$umi_uuid/" "$root/boot/armbianEnv.txt"

# Preserve legacy userspace, but replace the baseline login/gadget policy with this branch's.
port=$repo/tools/legacy/rootfs-build
overlay=$repo/make-fnnas/fnnas-files/different-files/xiaomi-umi/rootfs
systemctl --root="$root" disable usb-gadget-umi.service
rm -f "$root/etc/systemd/system/usb-gadget-umi.service"
# Redirect the inherited diagnostics and manual recovery unit to the new transport.
sed -i 's/usb-gadget-umi/umi-usb-gadget/g' \
    "$root/etc/systemd/system/boot-collect.service" "$root/etc/systemd/system/umi-put.service" \
    "$root/usr/local/bin/boot-collect.sh"
install -Dm755 "$port/packages/bsp/xiaomi-umi/umi-usb-gadget" "$root/usr/local/sbin/umi-usb-gadget"
install -Dm644 "$port/packages/bsp/xiaomi-umi/umi-usb-gadget.service" "$root/usr/lib/systemd/system/umi-usb-gadget.service"
systemctl --root="$root" enable umi-usb-gadget.service
if chroot "$root" getent passwd armbian >/dev/null; then
    chroot "$root" userdel -r armbian
fi
rm -f -- "$root/root/.ssh/authorized_keys" "$root/root/.ssh/authorized_keys2" "$root/etc/shadow-" \
    "$root/etc/ssh/sshd_config.d/99-umi.conf"
install -d "$root/tmp/overlay"
cp -a "$overlay/." "$root/tmp/overlay/"
chroot "$root" /bin/bash /tmp/overlay/usr/local/lib/umi/configure-login-image
rm -r -- "$root/tmp/overlay"
# Stop donor GPIO reset scripts and framebuffer test patterns from racing DRM.
# Remove any local unit before installing its mask.
for unit in panel-off.service powerkey-screen.service fbtest-red.service fbtest-green.service fbtest-blue.service; do
    if systemctl --root="$root" is-enabled --quiet "$unit" 2>/dev/null; then
        systemctl --root="$root" disable "$unit"
    fi
    rm -f -- "$root/etc/systemd/system/$unit"
    systemctl --root="$root" mask "$unit"
    test "$(systemctl --root="$root" is-enabled "$unit" || :)" = masked
done
rm -f -- "$root/usr/local/bin/panel-hold" "$root/usr/local/bin/panel-power" "$root/usr/local/bin/powerkey-screen.py" "$root/usr/local/bin/fbtest.py"
rm -f -- "$root/local/tmp/powerkey-screen.service" "$root/local/tmp/powerkey-screen.py" \
    "$root/usr/local/bin/__pycache__"/{powerkey-screen,fbtest}.cpython-*.pyc
install -Dm644 "$overlay/etc/udev/rules.d/80-umi-csot-backlight.rules" \
    "$root/etc/udev/rules.d/80-umi-csot-backlight.rules"
# Chroot sshd verification uses throwaway host keys; no pre-generated host key ships.
chroot "$root" ssh-keygen -A
install -d -m 0755 "$root/run/sshd"
chroot "$root" /usr/sbin/sshd -T > sshd-effective.txt
for line in 'permitrootlogin no' 'passwordauthentication no' 'kbdinteractiveauthentication no' 'authenticationmethods publickey'; do
    grep -Fx "$line" sshd-effective.txt
done
rm -f "$root/etc/ssh/"ssh_host_*
systemctl --root="$root" is-enabled ssh.service ssh.socket > ssh-enabled.txt || true
test "$(grep -xc masked ssh-enabled.txt)" -eq 2
awk -F: '$1=="root" {ok=($2=="!")} END {exit !ok}' "$root/etc/shadow"
test -f "$root/var/lib/umi/root-password-unset"
for service in docker.service containerd.service umi-venus-enable.service umi-gpu-maxfreq.service \
    battery-charge-limit.service umi-bcb-early.service boot-collect.service \
    umi-usb-gadget.service; do
    systemctl --root="$root" is-enabled "$service"
done
for binary in usr/bin/unudhcpd usr/bin/v4l2-ctl usr/bin/ffmpeg usr/bin/docker root/wifi-connect.sh; do
    test -x "$root/$binary" || { echo "Missing /$binary" >&2; exit 1; }
done
for module in ath11k_pci venus-core venus-dec venus-enc; do
    modinfo -b "$root" -k "$new" -F vermagic "$module" | grep -F "$new "
done
(cd "$root"; sha256sum --quiet -c "$work/main-firmware.sha256")
inventory_packages > new-packages.tsv
for file in main-packages.tsv new-packages.tsv; do
    awk '$1 !~ /^linux-(image|dtb)-current-sm8250$/' "$file" > "$file.userspace"
done
diff -u main-packages.tsv.userspace new-packages.tsv.userspace
chroot "$root" dpkg --audit > dpkg-audit.txt
test ! -s dpkg-audit.txt
umount "$root/dev"
trap - EXIT
# Never clone the seed captured from the donor system to every installation.
rm -f -- "$root/var/lib/systemd/random-seed"
test "$(stat -c %a "$root/tmp")" = 1777

img="$out/rootfs-umi-csot-${rate}hz-$version.img"
bash "$repo/make-fnnas/qualcomm/sm8250/scripts/assemble-rootfs.sh" "$root" ext4 "$umi_uuid" "$img"
debugfs -R 'cat /etc/fstab' "$img" 2>/dev/null | grep -F "UUID=$umi_uuid / ext4"
boot_name=boot-umi-csot-${rate}hz-$version.img
cp "$work/boot-build/$boot_name" "$out/"
bash "$repo/make-fnnas/qualcomm/sm8250/scripts/verify-release.sh" "$out/$boot_name" "$img" "$kdir"
(cd "$out"; sha256sum ./*.img > SHA256SUMS.txt; sha256sum -c SHA256SUMS.txt)
