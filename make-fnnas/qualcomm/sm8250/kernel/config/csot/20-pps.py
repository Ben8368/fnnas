"""Add the independent chip and Umi board owner as one guarded PPS path."""
from shutil import copy2
from source_layout import POWER_GROUPS, POWER_RULES

power = inputs / 'kernel/power'
dest = linux / 'drivers/power/supply/umi-wired'
for group in ('umi-bq25970', 'bq25970_core'):
    for unit in POWER_GROUPS[group]:
        copy2(power / (unit + '.c'), dest)
for rule in POWER_RULES:
    if ('BQ25970_CORE' in rule or 'bq25970_charger-y' in rule
            or 'CONFIG_CHARGER_MISEED_UMI_PPS' in rule
            or 'CONFIG_CHARGER_UMI_RX1619' in rule
            or 'CONFIG_UMI_RX_' in rule):
        append(dest / 'Makefile', rule)
copy2(power / 'Kconfig', dest / 'Kconfig')
for name in ('ti,bq25970.yaml', 'xiaomi,umi-bq25970.yaml'):
    copy2(power / 'bindings' / name, linux / 'Documentation/devicetree/bindings/power/supply')
copy2(power / 'umi-pps.dtsi', board)
append(csot, '#include "umi-pps.dtsi"')
