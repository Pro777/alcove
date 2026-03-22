#!/usr/bin/env python3
"""Structured audit logging for Alcove deployments.

Writes append-only NDJSON audit records to a configurable path.
Each record contains: timestamp, event type, actor, resource, outcome, and
optional detail fields. Suitable for HIPAA-adjacent, compliance, and
institutional deployments where query and ingest activity must be logged.

Usage::

    from tools.audit_log.audit_log import AuditLogger

    log = AuditLogger("/var/log/alcove/audit.ndjson")
    log.query("user@example.com", query="medieval manuscripts", results=12)
    log.ingest("admin@example.com", collection="latin_texts", chunk_count=847)

CLI usage::

    python tools/audit-log/audit_log.py --log-path /tmp/audit.ndjson query \\
        --actor user@example.com --query "test search"
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, TextIO


# ---------------------------------------------------------------------------
# Core logger
# ---------------------------------------------------------------------------


class AuditLogger:
    """Append-only NDJSON audit logger.

    Thread safety: each ``log()`` call opens, writes, and flushes the file
    atomically via a single ``write()`` syscall on POSIX systems. Suitable for
    single-process deployments. For multi-process use, point each process at a
    separate shard path and merge off-line.
    """

    def __init__(
        self,
        log_path: str | Path | None = None,
        *,
        stream: Optional[TextIO] = None,
    ) -> None:
        """
        Args:
            log_path: Path to the NDJSON audit log file. When ``None``, records
                are written to *stream* only (useful for testing and stdout mode).
            stream: Optional text stream to mirror every record to (e.g.
                ``sys.stdout``). When ``log_path`` is ``None``, ``stream``
                defaults to ``sys.stdout``.
        """
        self.log_path: Path | None = Path(log_path) if log_path else None
        self._stream: Optional[TextIO] = stream if stream is not None else (sys.stdout if log_path is None else None)

    # ------------------------------------------------------------------
    # High-level event methods
    # ------------------------------------------------------------------

    def query(
        self,
        actor: str,
        *,
        query: str,
        collection: str | None = None,
        results: int | None = None,
        outcome: str = "ok",
        **extra: Any,
    ) -> dict[str, Any]:
        """Log a search query event."""
        detail: dict[str, Any] = {"query": query}
        if collection is not None:
            detail["collection"] = collection
        if results is not None:
            detail["results"] = results
        detail.update(extra)
        return self.log("query", actor=actor, outcome=outcome, detail=detail)

    def ingest(
        self,
        actor: str,
        *,
        collection: str,
        chunk_count: int | None = None,
        source: str | None = None,
        outcome: str = "ok",
        **extra: Any,
    ) -> dict[str, Any]:
        """Log a corpus ingest event."""
        detail: dict[str, Any] = {"collection": collection}
        if chunk_count is not None:
            detail["chunk_count"] = chunk_count
        if source is not None:
            detail["source"] = source
        detail.update(extra)
        return self.log("ingest", actor=actor, outcome=outcome, detail=detail)

    def access(
        self,
        actor: str,
        *,
        resource: str,
        method: str = "GET",
        status: int = 200,
        **extra: Any,
    ) -> dict[str, Any]:
        """Log an HTTP access event."""
        outcome = "ok" if status < 400 else "error"
        detail: dict[str, Any] = {"resource": resource, "method": method, "status": status}
        detail.update(extra)
        return self.log("access", actor=actor, outcome=outcome, detail=detail)

    def admin(
        self,
        actor: str,
        *,
        action: str,
        target: str | None = None,
        outcome: str = "ok",
        **extra: Any,
    ) -> dict[str, Any]:
        """Log an administrative action (collection reset, config change, etc.)."""
        detail: dict[str, Any] = {"action": action}
        if target is not None:
            detail["target"] = target
        detail.update(extra)
        return self.log("admin", actor=actor, outcome=outcome, detail=detail)

    # ------------------------------------------------------------------
    # Low-level log method
    # ------------------------------------------------------------------

    def log(
        self,
        event_type: str,
        *,
        actor: str,
        outcome: str = "ok",
        detail: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Write a single audit record.

        Args:
            event_type: Short string categorising the event (e.g. ``"query"``,
                ``"ingest"``, ``"access"``).
            actor: Identity string for the initiating party (IP address, user
                ID, service account name, etc.).
            outcome: Result of the event — ``"ok"``, ``"error"``, or a
                domain-specific value.
            detail: Additional fields specific to the event type.

        Returns:
            The serialised record dict (useful for testing).
        """
        record: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "event": event_type,
            "actor": actor,
            "outcome": outcome,
        }
        if detail:
            record["detail"] = detail

        line = json.dumps(record, separators=(",", ":")) + "\n"

        if self.log_path is not None:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            # Open with O_CREAT | O_APPEND; chmod 0o600 on first create so the
            # log is owner-readable only (compliance-oriented deployments).
            fd = os.open(
                self.log_path,
                os.O_WRONLY | os.O_CREAT | os.O_APPEND,
                0o600,
            )
            with os.fdopen(fd, "a", encoding="utf-8") as fh:
                fh.write(line)

        if self._stream is not None:
            self._stream.write(line)
            self._stream.flush()

        return record


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Write a structured audit record to an NDJSON log.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--log-path",
        default=os.environ.get("ALCOVE_AUDIT_LOG", "audit.ndjson"),
        help="Path to the audit log file (env: ALCOVE_AUDIT_LOG; default: audit.ndjson)",
    )
    parser.add_argument(
        "--actor",
        default=os.environ.get("ALCOVE_AUDIT_ACTOR", "cli"),
        help="Actor identity (default: cli)",
    )
    parser.add_argument("--stdout", action="store_true", help="Mirror records to stdout")

    sub = parser.add_subparsers(dest="command", required=True)

    q = sub.add_parser("query", help="Log a search query event")
    q.add_argument("--query", required=True, help="Query string")
    q.add_argument("--collection", default=None)
    q.add_argument("--results", type=int, default=None)

    ing = sub.add_parser("ingest", help="Log a corpus ingest event")
    ing.add_argument("--collection", required=True)
    ing.add_argument("--chunk-count", type=int, default=None)
    ing.add_argument("--source", default=None)

    acc = sub.add_parser("access", help="Log an HTTP access event")
    acc.add_argument("--resource", required=True)
    acc.add_argument("--method", default="GET")
    acc.add_argument("--status", type=int, default=200)

    adm = sub.add_parser("admin", help="Log an administrative action")
    adm.add_argument("--action", required=True)
    adm.add_argument("--target", default=None)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    stream = sys.stdout if args.stdout else None
    logger = AuditLogger(args.log_path, stream=stream)

    try:
        if args.command == "query":
            logger.query(
                args.actor,
                query=args.query,
                collection=args.collection,
                results=args.results,
            )
        elif args.command == "ingest":
            logger.ingest(
                args.actor,
                collection=args.collection,
                chunk_count=args.chunk_count,
                source=args.source,
            )
        elif args.command == "access":
            logger.access(
                args.actor,
                resource=args.resource,
                method=args.method,
                status=args.status,
            )
        elif args.command == "admin":
            logger.admin(args.actor, action=args.action, target=args.target)
    except KeyboardInterrupt:
        raise
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
