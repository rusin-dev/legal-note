"""tests for src.modules.storage.remote — 每笔记一分支的 Git 同步"""
import subprocess

import pytest

from src.modules.storage.base import Note, note_id_for
from src.modules.storage.local import LocalStorage
from src.modules.storage.remote import (
    GitRemoteStorage,
    RemoteUnavailableError,
    build_auth_url,
)


def git(*args, check=True):
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, check=check
    ).stdout


@pytest.fixture
def origin(tmp_path):
    path = tmp_path / "origin.git"
    git("init", "--bare", str(path))
    return str(path)


def make_ws(tmp_path, name, origin):
    ws = tmp_path / name
    return LocalStorage(ws), GitRemoteStorage(ws, origin)


def origin_branches(origin):
    out = git("--git-dir", origin, "for-each-ref", "--format=%(refname)", "refs/heads/")
    return [line.removeprefix("refs/heads/") for line in out.splitlines()]


def origin_file_content(origin, branch, path):
    return git("--git-dir", origin, "show", f"refs/heads/{branch}:{path}")


def branch_of(rel_path):
    return "note/" + note_id_for(rel_path)


class TestPushPull:
    def test_new_note_pushes_to_its_own_branch(self, tmp_path, origin):
        local, remote = make_ws(tmp_path, "a", origin)
        local.write(Note(rel_path="journal/one.md", content="hello"))
        result = remote.sync()
        assert result.pushed == ["journal/one.md"]
        assert origin_branches(origin) == [branch_of("journal/one.md")]
        assert origin_file_content(
            origin, branch_of("journal/one.md"), "journal/one.md"
        ) == "hello"

    def test_second_workspace_pulls_note(self, tmp_path, origin):
        a_local, a_remote = make_ws(tmp_path, "a", origin)
        a_local.write(Note(rel_path="journal/one.md", content="hello"))
        a_remote.sync()
        b_local, b_remote = make_ws(tmp_path, "b", origin)
        result = b_remote.sync()
        assert result.pulled == ["journal/one.md"]
        assert b_local.read("journal/one.md").content == "hello"

    def test_local_edit_pushes_and_other_pulls(self, tmp_path, origin):
        a_local, a_remote = make_ws(tmp_path, "a", origin)
        b_local, b_remote = make_ws(tmp_path, "b", origin)
        a_local.write(Note(rel_path="x.md", content="v1"))
        a_remote.sync()
        b_remote.sync()
        a_local.write(Note(rel_path="x.md", content="v2"))
        assert a_remote.sync().pushed == ["x.md"]
        assert b_remote.sync().pulled == ["x.md"]
        assert b_local.read("x.md").content == "v2"

    def test_sync_is_idempotent(self, tmp_path, origin):
        local, remote = make_ws(tmp_path, "a", origin)
        local.write(Note(rel_path="x.md", content="v1"))
        remote.sync()
        quiet = remote.sync()
        assert quiet.pushed == []
        assert quiet.pulled == []
        assert quiet.conflicts == []

    def test_sync_survives_restart(self, tmp_path, origin):
        """state 持久化在 .rusin 目录，新实例不会把远端已有笔记误判为冲突"""
        local, remote = make_ws(tmp_path, "a", origin)
        local.write(Note(rel_path="x.md", content="v1"))
        remote.sync()
        restarted = GitRemoteStorage(tmp_path / "a", origin)
        result = restarted.sync()
        assert result.pushed == [] and result.pulled == [] and result.conflicts == []


