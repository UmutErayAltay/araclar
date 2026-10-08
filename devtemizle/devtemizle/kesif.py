"""Repo kesfi: ya verilen koklerden ya da atlas DB'sinden.

Yeni (v0.2):
- --derinlik N (varsayilan 3, en cok 8)
- --ev bayragi: ev dizininden derinlik 5 tarama; bazi dizinler hariç tutulur
- Repo meta: son commit tarihi (git log -1 --format=%ct, 5 sn timeout), kirli mi (git status --porcelain)
- git cagrilari 5 sn timeout, git yoksa sessiz geri donus
- .git icine girilmez; baglanti izlenmez

Guvenlik: atlas DB'si `mode=ro` ile acilir (yazmaz, sema kurmaz).
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from .tara import _baglanti


#: Bu dizinlerin ICINE girilmez (repo govdesi, derleme ciktilari).
SKIP_DIRS = frozenset({".git", "node_modules", ".venv", "venv", "__pycache__"})

#: --ev icin hariç tutulacak dizinler (ev altindaki bu isimlerde girilmez)
#: PLAN.md §3: AppData, Library, .cache, .local, .npm, .cargo, .rustup, .gradle,
#: OneDrive*, $Recycle.Bin, node_modules (repo degil), gizli dizinler (git hariç)
_EV_HARIC = frozenset({
    "AppData", "Library", ".cache", ".local", ".npm", ".cargo", ".rustup",
    ".gradle", "$Recycle.Bin", "node_modules",
})

#: Varsayilan derinlik (--root icin)
DERINLIK = 3
#: Maksimum derinlik
MAX_DERINLIK = 8
#: --ev icin derinlik
EV_DERINLIK = 5
#: git komutu timeout (saniye)
GIT_TIMEOUT = 5


class KesifHatasi(RuntimeError):
    """Repo listesi bulunamadi (kullanim/kesif hatasi)."""


@dataclass(frozen=True)
class RepoMeta:
    """Repo icin ek meta bilgiler (rapor + panel icin)."""
    yol: Path
    son_commit: int | None      # Unix timestamp (git log -1 --format=%ct), yoksa None
    kirli: bool                 # git status --porcelain bos degil mi
    aday_boyut: int = 0         # Tara.py sonrasinda doldurulur


def _atlas_db(yol: Path | None = None) -> Path:
    """Arguman > ATLAS_DB > ~/.atlas/atlas.db."""
    if yol is not None:
        return yol.expanduser()
    env = os.environ.get("ATLAS_DB")
    return Path(env).expanduser() if env else Path.home() / ".atlas" / "atlas.db"


def _git_var_mi() -> bool:
    """git komutu PATH'te var mi?"""
    return shutil.which("git") is not None


def _git_calistir(args: list[str], cwd: Path, timeout: int = GIT_TIMEOUT) -> tuple[bool, str]:
    """git komutunu calistirir; (basarili_mi, stdout). Hata/timeout -> (False, '')."""
    if not _git_var_mi():
        return False, ""
    try:
        sonuc = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
        return sonuc.returncode == 0, sonuc.stdout.strip()
    except (subprocess.TimeoutExpired, OSError, subprocess.SubprocessError):
        return False, ""


def _repo_meta_al(repo: Path) -> RepoMeta:
    """Reponun son commit tarihi ve kirli durumunu alir (git yoksa sessiz None/False)."""
    son_commit: int | None = None
    kirli = False

    # son commit tarihi: once git log, yoksa .git/HEAD mtime
    basarili, cikti = _git_calistir(["log", "-1", "--format=%ct"], repo)
    if basarili and cikti.isdigit():
        son_commit = int(cikti)
    else:
        # git yoksa/calismadiysa .git/HEAD dosyasinin mtime'ini kullan
        try:
            head_path = repo / ".git" / "HEAD"
            if head_path.exists():
                son_commit = int(head_path.stat().st_mtime)
        except OSError:
            pass

    # kirli mi? git status --porcelain
    basarili, cikti = _git_calistir(["status", "--porcelain"], repo)
    if basarili:
        kirli = bool(cikti.strip())

    return RepoMeta(yol=repo, son_commit=son_commit, kirli=kirli)


