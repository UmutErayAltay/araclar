"""Belge taramasi: `.env.example`, README, docker-compose icindeki ADLARI cikarir.

BAYAT KURALI: burada da DEGER okunmaz/basilmaz. Satirlar yalniz bir AD
 regex'i ile TANImlANIR; eslesen kisim disinda kalan metin bellekte de
raporda da tutulmaz.

- `.env.example` / `.env.sample` / `env.example` sablonlari: `AD=` satirlari.
- README(.md): metin icinde gecen `AD` kaliplari (tam kelime).
- `docker-compose*.yml`: `environment:` altindaki `AD: deger` / `AD=` girdileri
  ve `${AD}` degisken referanslari.
"""

from __future__ import annotations

import re
from pathlib import Path

from .tara import AZAMI_DOSYA, temiz_yol

#: Ornek/sablon ortam dosyalarinin ADLARI (karsilastirma tarafi).
ORNEK_ADLARI = (".env.example", ".env.sample", "env.example", ".env.ornek", ".env.template")

#: `.env.example` satiri: `export AD=deger` veya `AD=deger` (deger YOK sayilir).
_SATIR_AD = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")

#: docker-compose `environment:` girdisi: `AD: deger` ya da `- AD=deger`.
_YML_AD = re.compile(r"^\s*(?:-\s*)?(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*[:=]")

#: docker-compose'da `${AD}` / `$AD` degisken referansi (deger degil, AD).
_YML_REF = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")

#: README metninde geçen buyuk-harfli ortam adi (tam kelime).
_README_AD = re.compile(r"(?<![A-Za-z0-9_])([A-Z][A-Z0-9_]{2,})(?![A-Za-z0-9_])")


def _satirlar(dosya: Path) -> list[str]:
    """Dosya satirlarini dondurur; okunamaz/buyuk/ikili ise bos liste."""
    try:
        if dosya.stat().st_size > AZAMI_DOSYA:
            return []
        veri = dosya.read_bytes()
    except OSError:
        return []
    if b"\x00" in veri[:4096]:
        return []
    return veri.decode("utf-8", "surrogateescape").splitlines()


def _goreli(dosya: Path, repo: Path) -> str:
    try:
        return dosya.relative_to(repo).as_posix()
    except ValueError:
        return dosya.as_posix()


def ornek_dosyasi_mi(dosya: str) -> bool:
    """Bu dosya `.env.example` turunden bir sablon mu? (kucuk harf duyarsiz)."""
    ad = Path(dosya.replace("\\", "/")).name.lower()
    return any(ad == o.lower() for o in ORNEK_ADLARI) or ad.startswith(".env.sample")


def compose_dosyasi_mi(dosya: str) -> bool:
    """Bu dosya `docker-compose*.yml` mi? (kucuk harf duyarsiz)."""
    return Path(dosya.replace("\\", "/")).name.lower().startswith("docker-compose")


def readme_dosyasi_mi(dosya: str) -> bool:
    """Bu dosya bir README mi? (kucuk harf duyarsiz, uzantili olabilir)."""
    return Path(dosya.replace("\\", "/")).name.lower().startswith("readme")


def ornek_adlari(dosya: Path, repo: Path) -> list[str]:
    """`.env.example` icindeki tanimli ADLAR (degerler okunmaz)."""
    adlar: list[str] = []
    for satir in _satirlar(dosya):
        eslesme = _SATIR_AD.match(satir)
        if eslesme:
            adlar.append(eslesme.group(1))
    return sorted(set(adlar))


def compose_adlari(dosya: Path, repo: Path) -> list[str]:
    """docker-compose icindeki ADLAR: `environment:` girdileri + `${AD}` referansi.

    `environment:` blogu girintiyle kapanir: `environment:` anahtarinin girintisine
    donen bir satir blogu bitirmis demektir.
    """
    adlar: set[str] = set()
    ortam_girintisi: int | None = None
    for satir in _satirlar(dosya):
        kirp = satir.strip()
        if not kirp or kirp.startswith("#"):
            continue
        girinti = len(satir) - len(satir.lstrip())
        if ortam_girintisi is not None and girinti <= ortam_girintisi:
            ortam_girintisi = None  # blok kapandi
        if kirp.rstrip(":") == "environment":
            ortam_girintisi = girinti
            continue
        if ortam_girintisi is not None:
            eslesme = _YML_AD.match(satir)
            if eslesme and eslesme.group(1).upper() == eslesme.group(1):
                adlar.add(eslesme.group(1))
        for referans in _YML_REF.finditer(satir):
            adlar.add(referans.group(1))
    return sorted(adlar)


def readme_adlari(dosya: Path, repo: Path) -> list[str]:
    """README icinde gecen buyuk-harfli ortam adlari (tam kelime)."""
    adlar: set[str] = set()
    for satir in _satirlar(dosya):
        if satir.lstrip().startswith("```"):  # kod blogu degil
            continue
        for eslesme in _README_AD.finditer(satir):
            adlar.add(eslesme.group(1))
    return sorted(adlar)


def belgeleri_tara(repo: Path, atlanan: list[str]) -> dict:
    """Bir repodaki belge tarafi AD kümelerini dondurur (deger yok).

    Donus: `{"ornek": [...], "readme": [...], "compose": [...], "dosyalar": {...}}`
    """
    repo = Path(repo)
    ornekler: set[str] = set()
    readmeler: set[str] = set()
    compose: set[str] = set()
    dosyalar: dict[str, list[str]] = {}

    try:
        adaylar = sorted(p for p in repo.rglob("*") if p.is_file() and not p.is_symlink())
    except OSError as exc:
        atlanan.append(f"repo okunamadi: {exc.strerror or exc}")
        return {"ornek": [], "readme": [], "compose": [], "dosyalar": dosyalar}

    for dosya in adaylar:
        goreli = temiz_yol(_goreli(dosya, repo))
        if ornek_dosyasi_mi(goreli):
            adlar = ornek_adlari(dosya, repo)
            ornekler.update(adlar)
            dosyalar.setdefault("ornek", []).append(goreli)
        elif compose_dosyasi_mi(goreli):
            adlar = compose_adlari(dosya, repo)
            compose.update(adlar)
            dosyalar.setdefault("compose", []).append(goreli)
        elif readme_dosyasi_mi(goreli):
            adlar = readme_adlari(dosya, repo)
            readmeler.update(adlar)
            dosyalar.setdefault("readme", []).append(goreli)

    return {
        "ornek": sorted(ornekler),
        "readme": sorted(readmeler),
        "compose": sorted(compose),
        "dosyalar": {k: sorted(v) for k, v in dosyalar.items()},
    }
