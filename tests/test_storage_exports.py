"""storage 模块公共 API 导出"""
from src.modules.storage import (
    GitRemoteStorage,
    InvalidNotePathError,
    LocalStorage,
    Note,
    NoteNotFoundError,
    RemoteUnavailableError,
    StorageError,
    SyncConflict,
    SyncResult,
    note_id_for,
)


def test_public_api_is_exported():
    assert LocalStorage is not None
    assert GitRemoteStorage is not None
    assert Note is not None
    assert SyncResult is not None
    assert SyncConflict is not None
    assert note_id_for is not None
    assert issubclass(NoteNotFoundError, StorageError)
    assert issubclass(InvalidNotePathError, StorageError)
    assert issubclass(RemoteUnavailableError, StorageError)
