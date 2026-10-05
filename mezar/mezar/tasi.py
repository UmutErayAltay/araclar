"""Denetim 1 -- `mezar_tasi`: calisma agacinda geriye ne kaldi?

Bosaltma (mezar tasi) sonrasi calisma agacinda `.git` disinda YALNIZ `README.md`
kalmis olmali. Kalan baska bir sey varsa bu repo henuz tasinmaya hazir degildir:
"bosaltilmis gorunmuyor" bilgi notu dusulur.

Bu bir BULGU degil, bilgi notudur: tek basina karari degistirmez.
"""

from __future__ import annotations

import os
from pathlib import Path

#: Bosaltma sonrasi kalmasina izin verilen TEK dosya.
BEKLENEN = "README.md"

#: Sayilmayan dizinler (artik ya da gizli deger, dosya degil).
GIZLI = {".git"}

#: Bir alt dizine inilmeden sayilan KAP dizinler: icerik degil, klasor kabu.
KAP = {".github", "node_modules", "__pycache__", ".venv", "venv", ".idea", ".vscode"}


def kalan_dosyalar(repo: Path) -> list[str]:
    """Calisma agacindaki dosyalar (repo'ya gore goreli, alfabetik).

    KAP dizinlerinin ICINE inilmez: `.github/` altindaki yuzlerce dosya bir
    "mezar tasi" adayi icin anlamsizdir. Simge baglantili dizinlere de girilmez
    (`followlinks=False` varsayilanidir): donguye girmeyi onler.
    """
    bulunan: list[str] = []
    for kok, dizinler, dosyalar in os.walk(repo):
        if Path(kok) == repo:
            dizinler[:] = [d for d in dizinler if d not in GIZLI and d not in KAP]
        for ad in dosyalar:
            bulunan.append((Path(kok) / ad).relative_to(repo).as_posix())
    return sorted(bulunan)


def denetle(repo: Path) -> dict:
    """`mezar_tasi` denetimi: bosaltilmis mi, degil mi?

    Donen sozluk: {"durum", "kalan", "not"}. `not` yalnizca durum
    "bosaltilmis-gorunmuyor" iken doludur.
    """
    kalan = kalan_dosyalar(repo)
    fazlalar = [yol for yol in kalan if yol != BEKLENEN]
    if not fazlalar:
        return {"durum": "mezar-tasi", "kalan": [], "not": None}

    goster = fazlalar[:10]
    artan = len(fazlalar) - len(goster)
    not_metni = (
        f"bosaltilmis gorunmuyor: calisma agacinda README.md disinda {len(fazlalar)} dosya var "
        f"({', '.join(goster)}" + (f", +{artan} tane daha)" if artan > 0 else ")")
    )
    return {"durum": "bosaltilmis-gorunmuyor", "kalan": fazlalar, "not": not_metni}