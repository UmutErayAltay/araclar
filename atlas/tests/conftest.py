"""Gercek gecici git repolari kuran ortak yardimcilar. Hicbir mock yok."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Testlerde kullanilan sabit kimlik/tarih (deterministik last_commit_at icin).
GIT_ENV = {
    "GIT_AUTHOR_NAME": "atlas test",
    "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "atlas test",
    "GIT_COMMITTER_EMAIL": "test@example.invalid",
    "GIT_AUTHOR_DATE": "2024-01-02T03:04:05+00:00",
    "GIT_COMMITTER_DATE": "2024-01-02T03:04:05+00:00",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_TERMINAL_PROMPT": "0",
    "LC_ALL": "C",
}

GIT_IDENTITY = ["-c", "user.email=test@example.invalid", "-c", "user.name=atlas test"]


@pytest.fixture
def db_file(tmp_path: Path) -> Path:
    return tmp_path / "atlas-test.db"


def git(*args: str, cwd: Path | str | None = None, check: bool = True) -> str:
    env = dict(os.environ)
    env.update(GIT_ENV)
    proc = subprocess.run(
        ["git", *GIT_IDENTITY, *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        env=env,
    )
    if check and proc.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} basarisiz: {proc.stderr}")
    return proc.stdout


def make_repo(path: Path, *, commit: bool = True, filename: str = "README.md") -> Path:
    """Gercek git reposu kurar. `commit=True` ise tek commit atar."""
    path.mkdir(parents=True, exist_ok=True)
    git("init", "-q", "-b", "main", str(path))
    if commit:
        (path / filename).write_text("# test\n", encoding="utf-8")
        git("add", "-A", cwd=path)
        git("commit", "-q", "-m", "ilk commit", cwd=path)
    return path


def make_bare_remote(path: Path) -> Path:
    """Yerel bare repo (push hedefi)."""
    path.mkdir(parents=True, exist_ok=True)
    git("init", "-q", "--bare", "-b", "main", str(path))
    return path


def commit_file(repo: Path, name: str, content: str, message: str) -> None:
    (repo / name).parent.mkdir(parents=True, exist_ok=True)
    (repo / name).write_text(content, encoding="utf-8")
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", message, cwd=repo)


def rows_for(db_path: Path) -> dict[str, dict]:
    from atlas import db as db_mod

    conn = db_mod.connect(db_path)
    try:
        return {r["path"]: dict(r) for r in conn.execute("SELECT * FROM repos")}
    finally:
        conn.close()


def tree_hash(path: Path) -> str:
    """Dizindeki tum dosyalarin (yol+icerik) sha256 toplami."""
    digest = hashlib.sha256()
    for f in sorted(p for p in path.rglob("*") if p.is_file() and not p.is_symlink()):
        digest.update(str(f.relative_to(path)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(f.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def read_only_actor() -> None:
    """Yoksa testi atla: chmod sadece root disinda anlamli."""
    if os.geteuid() == 0:
        pytest.skip("root: chmod ile 'izin yok' durumu uretilemiyor")


def run_module_cli(*args: str, cwd: Path | str | None = None) -> subprocess.CompletedProcess:
    """`python3 -m atlas ...` komutunu GERCEKTEN subprocess olarak calistirir."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT)
    env.pop("ATLAS_DB", None)
    return subprocess.run(
        [sys.executable, "-m", "atlas", *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        env=env,
    )


# --------------------------------------------------------------------------
# Web paneli yardimcilari (Dalga C)
# --------------------------------------------------------------------------

#: Ekrana basilan HER metin maske testinde kontrol edilir; fixture metinleri
#: bilerek "sir" kalibi icerir ama parcalarindan kurulur (kaynakta literal yok).
def sahte_sir(n: int = 14) -> str:
    """Parcalardan kurulan sahte API anahtari (kaynakta tam literal YOK)."""
    return "sk-" + ("k" + "7") * n


def xss_yukle(deyim: str) -> str:
    """Guvenilmeyen veri gibi davranan fixture metni."""
    return f'"><{deyim}>'


@pytest.fixture
def web_app():
    """Bos bir DB ile panel uygulamasi (salt-okunur; fixture sonrasi kapanir)."""
    import tempfile
    from pathlib import Path as _Path

    from atlas.web import app_olustur

    dizin = tempfile.mkdtemp(prefix="atlas-web-")
    db_yolu = _Path(dizin) / "atlas.db"
    # Bos DB semasi: tablolar var, satır yok.
    from atlas import db as db_mod

    conn = db_mod.connect(db_yolu)
    conn.close()
    return app_olustur(db_yolu)


@pytest.fixture
def web_client(web_app):
    return web_app.test_client()


def db_doldur(
    db_path: Path,
    *,
    repos=(),
    findings=(),
    todos=(),
    readmes=(),
    summaries=(),
) -> Path:
    """Test DB'sine doğrudan (maskeli) satırlar yazar.

    Panelin okuduğu tabloyu doldurur; tarama ÇALIŞTIRMAZ (panel tarama
    tetiklemez — bu da testte kanıtlanır).
    """
    from atlas import db as db_mod

    conn = db_mod.connect(db_path)
    try:
        db_mod.upsert_repos(conn, list(repos))
        for f in findings:
            conn.execute(
                "INSERT INTO findings (repo, kind, severity, file, line, \"commit\", snippet_redacted) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    f["repo"], f["kind"], f.get("severity"), f.get("file"),
                    f.get("line"), f.get("commit"), f.get("snippet_redacted"),
                ),
            )
        for t in todos:
            conn.execute(
                "INSERT INTO todos (repo, file, line, text) VALUES (?, ?, ?, ?)",
                (t["repo"], t.get("file"), t.get("line"), t.get("text")),
            )
        for r in readmes:
            conn.execute(
                "INSERT OR REPLACE INTO readme_status "
                "(repo, readme_commit, behavior_commits_after, screenshot_age_days,"
                " readme_yolu, readme_commit_tarihi, skor, seviye, eksik_gorsel, neden, tarandi) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    r["repo"], r.get("readme_commit"), r.get("behavior_commits_after"),
                    r.get("screenshot_age_days"), r.get("readme_yolu"),
                    r.get("readme_commit_tarihi"), r.get("skor"), r.get("seviye"),
                    r.get("eksik_gorsel", 0), r.get("neden"), r.get("tarandi", 1),
                ),
            )
        for s in summaries:
            db_mod.replace_summary(
                conn, s["repo"], uretim=s.get("uretim", "2026-09-29T10:00:00+00:00"),
                kaynak=s.get("kaynak", "yerel"), model=s.get("model"),
                girdi_hash=s.get("girdi_hash", "kurgusal-hash"),
                metin=s["metin"],
            )
        conn.commit()
    finally:
        conn.close()
    return db_path
