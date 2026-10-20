"""Runs the Node unit tests for the Insert image dialog's crop maths (skipped when Node is missing)."""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.skipif(shutil.which('node') is None, reason='Node.js is not installed')
def test_insert_image_dialog_helpers():
    result = subprocess.run(['node', '--test', str(ROOT / 'tests' / 'js' / 'images.test.js')], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
