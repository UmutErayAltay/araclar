"""CLI sozlesmesi: `python -m iddia` GERCEKTEN subprocess olarak calistirilir.

Cikis kodlari: 0 bulgu yok, 1 bulgu var, 2 kullanim/kesif hatasi.
Tum testler gecici dizindeki sahte repolarda calisir; kullanici dizini okunmaz.
"""

from __future__ import annotations

import json
from pathlib import Path

from conftest import argparse_kaynak, py_test_dosyasi, run_module_cli, sahte_repo, tree_hash

KULLANIM_HATASI = 2
BULGU_VAR = 1


def _uyumlu_repo(tmp_path: Path) -> Path:
    """Iddialari koda uyan temiz repo (bulgu YOK olmali)."""
    kok = tmp_path / "projeler"
    repo = sahte_repo(kok / "r")
    py_test_dosyasi(repo, "tests/test_a.py", 10)
    argparse_kaynak(repo, "cli.py", 3, bayraklar=["--uygula"])
    (repo / "app").mkdir()
    (repo / "app" / "ozel.py").write_text("x\n", encoding="utf-8")
    (repo / "README.md").write_text(
        "10 test var. `app/ozel.py` calisir. `--uygula` ile. 3 komut sunuyor.\n",
        encoding="utf-8",
    )
    return kok


def _bulungu_repo(tmp_path: Path) -> Path:
    """Bulgulu repo (cikis 1 olmali)."""
    kok = tmp_path / "projeler"
    repo = sahte_repo(kok / "r")
    py_test_dosyasi(repo, "tests/test_a.py", 10)
    (repo / "README.md").write_text("1000 test var.\n", encoding="utf-8")
    return kok


# --------------------------------------------------------------------------
# cikis kodlari
# --------------------------------------------------------------------------


