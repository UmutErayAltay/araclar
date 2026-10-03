"""Silme: yasina/ture gore adaylari siler; varsayilan KURU CALISTIRMA.

Guvenlik:
- `uygula=False` ise HICBIR dosya sistemi degisikligi yapilmaz.
- Silmeden once adayin `resolve()` yolu repo kokunun altinda mi dogrulanir.
"""

from __future__ import annotations

import os
import shutil
import stat as stat_mod
from pathlib import Path

from .tara import tara


def _salt_okunur_sifirla(func, yol, _hata) -> None:
    """shutil.rmtree onerror shimi: yazma izni verip islemi bir kez daha dene."""
    os.chmod(yol, stat_mod.S_IWRITE | stat_mod.S_IREAD)
    func(yol)


def sil(
    repolar: list[Path],
    uygula: bool,
    yas: float = 7,
    turler: list[str] | None = None,
    simdi: float | None = None,
) -> dict:
    """Adaylari tazeden tarar ve (uygula ise) siler.

    Donus anahtarlari: silinecek / silindi / silinemedi / atlanan / bosalan_bayt.
    """
    sonuc = {"silinecek": [], "silindi": [], "silinemedi": [], "atlanan": [], "bosalan_bayt": 0}

    for aday in tara(repolar, simdi):
        yol = Path(aday["yol"])
        if aday["atlandi"]:  # baglanti veya pyvenv-yok: aday degil
            sonuc["atlanan"].append({"yol": str(yol), "neden": aday["atlandi"]})
            continue
        if turler is not None and aday["tur"] not in turler:
            sonuc["atlanan"].append({"yol": str(yol), "neden": "tur-disi"})
            continue
        if yas > 0 and aday["yas_gun"] < yas:  # yas=0 -> yas filtresi kapali
            sonuc["atlanan"].append({"yol": str(yol), "neden": "yeni"})
            continue

        sonuc["silinecek"].append(aday)
        if not uygula:
            continue  # kuru calistirma: dosya sistemine dokunma

        repo = Path(aday["repo"])
        try:
            # Guvenlik: yol repo kokunun altinda mi?
            yol.resolve().relative_to(repo.resolve())
        except (ValueError, OSError):
            sonuc["silinemedi"].append({"yol": str(yol), "neden": "repo-disi"})
            continue
        try:
            if yol.is_symlink() or not yol.is_dir():
                os.rmdir(yol)  # savunma: baglanti asla buraya girmemeli
            else:
                shutil.rmtree(yol, onerror=_salt_okunur_sifirla)
        except (PermissionError, OSError) as exc:
            neden = f"kilitli: {' '.join(str(exc).split())}"
            sonuc["silinemedi"].append({"yol": str(yol), "neden": neden})
            continue
        sonuc["silindi"].append(aday)
        sonuc["bosalan_bayt"] += aday["boyut"]

    return sonuc