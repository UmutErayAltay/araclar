"""Rapor: terminal tablosu + JSON (dosyaya rapor YAZILMAZ)."""

from __future__ import annotations

from .maskele import rotasyon

#: Uc satiri sabit: her rapor bu yasagi hatirlatir.
ROTASYON_UYARISI = "Maskeleme git geçmişini temizlemez; anahtarı sağlayıcıda döndürün."


def _sutun(basliklar: list[str], satirlar: list[list[str]]) -> str:
    """Sola yasali, sutunlari hizalayan metin tablosu."""
    genislik = [
        max(len(basliklar[i]), *(len(s[i]) for s in satirlar)) if satirlar else len(basliklar[i])
        for i in range(len(basliklar))
    ]

    def birlestir(hucre: list[str]) -> str:
        return "  ".join(hucre[i].ljust(genislik[i]) for i in range(len(hucre))).rstrip()

    return "\n".join([birlestir(basliklar), *(birlestir(s) for s in satirlar)])


def tablo(rapor: dict, *, kuru: bool) -> str:
    """Insan-okur metin raporu: bulgular + ozet + rotasyon listesi.

    Sutunlar: repo, dosya:satir, tur, ad, izi. DEGER YOK (izi `kisa` ise kisa
    deger parmak izi alamaz; ham deger de hicbir yerde yazilmaz).
    """
    bulgar = rapor.get("bulgar", [])
    basliklar = ["repo", "dosya:satir", "tur", "ad", "izi"]
    satirlar = [
        [
            _kisa(bulgu.get("repo", "")),
            f"{bulgu.get('dosya', '?')}:{bulgu.get('satir', '?')}",
            str(bulgu.get("tur", "?")),
            str(bulgu.get("ad", "?")),
            str(bulgu.get("izi")),
        ]
        for bulgu in bulgar
    ]

    satirlar_ozet: list[str] = []
    if not bulgar:
        satirlar_ozet.append("bulgu yok")
    else:
        satirlar_ozet.append(f"toplam {len(bulgar)} bulgu, {rapor.get('dosya', 0)} dosya tarandi")

    cikti = [_sutun(basliklar, satirlar)] if bulgar else ["bulgu yok"]
    cikti.extend(satirlar_ozet)
    cikti.extend(_rotasyon_metni(bulgar))
    if not kuru:
        cikti.append(f"maskelendi: {len(rapor.get('maskelendi', []))} bulgu")
    atlanan = rapor.get("atlanan") or []
    if atlanan:
        cikti.append(f"{len(atlanan)} dosya atlandi")
    return "\n".join(cikti)


def _rotasyon_metni(bulgar: list[dict]) -> list[str]:
    """Rotasyon listesi: dondurulmesi gereken anahtarlar (ayni sira tek satir)."""
    kayitlar = rotasyon(bulgar)
    if not kayitlar:
        return []
    satirlar = ["", "rotasyon listesi (degistirilmesi gereken anahtarlar):"]
    for kayit in kayitlar:
        adlar = ", ".join(kayit["adlar"])
        nerede = ", ".join(kayit["nerede"])
        satirlar.append(f"  {adlar}  {kayit['tur']}  {kayit['izi']}  {nerede}")
    satirlar.append(f"  ! {ROTASYON_UYARISI}")
    return satirlar


def _kisa(yol: str) -> str:
    """Repo yolunu son iki parcaya kisaltir (tablo okunur kalsin)."""
    parcalar = str(yol).replace("\\", "/").rstrip("/").split("/")
    return "/".join(parcalar[-2:]) if len(parcalar) > 1 else str(yol)


def json_ve(rapor: dict, *, kuru: bool) -> dict:
    """JSON ciktisinin govdesi: bulgular + rotasyon + uyari (deger YOK)."""
    return {
        "bulgar": rapor.get("bulgar", []),
        "maskelendi": rapor.get("maskelendi", []),
        "dosya": rapor.get("dosya", 0),
        "rotasyon": rotasyon(rapor.get("bulgar", [])),
        "kuru_calistirma": kuru,
        "uyari": ROTASYON_UYARISI,
    }