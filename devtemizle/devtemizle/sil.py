"""Silme: yasina/ture gore adaylari siler; varsayilan KURU CALISTIRMA.

Guvenlik:
- `uygula=False` ise HICBIR dosya sistemi degisikligi yapilmaz.
- Silmeden once adayin `resolve()` yolu repo kokunun altinda mi dogrulanir.
- sil_idler raporu KANIT SAYMAZ: her repo adayi silinmeden once repo yeniden
  taranir; aday hala var, baglanti degil, kanitli ve yasi yeterli olmali.
- Onbellek/dikkat kararlari statik kural tablosundan verilir (rapor degil).
- MEVCUT sil() IMCASI VE DAVRANISI KORUNUR.
"""

from __future__ import annotations

import os
import shutil
import stat as stat_mod
import sys
from pathlib import Path

from . import rapor
from . import tara as tara_modulu
from .onbellek import onbellek_riski, onbellek_temizle
from .tara import tara
from .turler import risk_durumu, tur_ara


class RaporYok(RuntimeError):
    """sil_idler icin rapor yok ya da okunamiyor (once `devtemizle tara` gerekir)."""


def _salt_okunur_sifirla(func, yol, _hata) -> None:
    """shutil.rmtree onerror/onexc shimi: yazma izni verip islemi bir kez daha dene.

    - Baglanti (symlink) uzerinden chmod YAPILMAZ: hata yukseltilir.
    - POSIX: silme ogenin bulundugu DIZIN yazilabilir olmasini ister; dizin duzeltilir.
    - Windows: salt-okunur bayrak ogenin kendisindedir; o duzeltilir.
    """
    ust = os.path.dirname(os.path.abspath(yol))
    if os.path.islink(yol) or os.path.islink(ust):
        raise PermissionError(f"baglanti uzerinde izin degistirilmez: {yol}")
    if os.name == "nt":
        os.chmod(yol, stat_mod.S_IWRITE | stat_mod.S_IREAD)
    else:
        kip = os.stat(ust).st_mode
        os.chmod(ust, kip | stat_mod.S_IWUSR | stat_mod.S_IXUSR)
    func(yol)


def _agaci_sil(yol: Path) -> None:
    """rmtree; Python 3.12+ onexc, eski surumler onerror kullanir."""
    if sys.version_info >= (3, 12):
        shutil.rmtree(yol, onexc=_salt_okunur_sifirla)
    else:
        shutil.rmtree(yol, onerror=_salt_okunur_sifirla)


def _icinde(yol: str, kok: str) -> bool:
    """`yol` (gercek yol) `kok`un altinda mi?"""
    try:
        Path(yol).relative_to(kok)
        return True
    except ValueError:
        return False


def _tekil_sil(yol: Path, repo: Path) -> str | None:
    """Aday dizinini siler. Basarida None; basarisizlikta neden metni.

    Silmeden hemen once yeniden denetlenir: baglanti (junction dahil) degil ve
    gercek yol (realpath) = ust dizinin gercek yolu + ad, repo icinde.
    """
    if tara_modulu._baglanti(yol):
        return "baglanti"
    gercek = os.path.realpath(yol)
    beklenen = os.path.join(os.path.realpath(yol.parent), yol.name)
    if gercek != beklenen or not _icinde(gercek, os.path.realpath(repo)):
        return "repo-disi"
    try:
        if yol.is_dir():
            _agaci_sil(yol)
        else:
            os.rmdir(yol)  # dosyayi asla silmez: yalniz bos dizin
    except OSError as exc:
        return f"kilitli: {' '.join(str(exc).split())}"
    if os.path.lexists(yol):
        return "kilitli: silinemedi (kismen)"
    return None


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
        neden = _tekil_sil(yol, repo)
        if neden:
            sonuc["silinemedi"].append({"yol": str(yol), "neden": neden})
            rapor.gunluk_yaz({
                "zaman": datetime_utc_iso(), "yol": str(yol), "tur": aday["tur"],
                "boyut": 0, "sonuc": "basarisiz",
            })
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


def _gecerli_repo(repo: Path) -> bool:
    """Repo kok: gercek dizin ve .git (dizin ya da dosya) iceriyor."""
    return repo.is_dir() and os.path.lexists(repo / ".git")


