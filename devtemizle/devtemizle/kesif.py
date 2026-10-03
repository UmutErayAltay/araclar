"""Repo kesfi: ya verilen koklerden ya da atlas DB'sinden.

Guvenlik: atlas DB'si `mode=ro` ile acilir (yazmaz, sema kurmaz).
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from .tara import _baglanti

#: Bu dizinlerin ICINE girilmez (repo govdesi, derleme ciktilari).
SKIP_DIRS = frozenset({".git", "node_modules", ".venv", "venv", "__pycache__"})

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
        dizinler[:] = sorted(
            d for d in dizinler if d not in SKIP_DIRS and not _baglanti(Path(mevcut) / d)
        )
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
            "gezinilecek yollari `--root` ile verin veya once `atlas tara` calistirin."
        )
    try:
        # mode=ro: yazmaz, sema kurmaz.
        conn = sqlite3.connect(f"file:{yol.as_posix()}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        raise KesifHatasi(
            f"atlas veritabani acilamadi: {yol} ({exc}) -> "
            "`--root` ile yol verin veya once `atlas tara` calistirin."
        ) from exc
    try:
        satirlar = conn.execute("SELECT path FROM repos ORDER BY path").fetchall()
    except sqlite3.Error as exc:
        raise KesifHatasi(
            f"atlas veritabani okunamadi: {yol} ({exc}) -> "
            "`--root` ile yol verin veya once `atlas tara` calistirin."
        ) from exc
    finally:
        conn.close()
    return [Path(satir[0]) for satir in satirlar if Path(satir[0]).exists()]


def repo_listesi(roots: list[Path] | None, atlas_db: Path | None = None) -> list[Path]:
    """Temizlenecek repolari dondurur: varsayilan olarak atlas DB'deki yollar."""
    if roots:
        repolar: list[Path] = []
        for kok in roots:
            kok = Path(kok).expanduser()
            if not kok.exists():
                raise KesifHatasi(f"verilen yol bulunamadi: {kok}")
            repolar.extend(_yuruyerek(kok) if kok.is_dir() else [kok])
        # Ayni repo birden fazla kok altinda sayilmis olabilir.
        repolar = list(dict.fromkeys(repolar))
    else:
        repolar = _atlastan(_atlas_db(atlas_db))
    if not repolar:
        raise KesifHatasi("temizlenecek repo bulunamadi")
    return repolar