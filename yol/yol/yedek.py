"""Yedekler (tam anlik goruntu) ve islem gunlugu. Veri dizini: YOL_DIR ya da ~/.yol."""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .kaynak import Deger, Kaynak, KaynakHatasi

YEDEK_SAYISI = 30
ID_RE = re.compile(r"^\d{8}T\d{6}\d{6}Z$")


class YedekHatasi(RuntimeError):
    """Yedek alinamadi, okunamadi ya da yedek kimligi gecersiz."""


def dizin() -> Path:
    ortam = os.environ.get("YOL_DIR", "").strip()
    return Path(ortam).expanduser() if ortam else Path.home() / ".yol"


def _simdi() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _yedek_klasoru() -> Path:
    return dizin() / "yedek"


def _atomik_yaz(hedef: Path, veri: dict) -> None:
    fd, gecici = tempfile.mkstemp(dir=str(hedef.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as akim:
            json.dump(veri, akim, ensure_ascii=False, indent=2)
        os.replace(gecici, hedef)
    except BaseException:
        Path(gecici).unlink(missing_ok=True)
        raise


def _buda(klasor: Path) -> None:
    kimlikler = sorted(p.stem for p in klasor.glob("*.json") if ID_RE.fullmatch(p.stem))
    for eski in kimlikler[:-YEDEK_SAYISI] if len(kimlikler) > YEDEK_SAYISI else []:
        (klasor / f"{eski}.json").unlink()


def _dosyadan_oku(yol: Path) -> dict[str, Any] | None:
    """Okunamayan ya da bicimi bozuk yedek dosyasi icin None (listelemede atlanir)."""
    try:
        veri = json.loads(yol.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(veri, dict):
        return None
    kapsamlar = veri.get("kapsamlar")
    if not isinstance(kapsamlar, dict) or not all(isinstance(v, dict) for v in kapsamlar.values()):
        return None
    return veri


def yedek_al(kaynak: Kaynak, kapsamlar: Iterable[str]) -> str:
    """Verilen kapsamlarin tam goruntusunu atomik olarak yazar; yedek kimligini doner."""
    kapsam_listesi = list(dict.fromkeys(kapsamlar))
    goruntu: dict[str, dict[str, dict]] = {}
    for kapsam in kapsam_listesi:
        try:
            goruntu[kapsam] = {ad: deger.sozluk() for ad, deger in kaynak.oku(kapsam).items()}
        except KaynakHatasi as exc:
            raise YedekHatasi(f"{kapsam} okunamadi, yedek alinmadi: {exc}") from exc

    klasor = _yedek_klasoru()
    zaman = _simdi()
    try:
        klasor.mkdir(parents=True, exist_ok=True)
        while True:
            kimlik = zaman.strftime("%Y%m%dT%H%M%S") + f"{zaman.microsecond:06d}Z"
            if not (klasor / f"{kimlik}.json").exists():
                break
            zaman += dt.timedelta(microseconds=1)
        veri = {
            "id": kimlik,
            "zaman": zaman.isoformat(),
            "kaynak": kaynak.ad,
            "kapsamlar": goruntu,
        }
        _atomik_yaz(klasor / f"{kimlik}.json", veri)
        _buda(klasor)
    except OSError as exc:
        raise YedekHatasi(f"yedek yazilamadi: {exc}") from exc
    return kimlik


def yedekler() -> list[dict]:
    """En yeni once. Okunamayan dosyalar atlanir."""
    klasor = _yedek_klasoru()
    if not klasor.is_dir():
        return []
    sonuc: list[dict] = []
    for yol in sorted(klasor.glob("*.json"), key=lambda p: p.stem, reverse=True):
        if not ID_RE.fullmatch(yol.stem):
            continue
        veri = _dosyadan_oku(yol)
        if veri is None:
            continue
        sonuc.append({
            "id": yol.stem,
            "zaman": veri.get("zaman"),
            "kapsamlar": {k: len(v) for k, v in veri["kapsamlar"].items()},
        })
    return sonuc


def yedek_oku(id: str) -> dict:
    """Yedegi Deger nesneleriyle doner. Kimlik once dogrulanir (yol gezintisi engellenir)."""
    if not isinstance(id, str) or not ID_RE.fullmatch(id):
        raise YedekHatasi("gecersiz yedek kimligi")
    yol = _yedek_klasoru() / f"{id}.json"
    if not yol.is_file():
        raise YedekHatasi(f"yedek bulunamadi: {id}")
    veri = _dosyadan_oku(yol)
    if veri is None:
        raise YedekHatasi(f"yedek okunamadi: {id}")
    try:
        kapsamlar = {
            kapsam: {ad: Deger.sozlukten(d) for ad, d in degerler.items()}
            for kapsam, degerler in veri["kapsamlar"].items()
        }
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise YedekHatasi(f"yedek bozuk: {id}") from exc
    return {"id": id, "zaman": veri.get("zaman"), "kaynak": veri.get("kaynak"), "kapsamlar": kapsamlar}


def gunluk_ekle(kayit: dict) -> None:
    """Gunlige bir JSON satiri ekler (zaman otomatik). Kayitta deger metni bulunmamali."""
    klasor = dizin()
    satir = dict(kayit)
    satir["zaman"] = _simdi().isoformat()
    try:
        klasor.mkdir(parents=True, exist_ok=True)
        with (klasor / "gunluk.jsonl").open("a", encoding="utf-8") as akim:
            akim.write(json.dumps(satir, ensure_ascii=False) + "\n")
    except OSError as exc:
        raise YedekHatasi(f"gunluk yazilamadi: {exc}") from exc
