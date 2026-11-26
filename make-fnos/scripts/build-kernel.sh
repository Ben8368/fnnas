#!/usr/bin/env bash
# Build the 6.18.60 kernel against the configuration embedded in the main release.
set -euo pipefail

repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
if (($# != 2)); then
    echo "Usage: $0 MAIN_BOOT_IMG NEW_LINUX_WORK_DIR" >&2
    exit 2
fi
boot=$(realpath -e -- "$1")
work=$(realpath -m -- "$2")
case "$work" in /mnt/*) echo 'Use a native Linux filesystem for kernel builds.' >&2; exit 2 ;; esac
printf '%s  %s\n' a7e4d341e35a663683bf41a8fe99d472bc6b8568aa1b54b05901dc7e9f2d842a "$boot" | sha256sum -c -
mkdir -- "$work"
cd -- "$work"
linux_commit=f45ed76d6791cf72ff1265ee93511175bbbc2f18

# KERNEL_BUNDLE permits an offline checkout from a previously fetched, identical source.
if [[ -n ${KERNEL_BUNDLE:-} ]]; then
    git clone -- "$KERNEL_BUNDLE" linux
else
    git clone --depth 1 --branch v6.18.60 -- \
        https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git linux
fi
test "$(git -C linux rev-parse HEAD)" = "$linux_commit"
unpack_bootimg --boot_img "$boot" --out main-boot
gzip -dc main-boot/kernel > main-boot/Image
linux/scripts/extract-ikconfig main-boot/Image > main-boot/kernel.config
locked_config=$repo/make-fnos/kernel/config/umi-6.18.60-base.config
cmp -- main-boot/kernel.config "$locked_config" || {
    echo 'Base kernel config differs from the checked-in, SHA-locked release config.' >&2
    exit 1
}
armbian_patches=$repo/make-fnos/sources/armbian-34f4924/patch/kernel/archive/sm8250-6.18
test -d "$armbian_patches"
for f in "$armbian_patches"/*.patch; do
    printf '\n=== %s ===\n' "${f##*/}"
    # 0021's Makefile context overlaps a new in-tree BQ257xx driver; GNU patch
    # accepts displaced/context-changed hunks but exits nonzero on any reject.
    patch -d linux --batch --forward -p1 < "$f"
done
port="$repo/make-fnos/kernel"
git -C linux apply --exclude=drivers/soc/qcom/ubwc_config.c "$port/patches/sm8250-6.18/0070-umi-match-abl-kona.patch"
cp "$port"/dts/* linux/arch/arm64/boot/dts/qcom/
cat >> linux/arch/arm64/boot/dts/qcom/Makefile <<'MAKEFILE'

dtb-$(CONFIG_ARCH_QCOM) += sm8250-xiaomi-umi-csot.dtb
MAKEFILE
# Release and lab builds use the checked-in native display source snapshots.
exec bash "$port/config/csot/build.sh" "$work"
