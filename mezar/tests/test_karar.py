"""Karar mantigi: dort denetimin sonucu `KAPATILABILIR` / `DIKKAT` olur.

Kritik ayrim: `remote izi yok` ve `bosaltilmis gorunmuyor` BULGU DEGILDIR --
yalniz not dusulur ve karari tek basina DEGISTIRMEZ. Testler bunu ayrica
sabitlemek icin var: guvenli gorunen ama kaniti olmayan bir karar, en kotu
ciktidir.
"""

from __future__ import annotations

from mezar import karar, tasi

from conftest import (
    bare_uzak,
    git,
    hedef_kopyala,
    mezar_tasi_repo,
    uzak_ekle_ve_gonder,
    yaz,
)

DOSYALAR = {"README.md": "# proje\n", "src/kod.py": "print(1)\n"}

#: Testte gecmiste bulunan sagde secret (parcalardan birlestirilir).
SAHTE = "AKIA" + "ZZZZZZZZZZZZZZZZZZ"


def _kapatilabilir_ortam(tmp_path, ad="anlat"):
    """HICBIR bulgu olmayan ortam: tasima tam, gonderilmis, gecmis temiz."""
    repo = mezar_tasi_repo(tmp_path, ad, DOSYALAR)
    hedef_kopyala(tmp_path / "araclar", ad, DOSYALAR)
    uzak_ekle_ve_gonder(repo, bare_uzak(tmp_path, ad))
    return tmp_path, repo


def test_butun_denetimler_temiz_kapatilabilir(tmp_path):
    """Pozitif: eksik yok, gonderilmis, gecmis temiz -> KAPATILABILIR."""
    kok, _ = _kapatilabilir_ortam(tmp_path)
    rapor = karar.denetle(kok, kok / "araclar", ["anlat"])
    assert rapor["repolar"][0]["karar"] == karar.KAPATILABILIR
    assert rapor["repolar"][0]["nedenler"] == []
    assert rapor["ozet"] == {"toplam": 1, "kapatilabilir": 1, "dikkat": 0}


def test_eksik_dosya_dikkat(tmp_path):
    """Negatif: hedefte eksik dosya varsa DIKKAT."""
    repo = mezar_tasi_repo(tmp_path, "anlat", DOSYALAR)
    hedef_kopyala(tmp_path / "araclar", "anlat", {"README.md": "# proje\n"})
    uzak_ekle_ve_gonder(repo, bare_uzak(tmp_path, "anlat"))
    rapor = karar.denetle(tmp_path, tmp_path / "araclar", ["anlat"])
    assert rapor["repolar"][0]["karar"] == karar.DIKKAT
    assert any("taşıma eksik" in n for n in rapor["repolar"][0]["nedenler"])


