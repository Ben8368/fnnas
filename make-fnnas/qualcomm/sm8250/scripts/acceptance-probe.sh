#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
# Make a physical acceptance probe from exact candidate bytes. Never run adb or fastboot.
set -euo pipefail
if (($# != 3)); then
    echo "Usage: $0 MAIN_BOOT_IMG CI_KERNEL_PACKAGE NEW_PROBE_IMG" >&2
    exit 2
fi
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
source "$here/kernel/source.sh"
donor=$(realpath -e -- "$1")
bundle=$(realpath -e -- "$2")
output=$3
printf '%s  %s\n' "$umi_boot_donor_sha256" "$donor" | sha256sum -c -
sha=$(sha256sum < "$bundle"); sha=${sha%% *}
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
for name in arch/arm64/boot/Image boot-csot.dtb native-display-cmdline; do
    tar -xOf "$bundle" "$name" > "$work/${name##*/}"
done
unpack_bootimg --boot_img "$donor" --out "$work/donor" > "$work/donor-header"
gzip -n -9 -c -- "$work/Image" > "$work/Image.gz"
python3 -B "$here/boot/abl-android-v2/tools/pack-abl-v2.py" "$donor" "$work/Image.gz" \
    "$work/donor/ramdisk" "$work/boot-csot.dtb" "$work/acceptance-template.img" \
    02232280-925f-4edc-984f-24e466d3b6f1 --native-cmdline "$work/native-display-cmdline"
# Only RAM PID 1; it never executes the donor init or mounts a block filesystem.
python3 -B "$here/boot/abl-android-v2/tools/make-ram-probe.py" "$work/acceptance-template.img" "$output" \
    --package-sha256 "$sha"
sha256sum -- "$output"
