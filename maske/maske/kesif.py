"""Repo kesfi: verilen koklerin altindaki git repolari (derinlik 3).

anahtarlik/devtemizle `kesif.py`lerinin Ayni yuruyus kurali: repoya girilmez,
sembolik bag izlenmez, kok sinirinda durulur. Fark: burda atlas DB YOKTUR --
kokler `--kok` ile ZORUNLU verilir (salt-okunur bir arac, ekran girdisi yeter).
"""

from __future__ import annotations

import os
from pathlib import Path

#: Bu dizinlerin ICINE girilmez (repo govdesi, dev bagimliliklari, derleme ciktilari).
ATLANAN = frozenset(
    {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".pytest_cache"}
)

#: Kok altinda aranacak en derin seviye: kok + 3 alt dizin.
DERINLIK = 3

#: Windows junction `os.walk(followlinks=False)` ile IZLENMEZ: kok disina
#: cikip kullaniciya ait baska dizinleri taramak istemeyiz.
_REPARSE_NOKTASI = 0x400


class KesifHatasi(RuntimeError):
    """Repo listesi bulunamadi (kullanim/kesif hatasi -> cikis 2)."""


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
        yol = Path(mevcut)
        dizinler[:] = sorted(
            d for d in dizinler if d not in ATLANAN and not _baglanti_mi(yol / d)
        )
        # .git dizin VEYA dosya olabilir (worktree / alt modul).
        if (yol / ".git").exists():
            bulunan.append(yol)
            dizinler[:] = []  # repo icine inme: ic ice repo sayilmaz
            continue
        if len(yol.relative_to(kok).parts) >= DERINLIK:
            dizinler[:] = []  # derinlik siniri
    return bulunan


def repo_listesi(kokler: list[str]) -> list[Path]:
    """Denetlenecek repolari dondurur (tekillestirilmis, sirali).

    `--kok` verilmezse anahtarlik'ta oldugu gibi hata: bu arac atlas DB'sine bakmaz.
    """
    if not kokler:
        raise KesifHatasi("en az bir `--kok DIZIN` verilmeli")
    repolar: list[Path] = []
    for kok in kokler:
        yol = Path(kok).expanduser()
        if not yol.exists():
            raise KesifHatasi(f"verilen yol bulunamadi: {yol}")
        repolar.extend(_yuruyerek(yol) if yol.is_dir() else [yol])
    # Ayni repo birden fazla kok altinda sayilmis olabilir (ayni + kardes kok).
    repolar = list(dict.fromkeys(repolar))
    if not repolar:
        raise KesifHatasi("taranacak repo bulunamadi (`.git` olan dizin yok)")
    return repolar