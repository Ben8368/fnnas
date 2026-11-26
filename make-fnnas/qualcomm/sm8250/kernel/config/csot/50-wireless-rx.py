"""Stage the optional Umi wireless RX path in the board-lab profile."""
from shutil import copy2

profile = os.environ.get('CSOT_RX_PROFILE', 'off')
if profile != 'off':
    supply = linux / 'drivers/power/supply/umi-wired'
    for name in ('rx1619.c', 'ln8282-observe.c', 'ln8282-forward.c', 'umi_rx_epp.c'):
        copy2(inputs / 'kernel/power' / name, supply / name)
    copy2(inputs / 'kernel/power/umi-rx1619.dtsi', board / 'umi-rx1619.dtsi')
    append(csot, '#include "umi-rx1619.dtsi"')
    binding_dir = linux / 'Documentation/devicetree/bindings/power/supply'
    for name in ('xiaomi,umi-rx1619.yaml', 'xiaomi,umi-ln8282.yaml'):
        copy2(inputs / 'kernel/power/bindings' / name, binding_dir / name)
