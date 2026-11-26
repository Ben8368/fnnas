#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
# Offline disk-image assembly only. No partition or device is ever flashed.
set -euo pipefail
debug=0
if [[ ${1:-} == --debug ]]; then debug=1; shift; fi
minimum=5
if (( debug )); then minimum=7; fi
if [[ ${1:-} == --help || ${1:-} == -h || $# -lt $minimum ]]; then
    if (( debug )); then
        echo 'Usage: renas -b xiaomi-umi native-debug PINNED_BASE_OR_DASH MAIN_BOOT_IMG FIRMWARE_TAR FIRMWARE_SHA256 NEW_OUTPUT_DIR STOCK_DTBO DTBO_INDEX --source SHA --profile PROFILE --run-id ID --run-attempt N --package-sha256 SHA256'
    else
        echo 'Usage: renas -b xiaomi-umi native PINNED_BASE_OR_DASH MAIN_BOOT_IMG FIRMWARE_TAR FIRMWARE_SHA256 NEW_OUTPUT_DIR [--refresh 60|90] [--version auto|6.18.x] [--repo OWNER/REPO]'
    fi
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
kernel=$scratch/kernel
if (( debug )); then
    dtbo=$(realpath -e -- "$1")
    dtbo_index=$2
    shift 2
    "$FNOS_PYTHON" -B "$scripts/kernel-release.py" fetch-candidate "$kernel" "$@"
    # Bind validation and the recorded digest to the same local copy.
    cp -- "$dtbo" "$scratch/stock-dtbo.img"
    "$FNOS_PYTHON" -B "$scripts/../boot/abl-android-v2/tools/check-installed-dtbo.py" \
        "$scratch/stock-dtbo.img" "$dtbo_index" "$kernel/boot-csot.dtb" --protect-live
    dtbo_sha=$(sha256sum < "$scratch/stock-dtbo.img")
    dtbo_sha=${dtbo_sha%% *}
    provenance=kernel-candidate.json
else
    "$FNOS_PYTHON" -B "$scripts/kernel-release.py" fetch "$kernel" "$@"
    provenance=kernel-promotion.json
fi
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
if (( debug )); then
    install -m644 "$kernel/candidate.json" "$staged/etc/umi-build/$provenance"
    printf 'dtbo_index=%s\ndtbo_sha256=%s\n' "$dtbo_index" "$dtbo_sha" > "$staged/etc/umi-build/stock-dtbo.txt"
fi
result=$scratch/output
mkdir -- "$result"
UMI_NATIVE_BTRFS=1 bash "$scripts/build-boot-pair.sh" "$boot" "$staged" "$uuid" "$scratch/boot-work" "$scratch/kernel"
release=$(< "$kernel/include/config/kernel.release")
modules=$(realpath -m -- "$staged/lib/modules/$release")
[[ $modules == "$staged/"* && ! -e $modules && ! -L $modules ]]
mkdir -p -- "$modules"
rsync -a --chown=0:0 -- "$kernel/lib/modules/$release/" "$modules/"
mv -- "$scratch/boot-work/boot/"boot-umi-*.img "$result/boot.img"
bash "$scripts/assemble-rootfs.sh" "$staged" btrfs "$uuid" "$result/rootfs.img"
UMI_NATIVE_BTRFS=1 bash "$scripts/verify-release.sh" "$result/boot.img" "$result/rootfs.img" "$kernel"
"$FNOS_PYTHON" -B "$scripts/native-rootfs.py" verify "$result/rootfs.img" "$kernel" "$uuid" | tee "$result/rootfs-verify.log"
if (( debug )); then
    cp -- "$staged/etc/umi-build/stock-dtbo.txt" "$result/"
else
    cp -- "$kernel/promotion.json" "$result/$provenance"
fi
cp -- "$staged/etc/umi-build/"*.json "$result/"
mv -- "$report" "$result/base-audit"
(cd "$result"; sha256sum boot.img rootfs.img > SHA256SUMS)
mv -Tn -- "$result" "$output"
[[ ! -e $result ]] || { echo "Output already exists: $output" >&2; exit 1; }
if (( debug )); then
    printf 'Local native fnOS debug image pair (CI candidate, static checks only): %s\n' "$output"
else
    printf 'Unaccepted native fnOS image pair (static checks only): %s\n' "$output"
fi
