"""kesif: koklerin altindaki git repolarini bulma, KesifHatasi yollari.

Gercek git CALISTIRILMAZ: kesif yalnizca `.git` varligina bakar; tum dizin
agaci tmp_path altinda kurulur.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import sahte_repo

from ortam.kesif import KesifHatasi, repo_listesi


def test_kok_alti_tum_repolar_bulunur(tmp_path):
    """.git isaretli dizinler repo sayilir; kokun altindaki hepsi listelenir."""
    kok = tmp_path / "projeler"
    sahte_repo(kok / "a")
    sahte_repo(kok / "b")
    assert sorted(p.name for p in repo_listesi([kok])) == ["a", "b"]


def test_git_dosya_olarak_isaretli(tmp_path):
    """`.git` bir DIZIN olmak zorunda degil: worktree'de dosyadadir, yine bulunur."""
    kok = tmp_path / "projeler"
    worktree = kok / "wt"
    worktree.mkdir(parents=True)
    (worktree / ".git").write_text("gitdir: ../../.git/modules/x\n", encoding="utf-8")
    assert repo_listesi([kok]) == [worktree]


def test_repo_icine_girilmez(tmp_path):
    """Ic ice repolar bulunur; dis repo, ic repo icin tek sayilir."""
    kok = tmp_path / "projeler"
    dis = sahte_repo(kok / "dis")
    sahte_repo(dis / "vendor" / "ic-repo")
    assert repo_listesi([kok]) == [dis]


def test_atlanan_dizinlere_girilmez(tmp_path):
    """node_modules/.venv/.git icindeki `.git` isaretli dizin gorulmez."""
    kok = tmp_path / "projeler"
    sahte_repo(kok / "node_modules" / "paket-repo")
    sahte_repo(kok / "gercek")
    assert repo_listesi([kok]) == [kok / "gercek"]


def test_derinlik_siniri(tmp_path):
    """Kesif yalnizca kok + 3 seviyeye kadar iner; daha derin gorulmez."""
    kok = tmp_path / "projeler"
    sahte_repo(kok / "a" / "b" / "c")
    assert (kok / "a" / "b" / "c") in repo_listesi([kok])
    sahte_repo(kok / "a" / "b" / "c" / "d" / "e" / "f")
    assert kok / "a" / "b" / "c" / "d" not in repo_listesi([kok])


def test_ayni_repo_tekrarlanmaz(tmp_path):
    """Ayni repo birden fazla kok altinda sayilmissa bir kez doner."""
    kok = tmp_path / "projeler"
    a = sahte_repo(kok / "a" / "repo")
    b = sahte_repo(kok / "b")
    sonuc = repo_listesi([kok, a, b])
    assert sonuc.count(a) == 1 and sorted(p.name for p in sonuc) == ["b", "repo"]


def test_bos_kok_kesif_hatasi(tmp_path):
    """Repo icermeyen bos kok: KesifHatasi ('denetlenecek repo bulunamadi')."""
    kok = tmp_path / "bos"
    kok.mkdir()
    with pytest.raises(KesifHatasi, match="denetlenecek repo bulunamadi"):
        repo_listesi([kok])


def test_olmayan_kok_kesif_hatasi(tmp_path):
    """Var olmayan yol: KesifHatasi 'bulunamadi' (CLI bunu cikis 2'ye cevirir)."""
    with pytest.raises(KesifHatasi, match="bulunamadi"):
        repo_listesi([tmp_path / "yok"])


def test_dogrudan_repo_yolu(tmp_path):
    """--kok ile bir repo dizininin KENDISI verilebilir; listeye girer."""
    repo = sahte_repo(tmp_path / "tek")
    assert repo_listesi([repo]) == [repo]
