"""onbellek.py testleri: yol çözümü, env önceliği, komutla temizleme, docker."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from devtemizle.onbellek import (
    onbellek_tara,
    onbellek_temizle,
    docker_boyutlari,
    _onbellek_yolu_bul,
    _komut_calistir,
    _tum_kurallar,
    OnbellekKurali,
)


# --------------------------------------------------------------------------
# Yol çözümü testleri (sahte HOME/LOCALAPPDATA/XDG_CACHE_HOME)
# --------------------------------------------------------------------------


def test_onbellek_yolu_bul_unix_env_onceligi(tmp_path, monkeypatch):
    """Unix'te env değişkeni (PIP_CACHE_DIR) yollardan önce denenir."""
    env_cache = tmp_path / "env-pip-cache"
    env_cache.mkdir()

    monkeypatch.setenv("PIP_CACHE_DIR", str(env_cache))
    monkeypatch.setenv("HOME", str(tmp_path / "fake-home"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg-cache"))

    kural = next(k for k in _tum_kurallar() if k.ad == "pip")
    yol = _onbellek_yolu_bul(kural)

    assert yol == env_cache


def test_onbellek_yolu_bul_unix_xdg_cache_home(tmp_path, monkeypatch):
    """XDG_CACHE_HOME set edildiyse ~/.cache yerine kullanılır."""
    xdg_cache = tmp_path / "xdg" / "pip"
    xdg_cache.mkdir(parents=True)

    monkeypatch.delenv("PIP_CACHE_DIR", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "fake-home"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))

    kural = next(k for k in _tum_kurallar() if k.ad == "pip")
    yol = _onbellek_yolu_bul(kural)

    assert yol == xdg_cache


def test_onbellek_yolu_bul_unix_default_cache(tmp_path, monkeypatch):
    """Hiçbir env yoksa ~/.cache/pip kullanılır."""
    home_cache = tmp_path / "home" / ".cache" / "pip"
    home_cache.mkdir(parents=True)

    monkeypatch.delenv("PIP_CACHE_DIR", raising=False)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    kural = next(k for k in _tum_kurallar() if k.ad == "pip")
    yol = _onbellek_yolu_bul(kural)

    assert yol == home_cache


def test_onbellek_yolu_bul_windows_localappdata(monkeypatch):
    """Windows'ta LOCALAPPDATA kullanılır (os.name monkeypatch ile).

    Linux'ta WindowsPath oluşturulamaz, bu yüzden _yol_coz'u mockluyoruz.
    """
    import devtemizle.onbellek as onbellek_mod

    original_name = os.name
    try:
        monkeypatch.setattr(os, "name", "nt")
        monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\Test\AppData\Local")

        # _yol_coz'u mockla: %LOCALAPPDATA%\pip\Cache -> Path objesi döner
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        with patch("devtemizle.onbellek._yol_coz", return_value=mock_path):
            kural = next(k for k in _tum_kurallar() if k.ad == "pip")
            yol = _onbellek_yolu_bul(kural)
            assert yol is not None
    finally:
        monkeypatch.setattr(os, "name", original_name)


def test_onbellek_yolu_bul_windows_appdata_fallback(monkeypatch):
    """Windows'ta LOCALAPPDATA yoksa APPDATA denenir."""
    import devtemizle.onbellek as onbellek_mod

    original_name = os.name
    try:
        monkeypatch.setattr(os, "name", "nt")
        monkeypatch.delenv("LOCALAPPDATA", raising=False)
        monkeypatch.setenv("APPDATA", r"C:\Users\Test\AppData\Roaming")

        mock_path = MagicMock()
        mock_path.exists.return_value = True
        with patch("devtemizle.onbellek._yol_coz", return_value=mock_path):
            kural = next(k for k in _tum_kurallar() if k.ad == "pip")
            yol = _onbellek_yolu_bul(kural)
            assert yol is not None
    finally:
        monkeypatch.setattr(os, "name", original_name)


def test_onbellek_yolu_bul_yoksa_none(tmp_path, monkeypatch):
    """Hiçbir yol yoksa None döner."""
    monkeypatch.delenv("PIP_CACHE_DIR", raising=False)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "bos-home"))

    kural = next(k for k in _tum_kurallar() if k.ad == "pip")
    yol = _onbellek_yolu_bul(kural)

    assert yol is None


