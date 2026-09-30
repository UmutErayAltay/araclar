"""Dalga D koşu entegrasyonu: duyarlılık sınamaları, göç, CLI, web.

Duyarlılık sınamaları (kabul kriteri 2) buradadır:
  (a) ÇIKIŞ KODU 0 + reddetme metni → görev `onay-bekliyor` (bugün `bitti` idi)
  (b) iddia var, görsel yolu yok/boş → `kanitli` ÇIKMAZ
  (c) gerçek PNG üreten sahte koşu → `kanitli`
  (d) `kanitli`/`kanitsiz` oranı fixture'larda beklenen dağılımda
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from orkestra import report
from orkestra.models import Durum, RunSonuc
from orkestra.queue import SEMA, Queue, _goc
from orkestra.runner import FakeRunner

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64

# Çıkış kodu 0 AMA reddetme metni: bugünkü en kritik boşluk.
RED_METNI = (
    "Görevin geri kalanını ekleyemedim.\n"
    "I was blocked from running the migration command by the permission layer.\n"
)


def _calisma_gecerli_png(dizin: Path, ad="ekran/panel.png") -> Path:
    dosya = dizin / ad
    dosya.parent.mkdir(parents=True, exist_ok=True)
    dosya.write_bytes(PNG)
    return dosya


# =========================================================================
# (a) DUYARLILIK: çıkış kodu 0 + reddetme metni
# =========================================================================


class _SifirCikisliRedGorevci:
    """`claude -p` reddi bildirip YİNE 0 ile biten sahte çalıştırıcı.

    `IZIN_REDDI_DESENI` yalnız sıfırdan farklı çıkışta bakıldığı için
    runner `onay_gerekli` ÜRETMEZ — kanıt katmanı bunu yakalamalıdır.
    Gerçek akışta `claude -p` çıktısı bir LOG DOSYASINA yazılır; burada da
    öyle yapılır (kanıt katmanı log'u okur).
    """
    cwd = None

    def __init__(self, metin: str = RED_METNI, log_dizini: Path | None = None):
        self.metin = metin
        self._dizin = log_dizini

    def calistir(self, task) -> RunSonuc:
        if self._dizin is None:
            return RunSonuc(cikis_kodu=0, cikti=None, kanit_yollari=[])
        self._dizin.mkdir(parents=True, exist_ok=True)
        log = self._dizin / f"{task.id}.log"
        log.write_text(self.metin, encoding="utf-8")
        return RunSonuc(cikis_kodu=0, cikti=str(log), kanit_yollari=[])


def test_sifir_cikisli_red_onay_bekliyor_olur(kuyruk, tmp_path):
    """BUGÜNKÜ DAVRANIŞ: görev `bitti` olurdu. DOĞRUSU: `onay-bekliyor`."""
    gorev = kuyruk.ekle("kizil-zarif", "kurgusal red senaryosu")
    sonuc = kuyruk.calistir_bir(_SifirCikisliRedGorevci(log_dizini=tmp_path))
    assert sonuc is not None
    gorev, kosu = sonuc
    assert kosu.cikis_kodu == 0, "sahte runner gerçekten 0 döndü"
    assert kosu.kanit_durumu == report.REDDEDILDI
    assert gorev.durum == Durum.ONAY_BEKLIYOR, (
        "çıkış kodu 0 olsa bile red metni `onay-bekliyor` üretmeli"
    )


def test_sifir_cikisli_red_runs_hata_alani(kuyruk, tmp_path):
    """`runs.hata` mevcut onay akışının okuduğu MAKİNE işaretini alır."""
    from orkestra.queue import IZIN_REDDI_SUPHESI

    gorev = kuyruk.ekle("kizil-zarif", "kurgusal red senaryosu")
    gorev, kosu = kuyruk.calistir_bir(_SifirCikisliRedGorevci(log_dizini=tmp_path))
    assert kosu.hata == IZIN_REDDI_SUPHESI == "izin-reddi-suphesi"


def test_sifir_cikisli_red_tekrar_denemez(kuyruk, tmp_path):
    """`onay-bekliyor` terminal değildir ama otomatik yeniden deneme YOK."""
    gorev = kuyruk.ekle("kizil-zarif", "kurgusal red senaryosu")
    gorev, _ = kuyruk.calistir_bir(_SifirCikisliRedGorevci(log_dizini=tmp_path))
    assert gorev.durum == Durum.ONAY_BEKLIYOR
    # Yeniden deneme YALNIZCA açık `tekrar` ile otomatik olmaz.
    assert kuyruk.calistir_bir(_SifirCikisliRedGorevci(log_dizini=tmp_path)) is None


# =========================================================================
# (b) ve (c) DUYARLILIK: iddia var ama kanıt yok / gerçek PNG
# =========================================================================


def test_iddia_var_kanit_yok_kanitli_cikmaz(kuyruk, tmp_path):
    gorev = kuyruk.ekle("kizil-zarif", "kurgusal iddia senaryosu")
    sonuc = kuyruk.calistir_bir(_MetinGorevci("Her şey giderildi, panel mükemmel."))
    _, kosu = sonuc
    assert kosu.kanit_durumu == report.KANITSIZ
    assert kosu.kanit_durumu != report.KANITLI


def test_bos_dosya_kanitli_cikmaz(kuyruk, tmp_path):
    dizin = tmp_path / "calisma"
    dizin.mkdir()
    (dizin / "ekran").mkdir()
    (dizin / "ekran" / "panel.png").write_bytes(b"")
    gorev = kuyruk.ekle("kizil-zarif", "kurgusal bos dosya")
    sonuc = kuyruk.calistir_bir(
        _MetinGorevci("Görsel: ekran/panel.png — kusur yok, her şey giderildi.",
                      calisma=dizin)
    )
    _, kosu = sonuc
    assert kosu.kanit_durumu == report.KANITSIZ


def test_gercek_png_uretten_kosu_kanitli(kuyruk, tmp_path):
    """Sahte koşu GERÇEK PNG üretip yolunu rapora yazınca `kanitli` olmalı."""
    dizin = tmp_path / "calisma"
    dizin.mkdir()

    def _uret(task) -> RunSonuc:
        _calisma_gecerli_png(dizin)
        log = dizin / "ajan.log"
        log.write_text(
            "## Kanıt\n"
            "- Test: python3 -m pytest -q → 42 passed in 1.20s\n"
            "- Görsel: ekran/panel.png — hizalama temiz, kusur yok\n",
            encoding="utf-8",
        )
        return RunSonuc(cikis_kodu=0, cikti=str(log), kanit_yollari=[])

    class _Gorevci(_SifirCikisliRedGorevci):
        def calistir(self, task) -> RunSonuc:
            return _uret(task)

    gorevci = _Gorevci()
    gorevci.cwd = str(dizin)
    kuyruk.ekle("kizil-zarif", "kurgusal basarili kosu")
    gorev, kosu = kuyruk.calistir_bir(gorevci)
    assert kosu.kanit_durumu == report.KANITLI
    assert kosu.kanit_ozeti["gozlemlenen_kanit_sayi"] == 1
    assert kosu.kanit_ozeti["testler"][0]["passed"] == 42


class _MetinGorevci:
    """Verilen metni log dosyasına yazıp 0 ile biten sahte çalıştırıcı."""

    cwd = None

    def __init__(self, metin: str, calisma: Path | None = None):
        self.metin = metin
        self._calisma = calisma

    def calistir(self, task) -> RunSonuc:
        if self._calisma is None:
            return RunSonuc(cikis_kodu=0, cikti=None)
        log = self._calisma / "ajan.log"
        log.write_text(self.metin, encoding="utf-8")
        return RunSonuc(cikis_kodu=0, cikti=str(log))


# =========================================================================
# (d) Dagilim: kanitli / kanitsiz orani
# =========================================================================


def test_dagilim_kanitli_kanitsiz(kuyruk, tmp_path):
    dizin = tmp_path / "calisma"
    dizin.mkdir()
    _calisma_gecerli_png(dizin)

    def _kosu(metin):
        gorevci = _MetinGorevci(metin, calisma=dizin)
        gorevci.cwd = str(dizin)
        kuyruk.ekle("kizil-zarif", "kurgusal dagilim")
        _, kosu = kuyruk.calistir_bir(gorevci)
        return kosu.kanit_durumu

    kanitli = _kosu("Görsel: ekran/panel.png — temiz.\n525 passed in 60s.")
    kanitsiz = _kosu("Her şey giderildi, hizalama mükemmel.")
    basarisiz = _kosu("3 failed, 10 passed in 4.5s\nGörsel: ekran/panel.png — x")
    assert kanitli == report.KANITLI
    assert kanitsiz == report.KANITSIZ
    assert basarisiz == report.BASARISIZ
    # Beklenen dağılım: her sınıf temsil edilir, "her şey kanıtlı" değil.
    assert len({kanitli, kanitsiz, basarisiz}) == 3


# =========================================================================
# Durum makinesine yeni durum EKLENMEZ
# =========================================================================


def test_durum_makinesi_degismedi(kuyruk):
    gorev = kuyruk.ekle("kizil-zarif", "kurgusal durum testi")
    kuyruk.calistir_bir(_SifirCikisliRedGorevci())
    # `bitti` görev kanıtsız olsa da `bitti` KALIR (terminal).
    kuyruk.ekle("kizil-zarif", "kurgusal kanitsiz basari")
    _, kosu = kuyruk.calistir_bir(_MetinGorevci("Her şey giderildi."))
    assert kosu.kanit_durumu == report.KANITSIZ
    gorev2 = kuyruk.al(2)
    assert gorev2.durum == Durum.BITTI, "kanitsiz `bitti` görev `bitti` kalmali"
    # Durum listesi DALGA C ile aynı (yeni durum yok).
    assert [d.value for d in Durum] == [
        "bekliyor", "calisiyor", "bitti", "hata", "onay-bekliyor", "iptal"
    ]


def test_kosu_kanit_yaz_db_guncellenir(kuyruk):
    kuyruk.ekle("kizil-zarif", "kurgusal yazma testi")
    _, kosu = kuyruk.calistir_bir(_SifirCikisliRedGorevci())
    kuyruk.run_kanit_yaz(kosu.id, report.KANITLI, {"ozet": "kurgusal"})
    yenilenmis = kuyruk.run_bul(kosu.id)
    assert yenilenmis.kanit_durumu == report.KANITLI
    assert yenilenmis.kanit_ozeti == {"ozet": "kurgusal"}


# =========================================================================
# Sema göçü: eski DB veri KAYBETMEDEN yükselir
# =========================================================================

ESKI_SEMA = """
CREATE TABLE tasks (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ajan      TEXT NOT NULL,
    istem     TEXT NOT NULL,
    durum     TEXT NOT NULL,
    olusturma TEXT NOT NULL
);
CREATE TABLE runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id       INTEGER NOT NULL REFERENCES tasks(id),
    baslangic     TEXT NOT NULL,
    bitis         TEXT,
    cikis_kodu     INTEGER,
    cikti_yolu    TEXT,
    kanit_yollari TEXT,
    hata          TEXT
);
"""


def test_goc_eski_sema_veri_kalir(tmp_path):
    """Eski şema ELLE kurulur, veri eklenir, Queue açılır: veri durur."""
    yol = tmp_path / "eski.db"
    b = sqlite3.connect(yol)
    b.executescript(ESKI_SEMA)
    b.execute(
        "INSERT INTO tasks (ajan,istem,durum,olusturma) VALUES (?,?,?,?)",
        ("kizil-zarif", "ESKI GOREV METNI", "bitti", "2026-01-01T00:00:00Z"),
    )
    b.execute(
        "INSERT INTO runs (task_id,baslangic,bitis,cikis_kodu,cikti_yolu,kanit_yollari,hata)"
        " VALUES (?,?,?,?,?,?,?)",
        (1, "2026-01-01T00:00:00Z", "2026-01-01T00:01:00Z", 0,
         "/tmp/eski.log", "[]", None),
    )
    b.commit()
    b.execute("PRAGMA user_version=0")
    b.commit()
    b.close()

    # Önce: yeni sütunlar YOK.
    b = sqlite3.connect(yol)
    assert "kanit_durumu" not in {s[1] for s in b.execute("PRAGMA table_info(runs)")}
    b.close()

    kuyruk = Queue(yol)
    try:
        # Yeni sütunlar eklendi.
        runs_sutun = {s[1] for s in kuyruk.baglanti_al().execute("PRAGMA table_info(runs)")}
        tasks_sutun = {s[1] for s in kuyruk.baglanti_al().execute("PRAGMA table_info(tasks)")}
        assert {"kanit_durumu", "kanit_ozeti"} <= runs_sutun
        assert "rapor_dosyasi" in tasks_sutun
        # ESKİ VERİ DURUYOR.
        gorev = kuyruk.al(1)
        assert gorev.ajan == "kizil-zarif"
        assert gorev.istem == "ESKI GOREV METNI"
        kosular = kuyruk.kosular(1)
        assert len(kosular) == 1
        assert kosular[0].cikti_yolu == "/tmp/eski.log"
        assert kosular[0].cikis_kodu == 0
        # Yeni alanlar None (değerlendirilmedi).
        assert kosular[0].kanit_durumu is None
        assert kosular[0].kanit_ozeti is None
        # plans tablosu da oluştu.
        assert kuyruk.plan_al(1) is None
    finally:
        kuyruk.kapat()


def test_goc_idempotent(tmp_path):
    """Göç iki kez çalışsa da hata vermez."""
    yol = tmp_path / "idempotent.db"
    kuyruk = Queue(yol)
    sutun1 = {s[1] for s in kuyruk.baglanti_al().execute("PRAGMA table_info(runs)")}
    kuyruk.kapat()
    kuyruk2 = Queue(yol)
    sutun2 = {s[1] for s in kuyruk2.baglanti_al().execute("PRAGMA table_info(runs)")}
    assert sutun1 == sutun2
    kuyruk2.kapat()


def test_goc_user_version(tmp_path):
    yol = tmp_path / "surum.db"
    sqlite3.connect(yol).executescript(ESKI_SEMA).connection.close()
    kuyruk = Queue(yol)
    try:
        surum = kuyruk.baglanti_al().execute("PRAGMA user_version").fetchone()[0]
        assert surum == 2
    finally:
        kuyruk.kapat()


# =========================================================================
# Web: eski DB'de sütun yoksa bozulmaz + salt-okunur
# =========================================================================


def test_web_eski_sema_calisir(tmp_path):
    """Dalga C'den kalmış DB'de kanıt sütunu YOK: panel bozulmaz."""
    from orkestra.web.sunucu import app_olustur

    yol = tmp_path / "eski_panel.db"
    b = sqlite3.connect(yol)
    b.executescript(ESKI_SEMA)
    b.execute(
        "INSERT INTO tasks (ajan,istem,durum,olusturma) VALUES (?,?,?,?)",
        ("kizil-zarif", "ESKI PANEL GOREVI", "bitti", "2026-01-01T00:00:00Z"),
    )
    b.execute(
        "INSERT INTO runs (task_id,baslangic,cikis_kodu) VALUES (?,?,0)",
        (1, "2026-01-01T00:00:00Z"),
    )
    b.commit()
    b.close()

    uygulama = app_olustur(yol)
    istemci = uygulama.test_client()
    cevap = istemci.get("/")
    assert cevap.status_code == 200
    assert b"ESKI PANEL" in cevap.data or b"kizil-zarif" in cevap.data
    # Rozet "değerlendirilmedi" (yeni sınıf) — sayfa yine de çizilir.
    detay = istemci.get("/gorev/1")
    assert detay.status_code == 200
    assert detay.data


def test_web_salt_okunur_kalir(tmp_path):
    """Panel kanıt sütunlarını gördükten sonra da YAZMAZ."""
    from orkestra.web.sunucu import app_olustur

    yol = tmp_path / "ro.db"
    kuyruk = Queue(yol)
    kuyruk.ekle("kizil-zarif", "kurgusal salt okunur")
    kuyruk.calistir_bir(_SifirCikisliRedGorevci())
    kuyruk.kapat()
    once = yol.read_bytes()

    uygulama = app_olustur(yol)
    istemci = uygulama.test_client()
    for yol_ in ("/", "/gorev/1", "/api/gorevler", "/api/gorev/1", "/kota"):
        istemci.get(yol_)
    assert yol.read_bytes() == once, "panel DB'ye YAZDI"


def test_web_maskeleme_kanit_ozetinde(tmp_path):
    """Rapordaki sahte anahtar web API'sine/HTML'sine HAM girmez."""
    from orkestra.web.sunucu import app_olustur

    sahte = "sk-" + "0" * 8 + "A" * 7 + "9" + "b" * 20
    # Ajan raporunda sahte anahtar GEÇİYOR: kanıt katmanı maskeleyerek saklar.
    yol = tmp_path / "maskeli.db"
    kuyruk = Queue(yol)
    gorev = kuyruk.ekle("kizil-zarif", "kurgusal maskeleme")
    _, kosu = kuyruk.calistir_bir(
        _SifirCikisliRedGorevci(metin=f"Panel mükemmel, anahtar {sahte} sızdı.",
                                log_dizini=tmp_path)
    )
    kuyruk.kapat()

    uygulama = app_olustur(yol, cikti_dizini=tmp_path)
    istemci = uygulama.test_client()
    for adres in (f"/api/gorev/{gorev.id}", f"/gorev/{gorev.id}"):
        ham = istemci.get(adres).get_data(as_text=True)
        assert sahte not in ham, f"{adres} ham sahte anahtari sirdi"
        assert "[maskeli]" in ham, f"{adres} maskeleme uygulanmadi"


def test_web_kanit_rozeti_siniflari():
    from orkestra.web.sunucu import KANIT_RENKLERI, KANIT_UYARI, kanit_rozeti

    for sinif in report.SONUC_SINIFLARI:
        satir = {"kanit_durumu": sinif}
        # sqlite.Row benzeri: `.keys()` ve `[]`.
        rozet = kanit_rozeti(_SahteSatir(satir))
        assert rozet["etiket"], f"{sinif} için METİN etiketi yok"
        assert rozet["renk"].startswith("#")
        assert rozet["uyari"] == (sinif in KANIT_UYARI)
    assert set(KANIT_RENKLERI) == set(report.SONUC_SINIFLARI)


def test_web_kanit_rozeti_bilinmeyen_sinif():
    from orkestra.web.sunucu import kanit_rozeti

    rozet = kanit_rozeti(_SahteSatir({"kanit_durumu": "uydurma"}))
    assert rozet["durum"] == report.DEGERLENDIRILMEDI
    rozet2 = kanit_rozeti(_SahteSatir({}))
    assert rozet2["durum"] == report.DEGERLENDIRILMEDI


class _SahteSatir:
    def __init__(self, veri: dict):
        self._veri = veri

    def keys(self):
        return self._veri.keys()

    def __getitem__(self, anahtar):
        return self._veri[anahtar]


# =========================================================================
# Plan kayıtları
# =========================================================================


def test_plan_kaydet_ve_al(kuyruk):
    veri = {"dalgalar": [{"ad": "A", "amac": "x", "gorevler": [], "kabul": ["1 test"]}]}
    plan_id = kuyruk.plan_kaydet(veri, "KURGUSAL HEDEF")
    kayit = kuyruk.plan_al(plan_id)
    assert kayit["hedef"] == "KURGUSAL HEDEF"
    assert kayit["json"] == veri
    assert kuyruk.plan_al(9999) is None


def test_plan_hedefi_maskeli(kuyruk):
    sahte = "sk-" + "0" * 8 + "A" * 7 + "9" + "b" * 20
    plan_id = kuyruk.plan_kaydet({"dalgalar": []}, f"hedef {sahte}")
    kayit = kuyruk.plan_al(plan_id)
    assert sahte not in kayit["hedef"]
    assert "[maskeli]" in kayit["hedef"]
