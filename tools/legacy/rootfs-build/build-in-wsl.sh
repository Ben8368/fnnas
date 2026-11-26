#!/usr/bin/env bash
# Build one matched CSOT boot/rootfs pair on native Linux or WSL2, never flash.
set -euo pipefail
if (($# != 3 && $# != 5)); then
    echo 'Usage: [CSOT_REFRESH=60|90] build-in-wsl.sh MAIN_BOOT MAIN_ROOTFS_TAR NEW_WORK_DIR [ANDROID_DTBO_TABLE INDEX]' >&2
    exit 2
fi
port=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
work=$(realpath -m -- "$3")
case $work in /mnt/*) echo 'Use a native Linux filesystem for the work directory.' >&2; exit 2 ;; esac
mkdir -- "$work"
export CSOT_LAB=0
bash "$port/build-release-kernel.sh" "$1" "$work/kernel"
sudo unshare --mount --propagation private bash "$port/assemble-release.sh" \
    "$1" "$2" "$work/kernel" "$work/assembly" "${@:4}"
