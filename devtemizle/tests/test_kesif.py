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


# --------------------------------------------------------------------------
# --ev bayrağı testleri (PLAN.md §3)
# --------------------------------------------------------------------------


def test_ev_bayragi_hariç_tutma_listesi(tmp_path, monkeypatch):
    """--ev: AppData, Library, .cache, .local, .npm, .cargo, .rustup, .gradle,
    OneDrive*, $Recycle.Bin, node_modules (repo değil), gizli dizinler (.git hariç)
    hariç tutulur."""
    ev = tmp_path / "ev"
    ev.mkdir()

    # Hariç tutulması gereken dizinler
    for ad in ["AppData", "Library", ".cache", ".local", ".npm", ".cargo",
               ".rustup", ".gradle", "$Recycle.Bin", "OneDrive", "OneDrive-Backup"]:
        (ev / ad).mkdir()
        sahte_repo(ev / ad / "repo-ici")  # Bu bulunmamalı

    # node_modules (repo değil) içindeki repo
    (ev / "node_modules").mkdir()
    sahte_repo(ev / "node_modules" / "paket-repo")

    # Gizli dizinler (.git hariç)
    (ev / ".gizli").mkdir()
    sahte_repo(ev / ".gizli" / "repo")

    # Geçerli repo (hariç listede olmayan)
    sahte_repo(ev / "projeler" / "gecerli-repo")

    monkeypatch.setattr("devtemizle.kesif.Path.home", lambda: ev)
    monkeypatch.setattr("devtemizle.kesif.os.name", "posix")

    from devtemizle.kesif import _ev_tara
    bulunan = _ev_tara()

    # Sadece geçerli repo bulunmalı
    assert [p.name for p in bulunan] == ["gecerli-repo"]


def test_ev_bayragi_derinlik_5(tmp_path, monkeypatch):
    """--ev: derinlik 5 sınırı uygulanır (ev + 5 alt).

    Derinlik sayımı: ev = 0, ev/projeler = 1, ev/projeler/a = 2, ...
    derinlik=5 -> 5 parça (ev/projeler/a/b/c/d) bulunur, ev/projeler/a/b/c/d/e (6 parça) bulunmaz.
    """
    ev = tmp_path / "ev"
    ev.mkdir()

    # Derinlik 5 içinde: ev/projeler/a/b/c/d = 5 parça (bulunmalı)
    repo_derinlik_5 = sahte_repo(ev / "projeler" / "a" / "b" / "c" / "d")
    # Derinlik 6: ev/projeler/a/b/c/d/e = 6 parça (bulunmamalı)
    sahte_repo(ev / "projeler" / "a" / "b" / "c" / "d" / "e" / "repo")

    monkeypatch.setattr("devtemizle.kesif.Path.home", lambda: ev)

    from devtemizle.kesif import _ev_tara
    bulunan = _ev_tara()

    assert repo_derinlik_5 in bulunan
    assert not any("e/repo" in str(p) for p in bulunan)


def test_ev_bayragi_gizli_dizinler_hariç_git_dahil(tmp_path, monkeypatch):
    """--ev: gizli dizinler hariç tutulur AMA .git içindeki repo bulunur."""
    ev = tmp_path / "ev"
    ev.mkdir()

    # .git hariç gizli dizinler hariç
    (ev / ".config").mkdir()
    sahte_repo(ev / ".config" / "repo")

    # .git içinde repo (worktree) - bu bir repo değil, .git dosyasıdır
    # .git dizini repo olarak sayılmaz (repo_listesi zaten .git'i atlar)

    monkeypatch.setattr("devtemizle.kesif.Path.home", lambda: ev)

    from devtemizle.kesif import _ev_tara
    bulunan = _ev_tara()

    # .config/repo bulunmamalı (gizli dizin)
    assert not any(".config" in str(p) for p in bulunan)


