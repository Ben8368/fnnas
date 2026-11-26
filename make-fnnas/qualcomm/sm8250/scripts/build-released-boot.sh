#!/usr/bin/env bash
# Build Android v2 boot from a promoted kernel and a prepared RootFS.
set -euo pipefail
usage() {
    printf 'Usage: refnos boot MAIN_BOOT_IMG STAGED_ROOTFS ROOT_UUID NEW_WORK_DIR [--refresh 60|90] [--version auto|6.18.x] [--repo OWNER/REPO]\n'
}
if [[ ${1:-} == --help || ${1:-} == -h ]]; then usage; exit 0; fi
if (($# < 4)); then usage >&2; exit 2; fi
scripts=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
output=$4
[[ ! -e $output && ! -L $output ]] || exit 1
scratch=$(mktemp -d)
trap 'rm -rf -- "$scratch"' EXIT
inputs=("${@:1:4}")
shift 4
"${FNOS_PYTHON:-python3}" -B "$scripts/kernel-release.py" fetch "$scratch/kernel" "$@"
bash "$scripts/build-boot-pair.sh" "${inputs[@]}" "$scratch/kernel"
