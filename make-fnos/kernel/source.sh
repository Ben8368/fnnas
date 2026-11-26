# Shared Linux Stable source selection and historical Umi boot donor identity.
umi_linux_repo=https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git
umi_linux_locked_version=6.18.60
umi_linux_locked_commit=f45ed76d6791cf72ff1265ee93511175bbbc2f18
umi_boot_donor_sha256=a7e4d341e35a663683bf41a8fe99d472bc6b8568aa1b54b05901dc7e9f2d842a

resolve_umi_linux() {
    local requested=${1:-auto} refs ref object version candidate picked
    case $requested in
        locked|"$umi_linux_locked_version")
            printf '%s\t%s\n' "$umi_linux_locked_version" "$umi_linux_locked_commit"
            return
            ;;
        auto) refs=$(git ls-remote --tags -- "$umi_linux_repo" 'refs/tags/v6.18.*') || return ;;
        *)
            if [[ ! $requested =~ ^6\.18\.(0|[1-9][0-9]*)$ ]]; then
                echo 'Select locked, auto or a concrete 6.18.x version.' >&2
                return 2
            fi
            refs=$(git ls-remote --tags -- "$umi_linux_repo" "refs/tags/v$requested" "refs/tags/v$requested^{}") || return
            ;;
    esac

    # Sort only final 6.18.x tag names. Prefer the peeled commit of an annotated tag.
    local -A commits=() peeled=()
    while read -r object ref; do
        [[ $object =~ ^[0-9a-f]{40}$ &&
            $ref =~ ^refs/tags/v(6\.18\.(0|[1-9][0-9]*))(\^\{\})?$ ]] || continue
        version=${BASH_REMATCH[1]}
        if [[ -n ${BASH_REMATCH[3]} ]]; then
            peeled[$version]=$object
        else
            commits[$version]=$object
        fi
    done <<< "$refs"
    if [[ $requested == auto ]]; then
        picked=$(printf '%s\n' "${!commits[@]}" | LC_ALL=C sort -V | tail -n 1)
    else
        picked=$requested
    fi
    if [[ -z $picked || ! -v 'commits[$picked]' ]]; then
        echo "Linux Stable has no matching release for $requested (6.18.y)." >&2
        return 1
    fi
    candidate=${peeled[$picked]:-${commits[$picked]}}
    printf '%s\t%s\n' "$picked" "$candidate"
}

apply_umi_armbian_patches() {
    local linux=$1 selected=$2 patches=$3 file name output path
    local -a conflicts patch_options
    for file in "$patches"/*.patch; do
        name=${file##*/}
        printf '\n=== %s ===\n' "$name"
        patch_options=(--batch --forward -p1)
        if [[ $selected != "$umi_linux_locked_commit" ]]; then
            case $name in
                0002-*|0009-*|0017-*|0033-*|0061-*|0062-*)
                    # Native display uses the upstream DSI manager. Keep upstream
                    # FastRPC, and omit the codec changes that cancel each other.
                    echo 'Keeping the upstream driver.'
                    continue
                    ;;
            esac
            # 0021 adds a separate charger and its Makefile entry has displaced
            # context since the in-tree BQ257xx driver was added.
            if [[ $name != 0021-* ]]; then patch_options+=(--fuzz=0); fi
            if git -C "$linux" apply --reverse --check "$file" 2>/dev/null; then
                echo 'Patch already present.'
                continue
            fi
            if ! output=$(LC_ALL=C patch -d "$linux" --dry-run "${patch_options[@]}" < "$file" 2>&1); then
                printf '%s\n' "$output"
                # GNU patch reports the rejected hunks under their file header.
                # Skip the whole patch only when every conflict is in an upstream driver edit.
                mapfile -t conflicts < <(awk '
                    /^checking file / { file = substr($0, 15) }
                    /^[0-9]+ out of [0-9]+ hunks? (FAILED|ignored)/ && file != "" { print file }
                ' <<< "$output" | sort -u)
                if ((${#conflicts[@]} == 0)); then return 1; fi
                if ! git -C "$linux" cat-file -e "$umi_linux_locked_commit^{commit}" 2>/dev/null; then
                    git -C "$linux" fetch --no-tags --depth 1 -- "$umi_linux_repo" "refs/tags/v$umi_linux_locked_version" ||
                        return 1
                    [[ $(git -C "$linux" rev-parse 'FETCH_HEAD^{commit}') == "$umi_linux_locked_commit" ]] ||
                        return 1
                fi
                for path in "${conflicts[@]}"; do
                    case $path in drivers/*|sound/*|include/linux/*) ;; *) return 1 ;; esac
                    if [[ -z $(git -C "$linux" diff --name-only "$umi_linux_locked_commit" "$selected" -- "$path") ]]; then
                        echo "Patch conflict without an upstream driver change: $path" >&2
                        return 1
                    fi
                done
                echo "Keeping upstream changes and skipping $name."
                continue
            fi
        fi
        patch -d "$linux" "${patch_options[@]}" < "$file" || return
    done
}
