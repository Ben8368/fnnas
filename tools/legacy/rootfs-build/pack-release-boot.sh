#!/usr/bin/env bash
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
exec bash "$repo/make-fnnas/qualcomm/sm8250/scripts/build-boot.sh" "$@"
