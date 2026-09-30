"""CLI sozlesmesi: `tara` ve `liste` gercek subprocess olarak calistirilir."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

from conftest import commit_file, git, make_bare_remote, make_repo, rows_for, run_module_cli


def test_tara_sifir_cikis_kodu(db_file: Path, tmp_path: Path):
    make_repo(tmp_path / "bir")
    proc = run_module_cli("tara", "--root", str(tmp_path), "--db", str(db_file))
    assert proc.returncode == 0, proc.stderr
    assert db_file.exists()


def test_tara_db_ye_yazar(db_file: Path, tmp_path: Path):
    repo = make_repo(tmp_path / "kayitli")
    proc = run_module_cli("tara", "--root", str(tmp_path), "--db", str(db_file))
    assert proc.returncode == 0, proc.stderr
    satirlar = rows_for(db_file)
    assert str(repo) in satirlar
    assert satirlar[str(repo)]["name"] == "kayitli"


def test_tara_ust_dizini_olusturur(tmp_path: Path):
    kok = tmp_path / "yeni-kok"
    kok.mkdir()
    make_repo(kok / "repo")
    db = tmp_path / "olmayan" / "a.db"
    proc = run_module_cli("tara", "--root", str(kok), "--db", str(db))
    assert proc.returncode == 0, proc.stderr
    assert db.exists()


def test_tara_birden_fazla_kok(db_file: Path, tmp_path: Path):
    a, b = tmp_path / "a", tmp_path / "b"
    make_repo(a / "birinci")
    make_repo(b / "ikinci")
    proc = run_module_cli(
        "tara", "--root", str(a), "--root", str(b), "--db", str(db_file)
    )
    assert proc.returncode == 0, proc.stderr
    adlar = sorted(r["name"] for r in rows_for(db_file).values())
    assert adlar == ["birinci", "ikinci"]


def test_tara_derinlik_secenegi(db_file: Path, tmp_path: Path):
    make_repo(tmp_path / "s1" / "s2" / "s3" / "repo")
    proc = run_module_cli(
        "tara", "--root", str(tmp_path), "--db", str(db_file), "--derinlik", "3"
    )
    assert proc.returncode == 0, proc.stderr
    assert rows_for(db_file) == {}
    proc = run_module_cli(
        "tara", "--root", str(tmp_path), "--db", str(db_file), "--derinlik", "5"
    )
    assert proc.returncode == 0, proc.stderr
    assert len(rows_for(db_file)) == 1


def test_tara_bos_kok_hata_vermez(db_file: Path, tmp_path: Path):
    proc = run_module_cli("tara", "--root", str(tmp_path), "--db", str(db_file))
    assert proc.returncode == 0, proc.stderr
    assert rows_for(db_file) == {}


def test_yeniden_tarama_cogaltmaz(db_file: Path, tmp_path: Path):
    repo = make_repo(tmp_path / "tekrar")
    for _ in range(3):
        proc = run_module_cli("tara", "--root", str(tmp_path), "--db", str(db_file))
        assert proc.returncode == 0, proc.stderr
    satirlar = rows_for(db_file)
    assert len(satirlar) == 1
    conn = sqlite3.connect(str(db_file))
    try:
        assert conn.execute("SELECT COUNT(*) FROM repos").fetchone()[0] == 1
    finally:
        conn.close()


def test_silinmis_repo_satiri_temizlenir(db_file: Path, tmp_path: Path):
    gidecek = make_repo(tmp_path / "gidecek")
    kalacak = make_repo(tmp_path / "kalacak")
    proc = run_module_cli("tara", "--root", str(tmp_path), "--db", str(db_file))
    assert proc.returncode == 0, proc.stderr
    import shutil

    shutil.rmtree(gidecek)
    proc = run_module_cli("tara", "--root", str(tmp_path), "--db", str(db_file))
    assert proc.returncode == 0, proc.stderr
    satirlar = rows_for(db_file)
    assert str(gidecek) not in satirlar
    assert str(kalacak) in satirlar


def test_liste_basar(db_file: Path, tmp_path: Path):
    make_repo(tmp_path / "birinci")
    make_repo(tmp_path / "ikinci")
    run_module_cli("tara", "--root", str(tmp_path), "--db", str(db_file))
    proc = run_module_cli("liste", "--db", str(db_file))
    assert proc.returncode == 0, proc.stderr
    assert "Ad" in proc.stdout and "Dal" in proc.stdout
    assert "Dirty" in proc.stdout and "Unpushed" in proc.stdout
    assert "birinci" in proc.stdout and "ikinci" in proc.stdout
    assert "Toplam: 2" in proc.stdout


def test_liste_sadece_yarim(db_file: Path, tmp_path: Path):
    temiz = make_repo(tmp_path / "temiz")
    kirli = make_repo(tmp_path / "kirli")
    (kirli / "README.md").write_text("# degisti\n", encoding="utf-8")
    run_module_cli("tara", "--root", str(tmp_path), "--db", str(db_file))
    proc = run_module_cli("liste", "--db", str(db_file), "--sadece-yarim")
    assert proc.returncode == 0, proc.stderr
    assert "kirli" in proc.stdout
    assert "temiz" not in proc.stdout
    assert str(temiz) not in proc.stdout


def test_liste_unpushed_de_gosterir(db_file: Path, tmp_path: Path):
    remote = make_bare_remote(tmp_path / "uzak.git")
    repo = make_repo(tmp_path / "gecikmis")
    git("remote", "add", "origin", str(remote), cwd=repo)
    git("push", "-q", "-u", "origin", "main", cwd=repo)
    commit_file(repo, "yeni.txt", "1", "ek commit")
    run_module_cli("tara", "--root", str(tmp_path / "gecikmis"), "--db", str(db_file))
    proc = run_module_cli("liste", "--db", str(db_file))
    assert "gecikmis" in proc.stdout
    assert rows_for(db_file)[str(repo)]["unpushed"] == 1


def test_liste_detached_gosterir(db_file: Path, tmp_path: Path):
    repo = make_repo(tmp_path / "ayrik")
    commit_file(repo, "a.txt", "1", "ikinci")
    ilk = git("rev-parse", "HEAD~1", cwd=repo).strip()
    git("checkout", "-q", ilk, cwd=repo)
    run_module_cli("tara", "--root", str(tmp_path), "--db", str(db_file))
    proc = run_module_cli("liste", "--db", str(db_file))
    assert "(detached)" in proc.stdout


def test_liste_bos_db_basar(db_file: Path):
    from atlas import db as db_mod

    db_mod.connect(db_file).close()  # bos DB var ama kayit yok
    proc = run_module_cli("liste", "--db", str(db_file))
    assert proc.returncode == 0, proc.stderr
    assert "Kayitli repo yok" in proc.stdout


def test_liste_var_olmayan_db_hatasi(db_file: Path, tmp_path: Path):
    proc = run_module_cli("liste", "--db", str(tmp_path / "yok.db"))
    assert proc.returncode == 1
    assert "Veritabani yok" in proc.stderr


def test_liste_bos_sonuc_yarim_suzgeci(db_file: Path, tmp_path: Path):
    make_repo(tmp_path / "temiz")
    run_module_cli("tara", "--root", str(tmp_path), "--db", str(db_file))
    proc = run_module_cli("liste", "--db", str(db_file), "--sadece-yarim")
    assert proc.returncode == 0
    assert "Yarim is olan repo yok" in proc.stdout


def test_atlas_db_ortam_degiskeni(tmp_path: Path):
    """ATLAS_DB verilmezse --db kullanilir; ortam degiskeni de gecerli olmali."""
    make_repo(tmp_path / "repo")
    db = tmp_path / "ortam.db"
    env = dict(os.environ)
    env["ATLAS_DB"] = str(db)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, "-m", "atlas", "tara", "--root", str(tmp_path)],
        capture_output=True, text=True, env=env,
    )
    assert proc.returncode == 0, proc.stderr
    assert db.exists()


def test_yardim_ve_surum(db_file: Path):
    assert run_module_cli("--help").returncode == 0
    surum = run_module_cli("--version")
    assert surum.returncode == 0
    assert "atlas" in surum.stdout


def test_komut_zorunlu():
    proc = run_module_cli()
    assert proc.returncode != 0


def test_tara_uyari_ama_sifir_cikis(db_file: Path, tmp_path: Path):
    """Bozuk repo olsa bile tarama 0 ile biter ve digerleri yazilir."""
    bozuk = tmp_path / "bozuk"
    bozuk.mkdir()
    (bozuk / ".git").mkdir()
    (bozuk / ".git" / "HEAD").write_text("gecersiz\n", encoding="utf-8")
    iyi = make_repo(tmp_path / "iyi")
    proc = run_module_cli("tara", "--root", str(tmp_path), "--db", str(db_file))
    assert proc.returncode == 0, proc.stderr
    assert str(iyi) in rows_for(db_file)
    assert "atlandi" in proc.stderr
