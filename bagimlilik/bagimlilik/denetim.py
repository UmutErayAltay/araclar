"""Denetim katmani: pip-audit ve npm audit ciktilarini tek modele indirger.

Guvenlik (baglayici): repolara HICBIR SEY yazilmaz. requirements dosyasi
`-r` ile yerinde OKUNUR; pyproject bagimliliklari gecici dizindeki gecici bir
requirements dosyasina; npm icin package.json + package-lock.json gecici
dizine KOPYALANIR ve orada calisir.

Cikis kodu semantigi: her iki arac da ACIK bulunca 1 doner -> bu HATA DEGIL.
Karar stdout JSON'unun ayristirilabilmesinden cikar, cikis kodundan degil.
"denetlenemedi" ASLA "temiz" sayilmaz.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .kesif import SKIP_DIRS

#: npm/pip siddet etiketleri -> rapordaki Turkce kisa adlar.
SIDDET_ESLEME = {
    "critical": "kritik",
    "high": "yuksek",
    "medium": "orta",
    "moderate": "orta",
    "low": "dusuk",
    "info": "dusuk",
}

#: v1'de desteklenmeyen ekosistem isaretleri (raporda not olarak gosterilir).
DESTEKLENMEYEN = ("*.csproj", "build.gradle*", "go.mod", "Cargo.toml", "pom.xml")

AYRINTI_EN_FAZLA = 300

#: Denetime enjekte edilebilir komut calistirici: (argv, cwd, zaman_asimi).
Calistir = Callable[[list[str], Path | None, int], "tuple[int, str, str]"]


@dataclass
class Acik:
    """Tek bir acik bulgusu (aciklar listesi TUM aciklari icerir, ozete indirgenmez)."""

    paket: str
    surum: str
    id: str
    duzeltme: str | None
    siddet: str


@dataclass
class Denetim:
    """Tek bir manifest/ekosistem denetimi."""

    ekosistem: str  # "pip" | "npm"
    kaynak: str  # manifest dosya adi, repo kokune gore
    durum: str  # "temiz" | "acik" | "denetlenemedi"
    neden: str | None = None  # arac-yok | zaman-asimi | kilit-yok | cikti-bozuk | hata
    sayilar: dict[str, int] = field(default_factory=dict)
    toplam: int = 0
    aciklar: list[Acik] = field(default_factory=list)
    ayrinti: str | None = None


@dataclass
class RepoSonuc:
    yol: str
    ad: str
    denetimler: list[Denetim] = field(default_factory=list)
    desteklenmeyen: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------
# Ayristirma
# --------------------------------------------------------------------------


def _bos_sayilar() -> dict[str, int]:
    return {"kritik": 0, "yuksek": 0, "orta": 0, "dusuk": 0, "bilinmiyor": 0}


def _kimlik(vuln: dict) -> str:
    """pip-audit kimligi: aliases icinde CVE varsa onu tercih et."""
    for ad in vuln.get("aliases") or []:
        if str(ad).startswith("CVE-"):
            return str(ad)
    return str(vuln.get("id") or "")


def _duzeltme(vuln: dict) -> str | None:
    surumler = vuln.get("fix_versions") or []
    return ",".join(str(s) for s in surumler) or None


def parse_pip_audit(metin: str) -> tuple[dict[str, int], list[Acik]]:
    """pip-audit JSON -> (sayilar, aciklar). pip-audit SIDDET VERMEZ.

    Ayni (paket, id) birden fazla kez gecebilir; TEKILlestirilir.
    """
    veri = json.loads(metin)
    sayilar = _bos_sayilar()
    aciklar: list[Acik] = []
    gorulen: set[tuple[str, str]] = set()
    for bagimlilik in veri.get("dependencies") or []:
        for vuln in bagimlilik.get("vulns") or []:
            ad = str(bagimlilik.get("name") or "")
            kimlik = _kimlik(vuln)
            if (ad, kimlik) in gorulen:
                continue
            gorulen.add((ad, kimlik))
            aciklar.append(
                Acik(
                    paket=ad,
                    surum=str(bagimlilik.get("version") or ""),
                    id=kimlik,
                    duzeltme=_duzeltme(vuln),
                    siddet="bilinmiyor",
                )
            )
            sayilar["bilinmiyor"] += 1
    return sayilar, aciklar


def parse_npm_audit(metin: str) -> tuple[dict[str, int], list[Acik]]:
    """npm audit JSON -> (sayilar, aciklar).

    Sayilar `metadata.vulnerabilities` sayimlarindandir; aciklar yalnizca
    `via` listesi DICT olan (yani gercek bildirimi olan) girislerdir. Bu
    yuzden `toplam` aciklar listesinden buyuk olabilir; normaldir.
    """
    veri = json.loads(metin)
    sayilar = _bos_sayilar()
    sayimlar = (veri.get("metadata") or {}).get("vulnerabilities") or {}
    sayilar["dusuk"] = int(sayimlar.get("low") or 0) + int(sayimlar.get("info") or 0)
    sayilar["orta"] = int(sayimlar.get("moderate") or 0)
    sayilar["yuksek"] = int(sayimlar.get("high") or 0)
    sayilar["kritik"] = int(sayimlar.get("critical") or 0)

    aciklar: list[Acik] = []
    for ad, girdi in (veri.get("vulnerabilities") or {}).items():
        duzeltme = girdi.get("fixAvailable")
        for via in girdi.get("via") or []:
            if not isinstance(via, dict):
                continue  # string ise zincir: bildirim kaynagi degil
            kimlik = str(via.get("url") or via.get("source") or "").rstrip("/").rsplit("/", 1)[-1]
            if isinstance(duzeltme, dict):
                duzeltme_metni = f"{duzeltme.get('name')}@{duzeltme.get('version')}"
            elif duzeltme is True:
                duzeltme_metni = "mevcut"
            else:
                duzeltme_metni = None
            siddet = SIDDET_ESLEME.get(str(via.get("severity") or "").lower(), "bilinmiyor")
            aciklar.append(
                Acik(
                    paket=str(via.get("name") or ad),
                    surum="",  # npm ciktisinda surum yok
                    id=kimlik,
                    duzeltme=duzeltme_metni,
                    siddet=siddet,
                )
            )
    return sayilar, aciklar


# --------------------------------------------------------------------------
# Manifest kesfi
# --------------------------------------------------------------------------


def _alt_dizinler(repo: Path) -> list[Path]:
    try:
        girisler = sorted(repo.iterdir())
    except OSError:
        return []
    return [g for g in girisler if g.is_dir() and g.name not in SKIP_DIRS]


def _kokler(repo: Path) -> list[Path]:
    """Repo koku + 1 seviye altindaki dizinler (SKIP_DIRS haric)."""
    return [repo, *_alt_dizinler(repo)]


def _iliskili(repo: Path, dosya: Path) -> str:
    """Manifest dosya adini repo kokune gore yaz (alt klasorde: alt/requirements.txt)."""
    try:
        return dosya.relative_to(repo).as_posix()
    except ValueError:
        return dosya.name


def _requirements_dosyalari(repo: Path) -> list[Path]:
    bulunan: list[Path] = []
    for kok in _kokler(repo):
        bulunan.extend(sorted(kok.glob("requirements*.txt")))
    return bulunan


def _pyproject_bagliliklari(dosya: Path) -> list[str] | None:
    """[project].dependencies varsa satirlari dondurur, yoksa/bozuksa None."""
    try:
        veri = tomllib.loads(dosya.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return None
    bagimliliklar = (veri.get("project") or {}).get("dependencies") or []
    return [str(b) for b in bagimliliklar] or None


def _pyproject_dosyalari(repo: Path) -> list[Path]:
    """Bagimlilik bildiren pyproject.toml dosyalari."""
    return [kok / "pyproject.toml" for kok in _kokler(repo) if (kok / "pyproject.toml").is_file()]


def _npm_manifestleri(repo: Path) -> list[tuple[Path, Path | None]]:
    """(kok, package-lock.json veya None) -> kilit yoksa denetlenemedi."""
    ciftler: list[tuple[Path, Path | None]] = []
    for kok in _kokler(repo):
        if not (kok / "package.json").is_file():
            continue
        kilit = kok / "package-lock.json"
        ciftler.append((kok, kilit if kilit.is_file() else None))
    return ciftler


def _desteklenmeyen(repo: Path) -> list[str]:
    bulunan: list[str] = []
    for kok in _kokler(repo):
        for kalip in DESTEKLENMEYEN:
            bulunan.extend(_iliskili(repo, e) for e in sorted(kok.glob(kalip)))
    return bulunan


# --------------------------------------------------------------------------
# Calistirma
# --------------------------------------------------------------------------


def _calistir(argv: list[str], cwd: Path | None, zaman_asimi: int) -> tuple[int, str, str]:
    """varsayilan calistirici: alt surec, cikti yakalanir, konsol penceresi acilmaz."""
    ek: dict[str, object] = {}
    if hasattr(subprocess, "CREATE_NO_WINDOW"):  # Windows
        ek["creationflags"] = subprocess.CREATE_NO_WINDOW
    biten = subprocess.run(
        argv,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=zaman_asimi,
        # pip-audit requirements'i yerel kod sayfasiyla okur; UTF-8 dosyada (Turkce yorum) Windows'ta cokuyor.
        env={**os.environ, "PYTHONUTF8": "1"},
        **ek,  # type: ignore[arg-type]
    )
    return biten.returncode, biten.stdout, biten.stderr


def _denetlenemedi(ekosistem: str, kaynak: str, neden: str, ayrinti: str | None = None) -> Denetim:
    return Denetim(
        ekosistem=ekosistem,
        kaynak=kaynak,
        durum="denetlenemedi",
        neden=neden,
        sayilar=_bos_sayilar(),
        toplam=0,
        aciklar=[],
        ayrinti=(ayrinti or "").strip()[-AYRINTI_EN_FAZLA:] or None,
    )


def _cozum(ekosistem: str, kaynak: str, stdout: str, stderr: str, ayristir) -> Denetim:
    """stdout JSON ise basarili sayilir; cikis koduna BAKILMAZ."""
    try:
        sayilar, aciklar = ayristir(stdout)
        toplam = len(aciklar) if ekosistem == "pip" else int(
            ((json.loads(stdout).get("metadata") or {}).get("vulnerabilities") or {}).get("total") or len(aciklar)
        )
    except (json.JSONDecodeError, AttributeError, TypeError, ValueError):
        return _denetlenemedi(ekosistem, kaynak, "cikti-bozuk", stderr)
    return Denetim(
        ekosistem=ekosistem,
        kaynak=kaynak,
        durum="temiz" if toplam == 0 else "acik",
        sayilar=sayilar,
        toplam=toplam,
        aciklar=aciklar,
    )


def _denetim_pip(
    kaynak: str, requirements: Path, calistir: Calistir, zaman_asimi: int
) -> Denetim:
    if importlib.util.find_spec("pip_audit") is None:
        return _denetlenemedi("pip", kaynak, "arac-yok", f"pip_audit bulunamadi: {sys.executable} -m pip install pip-audit")
    # --progress-spinner off SART: ilerleme metni stdout'a karisip JSON'u bozuyor.
    argv = [
        sys.executable, "-m", "pip_audit", "-r", str(requirements),
        "--format", "json", "--progress-spinner", "off",
    ]
    try:
        _rc, stdout, stderr = calistir(argv, None, zaman_asimi)
    except subprocess.TimeoutExpired:
        return _denetlenemedi("pip", kaynak, "zaman-asimi", f"{zaman_asimi} saniyede bitmedi")
    except FileNotFoundError as exc:
        return _denetlenemedi("pip", kaynak, "arac-yok", str(exc))
    except Exception as exc:  # tek repo taramayi cokertmemeli
        return _denetlenemedi("pip", kaynak, "hata", f"{type(exc).__name__}: {exc}")
    return _cozum("pip", kaynak, stdout, stderr, parse_pip_audit)


def _denetim_npm(
    kaynak: str, npm: str, kok: Path, gecici: Path, calistir: Calistir, zaman_asimi: int
) -> Denetim:
    # package.json + package-lock.json gecici dizine kopyalanir; repoda HICBIR SEY calisir.
    for ad in ("package.json", "package-lock.json"):
        shutil.copy2(kok / ad, gecici / ad)
    try:
        _rc, stdout, stderr = calistir([npm, "audit", "--json", "--package-lock-only"], gecici, zaman_asimi)
    except subprocess.TimeoutExpired:
        return _denetlenemedi("npm", kaynak, "zaman-asimi", f"{zaman_asimi} saniyede bitmedi")
    except FileNotFoundError as exc:
        return _denetlenemedi("npm", kaynak, "arac-yok", str(exc))
    except Exception as exc:
        return _denetlenemedi("npm", kaynak, "hata", f"{type(exc).__name__}: {exc}")
    return _cozum("npm", kaynak, stdout, stderr, parse_npm_audit)


def denetle_repo(repo: Path, calistir: Calistir = _calistir, zaman_asimi: int = 120) -> RepoSonuc:
    """Tek repoyu denetler. hicbir istisna disari tasmaz."""
    repo = Path(repo)
    sonuc = RepoSonuc(yol=str(repo), ad=repo.name or str(repo), desteklenmeyen=_desteklenmeyen(repo))
    npm = shutil.which("npm")
    # Gecici dizin: pyproject bagimliliklari ve npm kopyalari buraya yazilir, repoya HICBIR SEY.
    with tempfile.TemporaryDirectory(prefix="bagimlilik-") as gecici_ad:
        gecici = Path(gecici_ad)
        for dosya in _requirements_dosyalari(repo):
            sonuc.denetimler.append(_denetim_pip(_iliskili(repo, dosya), dosya, calistir, zaman_asimi))

        for pyproject in _pyproject_dosyalari(repo):
            satirlar = _pyproject_bagliliklari(pyproject)
            if not satirlar:
                continue  # bildirilen bagimlilik yok: denetlenecek sey yok, hata degil
            gecici_requirements = gecici / f"{_iliskili(repo, pyproject).replace('/', '_')}.requirements.txt"
            gecici_requirements.write_text("\n".join(satirlar) + "\n", encoding="utf-8")
            sonuc.denetimler.append(
                _denetim_pip(_iliskili(repo, pyproject), gecici_requirements, calistir, zaman_asimi)
            )

        for kok, kilit in _npm_manifestleri(repo):
            kaynak = _iliskili(repo, kok / "package.json")
            if kilit is None:
                sonuc.denetimler.append(_denetlenemedi("npm", kaynak, "kilit-yok", "package-lock.json yok"))
                continue
            if npm is None:
                sonuc.denetimler.append(_denetlenemedi("npm", kaynak, "arac-yok", "npm bulunamadi"))
                continue
            sonuc.denetimler.append(_denetim_npm(kaynak, npm, kok, gecici, calistir, zaman_asimi))
    return sonuc
