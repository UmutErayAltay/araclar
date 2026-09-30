"""BAGLAYICI: tarama salt-okunurdur, repolara hicbir sey yazmaz."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import (
    commit_file,
    git,
    make_bare_remote,
    make_repo,
    read_only_actor,
    run_module_cli,
    tree_hash,
)

#: Taramanin kullanmasina izin verilen alt komutlar.
IZINLI = {"status", "log", "rev-parse", "rev-list", "symbolic-ref", "remote", "for-each-ref"}

#: Bu komsularin hicbiri calistirilmamali.
YAZAN_KOMUTLAR = (
    "push", "fetch", "pull", "reset", "checkout", "restore", "clean", "gc",
    "rebase", "merge", "commit", "add", "rm", "mv", "filter-branch", "stash",
    "update-ref", "prune", "am", "cherry-pick", "revert", "worktree", "submodule",
)

GERCEK_GIT = shutil.which("git") or "/usr/bin/git"


def test_sadece_izinli_alt_komutlar():
    from atlas.scan import ALLOWED_GIT_SUBCOMMANDS

    assert set(ALLOWED_GIT_SUBCOMMANDS) == IZINLI
    for yasak in YAZAN_KOMUTLAR:
        assert yasak not in ALLOWED_GIT_SUBCOMMANDS


def _git_shim(dizin: Path) -> Path:
    """`git` yerine gecen koruma (guard) script'i: argumanlari kaydeder ve izin
    listesindeki alt komut disindaki HER seyi reddeder, gercek git'e devreder."""
    kayit = dizin / "cagrilar.log"
    koruma = dizin / "git"
    koruma.write_text(
        "#!/bin/sh\n"
        'printf "%s\\n" "$*" >> "{kayit}"\n'
        'shift 2\n'  # 'git -C <yol>' atlanir
        'case "$1" in\n'
        "  status|log|rev-parse|rev-list|symbolic-ref|remote|for-each-ref) exec {gercek} \"$@\" ;;\n"
        '  *) echo "YASAK alt komut: $1" >&2; exit 97 ;;\n'
        "esac\n".format(kayit=kayit, gercek=GERCEK_GIT),
        encoding="utf-8",
    )
    koruma.chmod(0o755)
    return kayit


def test_guard_kendisi_calisiyor(tmp_path: Path, monkeypatch):
    """Once korumanin dogru calistigini dogrula (aksi halde asagidaki test bos gecer)."""
    shim = tmp_path / "shim-dogrulama"
    shim.mkdir()
    _git_shim(shim)
    env = dict(os.environ)
    env["PATH"] = f"{shim}:{env['PATH']}"
    yasak = subprocess.run(
        ["git", "-C", str(tmp_path), "fetch", "--all"],
        capture_output=True, text=True, env=env,
    )
    assert yasak.returncode == 97
    assert "YASAK" in yasak.stderr
    serbest = subprocess.run(
        ["git", "-C", str(tmp_path), "remote"],
        capture_output=True, text=True, env=env,
    )
    assert serbest.returncode == 0


