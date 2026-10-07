"""存储层公共契约：Note、错误类型、笔记 ID"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field


class StorageError(Exception):
    """存储层错误基类"""


class NoteNotFoundError(StorageError):
    """笔记不存在"""


class InvalidNotePathError(StorageError):
    """非法的笔记相对路径"""


class GitCommandError(StorageError):
    """git 命令执行失败"""


class RemoteUnavailableError(StorageError):
    """远端仓库不可达（网络/认证失败）"""


@dataclass
class Note:
    rel_path: str
    metadata: dict = field(default_factory=dict)
    content: str = ""

    @property
    def note_id(self) -> str:
        return note_id_for(self.rel_path)


def normalize_rel_path(rel_path: str) -> str:
    """校验并规范化笔记相对路径，统一为 '/' 分隔、以 .md 结尾"""
    normalized = rel_path.replace("\\", "/")
    if not normalized or normalized.startswith("/"):
        raise InvalidNotePathError(f"非法笔记路径: {rel_path!r}")
    if re.match(r"^[A-Za-z]:", normalized):
        raise InvalidNotePathError(f"非法笔记路径（含盘符）: {rel_path!r}")
    segments = normalized.split("/")
    if any(seg in ("", ".", "..") for seg in segments):
        raise InvalidNotePathError(f"非法笔记路径: {rel_path!r}")
    if not segments[-1].endswith(".md"):
        raise InvalidNotePathError(f"笔记路径必须以 .md 结尾: {rel_path!r}")
    return normalized


def note_id_for(rel_path: str) -> str:
    return hashlib.sha1(normalize_rel_path(rel_path).encode("utf-8")).hexdigest()
