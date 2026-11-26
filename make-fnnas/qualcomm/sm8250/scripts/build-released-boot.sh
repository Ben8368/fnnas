#!/usr/bin/env bash
# Build Android v2 boot from an already published Umi kernel and a prepared RootFS.
set -euo pipefail
usage() {
    printf 'Usage: refnos boot MAIN_BOOT_IMG STAGED_ROOTFS ROOT_UUID NEW_WORK_DIR [--refresh 60|90] [--version auto|6.18.x] [--repo OWNER/REPO]\n'
}
if [[ ${1:-} == --help || ${1:-} == -h ]]; then usage; exit 0; fi
if (($# < 4)); then usage >&2; exit 2; fi
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../../.." && pwd)
source "$repo/make-fnnas/qualcomm/sm8250/kernel/source.sh"
boot=$(realpath -e -- "$1")
root=$(realpath -e -- "$2")
uuid=$3
[[ ! -L $4 ]] || { echo "Output path is a symlink: $4" >&2; exit 1; }
work=$(realpath -m -- "$4")
shift 4
[[ -d $root && $root != / && $work != "$root" && $work != "$root/"* &&
    $uuid =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]] || { usage >&2; exit 2; }
[[ ! -e $work ]] || { echo "Output already exists: $work" >&2; exit 1; }
printf '%s  %s\n' "$umi_boot_donor_sha256" "$boot" | sha256sum -c -
parent=$(dirname -- "$work")
mkdir -p -- "$parent"
scratch=$(mktemp -d -- "$parent/.umi-boot.XXXXXX")
trap 'rm -rf -- "$scratch"' EXIT
result=$scratch/output
"${FNOS_PYTHON:-python3}" "$repo/make-fnnas/qualcomm/sm8250/scripts/kernel-release.py" fetch "$result/kernel" "$@"
krel=$(< "$result/kernel/include/config/kernel.release")
unpack_bootimg --boot_img "$boot" --out "$scratch/donor"
UMI_ROOT_UUID="$uuid" bash "$repo/make-fnnas/qualcomm/sm8250/scripts/build-initramfs.sh" \
    "$scratch/donor/ramdisk" "$result/kernel" "$krel" "$root" "$scratch/initramfs" "$scratch/initrd.img"
bash "$repo/make-fnnas/qualcomm/sm8250/scripts/build-boot.sh" "$boot" "$result/kernel" "$scratch/initrd.img" "$uuid" "$result/boot"
mv -Tn -- "$result" "$work"
[[ ! -e $result ]] || { echo "Output already exists: $work" >&2; exit 1; }
printf 'Umi boot output: %s\n' "$work/boot"
