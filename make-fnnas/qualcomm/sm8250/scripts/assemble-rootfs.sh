#!/usr/bin/env bash
# Create a fresh filesystem image from an already prepared staging directory.
set -euo pipefail
if (($# != 4)); then
    echo "Usage: $0 STAGING EXT4_OR_BTRFS ROOT_UUID NEW_OUTPUT_IMG" >&2
    exit 2
fi
root=$(realpath -e -- "$1")
fs=$2
uuid=$3
[[ ! -L $4 ]] || { echo "Image path is a symlink: $4" >&2; exit 1; }
output=$(realpath -m -- "$4")
if [[ ! -d $root || $root == / || $output == "$root/"* ||
    ! $uuid =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]]; then
    echo 'Provide a staging directory, a separate image path and a lowercase filesystem UUID.' >&2
    exit 2
fi
[[ ! -e $output && ! -L $output ]] || { echo "Output already exists: $output" >&2; exit 1; }
case $fs in ext4|btrfs) ;; *) echo "Unsupported filesystem: $fs" >&2; exit 2 ;; esac
mkdir -p -- "$(dirname -- "$output")"
scratch=$(mktemp -d -- "$(dirname -- "$output")/.fnos-rootfs.XXXXXX")
trap 'rm -rf -- "$scratch"' EXIT
image=$scratch/rootfs.img
used=$(du -sm --apparent-size "$root" | cut -f1)
truncate -s "$((used + 1280))M" "$image"
case $fs in
    ext4)
        mkfs.ext4 -q -F -m 0 -O '^orphan_file,^metadata_csum_seed' -U "$uuid" -d "$root" "$image"
        e2fsck -fn "$image"
        ;;
    btrfs)
        mkfs.btrfs --quiet --uuid "$uuid" --rootdir "$root" "$image"
        btrfs check --readonly "$image"
        ;;
esac
[[ $(blkid -s TYPE -o value "$image") == "$fs" && $(blkid -s UUID -o value "$image") == "$uuid" ]]
ln -T -- "$image" "$output"
