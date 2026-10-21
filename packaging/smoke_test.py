"""End-to-end check of a built desktop program (the Linux file or IBSBookWriter.exe).

    python packaging/smoke_test.py dist/ibs-book-writer-linux-x86_64_v1_0
    python packaging/smoke_test.py dist\\IBSBookWriter_v1_0.exe

It starts the program on a free port with a throw-away data folder, then uses it the way a person would: registers,
writes a small book (text, a heading, a list, a table and a picture), generates the PDF, EPUB, HTML and ODT, checks
what came out, replaces and deletes stored copies, and finally stops the program. Standard library only, so it runs
the same wherever the program was built. Exit status 0 means everything passed.
"""
import http.cookiejar
import io
import json
import os
import re
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
import zlib
from pathlib import Path

HOST = '127.0.0.1'
STARTUP_SECONDS = 120            # a one-file program unpacks itself first, and a virus scanner may look at it
failures = []


def check(condition, label):
    print(('  ok    ' if condition else '  FAIL  ') + label, flush=True)
    if not condition:
        failures.append(label)
    return condition


def expected_display_name():
    """'IBS Book Writer v1_0', read from app/version.py in this checkout (the single source of the number)."""
    source = (Path(__file__).resolve().parent.parent / 'app' / 'version.py').read_text()
    name = re.search(r"^APP_NAME = '([^']+)'", source, re.M).group(1)
    number = re.search(r"^APP_VERSION = '([^']+)'", source, re.M).group(1)
    return f'{name} v{number}'


def free_port():
    with socket.socket() as probe:
        probe.bind((HOST, 0))
        return probe.getsockname()[1]


def tiny_png(width=64, height=48):
    """A small valid PNG (a colour gradient), made without any imaging library."""
    rows = b''.join(b'\x00' + b''.join(bytes((x * 4 % 256, y * 5 % 256, 160)) for x in range(width)) for y in range(height))

    def chunk(kind, data):
        body = kind + data
        return struct.pack('>I', len(data)) + body + struct.pack('>I', zlib.crc32(body) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b''))


