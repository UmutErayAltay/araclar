"""`atlas sizinti` ve `atlas bulgular` sozlesmesi + DB katmani (Dalga B)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from atlas import db as db_mod
from conftest import commit_file, git, make_repo, run_module_cli

FAKE_SK = "sk-" + "a1" * 15


def _sizinti(*ek: str) -> list:
    return run_module_cli("sizinti", *ek)


def test_sizinti_sifir_cikis_kodu(db_file: Path, tmp_path: Path):
    """Bulgu olmasi HATA DEGILDIR: cikis kodu 0."""
    repo = make_repo(tmp_path / "r")
    commit_file(repo, "s.txt", f"anahtar: {FAKE_SK}", "ekle")
    proc = _sizinti("--root", str(tmp_path), "--db", str(db_file))
    assert proc.returncode == 0, proc.stderr


def test_sizinti_db_ye_yazar(db_file: Path, tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    commit_file(repo, "s.txt", f"anahtar: {FAKE_SK}", "ekle")
    _sizinti("--root", str(tmp_path), "--db", str(db_file))
    conn = db_mod.connect(db_file)
    try:
        satirlar = db_mod.list_findings(conn, repo=str(repo))
        assert satirlar
        assert any(r["kind"] == "api-anahtari" for r in satirlar)
    finally:
        conn.close()


def test_sizinti_ozet_basar_ve_sayi_verir(db_file: Path, tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    commit_file(repo, "s.txt", f"anahtar: {FAKE_SK}", "ekle")
    proc = _sizinti("--root", str(tmp_path), "--db", str(db_file))
    assert "Taranan repo: 1" in proc.stdout
    assert "API anahtari" in proc.stdout  # Turkce tur basligi
    assert "yuksek" in proc.stdout  # onem bazinda sayi


def test_bulgular_tablosu_turkce_basliklar(db_file: Path, tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    commit_file(repo, "s.txt", f"anahtar: {FAKE_SK}", "ekle")
    _sizinti("--root", str(tmp_path), "--db", str(db_file))
    proc = run_module_cli("bulgular", "--db", str(db_file))
    assert proc.returncode == 0, proc.stderr
    for baslik in ("Repo", "Onem", "Tur", "Dosya", "Commit", "Snippet"):
        assert baslik in proc.stdout


def test_bulgular_bos_durum(db_file: Path, tmp_path: Path):
    make_repo(tmp_path / "r")
    _sizinti("--root", str(tmp_path), "--db", str(db_file))
    proc = run_module_cli("bulgular", "--db", str(db_file))
    assert proc.returncode == 0, proc.stderr
    assert "Bulgu yok" in proc.stdout


def test_bulgular_var_olmayan_db_hatasi(db_file: Path, tmp_path: Path):
    proc = run_module_cli("bulgular", "--db", str(tmp_path / "yok.db"))
    assert proc.returncode == 1
    assert "Veritabani yok" in proc.stderr


def test_bulgular_siddet_suzgeci(db_file: Path, tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    commit_file(repo, "s.txt", f"anahtar: {FAKE_SK}\n", "ekle")
    commit_file(repo, "y.txt", "yol: /Users/umut/proje", "ekle")
    _sizinti("--root", str(tmp_path), "--db", str(db_file))
    yuksek = run_module_cli("bulgular", "--db", str(db_file), "--siddet", "yuksek")
    assert "API anahtari" in yuksek.stdout
    assert "Kisisel yol" not in yuksek.stdout
    orta = run_module_cli("bulgular", "--db", str(db_file), "--siddet", "orta")
    assert "Kisisel yol" in orta.stdout
    assert "API anahtari" not in orta.stdout


def test_bulgular_tur_suzgeci(db_file: Path, tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    commit_file(repo, "s.txt", f"anahtar: {FAKE_SK}\n", "ekle")
    commit_file(repo, "y.txt", "yol: /Users/umut/proje", "ekle")
    _sizinti("--root", str(tmp_path), "--db", str(db_file))
    proc = run_module_cli("bulgular", "--db", str(db_file), "--tur", "kisisel-yol")
    assert "Kisisel yol" in proc.stdout
    assert "API anahtari" not in proc.stdout


def test_bulgular_gecmis_bulgusu_commit_gosterir(db_file: Path, tmp_path: Path):
    """Yalnizca gecmiste olan sir: bulgunun `commit` alani kisa hash DOLU."""
    repo = make_repo(tmp_path / "r")
    commit_file(repo, "gizli.txt", f"eski: {FAKE_SK}", "sir ekle")
    hash_ = git("rev-parse", "HEAD", cwd=repo).strip()[:7]
    git("rm", "-q", "gizli.txt", cwd=repo)
    git("commit", "-q", "-m", "sir sil", cwd=repo)
    _sizinti("--root", str(tmp_path), "--db", str(db_file))
    conn = db_mod.connect(db_file)
    try:
        gecmis = [r for r in db_mod.list_findings(conn, repo=str(repo)) if r["commit"] == hash_]
    finally:
        conn.close()
    assert gecmis, "gecmis bulgusu (commit hash'li) bulunamadi"
    proc = run_module_cli("bulgular", "--db", str(db_file))
    assert hash_ in proc.stdout


# --------------------------------------------------------------------------
# Yeniden tarama: repo basina bulgu yenileme
# --------------------------------------------------------------------------

def test_yeniden_tarama_cogaltmaz(db_file: Path, tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    commit_file(repo, "s.txt", f"anahtar: {FAKE_SK}", "ekle")
    for _ in range(3):
        _sizinti("--root", str(tmp_path), "--db", str(db_file))
    conn = sqlite3.connect(str(db_file))
    try:
        n = conn.execute("SELECT COUNT(*) FROM findings WHERE repo = ?", (str(repo),)).fetchone()[0]
    finally:
        conn.close()
    once = db_mod.connect(db_file)
    try:
        once_n = len(db_mod.list_findings(once, repo=str(repo)))
    finally:
        once.close()
    assert n == once_n, "yeniden tarama bulgulari cogaltti"


def test_yeniden_tarama_eski_bulgulari_siler(db_file: Path, tmp_path: Path):
    """SIR SILINDI: yeniden tarama eski bulguyu KALDIRIR."""
    repo = make_repo(tmp_path / "r")
    commit_file(repo, "s.txt", f"anahtar: {FAKE_SK}", "ekle")
    _sizinti("--root", str(tmp_path), "--db", str(db_file))
    conn = db_mod.connect(db_file)
    try:
        assert any(r["kind"] == "api-anahtari" for r in db_mod.list_findings(conn, repo=str(repo)))
    finally:
        conn.close()
    # Sir dosyasindan kaldir ve yeni commit at.
    git("rm", "-q", "s.txt", cwd=repo)
    git("commit", "-q", "-m", "sir sil", cwd=repo)
    _sizinti("--root", str(tmp_path), "--db", str(db_file))
    conn = db_mod.connect(db_file)
    try:
        kalan = [r for r in db_mod.list_findings(conn, repo=str(repo)) if r["commit"] is None]
    finally:
        conn.close()
    assert not kalan, "calisma agacindaki eski bulgu silinmedi"


def test_bir_repo_yenilenir_digeri_kalir(db_file: Path, tmp_path: Path):
    """Yalnizca TEKRAR TARANAN repo'nun bulgulari silinir; digeri kalir."""
    a = make_repo(tmp_path / "a")
    b = make_repo(tmp_path / "b")
    commit_file(a, "s.txt", f"anahtar: {FAKE_SK}", "ekle")
    commit_file(b, "s.txt", f"anahtar: {FAKE_SK}", "ekle")
    _sizinti("--root", str(tmp_path), "--db", str(db_file))
    # b'deki siri kaldir, a'ya dokunma; sonra sadece a'yi tara.
    git("rm", "-q", "s.txt", cwd=b)
    git("commit", "-q", "-m", "sir sil", cwd=b)
    proc = run_module_cli("sizinti", "--root", str(a), "--db", str(db_file))
    assert proc.returncode == 0, proc.stderr
    conn = db_mod.connect(db_file)
    try:
        a_bulgu = [r for r in db_mod.list_findings(conn, repo=str(a)) if r["commit"] is None]
        b_bulgu = [r for r in db_mod.list_findings(conn, repo=str(b)) if r["commit"] is None]
    finally:
        conn.close()
    assert a_bulgu, "a'nin bulgusu silinmemeliydi"
    # b bu turda TARAMADIGI icin eski bulgusu DB'de durur (digeri degilmis gibi
    # silinmez; yalnizca o repo taraninca yenilenir).
    assert b_bulgu, "b taranmadigi icin bulgusu korunmali"


