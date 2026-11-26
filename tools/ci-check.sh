#!/usr/bin/env bash
# Host-only PR regressions. Run from the repository root on Linux.
set -euo pipefail
while IFS= read -r -d '' file; do
    if [[ -f "$file" ]]; then bash -n "$file"; fi
done < <(git ls-files -z -- ':(glob)make-fnos/**/*.sh' ':(glob)tools/**/*.sh' refnos rekernel-umi 'tools/legacy/rootfs-build/config/boards/*.conf' \
    'tools/legacy/rootfs-build/packages/bsp/xiaomi-umi/*' ':!*.service' \
    'make-fnos/fnos-files/different-files/xiaomi-umi/rootfs/usr/local/bin/*' 'make-fnos/fnos-files/different-files/xiaomi-umi/rootfs/usr/local/sbin/*' \
    'make-fnos/fnos-files/different-files/xiaomi-umi/rootfs/usr/local/lib/umi/*')
python3 -B -m unittest discover -v -s make-fnos/boot/abl-android-v2/tests
python3 -B -m unittest discover -v -s tools/legacy/rootfs-build/tests
bash tools/legacy/rootfs-build/tests/test-serial-enrollment.sh
bash tools/legacy/rootfs-build/tests/test-charge-limit.sh
