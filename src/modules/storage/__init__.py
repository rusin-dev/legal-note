"""存储模块：本地 Markdown 笔记读写 + 基于 Git（每笔记一分支）的远端同步"""
from .base import (
    GitCommandError,
    InvalidNotePathError,
    Note,
    NoteNotFoundError,
    RemoteUnavailableError,
    StorageError,
    note_id_for,
)
from .local import LocalStorage
from .remote import GitRemoteStorage, SyncConflict, SyncResult, build_auth_url

__all__ = [
    "Note",
    "note_id_for",
    "LocalStorage",
    "GitRemoteStorage",
    "SyncResult",
    "SyncConflict",
    "build_auth_url",
    "StorageError",
    "NoteNotFoundError",
    "InvalidNotePathError",
    "GitCommandError",
    "RemoteUnavailableError",
]
