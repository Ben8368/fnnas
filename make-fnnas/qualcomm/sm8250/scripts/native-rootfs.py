#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Configure a pinned, extracted fnOS staging tree and check a built image."""
import argparse
import json
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile

from base_image import digest, mounted, open_disk, inventory


REQUIRED_FIRMWARE = {"qcom/sm8250/a650_zap.mbn", "qcom/a650_gmu.bin", "qcom/a650_sqe.fw"}
FSTAB = "UUID={uuid} / btrfs defaults,noatime,compress=zstd:1,subvolid=5 0 1\ntmpfs /tmp tmpfs defaults,nosuid 0 0\n"
UPDATE_MASKS = ("apt-daily.timer", "apt-daily-upgrade.timer", "apt-daily-upgrade.service", "resize-rootfs.service")
USB_ACM_UNIT = "umi-usb-acm.service"
USB_GETTY_MASK = "etc/systemd/system/serial-getty@ttyGS0.service"
DONOR_GETTY = "serial-getty@ttyAMA0.service"
DONOR_GETTY_WANT = Path(f"etc/systemd/system/getty.target.wants/{DONOR_GETTY}")
WSD_UNIT = "etc/systemd/system/wsdd2.service"
WSD_DAEMON = "usr/sbin/wsdd2"
WSD_DROPIN = Path(f"{WSD_UNIT}.d/90-umi-donor-path.conf")
WSD_CONFIG = "[Service]\nExecStart=\nExecStart=/usr/sbin/wsdd2 -4\n"
LEGACY_USB_GETTY_RULE = "etc/udev/rules.d/99-umi-serial.rules"
CONSOLE_FILES = {
    f"usr/lib/systemd/system/{USB_ACM_UNIT}": 0o644,
    "usr/local/sbin/umi-usb-acm": 0o755,
    "usr/local/sbin/umi-usb-network": 0o755,
    "usr/local/sbin/umi-usb-bootlog": 0o755,
    "usr/lib/systemd/system/umi-usb-network.service": 0o644,
    "usr/lib/systemd/system/umi-usb-bootlog.service": 0o644,
    "etc/NetworkManager/conf.d/90-umi-usb-setup.conf": 0o644,
    "etc/udev/rules.d/80-umi-csot-backlight.rules": 0o644,
    "etc/systemd/network/10-umi-usb-setup.link": 0o644,
    "usr/local/sbin/umi-serial-console": 0o755,
    "usr/local/sbin/umi-power": 0o755,
    "etc/systemd/system/serial-getty@ttyGS0.service.d/50-umi-console.conf": 0o644,
    "etc/systemd/journald.conf.d/90-umi-boot-log.conf": 0o644,
    "etc/systemd/pstore.conf.d/90-umi-boot-log.conf": 0o644,
}
PSTORE_LINK = Path("etc/systemd/system/sysinit.target.wants/systemd-pstore.service")
PSTORE_UNIT = "/lib/systemd/system/systemd-pstore.service"
DONOR_HOOKS = ("etc/kernel/postinst.d/10-sync-dtb", "etc/kernel/postinst.d/15-update-ukernel-ver",
               "etc/kernel/postinst.d/zz-update-grub", "etc/initramfs/post-update.d/99-uboot",
               "etc/initramfs/post-update.d/zz-update-uinitrd")
STAGING_MODES = {"/": 0o755, "/etc": 0o755, "/usr": 0o755, "/root": 0o700}

