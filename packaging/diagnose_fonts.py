"""Why is the PDF not set in the bundled fonts? Prints what fontconfig and WeasyPrint actually do.

    python packaging/diagnose_fonts.py            (run by build_windows.ps1 when the smoke test fails)

Each case runs in a fresh process, because fontconfig reads its settings once, when it first loads.
"""
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FONT = ROOT / 'app' / 'fonts' / 'LiberationSerif-Regular.ttf'

CHILD = r'''
import io, json, os, sys
mode, font, conf = sys.argv[1:4]
if sys.platform == 'win32' and os.environ.get('IBS_NATIVE_LIBS') is None and os.environ.get('MSYS2_ROOT'):
    os.environ.setdefault('WEASYPRINT_DLL_DIRECTORIES', os.environ['MSYS2_ROOT'] + r'\mingw64\bin')
if mode in ('runtime', 'runtime+putenv'):
    os.environ['FONTCONFIG_FILE'] = conf
    if mode == 'runtime+putenv' and sys.platform == 'win32':
        import ctypes
        for dll in ('msvcrt', 'ucrtbase'):
            try:
                getattr(ctypes.cdll, dll)._putenv(('FONTCONFIG_FILE=' + conf).encode('mbcs'))
            except Exception as exc:
                print('putenv', dll, 'failed', exc)
out = {'mode': mode, 'python_env': os.environ.get('FONTCONFIG_FILE')}
if sys.platform == 'win32':
    import ctypes
    for dll in ('msvcrt', 'ucrtbase'):
        try:
            fn = getattr(ctypes.cdll, dll).getenv
            fn.restype = ctypes.c_char_p
            out['getenv_' + dll] = (fn(b'FONTCONFIG_FILE') or b'').decode('mbcs') or None
        except Exception as exc:
            out['getenv_' + dll] = 'error ' + str(exc)
import logging
log = io.StringIO()
logger = logging.getLogger('weasyprint')
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler(log))
import weasyprint
from weasyprint.text.ffi import ffi, fontconfig
cfg = fontconfig.FcInitLoadConfigAndFonts()
out['system_fonts'] = fontconfig.FcConfigGetFonts(cfg, fontconfig.FcSetSystem).nfont
files = []
lst = fontconfig.FcConfigGetConfigFiles(cfg)
while True:
    item = fontconfig.FcStrListNext(lst)
    if item == ffi.NULL:
        break
    files.append(ffi.string(item).decode(errors='replace'))
out['config_files'] = files[:6]
html = ('<style>@font-face{font-family:"Liberation Serif";src:url("%s")}'
        'body{font-family:"Liberation Serif","Times New Roman",serif}</style><p>Hello fonts</p>') % ('file:///' + font.replace('\\', '/').lstrip('/'))
pdf = weasyprint.HTML(string=html).write_pdf()
try:
    from pypdf import PdfReader
    names = set()
    for page in PdfReader(io.BytesIO(pdf)).pages:
        for ref in (page['/Resources'].get('/Font') or {}).values():
            names.add(str(ref.get_object().get('/BaseFont')))
    out['pdf_fonts'] = sorted(names)
except Exception as exc:
    out['pdf_fonts'] = 'unreadable: %s' % exc
out['weasyprint_log'] = [line for line in log.getvalue().splitlines() if 'ont' in line][:12]
print('RESULT ' + json.dumps(out))
'''


def main():
    work = Path(tempfile.mkdtemp(prefix='ibs-fontdiag-'))
    conf = work / 'fonts.conf'
    conf.write_text('<?xml version="1.0"?>\n<fontconfig>\n  <dir>%s</dir>\n  <cachedir>%s</cachedir>\n</fontconfig>\n'
                    % (ROOT / 'app' / 'fonts', work / 'cache'), encoding='utf-8')
    print('font file exists:', FONT.is_file(), '| python', sys.version.split()[0], '| platform', sys.platform)
    base = {k: v for k, v in os.environ.items() if not k.startswith('FONTCONFIG')}
    cases = [('default', {}), ('env-before-start', {'FONTCONFIG_FILE': str(conf)}), ('runtime', {}), ('runtime+putenv', {})]
    for mode, extra in cases:
        proc = subprocess.run([sys.executable, '-c', CHILD, mode, str(FONT), str(conf)], capture_output=True, text=True,
                              env={**base, **extra}, timeout=300)
        lines = [l for l in proc.stdout.splitlines() if l.startswith('RESULT ')]
        print(f'--- {mode}: exit {proc.returncode}')
        if lines:
            for key, value in json.loads(lines[-1][7:]).items():
                print(f'    {key}: {value}')
        else:
            print(proc.stdout[-1500:], proc.stderr[-1500:])


if __name__ == '__main__':
    main()
