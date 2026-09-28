"""scanner.py testleri: gerçek git reposu, gerçek dosya sistemi."""

from __future__ import annotations

from pathlib import Path

import pytest

from generator.scanner import (
    NotARepositoryError,
    RepositoryHasNoCommitsError,
    ScannerError,
    read_commits,
    read_dependency_history,
    read_documents,
    scan_repository,
)


def test_scan_collects_all_signals(sample_repo: Path) -> None:
    scan = scan_repository(sample_repo)

    assert scan.repo_name == "ornek-proje"
    assert len(scan.commits) == 5
    assert {dep.path for dep in scan.dependency_files} == {
        "requirements.txt",
        "package.json",
    }
    assert {doc.path for doc in scan.documents} == {
        "README.md",
        ".context/mimari.md",
    }


def test_commits_are_chronological_oldest_first(sample_repo: Path) -> None:
    commits = read_commits(sample_repo)

    assert [c.date for c in commits] == sorted(c.date for c in commits)
    assert commits[0].subject == "ilk commit: README"
    assert commits[-1].subject == "mimari dokumani eklendi"


def test_commit_subjects_with_pipe_do_not_break_parsing(tmp_path: Path) -> None:
    """Konu satırındaki '|' karakteri alanları bozmamalı."""
    from tests.conftest import commit, git

    repo = tmp_path / "pipe-repo"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.name", "T")
    git(repo, "config", "user.email", "t@x.invalid")
    commit(repo, "a.txt", "x\n", "feat: a | b ekledi", "2024-01-01")

    commits = read_commits(repo)
    assert len(commits) == 1
    assert commits[0].subject == "feat: a | b ekledi"
    assert commits[0].date == "2024-01-01"


def test_dependency_history_contains_real_diff(sample_repo: Path) -> None:
    deps = {d.path: d for d in read_dependency_history(sample_repo)}

    requirements = deps["requirements.txt"].history
    assert "+flask==3.0.0" in requirements
    assert deps["package.json"].history.count("jest") >= 1


def test_dependency_history_is_bounded(sample_repo: Path) -> None:
    """Diff'ler sınırsız dökülmemeli; limit uygulanınca truncated işaretlenmeli."""
    deps = read_dependency_history(sample_repo, max_chars=50)
    assert all(d.truncated for d in deps)
    assert all(len(d.history) == 50 for d in deps)


def test_documents_include_context_dir(sample_repo: Path) -> None:
    docs = {d.path: d for d in read_documents(sample_repo)}
    assert "Bir deneme projesi" in docs["README.md"].content
    assert "Mimari notlari" in docs[".context/mimari.md"].content


def test_missing_optional_files_are_omitted(sample_repo: Path) -> None:
    (sample_repo / "requirements.txt").unlink()
    (sample_repo / "README.md").unlink()

    scan = scan_repository(sample_repo)
    assert all(dep.path != "requirements.txt" for dep in scan.dependency_files)
    assert all(doc.path != "README.md" for doc in scan.documents)


def test_max_commits_limit_respected(sample_repo: Path) -> None:
    assert len(read_commits(sample_repo, max_commits=2)) == 2


def test_not_a_repository_raises(tmp_path: Path) -> None:
    plain = tmp_path / "not-repo"
    plain.mkdir()
    with pytest.raises(NotARepositoryError):
        scan_repository(plain)


def test_repo_without_commits_raises(tmp_path: Path) -> None:
    empty = tmp_path / "bos-repo"
    empty.mkdir()
    import subprocess

    subprocess.run(["git", "-C", str(empty), "init", "-b", "main"], check=True, capture_output=True)

    with pytest.raises(RepositoryHasNoCommitsError):
        scan_repository(empty)


def test_nonexistent_path_raises(tmp_path: Path) -> None:
    with pytest.raises(ScannerError):
        scan_repository(tmp_path / "yok-boyle-bir-dizin")


def test_file_path_raises(tmp_path: Path) -> None:
    a_file = tmp_path / "dosya.txt"
    a_file.write_text("x", encoding="utf-8")
    with pytest.raises(ScannerError):
        scan_repository(a_file)
