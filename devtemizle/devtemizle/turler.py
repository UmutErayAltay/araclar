"""Turler: aday tür kural tablosu (PLAN.md §1).

Tek bir veri kaynağı; tara.py, sil.py, rapor.py, web paneli hepsi bunu kullanır.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class Tur:
    """Aday türü tanımı.

    Kanıt tuple'ı boşsa kanıt aranmaz (örn. __pycache__).
    Kanıt, adayın KARDEŞ dosyalarında aranır (adayın bulunduğu dizinde; repo
    kökünde değil). risk: "guvenli" | "dikkat"
    """
    ad: str
    grup: str
    risk: str
    kanit: tuple[str, ...]
    aciklama: str
    yeniden: str


# Kural tablosu (PLAN.md §1 tablo)
# Not: Çoklu isimli türler (örn. .next/.nuxt) ayrı Tur nesneleri olarak verilir.
_TURLER: Final[list[Tur]] = [
    Tur(
        ad="node_modules",
        grup="js",
        risk="guvenli",
        kanit=("package.json",),
        aciklama="npm install ile geri gelir",
        yeniden="npm install",
    ),
    Tur(
        ad=".next",
        grup="js",
        risk="guvenli",
        kanit=("package.json",),
        aciklama="npm run build ile geri gelir",
        yeniden="npm run build",
    ),
    Tur(
        ad=".nuxt",
        grup="js",
        risk="guvenli",
        kanit=("package.json",),
        aciklama="npm run build ile geri gelir",
        yeniden="npm run build",
    ),
    Tur(
        ad=".turbo",
        grup="js",
        risk="guvenli",
        kanit=("package.json",),
        aciklama="npm run build ile geri gelir",
        yeniden="npm run build",
    ),
    Tur(
        ad=".parcel-cache",
        grup="js",
        risk="guvenli",
        kanit=("package.json",),
        aciklama="npm run build ile geri gelir",
        yeniden="npm run build",
    ),
    Tur(
        ad=".svelte-kit",
        grup="js",
        risk="guvenli",
        kanit=("package.json",),
        aciklama="npm run build ile geri gelir",
        yeniden="npm run build",
    ),
    Tur(
        ad="__pycache__",
        grup="python",
        risk="guvenli",
        kanit=(),
        aciklama="otomatik yeniden oluşturulur",
        yeniden="otomatik",
    ),
    Tur(
        ad=".pytest_cache",
        grup="python",
        risk="guvenli",
        kanit=(),
        aciklama="pytest çalıştığında yeniden oluşur",
        yeniden="otomatik",
    ),
    Tur(
        ad=".mypy_cache",
        grup="python",
        risk="guvenli",
        kanit=(),
        aciklama="mypy çalıştığında yeniden oluşur",
        yeniden="otomatik",
    ),
    Tur(
        ad=".ruff_cache",
        grup="python",
        risk="guvenli",
        kanit=(),
        aciklama="ruff çalıştığında yeniden oluşur",
        yeniden="otomatik",
    ),
    Tur(
        ad=".tox",
        grup="python",
        risk="guvenli",
        kanit=("tox.ini", "noxfile.py", "pyproject.toml"),
        aciklama="tox ile yeniden oluşturulur",
        yeniden="tox",
    ),
    Tur(
        ad=".nox",
        grup="python",
        risk="guvenli",
        kanit=("tox.ini", "noxfile.py", "pyproject.toml"),
        aciklama="nox ile yeniden oluşturulur",
        yeniden="nox",
    ),
    Tur(
        ad=".venv",
        grup="python",
        risk="guvenli",
        kanit=(
            "pyproject.toml",
            "requirements.txt",
            "requirements-dev.txt",
            "Pipfile",
            "poetry.lock",
            "uv.lock",
        ),
        aciklama="pip install -r requirements.txt ile geri gelir",
        yeniden="pip install -r requirements.txt",
    ),
    Tur(
        ad="venv",
        grup="python",
        risk="guvenli",
        kanit=(
            "pyproject.toml",
            "requirements.txt",
            "requirements-dev.txt",
            "Pipfile",
            "poetry.lock",
            "uv.lock",
        ),
        aciklama="pip install -r requirements.txt ile geri gelir",
        yeniden="pip install -r requirements.txt",
    ),
    Tur(
        ad="target",
        grup="rust",
        risk="guvenli",
        kanit=("Cargo.toml",),
        aciklama="cargo build ile geri gelir",
        yeniden="cargo build",
    ),
    Tur(
        ad="build",
        grup="jvm",
        risk="dikkat",
        kanit=("build.gradle", "build.gradle.kts", "pom.xml", "CMakeLists.txt", "setup.py"),
        aciklama="proje derlemesi ile geri gelir",
        yeniden="proje derlemesi",
    ),
    Tur(
        ad=".gradle",
        grup="jvm",
        risk="guvenli",
        kanit=("build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts"),
        aciklama="otomatik yeniden oluşturulur",
        yeniden="otomatik",
    ),
    Tur(
        ad="dist",
        grup="genel",
        risk="dikkat",
        kanit=("package.json", "pyproject.toml", "setup.py"),
        aciklama="derleme ile geri gelir",
        yeniden="derleme",
    ),
    Tur(
        ad="htmlcov",
        grup="genel",
        risk="guvenli",
        kanit=("pyproject.toml", ".coveragerc", "setup.cfg", "tox.ini"),
        aciklama="test koşusu ile geri gelir",
        yeniden="test koşusu",
    ),
    Tur(
        ad="coverage",
        grup="genel",
        risk="dikkat",
        kanit=("package.json",),
        aciklama="test koşusu ile geri gelir",
        yeniden="test koşusu",
    ),
]


# İsim -> Tur haritası (hızlı arama için)
_TUR_HARITASI: Final[dict[str, Tur]] = {t.ad: t for t in _TURLER}


def tum_turler() -> list[Tur]:
    """Tüm türleri döndürür (sıralı kopya)."""
    return list(_TURLER)


def tur_ara(ad: str) -> Tur | None:
    """İsimle tür arar; yoksa None."""
    return _TUR_HARITASI.get(ad)


def tur_adlari() -> list[str]:
    """Sadece ad listesi (CLI choices için)."""
    return sorted(_TUR_HARITASI.keys())


def risk_durumu(ad: str, kardes_dizin: str | None = None, tur: Tur | None = None) -> str:
    """Bir tür için risk durumunu hesaplar.

    .venv/venv özel kuralı: bağımlılık listesi dosyası (adayın kardeşi) yoksa "dikkat".
    Diğer türler tablodaki risk değerini kullanır. Bilinmeyen tür: "dikkat".
    """
    t = tur or tur_ara(ad)
    if t is None:
        return "dikkat"

    if ad in (".venv", "venv"):
        # pyvenv.cfg varlığı tara.py'de zaten kontrol ediliyor; burada sadece
        # bağımlılık listesi dosyası var mı diye bakıyoruz.
        if kardes_dizin:
            from pathlib import Path
            for kanit_dosyasi in t.kanit:
                if (Path(kardes_dizin) / kanit_dosyasi).exists():
                    return "guvenli"
            return "dikkat"
        return "guvenli"

    return t.risk


# Orijinal v0.1 türleri (geriye uyumluluk için kanıt aranmaz)
_ORJINAL_TURLER = frozenset({"node_modules", "__pycache__", ".pytest_cache", ".venv", "venv"})


def kanit_var_mi(ad: str, kardes_dizin: str) -> bool:
    """Türün kanıtı, adayın KARDEŞ dizininde (kardes_dizin = adayın üst dizini) var mı?

    Repo kökündeki bir dosya, alt dizindeki adayı (ör. src/coverage) kanıtlamaz.
    Orijinal 5 tür (node_modules, __pycache__, .pytest_cache, .venv, venv)
    için geriye uyumluluk: kanıt aranmaz.
    """
    t = tur_ara(ad)
    if t is None or not t.kanit:
        return True  # kanıt gerekmez

    # Geriye uyumluluk: orijinal 5 tür için kanıt kontrolü atlanır
    if ad in _ORJINAL_TURLER:
        return True

    from pathlib import Path
    kok = Path(kardes_dizin)
    return any((kok / k).exists() for k in t.kanit)