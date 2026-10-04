"""Repo kesfi: ya verilen koklerden ya da atlas DB'sinden.

bagimlilik/bagimlilik/kesif.py'in KOPYASI (bagimlilik import edilmez; iki arac
bagimsiz kalsin). Guvenlik: atlas DB'si `mode=ro` ile acilir (yazmaz, sema kurmaz).
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

#: Bu dizinlerin ICINE girilmez (dev bagimliliklari, derleme ciktilari).
SKIP_DIRS = frozenset({".git", "node_modules", ".venv", "venv", "target", "__pycache__"})

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
    kok = kok.expanduser()
    for mevcut, dizinler, _dosyalar in os.walk(
        kok, topdown=True, followlinks=False, onerror=lambda _e: None
    ):
        yol = Path(mevcut)
        dizinler[:] = sorted(
            d for d in dizinler if d not in SKIP_DIRS and not _baglanti_mi(yol / d)
        )
        # .git dizin VEYA dosya olabilir (worktree/alt modulde dosyadır).
        if (yol / ".git").exists():
            bulunan.append(yol)
            dizinler[:] = []  # repo icine inme
            continue
        if len(yol.relative_to(kok).parts) >= DERINLIK:
            dizinler[:] = []  # derinlik siniri
    if not bulunan and _proje_izleri(kok):
        # Kok bir repo degil ama kendisi bir proje (requirements.txt/pyproject.toml/
        # package.json): kullanici bu projeyi denetlemek istedi, kendisi sayilir.
        bulunan.append(kok)
    return bulunan


def _proje_izleri(kok: Path) -> bool:
    return any(
        (kok / ad).is_file()
        for ad in ("requirements.txt", "pyproject.toml", "package.json", "setup.py")
    )


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
    """Denetlenecek repolari dondurur: varsayilan olarak atlas DB'deki yollar."""
    if roots:
        repolar: list[Path] = []
        for kok in roots:
            kok = Path(kok).expanduser()
            if not kok.exists():
                raise KesifHatasi(f"verilen yol bulunamadi: {kok}")
            repolar.extend(_yuruyerek(kok) if kok.is_dir() else [kok])
        # Ayni repo birden fazla kok altinda sayilmis olabilir.
        return list(dict.fromkeys(repolar))
    return _atlastan(_atlas_db(atlas_db))