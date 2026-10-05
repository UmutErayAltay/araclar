"""iddia testleri icin ortak yardimcilar. Hicbir mock kutuphanesi yok.

Ag YOK: gercek git CALISTIRILMAZ (`.git` isaret dizini yeter), gercek disk
GECICI dizinlerde (tmp_path) kurulur -- kullanici ~/kullanicinin gercek
repolari hicbir testte okunmaz/yazilmaz.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def sahte_repo(yol: Path, dosyalar: dict[str, str] | None = None, *, git: bool = True) -> Path:
    """Gercek git komutu CALISTIRMAZ: `.git` isaret dizini yeter.

    Denetim salt-okunur oldugundan "hicbir sey degismedi" kaniti icin
    `tree_hash` ile dosya agacinin hash'i alinir.
    """
    yol.mkdir(parents=True, exist_ok=True)
    if git:
        (yol / ".git").mkdir(exist_ok=True)
    for ad, icerik in (dosyalar or {}).items():
        hedef = yol / ad
        hedef.parent.mkdir(parents=True, exist_ok=True)
        hedef.write_text(icerik, encoding="utf-8")
    return yol


def py_test_dosyasi(repo: Path, ad: str, test_sayisi: int) -> Path:
    """`test_*.py` icinde N adet `def test_` yazan dosya kurar."""
    govde = "\n".join(f"def test_{i}():\n    assert True\n" for i in range(1, test_sayisi + 1))
    hedef = repo / ad
    hedef.parent.mkdir(parents=True, exist_ok=True)
    hedef.write_text(govde, encoding="utf-8")
    return hedef


def argparse_kaynak(repo: Path, ad: str, komut_sayisi: int, bayraklar: list[str] | None = None) -> Path:
    """N adet `add_parser(` iceren argparse kaynagi + istege bagli bayraklar."""
    satirlar = ["import argparse", "p = argparse.ArgumentParser()", "alt = p.add_subparsers()"]
    satirlar += [f'alt.add_parser("k{i}")' for i in range(1, komut_sayisi + 1)]
    for bayrak in bayraklar or []:
        satirlar.append(f'p.add_argument("{bayrak}", action="store_true")')
    hedef = repo / ad
    hedef.parent.mkdir(parents=True, exist_ok=True)
    hedef.write_text("\n".join(satirlar) + "\n", encoding="utf-8")
    return hedef


def tree_hash(yol: Path) -> str:
    """Dizindeki tum dosyalarin (yol+icerik) sha256 toplami: salt-okunurluk olcumu."""
    import hashlib

    ozet = hashlib.sha256()
    for f in sorted(p for p in yol.rglob("*") if p.is_file() and not p.is_symlink()):
        ozet.update(str(f.relative_to(yol)).encode("utf-8"))
        ozet.update(b"\0")
        ozet.update(f.read_bytes())
        ozet.update(b"\0")
    return ozet.hexdigest()


def run_module_cli(
    *args: str, cwd: Path | str | None = None, env_ek: dict[str, str] | None = None
):
    """`python -m iddia ...` komutunu GERCEKTEN subprocess olarak calistirir.

    HOME geciciye cevrilir: test unutsa bile kullanici dizini okunmaz.
    """
    temel = cwd if isinstance(cwd, Path) else (Path(cwd) if cwd else REPO_ROOT)
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT)
    env["HOME"] = env["USERPROFILE"] = str(temel)
    env.update(env_ek or {})
    return subprocess.run(
        [sys.executable, "-m", "iddia", *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        env=env,
    )


@pytest.fixture
def ev_isole(tmp_path: Path, monkeypatch) -> Path:
    """HOME/USERPROFILE'u gecici dizine cevirir: kullanici dizini okunmaz."""
    ev = tmp_path / "ev"
    ev.mkdir()
    for ad in ("HOME", "USERPROFILE"):
        monkeypatch.setenv(ad, str(ev))
    return ev