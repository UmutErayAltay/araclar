"""eslesme: paket adi normalizasyonu, satir ayiklama, import eslesme tablosu, izin listesi."""

from __future__ import annotations

import pytest

from olubag.eslesme import (
    ESLESME,
    IZINLI_ADLAR,
    import_adlari,
    karsilastir,
    normalle,
    paket_adi_satiri,
    izinli_mi,
)


# --------------------------------------------------------------------------
# paket_adi_satiri: surum / extras / ortam isaretleyicisi / -r / -e ayiklama
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "satir, beklenen",
    [
        ("requests", "requests"),
        ("  requests==2.31.0  ", "requests"),
        ("requests>=2.0,<3", "requests"),
        ("uvicorn[standard]>=0.20", "uvicorn"),
        ("psycopg[binary]>=3", "psycopg"),
        ("PyYAML", "pyyaml"),
        ("python-dotenv", "python-dotenv"),
        ("importlib-metadata", "importlib-metadata"),
        ("setuptools_scm", "setuptools-scm"),
        ('requests ; python_version < "3.9"', "requests"),
        ("flask @ https://example.invalid/f.whl", "flask"),
        ("django-rest-framework", "django-rest-framework"),
    ],
)
def test_paket_adi_ayiklanir(satir, beklenen):
    """Sadece paket adi kalir: surum, extras, ortam isaretleyicisi, URL atilir."""
    assert paket_adi_satiri(satir) == beklenen


def test_satir_ici_yorum_ayiklanir():
    """`requests==2.0  # aciklama` satirinda yorum kesilir, paket adi `requests` kalir."""
    assert paket_adi_satiri("requests==2.0  # aciklama") == "requests"


@pytest.mark.parametrize(
    "satir",
    [
        "",
        "   ",
        "# yorum satiri",
        "-r other.txt",
        "-r base.txt",
        "-e .",
        "-e git+https://example.invalid/x.git#egg=x",
        "--index-url https://example.invalid/simple",
        "--hash=sha256:abc123",
        "-i https://example.invalid/simple",
    ],
)
def test_paket_adi_olmayan_satirlar(satir):
    """Yorum, indirme satiri (-r/-e) ve bayraklar PAKET DEGILDIR -> None."""
    assert paket_adi_satiri(satir) is None


# --------------------------------------------------------------------------
# normalle
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ham, beklenen",
    [
        ("PyYAML", "pyyaml"),
        ("Flask_SQLAlchemy", "flask-sqlalchemy"),
        ("zope.interface", "zope-interface"),
        ("  Requests  ", "requests"),
    ],
)
def test_normalle_kucuk_harf_tire(ham, beklenen):
    """Ad normalizasyonu: kucuk harf, `_` ve `.` -> `-`."""
    assert normalle(ham) == beklenen


# --------------------------------------------------------------------------
# Eşleme tablosu
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "paket, import_ad",
    [
        ("pyyaml", "yaml"),
        ("python-multipart", "multipart"),
        ("pillow", "PIL"),
        ("beautifulsoup4", "bs4"),
        ("scikit-learn", "sklearn"),
        ("python-dateutil", "dateutil"),
        ("opencv-python", "cv2"),
        ("python-docx", "docx"),
        ("python-dotenv", "dotenv"),
        ("psycopg2-binary", "psycopg2"),
        ("psycopg", "psycopg"),
        ("uvicorn", "uvicorn"),
        ("cryptography", "cryptography"),
    ],
)
def test_import_eslesmeleri(paket, import_ad):
    """Sozlesmedeki eslesmeler dogru: paket adi -> import adi."""
    assert import_ad in import_adlari(paket), f"{paket} -> {import_adlari(paket)}"


def test_tabloda_yoksa_tire_underscore():
    """Tabloda olmayan paket icin kural: import adi = paket adi, `-` -> `_`."""
    assert import_adlari("flask-sqlalchemy") == ("flask_sqlalchemy",)
    assert import_adlari("rich") == ("rich",)


def test_eslesme_buyuk_kucuk_harf_duyarsiz():
    """Karsilastirma kucuk harfli kume ile yapilir: `PIL` = `pil` sayilir."""
    assert karsilastir("pillow", {"pil"}) is True


def test_karsilastir_ust_paket_egerleri():
    """`import a.b` icin ust paket `a` kullanilmis sayilir."""
    assert karsilastir("psycopg2", {"psycopg2"}) is True


def test_karsilastir_eslesme_yoksa_uyumsuz():
    """Kullanilan kume pakete uymuyorsa eslesme kurulmaz."""
    assert karsilastir("requests", {"yaml", "rich"}) is False
    assert karsilastir("pyyaml", {"yamlx"}) is False, "onek eslesmesi yanlis sayilmamali"


# --------------------------------------------------------------------------
# İzin listesi
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ad",
    ["pytest", "ruff", "mypy", "black", "hatchling", "setuptools", "wheel", "pip"],
)
def test_dev_araclari_izinli(ad):
    """Test/derleme araclari koda import edilmese de 'plugin gibi' calisir: izinli."""
    assert izinli_mi(ad) is True
    assert ad in IZINLI_ADLAR


@pytest.mark.parametrize("ad", ["pytest-cov", "pytest-asyncio", "pytest-xdist", "pytest-mock"])
def test_pytest_eklentileri_izinli(ad):
    """pytest eklentileri (pytest- oneki) otomatik izinlidir."""
    assert izinli_mi(ad) is True


def test_uygulama_paketleri_izinli_degil():
    """Normal uygulama bagimliliklari izinli DEGILDIR."""
    assert izinli_mi("requests") is False
    assert izinli_mi("pyyaml") is False


def test_eslesme_tablosu_normalize_kucuk_harf():
    """Tablo anahtarlari normalize kuralina uyar (buyuk harf sizmaz)."""
    for paket in ESLESME:
        assert paket == normalle(paket), paket