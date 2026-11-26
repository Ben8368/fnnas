"""Do not build PPS unless the pinned BQ backend passes its host fault test."""
import shutil
import subprocess

if not shutil.which('cc'):
    raise SystemExit('A host C compiler is required for the BQ watchdog gate')
subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', str(inputs / 'tests'),
                '-p', 'test_bq25970.py', '-v'], check=True)
