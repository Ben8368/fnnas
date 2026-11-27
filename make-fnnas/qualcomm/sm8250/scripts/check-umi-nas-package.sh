#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
# Inspect the actual installable kernel package, not just its kernel .config.
set -euo pipefail
package=${1:?Umi kernel package}
release=$(< "${2:?kernel.release from the same build}")
[[ $release =~ ^6\.18\.[0-9]+-csot(60|90)-sm8250$ ]]
archive_root=lib/modules/$release/kernel
scratch=$(mktemp -d)
trap 'rm -f -- "$scratch/module.ko"; rmdir -- "$scratch"' EXIT
for path in fs/nfsd/nfsd.ko net/openvswitch/openvswitch.ko; do
    # Stream only the requested member. No paths/symlinks from the archive
    # are used as local destinations.
    tar -xOzf "$package" -- "$archive_root/$path" > "$scratch/module.ko"
    magic=$(modinfo -F vermagic "$scratch/module.ko")
    if [[ ${magic%% *} != "$release" ]]; then
        printf 'Wrong or missing vermagic for %s: %s\n' "$path" "$magic" >&2
        exit 1
    fi
    printf '%s: %s; sha256=%s\n' "$path" "$magic" "$(sha256sum < "$scratch/module.ko" | cut -d ' ' -f1)"
done
