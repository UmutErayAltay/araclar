"""Rapor ayrıştırma testleri (Dalga D).

Fixture'lar KURGUSALDIR (uydurma proje, uydurma ajan adları, uydurma sayılar).
Yapıları bu oturumdaki gerçek ajan raporlarının YAPISINDAN türetildi
("## 1. Değişen dosyalar", "## 2. Test özeti", kanıtsız iddia cümleleri,
`docs/ekran/*.png` yolları, "525 passed" beyanları) ama İÇERİKleri kopyalanmadı.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from orkestra import report
from orkestra.report import (
    BASARISIZ,
    DEGERLENDIRILMEDI,
    KANITLI,
    KANITSIZ,
    REDDEDILDI,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40
GIF = b"GIF89a" + b"\x00" * 40
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 40
WEBP = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 32


# -- yardımcılar ----------------------------------------------------------


@pytest.fixture()
def calisma(tmp_path):
    dizin = tmp_path / "calisma"
    dizin.mkdir(parents=True, exist_ok=True)
    return dizin


@pytest.fixture()
def ekran(calisma):
    """Geçerli bir PNG yazan yardımcı (imza doğru, boyut > 0)."""
    def _yaz(yol="ekran/panel.png", veri=PNG, yaz=PNG):
        dosya = Path(yol)
        if not dosya.is_absolute():
            dosya = calisma / dosya
        dosya.parent.mkdir(parents=True, exist_ok=True)
        dosya.write_bytes(veri)
        if yaz is not None:
            # mtime'ı kontrollü ayarla (eski/yeni testi).
            import os

            ts = time.time() + (yaz if isinstance(yaz, (int, float)) else 0)
            os.utime(dosya, (ts, ts))
        return dosya
    return _yaz


def degerlendir(metin, calisma, **kw):
    return report.degerlendir(metin, calisma_dizini=calisma, **kw)


# =========================================================================
# 1) `reddedildi-suphesi` — GERÇEK BENZERİ POZİTİFLER
# =========================================================================
# Yapı, bu oturumdaki ajan loglarında görülen "izin sınıflandırıcısı reddi
# 0 çıkış koduyla da bildirilebiliyor" biçiminden türetildi; içerikler
# SANİTİZE edilip kurgusal projeye uyarlandı.

REDDEDILME_POZITIFLERI = [
    "I was blocked from running the migration command by the permission layer.",
    "I could not run the test suite because the tool was denied.",
    "Permission to write the file was not granted, so I stopped.",
    "I need your approval before I can apply the patch.",
    "The action was denied by the safety classifier, nothing was changed.",
    "I requested permission to edit the config, but you haven't granted it.",
    "The command is not allowed in this environment; I cannot continue.",
    "Waiting for the user's confirmation before modifying anything.",
    "İzin verilmediği için dosyayı değiştiremedim, hiçbir şey yapılmadı.",
    "Sınıflandırıcı reddi geldi; komut hiç çalışmadı.",
    "Bu işlem onay gerektiriyor, ben onay alamadan ilerleyemem.",
    "Değişiklik sınıflandırıcı tarafından engellendi.",
    # --- BU OTURUMDA GÖZLEMLE NEDEN ÇIKANLAR (gerçek `claude -p` çıktısı) ---
    # `cor claude -p` bu cümleyi YAZDI ve yine de ÇIKIŞ KODU 0 verdi:
    "Komut onay gerektiriyor, bu yüzden çalıştırılamadı. "
    "`python3 -c 'print(42*2)'` komutunun çıktısı bende yok. "
    "Onay verilirse tekrar çalıştırabilirim.",
    "Onay verilirse tekrar çalıştırabilirim; şimdilik hiçbir şey yapmadım.",
    "Ekleyemedim: dosya yazma izni gerektiriyor.",
]

# YANLIŞ POZİTİF KORUMASI: bu repo'nun kendi raporları bu sözcükleri sık
# kullanır — kod/hata/test anlatısı, red bildirimi DEĞİLDİR.
YANLIS_POZITIFLERI = [
    "The retry logic now matches `IZIN_REDDI_DESENI` in runner.py.",
    "PermissionError yakalanıyor; testler bu yolu doğruluyor.",
    "permission denied durumunda yeniden deneme yok, doğru davranış.",
    "Testi: permission denied senaryosu `onay-bekliyor` üretmeli.",
    "I added a test asserting the permission-denied path sets onay-bekliyor.",
    "pytest.raises(PermissionError) ile 403 durumunu sınadım.",
    "`runner.py` içinde IZIN_REDDI_DESENI kalıbı tanımlı ve test ediliyor.",
    "The den(y|ied) branch is skipped when the exit code is zero.",
    "We assert that a denied run never sets hata; it goes to onay-bekliyor.",
    "Test edildi: sınıflandırıcı reddi metni bulunduğunda görev onay bekler.",
    "```python\nif not permission_granted:\n    raise SystemExit(1)\n```",
    "The `blocked` word in the fixture text must not trigger a denial verdict.",
    # --- Yeni eklenen fiil çekimlerinin KARŞITI (kod/kural anlatısı) ---
    # "çalıştırılamadı" deseni genişletildi; aşağıdakiler YANLIŞ POZİTİFTİR.
    "Testi: komut çalıştırılamadı senaryosu `onay-bekliyor` üretmeli.",
    "`pytest` içinde `çalıştırılamadı` durumunu doğrulayan test eklendi.",
    "runner.py'de `calistirilamadi` durumunda yeniden deneme yok kuralı var.",
    "Çıktısı bende yok diyen satır test verisinde geçiyor, panele basılmıyor.",
    "onay gerektiriyor kuralı IZIN_REDDI_DESENI içinde tanımlı ve test edildi.",
]


@pytest.mark.parametrize("metin", REDDEDILME_POZITIFLERI)
def test_reddedilme_pozitifleri(metin, calisma):
    d = degerlendir(metin, calisma)
    assert d.sonuc == REDDEDILDI, f"pozitif kaçtı: {metin!r} -> {d.sonuc}"
    assert any(g.kural == "izin-reddi-son-mesaj" for g in d.gerekceler)


@pytest.mark.parametrize("metin", YANLIS_POZITIFLERI)
def test_reddedilme_yANLIS_pozitifleri(metin, calisma, ekran):
    # Kod anlatıları: görsel kanıt da verelim ki "kanitsiz" olsa da
    # YANLIŞLIKLA "red şüphesi" sayılmasın.
    ekran()
    d = degerlendir(
        metin + "\nGörsel: ekran/panel.png — kusur yok.\n525 passed.",
        calisma,
    )
    assert d.sonuc != REDDEDILDI, f"yanlış pozitif: {metin!r} -> {d.sonuc}"


def test_reddedilme_son_mesaj_disi_inde_tetiklenmez(calisma, ekran):
    """Gövdede red cümlesi var ama son ~60 satırda DEĞİLSE tetiklenmez.

    Gövde red cümlesi içerecek kadar UZUN olmalı, ama son bölüm onu içermemeli.
    """
    ekran()
    govde = "\n".join(["I was blocked from running the command."] * 80)
    d = degerlendir(
        govde + "\n\n## Sonuç bölümü\n" + "\n".join(
            ["Panel temiz görünüyor, hizalama doğru."] * 80
        ) + "\nGörsel: ekran/panel.png — kusur yok.\n525 passed.",
        calisma,
    )
    assert d.sonuc == KANITLI


def test_reddedilme_son_mesajda_gecerli(calisma):
    govde = "\n".join(["gorev tamamlandi"] * 80)
    d = degerlendir(
        govde + "\n\n## Son\nI was blocked from editing the file by the classifier.",
        calisma,
    )
    assert d.sonuc == REDDEDILDI


def test_belirsiz_ifade_uyari_durumuna_duser(calisma, ekran):
    """Emin olunamayan durum `reddedildi-suphesi` DEĞİL, `uyari` olur."""
    ekran()
    d = degerlendir(
        "I cannot say for sure whether the formatter is happy here.\n"
        "Görsel: ekran/panel.png — temiz.\n10 passed.",
        calisma,
    )
    assert d.sonuc == KANITLI
    assert d.uyarilar


# =========================================================================
# 2) Test beyanları: pytest / unittest / go / jest / cargo
# =========================================================================


@pytest.mark.parametrize(
    "satir,tur,passed,failed,error",
    [
        ("525 passed in 65.86s (0:01:05)", "pytest", 525, None, None),
        ("== 12 passed in 1.2s ==", "pytest", 12, None, None),
        ("3 failed, 10 passed in 4.5s", "pytest", 10, 3, None),
        ("2 passed, 1 error, 5 skipped", "pytest", 2, None, 1),
        ("Ran 12 tests in 0.512s", "unittest", 12, None, None),
        ("FAILED (failures=2, errors=1)", "unittest", None, 2, 1),
        ("ok  	kurgusal/paket  	0.203s", "go", 1, 0, None),
        ("FAIL	kurgusal/paket	0.114s", "go", 0, 1, None),
        ("Tests:       4 passed, 4 total", "jest", 4, 0, None),
        ("Tests:   2 failed, 5 passed, 7 total", "jest", 5, 2, None),
        ("test result: ok. 12 passed; 0 failed; 0 ignored", "cargo", 12, 0, None),
        ("test result: FAILED. 3 passed; 2 failed", "cargo", 3, 2, None),
    ],
)
def test_test_cikti_bicimleri(satir, tur, passed, failed, error):
    testler = report.testleri_ayikla(satir)
    assert testler, f"ayrıştırılamadı: {satir!r}"
    t = testler[0]
    assert t.tur == tur
    assert t.passed == passed, f"{satir!r}: {t.passed} != {passed}"
    if failed is not None:
        assert t.failed == failed, f"{satir!r}: {t.failed} != {failed}"
    if error is not None:
        assert t.error == error


def test_no_tests_ran_basarili_sayilmaz(calisma, ekran):
    ekran()
    d = degerlendir(
        "no tests ran in 0.01s\nGörsel: ekran/panel.png — temiz.", calisma
    )
    assert d.testler[0].passed == 0
    assert d.sonuc == KANITLI


def test_failed_test_basarisiz_sinifi(calisma, ekran):
    ekran()
    d = degerlendir(
        "3 failed, 10 passed in 4.5s\nGörsel: ekran/panel.png — temiz.", calisma
    )
    assert d.sonuc == BASARISIZ


def test_traceback_ile_biten_bolum_basarisiz(calisma, ekran):
    ekran()
    d = degerlendir(
        "Görsel: ekran/panel.png — temiz.\nTraceback (most recent call last):",
        calisma,
    )
    assert d.sonuc == BASARISIZ


def test_basarisizlik_ondeligi_reddi_gectirmez(calisma, ekran):
    """Öncelik sırası: red > başarısız > kanıtsız > kanıtlı."""
    ekran()
    d = degerlendir(
        "3 failed, 10 passed\nI was blocked from editing the file.\n"
        "Görsel: ekran/panel.png — temiz.",
        calisma,
    )
    assert d.sonuc == REDDEDILDI


# =========================================================================
# 3) Görsel kanıt: GÖZLEMLENEN denetimler
# =========================================================================


def test_gecerli_png_kanitlidir(calisma, ekran):
    ekran()
    d = degerlendir("Görsel: ekran/panel.png — hizalama temiz.", calisma)
    assert d.sonuc == KANITLI
    g = d.gorseller[0]
    assert g.gecerli and g.bayt == len(PNG)
    assert g.gerekce


@pytest.mark.parametrize("veri", [PNG, GIF, JPEG, WEBP])
def test_gecerli_imzalar(calisma, ekran, veri, tmp_path):
    # Uzantıyı gerçek imzaya uydur (yanlışlıkla geçmesin diye eşleştirilir).
    uzanti = {PNG: "a.png", GIF: "b.gif", JPEG: "c.jpg", WEBP: "d.webp"}[veri]
    ekran(f"ekran/{uzanti}", veri=veri)
    d = degerlendir(f"Görsel: ekran/{uzanti} — temiz.", calisma)
    assert d.gorseller[0].gecerli, d.gorseller[0].gerekce
    assert d.sonuc == KANITLI


def test_uzanti_yanlis_imza_reddedilir(calisma, ekran):
    """Metin dosyası `.png` adıyla duruyor: gözlemlenen kanıt DEĞİLDİR."""
    ekran("ekran/panel.png", veri=b"Bu bir metin dosyasi, PNG degil.\n")
    d = degerlendir("Görsel: ekran/panel.png — panel harika.", calisma)
    assert d.sonuc == KANITSIZ
    assert "imza" in d.gorseller[0].gerekce


def test_jpg_uzantili_png_dosyasi_reddedilir(calisma, ekran):
    ekran("ekran/panel.jpg", veri=PNG)
    d = degerlendir("Görsel: ekran/panel.jpg — temiz.", calisma)
    assert d.gorseller[0].gecerli is False


def test_bos_dosya_reddedilir(calisma, ekran):
    ekran("ekran/panel.png", veri=b"")
    d = degerlendir("Görsel: ekran/panel.png — temiz.", calisma)
    assert d.sonuc == KANITSIZ
    assert "bos" in d.gorseller[0].gerekce


def test_yok_dosya_kanitsiz(calisma):
    d = degerlendir("Görsel: ekran/yok.png — kusur yok.", calisma)
    assert d.sonuc == KANITSIZ
    assert "yok" in d.gorseller[0].gerekce


def test_nokta_nokta_kacisi_reddedilir(calisma, ekran):
    ekran()
    d = degerlendir("Görsel: ../kacis.png — temiz.", calisma)
    assert d.gorseller[0].gecerli is False
    assert d.sonuc == KANITSIZ


def test_derin_nokta_nokta_kacisi_reddedilir(calisma, ekran):
    ekran()
    d = degerlendir("Görsel: a/b/../../../kacis.png — temiz.", calisma)
    assert d.gorseller[0].gecerli is False


def test_mutlak_yol_calisma_dizini_disi_reddedilir(calisma, ekran, tmp_path):
    dis = tmp_path / "dis.png"
    dis.write_bytes(PNG)
    ekran()
    d = degerlendir(f"Görsel: {dis} — temiz.", calisma)
    assert d.gorseller[0].gecerli is False
    assert d.sonuc == KANITSIZ


def test_sembolik_bag_kacisi_reddedilir(calisma, ekran, tmp_path):
    """Çalışma dizini içindeki sembolik link DIŞARI çıkıyorsa reddedilir."""
    dis = tmp_path / "dis.png"
    dis.write_bytes(PNG)
    calisma.mkdir(parents=True, exist_ok=True)
    (calisma / "ekran").mkdir(exist_ok=True)
    try:
        (calisma / "ekran" / "panel.png").symlink_to(dis)
    except (OSError, NotImplementedError):  # pragma: no cover — Windows/symlink yok
        pytest.skip("sembolik bag olusturulamadi")
    d = degerlendir("Görsel: ekran/panel.png — temiz.", calisma)
    assert d.gorseller[0].gecerli is False
    assert d.sonuc == KANITSIZ


def test_sembolik_bag_dizin_ici_gecerli(calisma, ekran):
    ekran("ekran/gercek.png")
    (calisma / "ekran").mkdir(parents=True, exist_ok=True)
    try:
        (calisma / "ekran" / "panel.png").symlink_to(calisma / "ekran" / "gercek.png")
    except (OSError, NotImplementedError):  # pragma: no cover
        pytest.skip("sembolik bag olusturulamadi")
    d = degerlendir("Görsel: ekran/panel.png — temiz.", calisma)
    assert d.gorseller[0].gecerli is True


def test_mtime_eski_reddedilir(calisma, ekran):
    ekran("ekran/panel.png", yaz=-7200)  # 2 saat önce
    d = degerlendir(
        "Görsel: ekran/panel.png — temiz.",
        calisma,
        baslangic="2026-01-01T00:00:00Z",
    )
    # baslangic 1970 -> mtime yeni sayilir; gercek eski test icin guncel baslangic:
    import datetime as _dt

    yarin = (_dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(days=1)).isoformat()
    d2 = degerlendir("Görsel: ekran/panel.png — temiz.", calisma, baslangic=yarin)
    assert d2.gorseller[0].gecerli is False
    assert d2.gorseller[0].yeni_mi is False
    assert d2.sonuc == KANITSIZ


def test_mtime_yeni_kabul_edilir(calisma, ekran):
    ekran("ekran/panel.png", yaz=600)
    import datetime as _dt

    d = degerlendir(
        "Görsel: ekran/panel.png — temiz.",
        calisma,
        baslangic=(_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=1)).isoformat(),
    )
    assert d.gorseller[0].gecerli is True
    assert d.gorseller[0].yeni_mi is True


def test_bir_tanesi_gecerliyse_kanitli(calisma, ekran):
    ekran("ekran/iyi.png")
    d = degerlendir(
        "Görsel: ekran/iyi.png — temiz.\nGörsel: ekran/kotu.png — sorun var.",
        calisma,
    )
    assert d.gecerli_gorsel_sayisi == 1
    assert d.sonuc == KANITLI


# =========================================================================
# 4) İddia (BEYAN) vs GÖZLEMLENEN kanıt
# =========================================================================


@pytest.mark.parametrize(
    "cumle",
    [
        "Etiket hizalaması giderildi.",
        "Hata düzeltildi ve testler yeşil.",
        "Panel artık sorunsuz çalışıyor.",
        "Sonuç hatasız.",
        "Yerleşim mükemmel.",
        "Hiçbir etiket daireye binmiyor.",
        "Tüm dosyalar eksiksiz.",
        "Everything is fixed.",
        "Issue resolved.",
        "No issues found.",
        "The filter works.",
        "All tests pass.",
        "I added a new endpoint.",
        "Bu dosyayı değiştirdim.",
    ],
)
def test_kanitsiz_olan_iddia_tespit_edilir(cumle, calisma):
    d = degerlendir(cumle + "\nBu da uzun bir açıklama cümlesi.", calisma)
    assert d.iddialar, f"iddia yakalanmadi: {cumle!r}"
    assert d.sonuc == KANITSIZ
    assert any(g.kural == "iddia-kanitsiz" for g in d.gerekceler)


def test_iddia_ama_gorsel_yolu_yok_kanitli_cikmaz(calisma):
    """Duyarlılık (b): iddia var, görsel YOLU bile yok → kanıtlı ÇIKMAMALI."""
    d = degerlendir(
        "Panel mükemmel görünüyor, hiçbir etiket binmiyor ve her şey giderildi.",
        calisma,
    )
    assert d.sonuc == KANITSIZ
    assert d.gorseller == []


def test_iddia_ama_gorsel_bos_dosya_kanitli_cikmaz(calisma, ekran):
    """Duyarlılık (b): iddia var, görsel yolu VAR ama dosya boş → kanıtlı ÇIKMAMALI."""
    ekran("ekran/panel.png", veri=b"")
    d = degerlendir(
        "Her şey giderildi, panel sorunsuz.\nGörsel: ekran/panel.png — temiz.",
        calisma,
    )
    assert d.sonuc == KANITSIZ


def test_iddia_ve_gecerli_gorsel_kanitli(calisma, ekran):
    """Duyarlılık (c): gerçek PNG + yolunu yazan rapor → KANITLI."""
    ekran()
    d = degerlendir(
        "Her şey giderildi.\nGörsel: ekran/panel.png — hizalama temiz.\n525 passed.",
        calisma,
    )
    assert d.sonuc == KANITLI
    assert d.gozlemlenen_kanit_sayi() >= 1
    assert len(d.iddialar) >= 1


def test_beyan_kanit_saymaz(calisma):
    d = degerlendir("525 passed in 65s. Tum testler yesil.", calisma)
    assert d.testler[0].passed == 525
    assert d.gozlemlenen_kanit_sayi() == 0
    assert d.sonuc == KANITSIZ


# =========================================================================
# 5) Git kanıtı
# =========================================================================


def test_git_degisti_kanit(calisma, ekran):
    ekran()
    d = degerlendir(
        "Dosyayi yeniden yazdim.\nGörsel: ekran/panel.png — temiz.", calisma,
        git_once="abc\n", git_sonra="abc\nM dosya\n",
    )
    assert d.git_degisti is True
    assert d.sonuc == KANITLI


def test_git_degismedi_kanitsiz(calisma):
    d = degerlendir(
        "Degisiklikleri yazdim ve commit ettim, kod hazir.", calisma,
        git_once="abc\n", git_sonra="abc\n",
    )
    assert d.git_degisti is False
    assert d.sonuc == KANITSIZ
    assert any(g.kural == "degisim-iddiasi-kanitsiz" for g in d.gerekceler)


def test_git_bilmiyorsa_kural_islemez(calisma, ekran):
    ekran()
    d = degerlendir(
        "Dosyayi yazdim.\nGörsel: ekran/panel.png — temiz.", calisma,
        git_once=None, git_sonra=None,
    )
    assert d.git_degisti is None
    assert d.sonuc == KANITLI


def test_git_ozeti_depo_dedisinde_none(tmp_path):
    import subprocess

    try:
        tamam = subprocess.run(
            ["git", "--version"], capture_output=True, timeout=10, check=False
        )
    except (OSError, subprocess.SubprocessError):  # pragma: no cover
        pytest.skip("git yok")
    if tamam.returncode != 0:  # pragma: no cover
        pytest.skip("git yok")
    bos = tmp_path / "bos"
    bos.mkdir()
    assert report.git_ozeti(bos) is None


def test_git_ozeti_degisen_agaci_ayirt_edir(tmp_path):
    import subprocess

    try:
        subprocess.run(["git", "--version"], capture_output=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):  # pragma: no cover
        pytest.skip("git yok")
    depo = tmp_path / "depo"
    depo.mkdir()
    for argv in (
        ["git", "init", "-q"],
        ["git", "config", "user.email", "kurgusal@ornek.invalid"],
        ["git", "config", "user.name", "Kurgusal"],
    ):
        r = subprocess.run(argv, cwd=depo, capture_output=True, check=False)
        if r.returncode != 0:  # pragma: no cover
            pytest.skip("git init calisamadi")
    (depo / "a.txt").write_text("kurgusal\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=depo, capture_output=True, check=False)
    subprocess.run(["git", "commit", "-qm", "kurgusal"], cwd=depo, capture_output=True,
                   check=False)
    once = report.git_ozeti(depo)
    assert once is not None
    (depo / "b.txt").write_text("kurgusal\n", encoding="utf-8")
    sonra = report.git_ozeti(depo)
    assert sonra is not None and sonra != once


# =========================================================================
# 6) Kısa rapor
# =========================================================================


def test_bos_rapor_kanitsiz(calisma):
    d = degerlendir("", calisma)
    assert d.sonuc == KANITSIZ


def test_cok_kisa_rapor_kanitsiz(calisma):
    d = degerlendir("bitti", calisma)
    assert d.sonuc == KANITSIZ
    assert any(g.kural == "kisa-rapor" for g in d.gerekceler)


# =========================================================================
# 7) `## Kanıt` bölümü biçimi
# =========================================================================


def test_kanit_bolumu_oncelikli_okunur(calisma, ekran):
    ekran("ekran/panel.png")
    d = degerlendir(
        "Serbest metinde baska/baska.png gecir ama o calisma disinda.\n\n"
        "## Kanıt\n"
        "- Test: python3 -m pytest -q → 42 passed in 1.2s\n"
        "- Görsel: ekran/panel.png — etiketler hizali\n",
        calisma,
    )
    # Kanıt bölümü öncelikli: serbest metindeki yol PARÇALANMAZ.
    assert d.sonuc == KANITLI
    assert [g.yol for g in d.gorseller] == ["ekran/panel.png"]
    assert d.testler[0].passed == 42
    assert d.gorsel_beyanlar
    assert any("Test:" in b and "42 passed" in b for b in d.beyanlar)
    assert any("Görsel: ekran/panel.png" in b for b in d.beyanlar)


def test_kanit_bolumu_yoksa_serbest_metinden_okunur(calisma, ekran):
    """Eski istemler bu biçimi bilmez; eksikliği tek başına hata DEĞİLDİR."""
    ekran()
    d = degerlendir("Bosluklari ayarladim.\n`docs/ekran/panel.png` gorunuyor.", calisma)
    assert d.sonuc == KANITLI


def test_kanit_bolumu_bosluk_birakir(calisma, ekran):
    ekran()
    d = degerlendir(
        "## Kanıt\n- Test: pytest → gözlemlenmedi\n"
        "- Görsel: ekran/panel.png — gözlemlenmedi\n\n## Sonuç\nMetin.",
        calisma,
    )
    assert d.sonuc == KANITLI


# =========================================================================
# 8) Rapor dosyası
# =========================================================================


def test_rapor_dosyasi_katilir(calisma, ekran):
    ekran()
    (calisma / ".rapor.md").write_text(
        "## Kanıt\n- Görsel: ekran/panel.png — temiz\n- Test: pytest → 7 passed\n",
        encoding="utf-8",
    )
    d = degerlendir("ozet: bitti", calisma, rapor_dosyasi=".rapor.md")
    assert d.sonuc == KANITLI
    assert d.gorseller[0].gecerli


def test_rapor_dosyasi_yok_kanitsiz(calisma):
    d = degerlendir("bir seyler yazildi", calisma, rapor_dosyasi="yok.md")
    assert d.sonuc == KANITSIZ
    assert any("rapor dosyasi yok" in g.kanit for g in d.gerekceler)


def test_rapor_dosyasi_kacisi_reddedilir(calisma, tmp_path):
    dis = tmp_path / "dis.md"
    dis.write_text("Görsel: x.png\n", encoding="utf-8")
    d = degerlendir("metin", calisma, rapor_dosyasi=str(dis))
    assert d.sonuc == KANITSIZ
    assert any("calisma dizini disinda" in g.kanit for g in d.gerekceler)


def test_rapor_dosyasi_nokta_nokta_reddedilir(calisma):
    d = degerlendir("metin", calisma, rapor_dosyasi="../gizli.md")
    assert d.sonuc == KANITSIZ


def test_rapor_dosyasi_mutlak_disi_reddedilir(calisma, tmp_path):
    d = degerlendir("metin", calisma, rapor_dosyasi=str(tmp_path / "x.md"))
    assert d.sonuc == KANITSIZ


def test_rapor_dosyasi_512kib_ustu_reddedilir(calisma):
    (calisma).mkdir(parents=True, exist_ok=True)
    buyuk = calisma / "buyuk.md"
    buyuk.write_text("x" * (report.RAPOR_DOSYASI_TAVAN + 10), encoding="utf-8")
    d = degerlendir("metin", calisma, rapor_dosyasi="buyuk.md")
    assert d.sonuc == KANITSIZ
    assert any("bayt asiyor" in g.kanit for g in d.gerekceler)


def test_rapor_dosyasi_tam_sinirda_kabul(calisma, ekran):
    (calisma).mkdir(parents=True, exist_ok=True)
    ekran()
    dosya = calisma / "tam.md"
    govde = "## Kanıt\n- Görsel: ekran/panel.png — temiz\n" + "x" * (
        report.RAPOR_DOSYASI_TAVAN - 60
    )
    dosya.write_text(govde, encoding="utf-8")
    assert dosya.stat().st_size <= report.RAPOR_DOSYASI_TAVAN
    d = degerlendir("metin", calisma, rapor_dosyasi="tam.md")
    assert d.sonuc == KANITLI


# =========================================================================
# 9) Maskeleme
# =========================================================================


def test_sahte_anahtar_ozete_girmez(calisma, ekran):
    """Rapordaki sahte anahtar kanıt özetine ve web'e HAM girmez."""
    ekran()
    # Parça parça üretilmiş AÇIKÇA SAHTE anahtar (gerçek biçimde ama uydurma).
    sahte = "sk-" + "0" * 8 + "A" * 7 + "9" + "b" * 20
    metin = (
        "## Kanıt\n"
        "- Test: python3 -m pytest -q → 42 passed\n"
        f"- Görsel: ekran/panel.png — {sahte} hizasinda sorun yok\n"
        f"\nAnahtarı {sahte} ile denedim, panel mükemmel.\n"
    )
    d = degerlendir(metin, calisma)
    ham = json.dumps(d.json(), ensure_ascii=False)
    assert sahte not in ham, "HAM anahtar kanıt özetine sızdı"
    assert "[maskeli]" in ham, "maskeleme uygulanmadi"
    # Kanıt BÖLÜMÜ de maskeli saklanmalı.
    assert all(sahte not in b for b in d.beyanlar)
    assert all(sahte not in i for i in d.iddialar)
    assert d.sonuc == KANITLI


