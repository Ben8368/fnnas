"""Stage profile fragments only inside build.sh's new Linux work directory."""
import os
import runpy
import sys
from pathlib import Path

here = Path(__file__).resolve().parent
work = Path(sys.argv[1]).resolve()
linux = work / 'linux'
inputs = work / 'board-lab-inputs'
board = linux / 'arch/arm64/boot/dts/qcom'
csot = board / 'sm8250-xiaomi-umi-csot.dts'
sys.path.insert(0, str(inputs / 'tools'))


def append(path, text):
    with path.open('a', encoding='utf-8') as stream:
        stream.write('\n' + text.rstrip() + '\n')


for module in sorted(here.glob('[0-9][0-9]-*.py')):
    if module.name < '60' and os.environ.get('CSOT_LAB', '0') != '1':
        continue
    runpy.run_path(str(module), init_globals=globals().copy())
