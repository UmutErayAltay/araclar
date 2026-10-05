"""Rapor: insan-okur metin (varsayilan) ve JSON.

Bu modul SADECE yazdirir: hicbir dosya yazmaz. Raporun sonunda `karar.py`'nin
sabit kapanis uyarisi yer alir.
"""

from __future__ import annotations

from .tasima import GOSTERME_LIMITI

#: Uzun eksik listelerinde kacilinacak dosya sayisi.
KISALTMA = 25


def _bas(rapor: dict) -> list[str]:
    kok, arac = rapor["kok"], rapor["arac_repo"]
    return [f"kok:    {kok}", f"arac:   {arac}", ""]


def _repo_satirlari(repo: dict) -> list[str]:
    tasi = repo["mezar_tasi"]
    tasima = repo["tasima_tamlik"]
    gonder = repo["gonderilmemis"]
    gecmis = repo["gecmis_secret"]

    satirlar = [f"[{repo['ad']}]  {repo['karar']}", f"  yol:   {repo['yol']}", f"  hedef: {repo['hedef']}"]

    # 1) mezar tasi
    if tasi["durum"] == "mezar-tasi":
        satirlar.append("  mezar_tasi:      evet (yalniz README.md)")
    else:
        satirlar.append(f"  mezar_tasi:      HAYIR - {tasi['not']}")

    # 2) tasima tamlik
    if tasima["durum"] == "atlandi":
        satirlar.append("  tasima_tamlik:   atlandi - HEAD~1 yok")
    elif tasima["durum"] == "tam":
        satirlar.append(f"  tasima_tamlik:   tam ({tasima['kaynak']} dosya)")
    else:
        satirlar.append(
            f"  tasima_tamlik:   {tasima['eksik_sayisi']} EKSİK "
            f"({tasima['kaynak']} kaynak / {tasima['hedef']} hedef)"
        )
        for yol in tasima["eksik_gosterilen"]:
            satirlar.append(f"      - eksik: {yol}")
        artan = tasima["eksik_sayisi"] - len(tasima["eksik_gosterilen"])
        if artan > 0:
            satirlar.append(f"      ... +{artan} dosya daha (en fazla {GOSTERME_LIMITI} liste)")

    # 3) gonderilmemis
    if gonder["durum"] == "remote-yok":
        satirlar.append("  gonderilmemis:   BİLİNEMEDİ - remote izi yok")
    elif gonder["uzakta_yok"]:
        satirlar.append(
            f"  gonderilmemis:   [{gonder['onem']}] {gonder['uzakta_yok']} commit uzakta yok "
            f"({gonder['referans']})"
        )
        for konu in gonder["konular"]:
            satirlar.append(f"      - {konu}")
    else:
        satirlar.append(f"  gonderilmemis:   temiz ({gonder['referans']})")
    if gonder["kirli"]:
        satirlar.append(f"  calisma agaci:   KİRLİ ({len(gonder['kirli'])} yol)")
        for yol in gonder["kirli"][:KISALTMA]:
            satirlar.append(f"      - {yol}")
        if len(gonder["kirli"]) > KISALTMA:
            satirlar.append(f"      ... +{len(gonder['kirli']) - KISALTMA} yol daha")

    # 4) gecmis secret
    if gecmis["bulundu"]:
        satirlar.append(f"  gecmis_secret:   {len(gecmis['bulundu'])} iz BULUNDU (deger gosterilmez)")
        for bulgu in gecmis["bulundu"][:KISALTMA]:
            satirlar.append(
                f"      - {bulgu['commit']} {bulgu['dosya']} {bulgu['tur']} izi={bulgu['izi']}"
            )
        if len(gecmis["bulundu"]) > KISALTMA:
            satirlar.append(f"      ... +{len(gecmis['bulundu']) - KISALTMA} bulgu daha")
    else:
        satirlar.append("  gecmis_secret:   temiz")

    for notlar in repo["notlar"]:
        if notlar.startswith("kismi"):
            satirlar.append(f"  ! UYARI: {notlar}")
    satirlar.append("")
    return satirlar


def metin(rapor: dict) -> str:
    """Tam metin rapor (uyari satiri dahil)."""
    satirlar = _bas(rapor)
    for repo in rapor["repolar"]:
        satirlar.extend(_repo_satirlari(repo))
    o = rapor["ozet"]
    satirlar.append(
        f"ozet: {o['toplam']} repo, {o['kapatilabilir']} KAPATILABILIR, {o['dikkat']} DIKKAT"
    )
    satirlar.append(f"\n{rapor['uyari']}")
    return "\n".join(satirlar)