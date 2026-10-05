"""Karar: dort denetimin sonucunu `KAPATILABILIR` / `DIKKAT` olarak ozetler.

Kural tek cumleyle: eksik dosya, gonderilmemiş commit, gecmiste gizli anahtar
izi ya da yarim kalmis tarama varsa `DIKKAT`; hicbiri yoksa `KAPATILABILIR`.

"remote izi yok" ve "bosaltilmis gorunmuyor" BULGU DEGILDIR: yalniz not olarak
rapora girer ve karari tek basina degistirmez. Bir repo hicbir yere
gonderilmemis olabilir -- bu onu guvenli kapatmaz.

Bu modul karar verir, HICBIR SEY DEGISTIRMEZ. Silme/arsivleme aracin isinde
YOKTUR.
"""

from __future__ import annotations

from pathlib import Path

from . import gonderilmemis, gecmis, tasi, tasima
from . import kesif

KAPATILABILIR = "KAPATILABILIR"
DIKKAT = "DIKKAT"

#: Raporun sonunda her zaman yazan sabit uyari.
KAPANIS_UYARISI = (
    "Bu arac silmez/arşivlemez; kararı siz verirsiniz. "
    "Geçmişte secret bulunduysa repoyu silmek yetmez, anahtarı döndürün."
)


def denetle_repo(
    ad: str, kok: Path, arac_repo: Path, *, satir_limiti: int, sure_limiti: float
) -> dict:
    """Tek repo icin dort denetimi calistirir ve karar sozlugunu doner."""
    repo = kesif.repo_coz(ad, kok)
    arac_hedefi = kesif.arac_hedefi(arac_repo, ad)

    tasi_sonuc = tasi.denetle(repo)
    tasima_sonuc = tasima.denetle(repo, arac_hedefi)
    gonder_sonuc = gonderilmemis.denetle(repo)
    gecmis_sonuc = gecmis.tara(repo, satir_limiti=satir_limiti, sure_limiti=sure_limiti)

    nedenler: list[str] = []
    notlar: list[str] = []
    for not_metni in (tasi_sonuc["not"], gonder_sonuc["not"], tasima_sonuc["not"], gecmis_sonuc["not"]):
        if not_metni:
            notlar.append(not_metni)

    if tasima_sonuc["durum"] == "atlandi":
        nedenler.append("taşıma tamlığı doğrulanamadı (HEAD~1 yok)")
    elif tasima_sonuc["eksik_sayisi"]:
        nedenler.append(
            f"taşıma eksik: {tasima_sonuc['eksik_sayisi']} dosya hedefte yok"
        )
    if gonder_sonuc["durum"] == "gonderilmemis-var":
        nedenler.append(f"{gonder_sonuc['uzakta_yok']} commit uzakta yok")
    if gonder_sonuc["kirli"]:
        nedenler.append(f"çalışma ağacı kirli ({len(gonder_sonuc['kirli'])} yol)")
    if gecmis_sonuc["bulundu"]:
        nedenler.append(f"geçmişte {len(gecmis_sonuc['bulundu'])} gizli anahtar izi")
    if gecmis_sonuc["kismi"]:
        nedenler.append("geçmiş taraması yarım kaldı")

    return {
        "ad": ad,
        "yol": str(repo),
        "hedef": str(arac_hedefi),
        "karar": DIKKAT if nedenler else KAPATILABILIR,
        "nedenler": nedenler,
        "notlar": notlar,
        "mezar_tasi": tasi_sonuc,
        "tasima_tamlik": tasima_sonuc,
        "gonderilmemis": gonder_sonuc,
        "gecmis_secret": gecmis_sonuc,
    }


def denetle(
    kok: Path,
    arac_repo: Path,
    adlar: list[str],
    *,
    satir_limiti: int = gecmis.SATIR_LIMITI,
    sure_limiti: float = gecmis.SURE_LIMITI,
) -> dict:
    """Verilen repolari sirayla denetler; ozet + rapor sozlugunu doner.

    Kullanim hatasi (kok yok, repo git deposu degil) `KesifHatasi` ile firlatir.
    Bir repo denetimde cokerse arac KAPANIR: yarim rapor, kararsizlik degil
    sessizlik olmamalidir.
    """
    repolar = [denetle_repo(ad, kok, arac_repo, satir_limiti=satir_limiti, sure_limiti=sure_limiti)
               for ad in adlar]
    kapali = [r for r in repolar if r["karar"] == KAPATILABILIR]
    return {
        "kok": str(kok),
        "arac_repo": str(arac_repo),
        "repolar": repolar,
        "ozet": {
            "toplam": len(repolar),
            "kapatilabilir": len(kapali),
            "dikkat": len(repolar) - len(kapali),
        },
        "uyari": KAPANIS_UYARISI,
    }