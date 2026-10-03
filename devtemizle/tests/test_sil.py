"""sil: kuru calistirma, gercek silme, atlanan nedenler, guvenlik sinirlari.

Diger testlerden farkli olarak burada DISK GERCEKTEN DEGISTIRILIR -- ama yalnizca
tmp_path altinda. Kullanici ~/klasoru ve gercek repolar hicbir testte okunmaz.

YAS UYARISI: yeni kurulan sahte adaylarin yasi ~0 gundur. Bu yuzden gercek
silme testleri `yas=0` kullanir; 'neni' (korunur) testi `yas=7` ile yazildi.
"""

from __future__ import annotations

import os
import shutil
import stat
from pathlib import Path

import pytest
from conftest import (
    nedenler,
    sahte_aday,
    sahte_aday_soyut,
    sahte_repo,
    say,
    tree_hash,
)

from devtemizle.sil import sil
from devtemizle.tara import tara


# --------------------------------------------------------------------------
# Kuru calistirma (uygula=False)
# --------------------------------------------------------------------------


def test_kuru_calistirma_hicbir_dosyaya_dokunmaz(tmp_path):
    """uygula=False: disk BIRE BIR ayni kalir (hash oncesi == sonrasi)."""
    repo = sahte_repo(tmp_path / "r", {"index.js": "kaynak\n"})
    sahte_aday(repo, "node_modules")
    sahte_aday(repo, "__pycache__")
    once = tree_hash(repo)
    sonuc = sil([repo], uygula=False, yas=0)
    assert tree_hash(repo) == once, "kuru calistirma diskte iz birakti"
    assert (repo / "node_modules").is_dir() and (repo / "index.js").is_file()


def test_kuru_calistirma_silindi_bos(tmp_path):
    """uygula=False: hicbir aday silinmis sayilmaz; sayaclar 'ne silinecekti' bilgisini tasir."""
    repo = sahte_repo(tmp_path / "r")
    sahte_aday(repo, "node_modules")
    sahte_aday(repo, "__pycache__")
    sonuc = sil([repo], uygula=False, yas=0)
    assert say(sonuc["silindi"]) == 0
    assert say(sonuc["silinecek"]) >= 2
    assert say(sonuc["atlanan"]) == 0


def test_kuru_calistirma_ve_uygula_ayni_silinecek_sayisi(tmp_path):
    """Kuru calistirma gercek calistirmayla ayni adayi sayar: onizleme yaniltmaz."""
    repo = sahte_repo(tmp_path / "r")
    sahte_aday(repo, "node_modules")
    sahte_aday(repo, "__pycache__")
    kuru = sil([repo], uygula=False, yas=0)
    gercek = sil([repo], uygula=True, yas=0)
    assert say(kuru["silinecek"]) == say(gercek["silinecek"]) == say(gercek["silindi"])


# --------------------------------------------------------------------------
# Gercek silme
# --------------------------------------------------------------------------


def test_uygula_adaylari_siler(tmp_path):
    """uygula=True: aday dizinleri GERCEKTEN gider, silindi sayaci dolar."""
    repo = sahte_repo(tmp_path / "r")
    sahte_aday(repo, "node_modules")
    sahte_aday(repo, "__pycache__")
    sonuc = sil([repo], uygula=True, yas=0)
    assert not (repo / "node_modules").exists()
    assert not (repo / "__pycache__").exists()
    assert say(sonuc["silindi"]) == 2
    assert say(sonuc["silinemedi"]) == 0


def test_uygula_repo_kaynak_dosyalari_yerinde_kalir(tmp_path):
    """Sadece aday silinir; repo'nun kendi dosyalari ve .git DOKUNULMAZ."""
    repo = sahte_repo(tmp_path / "r", {"index.js": "kaynak\n", "sub/app.py": "x\n"})
    sahte_aday(repo, "node_modules")
    sil([repo], uygula=True, yas=0)
    assert (repo / ".git").is_dir(), ".git silindi"
    assert (repo / "index.js").read_text(encoding="utf-8") == "kaynak\n"
    assert (repo / "sub" / "app.py").is_file()


def test_bosalan_bayt_toplam_boyut(tmp_path):
    """bosalan_bayt = silinen adaylarin TOPLAM boyutu."""
    repo = sahte_repo(tmp_path / "r")
    sahte_aday(repo, "node_modules", bayt=1000)
    sahte_aday(repo, "__pycache__", bayt=24)
    sonuc = sil([repo], uygula=True, yas=0)
    assert sonuc["bosalan_bayt"] == 1024, sonuc


