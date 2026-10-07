"""Kod taramasi: ortam degiskeni KULLANIMLARINI (yalniz AD) cikarir.

BAYAT KURALI: bir ortam degiskeninin DEGERI hicbir yere girmez. Bu modul
kaynak satirlarini gorur ama yalnizca degiskenin ADINI ve satir numarasini
ureter; deger hicbir sozluke girmez.

Kurallar:
- Yalniz kaynak dosyalari okunur (`.py`, `.js`, `.ts`, `.tsx`, `.jsx`,
  `.mjs`, `.cjs`, `.go`). `.env*` ve README karsilastirma tarafinda
  `belge.py` icin ayridir.
- Atlanan dizinler: `node_modules`, `.git`, `.venv`, `venv`, `__pycache__`,
  `dist`, `build`, `.pytest_cache`.
- 1 MB'den buyuk ve ikili dosyalar okunmaz.
- Git'in IZLEDIGI `.env` dosyalari (`env_dosyasi_mi`) kaynak sayilmaz:
  icleri degerdir, bu modul onlari hic taranmaz.
"""

from __future__ import annotations

import bisect
import os
import re
from pathlib import Path, PurePosixPath

#: Bu dizinlerin ICINE girilmez (dev bagimliliklari, derleme ciktilari).
SKIP_DIRS = frozenset(
    {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".pytest_cache"}
)

#: Bu boyuttan buyuk kaynak dosyalari okunmaz.
AZAMI_DOSYA = 1024 * 1024  # 1 MB

