"""kesif: .git isaretli repo bulma, atlas DB okuma, KesifHatasi yollari.

Gercek git CALISTIRILMAZ: kesif yalnizca `.git` varligina bakar, tum dizin
agaci tmp_path altinda kurulur (kullanicinin gercek ~/klasoru okunmaz).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from conftest import atlas_db_olustur, sahte_repo

from devtemizle.kesif import KesifHatasi, repo_listesi


# --------------------------------------------------------------------------
# --root ile yuruyerek kesif
# --------------------------------------------------------------------------


def test_kok_alti_tum_repolar_bulunur(tmp_path):
    """.git isaretli dizinler repo sayilir; kokun altindaki hepsi listelenir."""
    kok = tmp_path / "projeler"
    sahte_repo(kok / "a")
    sahte_repo(kok / "b")
    sahte_repo(kok / "c")
    assert sorted(p.name for p in repo_listesi([kok])) == ["a", "b", "c"]


def test_git_dosya_olarak_işaretli(tmp_path):
    """.git bir DIZIN olmak zorunda degil: worktree/alt modulde dosyadir, yine bulunur."""
    kok = tmp_path / "projeler"
    worktree = kok / "worktree-repo"
    worktree.mkdir(parents=True)
    (worktree / ".git").write_text("gitdir: ../../.git/modules/x\n", encoding="utf-8")
    assert repo_listesi([kok]) == [worktree]


def test_kokun_kendisi_repo_sayilir(tmp_path):
    """Verilen kok zaten .git isaretliyse kendisi repo sayilir (altinda aranmaz)."""
    repo = sahte_repo(tmp_path / "tek")
    assert repo_listesi([repo]) == [repo]


def test_repo_icine_girilmez(tmp_path):
    """Ic ice repolar bulunur; dis repo, ic repo icin tek sayilir (repo icine inilmez)."""
    kok = tmp_path / "projeler"
    dis = sahte_repo(kok / "dis")
    sahte_repo(dis / "vendor" / "ic-repo")
    assert repo_listesi([kok]) == [dis]


def test_node_modules_icine_girilmez(tmp_path):
    """node_modules icindeki .git isaretli dizin GORULMEZ (bagimlilik deposu repo degildir)."""
    kok = tmp_path / "projeler"
    sahte_repo(kok / "node_modules" / "paket-repo")
    sahte_repo(kok / "gercek")
    assert repo_listesi([kok]) == [kok / "gercek"]


def test_derinlik_siniri(tmp_path):
    """Kesif yalnizca 3 derinlige kadar iner; cok derin repo gorulmez, bir seviye yukari bulunur.

    kok/a/b/c = kok + 3 alt dizin. Sozlesme 'derinlik 3'e kadar' dedigi icin
    4. seviye (kok/a/b/c/d) hem aranmaz hem de 3. seviyeyi gizlemez; boyle
    yazmak ki gercek siniri 3 ya da 4 yapan uygulamada da gecerli olsun.
    """
    kok = tmp_path / "projeler"
    sahte_repo(kok / "a" / "b" / "c")
    assert (kok / "a" / "b" / "c") in repo_listesi([kok])
    sahte_repo(kok / "a" / "b" / "c" / "d" / "e" / "f")
    assert kok / "a" / "b" / "c" / "d" not in repo_listesi([kok])


def test_bos_kok_kesif_hatasi(tmp_path):
    """Ne repo ne proje izi olan bos kok: KesifHatasi ('temizlenecek repo bulunamadi')."""
    kok = tmp_path / "bos"
    kok.mkdir()
    with pytest.raises(KesifHatasi, match="temizlenecek repo bulunamadi"):
        repo_listesi([kok])


def test_olmayan_root_kesif_hatasi(tmp_path):
    """Var olmayan yol: KesifHatasi 'bulunamadi' (CLI bunu cikis 2'ye cevirir)."""
    with pytest.raises(KesifHatasi, match="bulunamadi"):
        repo_listesi([tmp_path / "yok"])


def test_ayni_repo_tekrarlanmaz(tmp_path):
    """Ayni repo birden fazla kok altinda sayilmissa bir kez doner."""
    kok = tmp_path / "projeler"
    a = sahte_repo(kok / "a" / "repo")
    b = sahte_repo(kok / "b")
    sonuc = repo_listesi([kok, a, b])
    assert sonuc.count(a) == 1 and sorted(p.name for p in sonuc) == ["b", "repo"]


def test_bos_kok_listesi_atlas_db_ye_gider(tmp_path, ev_isole):
    """roots bos liste ([]) = kok verilmemis: atlas DB yoluna gider (kullanici ~/klasoru OKUNMAZ).

    Bu, CLI'nin `--root` verilmediginde yaptigi sey; kesif bos listede hata
    vermez, atlas'a bakar.
    """
    db = atlas_db_olustur(tmp_path / "a.db", [sahte_repo(tmp_path / "r")])
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ATLAS_DB", str(db))
        assert [p.name for p in repo_listesi([])] == ["r"]


# --------------------------------------------------------------------------
# atlas DB
# --------------------------------------------------------------------------


def test_atlas_db_ile_repo_listesi(tmp_path, monkeypatch):
    """--root yoksa varsayilan kaynak ATLAS_DB ortam degiskenidir."""
    db = atlas_db_olustur(
        tmp_path / "a.db", [sahte_repo(tmp_path / "r1"), sahte_repo(tmp_path / "r2")]
    )
    monkeypatch.setenv("ATLAS_DB", str(db))
    assert sorted(p.name for p in repo_listesi(None)) == ["r1", "r2"]


def test_atlas_db_argumani_env_den_guclu(tmp_path, monkeypatch):
    """Arguman > ATLAS_DB > (yok): acik arguman ortam degiskenini gecersiz kilar."""
    db = atlas_db_olustur(tmp_path / "a.db", [sahte_repo(tmp_path / "r")])
    monkeypatch.setenv("ATLAS_DB", str(tmp_path / "yok.db"))
    assert [p.name for p in repo_listesi(None, atlas_db=db)] == ["r"]


def test_atlas_db_sifirla_yazmaz(tmp_path):
    """DB salt-okunur acilir: kesif sonrasi DB dosyasi BIRE BIR degismez."""
    import hashlib

    db = atlas_db_olustur(tmp_path / "a.db", [sahte_repo(tmp_path / "r1")])
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    repo_listesi(None, atlas_db=db)
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before, "atlas DB'ye yazildi"


def test_atlas_db_yoksa_kesif_hatasi(tmp_path):
    """DB dosyasi yoksa KesifHatasi; mesaj Turkce ve --root/atlas tara'ya yonlendirir."""
    db = tmp_path / "yok.db"
    with pytest.raises(KesifHatasi) as hata:
        repo_listesi(None, atlas_db=db)
    mesaj = str(hata.value)
    assert "bulunamadi" in mesaj
    assert "--root" in mesaj and "atlas tara" in mesaj


def test_atlas_db_ortam_degiskeni_yoksa_kesif_hatasi(ev_isole, monkeypatch):
    """ATLAS_DB hic ayarlanmadiysa ~/.atlas/atlas.db'ye bakar; o da yoksa KesifHatasi.

    `ev_isole` HOME'u geciciye cevirir: test, KULLANICININ gercek atlas
    DB'sine erismez (o dosya bu makinede var).
    """
    monkeypatch.delenv("ATLAS_DB", raising=False)
    assert not (ev_isole / ".atlas" / "atlas.db").exists()
    with pytest.raises(KesifHatasi) as hata:
        repo_listesi(None)
    assert "atlas tara" in str(hata.value)


def test_atlas_db_okunamazsa_kesif_hatasi(tmp_path):
    """DB var ama gecersiz (repos tablosu yok): kesif patlamaz, KesifHatasi verir."""
    db = tmp_path / "bozuk.db"
    sqlite3.connect(str(db)).close()  # tablo yok
    with pytest.raises(KesifHatasi) as hata:
        repo_listesi(None, atlas_db=db)
    assert "atlas tara" in str(hata.value)


def test_atlas_db_silinmis_yol_elenir(tmp_path):
    """DB'de yolu olmayan repo satirlari sessizce elenir; kalan varsa liste doner."""
    var = sahte_repo(tmp_path / "var")
    db = atlas_db_olustur(tmp_path / "a.db", [var, tmp_path / "silinmis"])
    assert repo_listesi(None, atlas_db=db) == [var]


def test_atlas_db_sadece_silinmis_satir_kesif_hatasi(tmp_path):
    """DB'deki tum repolar silinmisse bos liste degil KesifHatasi doner."""
    db = atlas_db_olustur(tmp_path / "a.db", [tmp_path / "silinmis-1", tmp_path / "silinmis-2"])
    with pytest.raises(KesifHatasi, match="temizlenecek repo bulunamadi"):
        repo_listesi(None, atlas_db=db)


def test_atlas_db_sirali_doner(tmp_path):
    """Sonuc yola gore siralidir (rapor/tarama kararli olsun)."""
    yollar = [sahte_repo(tmp_path / f"r{i}") for i in range(3)]
    db = atlas_db_olustur(tmp_path / "a.db", yollar)
    assert [p.name for p in repo_listesi(None, atlas_db=db)] == ["r0", "r1", "r2"]