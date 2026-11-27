#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
# Convert a raw Umi rootfs image to an Android sparse image for fastboot.
# Usage: make-sparse-image.sh ROOTFS_IMG [SPARSE_IMG]
set -euo pipefail

if (($# < 1 || $# > 2)); then
    echo "Usage: $0 ROOTFS_IMG [SPARSE_IMG]" >&2
    exit 2
fi

resolve() {
    local path=$1
    (cd -- "$(dirname -- "$path")" && printf '%s/%s\n' "$PWD" "$(basename -- "$path")")
}

raw=$(resolve "$1")
[[ -f $raw && ! -L $raw ]] || { echo "Not a regular image: $raw" >&2; exit 1; }
if [[ $raw == *.img ]]; then
    default=${raw%.img}.simg
else
    default=$raw.simg
fi
out=$(resolve "${2:-$default}")
[[ $out != "$raw" && ! -e $out && ! -L $out ]] ||
    { echo "Refusing to overwrite: $out" >&2; exit 1; }
command -v img2simg >/dev/null 2>&1 || {
    echo 'img2simg is required (Debian/Ubuntu: android-sdk-libsparse-utils; macOS: run in a Linux VM).' >&2
    exit 1
}

trap 'rm -f -- "$out"' ERR
img2simg "$raw" "$out"
python3 - "$out" <<'PY'
import pathlib
import sys

magic = pathlib.Path(sys.argv[1]).read_bytes()[:4]
if magic != bytes.fromhex("3aff26ed"):
    raise SystemExit(f"Not an Android sparse image: {sys.argv[1]}")
PY
trap - ERR

if command -v sha256sum >/dev/null 2>&1; then
    digest=$(sha256sum "$out" | awk '{print $1}')
else
    digest=$(shasum -a 256 "$out" | awk '{print $1}')
fi
printf 'sparse=%s bytes=%s sha256=%s\n' "$out" "$(wc -c < "$out")" "$digest"
