"""Silme: yasina/ture gore adaylari siler; varsayilan KURU CALISTIRMA.

Guvenlik:
- `uygula=False` ise HICBIR dosya sistemi degisikligi yapilmaz.
- Silmeden once adayin `resolve()` yolu repo kokunun altinda mi dogrulanir.
- Yeni: id listesiyle silme (rapordan coz), onbellek temizleme, gunluk yazma.
- MEVCUT sil() IMCASI VE DAVRANISI KORUNUR.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import stat as stat_mod
import time
from pathlib import Path

from . import rapor
from .onbellek import onbellek_temizle
from .tara import tara


def _salt_okunur_sifirla(func, yol, _hata) -> None:
    """shutil.rmtree onerror shimi: yazma izni verip islemi bir kez daha dene."""
    os.chmod(yol, stat_mod.S_IWRITE | stat_mod.S_IREAD)
    func(yol)


def sil(
    repolar: list[Path],
    uygula: bool,
    yas: float = 7,
    turler: list[str] | None = None,
    simdi: float | None = None,
) -> dict:
    """Adaylari tazeden tarar ve (uygula ise) siler.

    Donus anahtarlari: silinecek / silindi / silinemedi / atlanan / bosalan_bayt.
    MEVCUT IMCAS VE DAVRANIS KORUNUR.
    """
    sonuc = {"silinecek": [], "silindi": [], "silinemedi": [], "atlanan": [], "bosalan_bayt": 0}

    for aday in tara(repolar, simdi):
        yol = Path(aday["yol"])
        if aday["atlandi"]:  # baglanti veya pyvenv-yok: aday degil
            sonuc["atlanan"].append({"yol": str(yol), "neden": aday["atlandi"]})
            continue
        if turler is not None and aday["tur"] not in turler:
            sonuc["atlanan"].append({"yol": str(yol), "neden": "tur-disi"})
            continue
        if yas > 0 and aday["yas_gun"] < yas:  # yas=0 -> yas filtresi kapali
            sonuc["atlanan"].append({"yol": str(yol), "neden": "yeni"})
            continue

        sonuc["silinecek"].append(aday)
        if not uygula:
            continue  # kuru calistirma: dosya sistemine dokunma

        repo = Path(aday["repo"])
        try:
            # Guvenlik: yol repo kokunun altinda mi?
            yol.resolve().relative_to(repo.resolve())
        except (ValueError, OSError):
            sonuc["silinemedi"].append({"yol": str(yol), "neden": "repo-disi"})
            continue
        try:
            if yol.is_symlink() or not yol.is_dir():
                os.rmdir(yol)  # savunma: baglanti asla buraya girmemeli
            else:
                shutil.rmtree(yol, onerror=_salt_okunur_sifirla)
        except (PermissionError, OSError) as exc:
            neden = f"kilitli: {' '.join(str(exc).split())}"
            sonuc["silinemedi"].append({"yol": str(yol), "neden": neden})
            continue
        sonuc["silindi"].append(aday)
        sonuc["bosalan_bayt"] += aday["boyut"]

        # Gunluk yaz
        rapor.gunluk_yaz({
            "zaman": datetime_utc_iso(),
            "yol": str(yol),
            "tur": aday["tur"],
            "boyut": aday["boyut"],
            "sonuc": "silindi",
        })

    return sonuc


def _aday_bul_id(rapor_veri: dict, id_: str) -> dict | None:
    """Rapordaki adaylar listesinden ID ile aday bulur."""
    for aday in rapor_veri.get("adaylar", []):
        if aday.get("id") == id_:
            return aday
    for ob in rapor_veri.get("onbellekler", []):
        if ob.get("id") == id_:
            return ob
    return None


def sil_idler(
    idler: list[str],
    onbellek_adlar: list[str] | None = None,
    *,
    uygula: bool = True,
    dikkat_dahil: bool = False,
    rapor_yol: Path | None = None,
) -> dict:
    """ID listesiyle silme (PLAN.md §4, §5).

    - Rapordan ID'leri cozer (adaylar + onbellekler)
    - Mevcut guvenlik denetimlerini TEKRAR yapar (repo altinda mi, baglanti mi, hâlâ var mi)
    - onbellek_adlar: --onbellek pip gibi isimlerle onbellek temizleme
    - dikkat_dahil: risk="dikkat" olan adaylari da sil (varsayilan hayir)
    - Gunluk.jsonl'ye yazar

    Donus: sil() ile ayni sema + onbellek_sonuclari
    """
    veri = rapor.yukle(rapor_yol)
    if not veri:
        return {
            "silinecek": [], "silindi": [], "silinemedi": [],
            "atlanan": [], "bosalan_bayt": 0, "onbellek_sonuclari": [],
        }

    sonuc = {
        "silinecek": [], "silindi": [], "silinemedi": [],
        "atlanan": [], "bosalan_bayt": 0, "onbellek_sonuclari": [],
    }

    # Adaylari ID ile coz ve sil
    for id_ in idler:
        aday = _aday_bul_id(veri, id_)
        if not aday:
            sonuc["atlanan"].append({"yol": id_, "neden": "raporda-yok"})
            continue

        # Onbellek mi?
        if "ad" in aday and "komut" in aday:  # onbellek kaydi
            onb_sonuc = onbellek_temizle(aday["ad"], uygula=uygula)
            sonuc["onbellek_sonuclari"].append(onb_sonuc)
            if onb_sonuc.get("basarili") and uygula:
                sonuc["bosalan_bayt"] += onb_sonuc.get("bosalan_bayt", 0)
                rapor.gunluk_yaz({
                    "zaman": datetime_utc_iso(),
                    "yol": onb_sonuc.get("yol", ""),
                    "tur": f"onbellek:{aday['ad']}",
                    "boyut": onb_sonuc.get("bosalan_bayt", 0),
                    "sonuc": "silindi",
                })
            continue

        # Normal repo adayi
        yol = Path(aday["yol"])
        repo = Path(aday["repo"])

        # Guvenlik denetimleri (tekrar!)
        if aday.get("atlandi"):
            sonuc["atlanan"].append({"yol": str(yol), "neden": aday["atlandi"]})
            continue
        if not dikkat_dahil and aday.get("risk") == "dikkat":
            sonuc["atlanan"].append({"yol": str(yol), "neden": "risk-dikkat"})
            continue
        # Hala var mi?
        if not yol.exists():
            sonuc["atlanan"].append({"yol": str(yol), "neden": "yok-oldu"})
            continue
        # Baglanti mi? (tara'da atlandi="baglanti" olmaliydi ama guvenlik icin tekrar)
        try:
            if yol.is_symlink():
                sonuc["atlanan"].append({"yol": str(yol), "neden": "baglanti"})
                continue
        except OSError:
            pass

        # Repo disi mi?
        try:
            yol.resolve().relative_to(repo.resolve())
        except (ValueError, OSError):
            sonuc["silinemedi"].append({"yol": str(yol), "neden": "repo-disi"})
            continue

        sonuc["silinecek"].append(aday)

        if not uygula:
            continue

        # Gercek silme
        try:
            if not yol.is_dir():
                os.rmdir(yol)
            else:
                shutil.rmtree(yol, onerror=_salt_okunur_sifirla)
        except (PermissionError, OSError) as exc:
            neden = f"kilitli: {' '.join(str(exc).split())}"
            sonuc["silinemedi"].append({"yol": str(yol), "neden": neden})
            continue

        sonuc["silindi"].append(aday)
        sonuc["bosalan_bayt"] += aday["boyut"]

        rapor.gunluk_yaz({
            "zaman": datetime_utc_iso(),
            "yol": str(yol),
            "tur": aday["tur"],
            "boyut": aday["boyut"],
            "sonuc": "silindi",
        })

    # Onbellek isimleriyle temizleme (--onbellek pip)
    if onbellek_adlar:
        for ad in onbellek_adlar:
            onb_sonuc = onbellek_temizle(ad, uygula=uygula)
            sonuc["onbellek_sonuclari"].append(onb_sonuc)
            if onb_sonuc.get("basarili") and uygula:
                sonuc["bosalan_bayt"] += onb_sonuc.get("bosalan_bayt", 0)
                rapor.gunluk_yaz({
                    "zaman": datetime_utc_iso(),
                    "yol": onb_sonuc.get("yol", ""),
                    "tur": f"onbellek:{ad}",
                    "boyut": onb_sonuc.get("bosalan_bayt", 0),
                    "sonuc": "silindi",
                })

    return sonuc


def datetime_utc_iso() -> str:
    """Simdiki zaman UTC ISO formatinda."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")