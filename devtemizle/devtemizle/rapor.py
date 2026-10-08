"""Rapor: JSON kaydi (atomik) + terminal tablosu (v2).

v2 semasi (PLAN.md §4):
{
  "surum": 2,
  "olusturma": "...",
  "sure_sn": 12.4,
  "adaylar": [{"id": "...", "repo": "...", "yol": "...", "tur": "node_modules",
               "grup": "js", "risk": "guvenli", "boyut": 0, "son_erisim": "...",
               "yas_gun": 0.0, "atlandi": null, "yeniden": "npm install"}],
  "onbellekler": [{"id": "...", "ad": "pip", "yol": "...", "boyut": 0, "risk": "guvenli",
                   "komut": ["pip", "cache", "purge"], "var": true}],
  "docker": {"var": true, "imaj": 0, "konteyner": 0, "volume": 0, "build_cache": 0},
  "repolar": [{"yol": "...", "son_commit": ..., "kirli": false, "aday_boyut": 0}]
}

v1 raporlari da okunabilir (surum alani yoksa 1 sayilir).
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SURUM = 1
SURUM_V2 = 2
VARSAYILAN_AD = "son.json"


def _dizin() -> Path:
    """DEVTEMIZLE_DIR ile dizin degistirilebilir, varsayilan ~/.devtemizle."""
    return Path(os.environ.get("DEVTEMIZLE_DIR") or (Path.home() / ".devtemizle")).expanduser()


def _yol(yol: Path | None = None) -> Path:
    return (Path(yol).expanduser() if yol else _dizin() / VARSAYILAN_AD)


def _gunluk_yol() -> Path:
    """Silinenler gunlugu: ~/.devtemizle/gunluk.jsonl"""
    return _dizin() / "gunluk.jsonl"


def olustur(
    adaylar: list[dict],
    onbellekler: list[dict] | None = None,
    docker: dict | None = None,
    repolar: list[dict] | None = None,
    simdi: float | None = None,
    sure_sn: float = 0.0,
) -> dict:
    """Rapor govdesi (yazmaz; kaydet() yazar).

    Yalniz adaylar verilirse v1 sema (surum/tarih/adaylar; eski cagrilar degismez).
    onbellekler/docker/repolar'dan biri verilirse v2 sema (PLAN.md §4).
    """
    olusturma = datetime.fromtimestamp(
        time.time() if simdi is None else simdi, timezone.utc
    ).isoformat(timespec="seconds")
    if onbellekler is None and docker is None and repolar is None:
        return {"surum": SURUM, "tarih": olusturma, "adaylar": adaylar}
    return {
        "surum": SURUM,  # eski okuyucular icin degismez; yeni alanlar eklemeli
        "sema": SURUM_V2,
        "tarih": olusturma,
        "olusturma": olusturma,
        "sure_sn": sure_sn,
        "adaylar": adaylar,
        "onbellekler": onbellekler or [],
        "docker": docker or {"var": False, "imaj": 0, "konteyner": 0, "volume": 0, "build_cache": 0},
        "repolar": repolar or [],
    }


def kaydet(rapor: dict, yol: Path | None = None) -> Path:
    """Raporu JSON olarak yazar (gecici dosya + os.replace: atomik)."""
    hedef = _yol(yol)
    hedef.parent.mkdir(parents=True, exist_ok=True)
    # Ayni dizinde gecici dosya: os.replace atomik olsun.
    fd, gecici_ad = tempfile.mkstemp(dir=hedef.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as akim:
            json.dump(rapor, akim, ensure_ascii=False, indent=2)
        os.replace(gecici_ad, hedef)
    except BaseException:
        Path(gecici_ad).unlink(missing_ok=True)
        raise
    return hedef


def yukle(yol: Path | None = None) -> dict | None:
    """Son raporu okur; yoksa/bozuksa None.

    v1 raporlari da okur (surum alani yoksa 1 sayilir, diger alanlar bos liste).
    """
    try:
        veri = json.loads(_yol(yol).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    # Geriye uyumluluk: v1 raporu (surum yok veya 1)
    surum = veri.get("surum", 1)
    if surum == 1:
        # v1 format: {"tarih": ..., "adaylar": [...]}
        # v2'ye donustur - yeni alanları koru
        return {
            "surum": 1,
            "olusturma": veri.get("tarih", ""),
            "tarih": veri.get("tarih", ""),
            "sure_sn": veri.get("sure_sn", 0.0),
            "adaylar": veri.get("adaylar", []),
            "onbellekler": veri.get("onbellekler", []),
            "docker": veri.get("docker", {"var": False, "imaj": 0, "konteyner": 0, "volume": 0, "build_cache": 0}),
            "repolar": veri.get("repolar", []),
        }
    return veri


def gunluk_yaz(kayit: dict) -> None:
    """Silinen ogeyi gunluk.jsonl'ye ekler (append, UTF-8)."""
    hedef = _gunluk_yol()
    hedef.parent.mkdir(parents=True, exist_ok=True)
    try:
        with hedef.open("a", encoding="utf-8") as f:
            f.write(json.dumps(kayit, ensure_ascii=False) + "\n")
    except OSError:
        pass  # gunluk yazilamasa bile ana islem durmaz


