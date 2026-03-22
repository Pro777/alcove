"""Tests for tools/plugin-registry/registry.py (alcove#65)."""
from __future__ import annotations

import importlib.util
import json
import sys
from contextlib import contextmanager
from io import StringIO
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Hermetic module load
# ---------------------------------------------------------------------------
_TOOL_PATH = (
    Path(__file__).resolve().parent.parent
    / "tools" / "plugin-registry" / "registry.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("plugin_registry", _TOOL_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["plugin_registry"] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _load_module()

PluginRegistry = _mod.PluginRegistry
manifest_fingerprint = _mod.manifest_fingerprint
VALID = _mod.VALID
INVALID = _mod.INVALID
UNTRUSTED = _mod.UNTRUSTED
ALLOWED_PERMISSIONS = _mod.ALLOWED_PERMISSIONS
HIGH_TRUST_PERMISSIONS = _mod.HIGH_TRUST_PERMISSIONS
main = _mod.main


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_manifest(**overrides) -> dict:
    m = {
        "name": "test-plugin",
        "version": "1.0.0",
        "description": "A test plugin",
        "author": "Test Author",
        "entry_point": "test_plugin.main:register",
        "permissions": ["read_collection"],
    }
    m.update(overrides)
    return m


def _make_store_open_fn(store: dict):
    """Returns an open_fn backed by an in-memory dict."""

    @contextmanager
    def open_fn(path, mode="r", **kwargs):
        key = str(path)
        if mode == "r":
            if key not in store:
                raise FileNotFoundError(key)
            yield StringIO(store[key])
        elif mode == "w":
            buf = StringIO()
            yield buf
            store[key] = buf.getvalue()
        else:
            raise ValueError(f"Unexpected mode {mode!r}")

    return open_fn


_PLUGINS_DIR = str(Path("/tmp/plugins"))
_PLUGIN_KEY = str(Path("/tmp/plugins") / "test-plugin.json")
_TRUSTED_KEYS_KEY = str(Path("/tmp/plugins") / "trusted_keys.json")


def _reg(store: dict | None = None) -> PluginRegistry:
    if store is None:
        store = {}
    return PluginRegistry("/tmp/plugins", open_fn=_make_store_open_fn(store))


# ---------------------------------------------------------------------------
# manifest_fingerprint
# ---------------------------------------------------------------------------

class TestManifestFingerprint:
    def test_returns_64_char_hex(self):
        fp = manifest_fingerprint(_minimal_manifest())
        assert len(fp) == 64
        assert all(c in "0123456789abcdef" for c in fp)

    def test_excludes_signature_field(self):
        m1 = _minimal_manifest()
        m2 = dict(m1, signature="aabbcc")
        assert manifest_fingerprint(m1) == manifest_fingerprint(m2)

    def test_different_manifests_different_fingerprints(self):
        m1 = _minimal_manifest(name="plugin-a")
        m2 = _minimal_manifest(name="plugin-b")
        assert manifest_fingerprint(m1) != manifest_fingerprint(m2)

    def test_deterministic(self):
        m = _minimal_manifest()
        assert manifest_fingerprint(m) == manifest_fingerprint(m)


# ---------------------------------------------------------------------------
# PluginRegistry.validate
# ---------------------------------------------------------------------------

class TestValidate:
    def test_valid_minimal_manifest(self):
        result = _reg().validate(_minimal_manifest())
        assert result["status"] == VALID
        assert result["errors"] == []

    def test_missing_name_is_invalid(self):
        m = _minimal_manifest()
        del m["name"]
        result = _reg().validate(m)
        assert result["status"] == INVALID
        assert any("name" in e for e in result["errors"])

    def test_missing_version_is_invalid(self):
        m = _minimal_manifest()
        del m["version"]
        result = _reg().validate(m)
        assert result["status"] == INVALID

    def test_missing_entry_point_is_invalid(self):
        m = _minimal_manifest()
        del m["entry_point"]
        result = _reg().validate(m)
        assert result["status"] == INVALID

    def test_missing_permissions_is_invalid(self):
        m = _minimal_manifest()
        del m["permissions"]
        result = _reg().validate(m)
        assert result["status"] == INVALID

    def test_unknown_permission_is_invalid(self):
        m = _minimal_manifest(permissions=["read_collection", "nuke_database"])
        result = _reg().validate(m)
        assert result["status"] == INVALID
        assert any("nuke_database" in e for e in result["errors"])

    def test_network_permission_warns(self):
        m = _minimal_manifest(permissions=["read_collection", "network"])
        result = _reg().validate(m)
        assert result["status"] == VALID
        assert any("network" in w for w in result["warnings"])
        assert "network" in result["high_trust_permissions"]

    def test_filesystem_permission_warns(self):
        m = _minimal_manifest(permissions=["filesystem"])
        result = _reg().validate(m)
        assert "filesystem" in result["high_trust_permissions"]

    def test_all_allowed_permissions_are_valid(self):
        for perm in ALLOWED_PERMISSIONS:
            m = _minimal_manifest(permissions=[perm])
            result = _reg().validate(m)
            assert result["status"] in (VALID, UNTRUSTED), f"failed for {perm}"

    def test_fingerprint_present(self):
        result = _reg().validate(_minimal_manifest())
        assert len(result["fingerprint"]) == 64

    def test_no_pubkey_stays_valid(self):
        m = _minimal_manifest()
        result = _reg().validate(m)
        assert result["status"] == VALID

    def test_pubkey_without_trust_is_untrusted(self):
        m = _minimal_manifest(public_key_pem="-----BEGIN PUBLIC KEY-----\nfake\n-----END PUBLIC KEY-----")
        result = _reg().validate(m)
        assert result["status"] == UNTRUSTED

    def test_permissions_not_list_is_invalid(self):
        m = _minimal_manifest(permissions="read_collection")
        result = _reg().validate(m)
        assert result["status"] == INVALID


# ---------------------------------------------------------------------------
# PluginRegistry.add
# ---------------------------------------------------------------------------

class TestAdd:
    def test_add_valid_manifest(self):
        store: dict = {}
        reg = _reg(store)
        result = reg.add(_minimal_manifest())
        assert result["status"] == VALID
        assert _PLUGIN_KEY in store

    def test_add_writes_valid_json(self):
        store: dict = {}
        reg = _reg(store)
        reg.add(_minimal_manifest())
        stored = json.loads(store[_PLUGIN_KEY])
        assert stored["name"] == "test-plugin"

    def test_add_invalid_manifest_raises(self):
        m = _minimal_manifest()
        del m["name"]
        with pytest.raises(ValueError, match="Cannot register invalid plugin"):
            _reg().add(m)

    def test_add_returns_validation_result(self):
        store: dict = {}
        result = _reg(store).add(_minimal_manifest())
        assert "status" in result
        assert "fingerprint" in result


# ---------------------------------------------------------------------------
# PluginRegistry.trust_key
# ---------------------------------------------------------------------------

class TestTrustKey:
    def test_trust_key_returns_fingerprint(self):
        store: dict = {}
        reg = _reg(store)
        fp = reg.trust_key("-----BEGIN PUBLIC KEY-----\nfake\n-----END PUBLIC KEY-----", label="test")
        assert len(fp) == 64

    def test_trusted_key_stored(self):
        store: dict = {}
        reg = _reg(store)
        pem = "-----BEGIN PUBLIC KEY-----\nfake\n-----END PUBLIC KEY-----"
        fp = reg.trust_key(pem, label="dev")
        # Reload from store
        trusted = json.loads(store[_TRUSTED_KEYS_KEY])
        assert fp in trusted
        assert trusted[fp]["label"] == "dev"

    def test_manifest_with_trusted_key_is_valid(self):
        store: dict = {}
        reg = _reg(store)
        pem = "-----BEGIN PUBLIC KEY-----\nfake\n-----END PUBLIC KEY-----"
        reg.trust_key(pem, label="dev")
        m = _minimal_manifest(public_key_pem=pem)
        result = reg.validate(m)
        # Status is valid or untrusted depending on sig presence — key IS trusted now
        assert result["status"] != INVALID
        # No "not in trusted keyring" warning
        assert not any("not in trusted keyring" in w for w in result["warnings"])

    def test_multiple_keys_can_be_trusted(self):
        store: dict = {}
        reg = _reg(store)
        fp1 = reg.trust_key("key1", label="dev1")
        fp2 = reg.trust_key("key2", label="dev2")
        trusted = json.loads(store[_TRUSTED_KEYS_KEY])
        assert fp1 in trusted
        assert fp2 in trusted


# ---------------------------------------------------------------------------
# PluginRegistry.get
# ---------------------------------------------------------------------------

class TestGet:
    def test_get_returns_manifest(self):
        store: dict = {}
        reg = _reg(store)
        m = _minimal_manifest()
        reg.add(m)
        retrieved = reg.get("test-plugin")
        assert retrieved is not None
        assert retrieved["name"] == "test-plugin"

    def test_get_missing_returns_none(self):
        result = _reg().get("nonexistent")
        assert result is None


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_permissions_list_valid(self):
        m = _minimal_manifest(permissions=[])
        result = _reg().validate(m)
        assert result["status"] == VALID

    def test_multiple_permissions_all_allowed(self):
        m = _minimal_manifest(permissions=["read_collection", "write_collection", "audio"])
        result = _reg().validate(m)
        assert result["status"] == VALID

    def test_high_trust_permissions_listed(self):
        m = _minimal_manifest(permissions=["network", "filesystem"])
        result = _reg().validate(m)
        assert set(result["high_trust_permissions"]) == {"network", "filesystem"}

    def test_description_optional(self):
        m = _minimal_manifest()
        del m["description"]
        result = _reg().validate(m)
        assert result["status"] == VALID

    def test_author_optional(self):
        m = _minimal_manifest()
        del m["author"]
        result = _reg().validate(m)
        assert result["status"] == VALID


# ---------------------------------------------------------------------------
# depends_on validation (#529)
# ---------------------------------------------------------------------------

class TestDependsOnValidation:
    def test_depends_on_optional(self):
        m = _minimal_manifest()
        result = _reg().validate(m)
        assert result["status"] == VALID

    def test_depends_on_empty_list_valid(self):
        m = _minimal_manifest(depends_on=[])
        result = _reg().validate(m)
        assert result["status"] == VALID

    def test_depends_on_list_of_strings_valid(self):
        m = _minimal_manifest(depends_on=["alcove-search", "alcove-auth"])
        result = _reg().validate(m)
        assert result["status"] == VALID

    def test_depends_on_not_a_list_is_invalid(self):
        m = _minimal_manifest(depends_on="alcove-search")
        result = _reg().validate(m)
        assert result["status"] == INVALID
        assert any("depends_on" in e for e in result["errors"])

    def test_depends_on_with_empty_string_entry_is_invalid(self):
        m = _minimal_manifest(depends_on=[""])
        result = _reg().validate(m)
        assert result["status"] == INVALID

    def test_depends_on_with_non_string_entry_is_invalid(self):
        m = _minimal_manifest(depends_on=[42])
        result = _reg().validate(m)
        assert result["status"] == INVALID


# ---------------------------------------------------------------------------
# resolve_order — topological sort + circular dependency detection (#529)
# ---------------------------------------------------------------------------

class TestResolveOrder:
    def _make(self, name: str, depends_on: list[str] | None = None) -> dict:
        return _minimal_manifest(name=name, depends_on=depends_on or [])

    def test_single_plugin_no_deps(self):
        m = self._make("alpha")
        result = _reg().resolve_order([m])
        assert [p["name"] for p in result] == ["alpha"]

    def test_independent_plugins_sorted_alphabetically(self):
        a = self._make("bravo")
        b = self._make("alpha")
        result = _reg().resolve_order([a, b])
        assert [p["name"] for p in result] == ["alpha", "bravo"]

    def test_linear_chain_resolved_in_order(self):
        # charlie depends on bravo, bravo depends on alpha
        alpha = self._make("alpha")
        bravo = self._make("bravo", depends_on=["alpha"])
        charlie = self._make("charlie", depends_on=["bravo"])
        result = _reg().resolve_order([charlie, bravo, alpha])
        names = [p["name"] for p in result]
        assert names.index("alpha") < names.index("bravo")
        assert names.index("bravo") < names.index("charlie")

    def test_diamond_dependency_resolved(self):
        # delta depends on bravo and charlie; both depend on alpha
        alpha = self._make("alpha")
        bravo = self._make("bravo", depends_on=["alpha"])
        charlie = self._make("charlie", depends_on=["alpha"])
        delta = self._make("delta", depends_on=["bravo", "charlie"])
        result = _reg().resolve_order([delta, charlie, bravo, alpha])
        names = [p["name"] for p in result]
        assert names.index("alpha") < names.index("bravo")
        assert names.index("alpha") < names.index("charlie")
        assert names.index("bravo") < names.index("delta")
        assert names.index("charlie") < names.index("delta")

    def test_missing_dependency_raises(self):
        import pytest
        bravo = self._make("bravo", depends_on=["alpha"])
        with pytest.raises(ValueError, match="alpha"):
            _reg().resolve_order([bravo])

    def test_direct_circular_dependency_raises(self):
        import pytest
        alpha = self._make("alpha", depends_on=["bravo"])
        bravo = self._make("bravo", depends_on=["alpha"])
        with pytest.raises(ValueError, match="[Cc]ircular"):
            _reg().resolve_order([alpha, bravo])

    def test_indirect_circular_dependency_raises(self):
        import pytest
        alpha = self._make("alpha", depends_on=["charlie"])
        bravo = self._make("bravo", depends_on=["alpha"])
        charlie = self._make("charlie", depends_on=["bravo"])
        with pytest.raises(ValueError, match="[Cc]ircular"):
            _reg().resolve_order([alpha, bravo, charlie])

    def test_no_depends_on_field_treated_as_no_deps(self):
        m = _minimal_manifest(name="solo")  # no depends_on key at all
        result = _reg().resolve_order([m])
        assert result[0]["name"] == "solo"
