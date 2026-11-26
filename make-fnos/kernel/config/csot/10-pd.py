"""Wired only: replace, do not co-register, Armbian's FG/SMB5 drivers."""
from shutil import copy2
import apply_adc5_fix as adc
import apply_pd_diagnostics as pd
from source_layout import POWER_GROUPS, POWER_HEADERS

supply = linux / 'drivers/power/supply'
dest = supply / 'umi-wired'
dest.mkdir()
power = inputs / 'kernel/power'
for name in POWER_HEADERS:
    copy2(power / name, dest / name)
for group, symbol in [('qcom_fg', 'BATTERY_MISEED_QCOM_FG'),
                      ('qcom_pm8150b_charger', 'CHARGER_MISEED_PM8150B')]:
    for unit in POWER_GROUPS[group]:
        copy2(power / (unit + '.c'), dest)
    append(dest / 'Makefile', f'obj-$(CONFIG_{symbol}) += {group}.o')
    append(dest / 'Makefile', group + '-y := ' + ' '.join(u + '.o' for u in POWER_GROUPS[group]))
append(supply / 'Makefile', 'obj-y += umi-wired/')
(dest / 'Kconfig').write_text((power / 'Kconfig').read_text().split('config CHARGER_BQ25970_CORE')[0])
append(supply / 'Kconfig', 'source "drivers/power/supply/umi-wired/Kconfig"')
for name in ('qcom,pm8150b-fg.yaml', 'qcom,pm8150b-charger.yaml'):
    copy2(power / 'bindings' / name, linux / 'Documentation/devicetree/bindings/power/supply')
adc.stage(linux)
# Take the pinned RX fix and profile selection, not the RAM logger's enlarged ring.
import hashlib
import tcpm_fixed_profile
for name, expected in pd.ORIGINAL.items():
    target = linux / name
    if hashlib.sha256(target.read_bytes()).hexdigest() != expected:
        raise ValueError(f'Unexpected TCPM/PHY baseline: {name}')
    text = target.read_text()
    target.write_text(tcpm_fixed_profile.transform(text, pd.replace_once) if name == pd.TCPM
                      else pd.transform(name, text, (power / 'pmic_pdphy_receive.inc').read_text()))
copy2(power / 'umi-pm8150b.dtsi', board)
copy2(here / 'wired-pd.dtsi', board)
append(csot, '#include "umi-pm8150b.dtsi"\n#include "wired-pd.dtsi"')
