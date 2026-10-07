"""Maskeleme: bulunan degeri `***MASKELENDI:<tur>***` ile degistirir.

Varsayilan KURU CALISTIRMA: `uygula=False` ise dosya sistemine HICBIR dokunus
olmaz, yalniz "maskelenirdi" listesi doner.

Guvenlik ve butunluk:
- **Yeniden tarar.** Rapor tasinabilir metin olarak deger TASIYAMAZ; bu yuzden
  maskeleme dosyayi bastan okuyup span'lari kendisi turetir. Rapor ile dosya
  arasinda deger dolasik bir kanal acilmaz.
- **Satir sonu korunur.** Satirlar `keepends` ile bolunur, sonu HARFI HARFINE
  geri yazilir: CRLF dosya CRLF kalir, son satirin satir sonu yoksa yine yoktur.
- **Izin korunur.** Yazma `mkstemp` ile yapildigi icin (0600) mod once eski
  dosyadan alinip gecici dosyaya uygulanir; `os.replace` sonrasi izin degismez.
- **Atomik yazma.** Gecici dosya + `os.replace`: yarim maskelenmis dosya gorunmez.
- **Idempotent.** Maske `***MASKELENDI:<tur>***` bir sir DEGILDIR ve desenlere
  eslesmez; ikinci calistirma 0 bulgu doner ve dosyaya dokunmaz.
- `.git` hicbir zaman yazilmaz (taramada zaten hic girilmez).
"""

from __future__ import annotations

import os
import stat as stat_mod
import tempfile
from pathlib import Path

from .tara import AZAMI_DOSYA, _govde_satir, _okunabilir_satirlar, eslesmeler, tara

#: Degerin yerine yazilan yer tutucu. Icerigi turden ibaret (sir degil).
def yertutucu(tur: str) -> str:
    return f"***MASKELENDI:{tur}***"


def _satiri_maskele(satir: str) -> tuple[str, list[tuple[int, int, str, str]]]:
    """Tek satiri maskeler; (yeni_satir, bulgular) doner.

    Satir sonu ayrilir ve AYNI metin olarak geri eklenir: `keepends` bolmesi
    sayesinde ayrilan son `\r\n`/`\n` degistirilmez.
    """
    govde, satir_sonu = _govde_satir(satir)
    bulgular = eslesmeler(govde)
    if not bulgular:
        return satir, []
    # Sondan basa dogru yaz: span konumlari kaymaz.
    yeni = govde
    for bas, bitis, tur, _ad in reversed(bulgular):
        yeni = yeni[:bas] + yertutucu(tur) + yeni[bitis:]
    return yeni + satir_sonu, bulgular


