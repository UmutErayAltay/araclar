"""kesif: kok altindaki repo bulma, derinlik/atlanan dizin kurallari, okunabilirlik.

Gercek git CALISTIRILMAZ; `.git` isaret dizini yeter.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import sahte_repo

from iddia.kesif import KesifHatasi, okunabilir, repo_listesi


# --------------------------------------------------------------------------
# repo bulma
# --------------------------------------------------------------------------


def test_kok_altindaki_repo_bulunur(tmp_path):
    """Kokun altindaki .git'li dizin repo sayilir."""
    kok = tmp_path / "projeler"
    repo = sahte_repo(kok / "harita")
    assert repo_listesi([kok]) == [repo]


def test_birden_fazla_kok_tekrar_saymaz(tmp_path):
    """Ayni repo iki kok altinda da olsa TEK kez listelenir."""
    kok = tmp_path / "a"
    repo = sahte_repo(kok / "r")
    assert repo_listesi([kok, kok]) == [repo]
    assert repo_listesi([kok, kok.parent]) == [repo]


def test_ic_ice_repo_tekrar_sayilmaz(tmp_path):
    """Bir repo bulunduktan sonra icine girilmez: alt repo AYRI sayilmaz."""
    kok = tmp_path / "projeler"
    dis = sahte_repo(kok / "dis")
    sahte_repo(dis / "vendor" / "ic")
    assert repo_listesi([kok]) == [dis]


def test_derinlik_siniri(tmp_path):
    """Derinlik 3'ten derindeki repo bulunmaz (bos sonuc kesif hatasi verir)."""
    kok = tmp_path / "projeler"
    sahte_repo(kok / "a" / "b" / "c" / "d")
    with pytest.raises(KesifHatasi):
        repo_listesi([kok])


def test_derinlik_uc_aktar(tmp_path):
    """Derinlik tam 3 olan repo yine bulunur (kok + 3 alt dizin)."""
    kok = tmp_path / "projeler"
    repo = sahte_repo(kok / "a" / "b" / "c")
    assert repo_listesi([kok]) == [repo]


def test_atlanan_dizinlere_girilmez(tmp_path):
    """node_modules/.venv/dist gibi dizinlerin ICINDEKI repo bulunmaz."""
    kok = tmp_path / "projeler"
    for ad in ("node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".pytest_cache"):
        sahte_repo(kok / ad / "gizli")
    with pytest.raises(KesifHatasi):
        repo_listesi([kok])


def test_git_dosya_olan_repo_bulunur(tmp_path):
    """.git dizin yerine DOSYA ise de repo sayilir (worktree/alt modul)."""
    kok = tmp_path / "projeler"
    repo = kok / "wt"
    repo.mkdir(parents=True)
    (repo / ".git").write_text("gitdir: /tmp/baska\n", encoding="utf-8")
    assert repo_listesi([kok]) == [repo]


def test_repo_olmayan_kok_hata(tmp_path):
    """.git icermeyen kok hata verir (bulgu yok sayilmaz)."""
    with pytest.raises(KesifHatasi):
        repo_listesi([tmp_path / "yok-boyle-bir-dizin"])


def test_kok_verilmezse_hata():
    """--kok zorunludur: liste bos ise kesif hatasi firlatir."""
    with pytest.raises(KesifHatasi):
        repo_listesi([])


def test_kok_dogrudan_repo_olarak(tmp_path):
    """Kok bir repo'nun kendisi ise o repo TEK BASINA islenir."""
    repo = sahte_repo(tmp_path / "r")
    assert repo_listesi([repo]) == [repo]


# --------------------------------------------------------------------------
# okunabilirlik
# --------------------------------------------------------------------------


def test_okunabilir_utf8_okur(tmp_path):
    """Kucuk metin dosyasi None vermez."""
    yol = tmp_path / "a.md"
    yol.write_text("Merhaba\n", encoding="utf-8")
    assert okunabilir(yol) == "Merhaba\n"


def test_okunabilir_ikili_atlar(tmp_path):
    """NUL iceren (ikili) dosya ATLANIR: yol iddiasi yanlis bulgu vermesin."""
    yol = tmp_path / "logo.png"
    yol.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00")
    assert okunabilir(yol) is None


def test_okunabilir_buyuk_atlar(tmp_path):
    """>1MB dosya ATLANIR (cok buyuk/ikili dosya kurali)."""
    yol = tmp_path / "dev.js"
    yol.write_bytes(b"a" * (1024 * 1024 + 1))
    assert okunabilir(yol) is None


def test_okunabilir_bozuk_kodlama_atlar(tmp_path):
    """UTF-8 olmayan dosya ATLANIR (iz (traceback) degil, sessiz atlama)."""
    yol = tmp_path / "eski.txt"
    yol.write_bytes(b"\xff\xfe\x00bad")
    assert okunabilir(yol) is None


def test_okunabilir_klasor_ve_yok_dosya(tmp_path):
    """Klasor ya da olmayan dosya icin None (hata degil)."""
    (tmp_path / "d").mkdir()
    assert okunabilir(tmp_path / "d") is None
    assert okunabilir(tmp_path / "yok") is None