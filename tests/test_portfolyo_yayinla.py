"""tools/portfolyo_yayinla.py: kopyalama, fark raporu, yanlış hedef koruması, commit atmama."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_KOK / "tools"))
import portfolyo_yayinla as py  # noqa: E402


def _site(tmp_path: Path) -> Path:
    site = tmp_path / "site"
    site.mkdir()
    (site / "portfolyo.json").write_text("{}", encoding="utf-8")
    return site


def test_ilk_kopyalama_dosyalari_ve_kaynak_txt_yazar(tmp_path):
    site = _site(tmp_path)
    ozet = py.kopyala(site)
    assert "generator/portfolyo/html.py" in ozet["yeni"] and "generator/tests/test_yazi.py" in ozet["yeni"]
    assert (site / "generator" / "portfolyo" / "cli.py").read_bytes() == (_KOK / "portfolyo" / "portfolyo" / "cli.py").read_bytes()
    kaynak = (site / "generator" / "KAYNAK.txt").read_text(encoding="utf-8")
    assert f"commit:   {py.kaynak_sha()}" in kaynak and "vendoring" in kaynak
    assert not (site / ".git").exists()  # commit/push yok, git deposu bile açılmaz


def test_ikinci_kopya_ayni_ve_check_sifir(tmp_path):
    site = _site(tmp_path)
    py.kopyala(site)
    ozet = py.kopyala(site, yaz=False)
    assert not (ozet["yeni"] or ozet["guncel"] or ozet["silinen"]) and ozet["ayni"]
    assert py.main(["--check", str(site)]) == 0


def test_degisen_ve_artik_dosyalar(tmp_path):
    site = _site(tmp_path)
    py.kopyala(site)
    cli = site / "generator" / "portfolyo" / "cli.py"
    cli.write_text("elle değişmiş", encoding="utf-8")
    artik = site / "generator" / "portfolyo" / "eski_modul.py"
    artik.write_text("x", encoding="utf-8")
    diger = site / "generator" / "portfolyo" / "notlar.txt"
    diger.write_text("dokunma", encoding="utf-8")
    assert py.main(["--check", str(site)]) == 1  # yazmaz
    assert cli.read_text(encoding="utf-8") == "elle değişmiş" and artik.exists()
    ozet = py.kopyala(site)
    assert ozet["guncel"] == ["generator/portfolyo/cli.py"] and ozet["silinen"] == ["generator/portfolyo/eski_modul.py"]
    assert cli.read_bytes() == (_KOK / "portfolyo" / "portfolyo" / "cli.py").read_bytes()
    assert not artik.exists() and diger.read_text(encoding="utf-8") == "dokunma"  # yalnız .py


def test_yanlis_hedef_reddedilir(tmp_path):
    with pytest.raises(SystemExit):
        py.kopyala(tmp_path)  # portfolyo.json yok
    assert not (tmp_path / "generator").exists()
