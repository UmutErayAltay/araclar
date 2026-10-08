"""Ortam degiskeni kaynaklari: Windows kayit defteri, JSON dosyasi, surec ortami.

Kural: okuma/yazma hatasi YUTULMAZ, `KaynakHatasi` olarak yukari cikar; degisiklik
katmani buna gore geri yukleme yapar. `winreg`/`ctypes` yalniz Windows'ta yuklenir,
modul her platformda import edilebilir.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

KULLANICI = "kullanici"
SISTEM = "sistem"
SUREC = "surec"

_HKCU_YOL = "Environment"
_HKLM_YOL = r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"


class KaynakHatasi(RuntimeError):
    """Kaynak okunamadi/yazilamadi."""


@dataclass(frozen=True)
class Deger:
    metin: str
    genisler: bool = False  # REG_EXPAND_SZ (True) / REG_SZ (False)

    def sozluk(self) -> dict:
        return {"metin": self.metin, "genisler": self.genisler}

    @classmethod
    def sozlukten(cls, veri: dict) -> "Deger":
        return cls(str(veri["metin"]), bool(veri.get("genisler", False)))


class Kaynak(Protocol):
    ad: str
    ayirici: str          # PATH ayirici (";" Windows, ":" POSIX)
    windows: bool         # PATHEXT ve buyuk/kucuk harf duyarsizligi uygulanir mi

    def kapsamlar(self) -> tuple[str, ...]: ...
    def oku(self, kapsam: str) -> dict[str, Deger]: ...
    def yaz(self, kapsam: str, ad: str, deger: Deger) -> None: ...
    def sil(self, kapsam: str, ad: str) -> None: ...
    def yazilabilir(self, kapsam: str) -> bool: ...
    def yayinla(self) -> None: ...


def _kapsam_denetle(kaynak: Kaynak, kapsam: str) -> None:
    if kapsam not in kaynak.kapsamlar():
        raise KaynakHatasi(f"bilinmeyen kapsam: {kapsam!r}")


# --------------------------------------------------------------------- Windows

class WindowsKaynak:
    """HKCU\\Environment (kullanici) ve HKLM ...\\Session Manager\\Environment (sistem)."""

    ad = "windows"
    ayirici = ";"
    windows = True

    def __init__(self) -> None:
        import winreg  # noqa: F401  (yalniz Windows)

    def kapsamlar(self) -> tuple[str, ...]:
        return (SISTEM, KULLANICI)

    def _anahtar(self, kapsam: str, yaz: bool):
        import winreg

        _kapsam_denetle(self, kapsam)
        kok, yol = (
            (winreg.HKEY_CURRENT_USER, _HKCU_YOL) if kapsam == KULLANICI
            else (winreg.HKEY_LOCAL_MACHINE, _HKLM_YOL)
        )
        erisim = winreg.KEY_READ | (winreg.KEY_SET_VALUE if yaz else 0)
        try:
            return winreg.OpenKey(kok, yol, 0, erisim)
        except OSError as exc:
            raise KaynakHatasi(f"{kapsam} anahtari acilamadi: {exc}") from exc

    def oku(self, kapsam: str) -> dict[str, Deger]:
        import winreg

        sonuc: dict[str, Deger] = {}
        with self._anahtar(kapsam, yaz=False) as anahtar:
            i = 0
            while True:
                try:
                    ad, deger, tip = winreg.EnumValue(anahtar, i)
                except OSError:
                    break  # ERROR_NO_MORE_ITEMS
                i += 1
                if tip in (winreg.REG_SZ, winreg.REG_EXPAND_SZ):
                    sonuc[ad] = Deger(str(deger), tip == winreg.REG_EXPAND_SZ)
                # Diger tipler (DWORD vb.) gosterilmez ve hic yazilmaz.
        return sonuc

    def yaz(self, kapsam: str, ad: str, deger: Deger) -> None:
        import winreg

        tip = winreg.REG_EXPAND_SZ if deger.genisler else winreg.REG_SZ
        try:
            with self._anahtar(kapsam, yaz=True) as anahtar:
                winreg.SetValueEx(anahtar, ad, 0, tip, deger.metin)
        except OSError as exc:
            raise KaynakHatasi(f"{kapsam}/{ad} yazilamadi: {exc}") from exc

    def sil(self, kapsam: str, ad: str) -> None:
        import winreg

        try:
            with self._anahtar(kapsam, yaz=True) as anahtar:
                winreg.DeleteValue(anahtar, ad)
        except FileNotFoundError:
            return  # zaten yok
        except OSError as exc:
            raise KaynakHatasi(f"{kapsam}/{ad} silinemedi: {exc}") from exc

    def yazilabilir(self, kapsam: str) -> bool:
        if kapsam == KULLANICI:
            return True
        import ctypes

        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except (AttributeError, OSError):
            return False

    def yayinla(self) -> None:
        """WM_SETTINGCHANGE("Environment"): yeni acilan surecler degisikligi gorur."""
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        gonder = user32.SendMessageTimeoutW
        gonder.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPCWSTR,
                           wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t)]
        gonder.restype = ctypes.c_size_t
        sonuc = ctypes.c_size_t(0)
        # HWND_BROADCAST, WM_SETTINGCHANGE, SMTO_ABORTIFHUNG, 5 sn
        gonder(0xFFFF, 0x001A, 0, "Environment", 0x0002, 5000, ctypes.byref(sonuc))


# ----------------------------------------------------------------------- Dosya

class DosyaKaynak:
    """JSON dosyasi: {"ayirici": ";", "windows": true, "kullanici": {AD: {metin, genisler}}, "sistem": {...}}.

    Testler, Linux demosu ve ekran goruntuleri icin. Yazma atomiktir.
    """

    ad = "dosya"

    def __init__(self, yol: Path | str) -> None:
        self.yol = Path(yol).expanduser()
        veri = self._yukle()
        self.ayirici = str(veri.get("ayirici", os.pathsep))
        self.windows = bool(veri.get("windows", os.name == "nt"))

    def kapsamlar(self) -> tuple[str, ...]:
        return (SISTEM, KULLANICI)

    def _yukle(self) -> dict:
        if not self.yol.exists():
            return {}
        try:
            return json.loads(self.yol.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise KaynakHatasi(f"{self.yol} okunamadi: {exc}") from exc

    def _kaydet(self, veri: dict) -> None:
        self.yol.parent.mkdir(parents=True, exist_ok=True)
        fd, gecici = tempfile.mkstemp(dir=self.yol.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as akim:
                json.dump(veri, akim, ensure_ascii=False, indent=2)
            os.replace(gecici, self.yol)
        except BaseException:
            Path(gecici).unlink(missing_ok=True)
            raise

    def oku(self, kapsam: str) -> dict[str, Deger]:
        _kapsam_denetle(self, kapsam)
        return {ad: Deger.sozlukten(d) for ad, d in self._yukle().get(kapsam, {}).items()}

    def yaz(self, kapsam: str, ad: str, deger: Deger) -> None:
        _kapsam_denetle(self, kapsam)
        veri = self._yukle()
        veri.setdefault(kapsam, {})[ad] = deger.sozluk()
        try:
            self._kaydet(veri)
        except OSError as exc:
            raise KaynakHatasi(f"{kapsam}/{ad} yazilamadi: {exc}") from exc

    def sil(self, kapsam: str, ad: str) -> None:
        _kapsam_denetle(self, kapsam)
        veri = self._yukle()
        if ad in veri.get(kapsam, {}):
            del veri[kapsam][ad]
            try:
                self._kaydet(veri)
            except OSError as exc:
                raise KaynakHatasi(f"{kapsam}/{ad} silinemedi: {exc}") from exc

    def yazilabilir(self, kapsam: str) -> bool:
        return kapsam in self.kapsamlar()

    def yayinla(self) -> None:
        return None


# ----------------------------------------------------------------------- Surec

class SurecKaynak:
    """Calisan surecin ortami; salt okunur, tek kapsam."""

    ad = "surec"
    ayirici = os.pathsep
    windows = os.name == "nt"

    def kapsamlar(self) -> tuple[str, ...]:
        return (SUREC,)

    def oku(self, kapsam: str) -> dict[str, Deger]:
        _kapsam_denetle(self, kapsam)
        return {ad: Deger(deger) for ad, deger in os.environ.items()}

    def yaz(self, kapsam: str, ad: str, deger: Deger) -> None:
        raise KaynakHatasi("surec ortami salt okunur")

    def sil(self, kapsam: str, ad: str) -> None:
        raise KaynakHatasi("surec ortami salt okunur")

    def yazilabilir(self, kapsam: str) -> bool:
        return False

    def yayinla(self) -> None:
        return None


def kaynak_sec(secim: str | None = None) -> Kaynak:
    """`secim` > YOL_KAYNAK ("dosya:<yol>" | "surec" | "windows") > platform varsayilani."""
    secim = secim or os.environ.get("YOL_KAYNAK", "").strip()
    if secim.startswith("dosya:"):
        return DosyaKaynak(secim[len("dosya:"):])
    if secim == "surec":
        return SurecKaynak()
    if secim == "windows" or (not secim and os.name == "nt"):
        return WindowsKaynak()
    if secim:
        raise KaynakHatasi(f"bilinmeyen YOL_KAYNAK: {secim!r} (dosya:<yol> | surec | windows)")
    return SurecKaynak()
