"""Terminal tablosu: bulgulari insan-okur tek satira indirger.

Guvenlik: burada YALNIZ ad, dosya:satir ve tur yazilir. Deger ne tabloya
ne ozete girer.
"""

from __future__ import annotations

from pathlib import Path

#: Tur sirasi (rapor okunurken onem sirasi).
TUR_SIRASI = ("env_izleniyor", "env_gitignorede_degil", "belgelenmemis", "kullanilmayan")


def _tur_sirasi(tur: str) -> int:
    return TUR_SIRASI.index(tur) if tur in TUR_SIRASI else len(TUR_SIRASI)


def _sutun(satirlar: list[list[str]], basliklar: list[str]) -> str:
    genislik = [
        max(len(basliklar[i]), *(len(s[i]) for s in satirlar)) if satirlar else len(basliklar[i])
        for i in range(len(basliklar))
    ]

    def birlestir(hucre: list[str]) -> str:
        return "  ".join(hucre[i].ljust(genislik[i]) for i in range(len(hucre))).rstrip()

    return "\n".join([birlestir(basliklar), *(birlestir(s) for s in satirlar)])


def _konum(bulgu: dict) -> str:
    dosya, satir = bulgu.get("dosya"), bulgu.get("satir")
    if dosya and satir:
        return f"{dosya}:{satir}"
    return dosya or "-"


def tablo(veri: dict) -> str:
    """Insan-okur metin tablosu + ozet satiri."""
    satirlar: list[list[str]] = []
    for bulgu in sorted(
        veri.get("bulgular", []),
        key=lambda b: (_tur_sirasi(b["tur"]), Path(b.get("repo", "")).name, b.get("ad") or ""),
    ):
        satirlar.append(
            [
                bulgu["tur"],
                Path(bulgu.get("repo", "")).name or "?",
                bulgu.get("ad") or "-",
                _konum(bulgu),
            ]
        )
    basliklar = ["tur", "repo", "ad", "dosya:satir"]
    govde = _sutun(satirlar, basliklar) if satirlar else "  ".join(basliklar)
    return f"{govde}\nozet: {veri.get('toplam', 0)} bulgu, {len(veri.get('repolar', []))} repo"
