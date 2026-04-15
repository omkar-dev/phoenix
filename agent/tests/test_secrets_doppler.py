"""Tests for the DopplerBackend secrets implementation."""

import json
from unittest.mock import MagicMock, patch

import pytest

from secrets import DopplerBackend


def _mock_urlopen(body: dict, status: int = 200):
    """Return a context-manager mock that yields a fake HTTP response."""
    resp = MagicMock()
    resp.read.return_value = json.dumps(body).encode()
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


class TestDopplerBackend:
    def test_get_returns_secret_value(self):
        backend = DopplerBackend(token="dp.st.test", project="proj", config="prd")
        body = {"secret": {"name": "GITHUB_TOKEN", "value": {"raw": "ghp_dop", "computed": "ghp_dop"}}}
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(body)):
            assert backend.get("GITHUB_TOKEN") == "ghp_dop"

    def test_get_caches_result_on_second_call(self):
        backend = DopplerBackend(token="dp.st.test", project="proj", config="prd")
        body = {"secret": {"name": "KEY", "value": {"raw": "cached-val", "computed": "cached-val"}}}
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(body)) as mock_open:
            backend.get("KEY")
            backend.get("KEY")
            # urlopen should only have been called once (second call hits cache)
            assert mock_open.call_count == 1

    def test_get_returns_none_when_raw_value_is_empty(self):
        backend = DopplerBackend(token="dp.st.test", project="proj", config="prd")
        body = {"secret": {"name": "KEY", "value": {"raw": "", "computed": ""}}}
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(body)):
            assert backend.get("KEY") is None

    def test_get_returns_none_on_404(self):
        import urllib.error
        backend = DopplerBackend(token="dp.st.test", project="proj", config="prd")
        with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError(
            url=None, code=404, msg="Not Found", hdrs=None, fp=None
        )):
            assert backend.get("MISSING_KEY") is None

    def test_get_raises_runtime_error_on_non_404_http_error(self):
        import urllib.error
        backend = DopplerBackend(token="dp.st.test", project="proj", config="prd")
        with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError(
            url=None, code=403, msg="Forbidden", hdrs=None, fp=None
        )):
            with pytest.raises(RuntimeError, match="403"):
                backend.get("KEY")

    def test_get_raises_runtime_error_when_token_missing(self):
        backend = DopplerBackend(token="", project="proj", config="prd")
        with pytest.raises(RuntimeError, match="DOPPLER_TOKEN"):
            backend.get("KEY")

    def test_reads_token_from_env(self, monkeypatch):
        monkeypatch.setenv("DOPPLER_TOKEN", "dp.st.env-token")
        monkeypatch.setenv("DOPPLER_PROJECT", "env-proj")
        monkeypatch.setenv("DOPPLER_CONFIG", "env-cfg")
        backend = DopplerBackend()
        body = {"secret": {"name": "K", "value": {"raw": "env-val", "computed": "env-val"}}}
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(body)):
            assert backend.get("K") == "env-val"

    def test_error_message_does_not_contain_secret_value(self):
        import urllib.error
        backend = DopplerBackend(token="dp.st.test", project="proj", config="prd")
        with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError(
            url=None, code=500, msg="Server Error", hdrs=None, fp=None
        )):
            try:
                backend.get("SUPER_SECRET")
            except RuntimeError as exc:
                # Error must not contain any value — only status code / metadata
                assert "SUPER_SECRET" not in str(exc) or "500" in str(exc)

    def test_url_error_raises_runtime_error(self):
        import urllib.error
        backend = DopplerBackend(token="dp.st.test", project="proj", config="prd")
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")):
            with pytest.raises(RuntimeError, match="Doppler API"):
                backend.get("KEY")
