#!/usr/bin/env bash
# Exercise the upstream priority policy without fetching Linux.
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../../../.." && pwd)
source "$repo/make-fnnas/qualcomm/sm8250/kernel/source.sh"
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
linux=$work/linux
git init -q "$linux"
git -C "$linux" config user.name Umi-CI
git -C "$linux" config user.email umi-ci@example.invalid
mkdir -p "$linux/drivers" "$linux/arch/arm64/boot/dts" "$work/driver-patches" "$work/board-patches"
board=arch/arm64/boot/dts/umi.dts
printf 'original driver\n' > "$linux/drivers/example.c"
printf 'original helper\n' > "$linux/drivers/helper.c"
printf 'original board\n' > "$linux/$board"
git -C "$linux" add .
git -C "$linux" commit -qm baseline
umi_linux_locked_commit=$(git -C "$linux" rev-parse HEAD)

printf 'downstream driver\n' > "$linux/drivers/example.c"
printf 'downstream helper\n' > "$linux/drivers/helper.c"
printf 'downstream board\n' > "$linux/$board"
git -C "$linux" diff -- drivers > "$work/driver-patches/9998-driver.patch"
git -C "$linux" diff -- "$board" > "$work/board-patches/9999-board.patch"
git -C "$linux" restore .

printf 'upstream driver\n' > "$linux/drivers/example.c"
printf 'upstream board\n' > "$linux/$board"
git -C "$linux" commit -qam upstream
selected=$(git -C "$linux" rev-parse HEAD)
for series in driver board; do
    if apply_umi_armbian_patches "$linux" "$selected" "$work/$series-patches" "$work/manifest.tsv"; then
        echo "Unexpected success for unknown $series conflict" >&2
        exit 1
    fi
    grep -q $'\tconflict\t' "$work/manifest.tsv"
done
grep -Fxq 'upstream driver' "$linux/drivers/example.c"
grep -Fxq 'original helper' "$linux/drivers/helper.c"
grep -Fxq 'upstream board' "$linux/$board"
git -C "$linux" diff --exit-code
git -C "$linux" checkout -q --detach "$umi_linux_locked_commit"
apply_umi_armbian_patches "$linux" "$umi_linux_locked_commit" "$work/driver-patches" "$work/manifest.tsv"
grep -q $'\tapplied\t' "$work/manifest.tsv"
apply_umi_armbian_patches "$linux" "$umi_linux_locked_commit" "$work/driver-patches" "$work/manifest.tsv"
grep -q $'\talready-present\t' "$work/manifest.tsv"
echo 'PASS: strict patch series and provenance'
