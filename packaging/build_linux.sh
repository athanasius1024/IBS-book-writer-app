#!/usr/bin/env bash
# Build the single-file Linux program:  dist/ibs-book-writer-linux-x86_64
#
#   packaging/build_linux.sh            build in .venv-desktop (created if missing)
#   packaging/build_linux.sh --test     ...and then run packaging/smoke_test.py against the result
#
# The program needs the C library of the machine it was built on, or newer. To make a file that runs on most
# distributions, build on an old one (the GitHub workflow uses Ubuntu 22.04, glibc 2.35).
# Needs, from the system: python3 (3.11+), libpango-1.0-0, libpangoft2-1.0-0, libharfbuzz-subset0, fontconfig.
set -eu
cd "$(dirname "$0")/.."

VENV=.venv-desktop
if [ ! -x "$VENV/bin/python" ]; then
    python3 -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install --quiet --upgrade pip
"$VENV/bin/python" -m pip install --quiet -r requirements-desktop.txt

rm -rf build/pyinstaller dist/ibs-book-writer-linux-x86_64
"$VENV/bin/python" -m PyInstaller --noconfirm --clean \
    --workpath build/pyinstaller --distpath dist packaging/ibsbook.spec

OUT=dist/ibs-book-writer-linux-x86_64
ls -lh "$OUT"
( cd dist && sha256sum ibs-book-writer-linux-x86_64 > ibs-book-writer-linux-x86_64.sha256 )

if [ "${1:-}" = "--test" ]; then
    "$VENV/bin/python" -m pip install --quiet pypdf          # only the test uses it, to read the PDF it gets
    "$VENV/bin/python" packaging/smoke_test.py "$OUT"
fi