# --------------------------------------------------------------------------
# Sadece tek repo (--repo)
# --------------------------------------------------------------------------

def test_repo_secenegi_tek_repo_tarar(db_file: Path, tmp_path: Path):
    a = make_repo(tmp_path / "a")
    b = make_repo(tmp_path / "b")
    commit_file(a, "s.txt", f"anahtar: {FAKE_SK}", "ekle")
    proc = run_module_cli("sizinti", "--root", str(tmp_path), "--db", str(db_file), "--repo", "a")
    assert proc.returncode == 0, proc.stderr
    conn = db_mod.connect(db_file)
    try:
        assert db_mod.list_findings(conn, repo=str(a))
        assert not db_mod.list_findings(conn, repo=str(b))
    finally:
        conn.close()


def test_repo_secenegi_yol_ile_calisir(db_file: Path, tmp_path: Path):
    a = make_repo(tmp_path / "a")
    commit_file(a, "s.txt", f"anahtar: {FAKE_SK}", "ekle")
    proc = run_module_cli("sizinti", "--db", str(db_file), "--repo", str(a))
    assert proc.returncode == 0, proc.stderr
    conn = db_mod.connect(db_file)
    try:
        assert db_mod.list_findings(conn, repo=str(a))
    finally:
        conn.close()


def test_repo_secenegi_bulunamazsa_hata(db_file: Path, tmp_path: Path):
    proc = run_module_cli("sizinti", "--db", str(db_file), "--repo", "olmayan-repo-xyz")
    assert proc.returncode == 1
    assert "Repo bulunamadi" in proc.stderr


