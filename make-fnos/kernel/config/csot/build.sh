#!/usr/bin/env bash
# Internal entry point; build-release-kernel.sh prepares a fresh, pinned tree.
set -euo pipefail
if (($# != 1)); then
    echo "Usage: $0 NEW_LINUX_WORK_DIR" >&2
    exit 2
fi
work=$(realpath -e -- "$1")
here=$(cd -- "$(dirname -- "$0")" && pwd)
cd "$work"
rate=${CSOT_REFRESH:-60}
export CSOT_REFRESH="$rate" CSOT_LAB="${CSOT_LAB:-0}"
rx_profile=${CSOT_RX_PROFILE:-off}
export CSOT_RX_PROFILE="$rx_profile"
source "$here/display-revisions.sh"
case $CSOT_LAB in
    0)
        [[ $rx_profile == off ]] || { echo 'Wireless RX profiles require CSOT_LAB=1' >&2; exit 2; }
        out=kernel-out; localversion=-csot${rate}-sm8250 ;;
    1)
        out=csot-out; localversion=-csot-lab
        case $rx_profile in
            off) ;;
            observe|link|epp|buck) fragments_rx="$here/wireless-rx-$rx_profile.config" ;;
            *) echo 'CSOT_RX_PROFILE must be off, observe, link, epp or buck' >&2; exit 2 ;;
        esac ;;
    *) echo 'CSOT_LAB must be 0 or 1' >&2; exit 2 ;;
esac
test -d "$display_source/kernel" && test -d "$display_source/tools" && test -d "$display_source/tests"
linux_rev=f45ed76d6791cf72ff1265ee93511175bbbc2f18
test "$(git -C linux rev-parse HEAD)" = "$linux_rev"
command -v cc >/dev/null || { echo 'Host C compiler required for the panel harness' >&2; exit 1; }
mkdir "$out" display-inputs
cp -a "$display_source/kernel" "$display_source/tools" "$display_source/tests" display-inputs/
fragments=("$out/native-display.config" "$here/btrfs-built-in.config" display-inputs/kernel/display/umi-native-dsi.config)
if [[ $out == csot-out ]]; then
    test -d "$lab_source/kernel" && test -d "$lab_source/tools"
    mkdir board-lab-inputs
    cp -a "$lab_source/kernel" "$lab_source/tools" "$lab_source/tests" board-lab-inputs/
    fragments+=("$here"/[1-4]0-*.config)
    if [[ $rx_profile != off ]]; then fragments+=("$fragments_rx"); fi
else
    fragments+=("$here/release-hardware.config")
fi
(cd display-inputs; python3 -B -m unittest tests.test_native_display.NativePanelTests.test_commands_fail_closed_reset_and_zero_brightness)
printf '%s\n' "$linux_rev" > linux/.display-source-revision
export ARCH=arm64 CROSS_COMPILE=${CROSS_COMPILE:-aarch64-linux-gnu-}
python3 "$here/stage.py" "$work"
linux/scripts/kconfig/merge_config.sh -m -O "$out" main-boot/kernel.config "${fragments[@]}"
make -C linux O="$work/$out" olddefconfig
for frag in "${fragments[@]}"; do
    while IFS= read -r line; do
        case $line in
            CONFIG_ENABLE_DEFAULT_TRACERS=y)
                # The minimal display config uses this fallback. The distribution's
                # generic tracer already provides the same event-tracing UAPI.
                grep -Fxq CONFIG_EVENT_TRACING=y "$out/.config" || exit 1 ;;
            CONFIG_*=*) grep -Fxq "$line" "$out/.config" || { echo "Missing $line" >&2; exit 1; } ;;
            '# CONFIG_'*' is not set') sym=${line#\# }; sym=${sym%% *}; ! grep -q "^${sym}=" "$out/.config" || exit 1 ;;
        esac
    done < "$frag"
done
for symbol in DRM_MSM_KMS_FBDEV FRAMEBUFFER_CONSOLE_DETECT_PRIMARY; do
    grep -Fxq "CONFIG_$symbol=y" "$out/.config"
done
if [[ $out == kernel-out ]]; then
    linux/scripts/diffconfig main-boot/kernel.config "$out/.config" > kernel-config.diff
    for symbol in DRM_MSM VIDEO_QCOM_VENUS ATH11K_PCI BATTERY_QCOM_FG CHARGER_QCOM_SMB5 \
        USB_CONFIGFS_NCM USB_CONFIGFS_ACM USB_ROLE_SWITCH USB_DWC3_DUAL_ROLE SCSI_UFS_QCOM EXT4_FS \
        SECURITY_APPARMOR OVERLAY_FS BRIDGE NETFILTER BTRFS_FS BTRFS_FS_POSIX_ACL; do
        grep -Eq "^CONFIG_${symbol}=[ym]$" "$out/.config" || { echo "Missing CONFIG_$symbol" >&2; exit 1; }
    done
fi
for symbol in BTRFS_FS CRYPTO_XXHASH CRYPTO_BLAKE2B RAID6_PQ XOR_BLOCKS BLK_DEV_LOOP; do
    grep -Fxq "CONFIG_${symbol}=y" "$out/.config" || {
        echo "Btrfs must be built into the kernel; CONFIG_${symbol} is not y" >&2
        exit 1
    }
done
dtb=$out/arch/arm64/boot/dts/qcom/sm8250-xiaomi-umi-csot.dtb
make -C linux O="$work/$out" LOCALVERSION="$localversion" -j"${JOBS:-$(nproc)}" qcom/sm8250-xiaomi-umi-csot.dtb
python3 "$here/verify-dtb.py" "$dtb" "$rate" "$CSOT_LAB" "$rx_profile"
python3 "$here/abl-display.py" "$dtb" "$out/boot-csot.dtb" display-inputs/kernel/umi-csot-dtbo-targets.txt main-boot/dtb
make -C linux O="$work/$out" LOCALVERSION="$localversion" -j"${JOBS:-$(nproc)}" Image modules
if find "$out" -type f -name 'btrfs.ko*' -print -quit | grep -q .; then
    echo 'Btrfs was built as a module; expected built-in CONFIG_BTRFS_FS=y' >&2
    exit 1
fi
(cd "$out"; sha256sum arch/arm64/boot/Image boot-csot.dtb native-display-cmdline > SHA256SUMS)
printf '%s\n' "$rate" > "$out/refresh"
printf '%s\n' "$display_source_rev" > "$out/display-source.sha"
if [[ $out == csot-out ]]; then printf '%s\n' "$lab_source_rev" > "$out/lab-source.sha"; fi
if [[ $out == csot-out ]]; then
    printf '%s\n' "$rx_profile" > "$out/wireless-rx-profile"
    if [[ $rx_profile != off ]]; then
        find board-lab-inputs/kernel/power -type f -print | sort | xargs sha256sum \
            > "$out/wireless-rx-source.sha256"
    fi
fi
