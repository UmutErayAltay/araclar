"""Paket adi <-> import adi eslesmesi, normalizasyon ve izin (dev) listesi.

Kural: tabloda yoksa import adi = paket adi (`-` -> `_`). Tabloyu buyutmek
eslesmeyi daraltir, kucultmek ise yanlis bulgu uretir; buradaki kayitlar
"import adi ne olabilir" olasiliklari listesidir.
"""

from __future__ import annotations

import re

#: Bildirilen (normalize edilmis) paket adi -> import adlari (ilk sirada birincil).
#: Bir paket birden fazla import adi ile gelebilir (orn. psycopg / psycopg2).
ESLESME: dict[str, tuple[str, ...]] = {
    "attrs": ("attr",),
    "beautifulsoup4": ("bs4",),
    "discord-py": ("discord",),
    "django-cors-headers": ("corsheaders",),
    "djangorestframework": ("rest_framework",),
    "dnspython": ("dns",),
    "docker": ("docker",),
    "email-validator": ("email_validator",),
    "google-api-python-client": ("googleapiclient",),
    "google-auth": ("google",),
    "grpcio": ("grpc",),
    "importlib-metadata": ("importlib_metadata",),
    "mysqlclient": ("MySQLdb",),
    "opencv-python": ("cv2",),
    "opencv-python-headless": ("cv2",),
    "pillow": ("PIL",),
    "protobuf": ("google",),
    "psycopg": ("psycopg",),
    "psycopg2": ("psycopg2",),
    "psycopg2-binary": ("psycopg2",),
    "pycryptodome": ("Crypto",),
    "pyjwt": ("jwt",),
    "pymongo": ("pymongo",),
    "pyodbc": ("pyodbc",),
    "pyopenssl": ("OpenSSL",),
    "pytest": ("pytest", "_pytest"),
    "python-dateutil": ("dateutil",),
    "python-docx": ("docx",),
    "python-dotenv": ("dotenv",),
    "python-jose": ("jose",),
    "python-json-logger": ("pythonjsonlogger",),
    "python-multipart": ("multipart",),
    "python-pptx": ("pptx",),
    "python-slugify": ("slugify",),
    "pytz": ("pytz",),
    "pyyaml": ("yaml",),
    "scikit-learn": ("sklearn",),
    "setuptools": ("setuptools", "pkg_resources"),
    "sqlalchemy": ("sqlalchemy",),
    "telegram": ("telegram",),
    "typing-extensions": ("typing_extensions",),
    "tzdata": ("tzdata",),
    "tzlocal": ("tzlocal",),
    "watchdog": ("watchdog",),
}

#: Test/derleme araclari: koda hic import edilmeseler de "plugin gibi" calisir,
#: bu yuzden KULLANILMAYAN sayilmazlar. On ekli adlar: pytest eklentileri.
IZINLI_ADLAR = frozenset(
    {
        "black",
        "build",
        "coverage",
        "flake8",
        "hatch",
        "hatchling",
        "isort",
        "mypy",
        "nox",
        "pip",
        "pip-tools",
        "pluggy",
        "pre-commit",
        "pylint",
        "pytest",
        "pytest-asyncio",
        "pytest-cov",
        "pytest-mock",
        "pytest-xdist",
        "ruff",
        "setuptools",
        "tox",
        "twine",
        "virtualenv",
        "wheel",
    }
)

#: Bir Python dosyasinin okunabilecegi en buyuk boyut (bayt). Daha buyugu ATLANIR.
MAKS_BOYUT = 1024 * 1024


def normalle(ad: str) -> str:
    """Paket adini karsilastirma icin normalize eder: kucuk harf, `_`/`.` -> `-`."""
    return ad.strip().lower().replace("_", "-").replace(".", "-")


def paket_adi_satiri(satir: str) -> str | None:
    """requirements.txt / pyproject bir satirindan paket adini cikarir.

    Ayiklanir: bos satir, yorum (`#`), surum (`==`), extras (`[x]`), ortam
    isaretleyicisi (`; python_version<"3"`), `-r other.txt`, `-e .`,
    `--hash`, bayrak (`-i ...`), opsiyonel `name @ url`.
    Donen deger normalize edilmis ad ya da None (paket degilse).
    """
    satir = satir.split("#", 1)[0].strip()
    if not satir or satir.startswith("-"):
        return None
    # "ad @ url" bicimi: yalnizca ad kalir.
    satir = satir.split("@", 1)[0].strip()
    if not satir:
        return None
    # extras + surum ayikla: "uvicorn[standard]>=0.20" -> "uvicorn"
    ad = re.split(r"[\[<>=!~;\s]", satir, maxsplit=1)[0].strip()
    if not ad or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", ad):
        return None
    return normalle(ad)


def import_adlari(paket: str) -> tuple[str, ...]:
    """Bir paketin olasi import adlari (kucuk harfli, nokta -> tire normalize)."""
    if paket in ESLESME:
        return ESLESME[paket]
    return (paket.replace("-", "_"),)


def izinli_mi(paket: str) -> bool:
    """Test/derleme araci ya da pytest eklentisi mi? (kullanilmayan sayilmaz)."""
    return paket in IZINLI_ADLAR or paket.startswith("pytest-")


def karsilastir(paket: str, kullanilan: set[str]) -> bool:
    """Paket adi, kullanilan import adlari kumesinde TEMSIL EDILIYOR mu?

    `kullanilan` kucuk harfli olmalidir. Import adinin ilk parcasi yeterlidir
    (`import a.b` icin `a` kullanilmis sayilir). Karsilastirma kucuk harfe
    indirilir: tablo `PIL` yazar, import adi da `pil` olabilir.
    """
    return any(ad.split(".")[0].lower() in kullanilan for ad in import_adlari(paket))