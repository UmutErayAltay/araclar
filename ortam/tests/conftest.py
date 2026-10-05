"""ortam testleri icin ortak yardimcilar. Hicbir mock kutuphanesi yok.

Ag YOK. Gercek disk YALNIZCA gecici dizinlerde (tmp_path) kullanilir; hicbir
test kullanicinin ~/klasorunu okumaz veya yazmaz.

DEGER KURALI: testlerde uretilen `DEGER` dizeleri (`GIZLI_DEGER_...`) sentinel
gibi kullanilir; hicbir cikti/test mesajinda gormemelidirler.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Testlerde `.env` icine yazilan GERCEK BIR DEGER gibi davranan sentinel.
#: Yakalanmamasi gereken tek dizedir (cikti, JSON, hata mesaji).
GIZLI_DEGER = "GIZLI_DEGER_0123456789_ABCDEFGHIJKL"


def sahte_repo(yol: Path, dosyalar: dict[str, str] | None = None) -> Path:
    """Gecici bir repo kurar.

    Gercek git komutu CALISTIRILMAZ: `.git` isaret dizini yeter. Boylece hicbir
    test gizli `.env` dosyasini gercek bir index'e yazmaz.
    """
    yol.mkdir(parents=True, exist_ok=True)
    (yol / ".git").mkdir(exist_ok=True)
    for ad, icerik in (dosyalar or {}).items():
        hedef = yol / ad
        hedef.parent.mkdir(parents=True, exist_ok=True)
        hedef.write_text(icerik, encoding="utf-8")
    return yol


def git_kur(yol: Path) -> Path:
    """GECERLI ama bos bir git deposu kurar (yalniz `env_izleniyor` testleri icin).

    Bu testler `git ls-files` ciktisina ihtiyac duyar; sahte `.git` dizini
    yetmez. `commit.gpgsign` kapali: testler imzaya takilip gecmesin.
    """
    yol.mkdir(parents=True, exist_ok=True)
    komutlar = (
        ["init", "-q", "-b", "main", "."],
        ["config", "user.email", "test@example.com"],
        ["config", "user.name", "Test"],
        ["config", "commit.gpgsign", "false"],
    )
    for args in komutlar:
        subprocess.run(
            ["git", "-C", str(yol), *args],
            capture_output=True,
            check=True,
            timeout=60,
        )
    return yol


def git_ekle_ve_kaydet(repo: Path, *dosyalar: str) -> None:
    """Verilen dosyalari `git add` edip commit'ler (izlenen dosya testleri icin)."""
    subprocess.run(
        ["git", "-C", str(repo), "add", "--", *dosyalar],
        capture_output=True,
        check=True,
        timeout=60,
    )
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "test"],
        capture_output=True,
        check=True,
        timeout=60,
    )


def tree_hash(yol: Path) -> str:
    """Dizindeki tum dosyalarin (yol+icerik) sha256 toplami: etkiyi olcer."""
    ozet = hashlib.sha256()
    for f in sorted(p for p in yol.rglob("*") if p.is_file() and not p.is_symlink()):
        ozet.update(str(f.relative_to(yol)).encode("utf-8"))
        ozet.update(b"\0")
        ozet.update(f.read_bytes())
        ozet.update(b"\0")
    return ozet.hexdigest()


def run_module_cli(*args: str, cwd: Path | str | None = None):
    """`python -m ortam ...` komutunu GERCEKTEN subprocess olarak calistirir.

    HOME geciciye cevrilir: bu aracin zaten HIC dosya yazmaz, ama alt surec
    yine de dis dunyaya hic dokunmasin diye ayrilir.
    """
    temel = cwd if isinstance(cwd, Path) else (Path(cwd) if cwd else REPO_ROOT)
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT)
    env["HOME"] = env["USERPROFILE"] = str(temel)
    return subprocess.run(
        [sys.executable, "-m", "ortam", *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        env=env,
    )


def turler(veri: dict) -> set[str]:
    """Analiz ciktisindaki bulgu TURLERI kumesi."""
    return {b["tur"] for b in veri["bulgular"]}


def adlar(veri: dict, tur: str) -> set[str]:
    """Verilen turdaki bulgularin AD kumesi (`detay` satiri olanlar haric)."""
    return {b["ad"] for b in veri["bulgular"] if b["tur"] == tur and b.get("ad")}


@pytest.fixture
def ev_isole(tmp_path: Path, monkeypatch) -> Path:
    """HOME/USERPROFILE'u gecici dizine cevirir."""
    ev = tmp_path / "ev"
    ev.mkdir()
    for ad in ("HOME", "USERPROFILE"):
        monkeypatch.setenv(ad, str(ev))
    return ev
