"""IBS Book Writer, desktop edition: the program you double-click.

It starts the app on this computer only (127.0.0.1, never reachable from the network), opens your web
browser at it, and keeps running until you close its window or press Ctrl+C. Your books, pictures and stored
copies live in one folder (see paths.py), by default a SQLite database, so there is nothing to install or set up.

    IBSBookWriter                      start (or open the copy that is already running)
    IBSBookWriter --no-browser         start without opening the browser
    IBSBookWriter --port 5050          prefer another port (the next free one is used if it is taken)
    IBSBookWriter --data-dir D         keep the data in folder D
    IBSBookWriter --setup-postgres     use a PostgreSQL server instead of the built-in database
    IBSBookWriter --version
"""
import argparse
import atexit
import json
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

VERSION = '1.0.0'
HOST = '127.0.0.1'
DEFAULT_PORT = 5000
PORT_TRIES = 25
INSTANCE_FILE = 'running.json'
BANNER_MARK = 'IBS Book Writer'


def parse_args(argv=None):
    parser = argparse.ArgumentParser(prog='IBSBookWriter', description='IBS Book Writer, desktop edition.')
    parser.add_argument('--port', type=int, default=DEFAULT_PORT, help='port to prefer (default %(default)s)')
    parser.add_argument('--no-browser', action='store_true', help='do not open the web browser')
    parser.add_argument('--data-dir', help='folder for the database, pictures and stored books')
    parser.add_argument('--setup-postgres', action='store_true', help='use a PostgreSQL server instead of SQLite')
    parser.add_argument('--version', action='store_true', help='show the version and exit')
    return parser.parse_args(argv)


# ---- the process environment, before Flask or WeasyPrint are imported -------------------------------------------

def fontconfig_text(fonts_dir, cache_dir):
    """A minimal fontconfig file: only the bundled fonts, with the cache inside the data folder."""
    return ('<?xml version="1.0"?>\n<fontconfig>\n'
            f'  <dir>{_xml(str(fonts_dir))}</dir>\n  <cachedir>{_xml(str(cache_dir))}</cachedir>\n</fontconfig>\n')


def _xml(text):
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def export_variable(name, value):
    """Set an environment variable for this process and for the native libraries it loads.

    On Windows the MSYS2 libraries (fontconfig ...) are linked against the old msvcrt, which keeps its own copy of
    the environment made when the process started. A variable set later from Python reaches the operating system
    but not that copy, so it is set there as well.
    """
    os.environ[name] = value
    if sys.platform == 'win32':
        import ctypes
        for runtime in ('msvcrt', 'ucrtbase'):
            try:
                getattr(ctypes.cdll, runtime)._putenv(f'{name}={value}'.encode('mbcs'))
            except (OSError, AttributeError):
                pass


def prepare_environment(data_dir=None, bundled_fontconfig=None):
    """Put the process in desktop mode and point the native libraries at what is bundled.

    Must run before `ibsbook` (and so Flask, SQLAlchemy and WeasyPrint) is imported. Returns the data folder.
    """
    os.environ['IBS_DESKTOP'] = '1'
    if data_dir:
        os.environ['IBS_DATA_DIR'] = str(Path(data_dir).expanduser())
    import paths
    data = paths.data_dir()
    bundled = paths.FROZEN if bundled_fontconfig is None else bundled_fontconfig
    if paths.FROZEN and sys.platform == 'win32':
        # Pango, GLib, HarfBuzz ... sit at the top of the bundle. WeasyPrint skips its own DLL-folder set-up when
        # frozen, so make the folder known to the loader here (both the search path and the DLL directory list).
        here = str(paths.resource_dir())
        os.environ['PATH'] = here + os.pathsep + os.environ.get('PATH', '')
        if hasattr(os, 'add_dll_directory'):
            os.add_dll_directory(here)
    if paths.FROZEN and sys.platform.startswith('linux'):
        # PyInstaller's launcher points LD_LIBRARY_PATH at the bundled libraries. The loader read it once, at start-up,
        # so putting the original back changes nothing for this program but keeps the web browser we open (and any
        # other child process) from picking up our copies of Pango, GLib and friends.
        original = os.environ.pop('LD_LIBRARY_PATH_ORIG', None)
        if original is None:
            os.environ.pop('LD_LIBRARY_PATH', None)
        else:
            os.environ['LD_LIBRARY_PATH'] = original
    if bundled:
        folder = data / 'fontconfig'
        (folder / 'cache').mkdir(parents=True, exist_ok=True)
        conf = folder / 'fonts.conf'
        conf.write_text(fontconfig_text(paths.fonts_dir(), folder / 'cache'), encoding='utf-8')
        export_variable('FONTCONFIG_FILE', str(conf))
        export_variable('FONTCONFIG_PATH', str(folder))
    return data


