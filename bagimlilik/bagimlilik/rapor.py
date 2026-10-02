"""Rapor: JSON kaydi (atomik) + terminal tablosu."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .denetim import RepoSonuc

SURUM = 1
VARSAYILAN_AD = "son.json"


def _dizin() -> Path:
    """BAGIMLILIK_DIR ile dizin degistirilebilir, varsayilan ~/.bagimlilik."""
    return Path(os.environ.get("BAGIMLILIK_DIR") or (Path.home() / ".bagimlilik")).expanduser()


def _yol(yol: Path | None = None) -> Path:
    return (Path(yol).expanduser() if yol else _dizin() / VARSAYILAN_AD)


def kaydet(sonuclar: list[RepoSonuc], yol: Path | None = None) -> Path:
    """Sonucu JSON olarak yazar (gecici dosya + os.replace: atomik)."""
    hedef = _yol(yol)
    hedef.parent.mkdir(parents=True, exist_ok=True)
    govde = {
        "surum": SURUM,
        "tarih": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "repolar": [asdict(s) for s in sonuclar],
    }
    # Ayni dizinde gecici dosya: os.replace atomik olsun.
    fd, gecici_ad = tempfile.mkstemp(dir=hedef.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as akim:
            json.dump(govde, akim, ensure_ascii=False, indent=2)
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


def _sayi(denetim, anahtar: str) -> str:
    deger = (denetim.sayilar or {}).get(anahtar, 0)
    # pip-audit siddet vermez: acik var ama kritik/yuksek/orta/dusuk sayilamaz.
    if anahtar != "bilinmiyor" and not deger and denetim.ekosistem == "pip" and denetim.toplam:
        return "?"
    return str(deger)


def _satir(repo_adi: str, denetim) -> list[str]:
    durum = denetim.durum
    if durum == "denetlenemedi":
        durum = f"denetlenemedi({denetim.neden})"
    return [
        repo_adi,
        f"{denetim.ekosistem}:{denetim.kaynak}",
        durum,
        _sayi(denetim, "kritik"),
        _sayi(denetim, "yuksek"),
        _sayi(denetim, "orta"),
        _sayi(denetim, "dusuk"),
        str(denetim.toplam),
    ]


def tablo(sonuclar: list[RepoSonuc]) -> str:
    """Insan-okur metin tablosu: once ozet satirlari, sonra aciklar."""
    basliklar = ["repo", "kaynak", "durum", "K", "Y", "O", "D", "toplam"]
    satirlar: list[list[str]] = []
    for sonuc in sonuclar:
        for denetim in sonuc.denetimler:
            satirlar.append(_satir(sonuc.ad, denetim))

    genislik = [max(len(basliklar[i]), *(len(s[i]) for s in satirlar)) if satirlar else len(basliklar[i])
               for i in range(len(basliklar))]
    def birlestir(hucre: list[str]) -> str:
        return "  ".join(hucre[i].ljust(genislik[i]) for i in range(len(hucre))).rstrip()

    cizgiler = [birlestir(basliklar)]
    cizgiler.extend(birlestir(s) for s in satirlar)

    for sonuc in sonuclar:
        for denetim in sonuc.denetimler:
            if denetim.durum != "acik":
                continue
            for acik in denetim.aciklar[:3]:
                cizgiler.append(
                    f"    - {acik.paket} {acik.surum} [{acik.siddet}] {acik.id}"
                    f" -> {acik.duzeltme or 'duzeltme yok'}"
                )

    temiz = acikli = denetlenemedi = denetimsiz = 0
    for sonuc in sonuclar:
        if not sonuc.denetimler:
            denetimsiz += 1
            continue
        durumlar = {d.durum for d in sonuc.denetimler}
        if "acik" in durumlar:
            acikli += 1
        elif "temiz" in durumlar:
            temiz += 1
        else:
            denetlenemedi += 1
    cizgiler.append(
        f"ozet: {len(sonuclar)} repo -> {temiz} temiz, {acikli} acikli, {denetlenemedi} denetlenemedi, {denetimsiz} manifestsiz"
        "  (K/Y/O/D = kritik/yuksek/orta/dusuk; ? = pip-audit siddet vermez)"
    )
    return "\n".join(cizgiler)
