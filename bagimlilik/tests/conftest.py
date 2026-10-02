"""bagimlilik testleri icin ortak yardimcilar. Hicbir mock kutuphanesi yok.

Ag YOK: denetimler daima sahte `calistir` ile surulur (imza:
calistir(argv, cwd, zaman_asimi) -> (rc, stdout, stderr)).
"""

from __future__ import annotations

import hashlib
import importlib.machinery
import importlib.util
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"

#: Kesif modulu bu tabloyu okur; atlas'in gercek semasi bu sutunlari icerir.
ATLAS_REPOS_SEMASI = (
    "CREATE TABLE repos (path TEXT PRIMARY KEY, name TEXT, scanned_at TEXT, "
    "dirty INTEGER, unpushed INTEGER, branch TEXT, last_commit_at TEXT, has_remote INTEGER)"
)


def fixture_yukle(ad: str) -> str:
    """tests/fixtures/<ad>.json icerigini metin olarak dondurur."""
    return (FIXTURES / f"{ad}.json").read_text(encoding="utf-8")


def sahte_repo(yol: Path, dosyalar: dict[str, str] | None = None, *, git: bool = True) -> Path:
    """Gercek git komutu CALISTIRMAZ: `.git` isaret dizini yeter.

    bagimlilik repoda git'i hic kullanmaz; yalnizca yazmamayi kanitlamak icin
    dosya agacinin hash'ini aliriz.
    """
    yol.mkdir(parents=True, exist_ok=True)
    if git:
        (yol / ".git").mkdir(exist_ok=True)
    for ad, icerik in (dosyalar or {}).items():
        hedef = yol / ad
        hedef.parent.mkdir(parents=True, exist_ok=True)
        hedef.write_text(icerik, encoding="utf-8")
    return yol


def sahte_calistir(
    cikti: str = "{}", rc: int = 0, *, hata: BaseException | None = None, stderr: str = ""
):
    """Cagri kaydi tutan sahte `calistir`.

    Kayit her cagri icin argv/cwd/zaman-asimi tutar; gecici dizin denetleme
    bittikten SONRA silindigi icin `cwd_icerik` ve `requirements` anlik
    kopyalanir.
    """
    cagrilar: list[dict] = []

    def calistir(argv, cwd, zaman_asimi):
        kayit = {
            "argv": list(argv),
            "cwd": cwd,
            "zaman_asimi": zaman_asimi,
            "cwd_icerik": sorted(p.name for p in Path(cwd).iterdir()) if cwd else None,
        }
        if "-r" in argv:
            i = argv.index("-r")
            kayit["requirements"] = Path(argv[i + 1]).read_text(encoding="utf-8")
        cagrilar.append(kayit)
        if hata is not None:
            raise hata
        return rc, cikti, stderr

    calistir.cagrilar = cagrilar  # type: ignore[attr-defined]
    return calistir


def tree_hash(yol: Path) -> str:
    """Dizindeki tum dosyalarin (yol+icerik) sha256 toplami (atlas/tests/conftest.py)."""
    ozet = hashlib.sha256()
    for f in sorted(p for p in yol.rglob("*") if p.is_file() and not p.is_symlink()):
        ozet.update(str(f.relative_to(yol)).encode("utf-8"))
        ozet.update(b"\0")
        ozet.update(f.read_bytes())
        ozet.update(b"\0")
    return ozet.hexdigest()


def atlas_db_olustur(yol: Path, yollar: list[Path]) -> Path:
    """Kesif'in okuyacagi `repos` tablosu olan gecici sqlite (satirlar yazilir)."""
    conn = sqlite3.connect(str(yol))
    try:
        conn.execute(ATLAS_REPOS_SEMASI)
        conn.executemany(
            "INSERT INTO repos (path, name) VALUES (?, ?)", [(str(p), p.name) for p in yollar]
        )
        conn.commit()
    finally:
        conn.close()
    return yol


def run_module_cli(*args: str, cwd: Path | str | None = None, env_ek: dict[str, str] | None = None):
    """`python -m bagimlilik ...` komutunu GERCEKTEN subprocess olarak calistirir.

    BAGIMLILIK_DIR / ATLAS_DB varsayilanlari KULLANILMAZ: env once temizlenir,
    sonra testin yonlendirdigi degerler yazilir (kullanici raporu ezilmez).
    """
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT)
    env.pop("ATLAS_DB", None)
    env.pop("BAGIMLILIK_DIR", None)
    env.update(env_ek or {})
    return subprocess.run(
        [sys.executable, "-m", "bagimlilik", *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        env=env,
    )


@pytest.fixture
def pip_audit_kurulu(monkeypatch) -> None:
    """pip-audit KURULU sayilsin (ag ve kurulum yok, sadece find_spec sahtelenir).

    Aksi halde `_denetim_pip` her seferinde "arac-yok" doner ve argv'i hic
    gormez; regresyon testleri (--format json, --progress-spinner off)
    ancak bu fixture ile anlamli olur.
    """
    gercek = importlib.util.find_spec

    def find_spec(name, package=None):
        if name == "pip_audit":
            return importlib.machinery.ModuleSpec("pip_audit", None)
        return gercek(name, package)

    monkeypatch.setattr(importlib.util, "find_spec", find_spec)


@pytest.fixture
def rapor_dizini(tmp_path: Path, monkeypatch) -> Path:
    """BAGIMLILIK_DIR'i gecici dizine yonlendirir (kullanici ~/.bagimlilik'i ezilmez)."""
    dizin = tmp_path / "raporlar"
    monkeypatch.setenv("BAGIMLILIK_DIR", str(dizin))
    return dizin
