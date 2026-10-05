"""Denetim 2 -- `tasima_tamlik`: tasinan kod gercekten tasinmis mi?

Bosaltma commit'inden ONCEKI son commit'in dosya listesi (`HEAD~1`) ile koddun
yeni yeri olan `<arac-repo>/<ad>/` altindaki dosya listesi karsilastirilir.

Eslestirme iki asamali:
  1. ayni goreli yol (birebir), 2. kalanlar icin ayni dosya adi (basename)
     -- "tasinirken yol degismis" durumu icin.

Hicbir asamada eslesmeyen dosyalar EKSIK sayilir. Liste en cok 25 dosya
gosterir, toplam sayi her zaman yazilir.

Yoksayilanlar: `.gitignore`, `__pycache__/`, `*.pyc`, `.pytest_cache/`,
`*.egg-info/` -- bunlar tasinan kod DEGILDIR, urun yanlisidir. Iki tarafta da
elenir: yoksa karsi tarafa hicbir yerde konmus `.gitignore` "eksik" sayilirdi.
"""

from __future__ import annotations

import os
from collections import Counter
from pathlib import Path, PurePosixPath

from . import kesif

#: Karsilastirmaya girmeyen dizin adlari (turetilmis / uretim ciktisi).
YOKSAYILAN_DIZIN = frozenset({"__pycache__", ".pytest_cache", ".git"})

#: Karsilastirmaya girmeyen dosya adlari.
YOKSAYILAN_AD = frozenset({".gitignore"})

#: Karsilastirmaya girmeyen dosya son ekleri.
YOKSAYILAN_EK = (".pyc", ".egg-info")

#: Listede gosterilecek en fazla eksik dosya; toplam sayi ayrica yazilir.
GOSTERME_LIMITI = 25


def yoksay(goreli: str) -> bool:
    """Bu yol karsilastirmaya girmeli mi?

    `*.egg-img` YOLUN HERHANGI BIR PARCASINDA aranir: `setup.py egg_info` ciktisi
    `foo.egg-info/` bir DIZINDIR, dosya degil (`foo.egg-info/PKG-INFO`).
    """
    parcalar = PurePosixPath(goreli).parts
    if any(p in YOKSAYILAN_DIZIN for p in parcalar):
        return True
    if any(p.endswith(".egg-info") for p in parcalar):
        return True
    ad = parcalar[-1]
    return ad in YOKSAYILAN_AD or ad.endswith(YOKSAYILAN_EK)


def _temizle(yollar: list[str]) -> list[str]:
    return sorted(yol for yol in yollar if yol and not yoksay(yol))


def hedef_dosyalar(arac_hedefi: Path) -> list[str]:
    """`<arac-repo>/<ad>/` altindaki dosyalar (hedefe gore goreli)."""
    if not arac_hedefi.is_dir():
        return []
    bulunan = [
        (Path(kok) / ad).relative_to(arac_hedefi).as_posix()
        for kok, _dizinler, dosyalar in os.walk(arac_hedefi)
        for ad in dosyalar
    ]
    return _temizle(bulunan)


def _eksikleri(kaynak: list[str], hedef: list[str]) -> list[str]:
    """Kaynakta olup hedefte OLMAYAN dosyalar (once yola, sonra ada gore eslesir).

    Iki es gecen ad, iki hedef ad varsa IKISI DE eslesir: coklu kopyayi tek
    dosyaya saymak, eksikleri gizlerdi.
    """
    kalan_hedef = Counter(hedef)
    eksik: list[str] = []
    kalan_kaynak: list[str] = []
    for yol in kaynak:  # 1. asam: birebir goreli yol
        if kalan_hedef[yol] > 0:
            kalan_hedef[yol] -= 1
        else:
            kalan_kaynak.append(yol)

    kalan_adlar = Counter(PurePosixPath(yol).name for yol in kalan_hedef.elements())
    for yol in kalan_kaynak:  # 2. asam: dosya adi herhangi bir yerde
        ad = PurePosixPath(yol).name
        if kalan_adlar[ad] > 0:
            kalan_adlar[ad] -= 1
        else:
            eksik.append(yol)
    return sorted(eksik)


def denetle(repo: Path, arac_hedefi: Path) -> dict:
    """`tasima_tamlik` denetimi.

    `HEAD~1` cozulemezse denetim ATLANIR: kaynak liste bilinmeden "0 eksik"
    gibi bir pozitif iddia URETILMEZ (sahte guvence, en kotu cikti).
    """
    hedef = _temizle(hedef_dosyalar(arac_hedefi))
    ham_kaynak = kesif.ls_tree(repo, "HEAD~1")
    if ham_kaynak is None:
        return {
            "durum": "atlandi",
            "kaynak": 0,
            "hedef": len(hedef),
            "eksik_sayisi": 0,
            "eksik_gosterilen": [],
            "not": "HEAD~1 yok (bosaltma commit'inden onceki commit bulunamadi); "
                   "tasima tamligi denetlenemedi",
        }

    kaynak = _temizle(ham_kaynak)
    eksik = _eksikleri(kaynak, hedef)
    return {
        "durum": "tam" if not eksik else "eksik-var",
        "kaynak": len(kaynak),
        "hedef": len(hedef),
        "eksik_sayisi": len(eksik),
        "eksik_gosterilen": eksik[:GOSTERME_LIMITI],
        "not": None,
    }