# ---- one copy at a time, on a free port ------------------------------------------------------------------------------

def port_is_free(port, host=HOST):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind((host, port))
        except OSError:
            return False
    return True


def find_port(preferred, tries=PORT_TRIES, host=HOST):
    """The preferred port if it is free, otherwise the next free one."""
    for port in range(preferred, min(preferred + tries, 65536)):
        if port_is_free(port, host):
            return port
    raise OSError(f'No free port found from {preferred} to {preferred + tries - 1}.')


def is_ours(port, host=HOST, timeout=1.5):
    """True if an IBS Book Writer answers on that port (its login page names it)."""
    try:
        with urllib.request.urlopen(f'http://{host}:{port}/login', timeout=timeout) as response:
            return response.status == 200 and BANNER_MARK.encode() in response.read(20000)
    except (urllib.error.URLError, OSError, ValueError):
        return False


def running_instance(data_dir):
    """The port of an already running copy that uses this data folder, or None."""
    path = Path(data_dir) / INSTANCE_FILE
    try:
        info = json.loads(path.read_text())
        port = int(info['port'])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return port if is_ours(port) else None


def record_instance(data_dir, port):
    path = Path(data_dir) / INSTANCE_FILE
    path.write_text(json.dumps({'pid': os.getpid(), 'port': port, 'started': time.time()}))

    def forget():
        try:
            if json.loads(path.read_text()).get('pid') == os.getpid():
                path.unlink()
        except (OSError, ValueError):
            pass
    atexit.register(forget)


def open_browser_when_ready(port, delay_limit=15):
    def wait_then_open():
        deadline = time.time() + delay_limit
        while time.time() < deadline and not is_ours(port, timeout=0.5):
            time.sleep(0.2)
        webbrowser.open(f'http://{HOST}:{port}/')
    threading.Thread(target=wait_then_open, daemon=True).start()


# ---- main ----------------------------------------------------------------------------------------------------------------

def main(argv=None):
    args = parse_args(argv)
    if args.version:
        print(f'{BANNER_MARK} {VERSION}')
        return 0
    data = prepare_environment(args.data_dir)

    if args.setup_postgres:
        import pgsetup
        return pgsetup.run_interactive(data)

    existing = running_instance(data)
    if existing:
        print(f'{BANNER_MARK} is already running at http://{HOST}:{existing}/ - opening it.')
        if not args.no_browser:
            webbrowser.open(f'http://{HOST}:{existing}/')
        return 0

    try:
        port = find_port(args.port)
    except OSError as exc:
        print(f'Could not start: {exc}', file=sys.stderr)
        return 1

    from waitress import serve
    from ibsbook import create_app
    try:
        app = create_app()
    except Exception as exc:                               # a clear message instead of a stack trace for a user
        print(f'{BANNER_MARK} could not start: {exc}', file=sys.stderr)
        return 1

    record_instance(data, port)
    if not args.no_browser:
        open_browser_when_ready(port)
    print(f'{BANNER_MARK} {VERSION} is running at http://{HOST}:{port}/')
    print(f'Your data is in {data}')
    print('Close this window (or press Ctrl+C) to stop it.')
    try:
        serve(app, host=HOST, port=port, threads=8, ident=BANNER_MARK.replace(' ', ''), clear_untrusted_proxy_headers=True)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == '__main__':
    sys.exit(main())
