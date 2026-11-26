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

# Only named, reviewed omissions. A digest binds the decision to the exact patch.
apply_umi_armbian_patches() {
    local linux=$1 selected=$2 patches=$3 manifest=$4 file name sha reason status
    local -a files
    shopt -s nullglob
    files=("$patches"/*.patch)
    shopt -u nullglob
    ((${#files[@]})) || { echo 'Empty Armbian patch series' >&2; return 1; }
    printf 'patch\tsha256\tstatus\treason\n' > "$manifest"
    for file in "${files[@]}"; do
        name=${file##*/}
        sha=$(sha256sum < "$file") || return
        sha=${sha%% *}
        printf '\n=== %s ===\n' "$name"
        reason=
        if [[ $selected != "$umi_linux_locked_commit" ]]; then
            case "$name:$sha" in
                0002-drm-dsi-emit-panel-turn-on-off-signal-to-touchscreen.patch:610e0e8e19c4d376787faf485512c7805634a2a5070ab85cf2e916dda27a9619) reason='Native Umi panel does not use the Armbian touchscreen notifier' ;;
                0009-drm-msm-dsi-change-sync-mode-to-sync-on-DSI0-rather-.patch:18a0c76656351b0bdbc645f0d6982295e208f376467499a5d36ad42b85e9fc23) reason='Native Umi uses upstream DSI synchronization' ;;
                0017-ASoC-cs35l45-disable-power-managerment.patch:684f3026b50ccecea31e50c06bd4192d0dfa350be68903a53a5855fd9f99c09d) reason='Codec change and its revert are omitted as a pair' ;;
                0033-Revert-ASoC-cs35l45-disable-power-managerment.patch:7760c58194e80f644aa695525db25734487b983b9caeee244f0a442780d7d9a4) reason='Codec change and its revert are omitted as a pair' ;;
                0061-Revert-misc-fastrpc-Rename-tgid-and-pid-to-client_id.patch:ee7aad7b886281f782d0af65272f6a20d8af00633ca815e2b17255ba7ac13341) reason='Keep upstream FastRPC client identity' ;;
                0062-Revert-misc-fastrpc-Add-support-for-multiple-PD-from.patch:1d3f411232cdf7c6b71f9a5ccfd8b44736797131339c3cef6e45ad512d0e6403) reason='Keep upstream FastRPC multi-PD support' ;;
            esac
        fi
        if [[ -n $reason ]]; then
            status=reviewed-skip
        elif git -C "$linux" apply --reverse --check -- "$file" 2>/dev/null; then
            status=already-present
        elif patch -d "$linux" --dry-run --batch --forward --fuzz=0 -p1 < "$file" &&
             patch -d "$linux" --batch --forward --fuzz=0 -p1 < "$file"; then
            status=applied
        else
            printf '%s\t%s\tconflict\tUnreviewed patch failure\n' "$name" "$sha" >> "$manifest"
            echo "Unreviewed Armbian patch conflict: $name on $selected" >&2
            return 1
        fi
        printf '%s\t%s\t%s\t%s\n' "$name" "$sha" "$status" "$reason" >> "$manifest"
    done
}
