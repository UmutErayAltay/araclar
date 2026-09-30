"""`orkestra durum --json` — kule entegrasyonu için TEK JSON özeti (v1).

Kule (kontrol kulesi paneli) bu projeyi alt süreçte çağırır ve YALNIZCA SAYI ve
DURUM okur. Sözleşme: `entegrasyon_sozlesme.md` → "orkestra" bölümü.

Kurallar (bağlayıcı):
  * stdout'a YALNIZCA tek bir JSON nesnesi; hatada da JSON, çıkış kodu 1.
  * `hata` SABİT koddur (`db_yok` / `sema_eski` / `okunamadi`); istisna metni,
    dosya yolu, SQL veya kullanıcı içeriği ASLA girmez.
  * Sadece sayı/bool/sabit etiket/ISO-8601 zaman. Görev metni, rapor, prompt,
    log İÇERİĞİ ve yollar çıktıya GİRMEZ.
  * Ağa çıkmaz, alt süreç çalıştırmaz, DB'ye YAZMAZ (`mode=ro`), hiçbir
    tarama/indeksleme TETİKLEMEZ — yalnızca mevcut durumu okur.

`kanitsiz_ya_da_supheli` NASIL hesaplanır: rapor sınıfı `runs.kanit_durumu`
sütununda SAKLANIR (Dalga D) ve her koşuda `queue._raporu_degerlendir` tarafından
yazılır. Bu komut YENİ bir sınıflandırma kuralı UYDURMAZ; yalnızca o sütunu
okur: görevin EN SON koşusunun sınıfı `kanitsiz` veya `reddedildi-suphesi` ise
görev sayılır. Sütun yoksa (eskiden başka bir şema) `sema_eski` döner.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

from . import quota, report
from .models import Durum
from .queue import SEMA_SURUM, varsayilan_db_yolu
from .web.sunucu import db_ac

SURUM = 1
KAYNAK = "orkestra"

# Sabit hata kodları (sözleşme: istisna metni/YOL ASLA girmez).
HATA_DB_YOK = "db_yok"
HATA_SEMA_ESKI = "sema_eski"
HATA_OKUNAMADI = "okunamadi"
HATA_YOL_GECERSIZ = "yol_gecersiz"

#: Kule'ye giden kanıt sınıfları: "kanıtsız ya da şüpheli". Değerler `report`
#: sabitlerinden gelir (sınıflandırma kuralı TEK kaynaktan).
SUPHELI_SINIFLAR = (report.KANITSIZ, report.REDDEDILDI)

#: Kanıt sütunu olmayan (eskiden başka bir şema) `runs` tabloları.
_KANIT_SUTUNLARI = ("kanit_durumu",)


def hata_cevabi(kod: str) -> dict:
    """Hata gövdesi: sabit kod, başka alan YOK."""
    return {"surum": SURUM, "kaynak": KAYNAK, "hata": kod}


def _tanimli(tablolar: set[str], tablo: str) -> bool:
    return any(t == tablo for t in tablolar)


def kanit_sutunu_var(baglanti: sqlite3.Connection) -> bool:
    """`runs.kanit_durumu` okunabiliyor mu (eski şema kontrolü)."""
    try:
        satirlar = baglanti.execute("PRAGMA table_info(runs)").fetchall()
    except sqlite3.Error:
        return False
    adlar = {s[1] for s in satirlar}
    return all(sutun in adlar for sutun in _KANIT_SUTUNLARI)


def _sayim(baglanti: sqlite3.Connection, tablo: str) -> int:
    try:
        return int(baglanti.execute(f"SELECT COUNT(*) FROM {tablo}").fetchone()[0])
    except (sqlite3.Error, TypeError, ValueError, IndexError):
        return 0


def durum_sayimlari(baglanti: sqlite3.Connection) -> dict[str, int]:
    """`gorev_durum`: `models.Durum` değerleri → adet (HER ZAMAN tüm anahtarlar)."""
    sayimlar = {d.value: 0 for d in Durum}
    try:
        satirlar = baglanti.execute("SELECT durum, COUNT(*) FROM tasks GROUP BY durum").fetchall()
    except sqlite3.Error:
        return sayimlar  # `tasks` yoksa sıfır: sayım üretmeden okunamadı demek değil.
    for satir in satirlar:
        deger = satir[0]
        if deger in sayimlar:  # yabancı/bilinmeyen durum yazısı sayılmaz
            sayimlar[deger] = int(satir[1])
    return sayimlar


def gorev_toplam(baglanti: sqlite3.Connection) -> int:
    return _sayim(baglanti, "tasks")


def onay_bekleyen(baglanti: sqlite3.Connection) -> int:
    return durum_sayimlari(baglanti).get(Durum.ONAY_BEKLIYOR.value, 0)


def kanitsiz_sayisi(baglanti: sqlite3.Connection) -> tuple[int, int]:
    """`(kanitsiz_ya_da_supheli, basarisiz)` — en son koşunun sınıfından.

    Sınıf `runs.kanit_durumu`'da saklanır (Dalga D); hiçbir koşu yazmamışsa
    `degerlendirilmedi` sayılır (bir sınıf tahmin EDİLMEZ).
    """
    sql = (
        "SELECT t.id AS gorev_id, "
        "  (SELECT r.kanit_durumu FROM runs r "
        "    WHERE r.task_id = t.id ORDER BY r.id DESC LIMIT 1) AS sinif "
        "FROM tasks t ORDER BY t.id"
    )
    try:
        satirlar = baglanti.execute(sql).fetchall()
    except sqlite3.Error:
        return (0, 0)
    supheli = basarisiz = 0
    for satir in satirlar:
        sinif = satir[1] if len(satir) > 1 else None
        if sinif in SUPHELI_SINIFLAR:
            supheli += 1
        elif sinif == report.BASARISIZ:
            basarisiz += 1
    return (supheli, basarisiz)


def kota_ozeti(baglanti: sqlite3.Connection, kota_toml: str | Path | None = None) -> dict | None:
    """`kota` alt nesnesi; okunamazsa `None` (kule "kota verisi yok" der)."""
    try:
        gorunum = quota.kota_gorunumu(baglanti, quota.limitleri_yukle(kota_toml))
    except (sqlite3.Error, OSError, ValueError, TypeError):
        return None
    return {
        "gun": gorunum.gun,
        "toplam_istek": int(gorunum.toplam_istek),
        "uyari_sayisi": int(gorunum.uyari_sayisi),
        "veri_var": bool(gorunum.veri_var),
    }


def ozet_uret(baglanti: sqlite3.Connection, kota_toml: str | Path | None = None) -> dict:
    """Başarılı çıktı gövdesi (yalnızca sayı/bool/sabit etiket)."""
    supheli, basarisiz = kanitsiz_sayisi(baglanti)
    return {
        "surum": SURUM,
        "kaynak": KAYNAK,
        "gorev_toplam": gorev_toplam(baglanti),
        "gorev_durum": durum_sayimlari(baglanti),
        "onay_bekleyen": onay_bekleyen(baglanti),
        "kanitsiz_ya_da_supheli": supheli,
        "basarisiz": basarisiz,
        "kota": kota_ozeti(baglanti, kota_toml),
    }


def _yol_coz(yol: str | Path | None) -> Path | None:
    if yol is None:
        return varsayilan_db_yolu()
    try:
        return Path(yol).expanduser()
    except (OSError, RuntimeError, ValueError, TypeError):
        return None


def durum_oku(yol: str | Path | None = None, kota_toml: str | Path | None = None) -> dict:
    """Sözleşme gövdesini üretir: başarılıysa özet, aksi hata kodu gövdesi.

    Sıralama: DB yok → `db_yok`; okunamıyor/şema okunamadı → `okunamadi`;
    şema sürümü eski → `sema_eski`.
    """
    cozulmus = _yol_coz(yol)
    if cozulmus is None:
        return hata_cevabi(HATA_YOL_GECERSIZ)
    if not cozulmus.is_file():
        return hata_cevabi(HATA_DB_YOK)
    try:
        baglanti = db_ac(cozulmus)
    except sqlite3.Error:
        return hata_cevabi(HATA_OKUNAMADI)
    try:
        tablolar = {
            s[0] for s in baglanti.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        if not _tanimli(tablolar, "tasks") or not _tanimli(tablolar, "runs"):
            return hata_cevabi(HATA_SEMA_ESKI)
        try:
            surum = int(baglanti.execute("PRAGMA user_version").fetchone()[0])
        except (sqlite3.Error, TypeError, ValueError, IndexError):
            return hata_cevabi(HATA_OKUNAMADI)
        if surum < SEMA_SURUM:
            return hata_cevabi(HATA_SEMA_ESKI)
        if not kanit_sutunu_var(baglanti):
            return hata_cevabi(HATA_SEMA_ESKI)
        return ozet_uret(baglanti, kota_toml)
    except sqlite3.Error:
        return hata_cevabi(HATA_OKUNAMADI)
    finally:
        baglanti.close()


def _yaz(veri: dict) -> None:
    """stdout'a TEK satır JSON (başka çıktı yok); stderr'e de gizli yazmaz."""
    sys.stdout.write(json.dumps(veri, ensure_ascii=True, sort_keys=False) + "\n")


def calistir_ve_yaz(
    yol: str | Path | None = None, kota_toml: str | Path | None = None
) -> int:
    """Komut girişi: 0 (başarı) / 1 (hata); stdout her hâlükârda JSON."""
    veri = durum_oku(yol, kota_toml)
    _yaz(veri)
    return 0 if "hata" not in veri else 1


def insan_ozeti(yol: str | Path | None = None, kota_toml: str | Path | None = None) -> int:
    """`--json` verilmezse: kısa insan-okur özet (sözleşme 1. madde)."""
    veri = durum_oku(yol, kota_toml)
    if "hata" in veri:
        print(f"Hata: {veri['hata']}", file=sys.stderr)
        return 1
    durumlar = veri["gorev_durum"]
    print(f"orkestra: {veri['gorev_toplam']} gorev "
          f"(onay bekleyen: {veri['onay_bekleyen']}, "
          f"basarisiz: {veri['basarisiz']}, "
          f"kanitsiz/supheli: {veri['kanitsiz_ya_da_supheli']})")
    dolu = [(ad, adet) for ad, adet in durumlar.items() if adet]
    if not dolu:
        print("  kuyruk bos")
    for ad, adet in dolu:
        print(f"  {ad}: {adet}")
    kota = veri["kota"]
    if kota is None:
        print("  kota: veri yok")
    else:
        print(f"  kota ({kota['gun']}): {kota['toplam_istek']} istek, "
              f"{kota['uyari_sayisi']} uyari, veri_var={kota['veri_var']}")
    return 0
