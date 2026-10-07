"""tests for src.modules.storage.local / base"""
from pathlib import Path

import pytest

from src.modules.storage.base import (
    InvalidNotePathError,
    Note,
    NoteNotFoundError,
    note_id_for,
)
from src.modules.storage.local import LocalStorage


@pytest.fixture
def store(tmp_path: Path) -> LocalStorage:
    return LocalStorage(tmp_path / "notes")


class TestReadWrite:
    def test_roundtrip_preserves_metadata_and_body(self, store):
        note = Note(
            rel_path="journal/day.md",
            metadata={"title": "Day", "tags": ["a", "b"]},
            content="# Hello\nbody text",
        )
        store.write(note)
        loaded = store.read("journal/day.md")
        assert loaded.content == "# Hello\nbody text"
        assert loaded.metadata == {"title": "Day", "tags": ["a", "b"]}

    def test_write_without_metadata_omits_front_matter(self, store):
        store.write(Note(rel_path="plain.md", metadata={}, content="just text"))
        raw = (store.workspace / "plain.md").read_text(encoding="utf-8")
        assert not raw.startswith("---")
        assert raw == "just text"

    def test_read_file_without_front_matter(self, store):
        (store.workspace / "legacy").mkdir(parents=True)
        (store.workspace / "legacy" / "old.md").write_text(
            "no front matter here", encoding="utf-8"
        )
        loaded = store.read("legacy/old.md")
        assert loaded.metadata == {}
        assert loaded.content == "no front matter here"

    def test_read_missing_note_raises(self, store):
        with pytest.raises(NoteNotFoundError):
            store.read("does/not/exist.md")

    def test_exists(self, store):
        store.write(Note(rel_path="a.md", metadata={}, content="x"))
        assert store.exists("a.md")
        assert not store.exists("b.md")


class TestListAndDelete:
    def test_list_returns_all_notes_sorted(self, store):
        store.write(Note(rel_path="b.md", metadata={}, content="2"))
        store.write(Note(rel_path="a/z.md", metadata={}, content="z"))
        store.write(Note(rel_path="a.md", metadata={}, content="1"))
        (store.workspace / "ignore.txt").write_text("x", encoding="utf-8")
        notes = store.list()
        assert [n.rel_path for n in notes] == ["a.md", "a/z.md", "b.md"]
        assert notes[0].content == "1"

    def test_delete_removes_file(self, store):
        store.write(Note(rel_path="gone.md", metadata={"k": "v"}, content="x"))
        store.delete("gone.md")
        assert not (store.workspace / "gone.md").exists()
        with pytest.raises(NoteNotFoundError):
            store.read("gone.md")


class TestPathSafety:
    @pytest.mark.parametrize(
        "bad",
        ["../evil.md", "a/../../evil.md", "/abs/evil.md", "C:\\evil.md", "sub\\a.md\\..\\..\\x.md"],
    )
    def test_write_rejects_unsafe_paths(self, store, bad):
        with pytest.raises(InvalidNotePathError):
            store.write(Note(rel_path=bad, metadata={}, content="x"))

    @pytest.mark.parametrize("bad", ["../evil.md", "notes.txt"])
    def test_read_rejects_unsafe_or_non_markdown_paths(self, store, bad):
        with pytest.raises(InvalidNotePathError):
            store.read(bad)

    def test_backslash_inside_path_is_normalized(self, store):
        store.write(Note(rel_path="dir\\file.md", metadata={}, content="ok"))
        assert store.read("dir/file.md").content == "ok"


class TestNoteId:
    def test_note_id_is_stable_sha1_of_rel_path(self):
        import hashlib

        assert note_id_for("a/b.md") == hashlib.sha1(b"a/b.md").hexdigest()
        assert note_id_for("a/b.md") == note_id_for("a/b.md")