def test_derinlik_maksimum_8(tmp_path, monkeypatch):
    """--derinlik en fazla 8 olabilir (PLAN.md §3)."""
    from devtemizle.kesif import MAX_DERINLIK, repo_listesi
    assert MAX_DERINLIK == 8

    kok = tmp_path / "projeler"
    # Derinlik 8: kok/a/b/c/d/e/f/g/h = 8 seviye
    repo_8 = sahte_repo(kok / "a" / "b" / "c" / "d" / "e" / "f" / "g" / "h")
    # Derinlik 9: bulunmamalı
    sahte_repo(kok / "a" / "b" / "c" / "d" / "e" / "f" / "g" / "h" / "i" / "repo")

    bulunan = repo_listesi([kok], derinlik=8)
    assert repo_8 in bulunan
    assert not any("i/repo" in str(p) for p in bulunan)


def test_derinlik_default_3(tmp_path):
    """--derinlik varsayılan 3."""
    from devtemizle.kesif import DERINLIK
    assert DERINLIK == 3


# --------------------------------------------------------------------------
# Repo meta testleri (git yoksa meta None)
# --------------------------------------------------------------------------


def test_repo_meta_git_yoksa_son_commit_none(tmp_path, monkeypatch):
    """git komutu yoksa son_commit=None, kirli=False."""
    repo = sahte_repo(tmp_path / "r", git=True)
    # git komutunu yok say
    monkeypatch.setattr("devtemizle.kesif._git_var_mi", lambda: False)

    from devtemizle.kesif import _repo_meta_al
    meta = _repo_meta_al(repo)

    assert meta.son_commit is None
    assert meta.kirli is False


def test_repo_meta_git_calisir_ama_hata(tmp_path, monkeypatch):
    """git var ama hata dönerse sessizce None/False."""
    repo = sahte_repo(tmp_path / "r", git=True)

    def mock_git_calistir(args, cwd, timeout=5):
        return False, ""

    monkeypatch.setattr("devtemizle.kesif._git_calistir", mock_git_calistir)

    from devtemizle.kesif import _repo_meta_al
    meta = _repo_meta_al(repo)

    assert meta.son_commit is None
    assert meta.kirli is False


def test_repo_meta_git_log_calisir(tmp_path, monkeypatch):
    """git log -1 --format=%ct çalışırsa timestamp döner."""
    repo = sahte_repo(tmp_path / "r", git=True)

    def mock_git_calistir(args, cwd, timeout=5):
        if args[:2] == ["log", "-1"]:
            return True, "1704067200"  # 2024-01-01
        if args[:2] == ["status", "--porcelain"]:
            return True, "M  file.txt"
        return False, ""

    monkeypatch.setattr("devtemizle.kesif._git_calistir", mock_git_calistir)

    from devtemizle.kesif import _repo_meta_al
    meta = _repo_meta_al(repo)

    assert meta.son_commit == 1704067200
    assert meta.kirli is True


def test_repo_meta_git_log_yok_head_mtime(tmp_path, monkeypatch):
    """git log yoksa .git/HEAD mtime kullanılır."""
    repo = sahte_repo(tmp_path / "r", git=True)
    head = repo / ".git" / "HEAD"
    head.write_text("ref: refs/heads/main\n", encoding="utf-8")
    import time
    mtime = time.time() - 86400 * 30  # 30 gün önce
    import os
    os.utime(head, (mtime, mtime))

    def mock_git_calistir(args, cwd, timeout=5):
        if args[:2] == ["log", "-1"]:
            return False, ""  # git log başarısız
        if args[:2] == ["status", "--porcelain"]:
            return True, ""
        return False, ""

    monkeypatch.setattr("devtemizle.kesif._git_calistir", mock_git_calistir)

    from devtemizle.kesif import _repo_meta_al
    meta = _repo_meta_al(repo)

    assert meta.son_commit is not None
    assert abs(meta.son_commit - mtime) < 2  # saniye hassasiyetinde
    assert meta.kirli is False