def gunluk_oku() -> list[dict]:
    """gunluk.jsonl'yi okur; satir satir JSON listesi dondurur."""
    try:
        satirlar = _gunluk_yol().read_text(encoding="utf-8").strip().splitlines()
    except OSError:
        return []
    sonuc: list[dict] = []
    for s in satirlar:
        s = s.strip()
        if not s:
            continue
        try:
            sonuc.append(json.loads(s))
        except json.JSONDecodeError:
            continue
    return sonuc


def boyut_yaz(bayt: int) -> str:
    """1024 tabanli, 1 ondalikli insan-okur boyut."""
    deger = float(bayt)
    for birim in ("B", "KB", "MB", "GB"):
        if deger < 1024 or birim == "GB":
            if birim == "B":
                return f"{int(deger)} B"
            return f"{deger:.1f} {birim}"
        deger /= 1024
    return f"{deger:.1f} GB"  # erisilemez


def _sutun(rapor: dict) -> str:
    adaylar = rapor.get("adaylar", [])
    basliklar = ["repo", "tur", "boyut", "yas(gun)", "durum"]
    satirlar = [
        [
            Path(a["repo"]).name,
            a.get("tur", "?"),
            boyut_yaz(a.get("boyut", 0)),
            str(int(a.get("yas_gun", 0))),
            a["atlandi"] or "silinebilir",
        ]
        for a in adaylar
    ]
    genislik = [
        max(len(basliklar[i]), *(len(s[i]) for s in satirlar)) if satirlar else len(basliklar[i])
        for i in range(len(basliklar))
    ]

    def birlestir(hucre: list[str]) -> str:
        return "  ".join(hucre[i].ljust(genislik[i]) for i in range(len(hucre))).rstrip()

    return "\n".join([birlestir(basliklar), *(birlestir(s) for s in satirlar)])


def tablo(rapor: dict) -> str:
    """Insan-okur metin tablosu + ozet satiri (v1 uyumlu)."""
    adaylar = rapor.get("adaylar", [])
    toplam = sum(a.get("boyut", 0) for a in adaylar)
    silinebilir = sum(a.get("boyut", 0) for a in adaylar if not a.get("atlandi"))
    atlandi = sum(1 for a in adaylar if a.get("atlandi"))
    return (
        f"{_sutun(rapor)}\n"
        f"ozet: {len(adaylar)} aday, {boyut_yaz(toplam)} toplam, "
        f"{boyut_yaz(silinebilir)} silinebilir, {atlandi} atlandi"
    )


