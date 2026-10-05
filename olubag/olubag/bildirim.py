"""Bildirim ayristirma: requirements*.txt, pyproject.toml, package.json.

Her bildirim `paket` + `satir` cifti dondurur. Satir numarasi TOML/JSON
ayristiricisindan gelmez (stdlib tomllib/json konum vermez); adin ham metinde
ilk goruldugu satir bulunur.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

from .eslesme import paket_adi_satiri

#: JS kaynak dosya uzantilari (import/require tarama yapilacak olanlar).
JS_UZANTILARI = frozenset({".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx"})


def _satir_bul(ham: str, ad: str) -> int:
    """Adin ham metinde ilk goruldugu 1 tabanli satir (yoksa 1).

    Buyuk/kucuk harf duyarsiz: bildirilen `PyYAML` metinde `PyYAML` yazar,
    biz `pyyaml` arariz.
    """
    kucuk = ham.lower()
    for no, satir in enumerate(kucuk.splitlines(), start=1):
        if ad in satir:
            return no
    return 1


def _kayit(dosya: Path, repo: Path, ad: str, ham: str | None = None) -> dict:
    return {
        "dosya": _gorece(dosya, repo),
        "satir": _satir_bul(ham, ad) if ham is not None else 1,
        "paket": ad,
    }


def _gorece(dosya: Path, repo: Path) -> str:
    """Repo kokune gore goreli yol (ayirici her zaman `/`)."""
    try:
        return dosya.resolve().relative_to(repo.resolve()).as_posix()
    except ValueError:
        return dosya.name


def _toml_adlar(veri: dict) -> list[str]:
    """[project].dependencies + optional-dependencies altindaki tum paket adlari."""
    proje = veri.get("project")
    if not isinstance(proje, dict):
        return []
    adlar = [
        paket_adi_satiri(s)
        for s in proje.get("dependencies") or []
        if isinstance(s, str)
    ]
    opsiyonel = proje.get("optional-dependencies") or {}
    if isinstance(opsiyonel, dict):
        for grup in opsiyonel.values():
            adlar.extend(
                paket_adi_satiri(s) for s in grup or [] if isinstance(s, str)
            )
    return [a for a in adlar if a]


def pyproject(dosya: Path, repo: Path) -> list[dict]:
    """pyproject.toml: [project].dependencies + optional-dependentials."""
    ham = dosya.read_text(encoding="utf-8", errors="replace")
    try:
        veri = tomllib.loads(ham)
    except (tomllib.TOMLDecodeError, UnicodeDecodeError):
        return []  # bozuk TOML: sessizce gec, rapor uydurma
    return [_kayit(dosya, repo, ad, ham) for ad in _toml_adlar(veri)]


def requirements(dosya: Path, repo: Path) -> list[dict]:
    """requirements*.txt: satir satir, yorumlar ve indirme satirlari haric."""
    ham = dosya.read_text(encoding="utf-8", errors="replace")
    kayitlar: list[dict] = []
    for no, satir in enumerate(ham.splitlines(), start=1):
        ad = paket_adi_satiri(satir)
        if ad:
            kayitlar.append({"dosya": _gorece(dosya, repo), "satir": no, "paket": ad})
    return kayitlar


def package_json(dosya: Path, repo: Path) -> list[dict]:
    """package.json: YALNIC `dependencies` (devDependencies HARIC)."""
    ham = dosya.read_text(encoding="utf-8", errors="replace")
    try:
        veri = json.loads(ham)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return []  # bozuk JSON: sessizce gec
    if not isinstance(veri, dict):
        return []
    bagimliliklar = veri.get("dependencies")
    if not isinstance(bagimliliklar, dict):
        return []
    return [_kayit(dosya, repo, ad, ham) for ad in bagimliliklar]


def bildirimleri(dosya: Path, repo: Path) -> list[dict]:
    """Dosya turune gore bildirimleri dondurur (bilinmeyen tur: bos liste)."""
    ad = dosya.name
    if ad == "pyproject.toml":
        return pyproject(dosya, repo)
    if ad == "package.json":
        return package_json(dosya, repo)
    if ad.startswith("requirements") and ad.endswith(".txt"):
        return requirements(dosya, repo)
    return []


def bildirim_dosyasi_mi(dosya: Path) -> bool:
    """Bu dosya bir bildirim dosyasi mi (bagimlilik beyan eder mi)?"""
    ad = dosya.name
    return (
        ad == "pyproject.toml"
        or ad == "package.json"
        or (ad.startswith("requirements") and ad.endswith(".txt"))
    )