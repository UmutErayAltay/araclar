"""kesif: .git isaretli repo bulma, atlas DB okuma (mode=ro), KesifHatasi yollari.

Gercek git CALISTIRILMAZ: kesif yalnizca `.git` varligina bakar, yalnizca
tmp_path altinda dizin agaci kurulur.
"""

from __future__ import annotations

import sqlite3

import pytest
from conftest import atlas_db_olustur, sahte_repo

from bagimlilik.kesif import DERINLIK, KesifHatasi, repo_listesi


# --------------------------------------------------------------------------
# --root ile yuruyerek kesif
# --------------------------------------------------------------------------


def test_kok_alti_repo_bulunur(tmp_path):
    """.git isaretli dizinler repo sayilir; kokun altindaki hepsi listelenir."""
    kok = tmp_path / "projeler"
    sahte_repo(kok / "a")
    sahte_repo(kok / "b")
    sahte_repo(kok / "c")
    assert sorted(p.name for p in repo_listesi([kok])) == ["a", "b", "c"]


def test_git_dosya_olarak_işaretli(tmp_path):
    """.git bir DIZIN olmak zorunda degil: worktree/alt modulde dosyadır, yine bulunur."""
    kok = tmp_path / "projeler"
    worktree = kok / "worktree-repo"
    worktree.mkdir(parents=True)
    (worktree / ".git").write_text("gitdir: ../../.git/modules/x\n", encoding="utf-8")
    assert repo_listesi([kok]) == [worktree]


def test_repo_icine_girilmez(tmp_path):
    """Ic ice repolar bulunur; dis repo, ic repo icin tek sayilir (repo icine inilmez)."""
    kok = tmp_path / "projeler"
    dis = sahte_repo(kok / "dis")
    sahte_repo(dis / "vendor" / "ic-repo")
    assert repo_listesi([kok]) == [dis]


def test_skip_dirs_ine_inilmez(tmp_path):
    """node_modules/.venv gibi SKIP_DIRS icindeki repolar GORULMEZ."""
    kok = tmp_path / "projeler"
    sahte_repo(kok / "node_modules" / "paket-repo")
    sahte_repo(kok / ".venv" / "venv-repo")
    sahte_repo(kok / "target" / "build-repo")
    sahte_repo(kok / "gercek")
    assert repo_listesi([kok]) == [kok / "gercek"]


def test_derinlik_siniri(tmp_path):
    """DERINLIK (kok + 3 alt dizin) asilirsa repo bulunmaz; bir seviye yukari bulunur.

    kok/a/b/c = 3 parca -> sınırda ve bulunur; kok/a/b/c/d = 4 parca -> bulunmaz.
    """
    kok = tmp_path / "projeler"
    sahte_repo(kok / "a" / "b" / "c")
    assert repo_listesi([kok]) == [kok / "a" / "b" / "c"]
    sahte_repo(kok / "a" / "b" / "c" / "d")
    assert repo_listesi([kok]) == [kok / "a" / "b" / "c"], "derinlik siniri asildi"


def test_proje_izi_olan_kok_kendisi_sayilir(tmp_path):
    """Kok'un kendisi repo degil ama requirements.txt/pyproject/package.json varsa kendisi sayilir."""
    kok = tmp_path / "tek-proje"
    sahte_repo(kok, {"pyproject.toml": '[project]\nname="x"\n'})
    assert repo_listesi([kok]) == [kok]


def test_proje_izi_olmayan_bos_kok_bos_liste(tmp_path):
    """Ne repo ne proje izi olan bos kok: bos liste (hata DEGIL, CLI bunu yakalar)."""
    kok = tmp_path / "bos"
    kok.mkdir()
    assert repo_listesi([kok]) == []


def test_ayni_repo_tekrarlanmaz(tmp_path):
    """Ayni repo birden fazla kok altinda sayilmissa bir kez doner."""
    kok = tmp_path / "projeler"
    a = sahte_repo(kok / "a" / "repo")
    b = sahte_repo(kok / "b")
    sonuc = repo_listesi([kok, a, b])
    assert sonuc.count(a) == 1 and sorted(p.name for p in sonuc) == ["b", "repo"]