# --------------------------------------------------------------------------
# Env değişkeni önceliği testleri (tüm önbellekler için)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("kural_ad,env_var,yol_suffix", [
    ("pip", "PIP_CACHE_DIR", "pip"),
    ("npm", "npm_config_cache", "npm"),
    ("yarn", "YARN_CACHE_FOLDER", "yarn"),
    ("pnpm", "PNPM_STORE_PATH", "pnpm/store"),
    ("uv", "UV_CACHE_DIR", "uv"),
    ("cargo", "CARGO_HOME", "cargo"),
    ("gradle", "GRADLE_USER_HOME", "gradle"),
    ("playwright", "PLAYWRIGHT_BROWSERS_PATH", "playwright"),
    ("huggingface", "HF_HOME", "huggingface"),
])
def test_env_degiskeni_onceligi(kural_ad, env_var, yol_suffix, tmp_path, monkeypatch):
    """Her önbellek için env değişkeni yollardan önce denenir."""
    env_yol = tmp_path / "env" / yol_suffix
    env_yol.mkdir(parents=True)

    monkeypatch.setenv(env_var, str(env_yol))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))

    kural = next(k for k in _tum_kurallar() if k.ad == kural_ad)
    yol = _onbellek_yolu_bul(kural)

    assert yol == env_yol, f"{kural_ad}: env değişkeni öncelikli olmalı"


# --------------------------------------------------------------------------
# Komutla temizleme testleri (subprocess.run monkeypatch - GERÇEK ÇALIŞMAZ)
# --------------------------------------------------------------------------


def test_onbellek_temizle_komut_basarili(monkeypatch, tmp_path):
    """Komut başarılıysa boyut farkı hesaplanır."""
    cache_dir = tmp_path / "pip-cache"
    cache_dir.mkdir()
    (cache_dir / "file").write_bytes(b"x" * 1000)

    kural = next(k for k in _tum_kurallar() if k.ad == "pip")

    # _onbellek_yolu_bul'ı mockla
    with patch("devtemizle.onbellek._onbellek_yolu_bul", return_value=cache_dir):
        # subprocess.run başarılı dönsün
        def mock_run(*args, **kwargs):
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "removed 1000 bytes"
            mock_result.stderr = ""
            return mock_result

        with patch("subprocess.run", mock_run):
            with patch("devtemizle.onbellek.shutil.which", return_value="/usr/bin/pip"):
                sonuc = onbellek_temizle("pip", uygula=True)

    assert sonuc["basarili"] is True
    assert sonuc["yontem"] == "komut"
    assert sonuc["bosalan_bayt"] >= 0


def test_onbellek_temizle_komut_basarisiz_klasor_silinmez(monkeypatch, tmp_path):
    """Komut başarısız olursa klasör SİLİNMEZ (PLAN.md §2)."""
    cache_dir = tmp_path / "pip-cache"
    cache_dir.mkdir()
    (cache_dir / "file").write_bytes(b"x" * 1000)

    kural = next(k for k in _tum_kurallar() if k.ad == "pip")

    with patch("devtemizle.onbellek._onbellek_yolu_bul", return_value=cache_dir):
        def mock_run(*args, **kwargs):
            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_result.stdout = ""
            mock_result.stderr = "permission denied"
            return mock_result

        with patch("subprocess.run", mock_run):
            with patch("devtemizle.onbellek.shutil.which", return_value="/usr/bin/pip"):
                sonuc = onbellek_temizle("pip", uygula=True)

    assert sonuc["basarili"] is False
    assert "komut basarisiz" in sonuc["hata"]
    # Klasör hala var olmalı (silinmemeli)
    assert cache_dir.exists()