def test_salt_okunur_dosya_olan_aday_silinir(tmp_path):
    """Salt-okunur (S_IREAD) dosya iceren node_modules silinebilir: rmtree oncesi yazma izni verilir."""
    repo = sahte_repo(tmp_path / "r")
    yol = sahte_aday(repo, "node_modules", bayt=10)
    kilit = yol / "salt-okunur.js"
    kilit.write_bytes(b"x" * 10)
    kilit.chmod(stat.S_IREAD)
    sonuc = sil([repo], uygula=True, yas=0)
    assert not yol.exists(), "salt-okunur dosya iceren aday silinemedi"
    assert say(sonuc["silindi"]) == 1
    assert say(sonuc["silinemedi"]) == 0


def test_silinmezse_sonuc_cokmez(tmp_path, monkeypatch):
    """Tek bir aday silinemese bile digerleri silinir, sonuc DONDURULUR (cokmez).

    Kilitli aday icin shutil.rmtree PermissionError firlatir; sil bunu yutar,
    nedeni 'kilitli...' ile baslayan bir metin olarak silinemedi'ye yazar.
    """
    from devtemizle import sil as sil_modulu

    repo = sahte_repo(tmp_path / "r")
    kilitli = sahte_aday(repo, "node_modules", bayt=5)
    normal = sahte_aday(repo, "__pycache__", bayt=5)
    gercek_rmtree = shutil.rmtree

    def kilitli_ol(path, *a, **k):
        if Path(path) == kilitli:
            raise PermissionError(13, "Permission denied")
        return gercek_rmtree(path, *a, **k)

    monkeypatch.setattr(sil_modulu.shutil, "rmtree", kilitli_ol)
    sonuc = sil([repo], uygula=True, yas=0)
    assert kilitli.is_dir(), "kilitli aday silinmemis olmali"
    assert not normal.exists(), "diger aday silinmeliydi"
    assert say(sonuc["silindi"]) == 1
    assert say(sonuc["silinemedi"]) == 1
    assert any(n.startswith("kilitli") for n in nedenler(sonuc["silinemedi"])), sonuc["silinemedi"]


# --------------------------------------------------------------------------
# Atlanan nedenler
# --------------------------------------------------------------------------


def test_baglanti_olan_aday_gercekten_silinmez(tmp_path, monkeypatch):
    """atlandi='baglanti' olan aday SILINMEZ — os.symlink gerektirmez.

    Bu, Windows Developer Mode olmayan makinelerde (ve symlink testleri
    atlandiginda) asil guvenlik sozlesmesini yine dener: tara bir adayi
    baglanti olarak isaretlediyse sil ona DOKUNMAZ. tara ciktisi sozlesmeye
    gore sahtelenebilir.
    """
    repo = sahte_repo(tmp_path / "r")
    gercek_aday = sahte_aday(repo, "node_modules", bayt=40)

    sahte = [sahte_aday_soyut(repo, "node_modules", yol=gercek_aday, boyut=40, atlandi="baglanti")]
    monkeypatch.setattr("devtemizle.sil.tara", tara_sahtesi(sahte))
    sonuc = sil([repo], uygula=True, yas=0)
    assert gercek_aday.is_dir(), "baglanti olarak isaretlenen aday silindi"
    assert say(sonuc["silindi"]) == 0
    assert say(sonuc["silinecek"]) == 0, "baglanti 'silinecek' sayilamaz"
    assert "baglanti" in nedenler(sonuc["atlanan"])


def test_baglanti_adayi_silinmez(tmp_path, symlink_kur):
    """node_modules baglantiysa SILINMEZ: hedef (repo disi) dokunulmaz."""
    repo = sahte_repo(tmp_path / "r")
    hedef = tmp_path / "hedef-depo"
    sahte_repo(hedef, {"paket.js": "x"})
    link = symlink_kur(hedef, "node_modules", ust=repo)
    sonuc = sil([repo], uygula=True, yas=0)
    assert link.exists(), "baglanti silindi"
    assert hedef.is_dir() and (hedef / "paket.js").is_file(), "baglanti hedefi silindi"
    assert say(sonuc["silindi"]) == 0


def test_baglanti_hedefi_ve_icereigi_kalir(tmp_path, symlink_kur):
    """Baglanti adayi boslanmaz: hedef dizinin icerigi ve .git'i sapkal kalir."""
    repo = sahte_repo(tmp_path / "r")
    hedef = sahte_repo(tmp_path / "hedef")
    (hedef / "paket.js").write_bytes(b"x" * 50)
    once = tree_hash(hedef)
    symlink_kur(hedef, "node_modules", ust=repo)
    sil([repo], uygula=True, yas=0)
    assert tree_hash(hedef) == once, "baglanti hedefi degisti"
    assert (hedef / ".git").is_dir()


