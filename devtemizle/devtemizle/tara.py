"""Tarama: her repoda aday klasorleri bulur (turler.py kural tablosunu kullanir).

Kurallar:
- Bir adayin ICINE girilmez: ic ice node_modules ayri sayilmaz.
- .git icine girilmez; baglanti (symlink/junction) ve pyvenv.cfg'siz sanal ortam
  ATLANIR ama raporda gorunur.
- Kanıtı olmayan eşleşme aday değildir (rapora `atlandi: "kanit-yok"` ile girer).
"""

from __future__ import annotations

import hashlib
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from .turler import Tur, kanit_var_mi, risk_durumu, tum_turler, tur_adlari, tur_ara

#: Windows FILE_ATTRIBUTE_REPARSE_POINT (junction noktasi). POSIX'te yok sayilir.
REPARSE_POINT = 0x400

#: Aday isimleri (turler.py'den gelir; CLI choices icin)
ADAYLAR = {t.ad: t.ad for t in tum_turler()}

#: Bu dizinlerin ICINE girilmez: repo govdesi, aday klasorler, baglantilar.
_ATLANAN = frozenset({".git"}) | frozenset(ADAYLAR.keys())


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


def _id_olustur(yol: str, tur_ad: str) -> str:
    """Kararlı ID: yol + tür'ün sha1'inin ilk 12 hex'i."""
    veri = (yol + tur_ad).encode("utf-8")
    return hashlib.sha1(veri).hexdigest()[:12]


def tara(repolar: list[Path], simdi: float | None = None) -> list[dict]:
    """Aday klasorleri aday dict listesi olarak dondurur (dosya sistemi degismez).

    Yeni alanlar (v2):
    - id: kararlı tanımlayıcı (yol + tür sha1[:12])
    - grup: "js" | "python" | "rust" | "jvm" | "genel"
    - risk: "guvenli" | "dikkat" (venv özel kuralı dahil)
    - yeniden: geri getirme komutu
    - atlandi: None | "baglanti" | "pyvenv-yok" | "kanit-yok"
    """
    simdi = time.time() if simdi is None else simdi
    adaylar: list[dict] = []

    for repo in repolar:
        repo = Path(repo)
        repo_str = str(repo)
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
                yol_str = str(yol)
                t = tur_ara(ad)
                if t is None:
                    continue  # olmamali

                atlandi: str | None = None
                if _baglanti(yol):
                    atlandi, boyut = "baglanti", 0
                else:
                    # Kanıt kontrolü
                    if not kanit_var_mi(ad, repo_str):
                        atlandi = "kanit-yok"
                        boyut = 0
                    else:
                        boyut = _boyut(yol)
                        # Adlandigi halde pyvenv.cfg yoksa sanal ortam DEGILDIR.
                        if ad in (".venv", "venv") and not _pyvenv_cfg(yol):
                            atlandi = "pyvenv-yok"

                son = _son_erisim(yol, repo)
                adaylar.append(
                    {
                        "repo": repo_str,
                        "yol": yol_str,
                        "tur": ad,
                        "boyut": boyut,
                        "son_erisim": _iso(son),
                        "yas_gun": (simdi - son) / 86400,
                        "atlandi": atlandi,
                    }
                )
    return adaylar