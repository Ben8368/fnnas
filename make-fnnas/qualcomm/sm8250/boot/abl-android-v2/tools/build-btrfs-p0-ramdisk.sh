#!/usr/bin/env bash
# Assemble a self-contained Btrfs P0 RAM initramfs and boot image.
set -euo pipefail

if (($# != 5)); then
    echo "Usage: $0 RELEASE_BOOT RELEASE_INITRD ROOTFS_ROOT NEW_WORK_DIR OUT_BOOT_IMG" >&2
    exit 2
fi
boot=$(realpath -e -- "$1")
initrd=$(realpath -e -- "$2")
rootfs=$(realpath -e -- "$3")
work=$(realpath -m -- "$4")
output=$(realpath -m -- "$5")
tools=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
test_script=$tools/umi-p0-btrfs-test.sh
packer=$tools/make-btrfs-p0-ram.py

for command in cpio gzip lsinitramfs mkfs.btrfs python3; do
    command -v "$command" >/dev/null || { echo "Missing build tool: $command" >&2; exit 1; }
done
test -x "$rootfs/usr/bin/btrfs" || {
    echo "Missing $rootfs/usr/bin/btrfs; install btrfs-progs in the Debian rootfs first" >&2
    exit 1
}
test -f "$test_script"
test ! -e "$work"
mkdir -m 700 -- "$work"
stage=$work/initramfs
mkdir -m 700 -- "$stage"
(cd "$stage"; gzip -dc -- "$initrd" | cpio --quiet -idm --no-absolute-filenames)

# Require the exact release config to record built-in Btrfs and crypto support.
lsinitramfs "$initrd" > "$work/release-initrd.list"
krel=$(find "$stage/usr/lib/modules" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | head -n 1)
test -n "$krel" || { echo 'No kernel module tree in release initramfs' >&2; exit 1; }
config="$rootfs/boot/config-$krel"
test -f "$config" || { echo "Missing release kernel config: $config" >&2; exit 1; }
for symbol in BTRFS_FS BTRFS_FS_POSIX_ACL CRYPTO_XXHASH CRYPTO_BLAKE2B RAID6_PQ XOR_BLOCKS BLK_DEV_LOOP; do
    grep -Fxq "CONFIG_${symbol}=y" "$config" || {
        echo "Release kernel is missing built-in CONFIG_${symbol}=y" >&2
        exit 1
    }
done
if find "$rootfs/usr/lib/modules/$krel" -type f -name 'btrfs.ko*' -print -quit | grep -q . || \
   grep -Fq "usr/lib/modules/$krel/kernel/fs/btrfs/btrfs.ko" "$work/release-initrd.list"; then
    echo 'Release kernel/initramfs contains btrfs.ko; expected built-in Btrfs.' >&2
    exit 1
fi

copy_runtime_binary() {
    local name=$1 source deps lib resolved mode
    local found=0
    for dir in bin sbin usr/bin usr/sbin; do
        if [[ -x "$stage/$dir/$name" ]]; then found=1; break; fi
    done
    source=$(chroot "$rootfs" /bin/sh -c 'command -v "$1"' sh "$name" 2>/dev/null || true)
    if [[ $source == /* && -x "$rootfs$source" ]]; then
        if ((!found)); then
            install -D -m 0755 "$(realpath -e -- "$rootfs$source")" "$stage$source"
        fi
        # Resolve libraries even for commands already present in the base
        # initramfs: usrmerge symlinks such as modprobe -> kmod can point to a
        # dynamic binary whose loader or libraries were not copied with it.
        deps=$work/ldd.$name
        chroot "$rootfs" ldd "$source" > "$deps" 2>&1 || true
        while IFS= read -r lib; do
            [[ $lib == /* && -e "$rootfs$lib" ]] || continue
            resolved=$(realpath -e -- "$rootfs$lib")
            mode=$(stat -c '%a' "$resolved")
            install -D -m "$mode" "$resolved" "$stage$lib"
        done < <(awk '$2 == "=>" && $3 ~ /^\// {print $3} $1 ~ /^\// {print $1}' "$deps" | sort -u)
        return 0
    fi
    if ((found)); then
        return 0
    fi
    {
        echo "Required command '$name' is absent from both initramfs and rootfs" >&2
    } >&2
    return 1
}

# Add only commands absent from the release initramfs; dependencies are copied
# from the matching Debian rootfs, so the test does not rely on host libraries.
for command in btrfs mount dd losetup grep cat sleep sync reboot; do
    copy_runtime_binary "$command"
done
chroot "$stage" /usr/bin/btrfs version >/dev/null

# A 160 MiB test filesystem is embedded in the initramfs and copied to tmpfs by
# the probe. No physical phone block device is opened or written.
test_volume=$work/umi-p0-test.btrfs
truncate -s 160M "$test_volume"
mkfs.btrfs -f -L UMI-P0 "$test_volume" > "$work/mkfs-btrfs.log"
btrfs check --readonly "$test_volume" > "$work/btrfs-check.log" 2>&1
install -Dm755 "$test_script" "$stage/umi-p0-btrfs-test"
install -Dm644 "$test_volume" "$stage/umi-p0-test.btrfs"
(cd "$stage"; find . -print0 | LC_ALL=C sort -z | cpio --quiet --null -o -H newc --owner=0:0) | gzip -n -9 > "$work/ramdisk-btrfs-p0.img.gz"
gzip -t "$work/ramdisk-btrfs-p0.img.gz"
lsinitramfs "$work/ramdisk-btrfs-p0.img.gz" > "$work/p0-initrd.list"
grep -Fxq 'umi-p0-btrfs-test' "$work/p0-initrd.list"
grep -Fxq 'umi-p0-test.btrfs' "$work/p0-initrd.list"
if grep -Fq 'kernel/fs/btrfs/btrfs.ko' "$work/p0-initrd.list"; then
    echo 'Btrfs module unexpectedly entered the RAM test initramfs.' >&2
    exit 1
fi

python3 "$packer" "$boot" "$work/ramdisk-btrfs-p0.img.gz" "$output"
sha256sum "$work/ramdisk-btrfs-p0.img.gz" "$test_volume" "$output" > "$work/SHA256SUMS.txt"
printf 'Built RAM-only Btrfs P0 image: %s\n' "$output"
printf 'Kernel release: %s\n' "$krel"
cat "$work/SHA256SUMS.txt"