def test_maskeleme_gercek_dosya_yolunu_bozmaz(calisma, ekran):
    ekran("ekran/panel.png")
    d = degerlendir("Görsel: ekran/panel.png — temiz.", calisma)
    assert d.gorseller[0].gecerli is True


# =========================================================================
# 10) Kurgusal rap fixture'ları — gerçek rapor YAPISINDAN
# =========================================================================
# Yapı: "## N. Başlık" bölümleri, değişen dosya tablosu, pytest özeti, uydurma
# proje/ajan/sayı. İçerik bu oturumdaki gerçek raporlardan KOPYALANMADI.

FIXTURE_YAPILI_BASARILI = """# Kurgusal Proje — Dalga B Raporu (kurgusal veri)

Kapsam: `ornek/modul.py`, `ornek/web/`, testler. KOMİT/PUSH YAPILMADI.

## 1. Değişen dosyalar

| Dosya | Satır | Ne |
|---|---|---|
| `ornek/modul.py` | 210 | ayrıştırıcı |
| `docs/ekran/panel.png` | 1 | kurgusal ekran görüntüsü |

## 2. Pytest özeti

```
$ python3 -m pytest -q
418 passed in 51.20s (0:00:51)
```

## 3. Ekran görüntüleri

`docs/ekran/panel.png` alındı ve **Read ile görüldü**.

## 4. Bulduğum hata

Tablodaki hizalama giderildi, panel artık sorunsuz.
"""

