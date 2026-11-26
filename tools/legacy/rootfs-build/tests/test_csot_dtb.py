"""Exercise the CSOT verifier on real FDT cells without a kernel build or hardware."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


VERIFY = Path(__file__).resolve().parents[4] / "make-fnnas/qualcomm/sm8250/kernel/config/csot/verify-dtb.py"
DTS = """/dts-v1/;
/ {
    model = "Xiaomi Mi 10 (CSOT)";
    tlmm: pins { gpio-controller; #gpio-cells = <2>; gpio-reserved-ranges = <28 4> GPIO50_RESERVATION; };
    other: other-pins { gpio-controller; #gpio-cells = <2>; };
    pm8150b_typec: typec { connector { power-role = "sink"; data-role = "device";
        capabilities { caps-1 { sink-pdos = <0x2d000 0xc0000000>; }; }; }; };
    umi_charger: charger { compatible = "qcom,pm8150b-charger"; };
    umi_fg: fg { compatible = "qcom,pm8150b-fg"; };
    umi_pps: pump { compatible = "xiaomi,umi-bq25970"; reg = <0x66>; };
    umi_nfc: nfc { compatible = "nxp,sn100t"; reg = <0x28>; };
    chosen { framebuffer: framebuffer@9c000000 { compatible = "simple-framebuffer"; status = "FB_STATUS";
        reg = <0 0x9c000000 0 0x2300000>; width = <1080>; height = <2340>;
        stride = <FB_STRIDE>; format = "a8r8g8b8"; }; };
    reserved-memory { dfps-data@9e300000 { reg = <0 0x9e300000 0 0x100000>; }; cont_splash_mem: splash { reg = <0 0x9c000000 0 0x2300000>; no-map; }; };
    dispcc: clock-controller { #reset-cells = <1>; };
    vreg_l9a_1p2: ldo9 {};
    vreg_l5a_0p88: ldo5 {};
    mdss: display {
        status = "okay"; resets = <&dispcc 0>;
        mdss_dsi0_phy: phy { status = "okay"; vdds-supply = <&vreg_l5a_0p88>; };
        mdss_dsi0: dsi {
            status = "okay"; vdda-supply = <&vreg_l9a_1p2>; LEGACY_SUPPLY
            port { mdss_dsi0_out: endpoint { remote-endpoint = <&umi_csot_in>; data-lanes = <0 1 2 3>; }; };
            umi_csot: panel@0 {
                reset-gpios = <&tlmm 12 1>; compatible = "xiaomi,umi-csot"; RATE_GPIO
                port { umi_csot_in: endpoint { remote-endpoint = <&mdss_dsi0_out>; }; };
            };
        };
    };
};"""


class RateGpioTests(unittest.TestCase):
    def test_rate_gpio(self):
        cases = [("60", "", True), ("90", "", False), ("60", "&tlmm 50 0", False),
                 ("90", "&tlmm 50 0", True), ("90", "&other 50 0", False),
                 ("90", "&tlmm 51 0", False), ("90", "&tlmm 50 1", False)]
        with tempfile.TemporaryDirectory() as tmp:
            dtb = Path(tmp) / "fixture.dtb"
            scenarios = [(r, c, 'okay', '4320', '', valid) for r, c, valid in cases]
            scenarios.extend([('60', '', 'disabled', '4320', '', False),
                              ('90', '&tlmm 50 0', 'disabled', '4320', '', False),
                              ('90', '&tlmm 50 0', 'okay', '4352', '', False),
                              ('90', '&tlmm 50 0', 'okay', '4320', 'refgen-supply = <&vreg_l9a_1p2>;', False)])
            for rate, cells, status, stride, supply, valid in scenarios:
                with self.subTest(rate=rate, cells=cells, status=status):
                    prop = f"disprate-gpios = <{cells}>;" if cells else ""
                    dts = (DTS.replace("RATE_GPIO", prop).replace("FB_STATUS", status)
                           .replace("FB_STRIDE", stride).replace("LEGACY_SUPPLY", supply)
                           .replace("GPIO50_RESERVATION", ", <50 1>" if rate == "60" else ""))
                    subprocess.run(["dtc", "-q", "-@", "-o", dtb],
                                   input=dts, text=True, check=True)
                    result = subprocess.run([sys.executable, VERIFY, dtb, rate], capture_output=True)
                    self.assertEqual(result.returncode == 0, valid, result.stderr)
                    if not valid:
                        self.assertIn(b"Unexpected compiled CSOT DTB: ", result.stderr)
