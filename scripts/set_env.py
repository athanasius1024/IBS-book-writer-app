#!/usr/bin/env python3
"""Set KEY=VALUE in the project's .env file (creating it, mode 600, if needed).

Usage: set_env.py KEY VALUE [--if-empty]

Values are written double-quoted with backslashes and quotes escaped, so
passwords containing special characters survive a round trip through
python-dotenv. With --if-empty an existing non-empty value is left alone.
"""
import os
import re
import sys
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parent.parent / '.env'


def current_value(lines, key):
    for line in lines:
        match = re.match(rf'^{re.escape(key)}=(.*)$', line)
        if match:
            return match.group(1).strip().strip('"\'')
    return None


def main(argv):
    if len(argv) not in (3, 4):
        sys.exit(__doc__)
    key, value = argv[1], argv[2]
    if_empty = len(argv) == 4 and argv[3] == '--if-empty'
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', key):
        sys.exit(f'Invalid variable name: {key}')

    lines = ENV_FILE.read_text().splitlines() if ENV_FILE.exists() else []
    existing = current_value(lines, key)
    if if_empty and existing:
        return

    escaped = value.replace('\\', '\\\\').replace('"', '\\"')
    new_line = f'{key}="{escaped}"'
    out, found = [], False
    for line in lines:
        if re.match(rf'^{re.escape(key)}=', line):
            out.append(new_line)
            found = True
        else:
            out.append(line)
    if not found:
        out.append(new_line)

    fd = os.open(ENV_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as handle:
        handle.write('\n'.join(out) + '\n')
    os.chmod(ENV_FILE, 0o600)


if __name__ == '__main__':
    main(sys.argv)
