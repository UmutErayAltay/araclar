"""Degisiklik modeli ve guvenli uygulama: once yedek, sonra yazma, hata halinde geri yukleme."""

from __future__ import annotations

import warnings
from collections.abc import Mapping
from dataclasses import dataclass, replace

from .analiz import parcala
from .kaynak import Deger, Kaynak
from .yedek import YedekHatasi, gunluk_ekle, goruntu_al, yedek_oku, yedek_yaz


class CakismaHatasi(RuntimeError):
    """Degisken, okunduktan sonra baska bir yerden degismis ya da yeni ad mevcut bir adla cakisiyor."""


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


@dataclass(frozen=True)
class UygulamaSonucu:
    yedek_id: str
    yayinlandi: bool  # False: yazma tamam ama acik surecler duyurulamadi (yeni terminaller yine gecerli)


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


def ad_coz(mevcut: Mapping[str, Deger], ad: str, windows: bool) -> str | None:
    """Mevcut kapsamda `ad`in saklanan yazimi. Windows'ta buyuk/kucuk harf farki yok sayilir."""
    if ad in mevcut:
        return ad
    if windows:
        hedef = ad.casefold()
        for mevcut_ad in mevcut:
            if mevcut_ad.casefold() == hedef:
                return mevcut_ad
    return None


def _tekil_denetle(degisiklikler: list[Degisiklik], windows: bool) -> None:
    gorulen: set[tuple[str, str]] = set()
    for d in degisiklikler:
        anahtar_ad = d.ad.casefold() if windows else d.ad
        if (d.kapsam, anahtar_ad) in gorulen:
            raise ValueError(f"ayni deger bir uygulamada iki kez degistirilemez: {d.kapsam}/{d.ad}")
        gorulen.add((d.kapsam, anahtar_ad))


def cakisma_denetle(kaynak: Kaynak, degisiklikler: list[Degisiklik],
                    goruntu: Mapping[str, Mapping[str, Deger]]) -> list[Degisiklik]:
    """Eski degerleri `goruntu` ile karsilastirir (yedekle ayni anlik goruntu). Yazmadan once cagrilir.

    Windows'ta ad buyuk/kucuk harf duyarsiz eslesir: var olan ad icin saklanan yazim kullanilir;
    yeni bir ad, mevcut bir adin yalniz harf farkiyla yazilmis hali olamaz. Cakisma varsa CakismaHatasi.
    """
    eski_cakisan: list[str] = []
    yeni_cakisan: list[str] = []
    cozumlu: list[Degisiklik] = []
    for d in degisiklikler:
        kapsam_goruntu = goruntu.get(d.kapsam, {})
        sakli = ad_coz(kapsam_goruntu, d.ad, kaynak.windows)
        etiket = f"{d.kapsam}/{d.ad}"
        if d.eski is None:
            if sakli is None:
                cozumlu.append(d)
            else:
                yeni_cakisan.append(f"{etiket} (zaten var: {sakli})")
        elif sakli is None or kapsam_goruntu[sakli] != d.eski:
            eski_cakisan.append(etiket)
        else:
            cozumlu.append(d if sakli == d.ad else replace(d, ad=sakli))
    mesajlar = []
    if eski_cakisan:
        mesajlar.append("degisken siz duzenlerken baska yerden degisti: " + ", ".join(eski_cakisan))
    if yeni_cakisan:
        mesajlar.append("ayni adli degisken zaten var: " + ", ".join(yeni_cakisan))
    if mesajlar:
        raise CakismaHatasi("; ".join(mesajlar))
    return cozumlu


def _geri_sar(kaynak: Kaynak, uygulanan: list[Degisiklik],
              goruntu: Mapping[str, Mapping[str, Deger]]) -> tuple[bool, list[str]]:
    """Yazilan adlari yedek anlik goruntusune gore geri alir.

    Yedekte olan ad, yedekteki (saklanan yazimli) degerine doner; yedekte olmayan ad silinir.
    Boylece d.eski'ye ya da ad eslesmesine dayanilmaz: windows'ta 'PATH' ile 'Path' ayni degisken.
    """
    hatalar: list[str] = []
    for d in reversed(uygulanan):
        try:
            kapsam_goruntu = goruntu.get(d.kapsam, {})
            sakli = ad_coz(kapsam_goruntu, d.ad, kaynak.windows)
            if sakli is None:
                kaynak.sil(d.kapsam, d.ad)
            else:
                kaynak.yaz(d.kapsam, sakli, kapsam_goruntu[sakli])
        except Exception as exc:  # hata kaydedilir, mesajda raporlanir
            hatalar.append(f"{d.kapsam}/{d.ad}: {type(exc).__name__}")
    return not hatalar, hatalar


