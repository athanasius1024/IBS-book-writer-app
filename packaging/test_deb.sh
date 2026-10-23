#!/usr/bin/env bash
# Test the .deb package without root, by installing it into a throw-away dpkg root.
#
#   packaging/test_deb.sh                    tests dist/ibs-book-writer_amd64_v<version>.deb
#   packaging/test_deb.sh path/to/file.deb   tests another copy (for example one downloaded from a release)
#
# What it proves: dpkg refuses the package on a system with a libc6 older than the one it declares, installs it on
# one that matches, the files and their modes are standard, the launcher entry is valid, the installed program starts
# and serves its login page, `dpkg -V` finds every file intact, and removing the package leaves nothing behind and
# does not touch the user's books. It does NOT replace trying `sudo apt install` on a real Ubuntu or Debian machine.
# Needs: dpkg, python3, curl (desktop-file-validate is used when present). No root, no changes outside a temp folder.
cd "$(dirname "$0")/.." || exit 1

field() { python3 -c "import sys; sys.path.insert(0, 'app'); import version; print(version.$1)"; }
DEB=${1:-dist/$(field DEB_FILE)}
EXPECTED=$(field DISPLAY_NAME)
[ -f "$DEB" ] || { echo "No such package: $DEB (build it with packaging/build_deb.sh)" >&2; exit 1; }
DEB=$(realpath "$DEB")

ROOT=$(mktemp -d)
cleanup() { pkill -f "$ROOT/root/opt/ibs-book-writer/ibs-book-writer" 2>/dev/null; rm -rf "$ROOT"; }
trap cleanup EXIT
mkdir -p "$ROOT/admin/info" "$ROOT/admin/updates" "$ROOT/admin/triggers" "$ROOT/root" "$ROOT/books"
DP=(dpkg --admindir="$ROOT/admin" --instdir="$ROOT/root" --force-not-root --force-bad-path --log="$ROOT/dpkg.log")
quiet() { grep -v -E 'needrestart|files list file for package .libc6|^\(Reading'; }   # noise from the host's dpkg hooks

fails=0
check() { if [ "$1" = ok ]; then echo "  ok    $2"; else echo "  FAIL  $2"; fails=$((fails + 1)); fi; }
libc_status() {   # pretend this system has libc6 version $1
    printf 'Package: libc6\nStatus: install ok installed\nPriority: required\nSection: libs\nInstalled-Size: 1\nMaintainer: x\nArchitecture: amd64\nVersion: %s\nDescription: C library\n\n' "$1" > "$ROOT/admin/status"
}

echo "Testing $DEB"
MIN=$(dpkg-deb -f "$DEB" Depends | sed -n 's/.*libc6 (>= \([0-9.]*\)).*/\1/p')
[ -n "$MIN" ] || { echo "The package declares no libc6 dependency" >&2; exit 1; }
BELOW="${MIN%%.*}.$(( ${MIN#*.} - 1 ))"

libc_status "$BELOW"
"${DP[@]}" -i "$DEB" 2>&1 | quiet | grep -q "depends on libc6 (>= $MIN)" && check ok "refused on libc6 $BELOW (needs $MIN)" || check bad "refused on libc6 $BELOW (needs $MIN)"

libc_status "$MIN"
"${DP[@]}" -i "$DEB" > "$ROOT/install.log" 2>&1
[ "$("${DP[@]}" -s ibs-book-writer 2>/dev/null | grep -c '^Status: install ok installed')" = 1 ] && check ok "installs on libc6 $MIN" || { check bad "installs on libc6 $MIN"; quiet < "$ROOT/install.log"; }

PROGRAM="$ROOT/root/opt/ibs-book-writer/ibs-book-writer"
[ -x "$PROGRAM" ] && check ok "program installed under /opt/ibs-book-writer" || check bad "program installed under /opt/ibs-book-writer"
[ "$(readlink "$ROOT/root/usr/bin/ibs-book-writer")" = /opt/ibs-book-writer/ibs-book-writer ] && check ok "/usr/bin/ibs-book-writer points at it" || check bad "/usr/bin/ibs-book-writer points at it"
[ -r "$ROOT/root/usr/share/doc/ibs-book-writer/copyright" ] && check ok "copyright file installed" || check bad "copyright file installed"

odd=$(dpkg-deb --contents "$DEB" | awk '($1 ~ /^d/ && $1 != "drwxr-xr-x") || ($1 ~ /^-/ && $1 != "-rw-r--r--" && $1 != "-rwxr-xr-x")')
[ -z "$odd" ] && check ok "every directory is 755 and every file 644 or 755" || { check bad "file modes are standard"; echo "$odd"; }

DESKTOP="$ROOT/root/usr/share/applications/ibs-book-writer.desktop"
if command -v desktop-file-validate > /dev/null; then
    desktop-file-validate "$DESKTOP" && check ok "applications-menu entry is valid" || check bad "applications-menu entry is valid"
fi

[ "$("$PROGRAM" --version 2>&1)" = "$EXPECTED" ] && check ok "program reports \"$EXPECTED\"" || check bad "program reports \"$EXPECTED\""

PORT=$(python3 -c "import socket; s = socket.socket(); s.bind(('127.0.0.1', 0)); print(s.getsockname()[1])")
"$PROGRAM" --no-browser --port "$PORT" --data-dir "$ROOT/books/data" > "$ROOT/program.log" 2>&1 &
code=000
for _ in $(seq 1 60); do
    code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/login")
    [ "$code" = 200 ] && break
    sleep 0.5
done
[ "$code" = 200 ] && check ok "installed program serves its login page" || { check bad "installed program serves its login page (HTTP $code)"; tail -5 "$ROOT/program.log"; }
pkill -f "$PROGRAM" 2>/dev/null; sleep 1
[ -f "$ROOT/books/data/ibsbook.db" ] && check ok "its books are kept in the data folder it was given" || check bad "its books are kept in the data folder it was given"

problems=$("${DP[@]}" -V ibs-book-writer 2>&1 | quiet)
[ -z "$problems" ] && check ok "dpkg -V: every installed file is intact" || { check bad "dpkg -V: every installed file is intact"; echo "$problems"; }

before=$(ls "$ROOT/books/data" | wc -l)
"${DP[@]}" -r ibs-book-writer > /dev/null 2>&1
left=$(cd "$ROOT/root" && find . -mindepth 1 | head -3)
[ -z "$left" ] && check ok "removal leaves nothing behind" || { check bad "removal leaves nothing behind"; echo "$left"; }
[ "$(ls "$ROOT/books/data" | wc -l)" = "$before" ] && [ "$before" -gt 0 ] && check ok "removal does not touch the user's books" || check bad "removal does not touch the user's books"

if [ "$fails" = 0 ]; then echo "All checks passed."; else echo "FAILED: $fails check(s)"; fi
[ "$fails" = 0 ]
