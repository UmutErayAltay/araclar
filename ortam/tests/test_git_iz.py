"""git_iz: `.gitignore` kapsami ve `git ls-files` ile izlenen `.env`.

Gercek git YALniz `git_kur()` ile kurulan GECICI repolarda calisir; hicbir
test kullanicinin repolarina dokunmaz. Ag YOK.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from conftest import GIZLI_DEGER, git_ekle_ve_kaydet, git_kur, sahte_repo

from ortam import git_iz


def _git_var_mi() -> bool:
    return shutil.which("git") is not None


needs_git = pytest.mark.skipif(not _git_var_mi(), reason="bu makinede git yok")


# --------------------------------------------------------------------------
# .gitignore kapsami (git calismaz)
# --------------------------------------------------------------------------


def test_gitignore_env_kapsiyor(tmp_path):
    """`.gitignore` icinde `.env` kaliplari aranir."""
    repo = sahte_repo(tmp_path / "r", {".gitignore": "node_modules/\n.env\n"})
    assert git_iz.gitignore_env_kapsiyor_mi(repo)


def test_gitignore_yildizli_kalip(tmp_path):
    """`.env*` ve `*.env` kaliplari da kapsam sayilir."""
    assert git_iz.gitignore_env_kapsiyor_mi(sahte_repo(tmp_path / "a", {".gitignore": ".env*\n"}))
    assert git_iz.gitignore_env_kapsiyor_mi(sahte_repo(tmp_path / "b", {".gitignore": "*.env\n"}))


def test_gitignore_negatif_yorum(tmp_path):
    """`# .env` bir YORUM: kapsam degildir."""
    repo = sahte_repo(tmp_path / "r", {".gitignore": "# .env gizli dosya\n"})
    assert not git_iz.gitignore_env_kapsiyor_mi(repo)


def test_gitignore_negatif_ilgisiz_kurallar(tmp_path):
    """`.env` gecmeyen bir .gitignore kapsamaz."""
    repo = sahte_repo(tmp_path / "r", {".gitignore": "node_modules/\n*.log\n"})
    assert not git_iz.gitignore_env_kapsiyor_mi(repo)


def test_gitignore_negatif_dosya_yok(tmp_path):
    """.gitignore yoksa kapsam YOKTUR (bulgu uretir)."""
    assert not git_iz.gitignore_env_kapsiyor_mi(sahte_repo(tmp_path / "r"))


# --------------------------------------------------------------------------
# yerel .env dosyalari (git calismaz)
# --------------------------------------------------------------------------


def test_env_dosyasi_var_mi_gercek_ornek_ayrimi(tmp_path):
    """`.env`/`.env.local` sayilir; `.env.example` SAYILMAZ."""
    repo = sahte_repo(
        tmp_path / "r", {".env": "A=1\n", ".env.local": "B=2\n", ".env.example": "C=3\n"}
    )
    assert git_iz.env_dosyasi_var_mi(repo) == [".env", ".env.local"]


def test_env_dosyasi_negatif_yok(tmp_path):
    """Yerel `.env` yoksa liste BOSTUR."""
    assert git_iz.env_dosyasi_var_mi(sahte_repo(tmp_path / "r", {"a.py": "x=1\n"})) == []


def test_env_dosyasi_deger_okunmaz(tmp_path):
    """Yerel `.env` icerigi HIC okunmaz: yalniz yol doner."""
    repo = sahte_repo(tmp_path / "r", {".env": f"GIZLI={GIZLI_DEGER}\n"})
    sonuc = git_iz.env_dosyasi_var_mi(repo)
    assert sonuc == [".env"]
    assert GIZLI_DEGER not in repr(sonuc)


# --------------------------------------------------------------------------
# git ls-files
# --------------------------------------------------------------------------


@needs_git
def test_izlenen_env_dosyasi_bulunur(tmp_path):
    """Commit'lenmis gercek `.env` `git ls-files` icinde gorunur."""
    repo = git_kur(tmp_path / "r")
    (repo / ".env").write_text(f"A={GIZLI_DEGER}\n", encoding="utf-8")
    git_ekle_ve_kaydet(repo, ".env")
    assert git_iz.izlenen_env_dosyalari(repo) == [".env"]


@needs_git
def test_izlenen_env_negatif_ornek_dosya(tmp_path):
    """Commit'lenmis `.env.example` izlenen-ENV sayilmaz (sablon, sorun degil)."""
    repo = git_kur(tmp_path / "r")
    (repo / ".env.example").write_text("A=\n", encoding="utf-8")
    git_ekle_ve_kaydet(repo, ".env.example")
    assert git_iz.izlenen_env_dosyalari(repo) == []


@needs_git
def test_izlenen_env_negatif_commit_yok(tmp_path):
    """Commit'lenmemis `.env` izlenmiyordur: bulgu uretmez."""
    repo = git_kur(tmp_path / "r")
    (repo / ".env").write_text(f"A={GIZLI_DEGER}\n", encoding="utf-8")
    assert git_iz.izlenen_env_dosyalari(repo) == []


@needs_git
def test_izlenen_env_negatif_git_degil(tmp_path):
    """Git deposu olmayan dizinde `ls-files` calismaz: bulgu URETILMEZ (None -> [])."""
    repo = sahte_repo(tmp_path / "r", {".env": f"A={GIZLI_DEGER}\n"})
    assert git_iz.izlenen_env_dosyalari(repo) == []