class TestConflicts:
    def setup_pair(self, tmp_path, origin):
        a_local, a_remote = make_ws(tmp_path, "a", origin)
        b_local, b_remote = make_ws(tmp_path, "b", origin)
        a_local.write(Note(rel_path="d.md", content="line1\nline2\n"))
        a_remote.sync()
        b_remote.sync()
        return a_local, a_remote, b_local, b_remote

    def test_diverged_edit_yields_diff_and_keeps_both_sides(self, tmp_path, origin):
        a_local, a_remote, b_local, b_remote = self.setup_pair(tmp_path, origin)
        a_local.write(Note(rel_path="d.md", content="line1\nline2a\n"))
        a_remote.sync()
        b_local.write(Note(rel_path="d.md", content="line1\nline2b\n"))
        result = b_remote.sync()
        assert len(result.conflicts) == 1
        conflict = result.conflicts[0]
        assert conflict.rel_path == "d.md"
        assert conflict.local == "line1\nline2b\n"
        assert conflict.remote == "line1\nline2a\n"
        assert "line2a" in conflict.diff and "line2b" in conflict.diff
        assert "line2a" in conflict.diff
        # 双方副本都保留：本地文件未被覆盖，远端分支仍是 A 的版本
        assert b_local.read("d.md").content == "line1\nline2b\n"
        assert origin_file_content(origin, branch_of("d.md"), "d.md") == "line1\nline2a\n"

    def test_resolve_conflict_pushs_merged_and_other_side_pulls(self, tmp_path, origin):
        a_local, a_remote, b_local, b_remote = self.setup_pair(tmp_path, origin)
        a_local.write(Note(rel_path="d.md", content="line1\nline2a\n"))
        a_remote.sync()
        b_local.write(Note(rel_path="d.md", content="line1\nline2b\n"))
        conflict = b_remote.sync().conflicts[0]
        b_remote.resolve_conflict(conflict.note_id, "line1\nmerged\n")
        assert origin_file_content(origin, branch_of("d.md"), "d.md") == "line1\nmerged\n"
        assert b_local.read("d.md").content == "line1\nmerged\n"
        assert a_remote.sync().pulled == ["d.md"]
        assert a_local.read("d.md").content == "line1\nmerged\n"

    def test_conflict_persists_until_resolved(self, tmp_path, origin):
        a_local, a_remote, b_local, b_remote = self.setup_pair(tmp_path, origin)
        a_local.write(Note(rel_path="d.md", content="line1\nline2a\n"))
        a_remote.sync()
        b_local.write(Note(rel_path="d.md", content="line1\nline2b\n"))
        assert len(b_remote.sync().conflicts) == 1
        assert len(b_remote.sync().conflicts) == 1


class TestDeletion:
    def test_local_delete_removes_remote_branch(self, tmp_path, origin):
        local, remote = make_ws(tmp_path, "a", origin)
        local.write(Note(rel_path="gone.md", content="x"))
        remote.sync()
        local.delete("gone.md")
        result = remote.sync()
        assert result.deleted_remote == ["gone.md"]
        assert origin_branches(origin) == []

    def test_remote_delete_removes_untouched_local_copy(self, tmp_path, origin):
        a_local, a_remote = make_ws(tmp_path, "a", origin)
        b_local, b_remote = make_ws(tmp_path, "b", origin)
        a_local.write(Note(rel_path="gone.md", content="x"))
        a_remote.sync()
        b_remote.sync()
        a_local.delete("gone.md")
        a_remote.sync()
        result = b_remote.sync()
        assert result.deleted_local == ["gone.md"]
        assert not (b_local.workspace / "gone.md").exists()

    def test_remote_delete_keeps_locally_edited_copy_and_repushes(self, tmp_path, origin):
        a_local, a_remote = make_ws(tmp_path, "a", origin)
        b_local, b_remote = make_ws(tmp_path, "b", origin)
        a_local.write(Note(rel_path="gone.md", content="x"))
        a_remote.sync()
        b_remote.sync()
        a_local.delete("gone.md")
        a_remote.sync()
        b_local.write(Note(rel_path="gone.md", content="edited after delete"))
        result = b_remote.sync()
        assert result.pushed == ["gone.md"]
        assert origin_file_content(
            origin, branch_of("gone.md"), "gone.md"
        ) == "edited after delete"


class TestAuthUrl:
    def test_token_is_injected_into_https_url(self):
        assert (
            build_auth_url("https://github.com/u/n.git", "tok")
            == "https://oauth2:tok@github.com/u/n.git"
        )

    def test_no_token_leaves_https_url_untouched(self):
        assert build_auth_url("https://github.com/u/n.git", None) == (
            "https://github.com/u/n.git"
        )

    def test_local_path_origin_is_untouched(self, tmp_path):
        assert build_auth_url(str(tmp_path), None) == str(tmp_path)
        assert build_auth_url(str(tmp_path), "tok") == str(tmp_path)


def test_unreachable_origin_raises_remote_unavailable(tmp_path):
    local, remote = make_ws(tmp_path, "a", str(tmp_path / "missing.git"))
    local.write(Note(rel_path="x.md", content="v"))
    with pytest.raises(RemoteUnavailableError):
        remote.sync()


def test_error_messages_do_not_leak_token(tmp_path):
    remote = GitRemoteStorage(
        tmp_path / "ws", "https://github.invalid/u/n.git", token="s3cr3t"
    )
    with pytest.raises(RemoteUnavailableError) as exc_info:
        remote.sync()
    assert "s3cr3t" not in str(exc_info.value)
