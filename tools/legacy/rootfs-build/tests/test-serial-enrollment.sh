#!/bin/bash
# Run without root. Redirect device commands and the state marker into a fixture.
set -euo pipefail
src="$(dirname "${BASH_SOURCE[0]}")/../../../../make-fnnas/fnnas-files/different-files/xiaomi-umi/rootfs/usr/local/sbin/umi-serial-console"
export FIXTURE
FIXTURE=$(mktemp -d)
trap 'rm -r -- "$FIXTURE"' EXIT
mkdir "$FIXTURE/bin"
export PATH="$FIXTURE/bin:$PATH"

sed -e "s|^marker=.*|marker='$FIXTURE/marker'|" -e 's|/sbin/agetty|agetty|g' "$src" > "$FIXTURE/console"
cat > "$FIXTURE/bin/tty" <<'EOF'
#!/bin/bash
printf '%s\n' "${TEST_TTY:-/dev/ttyGS0}"
EOF
cat > "$FIXTURE/bin/getent" <<'EOF'
#!/bin/bash
printf 'root:%s:0:0:99999:7:::\n' "$(< "$FIXTURE/hash")"
EOF
cat > "$FIXTURE/bin/passwd" <<'EOF'
#!/bin/bash
[[ "$*" == root ]] || exit 2
[[ ${TEST_CANCEL:-no} == no ]] || exit 1
printf 'test-password-hash\n' > "$FIXTURE/hash"
EOF
cat > "$FIXTURE/bin/agetty" <<'EOF'
#!/bin/bash
printf '%s\n' "$@"
EOF
chmod +x "$FIXTURE/bin/"*

console() { bash "$FIXTURE/console" "$@"; }
expect_failure() {
	if "$@"; then printf 'Unexpected success: %s\n' "$*" >&2; exit 1; fi
}

touch "$FIXTURE/marker"
printf '!\n' > "$FIXTURE/hash"
expect_failure env TEST_TTY=/dev/pts/0 bash "$FIXTURE/console" --enroll
console | grep -Fx -- '--enroll'
expect_failure env TEST_CANCEL=yes bash "$FIXTURE/console" --enroll
[[ -f "$FIXTURE/marker" && $(< "$FIXTURE/hash") == '!' ]]
console | grep -Fx -- '--enroll'

console --enroll
[[ ! -e "$FIXTURE/marker" && $(< "$FIXTURE/hash") == test-password-hash ]]
console | grep -Fx -- '-p -- \u'
expect_failure console --enroll

# Model disconnect after passwd commits but before marker removal.
touch "$FIXTURE/marker"
console | grep -Fx -- '-p -- \u'
expect_failure console --enroll
echo 'PASS: serial setup refuses other terminals, retries after cancellation and cannot reset an enrolled password'
