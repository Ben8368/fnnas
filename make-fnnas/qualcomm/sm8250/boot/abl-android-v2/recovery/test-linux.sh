#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
# ARM64 userspace/host regressions; never boot a device.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if (($#)); then
    # Kernel build passes its final .config, not a baseline seed. Recovery has
    # no module tree, so these capabilities must be built into this kernel.
    for feature in BLK_DEV_INITRD RD_GZIP DEVTMPFS CONFIGFS_FS USB_GADGET USB_CONFIGFS USB_CONFIGFS_ACM USB_DWC3 USB_DWC3_QCOM USB_DWC3_DUAL_ROLE; do
        if ! grep -Fxq "CONFIG_$feature=y" "$1"; then
            echo "Missing built-in Recovery support: CONFIG_$feature" >&2
            exit 1
        fi
    done
    grep -Fxq 'CONFIG_CMDLINE=""' "$1"
fi
scratch=$(mktemp -d)
trap 'rm -rf -- "$scratch"' EXIT
cd "$here"
go version
GOTOOLCHAIN=local CGO_ENABLED=0 GOOS=linux GOARCH=arm64 GOARM64=v8.0 \
    go test -c -o "$scratch/peer" init_linux.go protocol.go init_linux_test.go protocol_test.go
qemu-aarch64-static "$scratch/peer" -test.v
UMI_RECOVERY_PEER="$scratch/peer" "${RECOVERY_PYTHON:-/usr/bin/python3}" -B -m unittest discover -v -s ../tests -p test_umi_recovery.py
