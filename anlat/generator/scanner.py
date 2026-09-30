"""Bir git deposunu tarayıp anlatı üretimi için ham sinyal toplar.

Burada LLM yoktur; sadece gerçek `subprocess.run(["git", ...])` çağrılarıyla
toplanan, nedensellikten yoksun veri üretilir. Tüm hatalar açıkça yükselir:
git yoksa, depo değilse ya da commit yoksa sessizce boş sonuç dönülmez.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

DEPENDENCY_FILES = (
    "package.json",
    "requirements.txt",
    "pyproject.toml",
    "Cargo.toml",
    "go.mod",
)

MAX_COMMITS = 150
MAX_DEP_REVISIONS = 20
MAX_DEP_CHARS = 8_000
MAX_DOC_CHARS = 6_000

# Commit satırı ayrımı: konu satırında "|" geçse bile alanlar bozulmasın diye
# görünmez ayraç (ASCII 0x1f) kullanılır.
_LOG_FORMAT = "%h%x1f%ad%x1f%s"
_FIELD_SEP = "\x1f"


class ScannerError(RuntimeError):
    """Depoyu tararken çıkan genel hata."""


class GitNotAvailableError(ScannerError):
    """`git` çalıştırılabilir dosyası sistemde bulunamadı."""


class NotARepositoryError(ScannerError):
    """Verilen yol bir git deposu değil."""


class RepositoryHasNoCommitsError(ScannerError):
    """Depo geçerli ama henüz hiç commit yok."""


@dataclass
class Commit:
    short_hash: str
    date: str
    subject: str


@dataclass
class DependencyFile:
    """Bir bağımlılık manifestinin geçmişinden çıkarılan, kırpılmış diff."""

    path: str
    history: str
    truncated: bool


@dataclass
class Document:
    """README/CLAUDE.md/.context altındaki anlatı kaynakları."""

    path: str
    content: str
    truncated: bool


@dataclass
class RepoScan:
    repo_path: Path
    repo_name: str
    commits: list[Commit] = field(default_factory=list)
    dependency_files: list[DependencyFile] = field(default_factory=list)
    documents: list[Document] = field(default_factory=list)

    @property
    def oldest_commit(self) -> Commit | None:
        return self.commits[0] if self.commits else None

    @property
    def newest_commit(self) -> Commit | None:
        return self.commits[-1] if self.commits else None


def _run_git(repo_path: Path, *args: str, timeout: int = 60) -> str:
    """git komutunu çalıştırır, stdout döndürür. Hata durumunda yükselir."""
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_path), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise GitNotAvailableError(
            "`git` komutu bulunamadı. git kurulu olmadan depo taranamaz."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise ScannerError(
            f"git {' '.join(args)} zaman aşımına uğradı ({timeout}s)."
        ) from exc

    if completed.returncode != 0:
        detail = completed.stderr.strip() or "bilinmeyen hata"
        raise ScannerError(
            f"git {' '.join(args)} başarısız (çıkış kodu {completed.returncode}): {detail}"
        )
    return completed.stdout


def _truncate(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit], True


def _assert_repository(repo_path: Path) -> None:
    if not repo_path.exists():
        raise ScannerError(f"Depo yolu bulunamadı: {repo_path}")
    if not repo_path.is_dir():
        raise NotARepositoryError(f"Depo yolu bir dizin değil: {repo_path}")
    try:
        _run_git(repo_path, "rev-parse", "--git-dir")
    except ScannerError as exc:
        raise NotARepositoryError(f"{repo_path} bir git deposu değil.") from exc
    try:
        _run_git(repo_path, "rev-parse", "--verify", "HEAD")
    except ScannerError as exc:
        raise RepositoryHasNoCommitsError(
            f"{repo_path} deposunda henüz hiç commit yok."
        ) from exc


def read_commits(
    repo_path: Path, max_commits: int = MAX_COMMITS
) -> list[Commit]:
    """Commit özetlerini kronolojik (eskiden yeniye) sırayla döndürür."""
    output = _run_git(
        repo_path, "log", f"--max-count={max_commits}", f"--pretty=format:{_LOG_FORMAT}", "--date=short"
    )
    commits: list[Commit] = []
    for line in output.splitlines():
        parts = line.split(_FIELD_SEP)
        if len(parts) != 3:
            continue
        short_hash, date, subject = parts
        commits.append(Commit(short_hash=short_hash, date=date, subject=subject))
    # `git log` en yeniyi önce verir; anlatının zaman çizelgesi eskiden yeniye olmalı.
    commits.reverse()
    return commits


def read_dependency_history(
    repo_path: Path,
    dependency_files: tuple[str, ...] = DEPENDENCY_FILES,
    max_revisions: int = MAX_DEP_REVISIONS,
    max_chars: int = MAX_DEP_CHARS,
) -> list[DependencyFile]:
    """Bulunan bağımlılık dosyalarının diff geçmişini kırpılmış olarak toplar."""
    found: list[DependencyFile] = []
    for name in dependency_files:
        if not (repo_path / name).is_file():
            continue
        history = _run_git(
            repo_path, "log", "-p", f"--max-count={max_revisions}", "--", name
        )
        trimmed, truncated = _truncate(history, max_chars)
        found.append(DependencyFile(path=name, history=trimmed, truncated=truncated))
    return found


def read_documents(
    repo_path: Path, max_chars: int = MAX_DOC_CHARS
) -> list[Document]:
    """README.md, CLAUDE.md ve .context/ altındaki markdown dosyalarını okur."""
    candidates: list[Path] = []
    for name in ("README.md", "CLAUDE.md"):
        path = repo_path / name
        if path.is_file():
            candidates.append(path)
    context_dir = repo_path / ".context"
    if context_dir.is_dir():
        candidates.extend(sorted(p for p in context_dir.rglob("*.md") if p.is_file()))

    documents: list[Document] = []
    for path in candidates:
        content = path.read_text(encoding="utf-8", errors="replace")
        trimmed, truncated = _truncate(content, max_chars)
        documents.append(
            Document(
                path=path.relative_to(repo_path).as_posix(),
                content=trimmed,
                truncated=truncated,
            )
        )
    return documents


def scan_repository(
    repo_path: str | Path,
    max_commits: int = MAX_COMMITS,
    max_dep_revisions: int = MAX_DEP_REVISIONS,
    max_dep_chars: int = MAX_DEP_CHARS,
    max_doc_chars: int = MAX_DOC_CHARS,
) -> RepoScan:
    """Depoyu doğrular ve tüm ham sinyalleri tek bir RepoScan'de toplar."""
    path = Path(repo_path).expanduser().resolve()
    _assert_repository(path)
    return RepoScan(
        repo_path=path,
        repo_name=path.name,
        commits=read_commits(path, max_commits=max_commits),
        dependency_files=read_dependency_history(
            path, max_revisions=max_dep_revisions, max_chars=max_dep_chars
        ),
        documents=read_documents(path, max_chars=max_doc_chars),
    )
