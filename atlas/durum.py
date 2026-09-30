"""Tek sayfa ozet: web paneli (`/`, `/api/ozet`) ve CLI (`atlas durum`) ORTAK.

`ozet_verisi` ve `veri_bayat_mi` buraya TASINDI; web paneli de ayni fonksiyonu
cagirmaya devam eder, boylece SAYILAR TEK YERDEN uretilir. `/api/ozet`
cikti sekli bu tasima ile DEGISMEZ.

`atlas durum --json` sozlesmesi (v1): yalniz SAYI, bool, sabit etiket ve
ISO-8601 zaman disa cikar. Bulgunun kendisi (dosya, satir, eslesen metin),
repo yolu, dal adi ve commit basligi HICBIR SEKILDE tasinmaz.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

#: Onem sirasi (yuksek -> bilgi).
ONEMLER = ("yuksek", "orta", "dusuk", "bilgi")

#: README bayatligi seviyeleri. Duzturucu: hepsi sabit etiketler.
SEVIYE_ETIKETLERI = {
    "bayat": "bayat",
    "eskiyor": "eskiyor",
    "taze": "taze",
    "yok": "README yok",
}

#: `/` ozet kartinda "N bayat README" sayacinda sayilan seviyeler: yalniz
#: "bayat" ve "eskiyor". "taze" ve "yok" sayilmaz ("yok" = eksik veri, acik
#: sorun degil; "bayat" = gercekten gecikmis).
OZET_SAYILAN_SEVIYELER = ("bayat", "eskiyor")

#: Veri 24 saatten eskiyse bayat sayilir.
BAYAT_ESIK_SAAT = 24


def db_ac(yol: Path | str) -> sqlite3.Connection:
    """DB'yi `mode=ro` ile acar; hicbir kosulda yazmaz.

    Sema KURULMAZ: dosya yoksa hicbir tablo acilmaz ve `ozet_verisi` sifir
    sayilarla calisir. (Sema kurmak yazma olurdu; `durum` yalnizca OKUR.)
    """
    yol = Path(yol).expanduser()
    baglanti = sqlite3.connect(f"file:{yol}?mode=ro", uri=True)
    baglanti.row_factory = sqlite3.Row
    return baglanti


def ozet_verisi(conn: sqlite3.Connection) -> dict[str, Any]:
    """Ozet sayilari: `/`, `/api/ozet` ve `atlas durum` ayni fonksiyonu okur."""
    satir = conn.execute(
        "SELECT COUNT(*) AS toplam, "
        "SUM(CASE WHEN dirty > 0 THEN 1 ELSE 0 END) AS kirli, "
        "SUM(CASE WHEN unpushed IS NULL THEN 1 ELSE 0 END) AS bilinmeyen, "
        "SUM(CASE WHEN unpushed > 0 AND has_remote = 1 THEN 1 ELSE 0 END) AS push_bekleyen, "
        "MAX(scanned_at) AS son_tarama "
        "FROM repos"
    ).fetchone()
    toplam = int(satir["toplam"] or 0)
    kirli = int(satir["kirli"] or 0)
    bilinmeyen = int(satir["bilinmeyen"] or 0)
    push_bekleyen = int(satir["push_bekleyen"] or 0)

    bulgu_sayaclari = {
        onem: 0 for onem in ONEMLER
    }
    for satir_b in conn.execute(
        "SELECT severity, COUNT(*) AS adet FROM findings GROUP BY severity"
    ):
        onem = satir_b["severity"]
        if onem in bulgu_sayaclari:
            bulgu_sayaclari[onem] = int(satir_b["adet"])
    toplam_bulgu = sum(bulgu_sayaclari.values())

    todo_toplam = int(conn.execute("SELECT COUNT(*) FROM todos").fetchone()[0])

    # Eski semada `readme_status` YOKSA sayilar 0'dir: ozet karti "0 bayat
    # README" der, sayfa bos durum gosterir. (Tablo eksikligi HATA DEGILDIR.)
    readme_sayaclari = {seviye: 0 for seviye in SEVIYE_ETIKETLERI}
    readme_toplam = 0
    try:
        for satir_r in conn.execute("SELECT seviye, COUNT(*) AS adet FROM readme_status GROUP BY seviye"):
            anahtar = satir_r["seviye"] if satir_r["seviye"] in readme_sayaclari else None
            if anahtar is not None:
                readme_sayaclari[anahtar] += int(satir_r["adet"])
        readme_toplam = int(conn.execute("SELECT COUNT(*) FROM readme_status").fetchone()[0])
    except sqlite3.Error:  # tablo yoksa
        pass
    bayat_readme = sum(readme_sayaclari[s] for s in OZET_SAYILAN_SEVIYELER)

    return {
        "repo_sayisi": toplam,
        "kirli_repo": kirli,
        "push_bekleyen": push_bekleyen,
        "push_bilinmeyen": bilinmeyen,
        "bulgu_sayaclari": bulgu_sayaclari,
        "toplam_bulgu": toplam_bulgu,
        "toplam_todo": todo_toplam,
        "readme_sayaclari": readme_sayaclari,
        "readme_toplam": readme_toplam,
        "bayat_readme": bayat_readme,
        "son_tarama": satir["son_tarama"],
        "veri_bayat": veri_bayat_mi(satir["son_tarama"]),
    }


def veri_bayat_mi(son_tarama: str | None) -> bool:
    """Son tarama 24 saatten eski mi (ya da hic yok mu)?"""
    if not son_tarama:
        return True
    try:
        dt = datetime.fromisoformat(son_tarama)
    except ValueError:
        return True
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    yas = (datetime.now(timezone.utc) - dt).total_seconds()
    return yas > BAYAT_ESIK_SAAT * 3600


# --------------------------------------------------------------------------
# `atlas durum --json` sozlesmesi (v1)
# --------------------------------------------------------------------------

SURUM = 1
KAYNAK = "atlas"

#: SABIT hata kodlari. Istisna metni, dosya yolu, SQL veya kullanici icerigi
#: ASLA bu alana girmez.
HATA_DB_YOK = "db_yok"
HATA_OKUNAMADI = "okunamadi"
HATA_SEMA_ESKIDIR = "sema_eskidir"

#: Sadece sayi/bool/sabit etiket/zaman tasinan alanlar. Alan sayilari burada
#: donusturulur; hicbir bulgu satiri, dosya yolu veya metin tasinmaz.
_SAYI_ALANLAR: tuple[tuple[str, str], ...] = (
    ("repo_sayisi", "repo_sayisi"),
    ("kirli_repo", "kirli_repo"),
    ("push_bekleyen", "push_bekleyen"),
    ("push_bilinmeyen", "push_bilinmeyen"),
    ("bayat_readme", "bayat_readme"),
    ("bulgu_toplam", "toplam_bulgu"),
    ("todo_toplam", "toplam_todo"),
)


def hata_sozlesmesi(kod: str) -> dict[str, Any]:
    """Sozlesme hata govdesi. `hata` DEGISMEYEN kisa bir koddur."""
    return {"surum": SURUM, "kaynak": KAYNAK, "hata": kod}


def durum_sozlesmesi(ozet: dict[str, Any]) -> dict[str, Any]:
    """`ozet_verisi` ciktisindan SOZLESME govdesini kurar.

    Alanlar: `surum`, `kaynak`, `son_tarama`, `veri_bayat` ve sayilar.
    `son_tarama` DB'den gelen ISO-8601 metni veya `None` (hic tarama yoksa).
    """
    govde: dict[str, Any] = {
        "surum": SURUM,
        "kaynak": KAYNAK,
        "son_tarama": ozet["son_tarama"],
        "veri_bayat": bool(ozet["veri_bayat"]),
    }
    for hedef, kaynak in _SAYI_ALANLAR:
        govde[hedef] = int(ozet[kaynak])
    govde["bulgu_onem"] = {onem: int(ozet["bulgu_sayaclari"][onem]) for onem in ONEMLER}
    return govde