def test_dosya_verilen_kok_ve_yokluğu(tmp_path):
    """--root bir dosya ise o dosya repo sayilir; var olmayan yol KesifHatasi."""
    dosya = tmp_path / "notlar.txt"
    dosya.write_text("x", encoding="utf-8")
    assert repo_listesi([dosya]) == [dosya]
    with pytest.raises(KesifHatasi, match="bulunamadi"):
        repo_listesi([tmp_path / "yok"])


def test_root_verilmezse_atlas_db_ye_gider(tmp_path, monkeypatch):
    """--root yoksa varsayilan kaynak ATLAS_DB ortam degiskenidir."""
    db = atlas_db_olustur(tmp_path / "a.db", [sahte_repo(tmp_path / "r1"), sahte_repo(tmp_path / "r2")])
    monkeypatch.setenv("ATLAS_DB", str(db))
    assert sorted(p.name for p in repo_listesi(None)) == ["r1", "r2"]


# --------------------------------------------------------------------------
# atlas DB
# --------------------------------------------------------------------------


def test_atlas_db_sifirla_yazmaz(tmp_path):
    """DB mode=ro acilir: kesif sonrasi DB dosyasi degismez (hash ayni)."""
    import hashlib

    db = atlas_db_olustur(tmp_path / "a.db", [sahte_repo(tmp_path / "r1")])
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    repo_listesi(None, atlas_db=db)
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before, "atlas DB'ye yazildi"


def test_atlas_db_yoksa_turkce_ipucu(tmp_path):
    """DB dosyasi yoksa KesifHatasi; mesaj Turkce ve kullaniciyi --root/atlas tara'ya yonlendirir."""
    db = tmp_path / "yok.db"
    with pytest.raises(KesifHatasi) as hata:
        repo_listesi(None, atlas_db=db)
    mesaj = str(hata.value)
    assert "atlas veritabani bulunamadi" in mesaj
    assert "--root" in mesaj and "atlas tara" in mesaj


def test_atlas_db_okunamazsa_turkce_ipucu(tmp_path):
    """DB dosyasi var ama gecersiz (repos tablosu yok) -> KesifHatasi, mesaj Turkce."""
    db = tmp_path / "bozuk.db"
    sqlite3.connect(str(db)).close()  # tablo yok
    with pytest.raises(KesifHatasi) as hata:
        repo_listesi(None, atlas_db=db)
    assert "okunamadi" in str(hata.value) and "atlas tara" in str(hata.value)


def test_atlas_db_arguman_env_den_guclu(tmp_path, monkeypatch):
    """Arguman > ATLAS_DB > varsayilan; acik arguman ortam degiskenini gecersiz kilar."""
    db = atlas_db_olustur(tmp_path / "a.db", [sahte_repo(tmp_path / "r")])
    monkeypatch.setenv("ATLAS_DB", str(tmp_path / "yok.db"))
    assert [p.name for p in repo_listesi(None, atlas_db=db)] == ["r"]


def test_atlas_db_silinmis_yol_elenir(tmp_path):
    """DB'de yolu olmayan repo satirlari sessizce elenir (temizlik)."""
    var = sahte_repo(tmp_path / "var")
    db = atlas_db_olustur(tmp_path / "a.db", [var, tmp_path / "silinmis"])
    assert repo_listesi(None, atlas_db=db) == [var]


def test_atlas_db_sirali_doner(tmp_path):
    """Sonuc yola gore siralidir (rapor taramasi kararli olsun)."""
    yollar = [sahte_repo(tmp_path / f"r{i}") for i in range(3)]
    db = atlas_db_olustur(tmp_path / "a.db", yollar)
    assert [p.name for p in repo_listesi(None, atlas_db=db)] == ["r0", "r1", "r2"]


def test_atlas_db_olmayan_tabloda_hata(tmp_path):
    """repos tablosu olmayan DB: kesif patlamaz, KesifHatasi verir."""
    db = tmp_path / "baska.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE baska (x TEXT)")
    conn.commit()
    conn.close()
    with pytest.raises(KesifHatasi):
        repo_listesi(None, atlas_db=db)


def test_derinlik_sabiti_uc():
    """Kesif derinlik siniri degismez: kok + 3 alt dizin."""
    assert DERINLIK == 3