def test_bozuk_repo_taramayi_cozertmez(db_file: Path, tmp_path: Path):
    """Bozuk repo: atlanir, digerleri yazilir, cikis kodu 0."""
    bozuk = tmp_path / "bozuk"
    bozuk.mkdir()
    (bozuk / ".git").mkdir()
    (bozuk / ".git" / "HEAD").write_text("bu bir HEAD degil\n", encoding="utf-8")
    iyi = make_repo(tmp_path / "iyi")
    commit_file(iyi, "s.txt", f"anahtar: {FAKE_SK}", "ekle")
    proc = _sizinti("--root", str(tmp_path), "--db", str(db_file))
    assert proc.returncode == 0, proc.stderr
    conn = db_mod.connect(db_file)
    try:
        assert db_mod.list_findings(conn, repo=str(iyi))
    finally:
        conn.close()


def test_bos_repo_taramayi_cozertmez(db_file: Path, tmp_path: Path):
    make_repo(tmp_path / "bos", commit=False)
    proc = _sizinti("--root", str(tmp_path), "--db", str(db_file))
    assert proc.returncode == 0, proc.stderr
    assert "Bulgu: 0" in proc.stdout


def test_turkce_dosya_adi_taranir(db_file: Path, tmp_path: Path):
    """Turkce karakterli dosya adi: taranir, bulgu cikar, DB'ye yazilir."""
    repo = make_repo(tmp_path / "r")
    commit_file(repo, "kullanıcı/gizli ayarları.txt", f"anahtar: {FAKE_SK}", "ekle")
    proc = _sizinti("--root", str(tmp_path), "--db", str(db_file))
    assert proc.returncode == 0, proc.stderr
    conn = db_mod.connect(db_file)
    try:
        satirlar = db_mod.list_findings(conn, repo=str(repo))
    finally:
        conn.close()
    assert any("gizli" in (r["file"] or "") for r in satirlar)


# --------------------------------------------------------------------------
# DB katmani dogrudan
# --------------------------------------------------------------------------

def test_replace_findings_tek_transaction(db_file: Path):
    conn = db_mod.connect(db_file)
    try:
        eklendi = db_mod.replace_findings(
            conn, "/a/r", [{"kind": "api-anahtari", "severity": "yuksek", "file": "s.txt",
                            "line": 1, "commit": None, "snippet_redacted": "[maskeli:api-anahtari]"}]
        )
        assert eklendi == 1
        assert db_mod.count_findings(conn) == 1
    finally:
        conn.close()


def test_replace_findings_bos_liste_siler(db_file: Path):
    conn = db_mod.connect(db_file)
    try:
        db_mod.replace_findings(conn, "/a/r", [{"kind": "e-posta", "severity": "dusuk",
                                                "file": "s.txt", "line": 1, "commit": None,
                                                "snippet_redacted": "<e-posta>"}])
        assert db_mod.count_findings(conn) == 1
        db_mod.replace_findings(conn, "/a/r", [])  # sir silindi -> bulgu kalir mi? hayir
        assert not db_mod.list_findings(conn, repo="/a/r")
    finally:
        conn.close()


def test_findings_ozet_gruplar(db_file: Path):
    conn = db_mod.connect(db_file)
    try:
        db_mod.replace_findings(
            conn, "/a/r",
            [{"kind": "api-anahtari", "severity": "yuksek", "file": "a", "line": 1,
              "commit": None, "snippet_redacted": "x"}] * 3
            + [{"kind": "e-posta", "severity": "dusuk", "file": "b", "line": 1,
                "commit": None, "snippet_redacted": "y"}],
        )
        ozet = db_mod.findings_ozet(conn)
        assert {(r["kind"], r["adet"]) for r in ozet} == {("api-anahtari", 3), ("e-posta", 1)}
    finally:
        conn.close()
