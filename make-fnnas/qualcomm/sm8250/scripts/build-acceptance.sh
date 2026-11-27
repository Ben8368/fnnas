#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
set -euo pipefail

if [[ ${1:-} == --help || ${1:-} == -h || $# -lt 1 || $# -gt 3 ]]; then
    echo 'Usage: renas -b xiaomi-umi native-acceptance FNOS_ACCEPTANCE_TSV [INPUT_DIR [NEW_OUTPUT_DIR]]'
    echo "Default inputs: ${XDG_CONFIG_HOME:-$HOME/.config}/fnnas/umi-acceptance"
    if [[ ${1:-} == --help || ${1:-} == -h ]]; then exit 0; fi
    exit 2
fi

[[ $(uname -s) == Linux ]] || { echo 'Assemble native fnOS on Linux.' >&2; exit 1; }
scripts=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=../kernel/source.sh
source "$scripts/../kernel/source.sh"
mapfile -t handoff < "$1"
if ((${#handoff[@]} != 1)); then
    echo 'Expected one record from the CI fnos-acceptance.tsv.' >&2
    exit 2
fi
IFS=$'\t' read -r source_sha profile run_id attempt package_sha <<< "${handoff[0]}"
if [[ ! $source_sha =~ ^[0-9a-f]{40}$ ||
      ! $profile =~ ^(release|csot-60|csot-90)$ ||
      ! $run_id =~ ^[1-9][0-9]*$ || ! $attempt =~ ^[1-9][0-9]*$ ||
      ! $package_sha =~ ^[0-9a-f]{64}$ ||
      ${handoff[0]} != "$source_sha"$'\t'"$profile"$'\t'"$run_id"$'\t'"$attempt"$'\t'"$package_sha" ]]; then
    echo 'Invalid CI fnos-acceptance.tsv record.' >&2
    exit 2
fi

inputs=${2:-${XDG_CONFIG_HOME:-$HOME/.config}/fnnas/umi-acceptance}
for file in firmware.tar firmware.sha256; do
    [[ -f $inputs/$file ]] || { echo "Missing acceptance input: $inputs/$file" >&2; exit 2; }
done
inputs=$(realpath -e -- "$inputs")
firmware_sha=$(< "$inputs/firmware.sha256")
if [[ ! $firmware_sha =~ ^[0-9a-f]{64}$ ]]; then
    echo 'firmware.sha256 must contain the trusted digest alone.' >&2
    exit 2
fi
output=${3:-out/umi-fnos-$profile-$run_id-$attempt}
[[ ! -e $output && ! -L $output ]] || { echo "Output already exists: $output" >&2; exit 2; }
printf '%s  %s\n' "$firmware_sha" "$inputs/firmware.tar" | sha256sum -c -

base=-
if [[ -f $inputs/fnos.img.xz ]]; then base=$inputs/fnos.img.xz; fi
boot=$inputs/boot-donor.img
scratch=$(mktemp -d)
trap 'rm -rf -- "$scratch"' EXIT
if [[ ! -f $boot ]]; then
    boot=$scratch/boot-donor.img
    curl --fail --location --retry 4 --retry-all-errors --output "$boot" "$umi_boot_donor_url"
fi
printf '%s  %s\n' "$umi_boot_donor_sha256" "$boot" | sha256sum -c -

args=(--debug "$base" "$boot" "$inputs/firmware.tar" "$firmware_sha" "$output"
    lineage-latest all --source "$source_sha" --profile "$profile"
    --run-id "$run_id" --run-attempt "$attempt" --package-sha256 "$package_sha")
if (( EUID == 0 )); then
    bash "$scripts/build-native.sh" "${args[@]}"
else
    token=${GH_TOKEN:-$(gh auth token --hostname github.com)}
    GH_TOKEN="$token" sudo --preserve-env=GH_TOKEN -- bash "$scripts/build-native.sh" "${args[@]}"
fi
