"""
Git 远端存储

模型：远端仓库中每篇笔记对应一个长期分支 `note/<note-id>`，分支树里只存
该笔记文件（路径即笔记在工作区中的相对路径）。本地单一工作区目录，同步时
按「笔记 id（相对路径的 SHA1）→ 分支」映射，用 git plumbing 命令为单篇
笔记构建提交，不切换工作区检出。

冲突策略：本地与远端自上次同步基点后都有改动时，判定为冲突——两侧内容
都保留（本地文件不覆盖、远端分支不动），返回 base/local/remote 三方内容
及 unified diff，由调用方（UI）让用户决定，再用 resolve_conflict 提交合并
结果。
"""
from __future__ import annotations

import difflib
import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .base import (
    GitCommandError,
    RemoteUnavailableError,
    StorageError,
    note_id_for,
)
from .local import LocalStorage

BRANCH_PREFIX = "note/"
_IDENTITY_ENV = {
    "GIT_AUTHOR_NAME": "rusin-note",
    "GIT_AUTHOR_EMAIL": "storage@rusin.local",
    "GIT_COMMITTER_NAME": "rusin-note",
    "GIT_COMMITTER_EMAIL": "storage@rusin.local",
}


def build_auth_url(remote_url: str, token: str | None) -> str:
    """HTTPS 地址注入 oauth2 token；其他协议/无 token 原样返回"""
    if token and remote_url.startswith(("http://", "https://")):
        scheme, rest = remote_url.split("://", 1)
        return f"{scheme}://oauth2:{token}@{rest}"
    return remote_url


@dataclass
class SyncConflict:
    note_id: str
    rel_path: str
    base: str
    local: str
    remote: str
    diff: str


@dataclass
class SyncResult:
    pushed: list[str] = field(default_factory=list)
    pulled: list[str] = field(default_factory=list)
    conflicts: list[SyncConflict] = field(default_factory=list)
    deleted_local: list[str] = field(default_factory=list)
    deleted_remote: list[str] = field(default_factory=list)


