"""Read back the *compiled* CSOT profile, without touching a device."""
import subprocess
import sys

blob, refresh = sys.argv[1:3]
lab = len(sys.argv) == 3 or sys.argv[3] == '1'
rx_profile = sys.argv[4] if len(sys.argv) > 4 else 'off'


def get(node, prop, kind='s'):
    return subprocess.check_output(['fdtget', '-t', kind, blob, node, prop], text=True).strip()


def node(label):
    if not lab and label == 'tlmm':
        label = 'fnos_live_tlmm'
    return get('/__symbols__', label)


def properties(path):
    return subprocess.check_output(['fdtget', '-p', blob, path], text=True).split()


def phandle(path):
    return get(path, 'phandle', 'u')


def require(condition, context):
    if not condition:
        raise SystemExit('Unexpected compiled CSOT DTB: ' + context)


require(refresh in ('60', '90'), 'refresh selector')
require(get('/', 'model') == 'Xiaomi Mi 10 (CSOT)', 'panel variant')
if not lab:
    bluetooth = '/soc@0/geniqup@9c0000/serial@998000/bluetooth'
    pmu = '/qca6390-pmu'
    require(get(bluetooth, 'compatible') == 'qcom,qca6390-bt', 'Bluetooth remains enabled')
    require(not {'pinctrl-0', 'pinctrl-names', 'enable-gpios', 'swctrl-gpios'} & set(properties(bluetooth)),
            'Bluetooth must not claim the PMU pins')
    require(get(pmu, 'bt-enable-gpios', 'u').split()[-2:] == ['21', '0'], 'PMU must retain BT_EN')
    for name, ldo in zip(('rfacmn', 'aon', 'btcmx', 'rfa0p8', 'rfa1p2', 'rfa1p7'), (0, 1, 4, 5, 6, 7)):
        require(get(bluetooth, f'vdd{name}-supply', 'u') == phandle(f'{pmu}/regulators/ldo{ldo}'),
                f'Bluetooth PMU vdd{name} supply')
    require(get('/soc@0/pinctrl@33c0000', 'status') == 'disabled', 'unsupported ADSP clock consumer')
if lab:
    port = node('pm8150b_typec') + '/connector'
    require(get(port, 'power-role') == 'sink' and get(port, 'data-role') == 'device', 'USB roles')
    require('source-pdos' not in properties(port), 'OTG')
    pdos = [int(v, 16) for v in get(port + '/capabilities/caps-1', 'sink-pdos', 'x').split()]
    require(any(v >> 30 == 0 and (v >> 10 & 1023) == 180 for v in pdos), '9 V fixed PDO')
    require(any(v >> 28 == 12 for v in pdos), 'PPS APDO')
    for label, compatible in [('umi_charger', 'qcom,pm8150b-charger'), ('umi_fg', 'qcom,pm8150b-fg'),
                              ('umi_pps', 'xiaomi,umi-bq25970'), ('umi_nfc', 'nxp,sn100t'),
                              ('umi_csot', 'xiaomi,umi-csot')]:
        require(get(node(label), 'compatible') == compatible, label)
    require(get(node('umi_pps'), 'reg', 'x') == '66' and get(node('umi_nfc'), 'reg', 'x') == '28', 'I2C addresses')
    if rx_profile == 'off':
        require('umi_wireless_rx' not in properties('/__symbols__'), 'wireless RX disabled profile')
    else:
        require(rx_profile in ('observe', 'link', 'epp', 'buck'), 'wireless RX profile selector')
        rx = node('umi_wireless_rx')
        divider = node('umi_divider')
        require(get(rx, 'compatible') == 'xiaomi,umi-rx1619'
                and get(rx, 'reg', 'x') == '61', 'RX1619 node')
        require(get(divider, 'compatible') == 'xiaomi,umi-ln8282'
                and get(divider, 'reg', 'x') == '55', 'LN8282 node')
        require('qcom,wireless-rx' in properties(node('umi_charger')),
                'wireless RX charger reference')
