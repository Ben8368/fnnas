"""Stage the selected native display source and adapt CSOT backlight byte order."""
import os
import re
import runpy
import subprocess
from shutil import copy2

source = work / 'display-inputs'
lab = os.environ.get('CSOT_LAB') == '1'
out = work / ('csot-out' if lab else 'kernel-out')
# Select the display and console settings from the integrated common config.
# Its forced rescue command line is supplied by the fnOS boot packer instead.
display_options = {
    'CONFIG_DRM', 'CONFIG_DRM_SIMPLEDRM', 'CONFIG_DRM_FBDEV_EMULATION',
    'CONFIG_DRM_CLIENT_DEFAULT_FBDEV', 'CONFIG_FB_SIMPLE',
    'CONFIG_FRAMEBUFFER_CONSOLE', 'CONFIG_FRAMEBUFFER_CONSOLE_ROTATION',
    'CONFIG_FONTS', 'CONFIG_FONT_TER16x32',
    'CONFIG_SERIAL_QCOM_GENI', 'CONFIG_SERIAL_QCOM_GENI_CONSOLE', 'CONFIG_SERIAL_EARLYCON',
}
common = (source / 'kernel/umi-l2.config').read_text()
settings = dict(re.findall(r'^(?:# )?(CONFIG_\w+)(.*)$', common, re.M))
if display_options - settings.keys():
    raise ValueError(f'Missing native display config options: {sorted(display_options - settings.keys())}')
(out / 'native-display.config').write_text(''.join(
    f'{"# " if value.startswith(" is not set") else ""}{key}{value}\n'
    for key, value in settings.items() if key in display_options) +
    'CONFIG_VT=y\nCONFIG_VT_CONSOLE=y\n# CONFIG_SYSFB_SIMPLEFB is not set\n# CONFIG_LOGO is not set\n')
cmdline = runpy.run_path(str(source / 'tools/pack_android_boot_v2.py'))['CMDLINE']
(out / 'native-display-cmdline').write_bytes(cmdline + b'\n')

# Use the mainline DSI manager. Armbian installs a downstream
# blank notifier and a different bonded-link command path.
subprocess.run(['git', '-C', linux, 'restore', '--source=HEAD', '--',
                'drivers/gpu/drm/msm/dsi/dsi_manager.c'], check=True)
# The source stager expects its board entry. Keep it separate from fnOS.
copy2(source / 'kernel/umi-csot.dts', board)
subprocess.run([sys.executable, source / 'tools/apply_display_port.py',
                '--source', linux, '--native', '--expected-revision', linux_rev], check=True)

# The CSOT vendor DTS specifies MSB first for the two-byte DCS brightness.
panel = linux / 'drivers/gpu/drm/panel/panel-xiaomi-umi-csot.c'
driver = panel.read_bytes()
old_brightness = b'mipi_dsi_dcs_set_display_brightness(c->dsi, backlight_get_brightness(bl))'
new_brightness = b'mipi_dsi_dcs_set_display_brightness_large(c->dsi, backlight_get_brightness(bl))'
if driver.count(old_brightness) != 1:
    raise ValueError('Unexpected CSOT brightness call')
panel.write_bytes(driver.replace(old_brightness, new_brightness))

if not lab:
    # The generic board lacks the shipped WiFi PMU, Venus/GPU OPPs and ramoops.
    # Extend the exact release DTS instead of regressing unrelated hardware.
    release = here.parents[1] / 'dts-donor.dts'
    baseline = work / 'release-check.dtb'
    subprocess.run(['dtc', '-q', '-@', '-I', 'dts', '-O', 'dtb', '-o', baseline, release], check=True)
    if baseline.read_bytes() != (work / 'main-boot/dtb').read_bytes():
        raise ValueError('release DTS does not reproduce the verified donor')
    copy2(release, csot)
    copy2(here / 'release-display-labels.dtsi', board)
    copy2(here / 'release-hardware.dtsi', board)
    append(csot, '#include "release-display-labels.dtsi"\n#include "release-hardware.dtsi"')
else:
    append(csot, '#include <dt-bindings/clock/qcom,dispcc-sm8250.h>')
    append(csot, '#include <dt-bindings/gpio/gpio.h>')

# Import the firmware framebuffer and splash/DFPS regions verbatim.
# The matching nodes in the flattened release merge at their existing paths.
donor = (source / 'kernel/umi-csot.dts').read_text(encoding='utf-8')


def block(name):
    pattern = rf'^\t\t{re.escape(name)} \{{\n.*?^\t\t\}};'
    matches = re.findall(pattern, donor, re.M | re.S)
    if len(matches) != 1:
        raise ValueError(f'Unexpected CSOT board node: {name}')
    return matches[0]


splash = block('cont-splash@9c000000')
dfps = block('dfps-data@9e300000')
append(csot, f'''/ {{
    aliases {{ serial0 = &uart12; }};
    chosen {{
        stdout-path = "serial0:115200n8";
{block('framebuffer: framebuffer@9c000000')}
    }};
    reserved-memory {{
{splash}
{dfps}
    }};
}};
&uart12 {{ status = "okay"; }};
''')
append(csot, '#include "umi-native-dsi.dtsi"')
# Keep fnOS's board-wide pin reservations and reserve GPIO50 in the 60 Hz
# profile, as required when the native panel has no rate GPIO.
reserved = '<28 4>, <40 4>, <52 4>'
if os.environ.get('CSOT_REFRESH', '60') == '60':
    reserved += ', <50 1>'
append(csot, f'&tlmm {{ gpio-reserved-ranges = {reserved}; }};')
append(csot, '''
/* Use the mainline DSI PHY and RPMh supplies. */
&mdss_dsi0 { /delete-property/ refgen-supply; };
&{/soc@0/display-subsystem@ae00000/dsi@ae96000} { /delete-property/ refgen-supply; };
''')
flag = 'DTC_FLAGS_sm8250-xiaomi-umi-csot += -@'
if flag not in (board / 'Makefile').read_text().splitlines():
    append(board / 'Makefile', flag)
