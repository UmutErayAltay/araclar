"""Tarama: her repoda aday klasorleri (node_modules, __pycache__, sanal ortam...) bulur.

Kurallar:
- Bir adayin ICINE girilmez: ic ice node_modules ayri sayilmaz.
- .git icine girilmez; baglanti (symlink/junction) ve pyvenv.cfg'siz sanal ortam
  ATLANIR ama raporda gorunur.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from pathlib import Path

#: Aday klasor adi -> tur.
ADAYLAR = {
    "node_modules": "node_modules",
    "__pycache__": "__pycache__",
    ".pytest_cache": ".pytest_cache",
    ".venv": ".venv",
    "venv": "venv",
}

#: Windows FILE_ATTRIBUTE_REPARSE_POINT (junction noktasi). POSIX'te yok sayilir.
REPARSE_POINT = 0x400

#: Bunlarin icine girilmez: repo govdesi, aday klasorler, baglantilar.
_ATLANAN = frozenset({".git"}) | frozenset(ADAYLAR)


def _baglanti(yol: Path) -> bool:
    """Symlink veya Windows junction mi? (3.11 uyumlu: st_file_attributes getattr ile)."""
    try:
        stat = os.lstat(yol)
    except OSError:
        return False
    if os.path.islink(yol):
        return True
    return bool(getattr(stat, "st_file_attributes", 0) & REPARSE_POINT)


def _pyvenv_cfg(yol: Path) -> bool:
    """Gercek sanal ortam cfg'si mi? (yalniz dosya varligi taklit edilebilir; 'home' satiri aranir)."""
    try:
        return "home" in (yol / "pyvenv.cfg").read_text(encoding="utf-8", errors="ignore").lower()
    except OSError:
        return False


def _boyut(dizin: Path) -> int:
    """Dizin icindeki dosya boyutlari toplami (bayt). Baglanti izlenmez."""
    toplam = 0
    for mevcut, dizinler, dosyalar in os.walk(
        dizin, topdown=True, followlinks=False, onerror=lambda _e: None
    ):
        kok = Path(mevcut)
        dizinler[:] = [d for d in dizinler if not _baglanti(kok / d)]
        for ad in dosyalar:
            try:
                toplam += (kok / ad).lstat().st_size
            except OSError:
                continue  # kayboldu / erisilemedi: sayma
    return toplam


def _son_erisim(aday: Path, repo: Path) -> float:
    """Adayin son kullanildigi an: aday dizini, yoksa .git/index + .git/HEAD."""
    zamanlar = [aday.stat().st_mtime]
    for ad in ("index", "HEAD"):
        try:
            zamanlar.append((repo / ".git" / ad).stat().st_mtime)
        except OSError:
            continue  # yok (veya .git bir dosya: worktree/alt modul)
    return max(zamanlar)


def _iso(an: float) -> str:
    return datetime.fromtimestamp(an, timezone.utc).isoformat(timespec="seconds")


def tara(repolar: list[Path], simdi: float | None = None) -> list[dict]:
    """Aday klasorleri aday dict listesi olarak dondurur (dosya sistemi degismez)."""
    simdi = time.time() if simdi is None else simdi
    adaylar: list[dict] = []

    for repo in repolar:
        repo = Path(repo)
        for mevcut, dizinler, _dosyalar in os.walk(
            repo, topdown=True, followlinks=False, onerror=lambda _e: None
        ):
            kok = Path(mevcut)
            bulunan = [d for d in dizinler if d in ADAYLAR]
            # os.walk Windows junction'ini durdurmaz: baglantilar elle budanir (repo disina tasma).
            dizinler[:] = sorted(
                d for d in dizinler if d not in _ATLANAN and not _baglanti(kok / d)
            )

            for ad in bulunan:
                yol = kok / ad
                atlandi = None
                if _baglanti(yol):
                    atlandi, boyut = "baglanti", 0
                else:
                    boyut = _boyut(yol)
                    # Adlandigi halde pyvenv.cfg yoksa sanal ortam DEGILDIR.
                    if ADAYLAR[ad] in (".venv", "venv") and not _pyvenv_cfg(yol):
                        atlandi = "pyvenv-yok"
                son = _son_erisim(yol, repo)
                adaylar.append(
                    {
                        "repo": str(repo),
                        "yol": str(yol),
                        "tur": ADAYLAR[ad],
                        "boyut": boyut,
                        "son_erisim": _iso(son),
                        "yas_gun": (simdi - son) / 86400,
                        "atlandi": atlandi,
                    }
                )
    return adaylar