"""Degisiklik modeli ve guvenli uygulama: once yedek, sonra yazma, hata halinde geri yukleme."""

from __future__ import annotations

import warnings
from dataclasses import dataclass

from .analiz import parcala
from .kaynak import Deger, Kaynak
from .yedek import gunluk_ekle, yedek_al, yedek_oku


class CakismaHatasi(RuntimeError):
    """Degisken, okunduktan sonra baska bir yerden degismis."""


class YetkiHatasi(RuntimeError):
    """Hedef kapsam yazilabilir degil."""


class UygulamaHatasi(RuntimeError):
    """Yazma basarisiz oldu. `geri_yuklendi` onceki durumun geri yuklenip yuklenmedigini gosterir."""

    def __init__(self, mesaj: str, geri_yuklendi: bool) -> None:
        super().__init__(mesaj)
        self.geri_yuklendi = geri_yuklendi


@dataclass(frozen=True)
class Degisiklik:
    kapsam: str
    ad: str
    eski: Deger | None   # beklenen mevcut deger (None = yok olmali)
    yeni: Deger | None   # None = sil

    def sozluk(self) -> dict:
        return {
            "kapsam": self.kapsam,
            "ad": self.ad,
            "eski": None if self.eski is None else self.eski.sozluk(),
            "yeni": None if self.yeni is None else self.yeni.sozluk(),
        }

    @classmethod
    def sozlukten(cls, d: dict) -> "Degisiklik":
        try:
            eski = d.get("eski")
            yeni = d.get("yeni")
            return cls(
                kapsam=str(d["kapsam"]),
                ad=str(d["ad"]),
                eski=None if eski is None else Deger.sozlukten(eski),
                yeni=None if yeni is None else Deger.sozlukten(yeni),
            )
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise ValueError("gecersiz degisiklik kaydi") from exc


def eylem_adi(d: Degisiklik) -> str:
    if d.yeni is None:
        return "sil"
    if d.eski is None:
        return "ekle"
    return "degistir"


def path_farki(eski: str, yeni: str, ayirici: str) -> dict:
    """Ham metin kumeleri uzerinden eklenen/cikan girdiler (sira korunur, tekil)."""
    eski_listesi = parcala(eski, ayirici)
    yeni_listesi = parcala(yeni, ayirici)
    eski_kume = set(eski_listesi)
    yeni_kume = set(yeni_listesi)
    eklenen = list(dict.fromkeys(g for g in yeni_listesi if g not in eski_kume))
    cikan = list(dict.fromkeys(g for g in eski_listesi if g not in yeni_kume))
    return {"eklenen": eklenen, "cikan": cikan}


def _geri_sar(kaynak: Kaynak, uygulanan: list[Degisiklik]) -> tuple[bool, list[str]]:
    hatalar: list[str] = []
    for d in reversed(uygulanan):
        try:
            if d.eski is None:
                kaynak.sil(d.kapsam, d.ad)
            else:
                kaynak.yaz(d.kapsam, d.ad, d.eski)
        except Exception as exc:  # hata kaydedilir, mesajda raporlanir
            hatalar.append(f"{d.kapsam}/{d.ad}: {type(exc).__name__}")
    return not hatalar, hatalar


def uygula(kaynak: Kaynak, degisiklikler: list[Degisiklik]) -> str:
    """Degisiklikleri uygular ve yedek kimligini doner. Hic yazilmadan once tum kontroller yapilir."""
    if not degisiklikler:
        raise ValueError("uygulanacak degisiklik yok")

    gorulen: set[tuple[str, str]] = set()
    for d in degisiklikler:
        if (d.kapsam, d.ad) in gorulen:
            raise ValueError(f"ayni deger bir uygulamada iki kez degistirilemez: {d.kapsam}/{d.ad}")
        gorulen.add((d.kapsam, d.ad))

    kapsamlar = list(dict.fromkeys(d.kapsam for d in degisiklikler))
    yazilamaz = [k for k in kapsamlar if not kaynak.yazilabilir(k)]
    if yazilamaz:
        raise YetkiHatasi("yazilamayan kapsam: " + ", ".join(yazilamaz))

    mevcut = {k: kaynak.oku(k) for k in kapsamlar}
    cakisanlar = [f"{d.kapsam}/{d.ad}" for d in degisiklikler if mevcut[d.kapsam].get(d.ad) != d.eski]
    if cakisanlar:
        raise CakismaHatasi("degisken siz duzenlerken baska yerden degisti: " + ", ".join(cakisanlar))

    yedek_id = yedek_al(kaynak, kapsamlar)

    uygulanan: list[Degisiklik] = []
    try:
        for d in degisiklikler:
            # Yazmadan once listeye ekle: hata aninda yazilmis olabilecek degisiklik de geri alinir.
            uygulanan.append(d)
            if d.yeni is None:
                kaynak.sil(d.kapsam, d.ad)
            else:
                kaynak.yaz(d.kapsam, d.ad, d.yeni)
    except Exception as exc:
        geri, hatalar = _geri_sar(kaynak, uygulanan)
        if geri:
            mesaj = f"yazma basarisiz ({type(exc).__name__}); degisiklikler geri yuklendi (yedek: {yedek_id})"
        else:
            mesaj = (f"yazma basarisiz ({type(exc).__name__}); GERI YUKLENEMEDI, "
                     f"geri-al ile donun (yedek: {yedek_id}): " + "; ".join(hatalar))
        raise UygulamaHatasi(mesaj, geri_yuklendi=geri) from exc

    try:
        kaynak.yayinla()
    except Exception as exc:
        warnings.warn(
            f"degisiklikler yazildi ama yayinlanamadi ({type(exc).__name__}); "
            f"acik surecler etkilenmeyebilir (yedek: {yedek_id})",
            stacklevel=2,
        )
        gunluk_ekle({"eylem": "yayinla_hatasi", "yedek": yedek_id, "hata": type(exc).__name__})

    for d in degisiklikler:
        kayit = {"kapsam": d.kapsam, "ad": d.ad, "eylem": eylem_adi(d), "yedek": yedek_id}
        if d.ad.casefold() == "path":
            fark = path_farki(
                d.eski.metin if d.eski is not None else "",
                d.yeni.metin if d.yeni is not None else "",
                kaynak.ayirici,
            )
            kayit["eklenen"] = fark["eklenen"]
            kayit["cikan"] = fark["cikan"]
        gunluk_ekle(kayit)
    return yedek_id


def geri_al_plani(kaynak: Kaynak, yedek_id: str) -> list[Degisiklik]:
    """Yedekteki kapsamlarda mevcut durum ile yedek arasindaki farklar."""
    goruntu = yedek_oku(yedek_id)
    plan: list[Degisiklik] = []
    for kapsam, yedek_degerleri in goruntu["kapsamlar"].items():
        simdiki = kaynak.oku(kapsam)
        for ad in sorted(set(simdiki) | set(yedek_degerleri), key=str.casefold):
            eski = simdiki.get(ad)
            yeni = yedek_degerleri.get(ad)
            if eski != yeni:
                plan.append(Degisiklik(kapsam, ad, eski=eski, yeni=yeni))
    return plan
