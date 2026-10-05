"""Repo kesfi: verilen koklerin altindaki git repolarini bulur (salt okunur).

Kurallar:
- Kok, `--kok` ile ZORUNLU verilir; kok bir veya birden fazla olabilir.
- Bir repo koku olarak verilirse o repo TEK BASINA islenir, altindaki repolar
  ayrica sayilmaz (tekrar sayimi onler).
- `.git` dizini VEYA dosyasi (worktree/alt modul) bir repo isaretidir.
- Bu dizinlerin icine girilmez: node_modules, .git, .venv, venv, __pycache__,
  dist, build, .pytest_cache.
"""

from __future__ import annotations

import os
from pathlib import Path

#: Bu dizinlerin ICINE girilmez (bagimlilik agaci, derleme ciktilari, sanal ortam).
SKIP_DIRS = frozenset(
    {
        ".git",
        "node_modules",
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

#: Tek bir dosya icin en buyuk okunabilir boyut (bayt). Buyuk/ikili dosya ATLANIR.
MAKS_BOYUT = 1024 * 1024


class KesifHatasi(RuntimeError):
    """Repo listesi bulunamadi (kullanim/kesif hatasi)."""


def _baglanti(yol: Path) -> bool:
    """Symlink veya Windows junction mi? (repo disina tasmayi onler)."""
    try:
        return os.path.islink(yol)
    except OSError:
        return False


def _yuruyerek(kok: Path) -> list[Path]:
    """Kokun altindaki repolari bulur; bululan repo icine girmez."""
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
            dizinler[:] = []  # repo icine inme: ic ice repo tekrar sayilmaz
            continue
        if len(yol.relative_to(kok).parts) >= DERINLIK:
            dizinler[:] = []  # derinlik siniri
    return bulunan


def repo_listesi(kokler: list[Path]) -> list[Path]:
    """Denetlenecek repolari dondurur (yoksa hata firlatir)."""
    if not kokler:
        raise KesifHatasi("en az bir --kok verilmelidir")
    repolar: list[Path] = []
    for kok in kokler:
        kok = Path(kok).expanduser()
        if not kok.exists():
            raise KesifHatasi(f"verilen yol bulunamadi: {kok}")
        repolar.extend(_yuruyerek(kok) if kok.is_dir() else [kok])
    # Ayni repo birden fazla kok altinda sayilmis olabilir (sirali dus).
    repolar = list(dict.fromkeys(repolar))
    if not repolar:
        raise KesifHatasi("taranacak repo bulunamadi (kok altinda .git yok)")
    return repolar


def okunabilir(yol: Path) -> str | None:
    """Dosya metnini dondurur; ikili/cok buyuk/bozuk kodlamada None (ATLANIR).

    Boylece bir PNG veya minified bundle README'deki yol kalibini yanlis tetiklemez.
    """
    try:
        if not yol.is_file() or yol.stat().st_size > MAKS_BOYUT:
            return None
        veri = yol.read_bytes()
    except OSError:
        return None
    if b"\0" in veri:  # ikili (ikili icerik NUL icerir)
        return None
    try:
        return veri.decode("utf-8")
    except UnicodeDecodeError:
        return None


def yazili_metin(yol: Path) -> bool:
    """Kucuk metin dosyasi mi? (kaynak tarama icin on filtre; sonra okunabilir() dener)"""
    try:
        return yol.is_file() and yol.stat().st_size <= MAKS_BOYUT
    except OSError:
        return False