def test_pyvenv_cfg_yoksa_silinmez(tmp_path):
    """.venv/venv'de pyvenv.cfg yoksa atlanir: kullanici venv'i KAZANILMISTIR."""
    repo = sahte_repo(tmp_path / "r")
    sahte_aday(repo, ".venv", bayt=40)
    sahte_aday(repo, "venv", bayt=40)
    sonuc = sil([repo], uygula=True, yas=0)
    assert (repo / ".venv").is_dir() and (repo / "venv").is_dir()
    assert say(sonuc["silindi"]) == 0
    assert "pyvenv-yok" in nedenler(sonuc["atlanan"])


def test_yeni_aday_varsayilan_yasta_korunur(tmp_path):
    """yas=7: 7 gunden yeni aday SILINMEZ, 'yeni' nedeniyle atlanir.

    Yeni kurulan sahte klasorler ~0 gun yasindadir; bu yuzden atlamanin
    gercekten yas kuralindan geldigini gormek icin simdi'ye gore yaslandirilir.
    """
    repo = sahte_repo(tmp_path / "r")
    sahte_aday(repo, "node_modules", bayt=30)
    sonuc = sil([repo], uygula=True, yas=7)
    assert (repo / "node_modules").is_dir(), "yeni aday silindi"
    assert say(sonuc["silindi"]) == 0
    assert "yeni" in nedenler(sonuc["atlanan"])


def test_eski_aday_varsayilan_yasta_silinir(tmp_path):
    """yas=7: 7 gunden eski aday SILINIR (yas filtresi gercekten ayirir)."""
    import time

    from test_tara import eskit

    repo = sahte_repo(tmp_path / "r")
    sahte_aday(repo, "node_modules", bayt=30)
    eskit(repo / "node_modules", 30.0)
    sonuc = sil([repo], uygula=True, yas=7)
    assert not (repo / "node_modules").exists()
    assert say(sonuc["silindi"]) == 1


def test_yas_sifir_filtresini_kapatir(tmp_path):
    """yas=0: yeni adaylar da silinir (yeni kurulmus projeler icin pratik varsayilan)."""
    repo = sahte_repo(tmp_path / "r")
    sahte_aday(repo, "node_modules", bayt=30)
    sil([repo], uygula=True, yas=0)
    assert not (repo / "node_modules").exists()


def test_tur_listesi_yalniz_isteneni_siler(tmp_path):
    """turler=['node_modules']: yalniz o tur silinir, diger turler durur."""
    repo = sahte_repo(tmp_path / "r")
    sahte_aday(repo, "node_modules", bayt=30)
    sahte_aday(repo, "__pycache__", bayt=30)
    sonuc = sil([repo], uygula=True, yas=0, turler=["node_modules"])
    assert not (repo / "node_modules").exists()
    assert (repo / "__pycache__").is_dir(), "istenmeyen tur silindi"
    assert say(sonuc["silindi"]) == 1


def test_tur_disi_nedeni_atlananlarda(tmp_path):
    """turler filtresi disindaki aday SILINMEZ ve 'tur-disi' nedeniyle atlanir."""
    repo = sahte_repo(tmp_path / "r")
    sahte_aday(repo, "__pycache__", bayt=30)
    sonuc = sil([repo], uygula=True, yas=0, turler=["node_modules"])
    assert (repo / "__pycache__").is_dir()
    assert "tur-disi" in nedenler(sonuc["atlanan"])


def test_bos_tur_listesi_hicbir_seyi_silmez(tmp_path):
    """turler=[]: hicbir tur secilmemis -> disk degismez, hepsi 'tur-disi'."""
    repo = sahte_repo(tmp_path / "r")
    sahte_aday(repo, "node_modules", bayt=30)
    once = tree_hash(repo)
    sonuc = sil([repo], uygula=True, yas=0, turler=[])
    assert tree_hash(repo) == once
    assert say(sonuc["silindi"]) == 0


def test_tur_listesi_gecersiz_ad_sayisi_bolmez(tmp_path):
    """Bilinmeyen tur verilirse hicbir aday silinmez -- sessizce yanlis temizlik yapilmaz."""
    repo = sahte_repo(tmp_path / "r")
    sahte_aday(repo, "node_modules", bayt=30)
    once = tree_hash(repo)
    sonuc = sil([repo], uygula=True, yas=0, turler=["build"])
    assert tree_hash(repo) == once, "gecersiz tur filtresi bir seyi sildi"
    assert say(sonuc["silindi"]) == 0


# --------------------------------------------------------------------------
# Guvenlik: repo disina cozumlenen aday
# --------------------------------------------------------------------------


def tara_sahtesi(adaylar: list[dict]):
    """tara(...) yerine sabit aday listesi donduren sahte (sil kendi taramasini yapar)."""
    return lambda *a, **k: adaylar