def sil_ozeti(sonuc: dict, uygula: bool) -> str:
    """Silme ozeti: kuru calistirma uyarisi veya gercek sonuc."""
    satirlar: list[str] = []
    if not uygula:
        # Kuru calistirmada bosalan_bayt 0'dir; silinecek toplam gosterilir.
        kacacak = sum(a.get("boyut", 0) for a in sonuc["silinecek"])
        satirlar.append(
            f"KURU CALISTIRMA: {len(sonuc['silinecek'])} klasor silinecekti "
            f"({boyut_yaz(kacacak)}). Silmek icin --uygula ekleyin."
        )
        satirlar.extend(f"  - {a['yol']}  {boyut_yaz(a['boyut'])}  {a['tur']}" for a in sonuc["silinecek"])
    else:
        satirlar.append(
            f"{len(sonuc['silindi'])} silindi ({boyut_yaz(sonuc['bosalan_bayt'])} bosaldi), "
            f"{len(sonuc['silinemedi'])} silinemedi, {len(sonuc['atlanan'])} atlandi"
        )
        satirlar.extend(f"  ! {a['yol']}  {a['neden']}" for a in sonuc["silinemedi"])
    return "\n".join(satirlar)


def ozet_kartlari(rapor: dict) -> dict[str, Any]:
    """Web paneli icin ozet kartlari hesaplar.

    Donus: {
        "geri_kazanilabilir": int,      # guvenli aday toplam boyutu
        "dikkat_gerektiren": int,       # dikkat aday toplam boyutu
        "taranan_repo": int,            # benzersiz repo sayisi
        "aday_sayisi": int,             # toplam aday sayisi
        "simdiye_kadar_temizlenen": int # gunlukten toplam bosalan
    }
    """
    adaylar = rapor.get("adaylar", [])
    guvenli_boyut = sum(a.get("boyut", 0) for a in adaylar if not a.get("atlandi") and a.get("risk") == "guvenli")
    dikkat_boyut = sum(a.get("boyut", 0) for a in adaylar if not a.get("atlandi") and a.get("risk") == "dikkat")

    repo_set = set(a.get("repo") for a in adaylar if a.get("repo"))
    gunluk = gunluk_oku()
    temizlenen = sum(k.get("bosalan_bayt", 0) for k in gunluk if k.get("basarili"))

    return {
        "geri_kazanilabilir": guvenli_boyut,
        "dikkat_gerektiren": dikkat_boyut,
        "taranan_repo": len(repo_set),
        "aday_sayisi": len(adaylar),
        "simdiye_kadar_temizlenen": temizlenen,
    }


def dagilim_cubugu(rapor: dict) -> list[dict]:
    """Web paneli icin dagilim cubugu verisi (grup bazli yigilmis boyutlar).

    Donus: [{"grup": "js", "boyut": 12345, "risk": "guvenli", "sayi": 3}, ...]
    """
    adaylar = rapor.get("adaylar", [])
    onbellekler = rapor.get("onbellekler", [])

    from collections import defaultdict
    gruplar: dict[str, dict] = defaultdict(lambda: {"boyut": 0, "guvenli": 0, "dikkat": 0, "sayi": 0})

    for a in adaylar:
        if a.get("atlandi"):
            continue
        g = a.get("grup", "genel")
        r = a.get("risk", "guvenli")
        b = a.get("boyut", 0)
        gruplar[g]["boyut"] += b
        gruplar[g]["sayi"] += 1
        if r == "guvenli":
            gruplar[g]["guvenli"] += b
        else:
            gruplar[g]["dikkat"] += b

    # Onbellekler "onbellek" grubuna
    for o in onbellekler:
        if not o.get("var"):
            continue
        g = o.get("grup", "genel")
        b = o.get("boyut", 0)
        r = o.get("risk", "guvenli")
        gruplar[f"{g}-onbellek"]["boyut"] += b
        gruplar[f"{g}-onbellek"]["sayi"] += 1
        if r == "guvenli":
            gruplar[f"{g}-onbellek"]["guvenli"] += b
        else:
            gruplar[f"{g}-onbellek"]["dikkat"] += b

    sonuc = []
    for grup, veri in sorted(gruplar.items()):
        sonuc.append({
            "grup": grup,
            "boyut": veri["boyut"],
            "guvenli": veri["guvenli"],
            "dikkat": veri["dikkat"],
            "sayi": veri["sayi"],
        })
    return sonuc