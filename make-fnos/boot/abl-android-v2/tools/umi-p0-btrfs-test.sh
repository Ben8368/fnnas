#!/bin/sh
# RAM-only Btrfs P0 probe. rdinit bypasses the released init and rootfs.
export PATH=/sbin:/usr/sbin:/bin:/usr/bin
umask 077
mkdir -p /proc /sys /dev /run /mnt/umi-btrfs
mount -t devtmpfs devtmpfs /dev
report=/run/umi-p0-btrfs.log
log() {
    printf 'UMI_P0_BTRFS: %s\n' "$*" >>"$report"
    printf '<5>UMI_P0_BTRFS: %s\n' "$*" >/dev/kmsg
    printf 'UMI_P0_BTRFS: %s\n' "$*" >/dev/tty0 2>/dev/null || :
}
fail() {
    log "FAIL: $*"
    exit 1
}
mount -t tmpfs -o size=320m tmpfs /run || fail tmpfs_mount

log "START kernel=$(uname -r) ram_only=1 storage_devices=untouched"
mount -t proc proc /proc || fail proc_mount
mount -t sysfs sysfs /sys || fail sysfs_mount
(
    mkdir -p /sys/kernel/config
    mount -t configfs configfs /sys/kernel/config || exit 1
    g=/sys/kernel/config/usb_gadget/umi_p0_btrfs
    c=$g/configs/c.1
    f=$g/functions/acm.usb0
    mkdir "$g" || exit 1
    printf '0x1d6b\n' >"$g/idVendor" || exit 1
    printf '0x0104\n' >"$g/idProduct" || exit 1
    printf '0xef\n' >"$g/bDeviceClass" || exit 1
    printf '0x02\n' >"$g/bDeviceSubClass" || exit 1
    printf '0x01\n' >"$g/bDeviceProtocol" || exit 1
    mkdir -p "$g/strings/0x409" "$c" "$f" || exit 1
    printf 'UMI Btrfs RAM P0\n' >"$g/strings/0x409/product" || exit 1
    printf 'Local test\n' >"$g/strings/0x409/manufacturer" || exit 1
    printf 'UMI-P0-BTRFS\n' >"$g/strings/0x409/serialnumber" || exit 1
    ln -s "$f" "$c/acm.usb0" || exit 1
    for delay in 1 1 1 1 1 1 1 1; do
        for udc in /sys/class/udc/*; do
            [ -e "$udc" ] || continue
            if printf '%s\n' "${udc##*/}" >"$g/UDC"; then
                log "USB ACM ready udc=${udc##*/}"
                exit 0
            fi
        done
        sleep "$delay"
    done
    log 'USB ACM unavailable; results remain in pstore/kmsg'
) &
(
    while :; do
        if [ -c /dev/ttyGS0 ]; then
            {
                printf 'UMI_P0_BTRFS_REPORT_BEGIN\n'
                cat "$report"
                printf 'UMI_P0_BTRFS_REPORT_END\n'
            } >/dev/ttyGS0 2>/dev/null
        fi
        sleep 2
    done
) &
xxhash_seen=0
while IFS= read -r line; do
    case "$line" in *xxhash64*) xxhash_seen=1;; esac
done </proc/crypto
[ "$xxhash_seen" = 1 ] || fail crypto_xxhash_not_registered
log 'PASS: xxhash64 crypto implementation is available'
grep_btrfs=0
while IFS= read -r line; do
    case "$line" in *btrfs*) grep_btrfs=1;; esac
done </proc/filesystems
[ "$grep_btrfs" = 1 ] || fail btrfs_not_registered
if grep -q '^btrfs ' /proc/modules; then fail btrfs_must_be_builtin; fi
log 'PASS: Btrfs is registered as a built-in filesystem'

# Keep the only test block device in initramfs RAM; never enumerate or mount
# physical phone storage. The image itself is embedded in this initramfs.
[ -f /umi-p0-test.btrfs ] || fail missing_ram_test_volume
dd if=/umi-p0-test.btrfs of=/run/umi-p0-test.btrfs bs=1048576 || fail copy_volume_to_ram
losetup /dev/loop0 /run/umi-p0-test.btrfs || fail loop_attach
loop=/dev/loop0
case "$loop" in /dev/loop*) ;; *) fail "unexpected_loop_device=$loop";; esac
log "PASS: RAM image attached loop=$loop"
mount -t btrfs -o compress=zstd:1 "$loop" /mnt/umi-btrfs || fail btrfs_mount_zstd
log 'PASS: Btrfs mounted with compress=zstd:1'

printf 'umi-p0-ram-write-read-ok\n' >/mnt/umi-btrfs/marker || fail write_marker
dd if=/dev/zero of=/mnt/umi-btrfs/zstd-data.bin bs=1048576 count=8 || fail write_zstd_data
sync
IFS= read -r marker </mnt/umi-btrfs/marker || fail read_marker
[ "$marker" = 'umi-p0-ram-write-read-ok' ] || fail marker_mismatch
log 'PASS: Btrfs read/write and sync'

btrfs filesystem sync /mnt/umi-btrfs || fail btrfs_sync
btrfs inspect-internal dump-tree -t 5 "$loop" >/run/umi-p0-tree.txt || fail dump_root_tree
zstd_seen=0
while IFS= read -r line; do
    case "$line" in *'compression 3 (zstd)'*) zstd_seen=1;; esac
done </run/umi-p0-tree.txt
[ "$zstd_seen" = 1 ] || fail zstd_extent_not_found
log 'PASS: on-disk extent metadata confirms ZSTD compression'

btrfs subvolume create /mnt/umi-btrfs/p0-source || fail subvolume_create
printf 'snapshot-content-v1\n' >/mnt/umi-btrfs/p0-source/snapshot.txt || fail subvolume_write
btrfs subvolume snapshot -r /mnt/umi-btrfs/p0-source /mnt/umi-btrfs/p0-snapshot || fail snapshot_create
IFS= read -r snapshot_content </mnt/umi-btrfs/p0-snapshot/snapshot.txt || fail snapshot_read
[ "$snapshot_content" = 'snapshot-content-v1' ] || fail snapshot_content_mismatch
ro_state=$(btrfs property get -ts /mnt/umi-btrfs/p0-snapshot ro) || fail snapshot_ro_query
case "$ro_state" in *ro=true*) ;; *) fail "snapshot_not_readonly=$ro_state";; esac
log 'PASS: subvolume create and read-only snapshot verified'

btrfs filesystem sync /mnt/umi-btrfs || fail final_sync
log 'RESULT: PASS all RAM-only Btrfs P0 checks'
log 'No physical storage was mounted or written; rebooting to installed Android in 25 seconds'
sleep 25
reboot -n
log 'FAIL: reboot command returned'
while :; do sleep 5; done
