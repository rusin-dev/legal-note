"""updater 模块测试

真实网络用例以 https://github.com/rusin-dev/rusin-note 的 Release 为解析基准。
"""

import json
import re
from pathlib import Path

import pytest
import requests

from src.modules import updater
from src.modules.updater import (
    get_current_channel,
    get_current_version,
    get_latest_version,
)

# 解析基准仓库及其最新 stable Release（tag: v3.11.0）
BASELINE_REPO = "rusin-dev/rusin-note"
BASELINE_LATEST_STABLE = "3.11.0"

METADATA_FILE = Path(__file__).resolve().parents[1] / "data" / "metadata.json"


def _metadata() -> dict:
    return json.loads(METADATA_FILE.read_text(encoding="utf-8"))


def _release(tag: str, prerelease: bool = False, draft: bool = False) -> dict:
    return {"tag_name": tag, "prerelease": prerelease, "draft": draft}


class _FakeResponse:
    def __init__(self, status_code: int, payload: list | None = None):
        self.status_code = status_code
        self._payload = payload or []

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Client Error")

    def json(self) -> list:
        return self._payload


@pytest.fixture
def fake_get(monkeypatch):
    calls: dict = {}

    def _install(releases=None, status_code=200):
        def fake(url, headers=None, timeout=None, params=None):
            calls["url"] = url
            calls["headers"] = headers
            calls["timeout"] = timeout
            calls["params"] = params
            return _FakeResponse(status_code, releases)

        monkeypatch.setattr(updater.requests, "get", fake)
        return calls

    return _install


def test_get_current_version_matches_metadata_file():
    assert get_current_version() == _metadata()["version"]


def test_get_current_channel_matches_metadata_file():
    assert get_current_channel() == _metadata()["channel"]
    assert get_current_channel() in updater.CHANNELS


def test_get_latest_version_request_and_stable_filtering(fake_get):
    calls = fake_get(
        releases=[
            _release("v2.0.0-rc.1", prerelease=True),
            _release("v1.9.0", draft=True),
            _release("v1.8.0"),
        ]
    )

    version = get_latest_version(repo="owner/repo", channel="stable")

    assert version == "1.8.0"
    assert calls["url"] == "https://api.github.com/repos/owner/repo/releases"
    assert calls["params"] == {"per_page": 100}
    assert "User-Agent" in calls["headers"]
    assert calls["timeout"] == 10.0


def test_get_latest_version_beta_selects_prerelease(fake_get):
    fake_get(
        releases=[
            _release("v2.0.0-rc.1", prerelease=True),
            _release("v1.8.0"),
        ]
    )

    assert get_latest_version(repo="owner/repo", channel="beta") == "2.0.0-rc.1"


def test_get_latest_version_defaults_to_metadata(fake_get):
    calls = fake_get(releases=[_release("v9.9.9")])

    get_latest_version()

    assert calls["url"] == (
        f"https://api.github.com/repos/{_metadata()['repo']}/releases"
    )


def test_get_latest_version_unknown_channel():
    with pytest.raises(ValueError):
        get_latest_version(channel="nightly")


def test_get_latest_version_raises_lookup_when_channel_empty(fake_get):
    fake_get(releases=[_release("v2.0.0-beta", prerelease=True)])

    with pytest.raises(LookupError):
        get_latest_version(repo="owner/repo", channel="stable")


def test_get_latest_version_raises_on_error_status(fake_get):
    fake_get(status_code=404)

    with pytest.raises(requests.HTTPError):
        get_latest_version(repo="owner/repo")


@pytest.mark.network
def test_get_latest_version_against_baseline_repo():
    try:
        version = get_latest_version(repo=BASELINE_REPO, channel="stable")
    except requests.exceptions.ConnectionError:
        pytest.skip("network unavailable")

    assert re.fullmatch(r"\d+\.\d+\.\d+", version)
    assert version == BASELINE_LATEST_STABLE
