#!/usr/bin/env bash
# Apply the selected board's versioned file layers to a Linux staging tree.
set -euo pipefail
if (($# != 1 && $# != 3)); then
    echo "Usage: $0 ROOTFS_STAGING [--board xiaomi-umi]" >&2
    exit 2
fi
if (($# == 3)) && [[ $2 != --board || $3 != xiaomi-umi ]]; then
    echo 'Supported board: xiaomi-umi' >&2
    exit 2
fi
project=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
root=$(realpath -e -- "$1")
if [[ ! -d $root || $root == / || $project == "$root" || $project == "$root/"* || $root == "$project/"* ]]; then
    echo 'Choose a separate RootFS staging directory.' >&2
    exit 2
fi
for layer in common-files platform-files/qualcomm/sm8250 different-files/xiaomi-umi; do
    source=$project/fnos-files/$layer/rootfs
    if [[ -d $source ]]; then
        # Git records file modes and symlinks. Ignore checkout-specific ACLs and xattrs.
        rsync -aH --chown=0:0 -- "$source/" "$root/"
    fi
done
