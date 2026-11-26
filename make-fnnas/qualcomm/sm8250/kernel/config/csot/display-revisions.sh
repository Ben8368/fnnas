# Pin the source snapshot for each native display profile.
case ${CSOT_REFRESH:-90} in
    60)
        display_source_rev=3263cff0483f9cfa66c5ac693d759b4c7a6710d2
        display_source=$here/../../../sources/display-60 ;;
    90)
        display_source_rev=774c0a40b65d5f240fc69cd02f797e0a9196fcbb
        display_source=$here/../../../sources/display-90 ;;
    *) echo 'CSOT_REFRESH must be 60 or 90' >&2; exit 2 ;;
esac
lab_source_rev=fb5f76c7e6adef9bde55f93cd4e41f0beab953e9
lab_source=$here/../../../sources/board-lab