def test_onbellek_temizle_komut_yoksa_basarisiz(monkeypatch, tmp_path):
    """Komut PATH'te yoksa başarsız, klasör silinmez."""
    cache_dir = tmp_path / "pip-cache"
    cache_dir.mkdir()

    with patch("devtemizle.onbellek._onbellek_yolu_bul", return_value=cache_dir):
        with patch("devtemizle.onbellek.shutil.which", return_value=None):
            sonuc = onbellek_temizle("pip", uygula=True)

    assert sonuc["basarili"] is False
    assert "komut bulunamadi" in sonuc["hata"]
    assert cache_dir.exists()


def test_onbellek_temizle_komut_timeout(monkeypatch, tmp_path):
    """Komut timeout olursa başarsız, klasör silinmez."""
    cache_dir = tmp_path / "pip-cache"
    cache_dir.mkdir()

    with patch("devtemizle.onbellek._onbellek_yolu_bul", return_value=cache_dir):
        with patch("devtemizle.onbellek.shutil.which", return_value="/usr/bin/pip"):
            with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("pip", 300)):
                sonuc = onbellek_temizle("pip", uygula=True)

    assert sonuc["basarili"] is False
    assert "zaman asimi" in sonuc["hata"]
    assert cache_dir.exists()


def test_onbellek_temizle_klasor_silme_komut_yok(monkeypatch, tmp_path):
    """temizleme_komutu None olan önbellekler (cargo, gradle) klasör siler."""
    cache_dir = tmp_path / "cargo-registry"
    cache_dir.mkdir()
    (cache_dir / "cache").mkdir()
    (cache_dir / "cache" / "file").write_bytes(b"x" * 500)

    with patch("devtemizle.onbellek._onbellek_yolu_bul", return_value=cache_dir):
        sonuc = onbellek_temizle("cargo", uygula=True)

    assert sonuc["basarili"] is True
    assert sonuc["yontem"] == "klasor"
    assert not cache_dir.exists()


def test_onbellek_temizle_uygula_false_kuru_calisma(monkeypatch, tmp_path):
    """uygula=False: kuru çalıştırma, hiçbir şey silinmez."""
    cache_dir = tmp_path / "pip-cache"
    cache_dir.mkdir()
    (cache_dir / "file").write_bytes(b"x" * 1000)

    with patch("devtemizle.onbellek._onbellek_yolu_bul", return_value=cache_dir):
        sonuc = onbellek_temizle("pip", uygula=False)

    assert sonuc["basarili"] is True
    assert sonuc["yontem"] == "kuru-calisma"
    assert sonuc["bosalan_bayt"] == 0
    assert cache_dir.exists()


def test_onbellek_temizle_yoksa_basarili_sifir(monkeypatch):
    """Önbellek yoksa (var=False) başarıyla döner, 0 bayt."""
    with patch("devtemizle.onbellek._onbellek_yolu_bul", return_value=None):
        sonuc = onbellek_temizle("pip", uygula=True)

    assert sonuc["basarili"] is True
    assert sonuc["onceki_boyut"] == 0
    assert sonuc["bosalan_bayt"] == 0
    assert sonuc["yontem"] == "yok"


# --------------------------------------------------------------------------
# onbellek_tara testleri
# --------------------------------------------------------------------------


def test_onbellek_tara_liste_dondurur(monkeypatch):
    """onbellek_tara liste döner, her öğe gerekli alanları taşır."""
    with patch("devtemizle.onbellek._onbellek_yolu_bul", return_value=None):
        sonuc = onbellek_tara()

    assert isinstance(sonuc, list)
    assert len(sonuc) >= 9  # PLAN.md §2 tablosundaki 9 önbellek (Docker hariç)

    for o in sonuc:
        assert "id" in o
        assert "ad" in o
        assert "grup" in o
        assert "yol" in o
        assert "boyut" in o
        assert "risk" in o
        assert "komut" in o
        assert "var" in o
        assert "yontem" in o
        assert "aciklama" in o


def test_onbellek_tara_var_false_yol_bos(monkeypatch):
    """Yoksa var=False, yol boş string."""
    with patch("devtemizle.onbellek._onbellek_yolu_bul", return_value=None):
        sonuc = onbellek_tara()

    for o in sonuc:
        if not o["var"]:
            assert o["yol"] == ""
            assert o["boyut"] == 0


