"""
Github 仓库发行版更新器

版本信息来自 data/metadata.json（构建流水线生成）。
PyInstaller 打包需携带数据目录：--add-data "data;data"
"""

import json
import sys
from pathlib import Path

import requests

_METADATA_RELATIVE_PATH = Path("data") / "metadata.json"

CHANNELS = ("stable", "beta")


def _metadata_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / _METADATA_RELATIVE_PATH # pyright: ignore[reportAttributeAccessIssue]
    return Path(__file__).resolve().parents[2] / _METADATA_RELATIVE_PATH


def _load_metadata() -> dict:
    with open(_metadata_path(), encoding="utf-8") as f:
        return json.load(f)


def get_current_version() -> str:
    """本地 metadata.json 中记录的版本"""
    return _load_metadata()["version"]


def get_current_channel() -> str:
    """本地 metadata.json 中记录的更新渠道（stable / beta）"""
    return _load_metadata()["channel"]


def get_latest_version(
    repo: str | None = None,
    channel: str | None = None,
    timeout: float = 10.0,
) -> str:
    """从 GitHub Releases 获取指定渠道的最新版本号（去掉前导 v）

    stable 取非 prerelease 的 Release，beta 取 prerelease 的 Release；
    渠道内无匹配 Release 时抛 LookupError。
    """
    metadata = _load_metadata()
    repo = repo or metadata["repo"]
    channel = channel or metadata["channel"]
    if channel not in CHANNELS:
        raise ValueError(f"未知渠道 {channel!r}，可选：{CHANNELS}")
    want_prerelease = channel == "beta"

    response = requests.get(
        f"https://api.github.com/repos/{repo}/releases",
        params={"per_page": 100},
        headers={"User-Agent": "rusin-note-desktop-updater"},
        timeout=timeout,
    )
    response.raise_for_status()

    for release in response.json():
        if release["draft"]:
            continue
        if bool(release["prerelease"]) is want_prerelease:
            return release["tag_name"].lstrip("v")
    raise LookupError(f"{repo} 没有 {channel} 渠道的 Release")
