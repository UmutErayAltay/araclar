"""Tarama: her repoda bildirilen bagimliliklari kullanilmayan/belirsiz olarak isaretler.

Kurallar:
- Bildirilen her paket icin: kullanilan import adlari kumesi bulunur.
  Eslesme varsa ve karsilastirilabiliyorsa `kullanilmayan` bulgusu cikar.
- Kodda `__import__`/`importlib.import_module` varsa o paket `belirsiz` sayilir
  (bulgu DEGIL, ayri bir tur).
- Test/derleme araclari ve pytest eklentileri izinli: hicbir zaman bulgu degil.
- hicbir sey yazilmaz.
"""

from __future__ import annotations

import os
from pathlib import Path

from .bildirim import (
    JS_UZANTILARI,
    bildirim_dosyasi_mi,
    bildirimleri,
)
from .eslesme import karsilastir, izinli_mi
from .kaynak import (
    kaynak_dosyasi_mi,
    js_importlari,
    normalle_js,
    python_importlari,
    okunabilir,
)

#: Repo govdesinde atlanan dizinler (bagimlilik agaci, sanal ortam, cikti).
_ATLANAN = frozenset(
    {
        "node_modules",
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        "dist",
        "build",
        ".pytest_cache",
    }
)


def _tara_bir_repo(repo: Path) -> tuple[list[dict], list[str]]:
    """(bulgular, beyan edilen paketler) — tek repo icin."""
    repo = Path(repo)
    bildirimler: list[dict] = []
    py_importlar: set[str] = set()
    js_importlar: set[str] = set()
    py_belirsiz = False
    js_belirsiz = False

    for mevcut, dizinler, dosyalar in os.walk(
        repo, topdown=True, followlinks=False, onerror=lambda _e: None
    ):
        dizinler[:] = sorted(d for d in dizinler if d not in _ATLANAN)
        kok = Path(mevcut)
        for ad in sorted(dosyalar):
            yol = kok / ad
            if not okunabilir(yol):
                continue
            if bildirim_dosyasi_mi(yol):
                bildirimler.extend(bildirimleri(yol, repo))
                continue
            if not kaynak_dosyasi_mi(yol):
                continue
            if yol.suffix == ".py":
                adlar, belirsiz = python_importlari(yol)
                py_importlar |= adlar
                py_belirsiz = py_belirsiz or belirsiz
            elif yol.suffix in JS_UZANTILARI:
                adlar, belirsiz = js_importlari(yol)
                js_importlar |= {normalle_js(a) for a in adlar}
                js_belirsiz = js_belirsiz or belirsiz

    bulgular: list[dict] = []
    beyan: set[str] = set()
    for kayit in bildirimler:
        paket = kayit["paket"]
        if paket in beyan:
            continue  # ayni paket iki kez bildirilmis: tek yerde raporla
        beyan.add(paket)
        if izinli_mi(paket):
            continue  # test/derleme araci veya pytest eklentisi: bulgu degil
        js_kayit = _js_bildirim_mi(kayit)
        if js_kayit:
            kullanilmis = paket in js_importlar
            belirsiz = js_belirsiz
        else:
            kullanilmis = karsilastir(paket, py_importlar)
            belirsiz = py_belirsiz
        if kullanilmis:
            continue  # kullaniliyor: hicbir tur bulgu degil
        bulgular.append({**kayit, "tur": "belirsiz" if belirsiz else "kullanilmayan"})

    return bulgular, sorted(beyan)


def _js_bildirim_mi(kayit: dict) -> bool:
    return kayit["dosya"] == "package.json"


def tara(repolar: list[Path]) -> dict:
    """Tum repolari tarar; bulgulari ve ozeti dondurur (dosya sistemi degismez)."""
    repolar_sonuc: list[dict] = []
    toplam_kullanilmayan = 0
    toplam_belirsiz = 0

    for repo in repolar:
        bulgular, beyan = _tara_bir_repo(Path(repo))
        toplam_kullanilmayan += sum(1 for b in bulgular if b["tur"] == "kullanilmayan")
        toplam_belirsiz += sum(1 for b in bulgular if b["tur"] == "belirsiz")
        repolar_sonuc.append(
            {
                "repo": str(repo),
                "beyan": beyan,
                "bulgular": bulgular,
            }
        )

    return {
        "surum": 1,
        "repolar": repolar_sonuc,
        "ozet": {
            "repo": len(repolar),
            "kullanilmayan": toplam_kullanilmayan,
            "belirsiz": toplam_belirsiz,
        },
    }