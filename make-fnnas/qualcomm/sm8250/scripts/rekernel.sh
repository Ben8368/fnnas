#!/usr/bin/env bash
set -euo pipefail
scripts=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
case ${1:-} in
    --help|-h)
        printf 'Usage: [UMI_KERNEL_VERSION=locked|auto|6.18.x] rekernel -b xiaomi-umi MAIN_BOOT_IMG NEW_LINUX_WORK_DIR\n'
        printf '       rekernel -b xiaomi-umi query [locked|auto|6.18.x]\n'
        exit 0
        ;;
    query)
        if (($# > 2)); then
            echo 'Usage: rekernel -b xiaomi-umi query [locked|auto|6.18.x]' >&2
            exit 2
        fi
        source "$scripts/../kernel/source.sh"
        resolve_umi_linux "${2:-auto}"
        exit
        ;;
esac
exec bash "$scripts/build-kernel.sh" "$@"
