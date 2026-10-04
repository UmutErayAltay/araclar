""".env ayristirici.

GUMLIK NOTU: `oku()` HAM DEGER dondurur. Bu degerler YALNIZ `envanter.py`
icinde, parmak izi uretilip HEMEN birakildiktan sonra kullanilir. Ham deger
hicbir mesaja, hataya, tabloya veya JSON'a girmez.

Kabul edilen bicimler:
- `KEY=DEGER`, `export KEY=DEGER`
- tek/cift tirnakli deger (`#` tirnak icinde yorum DEGILDIR)
- tirnaksiz degerde bosluk + `#` ile satir sonu yorumu
- bos satirlar, tam yorum satirlari, CRLF satir sonlari, UTF-8 BOM
- Bozuk satir (yoksa `=`, bos anahtar, gecersiz anahtar karakteri): ATLANIR.
  Ham satir ne hataya ne cikisa gider; yalniz anahtar adlari sayilir.
"""

from __future__ import annotations

import re
from pathlib import Path

#: Gecerli ortam degiskeni adi.
_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

#: `.env` soyut adlarinin ALINMAMASI gereken son ekleri (ornek sablonlar).
ORNEK_SONEK = ("example", "sample", "template", "dist", "defaults", "ornek", "ornek")

#: Taranabilir dosya: `.env`, `.env.local`, `.env.production`, ...
_AD = re.compile(r"\.env(?:\.[A-Za-z0-9_-]+)*")


def env_dosyasi_mi(ad: str) -> bool:
    """`.env*` adi taranacak bir ortam dosyasi mi? (ornek sablonlar HARIC)."""
    if not _AD.fullmatch(ad):
        return False
    parcalar = ad.split(".")[1:]
    return not any(p.lower() in ORNEK_SONEK for p in parcalar)


def _deger(kalan: str) -> str:
    """Tirnagi soyulmus deger; tirnak yoksa satir sonu yorumu kirpilir."""
    kalan = kalan.lstrip()
    if kalan[:1] in ('"', "'"):
        tirnak = kalan[0]
        kapanis = kalan.find(tirnak, 1)
        return kalan[1:kapanis] if kapanis > 0 else kalan[1:]
    for i, karakter in enumerate(kalan):
        # `DEGER # yorum`: bosluktan sonra gelen `#` yorumdur, `abc#def` degil.
        if karakter == "#" and (i == 0 or kalan[i - 1].isspace()):
            return kalan[:i].rstrip()
    return kalan.rstrip()


def _satir(coz: str) -> tuple[str, str] | None:
    """Bir satirdan (ad, ham deger); taninmayan satir icin None."""
    satir = coz.strip()
    if not satir or satir.startswith("#"):
        return None
    if satir.startswith("export ") or satir.startswith("export\t"):
        satir = satir[7:].lstrip()
    ad, ayirac, kalan = satir.partition("=")
    ad = ad.strip()
    if not ayirac or not _KEY.fullmatch(ad):
        return None  # bozuk satir: sessizce atlanir
    return ad, _deger(kalan)


def _coz(veri: bytes) -> str:
    """BOM at, CRLF'i duzelt, baytlari metne cevir (bozuk bayt: surrogateescape)."""
    if veri.startswith(b"\xef\xbb\xbf"):
        veri = veri[3:]
    return veri.decode("utf-8", "surrogateescape")


def oku(yol: Path) -> list[tuple[str, str]]:
    """`yol` icindeki (ad, HAM deger) ciftlerini dondurur.

    Dosya okunamazsa bos liste (taramaci bir dosya bozmaz).
    """
    try:
        metin = _coz(Path(yol).read_bytes())
    except OSError:
        return []
    ciftler: list[tuple[str, str]] = []
    for satir in metin.splitlines():
        sonuc = _satir(satir)
        if sonuc is not None:
            ciftler.append(sonuc)
    return ciftler