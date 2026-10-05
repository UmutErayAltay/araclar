"""Repo kesfi: verilen koklerin altindaki git repolarini bulur.

Guvenlik: yalniz DIZINLISTESI okunur; hicbir dosya acilmaz, yazilmaz.
Kokun altinda derinlik 3'e kadar inilir; `node_modules`, `.git`, `.venv`,
`venv`, `__pycache__`, `dist`, `build`, `.pytest_cache` atlanir.
"""

from __future__ import annotations

import os
from pathlib import Path

#: Bu dizinlerin ICINE girilmez (dev bagimliliklari, derleme ciktilari).
SKIP_DIRS = frozenset(
    {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".pytest_cache"}
)

#: Kok altinda aranacak en derin seviye: kok + 3 alt dizin.
DERINLIK = 3


class KesifHatasi(RuntimeError):
    """Repo listesi bulunamadi (kullanim/kesif hatasi)."""


#: Windows junction `os.walk(followlinks=False)` ile IZLENMEZ: kok disina
#: cikip kullaniciya ait baska dizinleri envantere sokabilir.
_REPARSE_NOKTASI = 0x400


def _baglanti_mi(yol: Path) -> bool:
    """`yol` bir sembolik bag mi? (Windows junction dahil)."""
    try:
        if os.path.islink(yol):
            return True
        nitelik = getattr(os.lstat(yol), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(nitelik & _REPARSE_NOKTASI)


def _yuruyerek(kok: Path) -> list[Path]:
    """Kokun altindaki repolari bulur; repo icine girmez, link izlemez."""
    bulunan: list[Path] = []
    for mevcut, dizinler, _dosyalar in os.walk(
        kok, topdown=True, followlinks=False, onerror=lambda _e: None
    ):
        dizinler[:] = sorted(
            d for d in dizinler if d not in SKIP_DIRS and not _baglanti_mi(Path(mevcut) / d)
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


def repo_listesi(kokler: list[Path]) -> list[Path]:
    """Denetlenecek repolari dondurur (yoksa KesifHatasi).

    Ayni repo birden fazla kok altinda sayilmis olabilir: bir kez doner.
    """
    repolar: list[Path] = []
    for kok in kokler:
        kok = Path(kok).expanduser()
        if not kok.exists():
            raise KesifHatasi(f"verilen yol bulunamadi: {kok}")
        repolar.extend(_yuruyerek(kok) if kok.is_dir() else [kok])
    repolar = list(dict.fromkeys(repolar))
    if not repolar:
        raise KesifHatasi("denetlenecek repo bulunamadi")
    return repolar