# These are Umi adaptations of the pinned donor. Keep its enablement and
# adjust only the hardware or runtime prerequisite that was found missing.
NATIVE_SERVICE_POLICY = {
    "etc/systemd/system/led-set.service": (
        "/usr/trim/bin/system_setled.sh", "[Unit]\nConditionPathExists=/boot/board.json\n"),
    "etc/systemd/system/set_gpio-init.service": (
        "/usr/trim/bin/system_setgpio.sh", "[Unit]\nConditionPathExists=/boot/board.json\n"),
    "usr/lib/systemd/system/nut-server.service": (
        "/sbin/upsd -F", "[Service]\n"
        "ExecCondition=/bin/sh -c 'case \"$${MODE:-none}\" in standalone|netserver) exit 0;; *) exit 1;; esac'\n"),
    "usr/lib/systemd/system/nut-monitor.service": (
        "/sbin/upsmon -F", "[Service]\n"
        "ExecCondition=/bin/sh -c 'case \"$${MODE:-none}\" in standalone|netserver|netclient) exit 0;; *) exit 1;; esac'\n"),
    # No supported SMART devices is normal on the internal UFS. Leave the
    # scan and actionable errors enabled, including those on external disks.
    "usr/lib/systemd/system/smartmontools.service": (
        "/usr/sbin/smartd -n $smartd_opts", "[Service]\nExecStart=\nExecStart=/usr/sbin/smartd -n -q errors,nodev0 $smartd_opts\n"),
    "etc/systemd/system/trim_trashbind.service": (
        "/usr/trim/bin/trashbind", "[Unit]\nConditionPathIsMountPoint=/fs\n"),
    # Do not substitute another libupnp SONAME or the system libc. The
    # loader checks the real ABI before these optional vendor programs run.
    "etc/systemd/system/upnp.service": (
        "/usr/trim/bin/upnp_service", "[Service]\nExecCondition=/lib/ld-linux-aarch64.so.1 --list /usr/trim/bin/upnp_service\n"),
    "etc/systemd/system/trim_raid_check.service": (
        "/usr/trim/bin/check_raid456_resync_status",
        "[Service]\nExecCondition=/lib/ld-linux-aarch64.so.1 --list /usr/trim/bin/check_raid456_resync_status\n"),
}
EXIM_TMPFILES = "etc/tmpfiles.d/90-umi-exim.conf"
# Debian exim4-base.postinst creates this directory; the donor archive omits it.
EXIM_LOG_POLICY = "d /var/log/exim4 2750 Debian-exim adm -\n"


def service_dropin(path):
    return f"etc/systemd/system/{Path(path).name}.d/90-umi-compat.conf"


def apply_native_service_policy(root):
    for path, (command, dropin) in NATIVE_SERVICE_POLICY.items():
        unit = inside(root, path)
        if (unit.is_symlink() or not unit.is_file() or
                [line for line in unit.read_text().splitlines() if line.startswith("ExecStart=")]
                != [f"ExecStart={command}"]):
            raise ValueError(f"Donor service changed; review before adapting {path}")
        if Path(path).name in {"nut-server.service", "nut-monitor.service"} and (
                "EnvironmentFile=-/etc/nut/nut.conf" not in unit.read_text().splitlines()):
            raise ValueError(f"Donor NUT environment changed: {path}")
        if unit.stat().st_mode & 0o111:
            # Replace, not chmod through a hardlinked sibling in the donor.
            replace_file(unit, unit.read_text())
            unit.chmod(0o644)
        target = inside(root, service_dropin(path))
        target.parent.mkdir(exist_ok=True)
        with target.open("x", encoding="utf-8") as stream:
            stream.write(dropin)
        target.chmod(0o644)
    for path, name in (("etc/passwd", "Debian-exim"), ("etc/group", "adm")):
        if not any(line.partition(":")[0] == name for line in inside(root, path).read_text().splitlines()):
            raise ValueError(f"Donor account missing: {name}")
    tmpfiles = inside(root, EXIM_TMPFILES)
    tmpfiles.parent.mkdir(exist_ok=True)
    with tmpfiles.open("x", encoding="utf-8") as stream:
        stream.write(EXIM_LOG_POLICY)
    tmpfiles.chmod(0o644)


def inside(root, name):
    path = root / name
    if not path.resolve().is_relative_to(root):
        raise ValueError(f"RootFS path escapes staging: {name}")
    return path