def _repo_adayi_sil(
    aday: dict,
    *,
    dikkat_izni: bool,
    uygula: bool,
    yas: float,
    taze_tarama,
    sonuc: dict,
) -> str | None:
    """Tek repo adayi: rapora GUVENMEDEN yeniden denetlenir ve silinir.

    Silindiyse (uygula) sonucu tamamlayip aday kimligini; yoksa None dondurur.
    """
    yol = Path(aday.get("yol") or "")
    repo = Path(aday.get("repo") or "")
    tur_ad = aday.get("tur")

    def atla(neden: str) -> None:
        sonuc["atlanan"].append({"yol": str(yol), "neden": neden})

    # 1. Rapordaki atlama bilgisi
    if aday.get("atlandi"):
        atla(aday["atlandi"])
        return None
    # 2. Repo: gercek dizin ve .git
    if not _gecerli_repo(repo):
        atla("degisti")
        return None
    # 3. Adayin ust dizini repo icinde mi? (sahte rapor: repo disina cikis)
    if not _icinde(os.path.realpath(yol.parent), os.path.realpath(repo)):
        sonuc["silinemedi"].append({"yol": str(yol), "neden": "repo-disi"})
        return None
    # 4. Ad ve tur rapor ile tutarli ve bilinen tur mu?
    tur = tur_ara(tur_ad) if isinstance(tur_ad, str) else None
    if tur is None or yol.name != tur_ad:
        atla("gecersiz-rapor")
        return None
    # 5. Risk rapordan DEGIL, kural tablosundan (eksik/yanlis risk = dikkat)
    risk = risk_durumu(tur_ad, str(yol.parent), tur)
    if risk != "guvenli" and not dikkat_izni:
        atla("risk-dikkat")
        return None
    # 6. Hala var mi, baglanti mi?
    if not os.path.lexists(yol):
        atla("yok-oldu")
        return None
    if tara_modulu._baglanti(yol):
        atla("baglanti")
        return None
    # 7. Taze tarama: ayni yol, atlandi yok, yas yeterli
    kayit = next(
        (k for k in taze_tarama(repo)
         if os.path.normpath(k["yol"]) == os.path.normpath(str(yol)) and k["tur"] == tur_ad),
        None,
    )
    if kayit is None:
        atla("degisti")
        return None
    if kayit.get("atlandi"):
        atla(kayit["atlandi"])
        return None
    if yas > 0 and kayit["yas_gun"] < yas:
        atla("yeni")
        return None

    kimlikli = {**kayit, "id": aday.get("id")}
    if not uygula:
        sonuc["silinecek"].append(kimlikli)
        return None

    onceki = tara_modulu._boyut(yol)
    neden = _tekil_sil(yol, repo)
    sonra = tara_modulu._boyut(yol) if os.path.lexists(yol) else 0
    if neden:
        sonuc["silinemedi"].append({"yol": str(yol), "neden": neden})
        rapor.gunluk_yaz({"zaman": datetime_utc_iso(), "yol": str(yol), "tur": tur_ad,
                          "boyut": 0, "sonuc": "basarisiz"})
        return None

    bosalan = max(0, onceki - sonra)
    sonuc["silinecek"].append(kimlikli)
    sonuc["silindi"].append(kimlikli)
    sonuc["bosalan_bayt"] += bosalan
    rapor.gunluk_yaz({
        "zaman": datetime_utc_iso(),
        "yol": str(yol),
        "tur": tur_ad,
        "boyut": bosalan,
        "sonuc": "silindi",
    })
    return aday.get("id")


def _onbellek_sonucunu_yaz(sonuc: dict, onb_sonuc: dict, uygula: bool, etiket: str) -> None:
    """Onbellek sonucunu listeye ve (uygula ise) gunluge yazar."""
    sonuc["onbellek_sonuclari"].append(onb_sonuc)
    if not uygula:
        return
    kayit = {
        "zaman": datetime_utc_iso(),
        "yol": onb_sonuc.get("yol", ""),
        "tur": f"onbellek:{etiket}",
        "boyut": onb_sonuc.get("bosalan_bayt", 0),
    }
    if onb_sonuc.get("basarili"):
        sonuc["bosalan_bayt"] += onb_sonuc.get("bosalan_bayt", 0)
        rapor.gunluk_yaz({**kayit, "sonuc": "silindi"})
    else:
        rapor.gunluk_yaz({**kayit, "sonuc": "basarisiz"})