class Browser:
    """A very small browser: cookies, CSRF tokens, form posts, multipart uploads."""

    def __init__(self, base):
        self.base = base
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def get(self, path):
        response = self.opener.open(self.base + path, timeout=300)
        return response.read(), response

    def token(self, page_path):
        page, _ = self.get(page_path)
        match = (re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', page)
                 or re.search(rb'value="([^"]+)"[^>]*name="csrf_token"', page))
        if match is None:
            raise RuntimeError(f'no CSRF token on {page_path}')
        return match.group(1)

    def post(self, path, form, token_from, files=None):
        form = dict(form, csrf_token=self.token(token_from).decode())
        if files:
            boundary = uuid.uuid4().hex
            body = io.BytesIO()
            for key, value in form.items():
                body.write(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
            for key, (name, data, mime) in files.items():
                body.write(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"; filename="{name}"\r\n'
                           f'Content-Type: {mime}\r\n\r\n'.encode() + data + b'\r\n')
            body.write(f'--{boundary}--\r\n'.encode())
            request = urllib.request.Request(self.base + path, body.getvalue(),
                                             {'Content-Type': f'multipart/form-data; boundary={boundary}'})
        else:
            request = urllib.request.Request(self.base + path, urllib.parse.urlencode(form).encode())
        response = self.opener.open(request, timeout=300)
        return response.read(), response


def start(binary, data_dir, port, log):
    return subprocess.Popen([str(binary), '--no-browser', '--port', str(port), '--data-dir', str(data_dir)],
                            stdout=log, stderr=subprocess.STDOUT, cwd=str(data_dir.parent))


def wait_until_up(base, process):
    deadline = time.time() + STARTUP_SECONDS
    while time.time() < deadline:
        if process.poll() is not None:
            return None
        try:
            with urllib.request.urlopen(base + '/login', timeout=2) as response:
                if response.status == 200 and b'IBS Book Writer' in response.read():
                    return True
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(0.5)
    return False


def sniff(data):
    """Which of the four formats a file is."""
    if data.startswith(b'%PDF'):
        return 'pdf'
    if data[:2] == b'PK':
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            first = archive.read('mimetype')
        return {b'application/epub+zip': 'epub', b'application/vnd.oasis.opendocument.text': 'odt'}.get(first, 'zip?')
    if data.lstrip()[:15].lower().startswith(b'<!doctype html'):
        return 'html'
    return '?'


def stored_ids(browser, book_id):
    page, _ = browser.get(f'/books/{book_id}/renders')
    return sorted({int(i) for i in re.findall(rb'/renders/(\d+)/download', page)})


def run(binary):
    binary = Path(binary).resolve()
    work = Path(tempfile.mkdtemp(prefix='ibs-smoke-'))
    data = work / 'data'
    port = free_port()
    base = f'http://{HOST}:{port}'
    log_path = work / 'program.log'
    print(f'Testing {binary} ({binary.stat().st_size / 1e6:.0f} MB), data folder {data}')

    expected = expected_display_name()
    version = subprocess.run([str(binary), '--version'], capture_output=True, text=True, timeout=STARTUP_SECONDS)
    check(version.returncode == 0 and version.stdout.strip() == expected, f'--version prints "{version.stdout.strip()}" (expected "{expected}")')
    check(expected.split(' v')[-1] in binary.name, f'the file name carries the version ({binary.name})')

    log = open(log_path, 'wb')
    began = time.time()
    process = start(binary, data, port, log)
    try:
        up = wait_until_up(base, process)
        if not check(up, f'starts and serves the login page ({time.time() - began:.1f} s)'):
            return
        login_page, _ = Browser(base).get('/login')
        check(f'v{expected.split(" v")[-1]}'.encode() in login_page, 'the page shows the program version')
        check((data / 'ibsbook.db').is_file(), 'keeps its SQLite database in the data folder')
        check((data / 'secret_key').is_file(), 'made its own secret key')

        me = Browser(base)
        me.post('/register', {'username': 'smoke', 'password': 'correct-horse-battery',
                              'confirm_password': 'correct-horse-battery'}, '/register')
        _, response = me.post('/books/new', {'title': 'Smoke Test Book', 'author_name': 'Smoke Tester'}, '/books/new')
        book_id = re.search(r'/books/(\d+)$', response.geturl())
        if not check(book_id, 'registers and creates a book'):
            return
        book_id = book_id.group(1)
        _, response = me.post(f'/books/{book_id}/chapters/new', {'title': 'The First Chapter'}, f'/books/{book_id}')
        chapter_id = re.search(r'/chapters/(\d+)', response.geturl()).group(1)
        page = f'/chapters/{chapter_id}'
        prose = ' '.join(['The extraordinarily accommodating gentleman considered the photographic evidence carefully.'] * 12)
        me.post(f'/chapters/{chapter_id}/blocks/new', {'block_type': 'heading', 'content_text': 'A Heading', 'heading_level': '2'}, page)
        me.post(f'/chapters/{chapter_id}/blocks/new', {'block_type': 'text', 'content_text': prose + '\n\n' + prose}, page)
        me.post(f'/chapters/{chapter_id}/blocks/new', {'block_type': 'list', 'content_text': 'First\nSecond\nThird'}, page)
        me.post(f'/chapters/{chapter_id}/blocks/new', {'block_type': 'table', 'content_text': 'a | b\n1 | 2', 'table_header': '1'}, page)
        me.post(f'/chapters/{chapter_id}/blocks/new', {'block_type': 'image', 'content_text': 'A caption'}, page,
                files={'image': ('gradient.png', tiny_png(), 'image/png')})
        chapter_page, _ = me.get(page)
        check(b'A Heading' in chapter_page and b'A caption' in chapter_page, 'adds a heading, text, list, table and a picture')

        me.post(f'/books/{book_id}/renders/generate', {'all': '1'}, f'/books/{book_id}/renders')
        ids = stored_ids(me, book_id)
        check(len(ids) == 4, f'generates four stored copies (found {len(ids)})')
        files = {}
        for render_id in ids:
            data_bytes, _ = me.get(f'/renders/{render_id}/download')
            files[sniff(data_bytes)] = (render_id, data_bytes)
        check(sorted(files) == ['epub', 'html', 'odt', 'pdf'], f'the copies are a PDF, EPUB, HTML and ODT ({sorted(files)})')

        pdf = files['pdf'][1]
        try:
            from pypdf import PdfReader
        except ImportError:                          # page count and fonts sit in compressed PDF objects
            check(len(pdf) > 5000 and pdf.rstrip().endswith(b'%%EOF'), f'the PDF is complete ({len(pdf)} bytes; '
                  'install pypdf to also check its pages and fonts)')
        else:
            reader = PdfReader(io.BytesIO(pdf))
            check(len(reader.pages) >= 3, f'the PDF has {len(reader.pages)} pages')
            fonts = set()
            for page in reader.pages:
                for ref in (page['/Resources'].get('/Font') or {}).values():
                    fonts.add(str(ref.get_object().get('/BaseFont')).split('+')[-1])
            check(fonts and all(name.startswith('Liberation-Serif') for name in fonts),
                  f'the PDF is set in the bundled Liberation fonts ({sorted(fonts)})')
        epub = zipfile.ZipFile(io.BytesIO(files['epub'][1]))
        chapter_files = [n for n in epub.namelist() if n.endswith('.xhtml') and b'The First Chapter' in epub.read(n)]
        check(chapter_files and any(n.startswith('OEBPS/images/') or '/images/' in n for n in epub.namelist()),
              'the EPUB has the chapter and its picture')
        html = files['html'][1]
        check(b'The First Chapter' in html and b'data:image/' in html, 'the HTML is one file with the picture inside it')
        odt = zipfile.ZipFile(io.BytesIO(files['odt'][1]))
        check('The First Chapter' in odt.read('content.xml').decode() and any(n.startswith('Pictures/') for n in odt.namelist()),
              'the ODT has the chapter and its picture')
        check(all(b'Version 1' in blob or b'Version' in blob for blob in (html,)), 'the version and date stamp is in the HTML')

        stored = list((data / 'uploads' / 'renders').rglob('*.*'))
        check(len(stored) == 4, f'the stored books are files inside the data folder ({len(stored)})')

        me.post(f'/renders/{files["pdf"][0]}/replace', {}, f'/books/{book_id}/renders')
        after = stored_ids(me, book_id)
        check(len(after) == 4 and len(list((data / 'uploads' / 'renders').rglob('*.*'))) == 4, 'replacing keeps one copy per format')
        me.post(f'/renders/{files["odt"][0]}/delete', {}, f'/books/{book_id}/renders')
        check(len(stored_ids(me, book_id)) == 3 and len(list((data / 'uploads' / 'renders').rglob('*.*'))) == 3,
              'deleting removes the record and the file')
    finally:
        process.terminate()
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            process.kill()
        log.close()
    check(not (data / 'running.json').exists() or process.returncode is not None, 'stops when asked')
    if failures:
        print('\nProgram output:\n' + log_path.read_text(errors='replace')[-4000:])


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    try:
        run(sys.argv[1])
    except Exception as exc:                       # an unexpected error is a failure, with the evidence printed
        import traceback
        traceback.print_exc()
        failures.append(f'unexpected error: {exc}')
    print(f'\n{"FAILED: " + str(len(failures)) + " check(s)" if failures else "All checks passed."}')
    sys.exit(1 if failures else 0)
