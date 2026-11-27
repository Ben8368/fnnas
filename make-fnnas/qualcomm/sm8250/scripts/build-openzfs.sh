#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
# Build the external modules against the same configured tree as the Umi Image.
set -euo pipefail
linux=$(realpath -e -- "${1:?Linux source}")
obj=$(realpath -e -- "${2:?kernel build}")
module_root=$(realpath -e -- "${3:?staged modules root}")
work=$(realpath -m -- "${4:?new work directory}")
mkdir -- "$work"
cd "$work"
release=$(< "$obj/include/config/kernel.release")
[[ $release =~ ^6\.18\.[0-9]+(-csot(60|90)-sm8250)$ ]]
export LOCALVERSION=${BASH_REMATCH[1]} ARCH=arm64 CROSS_COMPILE=${CROSS_COMPILE:-aarch64-linux-gnu-}
# Match the pinned native ARM64 donor's openzfs-zfsutils 2.4.1-1.
archive=zfs-2.4.1.tar.gz
digest=c17b69770f0023154f578eb8c7536a70f07d6a3bb0bd38f04fa0e8811c3c1390
if [[ -n ${UMI_ZFS_ARCHIVE:-} ]]; then
    cp -- "$UMI_ZFS_ARCHIVE" "$archive"
else
    curl --fail --location --retry 3 -o "$archive" "https://github.com/openzfs/zfs/releases/download/zfs-2.4.1/$archive"
fi
printf '%s  %s\n' "$digest" "$archive" | sha256sum -c -
tar -xzf "$archive"
cd zfs-2.4.1
./configure --host="${CROSS_COMPILE%-}" --build="$(gcc -dumpmachine)" --with-config=kernel --with-linux="$linux" --with-linux-obj="$obj"
make -j"${JOBS:-$(nproc)}"
target="$module_root/lib/modules/$release/extra/openzfs"
mkdir -p -- "$target"
for name in spl zfs; do
    file="module/$name.ko"
    magic=$(modinfo -F vermagic "$file")
    [[ ${magic%% *} == "$release" && $(modinfo -F name "$file") == "$name" ]]
    "${CROSS_COMPILE}strip" --strip-debug -o "$target/$name.ko" "$file"
    sha256sum "$target/$name.ko"
done
# Keep corresponding upstream source and license notices with the modules.
install -m644 ../"$archive" "$target/"
install -m644 LICENSE COPYRIGHT NOTICE AUTHORS "$target/"
depmod -b "$module_root" "$release"
modprobe -d "$module_root" -S "$release" --show-depends zfs
