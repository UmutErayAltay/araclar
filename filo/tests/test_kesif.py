"""Repo kesfi kurallari: derinlik 1-2, atlanan dizinler, tekillestirme.

Gercek git CALISTIRILMAZ: `.git` isaret dizini yeter. Hepsi tmp_path altinda.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import sahte_repo
from filo.kesif import DERINLIK, KesifHatasi, repo_listesi


def test_kok_altindaki_derinlik_1_ve_2_bulunur(tmp_path):
    """Kok + 1 ve kok + 2 altindaki repolar bulunur; derinlik 3 bulunmaz."""
    kok = tmp_path / "projeler"
    kok.mkdir()
    sahte_repo(kok / "seviye1")
    sahte_repo(kok / "grup" / "seviye2")
    sahte_repo(kok / "grup" / "alt" / "seviye3")  # 2'den derin: bulunmamali
    bulunan = repo_listesi(None, [kok])
    adlar = {p.name for p in bulunan}
    assert adlar == {"seviye1", "seviye2"}
    assert "seviye3" not in adlar
    assert DERINLIK == 2


def test_derinlik_2_deki_repo_gecici_dizine_girmez(tmp_path):
    """Bir repo bulundugunda icine girilmez: icindeki repo listelenmez."""
    kok = tmp_path / "projeler"
    dis = sahte_repo(kok / "dis")
    sahte_repo(dis / "ic" / "repo")  # dis repo'nun icinde: sayilmamali
    bulunan = repo_listesi(None, [kok])
    assert bulunan == [dis]


def test_node_modules_ve_sanal_ortam_atlanir(tmp_path):
    """node_modules/.venv/__pycache__ icindeki .git YOK sayilir."""
    kok = tmp_path / "projeler"
    kok.mkdir()
    sahte_repo(kok / "gercek")
    sahte_repo(kok / "node_modules" / "sahte")
    sahte_repo(kok / "proje" / ".venv" / "sahte")
    sahte_repo(kok / "proje" / "__pycache__" / "sahte")
    adlar = {p.name for p in repo_listesi(None, [kok])}
    assert adlar == {"gercek"}


def test_git_dosya_olunan_repo_da_bulunur(tmp_path):
    """`.git` dizin yerine DOSYA ise (worktree/alt modul) yine repo sayilir."""
    kok = tmp_path / "projeler"
    kok.mkdir()
    repo = kok / "worktree"
    repo.mkdir()
    (repo / ".git").write_text("gitdir: /bir/yer\n", encoding="utf-8")
    assert repo_listesi(None, [kok]) == [repo]


def test_ayni_repo_iki_kokta_tekillestirilir(tmp_path):
    """Ayni repo iki kok altinda sayilirsa listede BIR kez olur."""
    kok = tmp_path / "projeler"
    sahte_repo(kok / "a" / "r")
    sahte_repo(kok / "b")
    repolar = repo_listesi(None, [kok, kok])
    assert len(repolar) == len(set(map(str, repolar)))


def test_repo_listesi_tekillestirir_ve_sira_korur(tmp_path):
    """Giris sirasi korunur (paralellik ciktinin sirasini bozmamali)."""
    kok = tmp_path / "projeler"
    kok.mkdir()
    for ad in ("c", "a", "b"):
        sahte_repo(kok / ad)
    repolar = repo_listesi(None, [kok])
    adlar = {p.name for p in repolar}
    assert adlar == {"a", "b", "c"}
    tek = repo_listesi(repolar, None)
    assert [str(p) for p in tek] == [str(p) for p in repolar]


# --------------------------------------------------------------------------
# negatif: hata durumlari
# --------------------------------------------------------------------------


def test_hicbir_secim_yoksa_hata():
    """Ne --repo ne --kok: KesifHatasi (CLI cikis 2)."""
    with pytest.raises(KesifHatasi, match="--repo"):
        repo_listesi(None, None)


def test_yok_kok_hata():
    """Var olmayan kok yolu -> KesifHatasi."""
    with pytest.raises(KesifHatasi, match="bulunamadi"):
        repo_listesi(None, [Path("/yok/boyle/bir/kok")])


def test_yok_repo_hata():
    """Var olmayan --repo yolu -> KesifHatasi."""
    with pytest.raises(KesifHatasi, match="bulunamadi"):
        repo_listesi([Path("/yok/boyle/bir/repo")], None)


def test_dosya_olan_kok_hata(tmp_path):
    """Kok bir dosyaya isaret ediyorsa (dizin degil) -> KesifHatasi."""
    dosya = tmp_path / "not.txt"
    dosya.write_text("x\n", encoding="utf-8")
    with pytest.raises(KesifHatasi, match="dizin degil"):
        repo_listesi(None, [dosya])


def test_repo_dizini_olmayan_yol_hata(tmp_path):
    """--repo bir dosyaya isaret ediyorsa -> KesifHatasi."""
    dosya = tmp_path / "not.txt"
    dosya.write_text("x\n", encoding="utf-8")
    with pytest.raises(KesifHatasi, match="dizin degil"):
        repo_listesi([dosya], None)