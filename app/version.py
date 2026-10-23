"""The version of the program (not of any book), and the names of the files built from it.

TO RELEASE THE NEXT VERSION: change APP_VERSION below (1_0 -> 1_1 -> 1_2 ...), commit, then tag that commit
with the same number and push the tag:

    git tag v1_1 && git push origin v1_1

The tag starts the GitHub build, which publishes IBSBookWriter_v1_1.exe and ibs-book-writer-linux-x86_64_v1_1.
The Debian/Ubuntu package (ibs-book-writer_amd64_v1_1.deb) is made from that Linux file with packaging/build_deb.sh.
Nothing else needs editing: the on-screen name, `--version`, the build scripts and the CI workflow all read it
from here. (The data folder is deliberately NOT versioned, so a new version finds the books of the old one.)

This file must stay free of imports, because the build scripts read it before anything is installed.
"""
APP_NAME = 'IBS Book Writer'
APP_VERSION = '1_0'

DISPLAY_NAME = f'{APP_NAME} v{APP_VERSION}'
WINDOWS_FILE = f'IBSBookWriter_v{APP_VERSION}.exe'
LINUX_FILE = f'ibs-book-writer-linux-x86_64_v{APP_VERSION}'
MACOS_FILE = f'ibs-book-writer-macos_v{APP_VERSION}'
DEB_FILE = f'ibs-book-writer_amd64_v{APP_VERSION}.deb'      # Debian/Ubuntu package
DEB_VERSION = APP_VERSION.replace('_', '.')                    # the package's own version: 1_0 -> 1.0
TAG = f'v{APP_VERSION}'