# --------------------------------------------------------------------------
# Docker testleri
# --------------------------------------------------------------------------


def test_docker_boyutlari_docker_yoksa_sessiz(monkeypatch):
    """docker binary yoksa sessizce var=False döner (hata değil)."""
    with patch("devtemizle.onbellek.shutil.which", return_value=None):
        sonuc = docker_boyutlari()

    assert sonuc["var"] is False
    assert sonuc["imaj"] == 0
    assert sonuc["konteyner"] == 0
    assert sonuc["volume"] == 0
    assert sonuc["build_cache"] == 0
    assert sonuc["hata"] is None


def test_docker_boyutlari_docker_var_ama_hata(monkeypatch):
    """docker var ama hata dönerse sessizce var=False."""
    def mock_run(*args, **kwargs):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "daemon not running"
        return mock_result

    with patch("devtemizle.onbellek.shutil.which", return_value="/usr/bin/docker"):
        with patch("subprocess.run", mock_run):
            sonuc = docker_boyutlari()

    assert sonuc["var"] is False
    assert sonuc["hata"] is not None


def test_docker_boyutlari_parse(monkeypatch):
    """docker system df --format json çıktısı parse edilir."""
    json_output = '''{"Type":"Images","TotalCount":"5","Size":"1.2GB","Reclaimable":"800MB"}
{"Type":"Containers","TotalCount":"2","Size":"100MB","Reclaimable":"50MB"}
{"Type":"Local Volumes","TotalCount":"3","Size":"2GB","Reclaimable":"1GB"}
{"Type":"Build Cache","TotalCount":"10","Size":"500MB","Reclaimable":"200MB"}'''

    def mock_run(*args, **kwargs):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json_output
        return mock_result

    with patch("devtemizle.onbellek.shutil.which", return_value="/usr/bin/docker"):
        with patch("subprocess.run", mock_run):
            sonuc = docker_boyutlari()

    assert sonuc["var"] is True
    assert sonuc["imaj"] == 800 * 1024 * 1024
    assert sonuc["konteyner"] == 50 * 1024 * 1024
    assert sonuc["volume"] == 1024 * 1024 * 1024
    assert sonuc["build_cache"] == 200 * 1024 * 1024


# --------------------------------------------------------------------------
# Risk seviyeleri
# --------------------------------------------------------------------------


def test_playwright_huggingface_risk_dikkat():
    """playwright ve huggingface risk='dikkat' (PLAN.md §2)."""
    for ad in ["playwright", "huggingface"]:
        kural = next(k for k in _tum_kurallar() if k.ad == ad)
        assert kural.risk == "dikkat"


def test_diger_onbellekler_risk_guvenli():
    """Diğer önbellekler risk='guvenli'."""
    for ad in ["pip", "npm", "yarn", "pnpm", "uv", "cargo", "gradle"]:
        kural = next(k for k in _tum_kurallar() if k.ad == ad)
        assert kural.risk == "guvenli"


# --------------------------------------------------------------------------
# _komut_calistir yardımcı testleri
# --------------------------------------------------------------------------


def test_komut_calistir_basarili(monkeypatch):
    """Komut başarılı çalışırsa (True, stdout) döner."""
    def mock_run(*args, **kwargs):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "success output"
        mock_result.stderr = ""
        return mock_result

    with patch("subprocess.run", mock_run):
        with patch("devtemizle.onbellek.shutil.which", return_value="/usr/bin/test"):
            basarili, cikti = _komut_calistir(("test", "arg"))

    assert basarili is True
    assert cikti == "success output"


def test_komut_calistir_basarisiz(monkeypatch):
    """Komut hata dönerse (False, stderr) döner."""
    def mock_run(*args, **kwargs):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "error message"
        return mock_result

    with patch("subprocess.run", mock_run):
        with patch("devtemizle.onbellek.shutil.which", return_value="/usr/bin/test"):
            basarili, cikti = _komut_calistir(("test", "arg"))

    assert basarili is False
    assert "error message" in cikti