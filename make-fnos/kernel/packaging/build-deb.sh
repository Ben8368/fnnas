#!/usr/bin/env bash
# Package a staged ARM64 kernel or DTB tree with numeric root ownership.
set -euo pipefail
if (($# != 4)); then
    echo "Usage: $0 PACKAGE VERSION STAGING NEW_OUTPUT_DEB" >&2
    exit 2
fi
name=$1
version=$2
staging=$(realpath -e -- "$3")
[[ ! -L $4 ]] || { echo "Package path is a symlink: $4" >&2; exit 1; }
output=$(realpath -m -- "$4")
[[ $name =~ ^linux-(image|dtb)-[a-z0-9.+-]+$ && -d $staging && $staging != / ]]
dpkg --validate-version "$version"
[[ ! -e $output && $output != "$staging/"* ]]
scratch=$(mktemp -d -- "$(dirname -- "$output")/.fnos-deb.XXXXXX")
trap 'rm -rf -- "$scratch"' EXIT
mkdir "$staging/DEBIAN"
trap 'rm -rf -- "$scratch" "$staging/DEBIAN"' EXIT
cat > "$staging/DEBIAN/control" <<CONTROL
Package: $name
Version: $version
Architecture: arm64
Section: kernel
Priority: optional
Maintainer: fnos-xiaomi-umi maintainers
Description: Xiaomi Mi 10 Linux kernel package ($name)
CONTROL
(cd "$staging"; find . -type f ! -path './DEBIAN/*' -printf '%P\0' | LC_ALL=C sort -z | xargs -0 -r md5sum) > "$staging/DEBIAN/md5sums"
dpkg-deb --root-owner-group -Zzstd --build "$staging" "$scratch/package.deb"
ln -T -- "$scratch/package.deb" "$output"
