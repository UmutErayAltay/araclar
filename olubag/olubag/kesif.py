"""Repo kesfi: verilen koklerden (derinlik 3) ya da atlas DB'sinden.

Guvenlik: atlas DB'si `mode=ro` ile acilir (yazmaz, sema kurmaz).
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

#: Bu dizinlerin ICINE girilmez (bagimlilik agaci, derleme ciktilari, sanal ortam).
SKIP_DIRS = frozenset(
    {
        "node_modules",
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        "dist",
        "build",
        ".pytest_cache",
    }
)

#: Kok altinda aranacak en derin seviye: kok + 3 alt dizin.
DERINLIK = 3


class KesifHatasi(RuntimeError):
    """Repo listesi bulunamadi (kullanim/kesif hatasi)."""


def _atlas_db(yol: Path | None = None) -> Path:
    """Arguman > ATLAS_DB > ~/.atlas/atlas.db."""
    if yol is not None:
        return yol.expanduser()
    env = os.environ.get("ATLAS_DB")
    return Path(env).expanduser() if env else Path.home() / ".atlas" / "atlas.db"


def _yuruyerek(kok: Path) -> list[Path]:
    """Kokun altindaki repolari bulur; repo icine girmez, link izlemez."""
    bulunan: list[Path] = []
    for mevcut, dizinler, _dosyalar in os.walk(
        kok, topdown=True, followlinks=False, onerror=lambda _e: None
    ):
        dizinler[:] = sorted(d for d in dizinler if d not in SKIP_DIRS)
        yol = Path(mevcut)
        # .git dizin VEYA dosya olabilir (worktree/alt modulde dosyadadir).
        if (yol / ".git").exists():
            bulunan.append(yol)
            dizinler[:] = []  # repo icine inme
            continue
        if len(yol.relative_to(kok).parts) >= DERINLIK:
            dizinler[:] = []  # derinlik siniri
    return bulunan


def _atlastan(yol: Path) -> list[Path]:
    if not yol.is_file():
        raise KesifHatasi(
            f"atlas veritabani bulunamadi: {yol} -> "
            "gezinilecek yollari `--kok` ile verin veya once `atlas tara` calistirin."
        )
    try:
        # mode=ro: yazmaz, sema kurmaz.
        conn = sqlite3.connect(f"file:{yol.as_posix()}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        raise KesifHatasi(
            f"atlas veritabani acilamadi: {yol} ({exc}) -> "
            "`--kok` ile yol verin veya once `atlas tara` calistirin."
        ) from exc
    try:
        satirlar = conn.execute("SELECT path FROM repos ORDER BY path").fetchall()
    except sqlite3.Error as exc:
        raise KesifHatasi(
            f"atlas veritabani okunamadi: {yol} ({exc}) -> "
            "`--kok` ile yol verin veya once `atlas tara` calistirin."
        ) from exc
    finally:
        conn.close()
    return [Path(satir[0]) for satir in satirlar if Path(satir[0]).exists()]


def repo_listesi(kokler: list[Path] | None, atlas_db: Path | None = None) -> list[Path]:
    """Taranacak repolari dondurur: kokler verilmezse atlas DB'deki yollar."""
    if kokler:
        repolar: list[Path] = []
        for kok in kokler:
            kok = Path(kok).expanduser()
            if not kok.exists():
                raise KesifHatasi(f"verilen yol bulunamadi: {kok}")
            repolar.extend(_yuruyerek(kok) if kok.is_dir() else [kok])
        # Ayni repo birden fazla kok altinda sayilmis olabilir.
        repolar = list(dict.fromkeys(repolar))
    else:
        repolar = _atlastan(_atlas_db(atlas_db))
    if not repolar:
        raise KesifHatasi("taranacak repo bulunamadi")
    return repolar