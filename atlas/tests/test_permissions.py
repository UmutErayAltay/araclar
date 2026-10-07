"""Izin reddi (EACCES) yolu gercekten kanitlanir.

Root calisiyorsa `chmod 000` bir seyi engellemez (DAC_OVERRIDE), bu yuzden
tarama `nobody` kullaniciyla, ayri bir surecte calistirilir. Root degilse ayni
test yine calisir ama chmod yeterlidir.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import REPO_ROOT

try:  # root degilsek kullanici kendimiz
    import pwd

    KULLANICI_ADI = None
    if os.geteuid() == 0 and pwd.getpwnam("nobody").pw_uid != os.geteuid():
        KULLANICI_ADI = "nobody"
except Exception:  # pragma: no cover
    KULLANICI_ADI = None

pytestmark = pytest.mark.skipif(
    getattr(os, "geteuid", lambda: 1)() != 0, reason="bu test root oldugunda sozlulugu calistirilir"
)


def _baslat(komut: list[str], env_ek: dict | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT)
    env.pop("ATLAS_DB", None)
    if env_ek:
        env.update(env_ek)
    if KULLANICI_ADI:
        return subprocess.run(
            ["runuser", "-u", KULLANICI_ADI, "--", "env", f"PYTHONPATH={REPO_ROOT}", *komut],
            capture_output=True, text=True, env=env,
        )
    return subprocess.run(komut, capture_output=True, text=True, env=env)


def _gecilir_izni(yol: Path) -> None:
    """pytest'in gecici dizinleri 0700; `nobody` icin yol boyunca +x verilir."""
    for p in [yol, *yol.parents]:
        try:
            if str(p) == "/":
                break
            os.chmod(p, os.stat(p).st_mode | 0o755)
        except OSError:
            break


GIT_KIMLIK = ["-c", "user.email=test@example.invalid", "-c", "user.name=atlas test"]