def _gunluge_yaz(ayirici: str, liste: list[Degisiklik], yedek_id: str, yayin_hatasi: str | None) -> None:
    """Yazmadan sonra calisir: gunluk hatasi degisikligi geri almaz, yalniz uyari verir."""
    try:
        if yayin_hatasi is not None:
            gunluk_ekle({"eylem": "yayinla_hatasi", "yedek": yedek_id, "hata": yayin_hatasi})
        for d in liste:
            kayit = {"kapsam": d.kapsam, "ad": d.ad, "eylem": eylem_adi(d), "yedek": yedek_id}
            if d.ad.casefold() == "path":
                fark = path_farki(
                    d.eski.metin if d.eski is not None else "",
                    d.yeni.metin if d.yeni is not None else "",
                    ayirici,
                )
                kayit["eklenen"] = fark["eklenen"]
                kayit["cikan"] = fark["cikan"]
            gunluk_ekle(kayit)
    except YedekHatasi as exc:
        warnings.warn(
            f"degisiklikler yazildi ama gunluge yazilamadi ({exc}); yedek: {yedek_id}",
            stacklevel=3,
        )


def uygula_ayrintili(kaynak: Kaynak, degisiklikler: list[Degisiklik]) -> UygulamaSonucu:
    """Degisiklikleri uygular.

    Hata siniflari: ValueError (kullanim), YetkiHatasi / CakismaHatasi / YedekHatasi (hicbir sey
    yazilmadi), UygulamaHatasi (yazma basarisiz; `geri_yuklendi` geri yuklemenin sonucunu gosterir).
    Yazmadan sonraki yayin ve gunluk hatalari istisna firlatmaz; uyari verilir.
    """
    if not degisiklikler:
        raise ValueError("uygulanacak degisiklik yok")
    _tekil_denetle(degisiklikler, kaynak.windows)

    kapsamlar = list(dict.fromkeys(d.kapsam for d in degisiklikler))
    yazilamaz = [k for k in kapsamlar if not kaynak.yazilabilir(k)]
    if yazilamaz:
        raise YetkiHatasi("yazilamayan kapsam: " + ", ".join(yazilamaz))

    # Anlik goruntu once alinir; karsilastirma ve yedek ayni veriyi kullanir.
    goruntu = goruntu_al(kaynak, kapsamlar)
    liste = cakisma_denetle(kaynak, degisiklikler, goruntu)
    yedek_id = yedek_yaz(goruntu, kaynak.ad)

    uygulanan: list[Degisiklik] = []
    try:
        for d in liste:
            # Yazmadan once listeye ekle: hata aninda yazilmis olabilecek degisiklik de geri alinir.
            uygulanan.append(d)
            if d.yeni is None:
                kaynak.sil(d.kapsam, d.ad)
            else:
                kaynak.yaz(d.kapsam, d.ad, d.yeni)
    except Exception as exc:
        geri, hatalar = _geri_sar(kaynak, uygulanan, goruntu)
        if geri:
            mesaj = f"yazma basarisiz ({type(exc).__name__}); degisiklikler geri yuklendi (yedek: {yedek_id})"
        else:
            mesaj = (f"yazma basarisiz ({type(exc).__name__}); GERI YUKLENEMEDI, "
                     f"geri-al ile donun (yedek: {yedek_id}): " + "; ".join(hatalar))
        raise UygulamaHatasi(mesaj, geri_yuklendi=geri) from exc

    yayinlandi = True
    yayin_hatasi: str | None = None
    try:
        kaynak.yayinla()
    except Exception as exc:
        yayinlandi = False
        yayin_hatasi = type(exc).__name__
        warnings.warn(
            f"degisiklikler yazildi ama yayinlanamadi ({yayin_hatasi}); "
            f"acik surecler etkilenmeyebilir (yedek: {yedek_id})",
            stacklevel=2,
        )

    _gunluge_yaz(kaynak.ayirici, liste, yedek_id, yayin_hatasi)
    return UygulamaSonucu(yedek_id=yedek_id, yayinlandi=yayinlandi)


def uygula(kaynak: Kaynak, degisiklikler: list[Degisiklik]) -> str:
    """Yedek kimligini doner. Yayin durumu gerekiyorsa `uygula_ayrintili` kullanilir."""
    return uygula_ayrintili(kaynak, degisiklikler).yedek_id


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