FIXTURE_IDDIA_KANITSIZ = """# Kurgusal Proje — Dalga A Raporu (kurgusal veri)

İş tamamlandı, hiçbir sorun kalmadı.

## Sonuç

Filtre kuralı yazıldı ve mükemmel çalışıyor. Tüm dosyalar eksiksiz.
Testler: 210 passed diye yazıyordu ama ekran görüntüsü alınmadı.
"""

FIXTURE_GORSEL_YOK = """# Kurgusal Proje — kısa rapor (kurgusal veri)

Daireler etiketlerin üstüne biniyordu, bu giderildi. Hizalama artık mükemmel.
Görsel dosyası ekran görüntüsünü hiç kaydetmedim ama her şey doğru.
"""

FIXTURE_BASARISIZ = """# Kurgusal Proje — hatalı koşu (kurgusal veri)

## Test özeti

```
3 failed, 210 passed in 44.10s
```
"""

FIXTURE_REDDEDILME = """# Kurgusal Proje — engellenen koşu (kurgusal veri)

I was blocked from running the deployment command by the permission layer,
so nothing in the repository was modified.
"""

FIXTURE_IZIN_KOD_RAHAT = """# Kurgusal Proje — izin kodu (kurgusal veri)

## Değişiklikler

`ornek/runner.py` içindeki IZIN_REDDI_DESENI genişletildi. Testi: permission
denied senaryosu onay-bekliyor üretmeli. PermissionError yakalanıyor.

## Kanıt
- Test: python3 -m pytest -q → 305 passed in 30.11s
- Görsel: ekran/panel.png — panel temiz
"""


