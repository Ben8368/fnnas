# CSOT native display

Release builds include native display by default. `CSOT_REFRESH=90` (default) and `60` select separate fixed-mode kernels at build time. The exact source trees used for each profile are checked into [`sources/`](../../../sources/), so clean builds need no network access for display code. The lab profile adds the separate `board-lab/` source snapshot. See [release build](../../../../../../tools/legacy/rootfs-build/BUILD.md) and the [source dependency audit](../../../../../../tools/legacy/rootfs-build/SOURCES.md).

| Mode | Locked source revision | Hardware result |
|---|---|---|
| 60 Hz | `3263cff0483f9cfa66c5ac693d759b4c7a6710d2` | Visible landscape console; standard backlight control. |
| 90 Hz | `774c0a40b65d5f240fc69cd02f797e0a9196fcbb` | 1080×2340 mode, GPIO50 high; earlier callback sample averaged 89.846 Hz. |

Both builds use Linux `f45ed76d6791cf72ff1265ee93511175bbbc2f18` and the checked-in panel, binding, DCS/DSC commands and display staging tools. The staged driver sends two-byte brightness values most significant byte first, as specified in the CSOT vendor device tree. The source includes MDSS reset handling, clock handoff, UBWC root matching and the MSM fbdev system-memory fix. The DT imports the native DSI graph, RPMh supplies, framebuffer, splash and DFPS regions. The build restores the pinned mainline DSI manager and removes Armbian's DSI refgen bindings. Per-file license and copyright notices are retained in the source tree.

The fnOS boot header uses the native display command line including `fbcon=font:TER16x32,rotate:3`, with fnOS root UUID and storage arguments. Early userspace and the rootfs use the standard CSOT backlight device at the startup level `1500/2047`. The release keeps the Wi-Fi, GPU and Venus board support and packages a CSOT image for the selected rate.

On 2026-11-25 the previous fnOS 90 Hz image showed a black screen on CSOT 0B / DTBO 11 despite framebuffer samples, an active DRM mode and a 45.234 Hz callback. The matching umi-mainline 6.18.60 reference initialized native DRM and measured 89.828 Hz command-mode callbacks. [umi-mainline acceptance](https://github.com/Ben8368/umi-mainline/blob/73c86bf/docs/TESTLOG.md#pr-2-csot-90-hz)

## fnOS RAM boot on 2026-11-25

Both profiles booted over Fastboot on CSOT 0B / DTBO index 11. Each showed visible landscape text at 146×33, used `msmdrmfb` on DSI-1, and returned to Android. The phone's partitions were left intact. The ext4 release rootfs was checked offline.

| Profile | Active DRM mode | Native console | Panel and callback evidence |
|---|---|---|---|
| 60 Hz | 1080×2340 @ 60 Hz, 235655 kHz | 8.75 s; the backlight device reported 1500/2047 at 10.79 s | DSC and all 59 DCS commands completed. The DRM callback sampler timed out. |
| 90 Hz | 1080×2340 @ 90 Hz, 235788 kHz | 8.95 s; visible text around the 10 s log lines | 90 Hz DCS timing programmed and GPIO50 selected. 91 DRM callbacks averaged 89.801 Hz with zero gaps. |

There was a brief black interval before the native console became visible. Physical scan frequency was not measured.

## Optional board lab (not a release image)

`CSOT_LAB=1` adds wired power and NFC bring-up into `csot-out`; release assembly rejects this kernel. Do not pair it with release rootfs power services. Wireless RX support is available only through the opt-in `CSOT_RX_PROFILE` lab profiles; it defaults to `off`. See [wireless RX status and profiles](WIRELESS-RX.md).

**Fixed PD:** TCPM selects standard sink PDOs; the PM8150B switch charger owns input limits and FG telemetry. This board profile intentionally removes the source PDO and OTG. Target-level qualification and thermal recovery remain open. Before any RAM boot, qualify the ABL overlay against this specific DTB, the root identity and the target rootfs services. Rollback is the unmodified release kernel/DTB/rootfs set.

**Wired PPS:** the BQ25970 is on I²C15, address `0x66` with GPIO68 IRQ. SMB5 and the pump share an exclusive board owner. The pinned DTS supplies limits, sensors, cooling maps and sink APDO; missing protections are not filled in with defaults. fnOS IRQ, protection injection, temperature scale and bypass hysteresis need separate verification.

**Charge watchdog:** the PPS driver already includes the BQ 30 s hardware timer; no independent userspace petter or disable switch is added. A host C regression must pass before building: a latched, read-to-clear timeout must surface as `-ETIME`. This is not the SMB5 bark interrupt or the system watchdog. Expiry/stop and recovery on the target remain untested.

**NFC:** SN100T on I²C1 `0x28`, using Linux NFC/NCI (no `/dev/nq-nci`). The source device discovered a physical MIFARE card, closed and reopened (`2026-11-19-umi-nfc-init-retry.md`). Keep shared VEN asserted on close; no eSE/MIFARE-key operations, NDEF or suspend/wakeup claim.

**横屏启动日志（CSOT 60/90 Hz）**使用逆时针 90° 和 16×32 字体。用 `cat /proc/cmdline` 核对 `fbcon=font:TER16x32,rotate:3`，用 `cat /sys/class/graphics/fbcon/rotate` 确认当前旋转为 `3`。
