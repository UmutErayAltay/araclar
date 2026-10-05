"""Rapor: bulgulari insan-okur tabloya cevirir (+ ozet satiri).

Bu modul YAZMAZ: arac salt-okunurdur, rapor yalniz ekrana basilir.
"""

from __future__ import annotations

from pathlib import Path

#: Tablodaki kolonlar.
KOLONLAR = ("repo", "readme", "tur", "iddia", "gercek")


def _hucre(bulgu: dict, kolon: str) -> str:
    deger = bulgu.get(kolon, "")
    if kolon == "repo":
        deger = Path(str(deger)).name or str(deger)  # tabloda kisa ad yeter
    return " ".join(str(deger).split()) or "-"


def _sutun(bulgular: list[dict]) -> str:
    satirlar = [[_hucre(b, k) for k in KOLONLAR] for b in bulgular]
    genislik = [
        max(len(kol), *(len(s[i]) for s in satirlar)) if satirlar else len(kol)
        for i, kol in enumerate(KOLONLAR)
    ]

    def birlestir(hucre: list[str]) -> str:
        return "  ".join(hucre[i].ljust(genislik[i]) for i in range(len(hucre))).rstrip()

    return "\n".join([birlestir(list(KOLONLAR)), *(birlestir(s) for s in satirlar)])


def _tur_sayimi(bulgular: list[dict]) -> dict[str, int]:
    sayim: dict[str, int] = {}
    for b in bulgular:
        sayim[b["tur"]] = sayim.get(b["tur"], 0) + 1
    return sayim


def tablo(bulgular: list[dict]) -> str:
    """Insan-okur metin tablosu + tur bazli ozet satiri."""
    if not bulgular:
        return "bulgu yok (README iddialari kodla uyumlu)"
    sayim = _tur_sayimi(bulgular)
    ozet = ", ".join(f"{sayim[tur]} {tur}" for tur in sorted(sayim))
    return f"{_sutun(bulgular)}\nozet: {len(bulgular)} bulgu ({ozet})"


def json_uret(bulgular: list[dict], repolar: list[Path]) -> dict:
    """`--json` ciktisi: JSON'a uygun govde (ensure_ascii=False ile basilir)."""
    return {
        "surum": 1,
        "bulgu_sayisi": len(bulgular),
        "repo_sayisi": len(repolar),
        "tur_sayimi": _tur_sayimi(bulgular),
        "bulgular": bulgular,
    }