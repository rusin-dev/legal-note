"""tests for src.core.data / DataService 统一数据接口"""
from pathlib import Path

import pytest

from src.core.data import ConfigStore, DataService, NoteRepository
from src.modules.storage.base import Note
from src.modules.storage.config import JsonConfigStore
from src.modules.storage.local import LocalStorage


@pytest.fixture
def service(tmp_path: Path) -> DataService:
    return DataService.local(tmp_path / "notes", tmp_path / "data")


class TestProtocols:
    def test_local_storage_satisfies_note_repository(self, tmp_path):
        assert isinstance(LocalStorage(tmp_path), NoteRepository)

    def test_json_config_store_satisfies_config_store(self, tmp_path):
        assert isinstance(JsonConfigStore(tmp_path / "c.json"), ConfigStore)


class TestNoteCrudThroughService:
    def test_write_read_roundtrip(self, service):
        service.notes.write(
            Note(rel_path="journal/a.md", metadata={"t": 1}, content="hi")
        )
        loaded = service.notes.read("journal/a.md")
        assert loaded.content == "hi"
        assert loaded.metadata == {"t": 1}

    def test_list_and_exists_and_delete(self, service):
        service.notes.write(Note(rel_path="b.md", metadata={}, content="2"))
        assert service.notes.exists("b.md")
        assert [n.rel_path for n in service.notes.list()] == ["b.md"]
        service.notes.delete("b.md")
        assert not service.notes.exists("b.md")


class TestConfigThroughService:
    def test_set_get_persists_under_data_dir(self, service, tmp_path):
        service.config.set("ui.theme", "dark")
        assert (tmp_path / "data" / "config.json").is_file()
        assert service.config.get("ui.theme") == "dark"

    def test_config_survives_new_service(self, service, tmp_path):
        service.config.set("updater.channel", "stable")
        reopened = DataService.local(tmp_path / "notes", tmp_path / "data")
        assert reopened.config.get("updater.channel") == "stable"


class TestDependencyInjection:
    def test_accepts_custom_note_repository(self, tmp_path):
        class InMemoryNotes:
            def __init__(self):
                self.notes: dict[str, Note] = {}

            def list(self):
                return list(self.notes.values())

            def exists(self, rel_path):
                return rel_path in self.notes

            def read(self, rel_path):
                return self.notes[rel_path]

            def write(self, note):
                self.notes[note.rel_path] = note

            def delete(self, rel_path):
                del self.notes[rel_path]

        fake = InMemoryNotes()
        service = DataService(
            notes=fake, config=JsonConfigStore(tmp_path / "c.json")
        )
        service.notes.write(Note(rel_path="x.md", metadata={}, content="1"))
        assert service.notes.read("x.md").content == "1"