def replace_file(path, text):
    if path.exists() or path.is_symlink():
        path.unlink()  # Do not overwrite through a link or mutate a hardlinked sibling.
    path.write_text(text, encoding="utf-8")


def remove_path(path):
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        raise ValueError(f"Unexpected special file: {path}")


def install_firmware(root, filename, expected):
    if not re.fullmatch(r"[0-9a-f]{64}", expected) or digest(filename, "sha256") != expected:
        raise ValueError("Firmware archive does not match the supplied SHA-256")
    with tarfile.open(filename, "r:*") as archive:
        entries = {}
        for member in archive.getmembers():
            path = Path(member.name)
            if (path.is_absolute() or ".." in path.parts or not path.parts
                    or path.parts[0] not in {"qcom", "ath11k"}):
                raise ValueError(f"Unexpected firmware path: {member.name}")
            if member.isdir():
                continue
            if not member.isfile() or member.size == 0 or str(path) in entries:
                raise ValueError(f"Firmware inputs must be unique, nonempty regular files: {member.name}")
            entries[str(path)] = member
        if not REQUIRED_FIRMWARE <= entries.keys():
            raise ValueError(f"Firmware bundle missing {sorted(REQUIRED_FIRMWARE - entries.keys())}")
        manifest = {}
        firmware = inside(root, "usr/lib/firmware")
        for name, member in sorted(entries.items()):
            target = firmware / name
            if not target.parent.resolve().is_relative_to(firmware.resolve()):
                raise ValueError(f"Firmware path escapes staging: {name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.is_symlink() or target.exists():
                target.unlink()
            with archive.extractfile(member) as payload, target.open("xb") as stream:
                shutil.copyfileobj(payload, stream)
            target.chmod(0o644)
            manifest[name] = digest(target, "sha256")
    stash = inside(root, "etc/umi-build")
    stash.mkdir(exist_ok=True)
    replace_file(stash / "firmware.json", json.dumps({"archive_sha256": expected, "files": manifest}, indent=2) + "\n")


def fix_donor_boot_services(root, system):
    want = inside(root, DONOR_GETTY_WANT.parent) / DONOR_GETTY_WANT.name
    if not want.is_symlink() or want.readlink() != Path("/lib/systemd/system/serial-getty@.service"):
        raise ValueError("Donor serial-getty enablement changed; review ttyAMA0 before porting")
    mask = system / DONOR_GETTY
    if mask.exists() or mask.is_symlink():
        raise ValueError("Unexpected donor ttyAMA0 override")
    unit = inside(root, WSD_UNIT)
    daemon = inside(root, WSD_DAEMON)
    if (not unit.is_file() or unit.is_symlink() or
            [line for line in unit.read_text().splitlines() if line.startswith("ExecStart=")]
            != ["ExecStart=/usr/trim/bin/wsdd2 -4"] or not daemon.is_file() or daemon.is_symlink()
            or not daemon.stat().st_mode & 0o111):
        raise ValueError("Donor wsdd2 service or installed executable changed; review before porting")
    dropin_dir = inside(root, WSD_DROPIN.parent)
    dropin_dir.mkdir(exist_ok=True)
    with (dropin_dir / WSD_DROPIN.name).open("x", encoding="utf-8") as stream:
        stream.write(WSD_CONFIG)
    (dropin_dir / WSD_DROPIN.name).chmod(0o644)
    want.unlink()
    mask.symlink_to("/dev/null")


def prepare(root, report, firmware, firmware_sha256, uuid):
    layout = json.loads((report / "partitions.json").read_text())
    info = json.loads((report / "image-info.json").read_text())
    part = next(part for part in layout["partitions"] if part["number"] == info["root_partition"])
    if (info["expected_sha256_checked"] is not True or part["filesystem"] != "btrfs"
            or part["default_subvolume"] != 5 or part["subvolumes"] or info["root_subvolume"] != 5):
        raise ValueError("Donor Btrfs layout not reviewed; preserve or review subvolumes before porting")
    fstab = inside(root, "etc/fstab")
    original = fstab.read_text()
    mounts = [line.split() for line in original.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    if [entry[:3] for entry in mounts] != [
        ["/dev/mmcblk0p2", "/", "btrfs"], ["/dev/mmcblk0p1", "/boot", "ext4"], ["tmpfs", "/tmp", "tmpfs"]
    ] or any(len(entry) != 6 or "subvol" in entry[3] for entry in mounts):
        raise ValueError("Donor fstab changed; review the layout rather than guessing")
    mode_changes = {}
    for relative, mode in STAGING_MODES.items():
        path = inside(root, relative.lstrip("/"))
        if path.is_dir() and not path.is_symlink():
            original_mode = stat.S_IMODE(path.stat().st_mode)
            if original_mode != mode:
                path.chmod(mode)
                mode_changes[relative] = [oct(original_mode), oct(mode)]
    replace_file(fstab, FSTAB.format(uuid=uuid))
    modules = inside(root, "lib/modules")
    for child in modules.iterdir():
        remove_path(child)
    for child in inside(root, "boot").iterdir():
        remove_path(child)
    for top in ("vmlinuz", "vmlinuz.old", "initrd.img", "initrd.img.old"):
        remove_path(root / top)
    disabled_hooks = []
    for name in DONOR_HOOKS:
        hook = inside(root, name)
        if hook.is_file() and not hook.is_symlink():
            hook.chmod(stat.S_IMODE(hook.stat().st_mode) & ~0o111)
            disabled_hooks.append(name)
        elif hook.exists() or hook.is_symlink():
            raise ValueError(f"Unexpected kernel hook type: {name}")
    for child in inside(root, "usr/src").glob("linux-headers-*"):
        remove_path(child)
    config = inside(root, "etc/initramfs-tools/update-initramfs.conf")
    if config.is_file():
        new, changed = re.subn(r"^update_initramfs=.*$", "update_initramfs=no", config.read_text(), flags=re.M)
        if changed != 1:
            raise ValueError("Donor update-initramfs policy changed")
        replace_file(config, new)
    system = inside(root, "etc/systemd/system")
    for unit in UPDATE_MASKS:
        path = system / unit
        if path.exists() or path.is_symlink():
            path.unlink()
        path.symlink_to("/dev/null")
    fix_donor_boot_services(root, system)
    apply_native_service_policy(root)
    for name, mode in CONSOLE_FILES.items():
        path = inside(root, name)
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"Umi console file is missing from the board overlay: {name}")
        path.chmod(mode)
    dnsmasq = inside(root, "usr/sbin/dnsmasq")
    if not dnsmasq.is_file() or (dnsmasq.stat().st_mode & 0o111) == 0:
        raise ValueError("The pinned donor must provide dnsmasq-base for isolated USB DHCP")
    # The board overlay's enrolment getty is for the legacy Debian image only.
    # Drop its udev trigger and mask only this tty, not other consoles.
    rule = Path(LEGACY_USB_GETTY_RULE)
    (inside(root, rule.parent) / rule.name).unlink(missing_ok=True)
    getty_path = Path(USB_GETTY_MASK)
    getty = inside(root, getty_path.parent) / getty_path.name
    if getty.is_symlink() and getty.readlink() == Path("/dev/null"):
        pass
    elif getty.exists() or getty.is_symlink():
        raise ValueError("Unexpected pre-existing Umi USB getty instance")
    else:
        getty.symlink_to("/dev/null")
    pstore_link = inside(root, PSTORE_LINK.parent) / PSTORE_LINK.name
    if not pstore_link.is_symlink() or pstore_link.readlink() != Path(PSTORE_UNIT):
        raise ValueError("The pinned donor must enable systemd-pstore")
    wants = inside(root, "etc/systemd/system/multi-user.target.wants")
    wants.mkdir(exist_ok=True)
    acm_link = wants / USB_ACM_UNIT
    if acm_link.exists() or acm_link.is_symlink():
        raise ValueError("Unexpected pre-existing Umi USB ACM enablement")
    acm_link.symlink_to(f"/usr/lib/systemd/system/{USB_ACM_UNIT}")
    # Pin out donor kernel packages without rewriting dpkg's installed metadata.
    held = sorted({line.split("\t", 1)[0] for line in (report / "packages.txt").read_text().splitlines()
                   if line.startswith(("linux-image-", "linux-headers-", "linux-modules-"))})
    if not held:
        raise ValueError("No donor kernel packages found to hold")
    preferences = inside(root, "etc/apt/preferences.d")
    preferences.mkdir(exist_ok=True)
    replace_file(preferences / "99-umi-no-donor-kernel", f"Package: {' '.join(held)}\nPin: version *\nPin-Priority: -1\n")
    install_firmware(root, firmware, firmware_sha256)
    policy = {"removed_donor_module_versions": info["rootfs"]["kernel_module_versions"],
              "original_fstab": original, "corrected_modes": mode_changes,
              "masked_units": (*UPDATE_MASKS, DONOR_GETTY), "disabled_donor_hooks": disabled_hooks,
              "donor_wsdd2_exec": f"/{WSD_DAEMON} -4", "apt_pinned_packages": held,
              "ota": "vendor OTA unverified; do not run upgrades on Umi"}
    replace_file(inside(root, "etc/umi-build") / "rootfs-policy.json", json.dumps(policy, indent=2) + "\n")


def verify(image, kernel, uuid):
    release = (kernel / "include/config/kernel.release").read_text().strip()
    with tempfile.TemporaryDirectory(prefix="umi-module-audit-") as scratch:
        archive_path = Path(scratch) / "modules.tar"
        root = Path(scratch) / "modules"
        with open_disk(image) as (guest, _):
            disk, = guest.list_devices()
            part = {"filesystem": "btrfs", "device": disk}
            if guest.blkid(disk).get("UUID") != uuid:
                raise ValueError("RootFS filesystem UUID mismatch")
            with mounted(guest, part):
                if guest.btrfs_subvolume_get_default("/") != 5 or guest.btrfs_subvolume_list("/"):
                    raise ValueError("Unexpected target Btrfs subvolume layout")
                info, _, _, modules = inventory(guest)
                if (modules != [release] or guest.ls("/lib/modules") != [release] or guest.ls("/boot")
                        or info["fstab"] != FSTAB.format(uuid=uuid)):
                    raise ValueError("Wrong RootFS modules, fstab or stale boot files")
                for path, mode in STAGING_MODES.items():
                    if (guest.statns(path)["st_mode"] & 0o7777) != mode:
                        raise ValueError(f"RootFS directory mode mismatch: {path}")
                for name in DONOR_HOOKS:
                    if guest.is_file(f"/{name}") and (guest.statns(f"/{name}")["st_mode"] & 0o111):
                        raise ValueError(f"Incompatible donor boot hook is still executable: {name}")
                for unit in (*UPDATE_MASKS, DONOR_GETTY):
                    if guest.readlink(f"/etc/systemd/system/{unit}") != "/dev/null":
                        raise ValueError(f"Update mask lost: {unit}")
                if (guest.readlink(f"/etc/systemd/system/multi-user.target.wants/{USB_ACM_UNIT}")
                        != f"/usr/lib/systemd/system/{USB_ACM_UNIT}"
                        or guest.readlink(f"/{PSTORE_LINK}") != PSTORE_UNIT
                        or not guest.is_file(PSTORE_UNIT)):
                    raise ValueError("Umi USB setup or systemd-pstore service is not enabled")
                if (guest.readlink(f"/{USB_GETTY_MASK}") != "/dev/null"
                        or guest.exists(f"/{LEGACY_USB_GETTY_RULE}")
                        or not guest.is_file("/usr/sbin/dnsmasq")
                        or not guest.statns("/usr/sbin/dnsmasq")["st_mode"] & 0o111):
                    raise ValueError("Umi read-only USB setup or DHCP dependency is missing")
                if (guest.is_symlink(f"/{DONOR_GETTY_WANT}") or guest.exists(f"/{DONOR_GETTY_WANT}")
                        or guest.cat(f"/{WSD_DROPIN}") != WSD_CONFIG or not guest.is_file(f"/{WSD_DAEMON}")
                        or not guest.statns(f"/{WSD_DAEMON}")["st_mode"] & 0o111):
                    raise ValueError("Donor getty or wsdd2 correction was not preserved")
                for path, (_, contents) in NATIVE_SERVICE_POLICY.items():
                    dropin = f"/{service_dropin(path)}"
                    if (guest.is_symlink(dropin) or guest.cat(dropin) != contents
                            or guest.statns(dropin)["st_mode"] & 0o7777 != 0o644
                            or guest.statns(f"/{path}")["st_mode"] & 0o111):
                        raise ValueError(f"Umi service compatibility policy missing: {path}")
                if (guest.is_symlink(f"/{EXIM_TMPFILES}") or guest.cat(f"/{EXIM_TMPFILES}") != EXIM_LOG_POLICY
                        or guest.statns(f"/{EXIM_TMPFILES}")["st_mode"] & 0o7777 != 0o644):
                    raise ValueError("Exim log directory policy was not preserved")
                for name, mode in CONSOLE_FILES.items():
                    if not guest.is_file(f"/{name}") or (guest.statns(f"/{name}")["st_mode"] & 0o7777) != mode:
                        raise ValueError(f"Umi console file missing or wrong mode: {name}")
                firmware = json.loads(guest.cat("/etc/umi-build/firmware.json"))
                if not REQUIRED_FIRMWARE <= firmware["files"].keys() or any(
                    guest.checksum("sha256", f"/usr/lib/firmware/{name}") != sha
                    for name, sha in firmware["files"].items()
                ):
                    raise ValueError("RootFS firmware mismatch")
                guest.tar_out(f"/lib/modules/{release}", str(archive_path))
        with tarfile.open(archive_path) as archive:
            archive.extractall(root, filter="data")
        count = 0
        for file in root.rglob("*.ko*"):
            if not re.search(r"\.ko(?:\.(?:gz|xz|zst))?$", file.name):
                continue
            magic = subprocess.check_output(["modinfo", "-F", "vermagic", file], text=True).split()
            reference = kernel / "lib/modules" / release / file.relative_to(root)
            if not magic or magic[0] != release or digest(file, "sha256") != digest(reference, "sha256"):
                raise ValueError(f"Module vermagic or bytes mismatch: {file.name}")
            count += 1
        original = [file for file in (kernel / "lib/modules" / release).rglob("*.ko*")
                    if re.search(r"\.ko(?:\.(?:gz|xz|zst))?$", file.name)]
        if not count or count != len(original) or not (root / "modules.dep").is_file():
            raise ValueError("Incomplete RootFS module tree")
        print(f"Verified {count} on-image modules and vermagic for {release}; Btrfs UUID {uuid}, default id 5")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    stage = commands.add_parser("prepare")
    for name in ("root", "report", "firmware"):
        stage.add_argument(name, type=Path)
    stage.add_argument("firmware_sha256")
    stage.add_argument("uuid")
    check = commands.add_parser("verify")
    check.add_argument("image", type=Path)
    check.add_argument("kernel", type=Path)
    check.add_argument("uuid")
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", args.uuid):
        parser.error("expected a lowercase UUID")
    try:
        if args.command == "prepare":
            root = args.root.resolve(strict=True)
            if root == Path("/"):
                raise ValueError("use a dedicated staging directory")
            prepare(root, args.report, args.firmware, args.firmware_sha256, args.uuid)
        else:
            verify(args.image, args.kernel, args.uuid)
    except (OSError, KeyError, ValueError, RuntimeError, StopIteration, subprocess.CalledProcessError, tarfile.TarError) as error:
        parser.exit(1, f"Native fnOS RootFS: {error}\n")
