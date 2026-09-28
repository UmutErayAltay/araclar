"""Testler için ortak fixture'lar: gerçek dosya sistemi, gerçek git."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    )
    return completed.stdout


def commit(repo: Path, filename: str, content: str, message: str, date: str) -> None:
    (repo / filename).write_text(content, encoding="utf-8")
    git(repo, "add", filename)
    env_date = f"{date}T12:00:00"
    git(repo, "commit", "-m", message, "--date", env_date)
    # Commit tarihini de sabitle (--date yalnızca author tarihini ayarlar).
    git(repo, "commit", "--amend", "--no-edit", "--date", env_date, "--reset-author")


@pytest.fixture
def sample_repo(tmp_path: Path) -> Path:
    """README, requirements.txt ve package.json içeren, birkaç commitli gerçek repo."""
    repo = tmp_path / "ornek-proje"
    repo.mkdir()

    git(repo, "init", "-b", "main")
    git(repo, "config", "user.name", "Test Kullanici")
    git(repo, "config", "user.email", "test@ornek.invalid")

    commit(repo, "README.md", "# Ornek Proje\n\nBir deneme projesi.\n", "ilk commit: README", "2024-01-10")
    commit(repo, "requirements.txt", "flask==3.0.0\n", "flask bagimliligi eklendi", "2024-02-05")
    commit(repo, "package.json", '{"name": "ornek", "devDependencies": {"jest": "^29.0.0"}}\n', "jest test runner eklendi", "2024-03-12")
    commit(repo, "app.py", "print('merhaba')\n", "ilk ozellik: selam verme", "2024-04-20")

    context = repo / ".context"
    context.mkdir()
    (context / "mimari.md").write_text("Mimari notlari burada.\n", encoding="utf-8")
    git(repo, "add", ".context/mimari.md")
    git(repo, "commit", "-m", "mimari dokumani eklendi", "--date", "2024-05-01T12:00:00")

    return repo