def _fixture_uzanti(calisma):
    ekran_d = calisma / "docs" / "ekran"
    ekran_d.mkdir(parents=True, exist_ok=True)
    (ekran_d / "panel.png").write_bytes(PNG)
    return ekran_d


def test_fixture_basarisiz_kanitli(calisma):
    _fixture_uzanti(calisma)
    d = degerlendir(FIXTURE_YAPILI_BASARILI, calisma)
    assert d.sonuc == KANITLI
    assert d.gecerli_gorsel_sayisi == 1
    assert d.testler[0].passed == 418


def test_fixture_iddia_kanitsiz(calisma):
    d = degerlendir(FIXTURE_IDDIA_KANITSIZ, calisma)
    assert d.sonuc == KANITSIZ
    assert len(d.iddialar) >= 2


def test_fixture_gorsel_yok_kanitsiz(calisma):
    d = degerlendir(FIXTURE_GORSEL_YOK, calisma)
    assert d.sonuc == KANITSIZ
    assert d.gorseller == []


def test_fixture_basarısız(calisma):
    d = degerlendir(FIXTURE_BASARISIZ, calisma)
    assert d.sonuc == BASARISIZ
    assert d.testler[0].failed == 3


def test_fixture_reddedilme(calisma):
    d = degerlendir(FIXTURE_REDDEDILME, calisma)
    assert d.sonuc == REDDEDILDI