def test_gercek_git_cagrisi_sadece_okuyan_komutlar(tmp_path: Path, monkeypatch):
    """Kanit: guard script'i ile her git cagrisi kaydedilir; kayitta yazan komut olmamali."""
    from atlas import scan

    repo = make_repo(tmp_path / "guvenlik")
    shim = tmp_path / "shim"
    shim.mkdir()
    kayit = _git_shim(shim)
    monkeypatch.setenv("PATH", f"{shim}:{os.environ['PATH']}")

    satir = scan.collect_repo(repo)
    assert satir["name"] == "guvenlik"  # tarama gercekten calisti

    cagrilar = [l for l in kayit.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert cagrilar, "hic git cagrisi kaydedilmedi"
    for cagri in cagrilar:
        parcalar = cagri.split()
        alt = parcalar[2]  # "-C <yol> <alt-komut>"
        assert alt in IZINLI, f"YAZAN komut cagrildi: {cagri}"
        assert alt not in YAZAN_KOMUTLAR


def test_tarama_once_ve_sonra_ayni(tmp_path: Path, db_file: Path):
    """Tarama repoyu HIC degistirmez: .git icerigi + calisma agaci ayni kalmali."""
    temiz = make_repo(tmp_path / "temiz")
    kirli = make_repo(tmp_path / "kirli")
    commit_file(kirli, "a.txt", "1", "ikinci")
    (kirli / "README.md").write_text("# degistirildi\n", encoding="utf-8")
    (kirli / "izlenmeyen.txt").write_text("yeni\n", encoding="utf-8")

    remote = make_bare_remote(tmp_path / "uzak.git")
    gecmis = make_repo(tmp_path / "gecmis")
    git("remote", "add", "origin", str(remote), cwd=gecmis)
    git("push", "-q", "-u", "origin", "main", cwd=gecmis)
    commit_file(gecmis, "b.txt", "1", "push edilmemiş")

    bos = make_repo(tmp_path / "bos", commit=False)
    ayrik = make_repo(tmp_path / "ayrik")
    commit_file(ayrik, "a.txt", "1", "ikinci")
    git("checkout", "-q", git("rev-parse", "HEAD~1", cwd=ayrik).strip(), cwd=ayrik)

    repolar = [temiz, kirli, gecmis, bos, ayrik]
    once = {r: tree_hash(r) for r in repolar}

    for repo in repolar:
        proc = run_module_cli("tara", "--root", str(repo.parent), "--db", str(db_file))
        assert proc.returncode == 0, proc.stderr

    for repo in repolar:
        assert once[repo] == tree_hash(repo), f"{repo} tarama ile degisti"
        assert not (repo / ".git" / "atlas.lock").exists()


def test_index_dosyasi_degismez(tmp_path: Path, db_file: Path):
    """`git status` index'i tazelemesin: index dosyasi bayt bayt ayni kalmali."""
    repo = make_repo(tmp_path / "repo")
    index = repo / ".git" / "index"
    assert index.exists()
    once = index.read_bytes()
    proc = run_module_cli("tara", "--root", str(tmp_path), "--db", str(db_file))
    assert proc.returncode == 0, proc.stderr
    assert index.read_bytes() == once


def test_optional_locks_kapatili_calistirilir(monkeypatch, tmp_path: Path):
    import subprocess as sp

    from atlas import scan

    repo = make_repo(tmp_path / "repo")
    gorulen: list[dict] = []
    gercek_run = sp.run

    def kaydedici(cmd, *a, **kw):
        gorulen.append(kw.get("env") or {})
        return gercek_run(cmd, *a, **kw)

    monkeypatch.setattr(scan.subprocess, "run", kaydedici)
    scan.collect_repo(repo)
    assert gorulen
    for env in gorulen:
        assert env.get("GIT_OPTIONAL_LOCKS") == "0"


def test_tarama_sonrasi_head_ve_refler_ayni(tmp_path: Path, db_file: Path):
    repo = make_repo(tmp_path / "repo")
    commit_file(repo, "a.txt", "1", "ikinci")
    once = {
        "head": git("rev-parse", "HEAD", cwd=repo),
        "ref": git("show-ref", cwd=repo, check=False),
        "log": git("log", "--format=%H %s", cwd=repo),
    }
    proc = run_module_cli("tara", "--root", str(tmp_path), "--db", str(db_file))
    assert proc.returncode == 0, proc.stderr
    assert git("rev-parse", "HEAD", cwd=repo) == once["head"]
    assert git("show-ref", cwd=repo, check=False) == once["ref"]
    assert git("log", "--format=%H %s", cwd=repo) == once["log"]


def test_okunamayan_dizin_taramayi_cozertmez(tmp_path: Path, db_file: Path):
    """chmod 000 dizin taramayi cokertmemeli ve diger repolar yazilmalı.

    Root icin de gecerli: root DAC_OVERRIDE ile her seyi okur, ama kritik olan
    taramanin 0 cikis koduyla bitmesi.
    """
    from conftest import rows_for

    iyi = make_repo(tmp_path / "okunur")
    kilitli = tmp_path / "kilitli"
    kilitli.mkdir()
    os.chmod(kilitli, 0o000)
    try:
        proc = run_module_cli("tara", "--root", str(tmp_path), "--db", str(db_file))
        assert proc.returncode == 0, proc.stderr
        assert str(iyi) in rows_for(db_file)
    finally:
        os.chmod(kilitli, stat.S_IRWXU)


def test_izinsiz_dizin_atlanir_ve_uyari_verilir(tmp_path: Path, db_file: Path):
    """Iceri gemedigi icin atlanan dizin stderr'a yazilir (seffaflik).

    Root oldugunda chmod 000 ise yaramaz; bu yol `test_permissions.py` icinde
    gercek `nobody` kullanicisiyla kanitlanir.
    """
    from conftest import rows_for

    iyi = make_repo(tmp_path / "okunur")
    kilitli = tmp_path / "kilitli"
    kilitli.mkdir()
    os.chmod(kilitli, 0o000)
    try:
        if os.access(kilitli, os.R_OK) and os.access(kilitli, os.X_OK):
            pytest.skip("root: chmod 000 etkisiz; test_permissions.py gercek kullaniciyla calisiyor")
        proc = run_module_cli("tara", "--root", str(tmp_path), "--db", str(db_file))
        assert proc.returncode == 0, proc.stderr
        assert str(iyi) in rows_for(db_file)
        assert "kilitli" in proc.stderr
    finally:
        os.chmod(kilitli, stat.S_IRWXU)


def test_bozuk_uzak_adresi_cozertmez(tmp_path: Path, db_file: Path):
    """Uzak sunucu erisilemez olsa da tarama bitmeli (fetch CALISTIRILMAZ)."""
    from conftest import rows_for

    repo = make_repo(tmp_path / "copuk")
    git("remote", "add", "origin", "https://ornek.invalid/olmayan.git", cwd=repo)
    proc = run_module_cli("tara", "--root", str(tmp_path), "--db", str(db_file))
    assert proc.returncode == 0, proc.stderr
    satir = rows_for(db_file)[str(repo)]
    assert satir["has_remote"] == 1
    # Yerelde hicbir uzak-takip ref'i yok ve fetch yasak: sayi UYDURULAMAZ.
    assert satir["unpushed"] is None
    assert satir["dirty"] == 0


def test_kilitli_ve_bozuk_ama_saglam_repolar(db_file: Path, tmp_path: Path):
    """Bozuk + bos + temiz + kirli + gecmis: hicbiri digerini cokertmemeli."""
    from conftest import rows_for

    bozuk = tmp_path / "bozuk"
    bozuk.mkdir()
    (bozuk / ".git").mkdir()
    (bozuk / ".git" / "HEAD").write_text("HEAD degil\n", encoding="utf-8")
    make_repo(tmp_path / "bos", commit=False)
    temiz = make_repo(tmp_path / "temiz")
    kirli = make_repo(tmp_path / "kirli")
    (kirli / "README.md").write_text("# x\n", encoding="utf-8")

    proc = run_module_cli("tara", "--root", str(tmp_path), "--db", str(db_file))
    assert proc.returncode == 0, proc.stderr
    satirlar = rows_for(db_file)
    assert sorted(r["name"] for r in satirlar.values()) == ["bos", "kirli", "temiz"]
    assert satirlar[str(temiz)]["dirty"] == 0
    assert satirlar[str(kirli)]["dirty"] == 1


def test_bozuk_git_dizini_taramayi_cozertmez(tmp_path: Path, db_file: Path):
    from conftest import rows_for

    bozuk = tmp_path / "bozuk"
    bozuk.mkdir()
    (bozuk / ".git").mkdir()
    (bozuk / ".git" / "HEAD").write_text("bu bir HEAD degil\n", encoding="utf-8")
    (bozuk / ".git" / "config").write_text("[coremel\n", encoding="utf-8")
    iyi = make_repo(tmp_path / "iyi")
    proc = run_module_cli("tara", "--root", str(tmp_path), "--db", str(db_file))
    assert proc.returncode == 0, proc.stderr
    satirlar = rows_for(db_file)
    assert str(iyi) in satirlar
    assert str(bozuk) not in satirlar  # hatali repo satir olarak yazilmaz
    assert "bozuk" in proc.stderr
