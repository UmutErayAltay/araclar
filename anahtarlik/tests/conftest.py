"""anahtarlik testleri icin ortak yardimcilar. Hicbir mock kutuphanesi yok.

Ag YOK. Gercek `~/.anahtarlik` HICBIR testte yazilmaz: `ANAHTARLIK_DIR` ve
`ATLAS_DB` gecici dizine yonlendirilir; alt yuklemede HOME da geciciye cevrilir.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def repo_kur(kok: Path, env_icerigi: str, ad: str = ".env") -> Path:
    """Gecici bir repo + `.env` dosyasi kurar (dizin `.git` ile isaretli)."""
    kok.mkdir(parents=True, exist_ok=True)
    (kok / ".git").mkdir(exist_ok=True)
    (kok / ad).write_text(env_icerigi, encoding="utf-8")
    return kok


def dosya_agaci(yol: Path) -> list[str]:
    """Dizindeki dosya adlari (yedek/temp sizmaz kontrolu icin)."""
    return sorted(p.relative_to(yol).as_posix() for p in yol.rglob("*") if p.is_file())


def run_module_cli(
    *args: str, cwd: Path | str | None = None, env_ek: dict[str, str] | None = None
):
    """`python -m anahtarlik ...` komutunu GERCEKTEN subprocess olarak calistirir.

    ANAHTARLIK_DIR/ATLAS_DB varsayilanlari KULLANILMAZ: env once temizlenir, sonra
    testin yonlendirdigi degerler yazilir. HOME da geciciye cevrilir: test
    unutsa bile ~/.anahtarlik YAZILMAZ.
    """
    temel = cwd if isinstance(cwd, Path) else (Path(cwd) if cwd else REPO_ROOT)
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT)
    env.pop("ANAHTARLIK_DIR", None)
    env.pop("ATLAS_DB", None)
    env["HOME"] = env["USERPROFILE"] = str(temel)
    env.update(env_ek or {})
    return subprocess.run(
        [sys.executable, "-m", "anahtarlik", *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        env=env,
    )


@pytest.fixture
def anahtarlik_dir(tmp_path: Path, monkeypatch) -> Path:
    """ANAHTARLIK_DIR'i gecici dizine yonlendirir (~/.anahtarlik YAZILMAZ)."""
    dizin = tmp_path / "anahtarlik"
    monkeypatch.setenv("ANAHTARLIK_DIR", str(dizin))
    return dizin


@pytest.fixture
def ortam(tmp_path: Path, anahtarlik_dir: Path) -> dict[str, str]:
    """CLI alt surecine verilecek izole ortam (tuz + envanter gecici)."""
    atlas = tmp_path / "yok.atlas.db"
    return {
        "ANAHTARLIK_DIR": str(anahtarlik_dir),
        "ATLAS_DB": str(atlas),
    }