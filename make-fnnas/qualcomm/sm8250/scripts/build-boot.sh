#!/usr/bin/env bash
# Only the native Image and qualified CSOT DTB from the SAME kernel build.
set -euo pipefail
if (($# != 5 && $# != 7)); then
    echo "Usage: $0 MAIN_BOOT KERNEL_OUT NEW_INITRD ROOT_UUID NEW_OUTPUT_DIR [ANDROID_DTBO_TABLE DTBO_INDEX]" >&2
    exit 2
fi
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../../.." && pwd)
main_boot=$1
kdir=$(realpath -e -- "$2")
ramdisk=$3
uuid=$4
out=$5
rate=$(cat "$kdir/refresh")
[[ $rate == 60 || $rate == 90 ]]
krel=$(< "$kdir/include/config/kernel.release")
version=${krel%-csot${rate}-sm8250}
[[ $version =~ ^6\.18\.(0|[1-9][0-9]*)$ && $krel == "$version-csot${rate}-sm8250" ]]
(cd "$kdir"; sha256sum -c SHA256SUMS)
mkdir -- "$out"
dtb="$kdir/boot-csot.dtb"
if (($# == 7)); then
    python3 "$repo/make-fnnas/qualcomm/sm8250/boot/abl-android-v2/tools/check-installed-dtbo.py" "$6" "$7" "$dtb" --protect-live
fi
gzip -n -9 -c -- "$kdir/arch/arm64/boot/Image" > "$out/Image.gz"
boot="$out/boot-umi-csot-${rate}hz-$version.img"
# pack-abl-v2 checks exact v2 layout, root UUID and load-address overlap.
python3 "$repo/make-fnnas/qualcomm/sm8250/boot/abl-android-v2/tools/pack-abl-v2.py" "$main_boot" "$out/Image.gz" "$ramdisk" "$dtb" "$boot" "$uuid" \
    --native-cmdline "$kdir/native-display-cmdline"
unpack_bootimg --boot_img "$boot" --out "$out/verify" > "$out/verify.txt"
cmp "$out/Image.gz" "$out/verify/kernel"
cmp "$ramdisk" "$out/verify/ramdisk"
cmp "$dtb" "$out/verify/dtb"
grep -F "root=UUID=$uuid" "$out/verify.txt"
