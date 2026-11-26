"""Use the Linux NCI transport; no Android HAL or eSE reset."""
from shutil import copy2
import apply_nfc_port
import apply_geni_nack_diagnostics

apply_nfc_port.apply(linux, inputs)
# Retry only isolated write address NACKs, not ambiguous DMA/data failures.
apply_geni_nack_diagnostics.apply(linux)
copy2(here / 'sn100t.dtsi', board)
append(csot, '#include "sn100t.dtsi"')