def test_fixture_izin_kod_rahati_kanitli(calisma):
    _fixture_uzanti(calisma)
    d = degerlendir(FIXTURE_IZIN_KOD_RAHAT, calisma)
    assert d.sonuc == KANITLI
    assert d.testler[0].passed == 305


@pytest.mark.parametrize(
    "ad, beklenen",
    [
        ("basarisili", KANITLI),
        ("iddia", KANITSIZ),
        ("gorsel_yok", KANITSIZ),
        ("basarisiz", BASARISIZ),
        ("reddedilme", REDDEDILDI),
        ("izin_kod", KANITLI),
    ],
)
def test_fixture_dagilimi(calisma, ad, beklenen):
    _fixture_uzanti(calisma)
    metin = {
        "basarisili": FIXTURE_YAPILI_BASARILI,
        "iddia": FIXTURE_IDDIA_KANITSIZ,
        "gorsel_yok": FIXTURE_GORSEL_YOK,
        "basarisiz": FIXTURE_BASARISIZ,
        "reddedilme": FIXTURE_REDDEDILME,
        "izin_kod": FIXTURE_IZIN_KOD_RAHAT,
    }[ad]
    assert degerlendir(metin, calisma).sonuc == beklenen


# =========================================================================
# 11) JSON çevrilebilirlik / API sözleşmesi
# =========================================================================


