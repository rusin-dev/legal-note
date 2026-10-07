"""统一数据接口：所有数据的 CRUD 都必须经过 DataService"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from src.modules.storage.base import Note
from src.modules.storage.config import JsonConfigStore
from src.modules.storage.local import LocalStorage


@runtime_checkable
class NoteRepository(Protocol):
    """笔记仓库抽象契约，LocalStorage 为其本地实现"""

    def list(self) -> list[Note]: ...

    def exists(self, rel_path: str) -> bool: ...

    def read(self, rel_path: str) -> Note: ...

    def write(self, note: Note) -> None: ...

    def delete(self, rel_path: str) -> None: ...


@runtime_checkable
class ConfigStore(Protocol):
    """扁平 KV 配置抽象契约，键名规范为 <module_id>.<data_id>"""

    def get(self, key: str, default: Any = None) -> Any: ...

    def set(self, key: str, value: Any) -> None: ...

    def delete(self, key: str) -> None: ...

    def keys(self, module_id: str | None = None) -> list[str]: ...


class DataService:
    """应用唯一数据入口：notes 子接口管理笔记，config 子接口管理配置"""

    def __init__(self, notes: NoteRepository, config: ConfigStore):
        self._notes = notes
        self._config = config

    @classmethod
    def local(cls, workspace: Path, data_dir: Path) -> "DataService":
        """装配本地实现：workspace 下的 Markdown 笔记 + data_dir/config.json 配置"""
        return cls(
            notes=LocalStorage(workspace),
            config=JsonConfigStore(Path(data_dir) / "config.json"),
        )

    @property
    def notes(self) -> NoteRepository:
        return self._notes

    @property
    def config(self) -> ConfigStore:
        return self._config
