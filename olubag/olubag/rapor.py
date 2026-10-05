"""Rapor: terminal tablosu. Bu arac SALT OKUNURDUR — hicbir dosya yazilmaz."""

from __future__ import annotations


def _sutunlar(veri: dict) -> str:
    """repo / dosya:satir / paket / tur sutunlari, enine hizalama."""
    satirlar: list[tuple[str, str, str, str, str]] = []
    for r in veri.get("repolar", []):
        for b in r.get("bulgular", []):
            konum = f"{b['dosya']}:{b['satir']}"
            satirlar.append((r["repo"], konum, b["paket"], b["tur"], ""))
    basliklar = ("repo", "dosya:satir", "paket", "tur")
    hucreler = [list(basliklar)] + [list(s[:4]) for s in satirlar]
    genislik = [
        max(len(h[i]) for h in hucreler) for i in range(len(basliklar))
    ]
    return "\n".join(
        "  ".join(h[i].ljust(genislik[i]) for i in range(len(h))).rstrip() for h in hucreler
    )


def tablo(veri: dict) -> str:
    """Insan-okur metin tablosu + ozet satiri."""
    ozet = veri.get("ozet", {})
    govde = _sutunlar(veri) if veri.get("repolar") and any(r.get("bulgular") for r in veri["repolar"]) else "(bulgu yok)"
    return (
        f"{govde}\n"
        f"ozet: {ozet.get('repo', 0)} repo, "
        f"{ozet.get('kullanilmayan', 0)} kullanilmayan, "
        f"{ozet.get('belirsiz', 0)} belirsiz"
    )