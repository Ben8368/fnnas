#!/usr/bin/env bash
set -euo pipefail
scripts=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)

# Accept the common image builder's kernel options before the Umi subcommand.
series=
automatic=
release_args=()
while [[ ${1:-} == -* && $1 != --help && $1 != -h ]]; do
    if (($# < 2)); then echo "Missing value for $1" >&2; exit 2; fi
    case $1 in
        -k|--Kernel) series=$2 ;;
        -a|--Autokernel) automatic=$2 ;;
        -r|--kernelRepository) release_args+=(--repo "${2#https://github.com/}") ;;
        *) echo "Unsupported Qualcomm option: $1" >&2; exit 2 ;;
    esac
    shift 2
done
if [[ -n $series || -n $automatic ]]; then
    series=${series:-6.18.y}
    if [[ $series != 6.18.y && ! $series =~ ^6\.18\.(0|[1-9][0-9]*)$ ]]; then
        echo 'Select 6.18.y or a concrete Umi kernel version (6.18.x).' >&2
        exit 2
    fi
    case ${automatic:-true} in
        true|yes) release_args+=(--version auto) ;;
        false|no)
            if [[ $series == 6.18.y ]]; then echo 'With -a false, specify a concrete 6.18.x version.' >&2; exit 2; fi
            release_args+=(--version "$series")
            ;;
        *) echo 'Use -a true or -a false.' >&2; exit 2 ;;
    esac
fi
if ((${#release_args[@]})); then
    case ${1:-}:${2:-} in
        kernel:query|kernel:fetch|boot:*|build:*|native:*) set -- "$@" "${release_args[@]}" ;;
        *) echo 'Kernel options apply to kernel query, kernel fetch, boot, build or native.' >&2; exit 2 ;;
    esac
fi
case "${1:-}" in
    inspect)
        shift
        exec bash "$scripts/inspect-base.sh" "$@"
        ;;
    extract)
        shift
        exec bash "$scripts/extract-rootfs.sh" "$@"
        ;;
    download)
        shift
        exec bash "$scripts/download-base.sh" "$@"
        ;;
    kernel)
        shift
        exec "${FNOS_PYTHON:-python3}" "$scripts/kernel-release.py" "$@"
        ;;
    boot)
        shift
        exec bash "$scripts/build-released-boot.sh" "$@"
        ;;
    overlay)
        shift
        exec bash "$scripts/apply-files.sh" "$@"
        ;;
    native)
        shift
        exec bash "$scripts/build-native.sh" "$@"
        ;;
    native-debug)
        shift
        exec bash "$scripts/build-native.sh" --debug "$@"
        ;;
    native-local-debug)
        shift
        exec bash "$scripts/build-native.sh" --local-debug "$@"
        ;;
    native-acceptance)
        shift
        exec bash "$scripts/build-acceptance.sh" "$@"
        ;;
    build)
        shift
        exec bash "$scripts/build-image.sh" "$@"
        ;;
    -h|--help|'')
        printf 'Usage: renas -b xiaomi-umi [-k VERSION] [-a true|false] [-r OWNER/REPO] {inspect|download|extract|kernel|overlay|boot|build|native|native-debug|native-local-debug|native-acceptance} --help\n'
        ;;
    *)
        printf 'Unknown Xiaomi Umi image command: %s\n' "$1" >&2
        exit 2
        ;;
esac
