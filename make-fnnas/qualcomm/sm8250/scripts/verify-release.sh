#!/usr/bin/env bash
# Verify that the rootfs and the Android v2 boot refer to the same build inputs.
set -euo pipefail
if (($# != 3)); then
    echo "Usage: $0 BOOT_IMG ROOTFS_IMG KERNEL_OUT" >&2
    exit 2
fi
boot=$(realpath -e -- "$1")
rootfs=$(realpath -e -- "$2")
kernel=$(realpath -e -- "$3")
[[ -f $boot && -f $rootfs ]]
uuid=$(blkid -s UUID -o value "$rootfs")
version=$(cat "$kernel/include/config/kernel.release")
(cd "$kernel"; sha256sum -c SHA256SUMS)
scratch=$(mktemp -d)
trap 'rm -rf -- "$scratch"' EXIT
unpack_bootimg --boot_img "$boot" --out "$scratch/boot" > "$scratch/header"
grep -Eq 'boot image header version: *2$' "$scratch/header"
grep -Eq "[[:space:]]root=UUID=$uuid([[:space:]]|$)" "$scratch/header"
gzip -dc "$scratch/boot/kernel" | cmp - "$kernel/arch/arm64/boot/Image"
cmp "$scratch/boot/dtb" "$kernel/boot-csot.dtb"
lsinitramfs "$scratch/boot/ramdisk" > "$scratch/ramdisk-list"
versions=$(awk -F / '{ sub(/^\.\//, "") } /^(usr\/)?lib\/modules\/[^/]+\// {
    if ($1 == "usr") print $4; else print $3
}' "$scratch/ramdisk-list" | LC_ALL=C sort -u)
[[ $versions == "$version" ]] || { echo "Initramfs module tree does not match $version" >&2; exit 1; }
printf 'Verified %s with RootFS UUID %s\n' "$version" "$uuid"
