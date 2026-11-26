#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
# Internal assembly helper; public image entrypoints fetch promoted kernels only.
set -euo pipefail
[[ $# == 5 ]] || exit 2
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../../.." && pwd)
source "$repo/make-fnnas/qualcomm/sm8250/kernel/source.sh"
boot=$(realpath -e -- "$1")
root=$(realpath -e -- "$2")
uuid=$3
[[ ! -L $4 ]] || { echo "Output path is a symlink: $4" >&2; exit 1; }
work=$(realpath -m -- "$4")
kernel=$(realpath -e -- "$5")
[[ -d $root && $root != / && $work != "$root" && $work != "$root/"* &&
    $uuid =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]] || { echo 'Invalid root or output path' >&2; exit 2; }
[[ ! -e $work ]] || { echo "Output already exists: $work" >&2; exit 1; }
printf '%s  %s\n' "$umi_boot_donor_sha256" "$boot" | sha256sum -c -
parent=$(dirname -- "$work")
mkdir -p -- "$parent"
scratch=$(mktemp -d -- "$parent/.umi-boot.XXXXXX")
trap 'rm -rf -- "$scratch"' EXIT
result=$scratch/output
mkdir -- "$result"
# The caller has fetched a release into its own private directory. Use the same verified bytes.
cp -a -- "$kernel" "$result/kernel"
krel=$(< "$result/kernel/include/config/kernel.release")
unpack_bootimg --boot_img "$boot" --out "$scratch/donor"
UMI_ROOT_UUID="$uuid" bash "$repo/make-fnnas/qualcomm/sm8250/scripts/build-initramfs.sh" \
    "$scratch/donor/ramdisk" "$result/kernel" "$krel" "$root" "$scratch/initramfs" "$scratch/initrd.img"
bash "$repo/make-fnnas/qualcomm/sm8250/scripts/build-boot.sh" "$boot" "$result/kernel" "$scratch/initrd.img" "$uuid" "$result/boot"
mv -Tn -- "$result" "$work"
[[ ! -e $result ]] || { echo "Output already exists: $work" >&2; exit 1; }
printf 'Umi boot output: %s\n' "$work/boot"
