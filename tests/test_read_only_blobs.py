"""Mapped files must be bounded regular text blobs, never checked out or executed."""

from pathlib import Path

import pytest

from doctracker.system import gitops
from doctracker.system.gitops import FileUnreadable, Workspace
from fixtures.build_fixture_repo import commit, run, write


@pytest.mark.parametrize('kind', ['symlink', 'oversized', 'binary'])
def test_unreadable_mapped_blob(kind: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / 'owner' / 'repo.git'
    repo.mkdir(parents=True)
    run(repo, 'init', '-q', '-b', 'main')
    if kind == 'symlink':
        (repo / 'doc.md').symlink_to('/etc/passwd')
    elif kind == 'oversized':
        write(repo, 'doc.md', 'x' * (gitops.MAX_TEXT_BYTES + 1))
    else:
        write(repo, 'doc.md', b'\x00binary')
    sha = commit(repo, 0, 'Unreadable fixture', 'unreadable')
    monkeypatch.setattr(gitops, 'GIT_BASE', f'file://{tmp_path}')
    with Workspace('owner/repo') as ws:
        ws.clone()
        with pytest.raises(FileUnreadable):
            ws.read_text(sha, 'doc.md')
        assert ws.read_text(sha, 'absent.md') is None


def test_script_is_read_as_text_and_never_executed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / 'owner' / 'repo.git'
    repo.mkdir(parents=True)
    run(repo, 'init', '-q', '-b', 'main')
    marker = tmp_path / 'executed'
    payload = f'#!/bin/sh\ntouch "{marker}"\n'
    write(repo, 'script.sh', payload)
    (repo / 'script.sh').chmod(0o755)
    sha = commit(repo, 0, 'Harmless execution marker', 'marker')
    monkeypatch.setattr(gitops, 'GIT_BASE', f'file://{tmp_path}')
    with Workspace('owner/repo') as ws:
        ws.clone()
        assert ws.read_text(sha, 'script.sh') == payload
    assert not marker.exists()
    assert (repo / 'script.sh').read_text() == payload