class GitRemoteStorage:
    def __init__(self, workspace: Path, remote_url: str, token: str | None = None):
        self.workspace = Path(workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.local = LocalStorage(self.workspace)
        self.remote_url = remote_url
        self._token = token
        self._auth_url = build_auth_url(remote_url, token)
        self._rusin_dir = self.workspace / ".rusin"
        self.git_dir = self._rusin_dir / "git"
        self._state_path = self._rusin_dir / "state.json"
        self._rusin_dir.mkdir(parents=True, exist_ok=True)
        if not (self.git_dir / "HEAD").exists():
            self._run("init", "--bare", "--quiet", str(self.git_dir), use_git_dir=False)

    # ---- public API ----

    def sync(self) -> SyncResult:
        state = self._load_state()
        local_notes = self._scan_local()
        remote_shas = self._list_remote_branches()
        self._fetch_remote(remote_shas)

        notes: dict[str, dict] = {}
        def entry(note_id: str, rel: str) -> dict:
            return notes.setdefault(note_id, {"rel_path": rel})

        for rel, content in local_notes.items():
            e = entry(note_id_for(rel), rel)
            e["local"] = content
        for note_id, s in state.items():
            entry(note_id, s["rel_path"])["state"] = s
        for note_id, sha in remote_shas.items():
            e = entry(note_id, self._remote_rel_path(note_id))
            e["remote"] = sha

        result = SyncResult()
        for note_id in sorted(notes, key=lambda i: (notes[i]["rel_path"], i)):
            self._sync_one(notes[note_id], note_id, state, result)
        self._save_state(state)
        return result

    def resolve_conflict(self, note_id: str, content: str) -> None:
        state = self._load_state()
        if note_id not in state:
            raise StorageError(f"未知笔记，无法解决冲突: {note_id}")
        rel = state[note_id]["rel_path"]
        remote_shas = self._list_remote_branches()
        self._fetch_remote(remote_shas)
        parent = remote_shas.get(note_id)
        sha, blob = self._push_note_commit(note_id, rel, content, parent)
        self._write_local_file(rel, content)
        state[note_id] = {"rel_path": rel, "base_sha": sha, "base_blob": blob}
        self._save_state(state)

    # ---- per-note sync ----

    def _sync_one(self, e: dict, note_id: str, state: dict, result: SyncResult) -> None:
        rel = e["rel_path"]
        local_content = e.get("local")
        remote_sha = e.get("remote")
        s = e.get("state")

        if local_content is not None and remote_sha is None:
            if s is None or s.get("base_sha") is None:
                self._do_push(note_id, rel, local_content, None, state, result)
            elif local_content == self._blob_content(s["base_blob"]):
                # 远端分支已被其他设备删除且本地未改动：跟随删除
                self.local.delete(rel)
                state.pop(note_id, None)
                result.deleted_local.append(rel)
            else:
                self._do_push(note_id, rel, local_content, None, state, result)
            return

        if local_content is None and remote_sha is not None:
            if s is not None:
                # 用户删除了笔记：传播删除远端分支
                self._do_delete_remote(note_id, rel, state, result)
            else:
                self._do_pull(note_id, rel, remote_sha, state, result)
            return

        if local_content is None and remote_sha is None and s is not None:
            state.pop(note_id, None)
            return

        base_sha = s["base_sha"] if s else None
        base_content = self._blob_content(s["base_blob"]) if s else ""
        local_changed = s is None or local_content != base_content
        remote_changed = s is None or remote_sha != base_sha
        if not local_changed and not remote_changed:
            return
        if local_changed and not remote_changed:
            self._do_push(note_id, rel, local_content, remote_sha, state, result)
            return
        remote_content = self._remote_content(note_id, rel)
        if remote_content == local_content:
            state[note_id] = {
                "rel_path": rel,
                "base_sha": remote_sha,
                "base_blob": self._hash_blob(local_content),
            }
            return
        if local_content == base_content:
            self._do_pull(note_id, rel, remote_sha, state, result)
            return
        result.conflicts.append(
            SyncConflict(
                note_id=note_id,
                rel_path=rel,
                base=base_content,
                local=local_content,
                remote=remote_content,
                diff="".join(
                    difflib.unified_diff(
                        remote_content.splitlines(keepends=True),
                        local_content.splitlines(keepends=True),
                        fromfile="remote/" + rel,
                        tofile="local/" + rel,
                    )
                ),
            )
        )

    def _do_push(self, note_id, rel, content, parent_sha, state, result) -> None:
        sha, blob = self._push_note_commit(note_id, rel, content, parent_sha)
        state[note_id] = {"rel_path": rel, "base_sha": sha, "base_blob": blob}
        result.pushed.append(rel)

    def _do_pull(self, note_id, rel, remote_sha, state, result) -> None:
        content = self._remote_content(note_id, rel)
        self._write_local_file(rel, content)
        state[note_id] = {
            "rel_path": rel,
            "base_sha": remote_sha,
            "base_blob": self._hash_blob(content),
        }
        result.pulled.append(rel)

    def _do_delete_remote(self, note_id, rel, state, result) -> None:
        self._run("push", self._auth_url, "--delete", f"refs/heads/{BRANCH_PREFIX}{note_id}", network=True)
        self._run("update-ref", "-d", f"refs/heads/{BRANCH_PREFIX}{note_id}")
        state.pop(note_id, None)
        result.deleted_remote.append(rel)

    # ---- git plumbing ----

    def _push_note_commit(self, note_id, rel, content, parent_sha) -> tuple[str, str]:
        blob = self._hash_blob(content)
        index_file = self.git_dir / f"sync-index-{os.getpid()}"
        try:
            if parent_sha:
                self._run("read-tree", parent_sha, index_file=index_file)
            self._run(
                "update-index", "--add", "--cacheinfo", f"100644,{blob},{rel}",
                index_file=index_file,
            )
            tree = self._run("write-tree", index_file=index_file).strip()
            args = ["commit-tree", tree, "-m", f"sync: {rel}"]
            if parent_sha:
                args += ["-p", parent_sha]
            commit = self._run(*args).strip()
            self._run("update-ref", f"refs/heads/{BRANCH_PREFIX}{note_id}", commit)
            self._run(
                "push", self._auth_url,
                f"refs/heads/{BRANCH_PREFIX}{note_id}:refs/heads/{BRANCH_PREFIX}{note_id}",
                network=True,
            )
        finally:
            index_file.unlink(missing_ok=True)
        return commit, blob

    def _hash_blob(self, content: str) -> str:
        return self._run("hash-object", "-w", "--stdin", stdin=content).strip()

    def _blob_content(self, blob: str) -> str:
        return self._run("cat-file", "blob", blob)

    def _remote_content(self, note_id: str, rel: str) -> str:
        return self._run(
            "cat-file", "blob", f"refs/remotes/origin/{BRANCH_PREFIX}{note_id}:{rel}"
        )

    def _remote_rel_path(self, note_id: str) -> str:
        sha_ref = f"refs/remotes/origin/{BRANCH_PREFIX}{note_id}"
        paths = [
            line for line in
            self._run("ls-tree", "-r", "--name-only", sha_ref).splitlines() if line
        ]
        if len(paths) != 1:
            raise StorageError(f"分支 {sha_ref} 应只含一个笔记文件，实际: {paths}")
        rel = paths[0]
        if note_id_for(rel) != note_id:
            raise StorageError(f"分支笔记 id 与路径不一致: {rel}")
        return rel

    def _list_remote_branches(self) -> dict[str, str]:
        out = self._run("ls-remote", "--heads", self._auth_url, network=True)
        branches: dict[str, str] = {}
        for line in out.splitlines():
            sha, _, ref = line.partition("\t")
            if ref.startswith(f"refs/heads/{BRANCH_PREFIX}"):
                branches[ref.removeprefix(f"refs/heads/{BRANCH_PREFIX}")] = sha
        return branches

    def _fetch_remote(self, remote_shas: dict[str, str]) -> None:
        stale = self._run(
            "for-each-ref", "--format=%(refname)", f"refs/remotes/origin/{BRANCH_PREFIX}"
        ).splitlines()
        for ref in stale:
            self._run("update-ref", "-d", ref)
        if not remote_shas:
            return
        refspecs = [
            f"+refs/heads/{BRANCH_PREFIX}{note_id}:refs/remotes/origin/{BRANCH_PREFIX}{note_id}"
            for note_id in sorted(remote_shas)
        ]
        self._run("fetch", "--no-tags", self._auth_url, *refspecs, network=True)

    # ---- workspace helpers ----

    def _scan_local(self) -> dict[str, str]:
        root = self.workspace.resolve()
        notes: dict[str, str] = {}
        for path in root.rglob("*.md"):
            if not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            if rel.split("/", 1)[0] == ".rusin":
                continue
            notes[rel] = path.read_text(encoding="utf-8")
        return notes

    def _write_local_file(self, rel: str, content: str) -> None:
        path = self.local._resolve(rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    # ---- state ----

    def _load_state(self) -> dict:
        if self._state_path.is_file():
            return json.loads(self._state_path.read_text(encoding="utf-8"))
        return {}

    def _save_state(self, state: dict) -> None:
        self._state_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ---- subprocess ----

    def _run(self, *args: str, stdin: str | None = None, index_file: Path | None = None,
             use_git_dir: bool = True, network: bool = False) -> str:
        env = os.environ.copy()
        if use_git_dir:
            env["GIT_DIR"] = str(self.git_dir)
        if index_file is not None:
            env["GIT_INDEX_FILE"] = str(index_file)
        env["GIT_TERMINAL_PROMPT"] = "0"
        env.update(_IDENTITY_ENV)
        proc = subprocess.run(
            ["git", *args], input=stdin, capture_output=True,
            text=True, encoding="utf-8", env=env,
        )
        if proc.returncode != 0:
            message = self._mask(f"git {' '.join(args)} 失败: {proc.stderr.strip()}")
            if network:
                raise RemoteUnavailableError(message) from None
            raise GitCommandError(message) from None
        return proc.stdout

    def _mask(self, text: str) -> str:
        if self._token:
            text = text.replace(self._auth_url, "***").replace(self._token, "***")
        return text