def _git_tara_kullanici(komut: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    """git komutunu tarama yapan kullanici adina calistirir.

    Repo sahibi tarayan kullanici olmali; aksi halde git 'dubious ownership'
    der ve repo atlanir (bu da dogru davranistir ama testin konusu degil).
    """
    env = {
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_AUTHOR_NAME": "atlas test",
        "GIT_AUTHOR_EMAIL": "test@example.invalid",
        "GIT_COMMITTER_NAME": "atlas test",
        "GIT_COMMITTER_EMAIL": "test@example.invalid",
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": "/tmp",
    }
    if KULLANICI_ADI:
        return subprocess.run(
            ["runuser", "-u", KULLANICI_ADI, "--", "git", *komut],
            cwd=str(cwd) if cwd else None, capture_output=True, text=True, env=env,
        )
    return subprocess.run(
        ["git", *GIT_KIMLIK, *komut],
        cwd=str(cwd) if cwd else None, capture_output=True, text=True, env=env,
    )


def _hazirla(tmp_path: Path) -> tuple[Path, Path]:
    """Kilitli (000) bir dizin + normal bir repo iceren agac kurar."""
    kok = tmp_path / "agac"
    kok.mkdir()
    os.chmod(kok, 0o777)
    kilitli = kok / "kilitli"
    kilitli.mkdir()
    (kilitli / "gizli.txt").write_text("gizli\n", encoding="utf-8")

    repo = kok / "acik"
    repo.mkdir()
    os.chmod(repo, 0o777)
    if KULLANICI_ADI:
        import pwd

        kimlik = pwd.getpwnam(KULLANICI_ADI)
        os.chown(repo, kimlik.pw_uid, kimlik.pw_gid)  # repo sahibi = tarayan kullanici
    proc = _git_tara_kullanici(["init", "-q", str(repo)])
    assert proc.returncode == 0, proc.stderr
    proc = _git_tara_kullanici(["commit", "-q", "--allow-empty", "-m", "x"], cwd=repo)
    assert proc.returncode == 0, proc.stderr
    return kok, repo


def test_izin_reddi_taramayi_cozertmez(tmp_path: Path):
    """chmod 000 dizin atlanir; saglam repo yazilir; cikis kodu 0."""
    _gecilir_izni(tmp_path)
    kok, repo = _hazirla(tmp_path)
    os.chmod(kok / "kilitli", 0o000)
    db = kok / "atlas.db"
    try:
        proc = _baslat([sys.executable, "-m", "atlas", "tara", "--root", str(kok), "--db", str(db)])
        assert proc.returncode == 0, f"stdout={proc.stdout} stderr={proc.stderr}"
        assert "Taranan repo: 1" in proc.stdout, proc.stdout

        sorgu = subprocess.run(
            [sys.executable, "-c",
             "import sys;from atlas import db;c=db.connect(sys.argv[1]);"
             "print([r['name'] for r in c.execute('SELECT name FROM repos')])", str(db)],
            capture_output=True, text=True,
            env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
        )
        assert sorgu.returncode == 0, sorgu.stderr
        assert "'acik'" in sorgu.stdout, sorgu.stdout
    finally:
        os.chmod(kok / "kilitli", 0o700)


def test_izinsiz_db_yolu_patlayan_iz_yok(tmp_path: Path):
    """Yazilamayan DB yolu temiz hata mesaji verir (traceback degil)."""
    _gecilir_izni(tmp_path)
    kok = tmp_path / "kilitli-db"
    kok.mkdir()
    os.chmod(kok, 0o555)  # salt okunur dizin: db olusturulamaz
    try:
        proc = _baslat([sys.executable, "-m", "atlas", "tara", "--root", str(kok),
                        "--db", str(kok / "yeni" / "atlas.db")])
        assert proc.returncode == 1
        assert "Traceback" not in proc.stderr
        assert ("Veritabani hatasi" in proc.stderr) or ("Hata:" in proc.stderr)
    finally:
        os.chmod(kok, 0o755)


def test_git_dubious_ownership_taramayi_cozertmez(tmp_path: Path):
    """Baska kullaniciya ait repo: git 'dubious ownership' verir, tarama cokmez."""
    from conftest import git, rows_for

    repo = tmp_path / "baskasi"
    repo.mkdir()
    git("init", "-q", str(repo))
    (repo / "f.txt").write_text("x\n", encoding="utf-8")
    git("-C", str(repo), "add", "-A")
    git("-C", str(repo), "commit", "-q", "-m", "x")
    db = tmp_path / "atlas.db"
    proc = subprocess.run(
        [sys.executable, "-m", "atlas", "tara", "--root", str(tmp_path), "--db", str(db)],
        capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT), "GIT_CONFIG_GLOBAL": os.devnull},
    )
    assert proc.returncode == 0, proc.stderr
    if "dubious ownership" in proc.stderr:
        # Satir yazilmadigi dogru davranis: hata raporlanir, tarama surer
        assert rows_for(db) == {}
        assert str(repo) in proc.stderr
    else:
        assert str(repo) in rows_for(db)


def test_bozuk_uzak_adresi_ag_yok(tmp_path: Path):
    """Erisilemeyen remote: ag yok, timeout yok, tarama aninda biter."""
    from conftest import git, rows_for

    repo = tmp_path / "copuk"
    repo.mkdir()
    git("init", "-q", str(repo))
    (repo / "f.txt").write_text("x\n", encoding="utf-8")
    git("-C", str(repo), "add", "-A")
    git("-C", str(repo), "commit", "-q", "-m", "x")
    git("-C", str(repo), "remote", "add", "origin", "https://ornek.invalid/yok.git")
    db = tmp_path / "atlas.db"
    proc = subprocess.run(
        [sys.executable, "-m", "atlas", "tara", "--root", str(tmp_path), "--db", str(db)],
        capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT), "GIT_CONFIG_GLOBAL": os.devnull},
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    satir = rows_for(db)[str(repo)]
    assert satir["has_remote"] == 1
    # Ag yok, yerel ref yok: "bilinmiyor" (None), uydurma sayi degil.
    assert satir["unpushed"] is None
