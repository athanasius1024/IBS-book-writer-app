# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller recipe for IBS Book Writer, desktop edition (one file, Linux and Windows).

    pyinstaller --noconfirm --clean packaging/ibsbook.spec

Output: dist/ibs-book-writer-linux-x86_64   or   dist/IBSBookWriter.exe

WeasyPrint reaches Pango, HarfBuzz and fontconfig through cffi.dlopen(), which PyInstaller's import analysis cannot
see, so those native libraries are collected here by hand:

  Linux    the closure of the libraries WeasyPrint opens (found with ldconfig and ldd), minus the C library and
           the compiler runtimes, which must come from the machine the program runs on.
  Windows  every DLL in the folder named by IBS_NATIVE_LIBS (default build/native-libs), which
           packaging/build_windows.ps1 fills from MSYS2 (Pango and everything it needs).
"""
import os
import re
import subprocess
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

ROOT = Path(SPECPATH).resolve().parent
APP = ROOT / 'app'
WINDOWS = sys.platform == 'win32'

# ---- native libraries -------------------------------------------------------------------------------------------

LINUX_REQUIRED = [
    'libgobject-2.0.so.0', 'libglib-2.0.so.0', 'libpango-1.0.so.0', 'libpangoft2-1.0.so.0',
    'libharfbuzz.so.0', 'libfontconfig.so.1', 'libfreetype.so.6',
]
# WeasyPrint uses these when present (the subset library makes smaller PDFs); bundled only if installed.
LINUX_OPTIONAL = ['libharfbuzz-subset.so.0']
# Never bundled: these have to match the kernel and C library of the machine the program runs on.
LINUX_SYSTEM = re.compile(r'^(ld-linux.*|linux-vdso.*|lib(c|m|dl|pthread|rt|resolv|util|nsl|anl|gcc_s|stdc\+\+|'
                          r'BrokenLocale|thread_db|GL|GLX|GLdispatch|EGL|X11|xcb|Xau|Xdmcp|drm)\.so.*)$')


def linux_native_libs():
    listing = subprocess.run(['ldconfig', '-p'], capture_output=True, text=True, check=True).stdout
    known = {}
    for line in listing.splitlines():
        match = re.match(r'\s*(\S+) \(([^)]*)\) => (\S+)', line)
        if match and 'x86-64' in match.group(2) and match.group(1) not in known:
            known[match.group(1)] = match.group(3)
    for soname in LINUX_REQUIRED:
        if soname not in known:
            raise SystemExit(f'Cannot build: {soname} is not installed. On Ubuntu: apt install libpango-1.0-0 '
                             'libpangoft2-1.0-0 libharfbuzz-subset0 fontconfig')
    wanted, found = {}, []
    todo = LINUX_REQUIRED + [s for s in LINUX_OPTIONAL if s in known]
    while todo:
        soname = todo.pop()
        if soname in wanted or LINUX_SYSTEM.match(soname):
            continue
        path = known.get(soname)
        if not path:
            continue
        wanted[soname] = path
        out = subprocess.run(['ldd', path], capture_output=True, text=True).stdout
        for dep in re.findall(r'^\s*(\S+) => (\S+)', out, flags=re.M):
            known.setdefault(dep[0], dep[1])
            todo.append(dep[0])
    for soname, path in sorted(wanted.items()):
        found.append((path, '.'))             # the soname is the file name PyInstaller gives the copy
    return found


def windows_native_libs():
    folder = Path(os.environ.get('IBS_NATIVE_LIBS') or ROOT / 'build' / 'native-libs')
    dlls = sorted(folder.glob('*.dll'))
    if not any(d.name.lower().startswith('libpango-1.0') for d in dlls):
        raise SystemExit(f'Cannot build: no Pango DLLs in {folder}. Run packaging/build_windows.ps1, which prepares them.')
    return [(str(d), '.') for d in dlls]


native = windows_native_libs() if WINDOWS else linux_native_libs()

# ---- what the program needs besides its own code ----------------------------------------------------------------

datas = [
    (str(APP / 'templates'), 'templates'),
    (str(APP / 'static'), 'static'),
    (str(APP / 'fonts'), 'fonts'),
    (str(ROOT / 'sql' / 'schema.sql'), 'sql'),
]
for package in ('weasyprint', 'pyphen', 'tinycss2', 'cssselect2'):
    datas += collect_data_files(package)
datas += copy_metadata('markdown')                     # Markdown finds "attr_list", "tables" ... by entry point

own_modules = sorted(p.stem for p in APP.glob('*.py') if p.stem != '__init__')
hiddenimports = own_modules
for package in ('weasyprint', 'markdown.extensions', 'bleach', 'sqlalchemy.dialects.sqlite',
                'sqlalchemy.dialects.postgresql', 'waitress'):
    hiddenimports += collect_submodules(package)
hiddenimports += ['psycopg2', 'psycopg2.extras', 'psycopg2.extensions']

a = Analysis(
    [str(APP / 'desktop.py')],
    pathex=[str(APP)],
    binaries=native,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=['tkinter', 'pytest', 'IPython', 'matplotlib'],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='IBSBookWriter' if WINDOWS else 'ibs-book-writer-linux-x86_64',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=True,            # the window you close to stop the program; it also shows where your data is
)
