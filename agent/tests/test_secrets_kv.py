"""Tests for the KVBackend secrets implementation."""

import json

import pytest

from secrets import KVBackend


class TestKVBackend:
    def test_get_returns_value_from_initial_dict(self):
        backend = KVBackend({"GITHUB_TOKEN": "ghp_test", "ANTHROPIC_API_KEY": "sk-ant"})
        assert backend.get("GITHUB_TOKEN") == "ghp_test"
        assert backend.get("ANTHROPIC_API_KEY") == "sk-ant"

    def test_get_returns_none_for_missing_key(self):
        backend = KVBackend({"OTHER": "value"})
        assert backend.get("MISSING") is None

    def test_get_returns_none_for_empty_string_value(self):
        backend = KVBackend({"EMPTY": ""})
        assert backend.get("EMPTY") is None

    def test_set_stores_and_retrieves_value(self):
        backend = KVBackend()
        backend.set("NEW_KEY", "new-value")
        assert backend.get("NEW_KEY") == "new-value"

    def test_set_overwrites_existing_key(self):
        backend = KVBackend({"KEY": "old"})
        backend.set("KEY", "new")
        assert backend.get("KEY") == "new"

    def test_delete_removes_key(self):
        backend = KVBackend({"KEY": "value"})
        backend.delete("KEY")
        assert backend.get("KEY") is None

    def test_delete_is_noop_for_missing_key(self):
        backend = KVBackend()
        backend.delete("NON_EXISTENT")  # must not raise

    def test_require_returns_value_when_present(self):
        backend = KVBackend({"API_KEY": "secret"})
        assert backend.require("API_KEY") == "secret"

    def test_require_raises_key_error_when_missing(self):
        backend = KVBackend()
        with pytest.raises(KeyError, match="API_KEY"):
            backend.require("API_KEY")

    def test_load_from_json_file(self, tmp_path):
        secrets_file = tmp_path / "secrets.json"
        secrets_file.write_text(json.dumps({"FILE_KEY": "file-value"}))
        backend = KVBackend(file=secrets_file)
        assert backend.get("FILE_KEY") == "file-value"

    def test_json_file_merges_with_initial_dict(self, tmp_path):
        secrets_file = tmp_path / "secrets.json"
        secrets_file.write_text(json.dumps({"FILE_KEY": "from-file"}))
        backend = KVBackend({"DICT_KEY": "from-dict"}, file=secrets_file)
        assert backend.get("DICT_KEY") == "from-dict"
        assert backend.get("FILE_KEY") == "from-file"

    def test_missing_json_file_is_not_fatal(self, tmp_path):
        """A non-existent KV file should not raise at construction time."""
        backend = KVBackend(file=tmp_path / "does_not_exist.json")
        assert backend.get("ANY_KEY") is None

    def test_json_file_from_env_var(self, tmp_path, monkeypatch):
        secrets_file = tmp_path / "env_secrets.json"
        secrets_file.write_text(json.dumps({"ENV_FILE_KEY": "env-value"}))
        monkeypatch.setenv("SECRETS_KV_FILE", str(secrets_file))
        backend = KVBackend()
        assert backend.get("ENV_FILE_KEY") == "env-value"

    def test_invalid_json_file_raises(self, tmp_path):
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("[1, 2, 3]")  # array, not object
        with pytest.raises(ValueError, match="JSON object"):
            KVBackend(file=bad_file)

    def test_secret_value_not_in_key_error_message(self):
        """Key errors should name the key, not reveal any value."""
        backend = KVBackend()
        try:
            backend.require("MY_SECRET")
        except KeyError as exc:
            assert "MY_SECRET" in str(exc)
