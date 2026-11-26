#!/bin/sh
# Runs as the RAM-only test PID 1, not in either release rootfs.
export PATH=/sbin:/usr/sbin:/bin:/usr/bin
# The release /init normally creates these. rdinit bypasses it; without
# mountpoints the probe could falsely report no UDC even with a working USB.
mkdir -p /proc /sys /dev /run
mount -t devtmpfs devtmpfs /dev
umask 077
report=/run/umi-ram-probe.log
log() {
    printf 'UMI_PROBE: %s\n' "$*" >>"$report"
    printf '<5>UMI_PROBE: %s\n' "$*" >/dev/kmsg
}

log "PID1 kernel=$(uname -r)"
proc_ok=0
sys_ok=0
if mount -t proc proc /proc && [ -r /proc/cmdline ]; then proc_ok=1; fi
if mount -t sysfs sysfs /sys && [ -d /sys/class ]; then sys_ok=1; fi
log "mounts proc=$proc_ok sysfs=$sys_ok"
# Independent of configfs, serial logging and root device presence. Klibc
# reboot uses the restart syscall; don't use busybox/systemd-only flags.
(
    sleep 35
    log 'restart deadline reached; rebooting to the installed system'
    reboot -n
    log 'reboot returned; trying sysrq-trigger'
    printf 'b\n' >/proc/sysrq-trigger
) &

if [ "$proc_ok" != 1 ] || [ "$sys_ok" != 1 ]; then
    log 'probe incomplete: not testing USB or root signature without proc and sysfs'
    while :; do sleep 5; done
fi

# The RAM probe bypasses udev. Use the same standard native backlight setting
# as the assembled rootfs and leave normal fbcon output on screen.
case "$(uname -r)" in
    *-csot60-sm8250|*-csot90-sm8250)
        (
            bl=/sys/class/backlight/ae94000.dsi.0
            for delay in 1 1 2 2 3 3; do
                driver=$(readlink "$bl/device/driver") || driver=
                if [ "${driver##*/}" = panel-xiaomi-umi-csot ] && [ "$(cat "$bl/max_brightness")" = 2047 ]; then
                    if printf '1500\n' >"$bl/brightness"; then
                        log "CSOT brightness=$(cat "$bl/actual_brightness")/2047"
                        printf '\nXiaomi Mi 10 CSOT - Linux %s\n' "$(uname -r)" >/dev/tty0
                    else
                        log 'CSOT brightness write failed'
                    fi
                    exit
                fi
                sleep "$delay"
            done
            log 'CSOT backlight did not register'
        ) &
        ;;
esac

# Read only a block-device signature when checking the expected root. Never
# assemble, unlock, mount, repair, initialize, or write any device filesystem.
(
    for x in $(cat /proc/cmdline); do
        case "$x" in
            root=UUID=*)
                uuid=${x#root=UUID=}
                if source=$(blkid -c /dev/null -U "$uuid" 2>/dev/null); then
                    log "expected root UUID=$uuid found on $source (not mounted)"
                else
                    log "expected root UUID=$uuid not found by blkid"
                fi
                ;;
        esac
    done
) &

setup_acm() (
    set -e
    stage=configfs
    log 'configuring ACM only (no serial shell)'
    # klibc dash only accepts trap number 0 for the exit trap.
    trap 'rc=$?; if [ "$rc" != 0 ]; then log "ACM failed stage=$stage rc=$rc"; fi' 0
    mkdir -p /sys/kernel/config
    mount -t configfs configfs /sys/kernel/config
    stage=descriptors
    g=/sys/kernel/config/usb_gadget/umi_probe
    c=$g/configs/c.1
    f=$g/functions/acm.usb0
    mkdir "$g"
    printf '0x1d6b\n' > "$g/idVendor"
    printf '0x0104\n' > "$g/idProduct"
    printf '0xef\n' > "$g/bDeviceClass"
    printf '0x02\n' > "$g/bDeviceSubClass"
    printf '0x01\n' > "$g/bDeviceProtocol"
    mkdir "$g/strings/0x409" "$c" "$f"
    printf 'UMI RAM-only probe\n' > "$g/strings/0x409/product"
    printf 'Local test\n' > "$g/strings/0x409/manufacturer"
    printf 'UMI-RAM-PROBE\n' > "$g/strings/0x409/serialnumber"
    stage=link
    ln -s "$f" "$c/acm.usb0"
    stage=udc
    log 'ACM function created; waiting for UDC'
    tries=0
    while [ "$tries" -lt 8 ]; do
        for x in /sys/class/udc/*; do
            [ -e "$x" ] || continue
            if printf '%s\n' "${x##*/}" > "$g/UDC"; then
                log "ACM bound to ${x##*/}"
                exit 0
            fi
        done
        tries=$((tries+1))
        sleep 1
    done
    log 'no available UDC after 8 seconds'
    exit 1
)

