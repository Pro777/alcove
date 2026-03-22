"""Tests for tools/batch-ingest/batch.py (#454).

All subprocess calls are replaced by a fake run_fn.
No real tools are invoked in CI.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Load standalone module
# ---------------------------------------------------------------------------

_SCRIPT = Path(__file__).parent.parent / "tools" / "batch-ingest" / "batch.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("batch_ingest", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["batch_ingest"] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _load_module()

load_manifest = _mod.load_manifest
validate_manifest = _mod.validate_manifest
build_command = _mod.build_command
run_job = _mod.run_job
run_manifest = _mod.run_manifest
TOOL_SCRIPTS = _mod.TOOL_SCRIPTS
BATCH_VERSION = _mod.BATCH_VERSION


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(_SCRIPT).resolve().parent.parent.parent

_MINIMAL_MANIFEST = {
    "batch_version": BATCH_VERSION,
    "jobs": [
        {
            "id": "arxiv-refresh",
            "enabled": True,
            "tool": "corpus-refresh",
            "args": {"--collection": "arxiv", "--out": "/tmp/arxiv.jsonl"},
        },
        {
            "id": "github-issues",
            "enabled": True,
            "tool": "github-ingest",
            "args": {"--repo": "Pro777/alcove"},
        },
        {
            "id": "chroma-sync-disabled",
            "enabled": False,
            "tool": "chroma-sync",
            "subcommand": "sync",
            "args": {},
        },
    ],
}


def _ok_run_fn(cmd, **_kwargs):
    return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="done", stderr="")


def _fail_run_fn(cmd, **_kwargs):
    return subprocess.CompletedProcess(
        args=cmd, returncode=1, stdout="", stderr="something went wrong"
    )


def _write_manifest(tmp_path: Path, manifest: dict) -> Path:
    p = tmp_path / "jobs.json"
    p.write_text(json.dumps(manifest))
    return p


# ---------------------------------------------------------------------------
# load_manifest
# ---------------------------------------------------------------------------


class TestLoadManifest:
    def test_loads_valid_manifest(self, tmp_path):
        p = _write_manifest(tmp_path, _MINIMAL_MANIFEST)
        m = load_manifest(p)
        assert "jobs" in m

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_manifest(tmp_path / "nonexistent.json")

    def test_wrong_version_raises(self, tmp_path):
        bad = {**_MINIMAL_MANIFEST, "batch_version": 99}
        p = _write_manifest(tmp_path, bad)
        with pytest.raises(ValueError, match="batch_version"):
            load_manifest(p)

    def test_missing_jobs_key_raises(self, tmp_path):
        bad = {"batch_version": BATCH_VERSION}
        p = _write_manifest(tmp_path, bad)
        with pytest.raises(ValueError, match="jobs"):
            load_manifest(p)


# ---------------------------------------------------------------------------
# validate_manifest
# ---------------------------------------------------------------------------


class TestValidateManifest:
    def test_valid_manifest_returns_no_errors(self):
        errors = validate_manifest(_MINIMAL_MANIFEST)
        assert errors == []

    def test_missing_id_reported(self):
        manifest = {
            "batch_version": BATCH_VERSION,
            "jobs": [{"tool": "corpus-refresh", "enabled": True}],
        }
        errors = validate_manifest(manifest)
        assert any("id" in e for e in errors)

    def test_missing_tool_reported(self):
        manifest = {
            "batch_version": BATCH_VERSION,
            "jobs": [{"id": "job1", "enabled": True}],
        }
        errors = validate_manifest(manifest)
        assert any("tool" in e for e in errors)

    def test_unknown_tool_reported(self):
        manifest = {
            "batch_version": BATCH_VERSION,
            "jobs": [{"id": "job1", "tool": "nonexistent-tool", "enabled": True}],
        }
        errors = validate_manifest(manifest)
        assert any("nonexistent-tool" in e for e in errors)

    def test_duplicate_id_reported(self):
        manifest = {
            "batch_version": BATCH_VERSION,
            "jobs": [
                {"id": "same", "tool": "corpus-refresh", "enabled": True},
                {"id": "same", "tool": "github-ingest", "enabled": True},
            ],
        }
        errors = validate_manifest(manifest)
        assert any("duplicate" in e for e in errors)

    def test_non_bool_enabled_reported(self):
        manifest = {
            "batch_version": BATCH_VERSION,
            "jobs": [{"id": "j", "tool": "corpus-refresh", "enabled": "yes"}],
        }
        errors = validate_manifest(manifest)
        assert any("enabled" in e for e in errors)


# ---------------------------------------------------------------------------
# build_command
# ---------------------------------------------------------------------------


class TestBuildCommand:
    def test_starts_with_python(self):
        job = {"id": "j", "tool": "corpus-refresh", "enabled": True, "args": {}}
        cmd = build_command(job, _REPO_ROOT)
        assert cmd[0].endswith("python") or "python" in cmd[0]

    def test_script_path_in_command(self):
        job = {"id": "j", "tool": "corpus-refresh", "enabled": True, "args": {}}
        cmd = build_command(job, _REPO_ROOT)
        cmd_str = " ".join(cmd)
        assert "corpus-refresh" in cmd_str

    def test_flags_appended(self):
        job = {
            "id": "j",
            "tool": "corpus-refresh",
            "enabled": True,
            "args": {"--collection": "arxiv"},
        }
        cmd = build_command(job, _REPO_ROOT)
        assert "--collection" in cmd
        assert "arxiv" in cmd

    def test_subcommand_appended(self):
        job = {
            "id": "j",
            "tool": "chroma-sync",
            "subcommand": "sync",
            "enabled": True,
            "args": {},
        }
        cmd = build_command(job, _REPO_ROOT)
        assert "sync" in cmd

    def test_list_args_expanded(self):
        job = {
            "id": "j",
            "tool": "chroma-sync",
            "subcommand": "sync",
            "enabled": True,
            "args": {"--collections": ["arxiv", "psyarxiv"]},
        }
        cmd = build_command(job, _REPO_ROOT)
        assert "arxiv" in cmd
        assert "psyarxiv" in cmd

    def test_bool_true_flag_included(self):
        job = {
            "id": "j",
            "tool": "corpus-refresh",
            "enabled": True,
            "args": {"--dry-run": True},
        }
        cmd = build_command(job, _REPO_ROOT)
        assert "--dry-run" in cmd

    def test_bool_false_flag_excluded(self):
        job = {
            "id": "j",
            "tool": "corpus-refresh",
            "enabled": True,
            "args": {"--dry-run": False},
        }
        cmd = build_command(job, _REPO_ROOT)
        assert "--dry-run" not in cmd


# ---------------------------------------------------------------------------
# run_job
# ---------------------------------------------------------------------------


class TestRunJob:
    def test_ok_result_on_exit_zero(self):
        job = _MINIMAL_MANIFEST["jobs"][0]
        result = run_job(job, _REPO_ROOT, run_fn=_ok_run_fn)
        assert result["result"] == "ok"
        assert result["exit_code"] == 0

    def test_failed_result_on_nonzero_exit(self):
        job = _MINIMAL_MANIFEST["jobs"][0]
        result = run_job(job, _REPO_ROOT, run_fn=_fail_run_fn)
        assert result["result"] == "failed"
        assert result["exit_code"] == 1

    def test_error_message_captured(self):
        job = _MINIMAL_MANIFEST["jobs"][0]
        result = run_job(job, _REPO_ROOT, run_fn=_fail_run_fn)
        assert "something went wrong" in (result["error"] or "")

    def test_job_id_in_result(self):
        job = _MINIMAL_MANIFEST["jobs"][0]
        result = run_job(job, _REPO_ROOT, run_fn=_ok_run_fn)
        assert result["job_id"] == "arxiv-refresh"

    def test_timestamps_set(self):
        job = _MINIMAL_MANIFEST["jobs"][0]
        result = run_job(job, _REPO_ROOT, run_fn=_ok_run_fn)
        assert result["started_at"] is not None
        assert result["finished_at"] is not None


# ---------------------------------------------------------------------------
# run_manifest
# ---------------------------------------------------------------------------


class TestRunManifest:
    def test_returns_result_per_job(self):
        results = run_manifest(_MINIMAL_MANIFEST, _REPO_ROOT, run_fn=_ok_run_fn)
        assert len(results) == len(_MINIMAL_MANIFEST["jobs"])

    def test_disabled_jobs_get_disabled_result(self):
        results = run_manifest(_MINIMAL_MANIFEST, _REPO_ROOT, run_fn=_ok_run_fn)
        disabled = [r for r in results if r["result"] == "disabled"]
        assert len(disabled) == 1
        assert disabled[0]["job_id"] == "chroma-sync-disabled"

    def test_job_id_filter_runs_only_matching_job(self):
        results = run_manifest(
            _MINIMAL_MANIFEST, _REPO_ROOT, job_id_filter="arxiv-refresh", run_fn=_ok_run_fn
        )
        assert len(results) == 1
        assert results[0]["job_id"] == "arxiv-refresh"

    def test_all_ok_when_all_succeed(self):
        results = run_manifest(_MINIMAL_MANIFEST, _REPO_ROOT, run_fn=_ok_run_fn)
        ok = [r for r in results if r["result"] == "ok"]
        assert len(ok) == 2  # 2 enabled jobs

    def test_failure_recorded_when_tool_fails(self):
        results = run_manifest(_MINIMAL_MANIFEST, _REPO_ROOT, run_fn=_fail_run_fn)
        failed = [r for r in results if r["result"] == "failed"]
        assert len(failed) == 2


# ---------------------------------------------------------------------------
# TOOL_SCRIPTS completeness
# ---------------------------------------------------------------------------


class TestToolScripts:
    def test_has_known_tools(self):
        for tool in ("corpus-refresh", "github-ingest", "chroma-sync", "index-sign"):
            assert tool in TOOL_SCRIPTS

    def test_all_scripts_have_paths(self):
        for name, path in TOOL_SCRIPTS.items():
            assert path.endswith(".py"), f"{name}: expected .py script, got {path}"


# ---------------------------------------------------------------------------
# CLI: validate
# ---------------------------------------------------------------------------


class TestCliValidate:
    def test_valid_manifest_returns_zero(self, tmp_path):
        p = _write_manifest(tmp_path, _MINIMAL_MANIFEST)
        rc = _mod.main(["--manifest", str(p), "validate"])
        assert rc == 0

    def test_invalid_manifest_returns_nonzero(self, tmp_path):
        bad = {
            "batch_version": BATCH_VERSION,
            "jobs": [{"tool": "nonexistent-tool", "enabled": True}],
        }
        p = _write_manifest(tmp_path, bad)
        rc = _mod.main(["--manifest", str(p), "validate"])
        assert rc != 0

    def test_missing_manifest_returns_nonzero(self, tmp_path):
        rc = _mod.main(["--manifest", str(tmp_path / "nope.json"), "validate"])
        assert rc != 0


# ---------------------------------------------------------------------------
# CLI: run
# ---------------------------------------------------------------------------


class TestCliRun:
    def test_run_all_ok(self, tmp_path):
        p = _write_manifest(tmp_path, _MINIMAL_MANIFEST)
        rc = _mod.main(["--manifest", str(p), "run"], run_fn=_ok_run_fn)
        assert rc == 0

    def test_run_with_failure_returns_nonzero(self, tmp_path):
        p = _write_manifest(tmp_path, _MINIMAL_MANIFEST)
        rc = _mod.main(["--manifest", str(p), "run"], run_fn=_fail_run_fn)
        assert rc != 0

    def test_run_writes_report(self, tmp_path):
        p = _write_manifest(tmp_path, _MINIMAL_MANIFEST)
        report = tmp_path / "report.json"
        _mod.main(
            ["--manifest", str(p), "run", "--report-out", str(report)],
            run_fn=_ok_run_fn,
        )
        assert report.is_file()
        data = json.loads(report.read_text())
        assert isinstance(data, list)

    def test_run_single_job(self, tmp_path):
        calls = []

        def recording_run_fn(cmd, **_kwargs):
            calls.append(cmd)
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

        p = _write_manifest(tmp_path, _MINIMAL_MANIFEST)
        _mod.main(
            ["--manifest", str(p), "run", "--job", "arxiv-refresh"],
            run_fn=recording_run_fn,
        )
        # Only one subprocess call should have been made.
        assert len(calls) == 1