else:
    pon = '/soc@0/spmi@c440000/pmic@0/pon@800'
    require(get(pon, 'compatible') == 'qcom,pm8998-pon'
            and get(pon, 'mode-bootloader', 'u') == '2', 'PM8150 Fastboot reboot mode')
    ramoops = '/reserved-memory/ramoops@b0000000'
    require(get(ramoops, 'compatible') == 'ramoops'
            and get(ramoops, 'console-size', 'x') == '200000', 'ramoops console log')
    pmic = '/soc@0/spmi@c440000/pmic@2'
    charger = pmic + '/charger@1000'
    adc = pmic + '/adc@3100'
    require(get(adc, 'compatible') == 'qcom,spmi-adc5'
            and ('status' not in properties(adc) or get(adc, 'status') == 'okay'),
            'PM8150B ADC5 provider')
    adc_phandle = phandle(adc)
    require(get(charger, 'status') == 'okay'
            and get(charger, 'io-channel-names') == 'usb_in_i_uv usb_in_v_div_16'
            and get(charger, 'io-channels', 'u').split() == [adc_phandle, '7', adc_phandle, '8'],
            'PM8150B charger ADC5 channels')
    require(get('/soc@0/gpu@3d00000/zap-shader', 'firmware-name') == 'qcom/sm8250/a650_zap.mbn',
            'Adreno early ZAP firmware path')
    for path in ('/sound', '/soc@0/codec@3370000', '/soc@0/soundwire@3210000',
                 '/soc@0/soundwire@3230000', '/soc@0/geniqup@ac0000/i2c@a94000',
                 '/audio-codec',
                 '/soc@0/geniqup@9c0000/i2c@98c000/speaker-amp@40',
                 '/soc@0/geniqup@9c0000/i2c@98c000/speaker-amp@42'):
        require(get(path, 'status') == 'disabled', path)
fb = node('framebuffer')
require('status' not in properties(fb) or get(fb, 'status') == 'okay', 'framebuffer hand-off')
require(fb == '/chosen/framebuffer@9c000000' and get(fb, 'compatible') == 'simple-framebuffer', 'ABL framebuffer')
require([get(fb, prop, 'u') for prop in ('width', 'height', 'stride')] == ['1080', '2340', '4320']
        and get(fb, 'format') == 'a8r8g8b8', 'ABL framebuffer layout')
splash = node('cont_splash_mem')
require(get(fb, 'reg', 'x') == get(splash, 'reg', 'x') == '0 9c000000 0 2300000', 'splash reservation')
require('no-map' in properties(splash), 'splash no-map')
require(get('/reserved-memory/dfps-data@9e300000', 'reg', 'x') == '0 9e300000 0 100000', 'DFPS reservation')
panel = node('umi_csot')
mdss, dsi, phy, output = (node(label) for label in
    ('mdss', 'mdss_dsi0' if lab else 'fnos_live_dsi0', 'mdss_dsi0_phy', 'mdss_dsi0_out'))
require(all(get(path, 'status') == 'okay' for path in (mdss, dsi, phy)), 'MDSS/DSI/PHY status')
require(get(mdss, 'resets', 'u').split() == [phandle(node('dispcc')), '0'], 'MDSS core reset')
require('refgen-supply' not in properties(dsi), 'legacy DSI refgen-supply')
require(get(dsi, 'vdda-supply', 'u') == phandle(node('vreg_l9a_1p2')), 'DSI LDO9 supply')
require(get(phy, 'vdds-supply', 'u') == phandle(node('vreg_l5a_0p88')), 'DSI PHY LDO5 supply')
require(panel == dsi + '/panel@0', 'panel on DSI0')
endpoint = node('umi_csot_in')
require(get(output, 'data-lanes', 'u') == '0 1 2 3'
        and get(output, 'remote-endpoint', 'u') == phandle(endpoint)
        and get(endpoint, 'remote-endpoint', 'u') == phandle(output), 'DSI panel graph')
require(get(panel, 'compatible') == 'xiaomi,umi-csot', 'panel compatible')
gpio = phandle(node('tlmm'))
require(get(panel, 'reset-gpios', 'u').split() == [gpio, '12', '1'], 'reset GPIO')
require(('disprate-gpios' in properties(panel)) == (refresh == '90'), 'panel rate-select ownership')
if refresh == '90':
    require(get(panel, 'disprate-gpios', 'u').split() == [gpio, '50', '0'], 'rate GPIO')
reserved = list(map(int, get(node('tlmm'), 'gpio-reserved-ranges', 'u').split()))
require(len(reserved) % 2 == 0, 'GPIO reservation format')
ranges = list(zip(reserved[::2], reserved[1::2]))
require(not any(start <= 12 < start + count for start, count in ranges), 'panel reset GPIO12 is reserved')
require(any(start <= 50 < start + count for start, count in ranges) == (refresh == '60'),
        'GPIO50 reservation for selected refresh rate')
print('PASS: compiled native CSOT display profile (' + refresh + ' Hz, RX ' + rx_profile + ')')
