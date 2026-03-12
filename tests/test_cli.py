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
    # search is the primary command; query is a hidden alias
    assert "search" in result.stdout
    assert "status" in result.stdout


def test_alcove_query_alias_still_works():
    """The 'query' alias must remain functional for backwards compatibility."""
    result = subprocess.run(
        [sys.executable, "-m", "alcove", "query", "--help"],
        capture_output=True, text=True
    )
    assert result.returncode == 0
    assert "--k" in result.stdout
    assert "--collection" in result.stdout


def test_alcove_mirrulations_demo_help_mentions_agency_filter():
    result = subprocess.run(
        [sys.executable, "-m", "alcove", "mirrulations-demo", "--help"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert "--agency" in result.stdout
    assert "mirrulations_docs" in result.stdout


def test_alcove_version():
    result = subprocess.run(
        [sys.executable, "-m", "alcove", "--version"],
        capture_output=True, text=True
    )
    assert result.returncode == 0
    assert "0.3.0" in result.stdout
