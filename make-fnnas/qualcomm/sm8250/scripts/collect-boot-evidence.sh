#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
# Run on the installed Umi through a trusted local administrator session.
# Only reads live state and writes the report to stdout. Keep the raw report private.
set -u
export LC_ALL=C SYSTEMD_COLORS=0
boot=${1:-0}
if [[ ${1:-} == --help ]]; then
    echo 'Usage: sudo bash collect-boot-evidence.sh [0|-1|BOOT_ID]'
    exit 0
fi
if (( $# > 1 )) || [[ ! $boot =~ ^(0|-[1-9][0-9]*|[0-9a-fA-F]{32})$ ]]; then
    echo 'Specify 0 (this boot), a negative boot offset, or a 32-digit boot ID.' >&2
    exit 2
fi
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
root_gpt() {
    local source parent
    source=$(findmnt -n --nofsroot -o SOURCE /) || return
    [[ -b $source ]] || { echo "Root source is not a block device: $source"; return 1; }
    parent=$(lsblk -dnpo PKNAME -- "$source") || return
    [[ -b $parent ]] || { echo "No single parent device for $source"; return 1; }
    sfdisk --json -- "$parent"
}
printf 'Requested journal boot: %s; live-state sections describe the current boot.\n' "$boot"
section 'Device wall clock' date --iso-8601=seconds
section 'Current boot ID' cat /proc/sys/kernel/random/boot_id
section 'Uptime (seconds)' cat /proc/uptime
section 'Kernel release' uname -r
section 'Journal boot index' journalctl --list-boots --no-pager
section 'Kernel journal (selected boot, monotonic)' journalctl -b "$boot" -k --no-pager -o short-monotonic
section 'Kernel ring buffer (current)' dmesg --color=never
section 'System journal (selected boot, monotonic)' journalctl -b "$boot" --no-pager -o short-monotonic
section 'Journal warning or higher (selected boot)' journalctl -b "$boot" -p warning --no-pager -o short-monotonic
section 'Failed units (current)' systemctl --failed --full --no-pager
section 'Journal disk usage' journalctl --disk-usage
section 'Journald configuration' systemd-analyze cat-config systemd/journald.conf
section 'Block devices (bytes) and SCSI addresses' lsblk --json --bytes -o NAME,KNAME,PATH,TYPE,SIZE,MODEL,HCTL,PARTLABEL,FSTYPE,MOUNTPOINTS
section 'Root mount' findmnt -n --notruncate -o SOURCE,TARGET,FSTYPE,OPTIONS --target /
section 'Root filesystem capacity (bytes)' df -B1 -T -- /
section 'Btrfs capacity (bytes)' btrfs filesystem usage -b /
section 'Kernel registered filesystems' cat /proc/filesystems
section 'Btrfs device counters (not reset)' btrfs device stats /
section 'Root disk partition table (read-only)' root_gpt
section 'Clock status' timedatectl status
printf '\n===== COLLECTION END (status=%s) =====\n' "$failed"
exit "$failed"
