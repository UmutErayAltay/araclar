"""Rapor: JSON kaydi (atomik) + terminal tablosu.

Gizlilik: rapor skill GOVDE icerigini ve description METNINI icermez; yalniz
ad + sayilar. Tahmin `karakter/4` (karakter/4 tahmini).
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from .ayar import temiz

SURUM = 1
VARSAYILAN_AD = "son.json"
VARSAYILAN_ILK = 15


def _dizin() -> Path:
    """RONTGEN_DIR ile dizin degistirilebilir, varsayilan ~/.baglam-rontgeni (goreli mutlak)."""
    yol = Path(os.environ.get("RONTGEN_DIR") or (Path.home() / ".baglam-rontgeni")).expanduser()
    return yol.resolve() if not yol.is_absolute() else yol


def _yol(yol: Path | None = None) -> Path:
    return (Path(yol).expanduser() if yol else _dizin() / VARSAYILAN_AD)


def olustur(kalemler: list[dict], simdi: float | None = None) -> dict:
    """Rapor govdesi (yazmaz; kaydet() yazar)."""
    acik = [k for k in kalemler if not k.get("kapali")]
    # kaynak yollari ev dizini altindaysa `~` ile kisaltilir (rapor paylasilirken
    # kullanici adi sizmasin); girdi kalemler DEGISTIRILMEZ.
    kartlar = [{**k, "kaynak": kisa(k["kaynak"])} if isinstance(k.get("kaynak"), str) else k for k in kalemler]
    return {
        "surum": SURUM,
        "tarih": datetime.fromtimestamp(
            time.time() if simdi is None else simdi, timezone.utc
        ).isoformat(timespec="seconds"),
        "tahmin_notu": "karakter/4 tahmini",
        "kalemler": kartlar,
        "toplam_acilis": sum(k.get("acilis_token") or 0 for k in acik),
    }


def kaydet(rapor: dict, yol: Path | None = None) -> Path:
    """Raporu JSON olarak yazar (gecici dosya + os.replace: atomik)."""
    hedef = _yol(yol)
    hedef.parent.mkdir(parents=True, exist_ok=True)
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


def _sayi(kalem: dict) -> int:
    """Acilis tokeni; olculemeyen kalem 0 (toplam/zincir sirasini bozmaz)."""
    return kalem.get("acilis_token") or 0


def kisa(yol: str) -> str:
    """Kullanici ana dizini `~` ile kisaltir (tam yol/kullanici adi sizmasin).

    Ayirac `/`ye cevrilir: rapor platformdan bagimsiz okunur.
    """
    try:
        ev = str(Path.home())
        if yol == ev:
            return "~"
        if yol.startswith(ev + os.sep) or yol.startswith(ev + "/"):
            return "~/" + yol[len(ev) + 1 :].replace("\\", "/")
    except (OSError, RuntimeError):
        pass  # ev dizini cozulemiyor: kisaltma yapma
    return yol


def tablo(rapor: dict, ilk: int = VARSAYILAN_ILK) -> str:
    """Buyukten kucuge ilk N satirlik tablo + ozet."""
    kalemler = sorted(rapor.get("kalemler", []), key=lambda k: -_sayi(k))
    gosterilen = kalemler[: max(0, ilk)]
    olculemeyen = sum(1 for k in kalemler if k.get("olculemedi"))
    gizli = sum(1 for k in kalemler if k.get("kapali"))

    def satir(k: dict) -> list[str]:
        istenen = "cagrilinca" if k.get("cagrilinca_token") else "-"
        durum = "kapali" if k.get("kapali") else ("olculemedi" if k.get("olculemedi") else "")
        return [
            temiz(str(k.get("ad", "?"))),
            temiz(str(k.get("tur", "?"))),
            str(_sayi(k)) if not k.get("olculemedi") else "-",
            str(k["cagrilinca_token"]) if istenen != "-" else "-",
            durum,
        ]

    basliklar = ["ad", "tur", "acilis", "cagrilinca", "durum"]
    satirlar = [satir(k) for k in gosterilen]
    genislik = [
        max(len(basliklar[i]), *(len(s[i]) for s in satirlar)) if satirlar else len(basliklar[i])
        for i in range(len(basliklar))
    ]

    def birlestir(hucre: list[str]) -> str:
        return "  ".join(hucre[i].ljust(genislik[i]) for i in range(len(hucre))).rstrip()

    satirlar_metni = [birlestir(h) for h in (basliklar, *satirlar)]
    if len(kalemler) > len(gosterilen):
        satirlar_metni.append(f"... ve {len(kalemler) - len(gosterilen)} kalem daha")
    satirlar_metni.append(
        f"toplam acilis ~{rapor.get('toplam_acilis', 0)} token (TAHMIN), "
        f"{olculemeyen} olculemeyen kalem, {gizli} kapali"
    )
    return "\n".join(satirlar_metni)