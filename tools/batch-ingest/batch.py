"""Alcove batch ingest runner — orchestrates pipeline jobs without Conductor (#454).

Reads a job manifest (JSON) and runs each enabled ingest job in sequence.
Each job invokes an alcove tool (corpus-refresh, github-ingest, chroma-sync,
index-sign, etc.) via subprocess.  Results are logged to a run report.

This enables alcove to run as a self-contained local processor without
requiring Conductor orchestration.  Run via launchd or cron for fully
autonomous operation.

Manifest format
---------------
``~/.alcove/batch/jobs.json``::

    {
        "batch_version": 1,
        "jobs": [
            {
                "id": "arxiv-refresh",
                "enabled": true,
                "tool": "corpus-refresh",
                "args": {
                    "--collection": "arxiv",
                    "--out": "data/raw/arxiv/new_papers.jsonl"
                },
                "description": "Nightly arXiv corpus refresh"
            },
            {
                "id": "github-issues",
                "enabled": true,
                "tool": "github-ingest",
                "args": {
                    "--repo": "Pro777/alcove",
                    "--types": ["issues", "prs"]
                }
            },
            {
                "id": "chroma-sync",
                "enabled": false,
                "tool": "chroma-sync",
                "subcommand": "sync",
                "args": {
                    "--src-host": "localhost",
                    "--src-port": "8003",
                    "--collections": ["arxiv", "psyarxiv"],
                    "--dst-path": "~/.alcove/chroma"
                }
            }
        ]
    }

Tool-to-script mapping
----------------------
Each ``tool`` name maps to a script path relative to the repo root.
Built-in mappings::

    corpus-refresh  → tools/corpus-refresh/refresh.py
    github-ingest   → tools/github-ingest/ingest.py
    chroma-sync     → tools/chroma-sync/sync.py
    index-sign      → tools/index-sign/sign.py
    whisper-subtitle → tools/whisper-subtitle/subtitle.py
    ncaa-bracket    → tools/ncaa-bracket/predict.py
    nfl-draft       → tools/nfl-draft/analyze.py

CLI usage
---------

Run all enabled jobs from the default manifest::

    python tools/batch-ingest/batch.py run

Run a specific job by ID::

    python tools/batch-ingest/batch.py run --job arxiv-refresh

Validate a manifest without running::

    python tools/batch-ingest/batch.py validate --manifest /path/to/jobs.json

Show job status summary::

    python tools/batch-ingest/batch.py status
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Repo root on sys.path for hermetic testing.
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_MANIFEST_PATH = Path.home() / ".alcove" / "batch" / "jobs.json"
DEFAULT_LOG_PATH = Path.home() / ".alcove" / "logs" / "batch.log"
BATCH_VERSION = 1

# Map tool names to script paths relative to repo root.
TOOL_SCRIPTS: dict[str, str] = {
    "corpus-refresh": "tools/corpus-refresh/refresh.py",
    "github-ingest": "tools/github-ingest/ingest.py",
    "chroma-sync": "tools/chroma-sync/sync.py",
    "index-sign": "tools/index-sign/sign.py",
    "whisper-subtitle": "tools/whisper-subtitle/subtitle.py",
    "ncaa-bracket": "tools/ncaa-bracket/predict.py",
    "nfl-draft": "tools/nfl-draft/analyze.py",
    "asl-gloss": "tools/asl-gloss/gloss.py",
    "demo-ranking": "tools/demo-ranking/score.py",
    "federation": "tools/federation/peers.py",
}

# Job result codes.
RESULT_OK = "ok"
RESULT_FAILED = "failed"
RESULT_DISABLED = "disabled"


# ---------------------------------------------------------------------------
# Manifest I/O
# ---------------------------------------------------------------------------


def load_manifest(manifest_path: Path) -> dict:
    """Load job manifest from *manifest_path*.

    Returns
    -------
    dict
        Parsed manifest with guaranteed ``jobs`` list.

    Raises
    ------
    FileNotFoundError
        If *manifest_path* does not exist.
    ValueError
        If the manifest is invalid or wrong version.
    """
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    version = data.get("batch_version")
    if version != BATCH_VERSION:
        raise ValueError(
            f"Unsupported batch_version {version!r} (expected {BATCH_VERSION})"
        )
    if "jobs" not in data or not isinstance(data["jobs"], list):
        raise ValueError("Manifest missing 'jobs' list")
    return data


def validate_manifest(manifest: dict) -> list[str]:
    """Validate *manifest* and return a list of error messages (empty = valid).

    Checks:
    - All jobs have ``id`` and ``tool`` keys.
    - All job IDs are unique.
    - All ``tool`` values are in :data:`TOOL_SCRIPTS`.
    - ``enabled`` is a bool (if present).
    """
    errors: list[str] = []
    seen_ids: set[str] = set()

    for i, job in enumerate(manifest.get("jobs", [])):
        prefix = f"Job[{i}]"

        job_id = job.get("id")
        if not job_id:
            errors.append(f"{prefix}: missing 'id'")
        elif job_id in seen_ids:
            errors.append(f"{prefix}: duplicate id '{job_id}'")
        else:
            seen_ids.add(job_id)

        tool = job.get("tool")
        if not tool:
            errors.append(f"{prefix}: missing 'tool'")
        elif tool not in TOOL_SCRIPTS:
            errors.append(
                f"{prefix} '{job_id}': unknown tool '{tool}' "
                f"(known: {', '.join(sorted(TOOL_SCRIPTS))})"
            )

        enabled = job.get("enabled", True)
        if not isinstance(enabled, bool):
            errors.append(f"{prefix} '{job_id}': 'enabled' must be bool, got {type(enabled).__name__}")

    return errors


# ---------------------------------------------------------------------------
# Command construction
# ---------------------------------------------------------------------------


def build_command(
    job: dict,
    repo_root: Path,
    python: str | None = None,
) -> list[str]:
    """Build the subprocess command list for *job*.

    Parameters
    ----------
    job:
        Job dict from the manifest.
    repo_root:
        Repo root directory (used to resolve tool script paths).
    python:
        Path to the Python interpreter. Defaults to ``sys.executable``.

    Returns
    -------
    list[str]
        Command ready for ``subprocess.run``.
    """
    py = python or sys.executable
    tool = job["tool"]
    script = str(repo_root / TOOL_SCRIPTS[tool])

    cmd = [py, script]

    # Optional subcommand (e.g. "sync" for chroma-sync).
    if "subcommand" in job:
        cmd.append(job["subcommand"])

    # Positional args.
    for arg in job.get("positional_args", []):
        cmd.append(str(arg))

    # Keyword args.
    for flag, value in job.get("args", {}).items():
        if isinstance(value, list):
            cmd.append(flag)
            cmd.extend(str(v) for v in value)
        elif isinstance(value, bool):
            if value:
                cmd.append(flag)
        else:
            cmd.append(flag)
            cmd.append(str(value))

    return cmd


# ---------------------------------------------------------------------------
# Job execution
# ---------------------------------------------------------------------------


def run_job(
    job: dict,
    repo_root: Path,
    *,
    run_fn=None,
    python: str | None = None,
) -> dict:
    """Execute a single job and return a result record.

    Parameters
    ----------
    job:
        Job dict from the manifest.
    repo_root:
        Repo root for resolving tool scripts.
    run_fn:
        Optional ``(cmd, **kwargs) -> CompletedProcess`` replacing
        ``subprocess.run`` for testing.
    python:
        Python interpreter path.

    Returns
    -------
    dict
        ``{"job_id": str, "result": str, "exit_code": int | None,
        "started_at": str, "finished_at": str, "error": str | None}``
    """
    runner = run_fn if run_fn is not None else subprocess.run
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    record: dict = {
        "job_id": job.get("id", "unknown"),
        "tool": job.get("tool", ""),
        "result": RESULT_FAILED,
        "exit_code": None,
        "started_at": now,
        "finished_at": None,
        "error": None,
    }

    try:
        cmd = build_command(job, repo_root, python=python)
        proc = runner(cmd, capture_output=True, text=True)
        record["exit_code"] = proc.returncode
        if proc.returncode == 0:
            record["result"] = RESULT_OK
        else:
            record["result"] = RESULT_FAILED
            record["error"] = (proc.stderr or "").strip()[:500]
    except Exception as exc:
        record["result"] = RESULT_FAILED
        record["error"] = f"{type(exc).__name__}: {exc}"

    record["finished_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    return record


def run_manifest(
    manifest: dict,
    repo_root: Path,
    *,
    job_id_filter: str | None = None,
    run_fn=None,
    python: str | None = None,
) -> list[dict]:
    """Run all enabled jobs in *manifest*.

    Parameters
    ----------
    manifest:
        Loaded manifest dict.
    repo_root:
        Repo root for resolving tool scripts.
    job_id_filter:
        If set, only run the job with this ID.
    run_fn:
        Injected subprocess runner for testing.
    python:
        Python interpreter path.

    Returns
    -------
    list[dict]
        One result record per job (including disabled/skipped).
    """
    results = []
    for job in manifest.get("jobs", []):
        job_id = job.get("id", "")

        if job_id_filter and job_id != job_id_filter:
            continue

        if not job.get("enabled", True):
            results.append({
                "job_id": job_id,
                "tool": job.get("tool", ""),
                "result": RESULT_DISABLED,
                "exit_code": None,
                "started_at": None,
                "finished_at": None,
                "error": None,
            })
            continue

        result = run_job(job, repo_root, run_fn=run_fn, python=python)
        results.append(result)

    return results


# ---------------------------------------------------------------------------
# CLI subcommands
# ---------------------------------------------------------------------------


def _cmd_run(args: argparse.Namespace, run_fn=None) -> int:
    manifest_path = Path(args.manifest) if args.manifest else DEFAULT_MANIFEST_PATH
    try:
        manifest = load_manifest(manifest_path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    repo_root = _REPO_ROOT
    results = run_manifest(
        manifest, repo_root, job_id_filter=args.job or None, run_fn=run_fn
    )

    ok = sum(1 for r in results if r["result"] == RESULT_OK)
    failed = sum(1 for r in results if r["result"] == RESULT_FAILED)
    disabled = sum(1 for r in results if r["result"] == RESULT_DISABLED)

    print(f"\nBatch run complete: {ok} ok, {failed} failed, {disabled} disabled\n")
    for r in results:
        icon = {"ok": "✓", "failed": "✗", "disabled": "-", "skipped": "~"}.get(r["result"], "?")
        print(f"  {icon} [{r['result']:8s}] {r['job_id']}")
        if r.get("error"):
            print(f"             {r['error'][:80]}")

    if args.report_out:
        import tempfile
        out_path = Path(args.report_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=out_path.parent,
            delete=False,
            suffix=".tmp",
        ) as tmp:
            tmp.write(json.dumps(results, indent=2))
            tmp_path = Path(tmp.name)
        tmp_path.replace(out_path)
        print(f"\nReport written to {out_path}")

    return 0 if failed == 0 else 1


def _cmd_validate(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest) if args.manifest else DEFAULT_MANIFEST_PATH
    try:
        manifest = load_manifest(manifest_path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    errors = validate_manifest(manifest)
    if errors:
        print(f"INVALID — {len(errors)} error(s):")
        for e in errors:
            print(f"  - {e}")
        return 1

    jobs = manifest.get("jobs", [])
    enabled = sum(1 for j in jobs if j.get("enabled", True))
    print(f"OK — {len(jobs)} jobs ({enabled} enabled)")
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest) if args.manifest else DEFAULT_MANIFEST_PATH
    try:
        manifest = load_manifest(manifest_path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    jobs = manifest.get("jobs", [])
    print(f"Manifest: {manifest_path}")
    print(f"Jobs: {len(jobs)}")
    for j in jobs:
        status = "enabled" if j.get("enabled", True) else "disabled"
        desc = j.get("description", "")
        print(f"  [{status:8s}] {j.get('id','?'):30s} {j.get('tool','?'):20s} {desc}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Alcove batch ingest runner.")
    p.add_argument("--manifest", help="Path to job manifest JSON (default: ~/.alcove/batch/jobs.json).")
    sub = p.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Run all enabled jobs.")
    run_p.add_argument("--job", help="Run only this job ID.")
    run_p.add_argument("--report-out", help="Write run report JSON to this path.")

    sub.add_parser("validate", help="Validate manifest without running.")

    sub.add_parser("status", help="Show job status summary.")

    return p


def main(argv: list[str] | None = None, *, run_fn=None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        return _cmd_run(args, run_fn=run_fn)
    if args.command == "validate":
        return _cmd_validate(args)
    if args.command == "status":
        return _cmd_status(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
