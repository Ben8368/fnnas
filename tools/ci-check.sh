#!/usr/bin/env bash
# Host-only PR regressions. Run from the repository root on Linux.
set -euo pipefail
while IFS= read -r -d '' file; do
    if [[ -f "$file" ]]; then bash -n "$file"; fi
done < <(git ls-files -z -- ':(glob)make-fnnas/qualcomm/sm8250/**/*.sh' ':(glob)tools/**/*.sh' renas rekernel refnos rekernel-umi 'tools/legacy/rootfs-build/config/boards/*.conf' \
    'tools/legacy/rootfs-build/packages/bsp/xiaomi-umi/*' ':!*.service' \
    'make-fnnas/fnnas-files/different-files/xiaomi-umi/rootfs/usr/local/bin/*' 'make-fnnas/fnnas-files/different-files/xiaomi-umi/rootfs/usr/local/sbin/*' \
    'make-fnnas/fnnas-files/different-files/xiaomi-umi/rootfs/usr/local/lib/umi/*')
[[ $(bash rekernel -b xiaomi-umi query locked) == "$(bash rekernel-umi query locked)" ]]
[[ $(bash renas -b xiaomi-umi kernel query --help) == "$(bash refnos kernel query --help)" ]]
bash renas -b xiaomi-umi -k 6.18.y -a true kernel query --help >/dev/null
if bash renas -b xiaomi-umi -k 6.18.y -a false kernel query --help; then
    echo 'A fixed Umi kernel selection must name a concrete version.' >&2
    exit 1
fi
bash renas -b xiaomi-umi build --help
bash renas -r Ben8368/fnnas -k 6.18.y --Autokernel true -b xiaomi-umi -- native --help
bash renas -b xiaomi-umi native-debug --help
if bash renas -s 6000 -b xiaomi-umi native --help; then
    echo 'An unsupported upstream option reached the Umi backend.' >&2
    exit 1
fi
python3 -B -m unittest discover -v -s make-fnnas/qualcomm/sm8250/boot/abl-android-v2/tests
python3 -B -m unittest discover -v -s make-fnnas/qualcomm/sm8250/scripts/tests -p test_kernel_release.py
bash make-fnnas/qualcomm/sm8250/scripts/tests/test_kernel_patches.sh
python3 -B -m unittest discover -v -s tools/legacy/rootfs-build/tests
bash tools/legacy/rootfs-build/tests/test-serial-enrollment.sh
bash tools/legacy/rootfs-build/tests/test-charge-limit.sh
