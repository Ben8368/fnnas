#!/usr/bin/env bash
# Build Linux Stable with the configuration embedded in the Umi boot donor.
set -euo pipefail

repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../../.." && pwd)
source "$repo/make-fnnas/qualcomm/sm8250/kernel/source.sh"
if (($# != 2)); then
    echo "Usage: $0 MAIN_BOOT_IMG NEW_LINUX_WORK_DIR" >&2
    exit 2
fi
boot=$(realpath -e -- "$1")
work=$(realpath -m -- "$2")
case "$work" in /mnt/*) echo 'Use a native Linux filesystem for kernel builds.' >&2; exit 2 ;; esac
printf '%s  %s\n' "$umi_boot_donor_sha256" "$boot" | sha256sum -c -
linux_source=$(resolve_umi_linux "${UMI_KERNEL_VERSION:-auto}")
read -r linux_version linux_commit <<< "$linux_source"
mkdir -- "$work"
cd -- "$work"
printf 'Building Linux v%s (%s)\n' "$linux_version" "$linux_commit"

# With UMI_KERNEL_VERSION=locked, KERNEL_BUNDLE permits an offline checkout.
if [[ -n ${KERNEL_BUNDLE:-} ]]; then
    git clone --no-checkout -- "$KERNEL_BUNDLE" linux
    git -C linux checkout --detach "$linux_commit"
else
    git clone --depth 1 --branch "v$linux_version" -- "$umi_linux_repo" linux
fi
test "$(git -C linux rev-parse HEAD)" = "$linux_commit"
test "$(make -s -C linux kernelversion)" = "$linux_version"
printf '%s\n' "$linux_source" > kernel-source.tsv
unpack_bootimg --boot_img "$boot" --out main-boot
gzip -dc main-boot/kernel > main-boot/Image
linux/scripts/extract-ikconfig main-boot/Image > main-boot/kernel.config
locked_config=$repo/make-fnnas/qualcomm/sm8250/kernel/config/umi-6.18.60-base.config
cmp -- main-boot/kernel.config "$locked_config" || {
    echo 'Base kernel config differs from the checked-in, SHA-locked release config.' >&2
    exit 1
}
armbian_patches=$repo/make-fnnas/qualcomm/sm8250/sources/armbian-34f4924/patch/kernel/archive/sm8250-6.18
test -d "$armbian_patches"
patch_manifest=${UMI_PATCH_MANIFEST:-$work/armbian-patches.tsv}
apply_umi_armbian_patches "$work/linux" "$linux_commit" "$armbian_patches" "$patch_manifest"
port="$repo/make-fnnas/qualcomm/sm8250/kernel"
patch_path="$port/patches/sm8250-6.18/0070-umi-match-abl-kona.patch"
patch_sha=$(sha256sum < "$patch_path")
patch_sha=${patch_sha%% *}
if ! git -C linux apply --exclude=drivers/soc/qcom/ubwc_config.c "$patch_path"; then
    printf '%s\t%s\tconflict\tFailed mandatory Umi cpufreq/PD mapper changes\n' "${patch_path##*/}" "$patch_sha" >> "$patch_manifest"
    exit 1
fi
printf '%s\t%s\tapplied\tCPUfreq and PD mapper hunks\n' "${patch_path##*/}" "$patch_sha" >> "$patch_manifest"
printf '%s:ubwc_config.c\t%s\treviewed-skip\tNative DSI port handles UBWC; preserve upstream table\n' \
    "${patch_path##*/}" "$patch_sha" >> "$patch_manifest"
if [[ $patch_manifest != "$work/armbian-patches.tsv" ]]; then
    cp -- "$patch_manifest" "$work/armbian-patches.tsv"
fi
cp "$port"/dts/* linux/arch/arm64/boot/dts/qcom/
cat >> linux/arch/arm64/boot/dts/qcom/Makefile <<'MAKEFILE'

dtb-$(CONFIG_ARCH_QCOM) += sm8250-xiaomi-umi-csot.dtb
MAKEFILE
# Release and lab builds use the checked-in native display source snapshots.
exec bash "$port/config/csot/build.sh" "$work"
