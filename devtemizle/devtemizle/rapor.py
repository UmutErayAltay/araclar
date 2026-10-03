"""Rapor: JSON kaydi (atomik) + terminal tablosu."""

from __future__ import annotations

import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

SURUM = 1
VARSAYILAN_AD = "son.json"


def _dizin() -> Path:
    """DEVTEMIZLE_DIR ile dizin degistirilebilir, varsayilan ~/.devtemizle."""
    return Path(os.environ.get("DEVTEMIZLE_DIR") or (Path.home() / ".devtemizle")).expanduser()


def _yol(yol: Path | None = None) -> Path:
    return (Path(yol).expanduser() if yol else _dizin() / VARSAYILAN_AD)


def olustur(adaylar: list[dict], simdi: float | None = None) -> dict:
    """Rapor govdesi (yazmaz; kaydet() yazar)."""
    return {
        "surum": SURUM,
        "tarih": datetime.fromtimestamp(
            time.time() if simdi is None else simdi, timezone.utc
        ).isoformat(timespec="seconds"),
        "adaylar": adaylar,
    }


def kaydet(rapor: dict, yol: Path | None = None) -> Path:
    """Raporu JSON olarak yazar (gecici dosya + os.replace: atomik)."""
    hedef = _yol(yol)
    hedef.parent.mkdir(parents=True, exist_ok=True)
    # Ayni dizinde gecici dosya: os.replace atomik olsun.
    fd, gecici_ad = tempfile.mkstemp(dir=hedef.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as akim:
            json.dump(rapor, akim, ensure_ascii=False, indent=2)
        os.replace(gecici_ad, hedef)
    except BaseException:
        Path(gecici_ad).unlink(missing_ok=True)
        raise
    return hedef


def yukle(yol: Path | None = None) -> dict | None:
    """Son raporu okur; yoksa/bozuksa None."""
    try:
        return json.loads(_yol(yol).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def boyut_yaz(bayt: int) -> str:
    """1024 tabanli, 1 ondalikli insan-okur boyut."""
    deger = float(bayt)
    for birim in ("B", "KB", "MB", "GB"):
        if deger < 1024 or birim == "GB":
            if birim == "B":
                return f"{int(deger)} B"
            return f"{deger:.1f} {birim}"
        deger /= 1024
    return f"{deger:.1f} GB"  # erisilemez


def _sutun(rapor: dict) -> str:
    adaylar = rapor.get("adaylar", [])
    basliklar = ["repo", "tur", "boyut", "yas(gun)", "durum"]
    satirlar = [
        [
            Path(a["repo"]).name,
            a.get("tur", "?"),
            boyut_yaz(a.get("boyut", 0)),
            str(int(a.get("yas_gun", 0))),
            a["atlandi"] or "silinebilir",
        ]
        for a in adaylar
    ]
    genislik = [
        max(len(basliklar[i]), *(len(s[i]) for s in satirlar)) if satirlar else len(basliklar[i])
        for i in range(len(basliklar))
    ]

    def birlestir(hucre: list[str]) -> str:
        return "  ".join(hucre[i].ljust(genislik[i]) for i in range(len(hucre))).rstrip()

    return "\n".join([birlestir(basliklar), *(birlestir(s) for s in satirlar)])


def tablo(rapor: dict) -> str:
    """Insan-okur metin tablosu + ozet satiri."""
    adaylar = rapor.get("adaylar", [])
    toplam = sum(a.get("boyut", 0) for a in adaylar)
    silinebilir = sum(a.get("boyut", 0) for a in adaylar if not a.get("atlandi"))
    atlandi = sum(1 for a in adaylar if a.get("atlandi"))
    return (
        f"{_sutun(rapor)}\n"
        f"ozet: {len(adaylar)} aday, {boyut_yaz(toplam)} toplam, "
        f"{boyut_yaz(silinebilir)} silinebilir, {atlandi} atlandi"
    )


def sil_ozeti(sonuc: dict, uygula: bool) -> str:
    """Silme ozeti: kuru calistirma uyarisi veya gercek sonuc."""
    satirlar: list[str] = []
    if not uygula:
        # Kuru calistirmada bosalan_bayt 0'dir; silinecek toplam gosterilir.
        kacacak = sum(a.get("boyut", 0) for a in sonuc["silinecek"])
        satirlar.append(
            f"KURU CALISTIRMA: {len(sonuc['silinecek'])} klasor silinecekti "
            f"({boyut_yaz(kacacak)}). Silmek icin --uygula ekleyin."
        )
        satirlar.extend(f"  - {a['yol']}  {boyut_yaz(a['boyut'])}  {a['tur']}" for a in sonuc["silinecek"])
    else:
        satirlar.append(
            f"{len(sonuc['silindi'])} silindi ({boyut_yaz(sonuc['bosalan_bayt'])} bosaldi), "
            f"{len(sonuc['silinemedi'])} silinemedi, {len(sonuc['atlanan'])} atlandi"
        )
        satirlar.extend(f"  ! {a['yol']}  {a['neden']}" for a in sonuc["silinemedi"])
    return "\n".join(satirlar)