"""Gunicorn settings for IBS Book Writer.

Run from anywhere with:   gunicorn --config deploy/gunicorn.conf.py

Everything can be overridden by environment variable, so the systemd unit
or a shell can tune it without editing this file.
"""
import os
from pathlib import Path

# The Flask modules (ibsbook.py, config.py, ...) live in app/.
chdir = str(Path(__file__).resolve().parent.parent / 'app')
wsgi_app = 'ibsbook:create_app()'

# Listen on loopback only; the reverse proxy (nginx/Caddy) is the public face.
bind = os.environ.get('GUNICORN_BIND', '127.0.0.1:8000')

# Building a PDF/EPUB is CPU-bound and can use a few hundred MB per render, so
# size workers by RAM as well as CPU. 3 is a good start for 2 vCPU / 2-4 GB.
workers = int(os.environ.get('WEB_CONCURRENCY', '3'))

# A large book can take several seconds to lay out (multi-pass WeasyPrint).
timeout = int(os.environ.get('GUNICORN_TIMEOUT', '180'))
graceful_timeout = 30
keepalive = 5

# Recycle workers now and then to cap memory growth from rendering.
max_requests = 1000
max_requests_jitter = 100

# Only trust X-Forwarded-Proto/For from a proxy on this host. nginx sends
# X-Forwarded-Proto, which makes request.scheme "https" inside Flask.
forwarded_allow_ips = os.environ.get('FORWARDED_ALLOW_IPS', '127.0.0.1')

# Newer gunicorn releases open a control socket under /run/user/<uid>, which a
# sandboxed system service does not have. It is not needed here (older
# releases simply ignore this setting).
control_socket_disable = True

# Log to stdout/stderr; systemd's journal collects it.
accesslog = '-'
errorlog = '-'
loglevel = os.environ.get('GUNICORN_LOG_LEVEL', 'info')
