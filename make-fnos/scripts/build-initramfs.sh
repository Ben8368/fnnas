#!/usr/bin/env bash
# Rebuild a slim initramfs while retaining the released early userspace, firmware
# and init scripts. Only modules for the newly built kernel may enter the archive.
set -euo pipefail
if (($# != 6)); then
    echo "Usage: $0 MAIN_RAMDISK MODULE_ROOT NEW_KREL ROOTFS NEW_WORK_DIR OUT_INITRD" >&2
    exit 2
fi
ramdisk=$(realpath -e -- "$1")
module_root=$(realpath -e -- "$2")
krel=$3
rootfs=$(realpath -e -- "$4")
staging=$(realpath -m -- "$5")
output=$(realpath -m -- "$6")
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
mkdir -m 700 -- "$staging"
(cd "$staging"; gzip -dc -- "$ramdisk" | cpio --quiet -idm --no-absolute-filenames)
# The boot donor contains a bytewise different ZAP blob under the same name.
# Use the verified release rootfs copy for Adreno's early secure initialization.
zap=usr/lib/firmware/qcom/sm8250/a650_zap.mbn
test -s "$rootfs/$zap" || { echo "Missing or empty release firmware: $rootfs/$zap" >&2; exit 1; }
install -Dm644 "$rootfs/$zap" "$staging/$zap"
old=6.18.52-current-sm8250
test -d "$staging/usr/lib/modules/$old/kernel"
test -d "$module_root/lib/modules/$krel/kernel"
find "$staging/usr/lib/modules/$old/kernel" -type f -name '*.ko' -printf '%f\n' | sort -u > "$staging.modules-main"
test -s "$staging.modules-main"
rm -r -- "$staging/usr/lib/modules/$old"
for f in modules.order modules.builtin modules.builtin.modinfo; do
    install -Dm644 "$module_root/lib/modules/$krel/$f" "$staging/usr/lib/modules/$krel/$f"
done
# Resolve dependencies against the entire new module tree, including prerequisites
# that weren't modules in the older release (or newly became built-ins).
while IFS= read -r module; do
    modprobe --dirname "$module_root" --set-version "$krel" --ignore-install \
        --show-depends "${module%.ko}"
done < "$staging.modules-main" > "$staging.module-dependencies"
# Optional out-of-tree modules needed by another rootfs profile. Built-in
# filesystems and their selected crypto dependencies do not belong here.
read -r -a extra_modules <<< "${UMI_INITRAMFS_EXTRA_MODULES:-}"
for module in "${extra_modules[@]}"; do
    [[ $module =~ ^[A-Za-z0-9_-]+$ ]] || { echo "Invalid extra module name: $module" >&2; exit 1; }
    modprobe --dirname "$module_root" --set-version "$krel" --ignore-install \
        --show-depends "$module" >> "$staging.module-dependencies"
done
while read -r kind path _; do
    case "$kind" in
        insmod)
            [[ $path == "$module_root/lib/modules/$krel/"* ]] || { echo "Unexpected module path: $path" >&2; exit 1; }
            install -Dm644 "$path" "$staging/usr/lib/modules/$krel/${path#"$module_root/lib/modules/$krel/"}"
            ;;
        builtin) ;;
        *) echo "Unexpected modprobe output: $kind $path" >&2; exit 1 ;;
    esac
done < <(sort -u "$staging.module-dependencies")
depmod -b "$staging" "$krel"
for module in "${extra_modules[@]}"; do
    modprobe --dirname "$staging" --set-version "$krel" --show-depends "$module" \
        > "$staging.module-check"
    while read -r kind path _; do
        [[ $kind == builtin || ( $kind == insmod && -f $path ) ]] || {
            echo "Incomplete initramfs dependency for $module: $kind $path" >&2
            exit 1
        }
    done < "$staging.module-check"
done
# Use the same CSOT backlight policy during early udev coldplug and rootfs boot.
rule=etc/udev/rules.d/80-umi-csot-backlight.rules
install -Dm644 "$repo/make-fnos/fnos-files/different-files/xiaomi-umi/rootfs/$rule" "$staging/$rule"
# Retain the rest of the early userspace, with its root UUID updated below.
if [[ -n ${UMI_ROOT_UUID:-} ]]; then
    sed -i "s/02232280-925f-4edc-984f-24e466d3b6f1/$UMI_ROOT_UUID/g" "$staging/etc/fstab"
fi
(cd "$staging"; find . -print0 | LC_ALL=C sort -z | cpio --quiet --null -o -H newc --owner=0:0) | gzip -n -9 > "$output"
lsinitramfs "$output" > "$output.list"
grep -q "^usr/lib/modules/$krel/" "$output.list"
grep -Fxq "$rule" "$output.list"
grep -Fxq "$zap" "$output.list"
if grep -Fq "usr/lib/modules/$krel/kernel/fs/btrfs/btrfs.ko" "$output.list"; then
    echo 'Btrfs must be built into the kernel and must not be packaged as a module.' >&2
    exit 1
fi
for module in "${extra_modules[@]}"; do
    if ! grep -E -q "^usr/lib/modules/$krel/kernel/.*/${module}\\.ko(\\.(gz|xz|zst))?$" "$output.list"; then
        echo "Requested initramfs module was not packaged: $module" >&2
        exit 1
    fi
done
if grep -Fq -- "$old" "$output.list"; then
    echo "Stale kernel $old found in $output" >&2
    exit 1
elif [[ $? != 1 ]]; then
    exit 1
fi
