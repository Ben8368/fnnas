# Umi wireless RX lab path

The main project previously had USB-C PD/PPS support but no RX1619 receiver, LN8282 divider, or wireless input arbitration path. This lab-only port adds those pieces to the board source snapshot. The receiver driver reports power-good, voltage, current, temperature and mailbox events through the kernel power-supply interface. The board charger code adds USB-C/wireless source ownership checks and optional guarded RX policies.

The profile is off by default. It is available only with `CSOT_LAB=1`; release image assembly rejects the board-lab kernel. Select one profile explicitly when building:

| `CSOT_RX_PROFILE` | Included path | Battery charging |
|---|---|---|
| `off` | No wireless RX nodes or drivers | Unchanged lab wired path |
| `observe` | RX1619 telemetry and DT | Disabled by the RX policy |
| `link` | RX mailbox negotiation and wired-attach sleep interlock | Disabled |
| `epp` | Link plus guarded LN8282 divider and thermal input policy | Disabled; RX may supply the system input |
| `buck` | EPP plus the SMB5 buck acceptance state machine | Explicitly enabled for lab acceptance; not hardware-qualified |

For example, `CSOT_LAB=1 CSOT_RX_PROFILE=observe` selects the read-only receiver path. `link`, `epp`, and especially `buck` are progressively more active experimental profiles. The build stamps the selected profile and hashes the wireless RX source inputs into `csot-out/`.

This is a source migration, not a claim that wireless charging is working. No profile has yet been built or booted from this repository, and the active battery path has no device acceptance here. Before using `buck`, verify receiver session identity, actual current limits, temperature/fault shutdown, wired/wireless handoff and physical reverse-current isolation. The current implementation deliberately does not request the wireless fast-charge pump, 15 V operation, FFC or battery-profile programming. Do not treat register readback or software ownership as evidence of physical current isolation.

The receiver, divider and charger changes keep their per-file SPDX and upstream copyright notices. The new implementation is GPL-2.0-only; the existing directory notice records component licensing and attribution.
