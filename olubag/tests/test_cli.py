"""CLI sozlesmesi: `python -m olubag` GERCEKTEN subprocess olarak calistirilir.

ATLAS_DB gecici dizine yonlendirilir: kullanicinin gercek atlas DB'si
okunmaz. Tarama yalnizca tmp_path altindaki sahte repolarda calisir.
"""

from __future__ import annotations

import json
from pathlib import Path

from conftest import js_repo, py_repo, run_module_cli, sahte_repo, tree_hash

KULLANIM_HATASI = 2
BULGU_VAR = 1


def test_bulgu_yokken_cikis_0(tmp_path):
    """Bulgu yoksa cikis 0 ve 'kullanilmayan' sayaci 0."""
    kok = tmp_path / "projeler"
    py_repo(kok / "r", ["requests"], kaynak="import requests\n")
    proc = run_module_cli("tara", "--kok", str(kok), cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert "0 kullanilmayan" in proc.stdout


def test_bulgu_varken_cikis_1(tmp_path):
    """Bulgu varsa cikis kodu 1 (CI'ya baglanabilir)."""
    kok = tmp_path / "projeler"
    py_repo(kok / "r", ["requests"], kaynak="print('x')\n")
    proc = run_module_cli("tara", "--kok", str(kok), cwd=tmp_path)
    assert proc.returncode == BULGU_VAR, proc.stdout
    assert "requests" in proc.stdout


def test_belirsiz_bulgu_da_cikis_1(tmp_path):
    """`belirsiz` bulgu da cikis kodu 1 verir (raporlanir)."""
    kok = tmp_path / "projeler"
    py_repo(kok / "r", ["requests"], kaynak="import importlib\nimportlib.import_module('x')\n")
    proc = run_module_cli("tara", "--kok", str(kok), cwd=tmp_path)
    assert proc.returncode == BULGU_VAR
    assert "belirsiz" in proc.stdout


def test_tablo_basarliklari_ve_icerik(tmp_path):
    """Tablo modu: repo/dosya:satir/paket/tur sutunlarini gosterir."""
    kok = tmp_path / "projeler"
    py_repo(kok / "r", ["requests"], kaynak="print('x')\n")
    proc = run_module_cli("tara", "--kok", str(kok), cwd=tmp_path)
    assert proc.returncode == BULGU_VAR
    assert "dosya:satir" in proc.stdout and "paket" in proc.stdout
    assert "pyproject.toml:4" in proc.stdout


def test_json_gecerli_ve_turkce_harfler(tmp_path):
    """`--json` gecerli JSON verir ve ensure_ascii=False (Turkce harfler korunur)."""
    kok = tmp_path / "projeler"
    py_repo(kok / "r", ["rich"], kaynak="print('x')\n")
    proc = run_module_cli("tara", "--kok", str(kok), "--json", cwd=tmp_path)
    assert proc.returncode == BULGU_VAR
    veri = json.loads(proc.stdout)
    assert veri["surum"] == 1
    bulgular = veri["repolar"][0]["bulgular"]
    assert bulgular[0]["paket"] == "rich" and bulgular[0]["tur"] == "kullanilmayan"


def test_json_ozet_alanlari(tmp_path):
    """JSON ciktisinda ozet sayaclari bulunur."""
    kok = tmp_path / "projeler"
    py_repo(kok / "r", ["requests", "rich"], kaynak="print('x')\n")
    proc = run_module_cli("tara", "--kok", str(kok), "--json", cwd=tmp_path)
    assert json.loads(proc.stdout)["ozet"] == {"repo": 1, "kullanilmayan": 2, "belirsiz": 0}


def test_bos_kok_cikis_2_hata_mesaji(tmp_path):
    """Hic repo bulunamazsa: cikis 2, Turkce 'Hata:' mesaji stderr'de, traceback YOK."""
    kok = tmp_path / "bos"
    kok.mkdir()
    proc = run_module_cli("tara", "--kok", str(kok), cwd=tmp_path)
    assert proc.returncode == KULLANIM_HATASI, proc.stdout
    assert "taranacak repo bulunamadi" in proc.stderr
    assert "Traceback" not in proc.stderr


def test_olmayan_kok_cikis_2(tmp_path):
    """Var olmayan --kok yolu: cikis 2, 'bulunamadi'."""
    proc = run_module_cli("tara", "--kok", str(tmp_path / "yok"), cwd=tmp_path)
    assert proc.returncode == KULLANIM_HATASI
    assert "bulunamadi" in proc.stderr


def test_birden_fazla_kok_tekrarlanabilir(tmp_path):
    """--kok birden fazla verilebilir (tekrarlanabilir bayrak)."""
    kok = tmp_path / "projeler"
    py_repo(kok / "a", ["requests"], kaynak="print('x')\n")
    py_repo(kok / "b", ["rich"], kaynak="print('x')\n")
    proc = run_module_cli("tara", "--kok", str(kok / "a"), "--kok", str(kok / "b"), cwd=tmp_path)
    assert proc.returncode == BULGU_VAR
    veri = json.loads(
        run_module_cli("tara", "--kok", str(kok / "a"), "--kok", str(kok / "b"), "--json", cwd=tmp_path).stdout
    )
    assert {r["repo"].split("/")[-1] for r in veri["repolar"]} == {"a", "b"}


def test_kok_icin_atlas_db_gerekli_ve_cikis_2(tmp_path, ev_isole):
    """--kok verilmezse atlas DB'ye gider; DB yoksa cikis 2, --kok onerilir."""
    proc = run_module_cli("tara", cwd=tmp_path, env_ek={"ATLAS_DB": str(tmp_path / "yok.db")})
    assert proc.returncode == KULLANIM_HATASI
    assert "bulunamadi" in proc.stderr and "--kok" in proc.stderr


def test_cli_diski_degistirmez(tmp_path):
    """Varsayilan davranis SALT-OKUNUR: CLI hicbir dosyayi degistirmez."""
    kok = tmp_path / "projeler"
    repo = py_repo(kok / "r", ["requests"], kaynak="import rich\n")
    once = tree_hash(repo)
    proc = run_module_cli("tara", "--kok", str(kok), cwd=tmp_path)
    assert proc.returncode == BULGU_VAR
    assert tree_hash(repo) == once, "CLI diske yazdi"


def test_uygulama_bayragi_yok(tmp_path):
    """Bu arac SALT-OKUNUR: --uygula bayragi YOKTUR (yanlis kullanim cikis 2)."""
    kok = tmp_path / "projeler"
    py_repo(kok / "r", ["requests"], kaynak="print('x')\n")
    proc = run_module_cli("tara", "--kok", str(kok), "--uygula", cwd=tmp_path)
    assert proc.returncode == KULLANIM_HATASI
    assert "unrecognized arguments" in proc.stderr or "usage" in proc.stderr.lower()


def test_alt_komut_zorunlu(tmp_path):
    """Alt komut verilmezse argparse hata, cikis 2."""
    proc = run_module_cli(cwd=tmp_path)
    assert proc.returncode == KULLANIM_HATASI
    assert "usage" in proc.stderr.lower()


def test_yardim_sifir_cikar(tmp_path):
    """--help cikis 0 ve komutu listeler."""
    proc = run_module_cli("--help", cwd=tmp_path)
    assert proc.returncode == 0
    assert "tara" in proc.stdout


def test_js_bulgu_cikis_1(tmp_path):
    """JS tarafi de ayni sozlesmeyi paylasir."""
    kok = tmp_path / "projeler"
    js_repo(kok / "r", ["express"], kaynak="console.log(1);\n")
    proc = run_module_cli("tara", "--kok", str(kok), cwd=tmp_path)
    assert proc.returncode == BULGU_VAR
    assert "express" in proc.stdout