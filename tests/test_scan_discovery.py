"""Repo kesfi: derinlik, atlama dizinleri, ic ice repo, sembolik link dongusu."""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.scan import SKIP_DIRS, find_repo_paths, find_repos, is_repo
from conftest import make_repo


def test_git_dosyasi_olan_dizin_repo_sayilir(tmp_path: Path):
    """git worktree / submodule icin .git bir dosyadır."""
    repo = tmp_path / "worktree"
    repo.mkdir()
    (repo / ".git").write_text("gitdir: /tmp/bir-yer\n", encoding="utf-8")
    assert is_repo(repo)
    assert [p.name for p in find_repos(tmp_path, depth=3)] == ["worktree"]


def test_git_disi_dizin_repo_sayilmaz(tmp_path: Path):
    (tmp_path / "duz").mkdir()
    (tmp_path / "duz" / "okubeni.md").write_text("x", encoding="utf-8")
    assert find_repos(tmp_path, depth=3) == []


def test_derinlik_siniri(tmp_path: Path):
    make_repo(tmp_path / "seviye1" / "seviye2" / "seviye3" / "repo")
    # kok=tmp; seviye1=1, seviye2=2, seviye3=3, repo=4
    assert find_repos(tmp_path, depth=3) == []
    assert [p.name for p in find_repos(tmp_path, depth=4)] == ["repo"]


def test_derinlik_bir(tmp_path: Path):
    make_repo(tmp_path / "a" / "repo")
    assert find_repos(tmp_path, depth=1) == []
    assert [p.name for p in find_repos(tmp_path, depth=2)] == ["repo"]


def test_derinlik_sifir_yalniz_kok(tmp_path: Path):
    make_repo(tmp_path)
    make_repo(tmp_path / "alt")
    assert [p.name for p in find_repos(tmp_path, depth=0)] == [tmp_path.name]


def test_repo_icerine_inilmez_ic_ice_repo_sayilmaz(tmp_path: Path):
    dis = make_repo(tmp_path / "dis")
    make_repo(dis / "ic" / "gizli")
    assert [p.name for p in find_repos(tmp_path, depth=5)] == ["dis"]


def test_node_modules_ici_repo_atlanir(tmp_path: Path):
    (tmp_path / "uygulama").mkdir()
    make_repo(tmp_path / "uygulama" / "node_modules" / "paket")
    make_repo(tmp_path / "uygulama" / "kaynak")
    bulunan = [p.name for p in find_repos(tmp_path, depth=5)]
    assert "paket" not in bulunan
    assert "kaynak" in bulunan


def test_atlanan_dizinler_tek_tek(tmp_path: Path):
    for ad in sorted(SKIP_DIRS - {".git"}):
        make_repo(tmp_path / ad / "repo")
        assert find_repos(tmp_path, depth=4) == [], f"{ad} atlanmadi"


def test_git_dizini_gezdirilmez(tmp_path: Path):
    """Kok dizinin kendisi .git iceriyorsa o bir repodur, ve icine girilmez."""
    (tmp_path / ".git").mkdir()
    make_repo(tmp_path / "alt")
    assert [p.name for p in find_repos(tmp_path, depth=3)] == [tmp_path.name]


def test_cok_derin_agac_sinirla_kalir(tmp_path: Path):
    make_repo(tmp_path / "a" / "b" / "c" / "d" / "cok-derin")
    assert find_repos(tmp_path, depth=3) == []


def test_sembolik_link_dongusu_cozulmez(tmp_path: Path):
    """Koke geri donen sembolik link sonsuz dongu yaratmamali."""
    kok = tmp_path / "kok"
    kok.mkdir()
    make_repo(kok / "repo")
    (kok / "geri").symlink_to(kok, target_is_directory=True)
    assert [p.name for p in find_repos(kok, depth=4)] == ["repo"]


def test_sembolik_link_uzerindeki_repo_girilmez(tmp_path: Path):
    gercek = tmp_path / "gercek"
    gercek.mkdir()
    make_repo(gercek / "repo")
    linkli = tmp_path / "linkli"
    linkli.mkdir()
    (linkli / "bag").symlink_to(gercek, target_is_directory=True)
    assert find_repos(linkli, depth=3) == []


def test_birden_fazla_kok(tmp_path: Path):
    a, b = tmp_path / "a", tmp_path / "b"
    make_repo(a / "bir")
    make_repo(b / "iki")
    yollar = find_repo_paths([a, b])
    assert sorted(p.name for p in yollar) == ["bir", "iki"]


def test_var_olmayan_kok_yok_sayilir(tmp_path: Path):
    assert find_repo_paths([tmp_path / "yok"]) == []


def test_kok_dosya_olarak_verilirse_yok_sayilir(tmp_path: Path):
    (tmp_path / "dosya.txt").write_text("x", encoding="utf-8")
    make_repo(tmp_path / "repo")
    yollar = find_repo_paths([tmp_path, tmp_path / "dosya.txt"])
    assert [p.name for p in yollar] == ["repo"]


def test_ayni_repo_iki_kokta_tekil_olmaz(tmp_path: Path):
    ust = tmp_path / "ust"
    make_repo(ust / "repo")
    yollar = find_repo_paths([tmp_path, ust])
    assert [str(p) for p in yollar].count(str(ust / "repo")) == 1