def _yuruyerek(kok: Path, derinlik: int = DERINLIK) -> list[Path]:
    """Kokun altindaki repolari bulur; repo icine girmez, link izlemez.

    derinlik: kok + N alt dizin (varsayilan 3, en cok 8).
    """
    if derinlik < 0:
        derinlik = 0
    if derinlik > MAX_DERINLIK:
        derinlik = MAX_DERINLIK

    bulunan: list[Path] = []
    for mevcut, dizinler, _dosyalar in os.walk(
        kok, topdown=True, followlinks=False, onerror=lambda _e: None
    ):
        mevcut_path = Path(mevcut)
        dizinler[:] = sorted(
            d for d in dizinler if d not in SKIP_DIRS and not _baglanti(mevcut_path / d)
        )
        yol = mevcut_path
        # .git dizin VEYA dosya olabilir (worktree/alt modulde dosyadadir).
        if (yol / ".git").exists():
            bulunan.append(yol)
            dizinler[:] = []  # repo icine inme
            continue
        if len(yol.relative_to(kok).parts) >= derinlik:
            dizinler[:] = []  # derinlik siniri
    return bulunan


def _ev_tara() -> list[Path]:
    """Ev dizinini tarar (derinlik 5); PLAN.md §3 hariç tutma listesi uygulanir."""
    ev = Path.home()
    bulunan: list[Path] = []
    for mevcut, dizinler, _dosyalar in os.walk(
        ev, topdown=True, followlinks=False, onerror=lambda _e: None
    ):
        mevcut_path = Path(mevcut)
        # Hariç tutma: isim tam eslesme veya baslangic (OneDrive*)
        dizinler[:] = sorted(
            d for d in dizinler
            if d not in _EV_HARIC
            and not d.startswith("OneDrive")
            and not (d.startswith(".") and d != ".git")
            and not _baglanti(mevcut_path / d)
        )
        yol = mevcut_path
        if (yol / ".git").exists():
            bulunan.append(yol)
            dizinler[:] = []  # repo icine inme
            continue
        if len(yol.relative_to(ev).parts) >= EV_DERINLIK:
            dizinler[:] = []  # derinlik siniri (5)
    return bulunan


def _atlastan(yol: Path) -> list[Path]:
    if not yol.is_file():
        raise KesifHatasi(
            f"atlas veritabani bulunamadi: {yol} -> "
            "gezinilecek yollari `--root` ile verin veya once `atlas tara` calistirin."
        )
    try:
        # mode=ro: yazmaz, sema kurmaz.
        conn = sqlite3.connect(f"file:{yol.as_posix()}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        raise KesifHatasi(
            f"atlas veritabani acilamadi: {yol} ({exc}) -> "
            "`--root` ile yol verin veya once `atlas tara` calistirin."
        ) from exc
    try:
        satirlar = conn.execute("SELECT path FROM repos ORDER BY path").fetchall()
    except sqlite3.Error as exc:
        raise KesifHatasi(
            f"atlas veritabani okunamadi: {yol} ({exc}) -> "
            "`--root` ile yol verin veya once `atlas tara` calistirin."
        ) from exc
    finally:
        conn.close()
    return [Path(satir[0]) for satir in satirlar if Path(satir[0]).exists()]


def repo_listesi(
    roots: list[Path] | None,
    atlas_db: Path | None = None,
    derinlik: int = DERINLIK,
    ev: bool = False,
) -> list[Path]:
    """Temizlenecek repolari dondurur.

    Parametreler:
    - roots: --root ile verilen kokler (birden fazla olabilir)
    - atlas_db: atlas veritabani yolu (None -> env/varsayilan)
    - derinlik: --root icin derinlik (varsayilan 3, max 8)
    - ev: --ev bayragi (ev dizinini tarar, derinlik 5)
    """
    repolar: list[Path] = []

    if roots:
        for kok in roots:
            kok = Path(kok).expanduser()
            if not kok.exists():
                raise KesifHatasi(f"verilen yol bulunamadi: {kok}")
            repolar.extend(_yuruyerek(kok, derinlik) if kok.is_dir() else [kok])
    elif ev:
        repolar.extend(_ev_tara())
    else:
        repolar = _atlastan(_atlas_db(atlas_db))

    # Ayni repo birden fazla kok altinda sayilmis olabilir.
    repolar = list(dict.fromkeys(repolar))

    if not repolar:
        raise KesifHatasi("temizlenecek repo bulunamadi")

    return repolar


def repo_meta_listesi(repolar: list[Path]) -> list[RepoMeta]:
    """Repo listesi icin meta bilgileri toplar."""
    return [_repo_meta_al(r) for r in repolar]