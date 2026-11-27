#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
# Run on the installed Umi through a trusted local administrator session.
# Only reads live state and writes the report to stdout. Keep the raw report private.
set -u
export LC_ALL=C SYSTEMD_COLORS=0
if (( EUID != 0 )); then
    echo 'Use sudo from an authorized administrator session for complete kernel and system logs.' >&2
    exit 2
fi
failed=0
section() {
    local title=$1 status=0
    shift
    printf '\n===== %s =====\n' "$title"
    "$@" 2>&1 || status=$?
    if (( status )); then
        printf '[collection failed: exit %s]\n' "$status"
        failed=1
    fi
}
section 'Device wall clock' date --iso-8601=seconds
section 'Boot ID' cat /proc/sys/kernel/random/boot_id
section 'Uptime (seconds)' cat /proc/uptime
section 'Kernel release' uname -r
section 'Kernel journal (this boot, monotonic)' journalctl -b -k --no-pager -o short-monotonic
section 'Kernel ring buffer (current)' dmesg --color=never
section 'System journal (this boot, monotonic)' journalctl -b --no-pager -o short-monotonic
section 'Failed units' systemctl --failed --no-pager
section 'Block devices (bytes) and SCSI addresses' lsblk -b -o NAME,KNAME,PATH,TYPE,SIZE,MODEL,HCTL,PARTLABEL,FSTYPE,MOUNTPOINTS
section 'Root mount' findmnt -no SOURCE,TARGET,FSTYPE,OPTIONS /
section 'Root filesystem capacity (bytes)' df -BT1 /
section 'Btrfs capacity (bytes)' btrfs filesystem usage -b /
section 'Clock status' timedatectl status
exit "$failed"
