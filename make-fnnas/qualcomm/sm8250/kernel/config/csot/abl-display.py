"""Export downstream DTBO symbols on inert nodes; retain live compiled phandles.

fnOS has more active devices than the rescue profile, including a live mdss_dsi0.
Quarantine all reviewed vendor targets from the active Android tree.
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path


def qualify(base, output, targets, donor):
    names = {s for s in targets.read_text().splitlines() if s and not s.startswith('#')}
    if len(names) != 241 or not all(re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', s) for s in names):
        raise ValueError('unexpected Android target list')
    # The verified release donor can contain additional ABL stub symbols.
    dump = subprocess.check_output(['dtc', '-q', '-I', 'dtb', '-O', 'dts', donor], text=True)
    stubs = re.findall(r'^\s*(\w+) = "/abl_ovf/[^/\"]+";', dump, re.M)
    if len(stubs) < 152:
        raise ValueError('missing donor ABL anchors')
    names.update(stubs)
    # Labels give each sink a real phandle. fdtoverlay remaps exported names,
    # but never the live Linux phandles inside the original compiled DTB.
    sinks = '\n'.join(f'{name}: sink-{i} {{ }};' for i, name in enumerate(sorted(names)))
    source = '/dts-v1/; /plugin/; &{/} { abl_ovf { status = "disabled";\n' + sinks + '\n}; };'
    with tempfile.TemporaryDirectory() as tmp:
        dtbo = Path(tmp) / 'sinks.dtbo'
        subprocess.run(['dtc', '-q', '-@', '-o', dtbo], input=source, text=True, check=True)
        subprocess.run(['fdtoverlay', '-i', base, '-o', output, dtbo], check=True)
    dump = subprocess.check_output(['dtc', '-q', '-I', 'dtb', '-O', 'dts', output], text=True)
    isolated = set(re.findall(r'^\s*(\w+) = "/abl_ovf/sink-\d+";', dump, re.M))
    if isolated != names:
        raise ValueError('vendor target escaped isolation')


if __name__ == '__main__':
    qualify(*map(Path, sys.argv[1:]))
