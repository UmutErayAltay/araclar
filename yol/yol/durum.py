"""Ortak durum katmani (CLI ve web paneli): PATH bulgulari, komut raporu, degisken listesi."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import asdict
from typing import Any

from .analiz import IZLENEN, etkin_dizinler, genislet, girdileri_analiz, komut_raporu, ozet, temizlik_onerisi
from .gizli import gizli_mi, maskele
from .kaynak import KULLANICI, Deger, Kaynak

_VARSAYILAN_PATHEXT = ".COM;.EXE;.BAT;.CMD"


def platform_bilgisi(kaynak: Kaynak) -> dict:
    return {
        "kaynak": kaynak.ad,
        "windows": kaynak.windows,
        "ayirici": kaynak.ayirici,
        "kapsamlar": [{"ad": k, "yazilabilir": kaynak.yazilabilir(k)} for k in kaynak.kapsamlar()],
    }


def _ci_al(ortam: Mapping[str, str], ad: str) -> str | None:
    if ad in ortam:
        return ortam[ad]
    for anahtar_ad, deger in ortam.items():
        if anahtar_ad.casefold() == ad.casefold():
            return deger
    return None


def path_kaydi(degerler: Mapping[str, Deger]) -> tuple[str | None, Deger | None]:
    """Bir kapsamdaki PATH degiskeninin (saklanan adi, degeri). Yoksa (None, None)."""
    if "PATH" in degerler:
        return "PATH", degerler["PATH"]
    for ad, deger in degerler.items():
        if ad.casefold() == "path":
            return ad, deger
    return None, None


def ortam_olustur(kaynak: Kaynak) -> dict[str, str]:
    """Surec ortami + tum kapsam degerleri (kapsam degerleri kazanir; sonraki kapsam onceki uzerine yazar).

    REG_EXPAND_SZ (genisler) degerler acilir. Acma sirasinda bir ad once surec ortamindan,
    yoksa kayittaki degerden alinir; boylece %ProgramFiles% gibi ic ice degiskenler cozulur.
    """
    surec: dict[str, str] = dict(os.environ)
    kayitlar: dict[str, Deger] = {}
    for kapsam in kaynak.kapsamlar():
        kayitlar.update(kaynak.oku(kapsam))
    acma: dict[str, str] = {ad: deger.metin for ad, deger in kayitlar.items()}
    acma.update(surec)  # surec ortami once: ayni ad icin kayittan onceliklidir
    ortam: dict[str, str] = dict(surec)
    for ad, deger in kayitlar.items():
        ortam[ad] = genislet(deger.metin, acma, kaynak.windows) if deger.genisler else deger.metin
    return ortam


def _surucu_koku_var(kok: str) -> bool:
    return os.path.isdir(kok)


def _pathext(kaynak: Kaynak, ortam: Mapping[str, str], pathext: list[str] | None) -> list[str]:
    if pathext is not None:
        return list(pathext)
    if not kaynak.windows:
        return []
    ham = _ci_al(ortam, "PATHEXT") or _VARSAYILAN_PATHEXT
    return [p.strip() for p in ham.split(";") if p.strip()]


def yol_baglami(kaynak: Kaynak, ortam: Mapping[str, str] | None = None,
                dizin_var: Callable[[str], bool] = os.path.isdir,
                dosya_var: Callable[[str], bool] = os.path.isfile,
                pathext: list[str] | None = None,
                kok_var: Callable[[str], bool] | None = None) -> dict[str, Any]:
    """PATH'in analiz ve arama icin hazirlanmis hali. Diger islemler bunu paylasir.

    Surucu koku denetimi gercek dosya sistemine bakildiginda yapilir (dizin_var enjekte edilmemisse);
    enjekte edilmis dizin_var sahte bir dunya tanimlar, bu durumda kok varsayilir.
    """
    ortam_son: dict[str, str] = dict(ortam) if ortam is not None else ortam_olustur(kaynak)
    if kok_var is None and dizin_var is os.path.isdir:
        kok_var = _surucu_koku_var
    adlar: dict[str, str | None] = {}
    degerler: dict[str, Deger | None] = {}
    metinler: dict[str, str] = {}
    for kapsam in kaynak.kapsamlar():
        ad, deger = path_kaydi(kaynak.oku(kapsam))
        adlar[kapsam] = ad
        degerler[kapsam] = deger
        metinler[kapsam] = deger.metin if deger is not None else ""

    girdiler = girdileri_analiz(metinler, kaynak.ayirici, ortam_son, kaynak.windows, dizin_var, kok_var)
    dizinler = etkin_dizinler(girdiler)
    uzantilar = _pathext(kaynak, ortam_son, pathext)
    komutlar = komut_raporu(dizinler, kaynak.windows, uzantilar, dosya_var, IZLENEN)
    toplam = len(kaynak.ayirici.join(m for m in metinler.values() if m))
    return {
        "girdiler": girdiler,
        "dizinler": dizinler,
        "komutlar": komutlar,
        "ozet": ozet(girdiler, komutlar, toplam),
        "adlar": adlar,
        "degerler": degerler,
        "metinler": metinler,
        "ortam": ortam_son,
        "pathext": uzantilar,
    }


def path_durumu(kaynak: Kaynak, ortam: Mapping[str, str] | None = None,
                dizin_var: Callable[[str], bool] = os.path.isdir,
                dosya_var: Callable[[str], bool] = os.path.isfile,
                pathext: list[str] | None = None,
                kok_var: Callable[[str], bool] | None = None) -> dict:
    baglam = yol_baglami(kaynak, ortam, dizin_var, dosya_var, pathext, kok_var)
    oneri: dict[str, str] = {}
    if KULLANICI in kaynak.kapsamlar() and kaynak.yazilabilir(KULLANICI):
        yeni = temizlik_onerisi(baglam["metinler"][KULLANICI], baglam["girdiler"], kaynak.ayirici, KULLANICI)
        if yeni is not None:
            oneri[KULLANICI] = yeni
    return {
        "girdiler": [asdict(g) for g in baglam["girdiler"]],
        "komutlar": baglam["komutlar"],
        "ozet": baglam["ozet"],
        "oneri": oneri,
        "path_adlari": baglam["adlar"],
    }


def degiskenler(kaynak: Kaynak, goster: bool = False) -> list[dict]:
    """Gizli gorunenler maskeli gelir (goster=True ile acilir). Maskeli degerin uzunlugu da verilmez."""
    sonuc: list[dict] = []
    for kapsam in kaynak.kapsamlar():
        for ad, deger in kaynak.oku(kapsam).items():
            gizli = gizli_mi(ad, deger.metin)
            acik = goster or not gizli
            sonuc.append({
                "kapsam": kapsam,
                "ad": ad,
                "deger": deger.metin if acik else maskele(deger.metin),
                "gizli": gizli,
                "genisler": deger.genisler,
                "uzunluk": len(deger.metin) if acik else None,
            })
    sonuc.sort(key=lambda s: (s["kapsam"], s["ad"].casefold()))
    return sonuc
