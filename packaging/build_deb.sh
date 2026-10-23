#!/usr/bin/env bash
# Build the Debian/Ubuntu package from the finished Linux program:  dist/ibs-book-writer_amd64_v<version>.deb
#
#   packaging/build_deb.sh                         wraps dist/ibs-book-writer-linux-x86_64_v<version>
#   packaging/build_deb.sh path/to/that/file       wraps another copy of it (for example the one from a release)
#
# The package only installs the self-contained program: no scripts run when it is installed or removed, and your
# books (in ~/.local/share/ibs-book-writer) are never touched. Names and the version come from app/version.py.
# Needs: dpkg-deb (any Debian or Ubuntu system).
set -eu
umask 022                      # files in the package must not depend on the builder's umask
cd "$(dirname "$0")/.."

field() { python3 -c "import sys; sys.path.insert(0, 'app'); import version; print(version.$1)"; }
LINUX_FILE=$(field LINUX_FILE)
DEB_FILE=$(field DEB_FILE)
DEB_VERSION=$(field DEB_VERSION)
BIN=${1:-dist/$LINUX_FILE}
[ -f "$BIN" ] || { echo "Cannot find the Linux program: $BIN (build it with packaging/build_linux.sh first)" >&2; exit 1; }

STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT

install -Dm755 "$BIN" "$STAGE/opt/ibs-book-writer/ibs-book-writer"
install -d "$STAGE/usr/bin"
ln -s /opt/ibs-book-writer/ibs-book-writer "$STAGE/usr/bin/ibs-book-writer"

install -d "$STAGE/usr/share/applications"
cat > "$STAGE/usr/share/applications/ibs-book-writer.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=IBS Book Writer
Comment=Write, lay out and export books (PDF, EPUB, HTML, ODT)
Exec=ibs-book-writer
Terminal=true
Categories=Office;WordProcessor;
Keywords=book;writing;epub;pdf;
EOF

DOC="$STAGE/usr/share/doc/ibs-book-writer"
install -d "$DOC"
install -m644 app/fonts/LICENSES.txt "$DOC/fonts-licenses.txt"
cat > "$DOC/copyright" <<'EOF'
IBS Book Writer
Copyright (c) Infodine Business Systems.
Source code and releases: https://github.com/athanasius1024/IBS-book-writer-app

The program carries these fonts, each under its own licence (see fonts-licenses.txt in this folder):
Liberation Serif and Sans, and DejaVu Serif.
EOF
chmod 644 "$DOC/copyright"

SIZE_KB=$(du -sk "$STAGE" | cut -f1)
install -d "$STAGE/DEBIAN"
cat > "$STAGE/DEBIAN/control" <<EOF
Package: ibs-book-writer
Version: $DEB_VERSION
Architecture: amd64
Maintainer: Angelo P. Arteman <athanasius1024@protonmail.com>
Installed-Size: $SIZE_KB
Depends: libc6 (>= 2.35)
Recommends: xdg-utils
Section: text
Priority: optional
Homepage: https://github.com/athanasius1024/IBS-book-writer-app
Description: write, lay out and export books on your own computer
 IBS Book Writer runs on this computer only and opens in your web browser.
 You write chapters, covers, a glossary and an index, then generate PDF,
 EPUB, HTML and ODT copies of the book. Your books are kept in
 ~/.local/share/ibs-book-writer; removing the package does not delete them.
 The program is self-contained: it carries its own Python, PDF libraries
 and fonts.
EOF

# Explicit modes (Debian policy): every directory 755 (mktemp makes the top one 700), data files 644.
find "$STAGE" -type d -exec chmod 755 {} +
chmod 644 "$STAGE/usr/share/applications/ibs-book-writer.desktop" "$STAGE/DEBIAN/control"

mkdir -p dist
rm -f "dist/$DEB_FILE"
dpkg-deb --build --root-owner-group -Zxz "$STAGE" "dist/$DEB_FILE" > /dev/null
( cd dist && sha256sum "$DEB_FILE" > "$DEB_FILE.sha256" )
ls -lh "dist/$DEB_FILE"
dpkg-deb --info "dist/$DEB_FILE" | sed -n '1,12p'