def test_json_sozlesmesi(calisma, ekran):
    ekran()
    d = degerlendir("Her sey giderildi.\nGörsel: ekran/panel.png — temiz.", calisma)
    veri = d.json()
    json.dumps(veri)  # serileştirilebilir olmalı
    assert veri["sonuc"] == KANITLI
    assert veri["sonuc_etiket"] == "kanıtlı"
    assert veri["gozlemlenen_kanit_sayi"] >= 1
    assert "beyanlar" in veri and "gorsel_beyanlar" in veri


def test_ozet_metin_miktari(calisma, ekran):
    ekran()
    d = degerlendir("Görsel: ekran/panel.png — temiz.", calisma)
    assert "kanıtlı" in d.ozet_metin()


def test_sonuc_etiketleri_renk_korusu(calisma, ekran):
    """Her sınıfın METİN etiketi var: rozet renge tek başına dayanmaz."""
    for sinif, etiket in report.SONUC_ETIKETLERI.items():
        assert etiket and etiket != sinif


def test_saf_fonksiyon_dosya_yazmaz(calisma, ekran):
    ekran()
    once = sorted(p.name for p in calisma.rglob("*"))
    degerlendir("Görsel: ekran/panel.png — temiz.", calisma)
    assert sorted(p.name for p in calisma.rglob("*")) == once


