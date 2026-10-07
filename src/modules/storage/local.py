"""
本地笔记存储
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from .base import InvalidNotePathError, Note, NoteNotFoundError, normalize_rel_path

_FRONT_MATTER = re.compile(r"^---\r?\n(.*?)\r?\n---(?:\r?\n|\Z)", re.DOTALL)


class LocalStorage:
    """以工作区目录为根的 Markdown 笔记读写，元数据存于 YAML front-matter"""

    def __init__(self, workspace: Path):
        self.workspace = Path(workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)

    def list(self) -> list[Note]:
        root = self.workspace.resolve()
        paths = sorted(
            p.relative_to(root).as_posix() for p in root.rglob("*.md") if p.is_file()
        )
        return [self.read(rel) for rel in paths]

    def exists(self, rel_path: str) -> bool:
        return self._resolve(rel_path).is_file()

    def read(self, rel_path: str) -> Note:
        path = self._resolve(rel_path)
        if not path.is_file():
            raise NoteNotFoundError(f"笔记不存在: {rel_path}")
        raw = path.read_text(encoding="utf-8")
        match = _FRONT_MATTER.match(raw)
        if match:
            metadata = yaml.safe_load(match.group(1))
            content = raw[match.end():]
        else:
            metadata, content = {}, raw
        return Note(
            rel_path=normalize_rel_path(rel_path),
            metadata=metadata if isinstance(metadata, dict) else {},
            content=content,
        )

    def write(self, note: Note) -> None:
        path = self._resolve(note.rel_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if note.metadata:
            front = yaml.safe_dump(
                note.metadata, allow_unicode=True, sort_keys=True
            )
            path.write_text(f"---\n{front}---\n{note.content}", encoding="utf-8")
        else:
            path.write_text(note.content, encoding="utf-8")

    def delete(self, rel_path: str) -> None:
        path = self._resolve(rel_path)
        if not path.is_file():
            raise NoteNotFoundError(f"笔记不存在: {rel_path}")
        path.unlink()

    def _resolve(self, rel_path: str) -> Path:
        normalized = normalize_rel_path(rel_path)
        root = self.workspace.resolve()
        path = (root / normalized).resolve()
        if not path.is_relative_to(root):
            raise InvalidNotePathError(f"非法笔记路径（越出工作区）: {rel_path!r}")
        return path