#: Kaynak olarak taranan dosya son ekleri.
KAYNAK_SONEKLERI = frozenset({".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".go"})

#: Terminale yazilacak metinden cikarilan KONTROL karakterLERI: ANSI kacis,
#: bell, satir sonu gibi. Bunlar dosya adi olsa bile ekranda komut/cikti
#: taklit edebilir (ORN: `x\x1b[2J` ekrani siler).
_KONTROL = re.compile(r"[\x00-\x1f\x7f]")

#: Git'in IZLEDIGI `.env` dosyasi adi (`.env.example` vb. DEGILDIR).
_ENV_ADI = re.compile(r"^\.env(\..+)?$", re.IGNORECASE)
#: Ornek/sablon son ekleri: git'in izlemedigi `.env` varyantlari.
ENV_ORNEK_SONEKLERI = (".example", ".sample", ".template", ".dist", ".defaults", ".ornek")


def env_dosyasi_mi(dosya: str) -> bool:
    """Git'in IZLEDIGI `.env` dosyasi mi? (`.env.example` vb. HAYIR).

    `env_izleniyor` bulgusu bu ayrimla calisir: sablon izlenmesi normaldir,
    `.env.production` izlenmesi sizintidir.
    """
    ad = PurePosixPath(dosya.replace("\\", "/")).name
    if not _ENV_ADI.match(ad):
        return False
    kucuk = ad.lower()
    return not any(kucuk.endswith(ek) for ek in ENV_ORNEK_SONEKLERI)


# --- Python: os.environ["X"], os.environ.get("X", ...), os.getenv("X", ...) ---
_PY = [
    re.compile(r"os\s*\.\s*environ\s*\[\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]\s*\]"),
    re.compile(r"os\s*\.\s*environ\s*\.\s*get\s*\(\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]"),
    re.compile(r"os\s*\.\s*getenv\s*\(\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]"),
]

# --- JS/TS: process.env["X"], process.env.X ---
_JS = [
    re.compile(r"process\s*\.\s*env\s*\[\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]\s*\]"),
    re.compile(r"process\s*\.\s*env\s*\.\s*([A-Za-z_][A-Za-z0-9_]*)"),
]

# --- Go: os.Getenv("X"), os.LookupEnv("X") ---
_GO = [
    re.compile(r"os\s*\.\s*Getenv\s*\(\s*\"([A-Za-z_][A-Za-z0-9_]*)\""),
    re.compile(r"os\s*\.\s*LookupEnv\s*\(\s*\"([A-Za-z_][A-Za-z0-9_]*)\""),
]

_DESENLER: dict[str, list[re.Pattern]] = {".py": _PY, ".go": _GO}
for _sonek in (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"):
    _DESENLER[_sonek] = _JS

#: Satir sonu konumlari (bulgunun BASLANGIC satirini bulmak icin onceden hesaplanir).
_SATIR_BASLANGIC = re.compile(r"\n")


def temiz_yol(metin: str) -> str:
    """Dosya yolunu terminale guvenli yazmak icin: kontrol karakterleri `?`."""
    return _KONTROL.sub("?", metin)


def kaynak_mi(dosya: str) -> bool:
    """Bu dosya kaynak kod mu? (uzanti taranir)"""
    return PurePosixPath(dosya.replace("\\", "/")).suffix.lower() in KAYNAK_SONEKLERI


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
    return bool(nitelik & 0x400)  # FILE_ATTRIBUTE_REPARSE_POINT


def _goreli(dosya: Path, repo: Path) -> str:
    """Repo'ya gore goreli yol (tabloya okunakli yazilsin)."""
    try:
        return dosya.relative_to(repo).as_posix()
    except ValueError:
        return dosya.as_posix()  # repo disi: goreli hesaplanamaz


def _metin_oku(dosya: Path, repo: Path, atlanan: list[str]) -> str | None:
    """Dosya metnini okur; okunamaz/buyuk/ikili ise None (neden `atlanan`a)."""
    goreli = _goreli(dosya, repo)
    try:
        if dosya.stat().st_size > AZAMI_DOSYA:
            atlanan.append(f"{goreli}: 1 MB'den buyuk, atlandi")
            return None
        veri = dosya.read_bytes()
    except OSError as exc:
        atlanan.append(f"{goreli}: okunamadi ({exc.strerror or exc})")
        return None
    if b"\x00" in veri[:4096]:
        return None  # ikili dosya: metin degildir
    # surrogateescape: bozuk bayt kod tablosunu patlatmaz.
    return veri.decode("utf-8", "surrogateescape")


def kaynak_dosyalari(repo: Path) -> list[Path]:
    """Repo icindeki taranabilir kaynak dosyalar (baglanti izlenmez)."""
    bulunan: list[Path] = []
    for mevcut, dizinler, dosyalar in os.walk(
        repo, topdown=True, followlinks=False, onerror=lambda _e: None
    ):
        kok = Path(mevcut)
        dizinler[:] = sorted(d for d in dizinler if d not in SKIP_DIRS and not _baglanti_mi(kok / d))
        for ad in dosyalar:
            if env_dosyasi_mi(ad):
                continue  # `.env` DEGERDUR: bu modul icin hic taranmaz
            if kaynak_mi(ad):
                bulunan.append(kok / ad)
    return sorted(bulunan)


def _kod_satiri(satir: str) -> bool:
    """Bu satir gercek KOD mu? (yorum ve dokuman satirlari atlanir).

    Modulun kendi dokumaninda bir ortam okuma KALIBI yazan yorum satiri bir
    KULLANIM degildir; tarandiginda `belgelenmemis` gibi yanlis pozitif uretirdi.
    """
    kirp = satir.lstrip()
    return not (kirp.startswith(("#", "//", "/*", "*", '"""', "'''")))


def dosya_tara(dosya: Path, repo: Path, atlanan: list[str]) -> list[dict]:
    """Tek kaynak dosyasindaki ortam degiskeni kullanimlarini cikarir.

    Her bulgu `{"ad", "dosya", "satir"}` sozlugudur. DEGER YOKTUR.

    Tarama satir satir DEGIL, dosyanin TAMAMI uzerinde yapilir: `os.environ.get(`
    cagrisi cok satirli yazildiginda (bicimlendirici/ satir sonu) degisken adi
    bir sonraki satirdadir. Satir satir tarama bunu gormez ve kullanilan bir
    degiskeni `kullanilmayan` sanirdi. Satir no, eslesmenin BASLANGIC konumundan
    hesaplanir.
    """
    metin = _metin_oku(dosya, repo, atlanan)
    if metin is None:
        return []
    desenler = _DESENLER.get(dosya.suffix.lower(), _JS)
    goreli = temiz_yol(_goreli(dosya, repo))
    satir_baslangic = [0]
    for konum in _SATIR_BASLANGIC.finditer(metin):
        satir_baslangic.append(konum.end())

    def satir_no(konum: int) -> int:
        return bisect.bisect_right(satir_baslangic, konum)

    bulgular: list[dict] = []
    for desen in desenler:
        for eslesme in desen.finditer(metin):
            ad = eslesme.group(1)
            no = satir_no(eslesme.start())
            if not ad or not _kod_satiri(metin.splitlines()[no - 1]):
                continue
            bulgular.append({"ad": ad, "dosya": goreli, "satir": no})
    return sorted(bulgular, key=lambda b: (b["satir"], b["ad"]))


def repo_tara(repo: Path, atlanan: list[str]) -> list[dict]:
    """Bir repodaki tum ortam degiskeni kullanimlarini dondurur (deger yok)."""
    repo = Path(repo)
    bulgular: list[dict] = []
    for dosya in kaynak_dosyalari(repo):
        bulgular.extend(dosya_tara(dosya, repo, atlanan))
    return bulgular
