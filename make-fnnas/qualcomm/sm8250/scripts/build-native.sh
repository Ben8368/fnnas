#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
# Offline disk-image assembly only. No partition or device is ever flashed.
set -euo pipefail
debug=0
local_debug=0
case ${1:-} in
    --debug) debug=1; shift ;;
    --local-debug) debug=1; local_debug=1; shift ;;
esac
if [[ ${1:-} == --help || ${1:-} == -h || $# -lt 5 ]]; then
    if (( local_debug )); then
        echo 'Usage: renas -b xiaomi-umi native-local-debug PINNED_BASE_OR_DASH MAIN_BOOT_IMG FIRMWARE_TAR FIRMWARE_SHA256 NEW_OUTPUT_DIR [lineage-latest all | STOCK_DTBO DTBO_INDEX] --local-package PACKAGE --source SHA --linux-commit SHA --profile PROFILE --package-sha256 SHA256'
    elif (( debug )); then
        echo 'Usage: renas -b xiaomi-umi native-debug PINNED_BASE_OR_DASH MAIN_BOOT_IMG FIRMWARE_TAR FIRMWARE_SHA256 NEW_OUTPUT_DIR [lineage-latest all | STOCK_DTBO DTBO_INDEX] --source SHA --profile PROFILE --run-id ID --run-attempt N --package-sha256 SHA256'
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
lineage=1
if (( debug )); then
    # The optional positional pair is kept for the historical readback workflow.
    if [[ $# -gt 0 && $1 != --* ]]; then
        [[ $# -ge 2 ]] || { echo 'A DTBO selector requires an index or all.' >&2; exit 2; }
        dtbo=$1
        dtbo_index=$2
        shift 2
        if [[ $dtbo == lineage-latest && $dtbo_index == all ]]; then
            :
        elif [[ $dtbo != lineage-latest && $dtbo_index =~ ^(0|[1-9][0-9]*)$ ]]; then
            lineage=0
            cp -- "$(realpath -e -- "$dtbo")" "$scratch/dtbo.img"
        else
            echo 'Select either lineage-latest all or a local DTBO and numeric active index.' >&2
            exit 2
        fi
    fi
    if (( local_debug )); then
        "$FNOS_PYTHON" -B "$scripts/kernel-release.py" fetch-local "$kernel" "$@"
        package_record=local-build.json
        provenance=kernel-local-build.json
    else
        "$FNOS_PYTHON" -B "$scripts/kernel-release.py" fetch-candidate "$kernel" "$@"
        package_record=candidate.json
        provenance=kernel-candidate.json
    fi
else
    "$FNOS_PYTHON" -B "$scripts/kernel-release.py" fetch "$kernel" "$@"
    provenance=kernel-promotion.json
fi
if (( local_debug )); then
    release=$(< "$kernel/include/config/kernel.release")
    for module in fs/nfsd/nfsd.ko net/openvswitch/openvswitch.ko; do
        path=$kernel/lib/modules/$release/kernel/$module
        magic=$(modinfo -F vermagic "$path")
        [[ ${magic%% *} == "$release" ]] || { echo "Invalid vermagic for $module" >&2; exit 1; }
        sha256sum -- "$path"
    done
fi
if (( lineage )); then
    dtbo_index=all
    "$FNOS_PYTHON" -B "$scripts/lineage-dtbo.py" "$scratch"
fi
# build-boot.sh also compares this kernel DTB byte-for-byte with the packed DTB.
"$FNOS_PYTHON" -B "$scripts/../boot/abl-android-v2/tools/check-installed-dtbo.py" \
    "$scratch/dtbo.img" "$dtbo_index" "$kernel/boot-csot.dtb" --protect-live
if [[ $base == - ]]; then
    base=$scratch/fnos.img.xz
    bash "$scripts/download-base.sh" "$base"
else
    base=$(realpath -e -- "$base")
fi
report=$scratch/base-audit
bash "$scripts/inspect-base.sh" "$base" --sha256 locked --output "$report" --rootfs-archive "$scratch/rootfs.tar"
staged=$scratch/staged
# Keep the mountpoint. The donor's /dev entries are 0:0 placeholders and
# the initramfs supplies the live devtmpfs before switching root.
tar --numeric-owner --xattrs --xattrs-include='*' --acls --selinux \
    --exclude='./dev/*' -xpf "$scratch/rootfs.tar" -C "$staged"
rm -- "$scratch/rootfs.tar"
uuid=$(uuidgen -r | tr '[:upper:]' '[:lower:]')
bash "$scripts/apply-files.sh" "$staged"
"$FNOS_PYTHON" -B "$scripts/native-rootfs.py" prepare "$staged" "$report" "$firmware" "$firmware_sha" "$uuid"
if (( debug )); then
    install -m644 "$kernel/$package_record" "$staged/etc/umi-build/$provenance"
fi
if (( lineage )); then
    install -m644 "$scratch/lineage-dtbo.json" "$staged/etc/umi-build/lineage-dtbo.json"
else
    dtbo_sha=$(sha256sum < "$scratch/dtbo.img")
    printf 'dtbo_index=%s\ndtbo_sha256=%s\n' "$dtbo_index" "${dtbo_sha%% *}" > "$staged/etc/umi-build/stock-dtbo.txt"
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
if (( lineage )); then
    cp -- "$scratch/dtbo.img" "$result/"
else
    cp -- "$staged/etc/umi-build/stock-dtbo.txt" "$result/"
fi
if (( ! debug )); then
    cp -- "$kernel/promotion.json" "$result/$provenance"
fi
install -m644 "$scripts/../docs/flash-acceptance.md" "$result/FLASH.md"
install -m644 "$scripts/collect-boot-evidence.sh" "$result/collect-boot-evidence.sh"
cp -- "$staged/etc/umi-build/"*.json "$result/"
mv -- "$report" "$result/base-audit"
checksum_files=(boot.img rootfs.img FLASH.md collect-boot-evidence.sh "$provenance")
if (( lineage )); then checksum_files+=(dtbo.img lineage-dtbo.json); else checksum_files+=(stock-dtbo.txt); fi
(cd "$result"; sha256sum "${checksum_files[@]}" > SHA256SUMS)
mv -Tn -- "$result" "$output"
[[ ! -e $result ]] || { echo "Output already exists: $output" >&2; exit 1; }
if (( local_debug )); then
    printf 'Local native fnOS debug image pair (local build, static checks only): %s\n' "$output"
elif (( debug )); then
    printf 'Local native fnOS debug image pair (CI candidate, static checks only): %s\n' "$output"
else
    printf 'Unaccepted native fnOS image pair (static checks only): %s\n' "$output"
fi
printf 'Install and verify using %s/FLASH.md\n' "$output"
