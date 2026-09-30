"""Repo duzeyi davranis: kapsam, atlamalar, sure siniri, salt-okunurluk."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from atlas import leaks
from conftest import commit_file, git, make_repo, run_module_cli

FAKE_SK = "sk-" + "a1" * 15


def test_sadece_izlenen_dosyalar_taranir(tmp_path: Path):
    """Izlenmeyen dosyadaki sir KAPSAM DIŞI (git ls-files disi)."""
    repo = make_repo(tmp_path / "r")
    (repo / "izlenmeyen.txt").write_text(f"{FAKE_SK}\n", encoding="utf-8")
    b = leaks.tara_calisma_agaci(repo)
    assert not [x for x in b if x["kind"] == "api-anahtari"]


def test_ignored_dosya_taranmaz(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    (repo / ".gitignore").write_text("gizli/\n*.log\n", encoding="utf-8")
    (repo / "gizli").mkdir()
    (repo / "gizli" / "sir.txt").write_text(f"{FAKE_SK}\n", encoding="utf-8")
    (repo / "kayit.log").write_text(f"{FAKE_SK}\n", encoding="utf-8")
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "ignore", cwd=repo)
    b = leaks.tara_calisma_agaci(repo)
    assert not [x for x in b if x["kind"] == "api-anahtari"]


def test_env_icerigi_okunmaz_sadece_yol(tmp_path: Path):
    """`.env` IZLENIYORSA bulgu cikar; ama icerigi hicbir yere girmez."""
    repo = make_repo(tmp_path / "r")
    (repo / ".env").write_text(f"GIZLI={FAKE_SK}\n", encoding="utf-8")
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "env", cwd=repo)
    b = leaks.tara_calisma_agaci(repo)
    env = [x for x in b if x["kind"] == "env-izlenen"]
    assert env
    assert env[0]["snippet_redacted"] is None
    # `.env` icerigi API anahtari olarak da raporlanMAMALI (icerik okunmaz).
    assert not [x for x in b if x["kind"] == "api-anahtari" and x["file"] == ".env"]


def test_env_dosyasi_izlenmiyorsa_bulgu_yok(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    (repo / ".env").write_text("X=1\n", encoding="utf-8")  # git add YOK
    assert not [x for x in leaks.tara_calisma_agaci(repo) if x["kind"] == "env-izlenen"]


def test_bos_repo_gecmis_taramasi_cozertmez(tmp_path: Path):
    """Hic commit yok: `git log` hata verir ama taramayi COZERTMEZ."""
    repo = make_repo(tmp_path / "bos", commit=False)
    tarama = leaks.tara_repo(repo, commit_sayisi=10)
    assert isinstance(tarama.bulgular, list)


def test_ayrik_head_gecmis_taramasi(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    commit_file(repo, "a.txt", f"anahtar: {FAKE_SK}", "ekle")
    ilk = git("rev-parse", "HEAD~0", cwd=repo).strip()
    git("checkout", "-q", ilk, cwd=repo)
    tarama = leaks.tara_repo(repo, commit_sayisi=10)
    assert isinstance(tarama.bulgular, list)


def test_okunamayan_dosya_taramayi_cozertmez(tmp_path: Path):
    """chmod 000 dosya: sessizce atlanir, digerleri taranir."""
    if os.geteuid() == 0:
        pytest.skip("root: chmod 000 etkisiz")
    repo = make_repo(tmp_path / "r")
    (repo / "kilitli.txt").write_text(f"{FAKE_SK}\n", encoding="utf-8")
    kilitli = repo / "kilitli.txt"
    os.chmod(kilitli, 0o000)
    try:
        b = leaks.tara_calisma_agaci(repo)  # hata vermemeli
        assert isinstance(b, list)
    finally:
        os.chmod(kilitli, stat.S_IRUSR | stat.S_IWUSR)


def test_sembolik_link_dosya_atlanir(tmp_path: Path):
    """Sembolik link (disariyi gosteren) takip edilmez."""
    repo = make_repo(tmp_path / "r")
    hedef = tmp_path / "disi.txt"
    hedef.write_text(f"{FAKE_SK}\n", encoding="utf-8")
    try:
        os.symlink(hedef, repo / "baglanti.txt")
    except (OSError, NotImplementedError):  # pragma: no cover
        pytest.skip("sembolik link olusturulamadi")
    b = leaks.tara_calisma_agaci(repo)
    assert not [x for x in b if x["kind"] == "api-anahtari" and x["file"] == "baglanti.txt"]


# --------------------------------------------------------------------------
# Sure siniri / kismi tarama
# --------------------------------------------------------------------------

def test_kismi_tarama_uyarisi_uretir(monkeypatch, tmp_path: Path):
    """Sure usteligi asilirsa 'kismi tarama' uyarisi cikar (HATA DEGIL)."""
    repo = make_repo(tmp_path / "r")
    commit_file(repo, "s.txt", f"anahtar: {FAKE_SK}", "ekle")
    monkeypatch.setattr(leaks, "REPO_SURE_UST_SINIR", -1.0)  # her zaman asilir
    tarama = leaks.tara_repo(repo, commit_sayisi=10)
    assert any("kismi tarama" in u for u in tarama.uyarilar)
    assert tarama.bulgular  # bulgular KORUNUR


def test_tara_roots_hatali_repo_digerlerini_cozertmez(tmp_path: Path):
    bozuk = tmp_path / "bozuk"
    bozuk.mkdir()
    (bozuk / ".git").mkdir()
    (bozuk / ".git" / "HEAD").write_text("gecersiz\n", encoding="utf-8")
    iyi = make_repo(tmp_path / "iyi")
    commit_file(iyi, "s.txt", f"anahtar: {FAKE_SK}", "ekle")
    sonuc, hatalar = leaks.tara_roots([tmp_path], commit_sayisi=10)
    assert str(iyi) in sonuc
    assert sonuc[str(iyi)]  # iyi repo bulgu uretti
    assert hatalar  # bozuk repo hata listesinde


def test_tara_roots_tum_kokleri_kapsar(tmp_path: Path):
    a = make_repo(tmp_path / "a" / "r1")
    b = make_repo(tmp_path / "b" / "r2")
    sonuc, _ = leaks.tara_roots([tmp_path / "a", tmp_path / "b"], commit_sayisi=10)
    assert str(a) in sonuc and str(b) in sonuc


# --------------------------------------------------------------------------
# Uctan uca CLI: hata durumlari
# --------------------------------------------------------------------------

def test_sizinti_yarim_is_durumunda_calisir(db_file: Path, tmp_path: Path):
    """Kirli repo: taramayi cokertmez."""
    repo = make_repo(tmp_path / "r")
    commit_file(repo, "s.txt", f"anahtar: {FAKE_SK}", "ekle")
    (repo / "s.txt").write_text(f"degisti: {FAKE_SK}\n", encoding="utf-8")  # kirli
    proc = run_module_cli("sizinti", "--root", str(tmp_path), "--db", str(db_file))
    assert proc.returncode == 0, proc.stderr


def test_sizinti_gecmis_sifir(db_file: Path, tmp_path: Path):
    """--gecmis 0: gecmis taramasi yapilmaz, yalnizca calisma agaci."""
    repo = make_repo(tmp_path / "r")
    commit_file(repo, "gizli.txt", f"eski: {FAKE_SK}", "sir")
    hash_ = git("rev-parse", "HEAD", cwd=repo).strip()[:7]
    git("rm", "-q", "gizli.txt", cwd=repo)
    git("commit", "-q", "-m", "sil", cwd=repo)
    proc = run_module_cli("sizinti", "--root", str(tmp_path), "--db", str(db_file),
                          "--gecmis", "0")
    assert proc.returncode == 0, proc.stderr
    from atlas import db as db_mod

    conn = db_mod.connect(db_file)
    try:
        satirlar = db_mod.list_findings(conn, repo=str(repo))
    finally:
        conn.close()
    # Gecmis taranmadigi icin commit'li bulgu OLMAMALI.
    assert not [r for r in satirlar if r["commit"] == hash_]


def test_sizinti_ust_dizini_olusturur(tmp_path: Path):
    make_repo(tmp_path / "r")
    db = tmp_path / "yeni" / "a.db"
    proc = run_module_cli("sizinti", "--root", str(tmp_path), "--db", str(db))
    assert proc.returncode == 0, proc.stderr
    assert db.exists()


def test_sizinti_izlenmeyen_db_ortam_degiskeni(tmp_path: Path):
    import os as _os
    import subprocess
    import sys

    from conftest import REPO_ROOT

    make_repo(tmp_path / "r")
    db = tmp_path / "ortam.db"
    env = dict(_os.environ)
    env["ATLAS_DB"] = str(db)
    env["PYTHONPATH"] = str(REPO_ROOT)
    proc = subprocess.run(
        [sys.executable, "-m", "atlas", "sizinti", "--root", str(tmp_path)],
        capture_output=True, text=True, env=env,
    )
    assert proc.returncode == 0, proc.stderr
    assert db.exists()


def test_sizinti_yardim_gosterir():
    proc = run_module_cli("sizinti", "--help")
    assert proc.returncode == 0
    assert "--gecmis" in proc.stdout
    assert "--root" in proc.stdout
    bulgular = run_module_cli("bulgular", "--help")
    assert "--siddet" in bulgular.stdout
    assert "--tur" in bulgular.stdout


def test_ana_komut_listesinde_var():
    proc = run_module_cli("--help")
    assert "sizinti" in proc.stdout
    assert "bulgular" in proc.stdout