def test_bulgu_yoksa_cikis_0(tmp_path):
    """Uyumlu repo: cikis 0 ve 'bulgu yok' yazilir."""
    kok = _uyumlu_repo(tmp_path)
    proc = run_module_cli("tara", "--kok", str(kok), cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert "bulgu yok" in proc.stdout


def test_bulgu_varsa_cikis_1(tmp_path):
    """Sapmali iddia: cikis 1 ve bulgu satiri basilir."""
    kok = _bulungu_repo(tmp_path)
    proc = run_module_cli("tara", "--kok", str(kok), cwd=tmp_path)
    assert proc.returncode == BULGU_VAR, proc.stderr
    assert "1000 test" in proc.stdout


def test_yok_kok_hata_ve_cikis_2(tmp_path):
    """Olmayan yol: stderr'a `Hata:` yazilir, traceback YOK."""
    proc = run_module_cli("tara", "--kok", str(tmp_path / "yok"), cwd=tmp_path)
    assert proc.returncode == KULLANIM_HATASI
    assert proc.stderr.startswith("Hata:")
    assert "Traceback" not in proc.stderr


def test_repo_bulunamazsa_cikis_2(tmp_path):
    """Kok var ama icinde .git yok: cikis 2 (bulgu 0 DEGIL)."""
    kok = tmp_path / "bos"
    kok.mkdir()
    proc = run_module_cli("tara", "--kok", str(kok), cwd=tmp_path)
    assert proc.returncode == KULLANIM_HATASI
    assert "Hata:" in proc.stderr


def test_kok_verilmezse_cikis_2(tmp_path):
    """--kok zorunludur: argparse hatasi, traceback degil."""
    proc = run_module_cli("tara", cwd=tmp_path)
    assert proc.returncode != 0
    assert "Traceback" not in proc.stderr


def test_bilinmeyen_komut_cikis_2(tmp_path):
    """Alt komut yoksa argparse cikis 2 verir."""
    assert run_module_cli("yok-boyle-bir-komut", cwd=tmp_path).returncode == KULLANIM_HATASI


# --------------------------------------------------------------------------
# cikti bicimi
# --------------------------------------------------------------------------


def test_json_gecerli_json_ve_turler(tmp_path):
    """`--json` gecerli JSON yazar (ensure_ascii=False, tablo degil)."""
    kok = _bulungu_repo(tmp_path)
    proc = run_module_cli("tara", "--kok", str(kok), "--json", cwd=tmp_path)
    assert proc.returncode == BULGU_VAR, proc.stderr
    veri = json.loads(proc.stdout)
    assert veri["surum"] == 1
    assert veri["bulgu_sayisi"] == 1
    assert veri["tur_sayimi"] == {"test-sayisi": 1}
    b = veri["bulgular"][0]
    assert set(b) == {"repo", "readme", "tur", "iddia", "gercek"}
    assert b["iddia"] == "1000 test"
    assert b["readme"] == "README.md:1"


def test_json_bulunmazsa_gecerli_json(tmp_path):
    """Bulgu yokken de `--json` gecerli JSON verir."""
    kok = _uyumlu_repo(tmp_path)
    proc = run_module_cli("tara", "--kok", str(kok), "--json", cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    veri = json.loads(proc.stdout)
    assert veri["bulgu_sayisi"] == 0
    assert veri["bulgular"] == []


def test_json_yazma_yapmaz(tmp_path):
    """Arac rapor dosyasi YAZMAZ (salt-okunur; HOME bile dokunulmaz)."""
    ev = tmp_path / "ev"
    ev.mkdir()
    kok = _bulungu_repo(tmp_path)
    run_module_cli("tara", "--kok", str(kok), "--json", cwd=tmp_path, env_ek={"HOME": str(ev)})
    assert list(ev.iterdir()) == []


# --------------------------------------------------------------------------
# tarama kurallari (alt surec uzerinden)
# --------------------------------------------------------------------------


def test_birden_fazla_kok_birlikte_taranir(tmp_path):
    """Iki ayri kok verildiginde ikisinin bulgulari birlikte raporlanir.

    Her repoda test dosyasi OLMAK ZORUNDA: test dosyasi yoksa test-sayisi turu
    emin olamadigi icin bulgu uretilmez (yanlis pozitiften kacinma kurali).
    """
    kok1 = tmp_path / "a"
    kok2 = tmp_path / "b"
    r1 = sahte_repo(kok1 / "r1")
    py_test_dosyasi(r1, "tests/test_a.py", 10)
    (r1 / "README.md").write_text("1000 test\n", encoding="utf-8")
    r2 = sahte_repo(kok2 / "r2")
    py_test_dosyasi(r2, "tests/test_b.py", 10)
    (r2 / "README.md").write_text("9000 tests\n", encoding="utf-8")
    proc = run_module_cli("tara", "--kok", str(kok1), "--kok", str(kok2), cwd=tmp_path)
    assert proc.returncode == BULGU_VAR, proc.stderr
    veri = json.loads(run_module_cli("tara", "--kok", str(kok1), "--kok", str(kok2),
                                     "--json", cwd=tmp_path).stdout)
    assert veri["repo_sayisi"] == 2
    assert veri["bulgu_sayisi"] == 2


def test_atlanan_dizinler_taranmaz(tmp_path):
    """node_modules altindaki README'ler taranmaz (kural: dizine girilmez)."""
    kok = tmp_path / "projeler"
    repo = sahte_repo(kok / "r")
    py_test_dosyasi(repo, "tests/test_a.py", 2)
    sahte_repo(kok / "r" / "node_modules" / "paket", {"README.md": "1000 tests\n"})
    proc = run_module_cli("tara", "--kok", str(kok), "--json", cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["bulgu_sayisi"] == 0


def test_tarama_dosya_sistemini_degistirmez(tmp_path):
    """Tarma sonrasi repo agaci BIT BIT ayni (salt-okunurluk kaniti)."""
    kok = _bulungu_repo(tmp_path)
    repo = kok / "r"
    once = tree_hash(repo)
    proc = run_module_cli("tara", "--kok", str(kok), cwd=tmp_path)
    assert proc.returncode == BULGU_VAR
    assert tree_hash(repo) == once


def test_uygula_bayragi_yoktur(tmp_path):
    """Salt-okunur arac: `--uygula` kabul edilmez (yazma yolu YOK)."""
    proc = run_module_cli("tara", "--kok", str(tmp_path), "--uygula", cwd=tmp_path)
    assert proc.returncode == KULLANIM_HATASI
    assert "--uygula" in proc.stderr