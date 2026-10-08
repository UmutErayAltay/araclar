"""Tarama: her repoda aday klasorleri bulur (turler.py kural tablosunu kullanir).

Kurallar:
- Bir adayin ICINE girilmez: ic ice node_modules ayri sayilmaz.
- .git icine girilmez; baglanti (symlink/junction) ve pyvenv.cfg'siz sanal ortam
  ATLANIR ama raporda gorunur.
- Kanıtı olmayan eşleşme aday değildir (rapora `atlandi: "kanit-yok"` ile girer).
  Kanit, adayin KARDES dosyalarinda aranir (repo kokunde degil).
- Git tarafindan IZLENEN dosya iceren aday atlanir (`atlandi: "izlenen-dosya"`).
"""

from __future__ import annotations

import hashlib
import os
import shutil
import stat as stat_mod
import subprocess
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

#: Yas icin bakilan, adayin ust duzeyindeki "son kullanim" izleri (varsa mtime alinir).
_YAS_IZLERI = ("pyvenv.cfg", "bin", "Scripts", ".package-lock.json", ".yarn-integrity", ".modules.yaml")

#: git komutlari icin zaman asimi (saniye)
_GIT_TIMEOUT = 5


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
    """Dizin icindeki dosya boyutlari toplami (bayt). Baglanti izlenmez.

    Sert baglantilar (ayni st_dev/st_ino) yalniz bir kez sayilir.
    """
    toplam = 0
    goruldu: set[tuple[int, int]] = set()
    for mevcut, dizinler, dosyalar in os.walk(
        dizin, topdown=True, followlinks=False, onerror=lambda _e: None
    ):
        kok = Path(mevcut)
        dizinler[:] = [d for d in dizinler if not _baglanti(kok / d)]
        for ad in dosyalar:
            try:
                st = (kok / ad).lstat()
            except OSError:
                continue  # kayboldu / erisilemedi: sayma
            anahtar = (st.st_dev, st.st_ino)
            if st.st_ino and anahtar in goruldu:
                continue  # sert baglanti: ayni veri ikinci kez sayilmaz
            if st.st_ino:
                goruldu.add(anahtar)
            toplam += st.st_size
    return toplam


def _mtime(yol: Path) -> float | None:
    try:
        return os.lstat(yol).st_mtime
    except OSError:
        return None


def _son_commit_zamani(repo: Path) -> float | None:
    """Reponun son commit zamani (Unix sn); git yoksa / hata varsa None. Timeout 5 sn."""
    if shutil.which("git") is None:
        return None
    try:
        sonuc = subprocess.run(
            ["git", "-C", str(repo), "log", "-1", "--format=%ct"],
            capture_output=True, text=True, timeout=_GIT_TIMEOUT, shell=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if sonuc.returncode != 0:
        return None
    try:
        return float(sonuc.stdout.strip())
    except ValueError:
        return None


def _son_erisim(aday: Path, repo: Path, son_commit: float | None = None) -> float:
    """Adayin son kullanildigi an (en yeni zaman).

    Adayin kendi mtime'i, adayin ust duzey izleri (pyvenv.cfg, bin, Scripts, ...),
    .git/index, .git/HEAD ve reponun son commit zamani birlikte degerlendirilir.
    """
    zamanlar = []
    for kaynak in [aday] + [aday / ad for ad in _YAS_IZLERI]:
        z = _mtime(kaynak)
        if z is not None:
            zamanlar.append(z)
    for ad in ("index", "HEAD"):
        z = _mtime(repo / ".git" / ad)  # yok (veya .git bir dosya) ise None
        if z is not None:
            zamanlar.append(z)
    if son_commit is not None:
        zamanlar.append(son_commit)
    return max(zamanlar) if zamanlar else _mtime(aday) or 0.0


def _izlenen_dosya_var_mi(yol: Path, repo: Path) -> bool:
    """Adayda git tarafindan izlenen dosya var mi?

    git yoksa, repo git deposu degilse veya cikti bossa False (atlanmaz).
    Zaman asimi: dogrulanamadi -> True (guvenli taraf: atlanir).
    """
    if shutil.which("git") is None:
        return False
    try:
        rel = yol.relative_to(repo).as_posix()
    except ValueError:
        return False
    try:
        sonuc = subprocess.run(
            ["git", "-C", str(repo), "ls-files", "--", rel],
            capture_output=True, text=True, timeout=_GIT_TIMEOUT, shell=False,
        )
    except subprocess.TimeoutExpired:
        return True
    except OSError:
        return False
    if sonuc.returncode != 0:
        return False
    return bool(sonuc.stdout.strip())


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
    - atlandi: None | "baglanti" | "pyvenv-yok" | "kanit-yok" | "izlenen-dosya"
    """
    simdi = time.time() if simdi is None else simdi
    adaylar: list[dict] = []

    for repo in repolar:
        repo = Path(repo)
        repo_str = str(repo)
        son_commit = _son_commit_zamani(repo)
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
                    # Kanıt kontrolü: kardes dosyalar (adayin ust dizini)
                    if not kanit_var_mi(ad, str(kok)):
                        atlandi = "kanit-yok"
                        boyut = 0
                    elif _izlenen_dosya_var_mi(yol, repo):
                        atlandi = "izlenen-dosya"
                        boyut = 0
                    else:
                        boyut = _boyut(yol)
                        # Adlandigi halde pyvenv.cfg yoksa sanal ortam DEGILDIR.
                        if ad in (".venv", "venv") and not _pyvenv_cfg(yol):
                            atlandi = "pyvenv-yok"

                son = _son_erisim(yol, repo, son_commit)
                adaylar.append(
                    {
                        "repo": repo_str,
                        "yol": yol_str,
                        "tur": ad,
                        "boyut": boyut,
                        "son_erisim": _iso(son),
                        "yas_gun": max(0.0, (simdi - son) / 86400),
                        "atlandi": atlandi,
                    }
                )
    return adaylar
