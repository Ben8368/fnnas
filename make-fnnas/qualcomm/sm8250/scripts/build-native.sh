#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
# Offline disk-image assembly only. No partition or device is ever flashed.
set -euo pipefail
if [[ ${1:-} == --help || ${1:-} == -h || $# -lt 5 ]]; then
    echo 'Usage: renas -b xiaomi-umi native PINNED_BASE_OR_DASH MAIN_BOOT_IMG FIRMWARE_TAR FIRMWARE_SHA256 NEW_OUTPUT_DIR [--refresh 60|90] [--version auto|6.18.x] [--repo OWNER/REPO]'
    if [[ ${1:-} == --help || ${1:-} == -h ]]; then exit 0; fi
    exit 2
fi
(( EUID == 0 )) || { echo 'Use root on Linux (numeric owners, ACLs, xattrs).' >&2; exit 1; }
scripts=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
base=$1
boot=$(realpath -e -- "$2")
firmware=$(realpath -e -- "$3")
firmware_sha=$4
[[ ! -L $5 ]] || exit 2
output=$(realpath -m -- "$5")
shift 5
[[ ! -e $output && -f $boot && -f $firmware && $firmware_sha =~ ^[0-9a-f]{64}$ ]] || exit 2
export FNOS_PYTHON=${FNOS_PYTHON:-/usr/bin/python3}
export LIBGUESTFS_BACKEND=${LIBGUESTFS_BACKEND:-direct}
export LIBGUESTFS_BACKEND_SETTINGS=${LIBGUESTFS_BACKEND_SETTINGS:-force_tcg}
parent=$(dirname -- "$output")
mkdir -p -- "$parent"
scratch=$(mktemp -d -- "$parent/.umi-native.XXXXXX")
trap 'rm -rf -- "$scratch"' EXIT
mkdir -- "$scratch/staged"
# Fetch only a published, accepted bundle. Do not fall back to CI candidates.
"$FNOS_PYTHON" -B "$scripts/kernel-release.py" fetch "$scratch/kernel" "$@"
if [[ $base == - ]]; then
    base=$scratch/fnos.img.xz
    bash "$scripts/download-base.sh" "$base"
else
    base=$(realpath -e -- "$base")
fi
report=$scratch/base-audit
bash "$scripts/inspect-base.sh" "$base" --sha256 locked --output "$report" --rootfs-archive "$scratch/rootfs.tar"
staged=$scratch/staged
tar --numeric-owner --xattrs --xattrs-include='*' --acls --selinux -xpf "$scratch/rootfs.tar" -C "$staged"
rm -- "$scratch/rootfs.tar"
uuid=$(uuidgen -r | tr '[:upper:]' '[:lower:]')
bash "$scripts/apply-files.sh" "$staged"
"$FNOS_PYTHON" -B "$scripts/native-rootfs.py" prepare "$staged" "$report" "$firmware" "$firmware_sha" "$uuid"
result=$scratch/output
mkdir -- "$result"
UMI_NATIVE_BTRFS=1 bash "$scripts/build-boot-pair.sh" "$boot" "$staged" "$uuid" "$scratch/boot-work" "$scratch/kernel"
kernel=$scratch/kernel
release=$(< "$kernel/include/config/kernel.release")
modules=$(realpath -m -- "$staged/lib/modules/$release")
[[ $modules == "$staged/"* && ! -e $modules && ! -L $modules ]]
mkdir -p -- "$modules"
rsync -a --chown=0:0 -- "$kernel/lib/modules/$release/" "$modules/"
mv -- "$scratch/boot-work/boot/"boot-umi-*.img "$result/boot.img"
bash "$scripts/assemble-rootfs.sh" "$staged" btrfs "$uuid" "$result/rootfs.img"
UMI_NATIVE_BTRFS=1 bash "$scripts/verify-release.sh" "$result/boot.img" "$result/rootfs.img" "$kernel"
"$FNOS_PYTHON" -B "$scripts/native-rootfs.py" verify "$result/rootfs.img" "$kernel" "$uuid" | tee "$result/rootfs-verify.log"
cp -- "$kernel/promotion.json" "$result/kernel-promotion.json"
cp -- "$staged/etc/umi-build/"*.json "$result/"
mv -- "$report" "$result/base-audit"
(cd "$result"; sha256sum boot.img rootfs.img > SHA256SUMS)
mv -Tn -- "$result" "$output"
[[ ! -e $result ]] || { echo "Output already exists: $output" >&2; exit 1; }
printf 'Unaccepted native fnOS image pair (static checks only): %s\n' "$output"
