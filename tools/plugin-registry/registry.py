"""Alcove plugin registry — discovery, validation, and trust model (alcove#65).

Implements the foundational layer of the alcove plugin ecosystem.  Operators
install plugins by dropping a manifest file into ``~/.alcove/plugins/``; the
registry validates, fingerprints, and enforces a permission allowlist before
any plugin code is loaded.

Plugin manifest format
-----------------------
Each manifest is a JSON file::

    {
        "name": "my-plugin",
        "version": "1.0.0",
        "description": "Does something useful",
        "author": "Jane Dev <jane@example.com>",
        "entry_point": "my_plugin.main:register",
        "permissions": ["read_collection", "write_collection"],
        "depends_on": ["alcove-search", "alcove-auth"],
        "public_key_pem": "-----BEGIN PUBLIC KEY-----\\n...\\n-----END PUBLIC KEY-----",
        "signature": "<hex-encoded Ed25519 signature of canonical manifest JSON>"
    }

``depends_on`` is optional.  When present it must be a list of plugin name
strings.  ``PluginRegistry.resolve_order()`` performs a topological sort and
raises ``ValueError`` on circular or missing dependencies.

Permission model
-----------------
Plugins declare the permissions they need.  The registry enforces an
allowlist of recognised permissions:

- ``read_collection``  — read index data
- ``write_collection`` — add/delete documents
- ``read_config``      — access non-secret config keys
- ``network``          — make outbound HTTP requests (high-trust)
- ``filesystem``       — read/write local files (high-trust)
- ``audio``            — access audio capture devices
- ``display``          — render UI overlays

High-trust permissions (``network``, ``filesystem``) trigger an explicit
warning in ``validate()`` output.

Trust model
-----------
Plugins are signed with Ed25519.  The canonical JSON used for signing
is the manifest body *excluding* the ``signature`` field, serialised as
``json.dumps(body, sort_keys=True, separators=(',',':'))``.

The registry stores trusted public keys in
``~/.alcove/plugins/trusted_keys.json``.  A plugin whose public key is
not in the trusted keyring is ``UNTRUSTED`` even if the signature is
mathematically valid.

CLI usage
---------

List registered plugins::

    python tools/plugin-registry/registry.py list --plugins ~/.alcove/plugins

Validate a manifest::

    python tools/plugin-registry/registry.py validate --manifest path/to/plugin.json

Add a manifest to the registry (copies it into the plugins dir)::

    python tools/plugin-registry/registry.py add --manifest path/to/plugin.json \\
        --plugins ~/.alcove/plugins

Remove a plugin::

    python tools/plugin-registry/registry.py remove --name my-plugin \\
        --plugins ~/.alcove/plugins

Trust a public key::

    python tools/plugin-registry/registry.py trust \\
        --pubkey path/to/pubkey.pem --label "Jane Dev" \\
        --plugins ~/.alcove/plugins
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Callable

# ---------------------------------------------------------------------------
# Repo root on sys.path
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MANIFEST_VERSION = 1

ALLOWED_PERMISSIONS: set[str] = {
    "read_collection",
    "write_collection",
    "read_config",
    "network",
    "filesystem",
    "audio",
    "display",
}

HIGH_TRUST_PERMISSIONS: set[str] = {"network", "filesystem"}

TRUSTED_KEYS_FILENAME = "trusted_keys.json"

# Validation result codes
VALID = "valid"
INVALID = "invalid"
UNTRUSTED = "untrusted"

# Whitelist regex for plugin names used in path construction.
# Only [a-zA-Z0-9_-] are permitted — no path separators, no dots, no spaces.
_PLUGIN_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")

# ---------------------------------------------------------------------------
# Manifest helpers
# ---------------------------------------------------------------------------


def _canonical_signable(manifest: dict) -> bytes:
    """Return the canonical bytes used for signing/verification.

    This is the manifest body with the ``signature`` key removed,
    serialised with sorted keys and no whitespace.
    """
    body = {k: v for k, v in manifest.items() if k != "signature"}
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")


def manifest_fingerprint(manifest: dict) -> str:
    """Return a SHA-256 hex fingerprint of the signable manifest body."""
    return hashlib.sha256(_canonical_signable(manifest)).hexdigest()


# ---------------------------------------------------------------------------
# Signature verification (Ed25519 via cryptography package)
# ---------------------------------------------------------------------------


def _verify_signature(manifest: dict) -> tuple[bool, str]:
    """Verify the Ed25519 signature in the manifest.

    Returns ``(ok, reason)``.  Requires ``cryptography`` package.
    """
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from cryptography.hazmat.primitives.serialization import load_pem_public_key
        from cryptography.exceptions import InvalidSignature
    except ImportError:
        return False, "cryptography package not installed"

    sig_hex = manifest.get("signature", "")
    pubkey_pem = manifest.get("public_key_pem", "")
    if not sig_hex:
        return False, "manifest has no signature field"
    if not pubkey_pem:
        return False, "manifest has no public_key_pem field"

    try:
        sig_bytes = bytes.fromhex(sig_hex)
    except ValueError:
        return False, "signature is not valid hex"

    try:
        pubkey = load_pem_public_key(pubkey_pem.encode("utf-8"))
    except Exception as exc:
        return False, f"could not parse public_key_pem: {exc}"

    if not isinstance(pubkey, Ed25519PublicKey):
        return False, "public key is not an Ed25519 key"

    try:
        pubkey.verify(sig_bytes, _canonical_signable(manifest))
        return True, "signature valid"
    except InvalidSignature:
        return False, "signature does not match manifest body"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class PluginRegistry:
    """Alcove plugin registry.

    Parameters
    ----------
    plugins_dir:
        Directory where plugin manifests (``*.json``) are stored.
    open_fn:
        Injectable file opener for testing.
    """

    def __init__(
        self,
        plugins_dir: str | Path,
        *,
        open_fn: Callable | None = None,
    ) -> None:
        self._plugins_dir = Path(plugins_dir)
        self._open_fn = open_fn

    # ------------------------------------------------------------------
    # Internal I/O helpers
    # ------------------------------------------------------------------

    def _read_json(self, path: Path) -> dict:
        if self._open_fn is not None:
            with self._open_fn(path, "r") as fh:
                return json.load(fh)
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)

    def _write_json(self, path: Path, data: dict) -> None:
        if self._open_fn is not None:
            with self._open_fn(path, "w") as fh:
                json.dump(data, fh, indent=2)
                fh.write("\n")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
                fh.write("\n")

    def _trusted_keys_path(self) -> Path:
        return self._plugins_dir / TRUSTED_KEYS_FILENAME

    def _load_trusted_keys(self) -> dict:
        path = self._trusted_keys_path()
        try:
            return self._read_json(path)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _validate_plugin_name(self, name: str) -> None:
        """Raise ValueError if *name* is unsafe for use in a filesystem path.

        Enforces a strict whitelist (``[a-zA-Z0-9_-]`` only) and then
        resolves the candidate path to assert it stays inside
        ``self._plugins_dir``.
        """
        if not name:
            raise ValueError("Plugin name must not be empty")
        if not _PLUGIN_NAME_RE.match(name):
            raise ValueError(
                f"Plugin name {name!r} contains invalid characters; "
                "only [a-zA-Z0-9_-] are allowed"
            )
        # Belt-and-suspenders: resolve and assert confinement.
        # Only applicable when _plugins_dir exists on the real filesystem.
        plugins_dir_resolved = self._plugins_dir.resolve()
        candidate = (self._plugins_dir / f"{name}.json").resolve()
        if not str(candidate).startswith(str(plugins_dir_resolved)):
            raise ValueError(
                f"Plugin name {name!r} would escape the plugins directory"
            )

    def _manifest_path(self, name: str) -> Path:
        self._validate_plugin_name(name)
        return self._plugins_dir / f"{name}.json"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate(self, manifest: dict) -> dict:
        """Validate a plugin manifest.

        Returns a result dict::

            {
                "status": "valid" | "invalid" | "untrusted",
                "errors": [...],
                "warnings": [...],
                "fingerprint": "<sha256 hex>",
                "high_trust_permissions": [...],
            }
        """
        errors: list[str] = []
        warnings: list[str] = []

        # Required fields
        for field in ("name", "version", "entry_point"):
            if not manifest.get(field):
                errors.append(f"missing required field: {field!r}")
        if "permissions" not in manifest:
            errors.append("missing required field: 'permissions'")

        # Permissions allowlist
        perms = manifest.get("permissions", [])
        if not isinstance(perms, list):
            errors.append("'permissions' must be a list")
            perms = []
        # Filter to string-only items before set operations to prevent
        # TypeError from non-hashable entries (e.g. lists, dicts).
        valid_perms = [p for p in perms if isinstance(p, str)]
        unknown = sorted(set(valid_perms) - ALLOWED_PERMISSIONS)
        if unknown:
            errors.append(f"unrecognised permissions: {unknown}")

        high_trust = sorted(set(valid_perms) & HIGH_TRUST_PERMISSIONS)
        for p in high_trust:
            warnings.append(f"high-trust permission declared: {p!r}")

        # depends_on — optional, must be a list of non-empty strings if present
        deps = manifest.get("depends_on")
        if deps is not None:
            if not isinstance(deps, list):
                errors.append("'depends_on' must be a list of plugin name strings")
            else:
                bad = [d for d in deps if not isinstance(d, str) or not d.strip()]
                if bad:
                    errors.append(f"'depends_on' entries must be non-empty strings, got: {bad}")

        fingerprint = manifest_fingerprint(manifest)

        # Signature / public key consistency check:
        # public_key_pem without signature is always INVALID — the key
        # serves no purpose without a corresponding signature to verify.
        if manifest.get("public_key_pem") and not manifest.get("signature"):
            errors.append("signature missing for provided public_key_pem")

        # Signature check (only when a signature field is present)
        sig_ok, sig_reason = _verify_signature(manifest)
        if not sig_ok and manifest.get("signature"):
            errors.append(f"signature invalid: {sig_reason}")

        # Trust check (only if no errors so far and public key is present)
        status = VALID
        if errors:
            status = INVALID
        elif manifest.get("public_key_pem"):
            trusted = self._load_trusted_keys()
            pubkey_pem = manifest["public_key_pem"].strip()
            key_fp = hashlib.sha256(pubkey_pem.encode("utf-8")).hexdigest()
            if key_fp not in trusted:
                warnings.append("plugin public key not in trusted keyring")
                status = UNTRUSTED

        return {
            "status": status,
            "errors": errors,
            "warnings": warnings,
            "fingerprint": fingerprint,
            "high_trust_permissions": high_trust,
        }

    def add(self, manifest: dict) -> dict:
        """Add a plugin manifest to the registry.

        Returns the validation result.  Raises ``ValueError`` if the manifest
        is invalid (status == ``invalid``).
        """
        result = self.validate(manifest)
        if result["status"] == INVALID:
            raise ValueError(
                f"Cannot register invalid plugin: {result['errors']}"
            )
        name = manifest["name"]
        self._write_json(self._manifest_path(name), manifest)
        return result

    def remove(self, name: str) -> bool:
        """Remove a plugin by name. Returns True if it existed."""
        path = self._manifest_path(name)
        if self._open_fn is not None:
            # Delegate to caller's store — can't truly delete; mark absent
            raise NotImplementedError("remove() not supported with open_fn")
        if path.exists():
            path.unlink()
            return True
        return False

    def list(self) -> list[dict]:
        """Return a list of installed plugin summary dicts."""
        plugins: list[dict] = []
        if self._open_fn is not None:
            raise NotImplementedError("list() not supported with open_fn")
        if not self._plugins_dir.exists():
            return []
        for path in sorted(self._plugins_dir.glob("*.json")):
            if path.name == TRUSTED_KEYS_FILENAME:
                continue
            try:
                m = self._read_json(path)
                plugins.append({
                    "name": m.get("name", path.stem),
                    "version": m.get("version", ""),
                    "description": m.get("description", ""),
                    "permissions": m.get("permissions", []),
                    "fingerprint": manifest_fingerprint(m),
                })
            except (json.JSONDecodeError, OSError):
                continue
        return plugins

    def trust_key(self, pubkey_pem: str, label: str = "") -> str:
        """Add a public key to the trusted keyring.

        Returns the key fingerprint (SHA-256 hex of the PEM string).
        """
        trusted = self._load_trusted_keys()
        key_fp = hashlib.sha256(pubkey_pem.strip().encode("utf-8")).hexdigest()
        trusted[key_fp] = {"label": label, "pem": pubkey_pem.strip()}
        self._write_json(self._trusted_keys_path(), trusted)
        return key_fp

    def get(self, name: str) -> dict | None:
        """Return a manifest by plugin name, or None."""
        path = self._manifest_path(name)
        try:
            return self._read_json(path)
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def resolve_order(self, manifests: list[dict]) -> list[dict]:
        """Return *manifests* in dependency-safe activation order (#529).

        Performs a topological sort of the given manifests using each
        manifest's ``depends_on`` field.  All declared dependencies must
        be present in *manifests*.

        Raises
        ------
        ValueError
            If a dependency is missing from *manifests*, if duplicate plugin
            names are detected, or if circular dependencies are present.
        """
        # Detect duplicate plugin names before building the lookup dict.
        seen_names: set[str] = set()
        for m in manifests:
            name = m["name"]
            if name in seen_names:
                raise ValueError(f"Duplicate plugin name: {name!r}")
            seen_names.add(name)

        by_name: dict[str, dict] = {m["name"]: m for m in manifests}

        # Verify all depends_on names are present
        for m in manifests:
            for dep in m.get("depends_on") or []:
                if dep not in by_name:
                    raise ValueError(
                        f"Plugin {m['name']!r} depends on {dep!r} which is not in the provided manifest set"
                    )

        # Kahn's algorithm for topological sort
        in_degree: dict[str, int] = {name: 0 for name in by_name}
        dependents: dict[str, list[str]] = {name: [] for name in by_name}
        for m in manifests:
            for dep in m.get("depends_on") or []:
                in_degree[m["name"]] += 1
                dependents[dep].append(m["name"])

        queue = [name for name, deg in in_degree.items() if deg == 0]
        queue.sort()  # deterministic order for independent nodes
        ordered: list[dict] = []

        while queue:
            name = queue.pop(0)
            ordered.append(by_name[name])
            for dependent in sorted(dependents[name]):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        if len(ordered) != len(manifests):
            cycle_members = [n for n, d in in_degree.items() if d > 0]
            raise ValueError(
                f"Circular dependency detected among plugins: {sorted(cycle_members)}"
            )

        return ordered


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------


def _load_manifest_file(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _cmd_list(args: argparse.Namespace) -> int:
    reg = PluginRegistry(args.plugins)
    plugins = reg.list()
    if not plugins:
        print("No plugins installed.", file=sys.stderr)
        return 0
    for p in plugins:
        print(f"{p['name']} v{p['version']}  [{', '.join(p['permissions'])}]")
        if p["description"]:
            print(f"  {p['description']}")
    print(f"\n{len(plugins)} plugin(s) installed.", file=sys.stderr)
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    reg = PluginRegistry(args.plugins)
    manifest = _load_manifest_file(args.manifest)
    result = reg.validate(manifest)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] != INVALID else 1


def _cmd_add(args: argparse.Namespace) -> int:
    reg = PluginRegistry(args.plugins)
    manifest = _load_manifest_file(args.manifest)
    try:
        result = reg.add(manifest)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Registered {manifest['name']} ({result['status']})")
    for w in result["warnings"]:
        print(f"  WARNING: {w}")
    return 0


def _cmd_remove(args: argparse.Namespace) -> int:
    reg = PluginRegistry(args.plugins)
    found = reg.remove(args.name)
    if found:
        print(f"Removed plugin {args.name!r}")
    else:
        print(f"Plugin {args.name!r} not found", file=sys.stderr)
    return 0 if found else 1


def _cmd_trust(args: argparse.Namespace) -> int:
    reg = PluginRegistry(args.plugins)
    with open(args.pubkey, "r", encoding="utf-8") as fh:
        pem = fh.read()
    fp = reg.trust_key(pem, label=args.label or "")
    print(f"Trusted key fingerprint: {fp}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Alcove plugin registry.")
    p.add_argument(
        "--plugins",
        default=str(Path.home() / ".alcove" / "plugins"),
        help="Plugin directory (default: ~/.alcove/plugins).",
    )
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List installed plugins.")

    val_p = sub.add_parser("validate", help="Validate a plugin manifest.")
    val_p.add_argument("--manifest", required=True, help="Path to manifest JSON.")

    add_p = sub.add_parser("add", help="Add a plugin to the registry.")
    add_p.add_argument("--manifest", required=True, help="Path to manifest JSON.")

    rm_p = sub.add_parser("remove", help="Remove a plugin.")
    rm_p.add_argument("--name", required=True, help="Plugin name.")

    trust_p = sub.add_parser("trust", help="Trust a public key.")
    trust_p.add_argument("--pubkey", required=True, help="Path to PEM public key file.")
    trust_p.add_argument("--label", default="", help="Human-readable label.")

    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "list":
        return _cmd_list(args)
    if args.command == "validate":
        return _cmd_validate(args)
    if args.command == "add":
        return _cmd_add(args)
    if args.command == "remove":
        return _cmd_remove(args)
    if args.command == "trust":
        return _cmd_trust(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