def test_repo_disina_cozumlenen_aday_silinmez(tmp_path, monkeypatch):
    """Aday yolu repo disina cozumleniyorsa SILINMEZ: 'repo-disi' guvenlik freni.

    tara sonucu sahtelenir: bir aday repo disindaki bir dosyayi isaret eder,
    digeri repo icinde gecerli bir adaydir.
    """
    repo = sahte_repo(tmp_path / "r")
    dis = tmp_path / "komsu-paket"
    dis.mkdir()
    (dis / "paket.js").write_bytes(b"x" * 20)
    guvenli = sahte_aday(repo, "node_modules", bayt=30)

    sahte = [
        sahte_aday_soyut(repo, "__pycache__", yol=dis / "paket.js", boyut=20),
        sahte_aday_soyut(repo, "node_modules", yol=guvenli, boyut=30),
    ]
    monkeypatch.setattr("devtemizle.sil.tara", tara_sahtesi(sahte))
    sonuc = sil([repo], uygula=True, yas=0)
    assert (dis / "paket.js").is_file(), "repo disi dosya silindi"
    assert not guvenli.exists(), "repo ici guvenli aday silinmeliydi"
    assert "repo-disi" in nedenler(sonuc["silinemedi"])
    assert say(sonuc["silindi"]) == 1


def test_repo_disina_cozumlenen_dizin_silinmez(tmp_path, monkeypatch):
    """Repo disina cozumlenen aday DIZINI de silinmez (dosya siniri yok)."""
    repo = sahte_repo(tmp_path / "r")
    komsu = tmp_path / "komsu-repo"
    (komsu / "node_modules").mkdir(parents=True)
    (komsu / "node_modules" / "paket.js").write_bytes(b"x" * 20)

    sahte = [sahte_aday_soyut(repo, "node_modules", yol=komsu / "node_modules", boyut=20)]
    monkeypatch.setattr("devtemizle.sil.tara", tara_sahtesi(sahte))
    sonuc = sil([repo], uygula=True, yas=0)
    assert (komsu / "node_modules" / "paket.js").is_file(), "komsu repo adayi silindi"
    assert "repo-disi" in nedenler(sonuc["silinemedi"])


def test_sonuc_basi_gozeten_gecerli_diktator_sozlesmesi(tmp_path):
    """sil() sonucu sozlesmedeki bes alani tasir."""
    repo = sahte_repo(tmp_path / "r")
    sahte_aday(repo, "node_modules", bayt=7)
    sonuc = sil([repo], uygula=False, yas=0)
    assert set(sonuc) == {
        "silinecek",
        "silindi",
        "silinemedi",
        "atlanan",
        "bosalan_bayt",
    }


def test_birden_fazla_repo_silinir(tmp_path):
    """repolar listesi sirayla temizlenir; her repo kendi adaylarini siler."""
    kok = tmp_path / "projeler"
    a = sahte_repo(kok / "a")
    b = sahte_repo(kok / "b")
    sahte_aday(a, "node_modules", bayt=10)
    sahte_aday(b, "__pycache__", bayt=20)
    sonuc = sil([a, b], uygula=True, yas=0)
    assert say(sonuc["silindi"]) == 2
    assert not (a / "node_modules").exists() and not (b / "__pycache__").exists()
    assert sonuc["bosalan_bayt"] == 30


def test_aday_listesi_verilse_direkt_calisir(tmp_path):
    """sil(repolar, ...) kendi taramasi yapar; tara ile ayni sonucu verir."""
    repo = sahte_repo(tmp_path / "r")
    sahte_aday(repo, "node_modules", bayt=11)
    adaylar = tara([repo])
    sonuc = sil([repo], uygula=True, yas=0)
    assert say(sonuc["silinecek"]) == len(adaylar) == 1

def test_ara_dizindeki_junction_repo_disina_tasmaz(tmp_path):
    """Regresyon: repo icindeki junction izlenmez; hedefteki venv/node_modules SILINMEZ."""
    import subprocess
    import pytest
    from devtemizle.sil import sil

    dis = tmp_path / "dis" / "eski"
    (dis / "node_modules").mkdir(parents=True)
    (dis / "node_modules" / "ONEMLI.txt").write_text("x", encoding="utf-8")
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    r = subprocess.run(["cmd", "/c", "mklink", "/J", str(repo / "izgara"), str(dis)],
                       capture_output=True)
    if r.returncode != 0:
        pytest.skip("junction olusturulamadi")
    sonuc = sil([repo], uygula=True, yas=0)
    assert (dis / "node_modules" / "ONEMLI.txt").is_file()
    assert sonuc["silindi"] == []