def test_imza_tur_bilinenler():
    assert report.imza_tur(PNG) == "png"
    assert report.imza_tur(GIF) == "gif"
    assert report.imza_tur(JPEG) == "jpeg"
    assert report.imza_tur(WEBP) == "webp"
    assert report.imza_tur(b"metin dosyasi") == ""
    assert report.imza_tur(b"") == ""


def test_guvenli_coz_kacislari(tmp_path):
    kok = tmp_path / "kok"
    kok.mkdir()
    (kok / "a.png").write_bytes(PNG)
    # `guvenli_cöz` yalnız KAPSAMA denetler; varlık `_gorseli_denetle`'de.
    assert report.guvenli_cöz("a.png", kok) is not None
    assert report.guvenli_cöz("yok.png", kok) is not None
    assert report.guvenli_cöz("../a.png", kok) is None
    assert report.guvenli_cöz("/etc/passwd", kok) is None
    assert report.guvenli_cöz("", kok) is None
    assert report.guvenli_cöz(kok, kok) is None  # kökün kendisi reddedilir


# --- Ana oturum incelemesinde bulunan yanlış pozitifler (2026-09-30) -----------

@pytest.mark.parametrize("metin", [
    "Yeni bağımlılık eklemedim. Commit atmadım, push yapmadım (görev kuralı).",
    "Planlanan görevleri bilerek ÇALIŞTIRMADIM: yalnız kuyruğa eklendi (çalıştırılmadı).",
    "İkinci dalgayı yapmadım; kapsam dışıydı.",
])
def test_bilerek_yapilmadi_red_degildir(metin, calisma):
    """'yapmadım/eklemedim/çalıştırılmadı' BİLEREK yapılmayanı anlatır; engel bildirimi değil."""
    d = degerlendir(metin + "\n" + "x" * 60, calisma)
    assert d.sonuc != REDDEDILDI, d.gerekceler


def test_eski_basarisizlik_anilan_ama_guncel_temiz_rapor_basarisiz_degil(calisma):
    metin = (
        "Önce: 524 passed, 1 failed (zaman bombası testi). Düzelttim.\n"
        "Şimdi: 738 passed in 148.09s\n"
        + "x" * 60
    )
    d = degerlendir(metin, calisma)
    assert d.sonuc != BASARISIZ, d.gerekceler
    assert any("onceki" in u for u in d.uyarilar)


def test_guncel_buyuk_kosu_basarisizsa_rapor_basarisiz(calisma):
    metin = "Önce: 524 passed\nSon: 700 passed, 3 failed in 90s\n" + "x" * 60
    assert degerlendir(metin, calisma).sonuc == BASARISIZ
