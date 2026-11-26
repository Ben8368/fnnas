#!/usr/bin/env bash
# Build a kernel and optionally the Debian baseline on a disposable Ubuntu runner.
set -euo pipefail
profile=${1:?release, csot-60 or csot-90}
with_debian=${WITH_DEBIAN_BASELINE:-true}
case $profile in release|csot-60|csot-90|lab-60|lab-90) ;; *) exit 2 ;; esac
work=$(realpath -m -- "${2:?new native work directory}")
mkdir -- "$work"
mkdir "$work/evidence"
exec > >(tee "$work/evidence/build.log") 2>&1
release=https://github.com/misaka-link/umi-linux/releases/download/v2026-09-27
boot=boot-umi-csot-ovf-wifi6-gpu-oc-final.img
archive=umi-system-opensource-2026-09-27.tar.gz
if [[ -n ${UMI_BASE_INPUT_DIR:-} ]]; then
    base_inputs=$(realpath -e -- "$UMI_BASE_INPUT_DIR")
    [[ -d $base_inputs ]] || { echo "Not a directory: $base_inputs" >&2; exit 1; }
    fetch() {
        [[ -f $base_inputs/$1 ]] || { echo "Missing cached base input: $base_inputs/$1" >&2; exit 1; }
        cp -- "$base_inputs/$1" "$work/$1"
    }
else
    fetch() { curl --fail --location --retry 4 --retry-all-errors -o "$work/$1" "$release/$1"; }
fi
git rev-parse HEAD > "$work/evidence/project.sha"
aarch64-linux-gnu-gcc --version
unset CSOT_REFRESH CSOT_LAB
case $profile in
    release) export CSOT_REFRESH=60 ;;
    *) export CSOT_REFRESH=${profile#*-} ;;
esac
fetch "$boot"
if [[ $profile == lab-* ]]; then
    export CSOT_LAB=1
fi
if [[ $profile != lab-* && $with_debian == true ]]; then
    if [[ $(uname -m) != aarch64 ]]; then
        sudo systemctl restart systemd-binfmt
        grep -q '^flags: .*F' /proc/sys/fs/binfmt_misc/qemu-aarch64
    fi
    fetch "$archive"
fi
# The project builders verify source revisions and baseline SHA-256 before use.
bash rekernel -b xiaomi-umi "$work/$boot" "$work/kernel"
kernel_out=$work/kernel/kernel-out
if [[ $profile == lab-* ]]; then kernel_out=$work/kernel/csot-out; fi
install -m644 "$kernel_out/kernel-source.tsv" "$work/evidence/kernel-source.tsv"
read -r version _ < "$kernel_out/kernel-source.tsv"
if [[ $profile != lab-* && $with_debian == true ]]; then
    cp "$work/kernel/kernel-out/.config" "$work/evidence/kernel.config"
    sudo unshare --mount --propagation private bash tools/legacy/rootfs-build/assemble-release.sh \
        "$work/$boot" "$work/$archive" "$work/kernel" "$work/assembly"
    images=$work/assembly/images
    (cd "$images"; sha256sum -c SHA256SUMS.txt)
    make -s -C "$work/kernel/linux" O="$work/kernel/kernel-out" ARCH=arm64 \
        CROSS_COMPILE=aarch64-linux-gnu- INSTALL_HDR_PATH="$work/headers" headers_install
    aarch64-linux-gnu-gcc -Wall -Wextra -Werror -O2 -static -I"$work/headers/include" \
        -o "$work/umi-gpu-check" make-fnnas/qualcomm/sm8250/boot/abl-android-v2/tools/umi-gpu-check.c
    boot_name=boot-umi-csot-${CSOT_REFRESH}hz-$version.img
    python3 -B make-fnnas/qualcomm/sm8250/boot/abl-android-v2/tools/make-ram-probe.py "$images/$boot_name" \
        "$work/evidence/ram-probe-$boot_name" --gpu-check "$work/umi-gpu-check"
    install -m644 "$images/$boot_name" "$work/evidence/"
    cp "$images/SHA256SUMS.txt" "$work/assembly/dpkg-audit.txt" "$work/kernel/kernel-out/display-source.sha" "$work/kernel/kernel-config.diff" "$work/evidence/"
else
    output=$work/evidence/kernel
    for file in arch/arm64/boot/Image boot-csot.dtb native-display-cmdline \
        include/config/kernel.release .config SHA256SUMS; do
        install -Dm644 "$kernel_out/$file" "$output/$file"
    done
    (cd "$output"; sha256sum -c SHA256SUMS)
fi
if [[ $profile != lab-* && ${PACKAGE_UMI_KERNEL:-false} == true ]]; then
    if [[ $with_debian == true ]]; then
        module_root=$work/assembly/pkg-image
    else
        module_root=$work/kernel-modules
        krel=$(< "$kernel_out/include/config/kernel.release")
        make -s -C "$work/kernel/linux" O="$kernel_out" ARCH=arm64 \
            CROSS_COMPILE="${CROSS_COMPILE:-aarch64-linux-gnu-}" LOCALVERSION="-csot${CSOT_REFRESH}-sm8250" \
            -j"${JOBS:-$(nproc)}" INSTALL_MOD_PATH="$module_root" INSTALL_MOD_STRIP=1 modules_install
        rm -f "$module_root/lib/modules/$krel/build" "$module_root/lib/modules/$krel/source"
        depmod -b "$module_root" "$krel"
    fi
    python3 -B make-fnnas/qualcomm/sm8250/scripts/kernel-release.py pack "$kernel_out" "$module_root" "$work/evidence"
fi
