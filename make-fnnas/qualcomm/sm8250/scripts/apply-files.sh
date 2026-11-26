#!/usr/bin/env bash
# Apply the selected board's versioned file layers to a Linux staging tree.
set -euo pipefail
if [[ ${1:-} == --help || ${1:-} == -h ]]; then
    echo 'Usage: renas -b xiaomi-umi overlay ROOTFS_STAGING'
    exit 0
fi
if (($# != 1 && $# != 3)); then
    echo "Usage: $0 ROOTFS_STAGING [--board xiaomi-umi]" >&2
    exit 2
fi
if (($# == 3)) && [[ $2 != --board || $3 != xiaomi-umi ]]; then
    echo 'Supported board: xiaomi-umi' >&2
    exit 2
fi
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../../.." && pwd)
resources=$repo/make-fnnas
root=$(realpath -e -- "$1")
if [[ ! -d $root || $root == / || $resources == "$root" || $resources == "$root/"* || $root == "$resources/"* ]]; then
    echo 'Choose a separate RootFS staging directory.' >&2
    exit 2
fi
for layer in platform-files/qualcomm/sm8250 different-files/xiaomi-umi; do
    source=$resources/fnnas-files/$layer/rootfs
    if [[ -d $source ]]; then
        # Git records file modes and symlinks. Ignore checkout-specific ACLs and xattrs.
        rsync -aH --chown=0:0 -- "$source/" "$root/"
    fi
done
