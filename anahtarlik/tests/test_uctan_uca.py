"""Uctan uca: CLI ile hook kurulur, GERCEK `git push` sirli commit'te durur.

Uzak depo tmp'de bare repo; ag yok. `core.hooksPath` depo icine acikca
set edilir (bu makinada global hooksPath var; testler ona yazmamali).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from conftest import REPO_ROOT, run_module_cli

SIR = "sk-SENTINEL8fHq2Lp9Zx4Wq7Nb3uU"


def _env() -> dict[str, str]:
    env = dict(os.environ)
    # Hook icindeki `python -m anahtarlik` bu paketi bulsun, bu yorumlayici olsun.
    env["PYTHONPATH"] = str(REPO_ROOT)
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def git(repo: Path, *args: str, kontrol: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          env=_env(), check=kontrol)


def _kur(tmp_path: Path) -> Path:
    uzak = tmp_path / "uzak.git"
    subprocess.run(["git", "init", "-q", "--bare", str(uzak)], check=True, capture_output=True)
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "t@example.com")
    git(repo, "config", "user.name", "t")
    git(repo, "config", "core.hooksPath", str(repo / ".git" / "hooks"))
    git(repo, "remote", "add", "origin", str(uzak))
    (repo / "README.md").write_text("ilk\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "ilk")
    return repo


def test_cli_hook_kur_kuru_calistirma_yazmaz(tmp_path: Path):
    repo = _kur(tmp_path)
    proc = run_module_cli("hook-kur", "--repo", str(repo), cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert "kuru calistirma" in proc.stdout
    assert not (repo / ".git" / "hooks" / "pre-push").exists()


def test_cli_hook_kur_ortak_dizine_izinsiz_yazmaz(tmp_path: Path):
    repo = _kur(tmp_path)
    disari = tmp_path / "global-hooks"
    git(repo, "config", "core.hooksPath", str(disari))
    proc = run_module_cli("hook-kur", "--repo", str(repo), "--uygula", cwd=tmp_path)
    assert proc.returncode == 2
    assert "--ortak" in proc.stdout
    assert not disari.exists()
    proc = run_module_cli("hook-kur", "--repo", str(repo), "--uygula", "--ortak", cwd=tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert (disari / "pre-push").is_file()


def test_gercek_push_sirli_committe_durur_temizde_gecer(tmp_path: Path):
    repo = _kur(tmp_path)
    proc = run_module_cli("hook-kur", "--repo", str(repo), "--uygula", cwd=tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr

    # Temiz push gecer.
    temiz = git(repo, "push", "-q", "origin", "main", kontrol=False)
    assert temiz.returncode == 0, temiz.stderr

    # Sirli commit: push DURUR, ham deger ciktida yok.
    (repo / "ayar.py").write_text(f'API_KEY = "{SIR}"\n', encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "sir")
    kirli = git(repo, "push", "origin", "main", kontrol=False)
    assert kirli.returncode != 0
    assert "ayar.py:1" in kirli.stderr
    assert SIR not in kirli.stdout + kirli.stderr

    # Uzak depoya sir ulasmadi.
    uzak_log = subprocess.run(["git", "-C", str(tmp_path / "uzak.git"), "log", "--oneline", "main"],
                              capture_output=True, text=True)
    assert "sir" not in uzak_log.stdout.split()


def test_fark_github_olmayan_repo_cikis_2(tmp_path: Path):
    repo = _kur(tmp_path)
    proc = run_module_cli("fark", "--repo", str(repo), cwd=tmp_path)
    assert proc.returncode == 2
    assert "github-degil" in proc.stderr
