"""turler.py testleri: kanıtlı/kanıtsız türler, risk durumu, venv özel kuralı."""

from __future__ import annotations

from pathlib import Path
import pytest
from devtemizle.turler import (
    tum_turler,
    tur_ara,
    risk_durumu,
    kanit_var_mi,
    tur_adlari,
)


# --------------------------------------------------------------------------
# Tür tanımı doğrulama
# --------------------------------------------------------------------------


def test_tum_turler_dolu():
    """En az 1 tür tanımı var."""
    assert len(tum_turler()) >= 5


def test_tur_ara_bilinen():
    """Bilinen türler bulunur."""
    assert tur_ara("node_modules") is not None
    assert tur_ara("__pycache__") is not None
    assert tur_ara(".venv") is not None


def test_tur_ara_bilinmeyen_none():
    """Bilinmeyen tür None döner."""
    assert tur_ara("yok-boyle-tur") is None


def test_tur_adlari_sirali():
    """tur_adlari sıralı liste döner."""
    adlar = tur_adlari()
    assert adlar == sorted(adlar)
    assert "node_modules" in adlar


# --------------------------------------------------------------------------
# Kanıtlı / kanıtsız türler
# --------------------------------------------------------------------------


@pytest.mark.parametrize("tur_ad", ["__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"])
def test_python_cache_turleri_kanitsiz(tur_ad):
    """Python cache türleri kanıtsız (kanit tuple'ı boş)."""
    t = tur_ara(tur_ad)
    assert t is not None
    assert t.kanit == ()
    assert kanit_var_mi(tur_ad, "/tmp/yok") is True  # her yerde geçerli


@pytest.mark.parametrize("tur_ad", ["htmlcov"])
def test_htmlcov_kanitsiz(tur_ad):
    """htmlcov kanıtsız."""
    t = tur_ara(tur_ad)
    assert t is not None
    assert t.kanit == ()


@pytest.mark.parametrize("tur_ad", ["node_modules", "__pycache__", ".pytest_cache", ".venv", "venv"])
def test_orijinal_turler_kanitsiz_geriye_uyumlu(tur_ad, tmp_path):
    """Orijinal 5 tür (v0.1) geriye uyumluluk için kanıtsız çalışır.

    Boş repoda bile aday sayılır (atlanmaz).
    """
    repo = tmp_path / "r"
    repo.mkdir()
    assert kanit_var_mi(tur_ad, str(repo)) is True, f"{tur_ad} kanıtsız olmalı"


@pytest.mark.parametrize("tur_ad,kanit_dosyasi", [
    (".next", "package.json"),
    (".nuxt", "package.json"),
    (".turbo", "package.json"),
    (".parcel-cache", "package.json"),
    (".svelte-kit", "package.json"),
    ("target", "Cargo.toml"),
    (".tox", "tox.ini"),
    (".nox", "noxfile.py"),
    ("build", "build.gradle"),
    (".gradle", "build.gradle"),
    ("dist", "package.json"),
    ("coverage", "package.json"),
])
def test_tur_kanit_dosyasi(tur_ad, kanit_dosyasi, tmp_path):
    """YENİ türler için kanıt dosyası varsa aday olur, yoksa atlanır.

    Not: orijinal 5 tür (node_modules, __pycache__, .pytest_cache, .venv, venv)
    geriye uyumluluk için kanıtsız çalışır (bkz. test_orijinal_turler_kanitsiz_geriye_uyumlu).
    """
    t = tur_ara(tur_ad)
    assert t is not None
    assert kanit_dosyasi in t.kanit

    repo = tmp_path / "r"
    repo.mkdir()
    # Kanıt yok -> atlandi
    assert kanit_var_mi(tur_ad, str(repo)) is False
    # Kanıt var -> aday
    (repo / kanit_dosyasi).write_text("", encoding="utf-8")
    assert kanit_var_mi(tur_ad, str(repo)) is True