def _yaz_atomik(dosya: Path, icerik: bytes) -> None:
    """Dosyayi ATOMIK olarak yeniden yazar; izinler ve sahiplik korunur.

    Ayni dizinde gecici dosya kullanilir: `os.replace` yalnizca ayni dosya
    sisteminde atomiktir (yoksa yarim dosya gorunur).
    """
    eski = dosya.stat()
    fd, gecici_ad = tempfile.mkstemp(dir=dosya.parent, prefix=f".{dosya.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as akim:
            akim.write(icerik)
        # mkstemp 0600 verir: eski izinleri (ve varsa setuid/setgid) geri koy.
        os.chmod(gecici_ad, stat_mod.S_IMODE(eski.st_mode))
        os.replace(gecici_ad, dosya)
    except BaseException:
        # Yarim dosya kalmasin: hedefe hic dokunulmamis olur.
        Path(gecici_ad).unlink(missing_ok=True)
        raise


def dosya_maskele(repo: Path, dosya: Path, atlanan: list[str]) -> list[dict]:
    """Tek dosyayi maskeler; degistirilen bulgulari dondurur (deger YOK).

    Dosyada bulgu yoksa **hic yazmaz** (dokunulmamis dosya bayt bayt kalir).
    """
    try:
        boyut = dosya.stat().st_size
    except OSError as exc:
        atlanan.append(f"{dosya}: okunamadi ({exc.strerror or exc})")
        return []
    if boyut > AZAMI_DOSYA:
        atlanan.append(f"{dosya}: 1 MB'den buyuk ({boyut} bayt), atlandi")
        return []
    try:
        icerik = dosya.read_bytes()
    except OSError as exc:
        atlanan.append(f"{dosya}: okunamadi ({exc.strerror or exc})")
        return []
    satirlar = _okunabilir_satirlar(icerik)
    if satirlar is None:
        return []  # ikili: sessizce gec

    goreli = _goreli(dosya, repo)
    degisen: list[dict] = []
    parcalar: list[bytes] = []
    degisti = False
    for numara, satir in enumerate(satirlar, start=1):
        yeni, bulgular = _satiri_maskele(satir)
        if bulgular:
            degisti = True
            degisen.extend(
                {
                    "repo": str(repo),
                    "dosya": goreli,
                    "satir": numara,
                    "tur": tur,
                    "ad": ad,
                }
                for _bas, _bitis, tur, ad in bulgular
            )
        parcalar.append(yeni.encode("utf-8"))

    if not degisti:
        return []  # HICBIR yazma: bulgusuz dosya aynen durur
    _yaz_atomik(dosya, b"".join(parcalar))
    return degisen


def _goreli(dosya: Path, repo: Path) -> str:
    try:
        return dosya.relative_to(repo).as_posix()
    except ValueError:
        return dosya.as_posix()


def uygula(repolar: list[Path], yaz: bool) -> dict:
    """Repolari tarar ve (`yaz` ise) bulgulari maskeler.

    `yaz=False` (varsayilan KURU CALISTIRMA) ise dosya sistemine dokunulmaz.
    Donus: {"bulgar": [...], "maskelendi": [...], "dosya": N}
    """
    rapor = tara(repolar)  # tuz yonlendirmesi `tara.tara` icinde yapilir
    bulgular = rapor["bulgar"]
    if not yaz:
        return {"bulgar": bulgular, "maskelendi": [], "dosya": rapor["dosya"]}

    # Dosya bazinda TEK KEZ yaz: ayni dosya N bulgu icin N kez yazilirsa
    # ilk yazimdan sonraki turler zaten bulgu bulamaz (maske bir sir degildir).
    atlanan: list[str] = []
    maskelendi: list[dict] = []
    gorulen: set[tuple[str, str]] = set()
    for bulgu in bulgular:
        repo, ad = bulgu["repo"], bulgu["dosya"]
        if (repo, ad) in gorulen:
            continue
        gorulen.add((repo, ad))
        maskelendi.extend(dosya_maskele(Path(repo), Path(repo) / ad, atlanan))
    return {"bulgar": bulgular, "maskelendi": maskelendi, "dosya": rapor["dosya"]}


def rotasyon(bulgar: list[dict]) -> list[dict]:
    """Dondurulmesi gereken anahtarlar: ayni sira tek satira iner.

    Ayni deger = ayni parmak izi. Iki dosyada `KEY` ve `K2` etiketleriyle
    gecen TEK bir API key, rotasyon listesinde TEK satir olur; etiketler farkli
    olsa bile gruplama IZE GORE yapilir. `adlar` alani o sirin gectigi tum
    etiketleri toplar. Deger YOK: ad + tur + izi.

    `ad` TEK etiketli kucuk harfli alan (bulgu kaydiyla AYNI ad, bkz. `tara`:
    `ad` etiket, `adlar` etiket listesi): kardes aracin `envanter`/`ayni_deger`
    sozlesmesi de tek etiketi `ad` ile tutar. Birden cok etiket varsa `ad`
    alfabetik ilk etikettir; `adlar` daima butun etiketleri tasir.
    """
    kume: dict[str, dict] = {}
    for bulgu in bulgar:
        izi = bulgu["izi"]
        kayit = kume.setdefault(
            izi, {"ad": None, "adlar": [], "tur": bulgu["tur"], "izi": izi, "nerede": []}
        )
        if bulgu["ad"] not in kayit["adlar"]:
            kayit["adlar"].append(bulgu["ad"])
        yer = f"{bulgu['repo']}/{bulgu['dosya']}:{bulgu['satir']}"
        if yer not in kayit["nerede"]:
            kayit["nerede"].append(yer)
    kayitlar = [kume[k] for k in sorted(kume)]
    for kayit in kayitlar:
        kayit["ad"] = sorted(kayit["adlar"])[0]  # cok etiketli tek sir: ilki temsilci
    return kayitlar