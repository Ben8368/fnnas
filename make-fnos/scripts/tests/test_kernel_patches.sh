#!/usr/bin/env bash
# Exercise the upstream priority policy without fetching Linux.
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
source "$repo/make-fnos/kernel/source.sh"
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
linux=$work/linux
git init -q "$linux"
git -C "$linux" config user.name Umi-CI
git -C "$linux" config user.email umi-ci@example.invalid
mkdir -p "$linux/drivers" "$linux/arch/arm64/boot/dts" "$work/driver-patches" "$work/dts-patches"
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
git -C "$linux" diff -- "$board" > "$work/dts-patches/9999-board.patch"
git -C "$linux" restore .

printf 'upstream driver\n' > "$linux/drivers/example.c"
printf 'upstream board\n' > "$linux/$board"
git -C "$linux" commit -qam upstream
selected=$(git -C "$linux" rev-parse HEAD)
apply_umi_armbian_patches "$linux" "$selected" "$work/driver-patches" > "$work/driver.log"
grep -Fq 'Keeping upstream changes and skipping 9998-driver.patch' "$work/driver.log"
grep -Fxq 'upstream driver' "$linux/drivers/example.c"
grep -Fxq 'original helper' "$linux/drivers/helper.c"

if apply_umi_armbian_patches "$linux" "$selected" "$work/dts-patches" > "$work/board.log"; then
    echo 'An upstream board conflict must stop the candidate build.' >&2
    exit 1
fi
grep -Fxq 'upstream board' "$linux/$board"
git -C "$linux" diff --exit-code
echo 'PASS: upstream driver changes take priority and board conflicts stop the build'