setup_acm &
# Read only the driver core's deferred-probe status; never inspect register or
# nvmem files in debugfs/sysfs (some devices do not tolerate those reads).
(
    if mount -t debugfs -o ro debugfs /sys/kernel/debug; then
        sleep 13
        while IFS= read -r line; do
            case "$line" in
                *usb*|*typec*|*dwc3*|*88e3000*|*charger*|*ae94000*|*ae00000*|*3d00000*|*soundwire*|*a94000*) log "deferred: $line" ;;
            esac
        done </sys/kernel/debug/devices_deferred
        for state in /sys/kernel/debug/dri/*/state; do
            [ -r "$state" ] || continue
            while IFS= read -r line; do
                case "$line" in
                    *DSI-*|*"mode: "*1080x2340*|*"active=1"*) log "DRM: $line" ;;
                esac
            done <"$state"
        done
    else
        log 'debugfs unavailable; deferred probes not collected'
    fi
    # Report host controller / PHY binding status without dereferencing MMIO.
    for node in /sys/bus/platform/devices/*a600000* /sys/bus/platform/devices/*a6f8800* /sys/bus/platform/devices/*88e3000*; do
        [ -e "$node" ] || continue
        driver=$(readlink "$node/driver") || driver=unbound
        log "platform ${node##*/} driver=${driver##*/}"
    done
    for path in /sys/class/drm/card*-DSI-*/status /sys/class/drm/card*-DSI-*/enabled /sys/class/graphics/fb*/name; do
        [ -r "$path" ] && log "display $path=$(cat "$path")"
    done
    charger=/sys/class/power_supply/pm8150b-charger
    [ -d "$charger" ] || charger=/sys/class/power_supply/pm8150b_charger
    if [ -d "$charger" ]; then
        for attr in online status voltage_now current_now; do
            value=$(cat "$charger/$attr" 2>/dev/null) || value=unavailable
            log "PM8150B $attr=$value"
        done
    else
        log 'PM8150B power supply unavailable'
    fi
    if [ -x /umi-gpu-check ]; then
        /umi-gpu-check /dev/dri/renderD* | while IFS= read -r line; do
            log "$line"
        done
    fi
    dmesg | while IFS= read -r line; do
        case "$line" in
            *"CSOT prepared"*|*"CSOT brightness="*|*"MiSeed DSI timeout"*|*"SM8250 UBWC"*|*"msm-mdss"*|*simpledrm*|*"switching to colour"*)
                log "display $line" ;;
        esac
    done
    if [ -x /umi-display-vblank ]; then
        /umi-display-vblank | while IFS= read -r line; do
            case "$line" in
                DISPLAY_VBLANK_RESULT*) log "$line" ;;
            esac
        done
    fi
) &
# Check the negotiated role without forcing device mode or disturbing OTG.
snapshot() {
    state=
    for x in /sys/class/udc/*/state /sys/class/usb_role/*/role /sys/class/typec/port*/data_role; do
        [ -r "$x" ] || continue
        value=$(cat "$x")
        state="$state $x=$value"
    done
    log "USB ${state:-no UDC/role state exposed}"
}
# A write to the optional serial port may block; never gate reboot on it.
(
    while :; do
        if [ -c /dev/ttyGS0 ]; then
            {
                printf 'UMI RAM-only probe: %s\n' "$(uname -r)"
                cat "$report"
                printf 'UMI_PROBE_REPORT_END\n'
            } >/dev/ttyGS0
        fi
        sleep 2
    done
) &
while :; do
    snapshot
    sleep 5
done