def test_gonderilmemis_commit_dikkat(tmp_path):
    """Negatif: uzakta olmayan commit varsa DIKKAT + 'N commit uzakta yok'."""
    kok, repo = _kapatilabilir_ortam(tmp_path)
    yaz(repo / "README.md", "# proje\n\nyeni\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "yerel is")
    rapor = karar.denetle(kok, kok / "araclar", ["anlat"])
    assert rapor["repolar"][0]["karar"] == karar.DIKKAT
    assert any("1 commit uzakta yok" in n for n in rapor["repolar"][0]["nedenler"])


def test_kirli_calisma_agaci_dikkat(tmp_path):
    """Negatif: commit EDILMEMIS degisiklik varsa DIKKAT."""
    kok, repo = _kapatilabilir_ortam(tmp_path)
    yaz(repo / "README.md", "# degisti\n")
    rapor = karar.denetle(kok, kok / "araclar", ["anlat"])
    assert rapor["repolar"][0]["karar"] == karar.DIKKAT
    assert any("çalışma ağacı kirli" in n for n in rapor["repolar"][0]["nedenler"])


def test_gecmiste_secret_dikkat_ve_deger_sizmaz(tmp_path):
    """Negatif: gecmiste secret varsa DIKKAT; ham deger rapora GIRMEZ."""
    repo = mezar_tasi_repo(tmp_path, "anlat", {"ayar.py": f'aws = "{SAHTE}"\n'})
    hedef_kopyala(tmp_path / "araclar", "anlat", {"ayar.py": "aws = ''\n"})
    uzak_ekle_ve_gonder(repo, bare_uzak(tmp_path, "anlat"))
    rapor = karar.denetle(tmp_path, tmp_path / "araclar", ["anlat"])
    assert rapor["repolar"][0]["karar"] == karar.DIKKAT
    assert any("gizli anahtar izi" in n for n in rapor["repolar"][0]["nedenler"])
    assert SAHTE not in repr(rapor)


def test_remote_izi_yok_karari_DEGISTIRMEZ(tmp_path):
    """Pozitif (ayrim): uzak YOK ama tasinma tam ve gecmis temizse KAPATILABILIR.

    "Gonderilmemis commit kontrol EDILEMEDI" bir uyaridir, bulgu DEGILDIR.
    """
    repo = mezar_tasi_repo(tmp_path, "anlat", DOSYALAR)
    hedef_kopyala(tmp_path / "araclar", "anlat", DOSYALAR)
    rapor = karar.denetle(tmp_path, tmp_path / "araclar", ["anlat"])
    sonuc = rapor["repolar"][0]
    assert sonuc["karar"] == karar.KAPATILABILIR, sonuc["nedenler"]
    assert sonuc["gonderilmemis"]["durum"] == "remote-yok"
    assert any("KONTROL EDILEMEDI" in n for n in sonuc["notlar"])


def test_bosaltilmis_gorunmuyor_karari_DEGISTIRMEZ(tmp_path):
    """Pozitif (ayrim): bosaltma yapilmamis repo KAPATILABILIR kalabilir.

    Bosaltma tasi bir BULGU DEGIL, bilgi notudur: diger uc denetim temizse
    karar degismez. Kullanici notu gorup karari kendisi verir.
    """
    kok, repo = _kapatilabilir_ortam(tmp_path)
    # Artik dosya COMMIT'LENIR ve gonderilir: aksi halde calisma agaci kirli
    # kalir ve bu test, bosaltma notunu denetlemez hale gelir.
    yaz(repo / "kalan.py", "# hicbir yere tasinmadi\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "kalan dosya eklendi")
    git(repo, "push", "-q", "origin", "HEAD:refs/heads/main")   # uzak onceki adimda kuruldu
    rapor = karar.denetle(kok, kok / "araclar", ["anlat"])
    sonuc = rapor["repolar"][0]
    assert sonuc["mezar_tasi"]["durum"] == "bosaltilmis-gorunmuyor"
    assert sonuc["karar"] == karar.KAPATILABILIR, sonuc["nedenler"]
    assert any("bosaltilmis gorunmuyor" in n for n in sonuc["notlar"])


def test_head1_yoksa_tasima_dogrulanamaz_dikkat(tmp_path):
    """Negatif: HEAD~1 yoksa tasima denetlenemez -> DIKKAT (sahte guvence yok)."""
    repo = tmp_path / "tek"
    repo.mkdir()
    yaz(repo / "README.md", "# tek commit\n")
    git(repo, "init", "-q")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "tek")
    uzak_ekle_ve_gonder(repo, bare_uzak(tmp_path, "tek"))
    (tmp_path / "araclar").mkdir()
    rapor = karar.denetle(tmp_path, tmp_path / "araclar", ["tek"])
    sonuc = rapor["repolar"][0]
    assert sonuc["karar"] == karar.DIKKAT
    assert any("doğrulanamadı" in n for n in sonuc["nedenler"])


def test_kismi_tarama_dikkat(tmp_path):
    """Negatif: gecmis taramasi yarim kaldiysa DIKKAT ('sir yok' demek DEGILDIR)."""
    kok, repo = _kapatilabilir_ortam(tmp_path)
    rapor = karar.denetle(
        kok, kok / "araclar", ["anlat"], satir_limiti=1, sure_limiti=30
    )
    sonuc = rapor["repolar"][0]
    assert sonuc["karar"] == karar.DIKKAT
    assert sonuc["gecmis_secret"]["kismi"] is True
    assert any("yarım kaldı" in n for n in sonuc["nedenler"])


def test_coklu_repo_ozet(tmp_path):
    """Ozet sayaclari kararlarla tutarli olmali (karisik kutuphane)."""
    kok, repo = _kapatilabilir_ortam(tmp_path, "anlat")
    mezar_tasi_repo(tmp_path, "atlas", DOSYALAR)          # uzak yok -> KAPATILABILIR
    hedef_kopyala(kok / "araclar", "atlas", DOSYALAR)      # tasinma tam olsun
    sirli = mezar_tasi_repo(tmp_path, "harita", {"ayar.py": f'aws = "{SAHTE}"\n'})
    uzak_ekle_ve_gonder(sirli, bare_uzak(tmp_path, "harita"))
    rapor = karar.denetle(kok, kok / "araclar", ["anlat", "atlas", "harita"])
    assert rapor["ozet"]["toplam"] == 3
    assert rapor["ozet"]["kapatilabilir"] + rapor["ozet"]["dikkat"] == 3
    kararlar = {r["ad"]: r["karar"] for r in rapor["repolar"]}
    assert kararlar["anlat"] == karar.KAPATILABILIR
    assert kararlar["atlas"] == karar.KAPATILABILIR
    assert kararlar["harita"] == karar.DIKKAT


def test_kapanis_uyarisi_her_zaman_var(tmp_path):
    """Sabit uyari raporun sonunda her zaman yer alir."""
    kok, _ = _kapatilabilir_ortam(tmp_path)
    rapor = karar.denetle(kok, kok / "araclar", ["anlat"])
    assert rapor["uyari"] == karar.KAPANIS_UYARISI
    assert "silmez/arşivlemez" in rapor["uyari"]
    assert "anahtarı döndürün" in rapor["uyari"]


def test_tasi_denetimi_not_dusur(tmp_path):
    """Yardimci: `mezar_tasi` bosaltma yapilmamis repo notu dusurur."""
    repo = tmp_path / "r"
    yaz(repo / "README.md", "# arsiv\n")
    yaz(repo / "kod.py", "x\n")
    assert tasi.denetle(repo)["durum"] == "bosaltilmis-gorunmuyor"