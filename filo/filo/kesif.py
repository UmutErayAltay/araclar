"""Repo kesfi: `--repo` ile tek tek, `--kok` ile kok altinda derinlik 1-2.

Guvenlik: bu modul YAZMAZ -- yalnizca dizin ağacini gezer. `.git` icine girmez,
`node_modules`/`.venv`/`__pycache__` gibi derleme artiklarina inmez, sembolik
baglantilari izlemez.
"""

from __future__ import annotations

import os
from pathlib import Path

#: Bu dizinlerin ICINE girilmez (derleme/sanal ortam artiklari).
SKIP_DIRS = frozenset({"node_modules", ".venv", "venv", "__pycache__", ".pytest_cache", "dist", "build"})

#: Kokun altinda aranacak en derin seviye: kok + 2 alt dizin (derinlik 1-2).
DERINLIK = 2


class KesifHatasi(RuntimeError):
    """Repo listesi bulunamadi (kullanim/kesif hatasi)."""


def _baglanti(yol: Path) -> bool:
    """Symlink veya Windows junction mi? (3.11 uyumlu: st_file_attributes getattr ile)."""
    try:
        stat = os.lstat(yol)
    except OSError:
        return False
    if os.path.islink(yol):
        return True
    return bool(getattr(stat, "st_file_attributes", 0) & 0x400)  # REPARSE_POINT


def _yuruyerek(kok: Path) -> list[Path]:
    """Kokun altindaki repolari bulur; repo icine girmez, baglanti izlemez."""
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


def repo_listesi(repolar: list[Path] | None = None, kokler: list[Path] | None = None) -> list[Path]:
    """Calistirilacak repolari dondurur.

    `--repo` verilmisse o yollar; `--kok` verilmisse kok altindaki kesif.
    En az biri bos ise `KesifHatasi` verir (CLI cikis kodu 2).
    """
    secili: list[Path] = []
    for yol in repolar or []:
        yol = Path(yol).expanduser()
        if not yol.exists():
            raise KesifHatasi(f"verilen repo bulunamadi: {yol}")
        if not yol.is_dir():
            raise KesifHatasi(f"verilen repo bir dizin degil: {yol}")
        secili.append(yol)
    for kok in kokler or []:
        kok = Path(kok).expanduser()
        if not kok.exists():
            raise KesifHatasi(f"verilen kok bulunamadi: {kok}")
        if not kok.is_dir():
            raise KesifHatasi(f"verilen kok bir dizin degil: {kok}")
        secili.extend(_yuruyerek(kok) if kok.is_dir() else [kok])
    if not secili:
        raise KesifHatasi(
            "calistirilacak repo bulunamadi: en az biri `--repo` ya da `--kok` verilmeli."
        )
    # Ayni repo birden fazla kok altinda sayilmis olabilir.
    return list(dict.fromkeys(secili))