# --------------------------------------------------------------------------
# Risk durumu: dikkat türleri varsayılan dışı
# --------------------------------------------------------------------------


def test_dikkat_turleri_risk_dikkat():
    """PLAN.md §1 tablosundaki dikkat türleri risk='dikkat'."""
    for tur_ad in ["build", "dist"]:
        t = tur_ara(tur_ad)
        assert t is not None
        assert t.risk == "dikkat"
        assert risk_durumu(tur_ad, "/tmp/repo") == "dikkat"


def test_guvenli_turler_risk_guvenli():
    """Diğer türler risk='guvenli'."""
    for tur_ad in ["node_modules", "__pycache__", ".pytest_cache", "target", ".gradle", "htmlcov"]:
        t = tur_ara(tur_ad)
        assert t is not None
        assert t.risk == "guvenli"
        assert risk_durumu(tur_ad, "/tmp/repo") == "guvenli"


# --------------------------------------------------------------------------
# venv / .venv özel kuralı: bağımlılık listesi yoksa dikkat
# --------------------------------------------------------------------------


@pytest.mark.parametrize("tur_ad", [".venv", "venv"])
def test_venv_baglanti_listesi_varsa_guvenli(tur_ad, tmp_path):
    """Bağımlılık listesi dosyası (pyproject.toml, requirements.txt, vb.) varsa güvenli."""
    repo = tmp_path / "r"
    repo.mkdir()
    (repo / "requirements.txt").write_text("requests\n", encoding="utf-8")
    assert risk_durumu(tur_ad, str(repo)) == "guvenli"


@pytest.mark.parametrize("tur_ad", [".venv", "venv"])
def test_venv_baglanti_listesi_yoksa_dikkat(tur_ad, tmp_path):
    """Hiçbir bağımlılık listesi dosyası yoksa dikkat."""
    repo = tmp_path / "r"
    repo.mkdir()
    # Boş repo, hiçbir kanıt dosyası yok
    assert risk_durumu(tur_ad, str(repo)) == "dikkat"


@pytest.mark.parametrize("kanit", ("pyproject.toml", "requirements.txt", "requirements-dev.txt", "Pipfile", "poetry.lock", "uv.lock"))
def test_venv_kanit_dosyalari(tmp_path, kanit):
    """Tüm bağımlılık listesi dosyaları güvenli sayılmalı."""
    repo = tmp_path / "r"
    repo.mkdir()
    (repo / kanit).write_text("", encoding="utf-8")
    assert risk_durumu(".venv", str(repo)) == "guvenli", f"{kanit} için güvenli olmadı"
    assert risk_durumu("venv", str(repo)) == "guvenli", f"{kanit} için güvenli olmadı"


def test_venv_repo_kok_none_guvenli():
    """repo_kok None verilirse (bilinmiyorsa) varsayılan güvenli."""
    # risk_durumu None repo_kok için tablo risk'ini döndürür
    assert risk_durumu(".venv", None) == "guvenli"
    assert risk_durumu("venv", None) == "guvenli"


# --------------------------------------------------------------------------
# Yeniden komutları
# --------------------------------------------------------------------------


def test_yeniden_komutlari_dolu():
    """Her tür için yeniden alanı dolu."""
    for t in tum_turler():
        assert t.yeniden, f"{t.ad} için yeniden komutu boş"
        assert isinstance(t.yeniden, str)


def test_aciklama_dolu():
    """Her tür için açıklama dolu."""
    for t in tum_turler():
        assert t.aciklama, f"{t.ad} için açıklama boş"
        assert isinstance(t.aciklama, str)


# --------------------------------------------------------------------------
# Grup doğrulaması
# --------------------------------------------------------------------------


def test_gruplar_gecerli():
    """Grup değerleri izinli listede."""
    izinli = {"js", "python", "rust", "jvm", "genel"}
    for t in tum_turler():
        assert t.grup in izinli, f"{t.ad}: geçersiz grup {t.grup}"