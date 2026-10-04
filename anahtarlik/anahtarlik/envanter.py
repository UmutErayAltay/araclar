"""Envanter: repolardaki anahtarlarin HARITASI (ad + parmak izi).

HAMLIK KURALI: bu modul ham degeri okur, `parmak.izi()` ile ozetler ve degeri
HEMEN birakir. Kayit, JSON, tablo ve hata mesajlarinda deger YOKTUR.

Envanter govdesi:
    {"surum": 1, "tarih": iso, "repolar": [
        {"repo": yol, "anahtarlar": [{"ad", "dosya", "izi", "uzunluk_sinifi"}]}]}

`notlar.json`: rota/iptal notlari ({ad, tarih, aciklama?}) -- `eski` bunlari okur.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from datetime import date, datetime, timezone
from pathlib import Path

from . import env, parmak

SURUM = 1
VARSAYILAN_AD = "envanter.json"
NOTLAR_AD = "notlar.json"

#: Bu dizinlerin ICINE girilmez (dev bagimliliklari, derleme ciktilari).
SKIP_DIRS = frozenset(
    {".git", "node_modules", ".venv", "venv", "vendor", "dist", "build", "__pycache__"}
)

#: Repo kokundan asagi en fazla bu kadar dizin seviyesi taranir.
DERINLIK = 4

#: Bu boyuttan buyuk env dosyalari atlanir (uretimde yazilan dev dosyalar).
AZAMI_DOSYA = 1024 * 1024  # 1 MB

#: Deger uzunlugu siniflari (ham deger yerine etiket saklanir).
SINIFLAR = ((64, "uzun"), (24, "orta"), (parmak.ASGARI_UZUNLUK, "kisa"))


class EnvanterHatasi(RuntimeError):
    """Envanter/notlar okunamadi veya yazilamadi (kullanim hatasi)."""


# --------------------------------------------------------------------------
# yol yardimcilari
# --------------------------------------------------------------------------


def dizin() -> Path:
    return parmak.dizin()


def _yol(ad: str = VARSAYILAN_AD) -> Path:
    return dizin() / ad


def _yaz(veri: dict, hedef: Path) -> Path:
    """JSON'u atomik yazar (mkstemp + os.replace: yarim dosya gorunmez)."""
    try:
        hedef.parent.mkdir(parents=True, exist_ok=True)
        fd, gecici_ad = tempfile.mkstemp(dir=hedef.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as akim:
                json.dump(veri, akim, ensure_ascii=False, indent=2)
            os.replace(gecici_ad, hedef)
        except BaseException:
            Path(gecici_ad).unlink(missing_ok=True)
            raise
    except OSError as exc:
        raise EnvanterHatasi(f"dosya yazilamadi: {hedef} ({exc.strerror or exc})") from None
    return hedef


def _oku_json(hedef: Path) -> dict | None:
    try:
        return json.loads(hedef.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def kaydet(envanter: dict) -> Path:
    """Envanteri `ANAHTARLIK_DIR/envanter.json`a yazar."""
    return _yaz(envanter, _yol())


def yukle() -> dict | None:
    """Son envanteri okur; yoksa/bozuksa None."""
    return _oku_json(_yol())


# --------------------------------------------------------------------------
# tarama
# --------------------------------------------------------------------------


def _uzunluk_sinifi(uzunluk: int, izi_deger: str | None) -> str:
    """Ham deger YOK: yalniz uzunlugu siniflanir (kisa deger izi almadigi icin 'kisa')."""
    if izi_deger is None:
        return "kisa"
    return next(etiket for esik, etiket in SINIFLAR if uzunluk >= esik)


#: Windows junction/symlink dizini `os.walk(followlinks=False)` ile IZLENMEZ
#: (ozelikle junction: `is_symlink()` False, `is_dir()` True). Repoda boyle bir
#: bag varsa tarama repo DIŞINA cikar. `st_file_attributes & 0x400` = REPARSE.
_REPARSE_NOKTASI = 0x400


def _baglanti_mi(yol: Path) -> bool:
    """`yol` bir sembolik bag mi? (Windows junction dahil).

    `Path.is_symlink()` junction'i YAKALAMAZ; os.walk de izlemez. Bu yuzden
    dosya niteliklerindeki REPARSE bayragina bakilir (junction + symlink).
    """
    try:
        if os.path.islink(yol):
            return True
        nitelik = getattr(os.lstat(yol), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(nitelik & _REPARSE_NOKTASI)


def _env_dosyalari(repo: Path) -> list[Path]:
    """Repo icindeki `.env*` dosyalari (baglanti izlenmez, derinlik sinirli)."""
    bulunan: list[Path] = []
    for mevcut, dizinler, dosyalar in os.walk(
        repo, topdown=True, followlinks=False, onerror=lambda _e: None
    ):
        yol = Path(mevcut)
        dizinler[:] = sorted(
            d for d in dizinler if d not in SKIP_DIRS and not _baglanti_mi(yol / d)
        )
        for ad in dosyalar:
            if env.env_dosyasi_mi(ad):
                bulunan.append(yol / ad)
        if len(yol.relative_to(repo).parts) >= DERINLIK:
            dizinler[:] = []  # derinlik siniri
    return sorted(bulunan)


def _oku_env(dosya: Path, repo: Path, atlanan: list[str]) -> list[dict]:
    """Dosyadaki anahtarlari iz + ad olarak cikarir; ham deger birakilir."""
    try:
        boyut = dosya.stat().st_size
    except OSError as exc:
        atlanan.append(f"{dosya}: okunamadi ({exc.strerror or exc})")
        return []
    if boyut > AZAMI_DOSYA:
        atlanan.append(f"{dosya}: 1 MB'den buyuk ({boyut} bayt), atlandi")
        return []

    goreli = _goreli(dosya, repo)
    kartlar: list[dict] = []
    for ad, deger in env.oku(dosya):
        # --- ham deger yasam alani: yalniz burada, iz uretilip birakiliyor ---
        uzunluk = len(deger)
        izi_deger = parmak.izi(deger)
        del deger
        # ------------------------------------------------------------------
        kartlar.append(
            {
                "ad": ad,
                "dosya": goreli,
                "izi": izi_deger,
                "uzunluk_sinifi": _uzunluk_sinifi(uzunluk, izi_deger),
            }
        )
    return kartlar


def _goreli(dosya: Path, repo: Path) -> str:
    """Repo'ya gore goreli yol (tabloya okunakli yazilsin)."""
    try:
        return dosya.relative_to(repo).as_posix()
    except ValueError:
        return dosya.as_posix()  # repo disi: goreli hesaplanamaz


def tara(repolar: list[Path]) -> dict:
    """Verilen repolari tarar; envanter govdesi doner (yazmaz; kaydet() yazar)."""
    atlanan: list[str] = []
    kayitlar: list[dict] = []
    for repo in repolar:
        anahtarlar: list[dict] = []
        for dosya in _env_dosyalari(Path(repo)):
            anahtarlar.extend(_oku_env(dosya, Path(repo), atlanan))
        if anahtarlar:
            kayitlar.append(
                {"repo": str(repo), "anahtarlar": sorted(anahtarlar, key=_sirala)}
            )
    return {
        "surum": SURUM,
        "tarih": datetime.fromtimestamp(time.time(), timezone.utc).isoformat(timespec="seconds"),
        "repolar": kayitlar,
        "atlanan": atlanan,
        "toplam": sum(len(r["anahtarlar"]) for r in kayitlar),
    }


def _sirala(kart: dict) -> tuple:
    return (kart["ad"], kart["dosya"], kart["izi"] or "")


# --------------------------------------------------------------------------
# ayni deger / notlar
# --------------------------------------------------------------------------


def ayni_deger(envanter: dict) -> list[dict]:
    """Ayni parmak izini paylasan, FARKLI repolardaki adlari dondurur.

    Ayni sir (API key) birden fazla repoda tekrar ediyor demektir: tek kazada
    hepsi birden sigar. Deger gorunmez; iz ve ad gorunur.
    """
    iz_kumesi: dict[str, list[dict]] = {}
    for repo in envanter.get("repolar", []):
        for kart in repo.get("anahtarlar", []):
            if kart.get("izi"):
                iz_kumesi.setdefault(kart["izi"], []).append(
                    {
                        "izi": kart["izi"],
                        "ad": kart.get("ad"),
                        "repo": repo.get("repo"),
                        "dosya": kart.get("dosya"),
                    }
                )
    return [
        {"izi": iz, "adlar": sorted({k["ad"] for k in kartlar}), "kullanim": kartlar}
        for iz, kartlar in sorted(iz_kumesi.items())
        if len({k["repo"] for k in kartlar}) > 1
    ]


def _gun_once(tarih_iso: str | None, gun: int, simdi: float) -> bool:
    """`tarih_iso` bugunden `gun` gun eski mi? (tarih yoksa da 'evet' sayilir)"""
    if not tarih_iso:
        return True
    try:
        gun_ = date.fromisoformat(tarih_iso)
    except (TypeError, ValueError):
        return True  # bozuk tarih: guvenli tarafta karar ver
    bugun = datetime.fromtimestamp(simdi).date()  # yerel: not tarihleri de yerel
    return (bugun - gun_).days > gun


def eski_olanlar(envanter: dict, notlar: dict | None = None, gun: int = 90, simdi: float | None = None) -> list[dict]:
    """Rotasyon notu olmayan ya da `gun` gunden eski notu gosterilen adlar.

    `notlar`: {"ad": {"tarih": iso, "aciklama": ...}} ya da None.
    """
    simdi = time.time() if simdi is None else simdi
    notlar = notlar if notlar is not None else notlari_yukle()
    bulunan: dict[str, dict] = {}
    for repo in envanter.get("repolar", []):
        for kart in repo.get("anahtarlar", []):
            ad = kart.get("ad")
            if ad:
                bulunan[ad] = {"ad": ad, "izi": kart.get("izi"), "repo": repo.get("repo")}
    sonuc: list[dict] = []
    for ad, kart in sorted(bulunan.items()):
        not_ = notlar.get(ad) or {}
        if _gun_once(not_.get("tarih"), gun, simdi):
            sonuc.append({**kart, "not": not_ or None})
    return sonuc


def not_ekle(ad: str, tarih_iso: str, aciklama: str | None = None) -> dict:
    """Rotasyon/iptal notunu `notlar.json`'a yazar (tarih ISO, `YYYY-MM-DD`).

    Bir ad icin son not KALIR (ustune yazar): tarih gecmise yazilirsa geri sayilir.
    """
    notlar = notlari_yukle() or {}
    notlar[ad] = {"tarih": tarih_iso, "aciklama": aciklama}
    _yaz({"surum": SURUM, "notlar": notlar}, _yol(NOTLAR_AD))
    return notlar[ad]


def notlari_yukle() -> dict:
    """`notlar.json`'i okur: ad -> {tarih, aciklama?}."""
    veri = _oku_json(_yol(NOTLAR_AD)) or {}
    notlar = veri.get("notlar", veri)
    return notlar if isinstance(notlar, dict) else {}


# --------------------------------------------------------------------------
# tablo
# --------------------------------------------------------------------------


def tablo(envanter: dict) -> str:
    """Terminal tablosu: YALNIZ ad, repo, dosya, parmak izi."""
    satirlar: list[list[str]] = []
    for repo in envanter.get("repolar", []):
        for kart in repo.get("anahtarlar", []):
            satirlar.append(
                [
                    str(kart.get("ad", "?")),
                    # repo ust kayitta durur; kartta varsa o kullanilir.
                    str(kart.get("repo") or repo.get("repo", "?")),
                    str(kart.get("dosya", "?")),
                    str(kart.get("izi") or "kisa"),
                ]
            )
    basliklar = ["ad", "repo", "dosya", "izi"]
    genislik = [
        max(len(basliklar[i]), *(len(s[i]) for s in satirlar)) if satirlar else len(basliklar[i])
        for i in range(len(basliklar))
    ]

    def birlestir(hucre: list[str]) -> str:
        return "  ".join(hucre[i].ljust(genislik[i]) for i in range(len(hucre))).rstrip()

    cikti = "\n".join(birlestir(h) for h in (basliklar, *satirlar))
    tekrar = ayni_deger(envanter)
    ek = [
        f"toplam {envanter.get('toplam', 0)} anahtar, {len(envanter.get('repolar', []))} repo",
        f"{len(tekrar)} ayni deger (iz esit ama repo farkli)",
    ]
    atlanan = envanter.get("atlanan") or []
    if atlanan:
        ek.append(f"{len(atlanan)} dosya atlandi")
    return "\n".join([cikti, *(f"- {k}" for k in ek)])