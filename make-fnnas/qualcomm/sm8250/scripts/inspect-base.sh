#!/usr/bin/env bash
set -euo pipefail
scripts=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
exec "${FNOS_PYTHON:-python3}" -B "$scripts/base_image.py" inspect "$@"
