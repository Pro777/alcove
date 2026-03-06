import subprocess
import sys


def test_alcove_help_exits_zero():
    result = subprocess.run(
        [sys.executable, "-m", "alcove", "--help"],
        capture_output=True, text=True
    )
    assert result.returncode == 0
    assert "serve" in result.stdout
    assert "ingest" in result.stdout
    assert "query" in result.stdout


def test_alcove_version():
    result = subprocess.run(
        [sys.executable, "-m", "alcove", "--version"],
        capture_output=True, text=True
    )
    assert result.returncode == 0
    assert "0.3.0" in result.stdout