def _rapordan_cikar(rapor_yol: Path | None, kimlikler: list[str]) -> str | None:
    """Silinen kimlikleri rapor dosyasindan cikarir (yeniden baslatmada geri gelmesin).

    Basarisizsa uyari metni dondurur; silme zaten yapildigi icin hata firlatilmaz.
    """
    if not kimlikler:
        return None
    veri = rapor.yukle(rapor_yol)
    if veri is None:
        return None
    kume = set(kimlikler)
    veri["adaylar"] = [a for a in veri.get("adaylar", []) if a.get("id") not in kume]
    veri["onbellekler"] = [o for o in veri.get("onbellekler", []) if o.get("id") not in kume]
    try:
        rapor.kaydet(veri, rapor_yol)
    except OSError as exc:
        return f"rapor guncellenemedi: {exc}"
    return None


def sil_idler(
    idler: list[str],
    onbellek_adlar: list[str] | None = None,
    *,
    uygula: bool = True,
    dikkat_dahil: bool = False,
    dikkat_idler: list[str] | set[str] | None = None,
    yas: float = 7,
    rapor_yol: Path | None = None,
) -> dict:
    """ID listesiyle silme (PLAN.md §4, §5).

    - Rapordan ID'leri cozer (adaylar + onbellekler). Rapor yoksa RaporYok.
    - Repo adaylari silinmeden once repo yeniden taranir (rapor kanit sayilmaz).
    - Risk: repo icin turler tablosu, onbellek icin onbellek kural tablosu.
      "guvenli" disindaki her sey dikkat sayilir; dikkat_dahil ya da o kimlik
      dikkat_idler icinde ise silinir.
    - yas: taze tarama yasi bu esikten kucukse atlanir (0 = filtre kapali).
    - onbellek_adlar: --onbellek pip gibi isimlerle onbellek temizleme
    - Basarili silmeler rapor dosyasindan cikarilir; gunluk.jsonl'ye yazilir.

    Donus: sil() ile ayni sema + onbellek_sonuclari
    """
    veri = rapor.yukle(rapor_yol)
    if veri is None:
        raise RaporYok(
            "rapor yok; once `devtemizle tara` calistirin "
            f"(beklenen: {rapor._yol(rapor_yol)})"
        )

    sonuc = {
        "silinecek": [], "silindi": [], "silinemedi": [],
        "atlanan": [], "bosalan_bayt": 0, "onbellek_sonuclari": [],
    }
    dikkat_kumesi = set(dikkat_idler or [])
    silinen_idler: list[str] = []
    taze_kayitlar: dict[str, list[dict]] = {}

    def taze_tarama(repo: Path) -> list[dict]:
        anahtar = str(repo)
        if anahtar not in taze_kayitlar:
            taze_kayitlar[anahtar] = tara([repo])
        return taze_kayitlar[anahtar]

    # Adaylari ID ile coz ve sil
    for id_ in idler:
        aday = _aday_bul_id(veri, id_)
        if not aday:
            sonuc["atlanan"].append({"yol": id_, "neden": "raporda-yok"})
            continue
        dikkat_izni = dikkat_dahil or id_ in dikkat_kumesi

        # Onbellek mi?
        if "ad" in aday and "komut" in aday:
            ad = str(aday.get("ad", ""))
            if onbellek_riski(ad) != "guvenli" and not dikkat_izni:  # kapi, cache'den ONCE
                sonuc["atlanan"].append({"yol": str(aday.get("yol") or ad), "neden": "risk-dikkat"})
                continue
            onb_sonuc = onbellek_temizle(ad, uygula=uygula)
            _onbellek_sonucunu_yaz(sonuc, onb_sonuc, uygula, ad)
            if uygula and onb_sonuc.get("basarili"):
                silinen_idler.append(id_)
            continue

        # Normal repo adayi (rapor yalniz aday gosterir; denetim yeniden yapilir)
        silinen = _repo_adayi_sil(
            aday,
            dikkat_izni=dikkat_izni,
            uygula=uygula,
            yas=yas,
            taze_tarama=taze_tarama,
            sonuc=sonuc,
        )
        if silinen is not None:
            silinen_idler.append(silinen)

    # Onbellek isimleriyle temizleme (--onbellek pip)
    if onbellek_adlar:
        for ad in onbellek_adlar:
            onb_sonuc = onbellek_temizle(ad, uygula=uygula)
            _onbellek_sonucunu_yaz(sonuc, onb_sonuc, uygula, ad)

    if uygula:
        uyari = _rapordan_cikar(rapor_yol, silinen_idler)
        if uyari:
            sonuc["uyari"] = uyari

    return sonuc


def datetime_utc_iso() -> str:
    """Simdiki zaman UTC ISO formatinda."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
