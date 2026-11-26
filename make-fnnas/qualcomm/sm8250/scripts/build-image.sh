#!/usr/bin/env bash
# Assemble a matched Android boot image and filesystem image from a prepared Umi RootFS.
set -euo pipefail

usage() {
    echo 'Usage: renas -b xiaomi-umi build MAIN_BOOT_IMG STAGED_ROOTFS EXT4_OR_BTRFS ROOT_UUID NEW_OUTPUT_DIR [--refresh 60|90] [--version auto|6.18.x] [--repo OWNER/REPO]'
}

if [[ ${1:-} == --help || ${1:-} == -h ]]; then usage; exit 0; fi
if (($# < 5)); then usage >&2; exit 2; fi
scripts=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
boot=$(realpath -e -- "$1")
root=$(realpath -e -- "$2")
filesystem=$3
uuid=$4
[[ ! -L $5 ]] || { echo "Output path is a symlink: $5" >&2; exit 1; }
output=$(realpath -m -- "$5")
shift 5
if [[ ! -f $boot || ! -d $root || $root == / || $output == "$root" || $output == "$root/"* ||
    ! $uuid =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]]; then
    echo 'Provide a boot donor, a staged RootFS, a lowercase UUID, and an output outside the source tree.' >&2
    exit 2
fi
case $filesystem in ext4|btrfs) ;; *) usage >&2; exit 2 ;; esac
[[ ! -e $output ]] || { echo "Output already exists: $output" >&2; exit 1; }
(( EUID == 0 )) || { echo 'Run the image build as root to preserve RootFS owners and attributes.' >&2; exit 1; }

parent=$(dirname -- "$output")
mkdir -p -- "$parent"
scratch=$(mktemp -d -- "$parent/.umi-image.XXXXXX")
trap 'rm -rf -- "$scratch"' EXIT
result=$scratch/output
staged=$scratch/rootfs
mkdir -- "$result" "$staged"
rsync -aHAX --numeric-ids -- "$root/" "$staged/"
bash "$scripts/build-released-boot.sh" "$boot" "$staged" "$uuid" "$scratch/release" "$@"

kernel=$scratch/release/kernel
kernel_release=$(< "$kernel/include/config/kernel.release")
modules=$(realpath -m -- "$staged/lib/modules/$kernel_release")
if [[ $modules != "$staged/"* || -e $modules || -L $staged/lib/modules/$kernel_release ]]; then
    echo "The staged RootFS must have an unused in-tree module path for $kernel_release." >&2
    exit 1
fi
mkdir -p -- "$modules"
rsync -a --chown=0:0 -- "$kernel/lib/modules/$kernel_release/" "$modules/"
mv -- "$scratch/release/boot/"boot-umi-*.img "$result/boot.img"
bash "$scripts/assemble-rootfs.sh" "$staged" "$filesystem" "$uuid" "$result/rootfs.img"
bash "$scripts/verify-release.sh" "$result/boot.img" "$result/rootfs.img" "$kernel"
(cd "$result"; sha256sum boot.img rootfs.img > SHA256SUMS)
mv -Tn -- "$result" "$output"
[[ ! -e $result ]] || { echo "Output already exists: $output" >&2; exit 1; }
printf 'Umi image output: %s\n' "$output"
