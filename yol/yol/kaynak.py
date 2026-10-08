from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

if os.name == "nt":
    try:
        import winreg
    except ImportError:
        winreg = None
    try:
        import ctypes
    except ImportError:
        ctypes = None
else:
    winreg = None
    ctypes = None

WINDOWS_HKCU_ENVIRONMENT = r"Environment"
WINDOWS_HKLM_SESSION_MANAGER_ENVIRONMENT = r"SYSTEM\\CurrentControlSet\\Control\\Session Manager\\Environment"
@dataclass(frozen=True)
class Deger:
    """Bir ortam değişkeninin değeri ve genişleme tipi."""

    metin: str
    genisler: bool  # REG_EXPAND_SZ mi (True) REG_SZ mi (False)
def _get_user_profile() -> Path:
    """Windows'ta USERPROFILE değişkenini döndürür, aksi halde geçerli kullanıcının home dizinini kullanır."""
    if os.name == "nt":
        return Path(os.environ.get("USERPROFILE", ""))
    else:
        return Path.home()
class WindowsKaynak:
    """Windows'ta kullanici HKCU\\Environment ve sistem HKLM\\SYSTEM\\CurrentControlSet\\Control\\Session Manager\\Environment kayıt defterini okur/yazar."""

    def __init__(self) -> None:
        self.kullanici_anahtar = None
        self.sistem_anahtar = None
        if winreg is not None:
            try:
                self.kullanici_anahtar = winreg.OpenKey(winreg.HKEY_CURRENT_USER, WINDOWS_HKCU_ENVIRONMENT, 0, winreg.KEY_READ | winreg.KEY_WRITE)
            except OSError:
                # Kullanıcı ortam değişikliklerine yazamıyor olabilir; salt okunur anahtar açmayı deneyin
                try:
                    self.kullanici_anahtar = winreg.OpenKey(winreg.HKEY_CURRENT_USER, WINDOWS_HKCU_ENVIRONMENT, 0, winreg.KEY_READ)
                except OSError:
                    self.kullanici_anahtar = None
            try:
                self.sistem_anahtar = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, WINDOWS_HKLM_SESSION_MANAGER_ENVIRONMENT, 0, winreg.KEY_READ | winreg.KEY_WRITE)
            except OSError:
                try:
                    self.sistem_anahtar = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, WINDOWS_HKLM_SESSION_MANAGER_ENVIRONMENT, 0, winreg.KEY_READ)
                except OSError:
                    self.sistem_anahtar = None

    def oku(self, kapsam: str) -> dict[str, Deger]:
        """Windows kayıt defterinden verilen kapsam için değerleri okur."""
        result: dict[str, Deger] = {}
        if not winreg or (kapsam == "kullanici" and not self.kullanici_anahtar) or (kapsam == "sistem" and not self.sistem_anahtar):
            return result

        anahtar = self.kullanici_anahtar if kapsam == "kullanici" else self.sistem_anahtar
        i = 0
        while True:
            try:
                ad, deger, tip = winreg.EnumValue(anahtar, i)
                metin = str(deger)
                genisler = (tip == winreg.REG_EXPAND_SZ)
                result[ad] = Deger(metin=metin, genisler=genisler)
                i += 1
            except OSError:
                break
        return result

    def yaz(self, kapsam: str, ad: str, deger: Deger) -> None:
        """Windows kayıt defterine verilen kapsam, ad ve değeri yazar."""
        if not winreg:
            return
        anahtar = self.kullanici_anahtar if kapsam == "kullanici" else self.sistem_anahtar
        if anahtar is None:
            return
        tip = winreg.REG_EXPAND_SZ if deger.genisler else winreg.REG_SZ
        try:
            winreg.SetValueEx(anahtar, ad, 0, tip, deger.metin)
        except OSError:
            pass

    def sil(self, kapsam: str, ad: str) -> None:
        """Windows kayıt defterinden verilen kapsam, ad için değeri siler."""
        if not winreg:
            return
        anahtar = self.kullanici_anahtar if kapsam == "kullanici" else self.sistem_anahtar
        if anahtar is None:
            return
        try:
            winreg.DeleteValue(anahtar, ad)
        except OSError:
            pass

    def yazilabilir(self, kapsam: str) -> bool:
        """Windows'ta verilen kapsamın değerlerini yazıp yazamayacağımızı döndürür."""
        if os.name != "nt":
            return False
        if ctypes is None:
            return False
        if kapsam == "kullanici":
            return True  # HKEY_CURRENT_USER her zaman yazılabilir
        else:  # sistem
            return ctypes.windll.shell32.IsUserAnAdmin() > 0

    def yayinla(self) -> None:
        """Windows'ta çevreleme mesajı göndererek ortam değişikliklerini bildirir."""
        if os.name != "nt" or ctypes is None:
            return
        # SendMessageTimeoutW ile HWND_BROADCAST'a WM_SETTINGCHANGE mesajı gönder
        # Parametreler: HWND_BROADCAST (0xFFFF), mesaj "Environment" (unicode)
        try:
            ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x1A, 0, "Environment", 0x80 | 0x20, 5000)
        except (AttributeError, OSError):
            pass
class DosyaKaynak:
    """JSON dosyasına okuma/yazma (kapsamlar: kullanici, sistem)."""

    def __init__(self, yol: Path | str | None = None) -> None:
        if yol is None:
            yol = _get_user_profile() / ".yol" / "ortam.json"
        self.yol = Path(yol)
        self.yol.parent.mkdir(parents=True, exist_ok=True)

    def _yükle(self) -> dict[str, dict[str, Deger]]:
        """Depolanan ortam değişkenlerini içeren sözlüğü yükler."""
        if not self.yol.exists():
            return {"kullanici": {}, "sistem": {}}
        try:
            with open(self.yol, "r", encoding="utf-8") as f:
                veri = json.load(f)
                # Geçmiş veriyle uyumluluk için eski formatı destekle
                if isinstance(veri, dict):
                    return {"kullanici": {}, "sistem": {}, **veri}
                return veri
        except (OSError, json.JSONDecodeError):
            return {"kullanici": {}, "sistem": {}}

    def _kaydet(self, veri: dict[str, dict[str, Deger]]) -> None:
        """Ortama özgü JSON dosyasını yazar."""
        try:
            with open(self.yol, "w", encoding="utf-8") as f:
                json.dump(veri, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def oku(self, kapsam: str) -> dict[str, Deger]:
        """Dosyadan verilen kapsam için değerleri okur."""
        veri = self._yükle()
        return veri.get(kapsam, {})

    def yaz(self, kapsam: str, ad: str, deger: Deger) -> None:
        """Verilen kapsam için adlı değişkeni verilen değere ayarlar."""
        veri = self._yükle()
        if "kullanici" not in veri:
            veri["kullanici"] = {}
        if "sistem" not in veri:
            veri["sistem"] = {}
        if kapsam not in veri:
            veri[kapsam] = {}
        veri[kapsam][ad] = deger
        self._kaydet(veri)

    def sil(self, kapsam: str, ad: str) -> None:
        """Verilen kapsam için adlı değişkeni siler."""
        veri = self._yükle()
        if kapsam in veri and ad in veri[kapsam]:
            del veri[kapsam][ad]
            self._kaydet(veri)

    def yazilabilir(self, kapsam: str) -> bool:
        """Dosya kaynağı her zaman yazılabilir (üzerinde çalışma korumalı yapıya sahiptir)."""
        return True

    def yayinla(self) -> None:
        """Dosya kaynağı yayım yapmak için bir mekanizmaya sahip değildir."""
        pass
class SurecKaynak:
    """Mevcut ortam değişkenlerini okur (salt okunur, geçici kapsam)."""

    def oku(self, kapsam: str) -> dict[str, Deger]:
        """Güncel ortam değişkenlerini içeren sözlüğü döndürür (salt okunur)."""
        result: dict[str, Deger] = {}
        if kapsam != "surec":
            return result
        for ad, deger in os.environ.items():
            result[ad] = Deger(metin=deger, genisler=False)
        return result

    def yaz(self, kapsam: str, ad: str, deger: Deger) -> None:
        """Süreç kaynağı üzerinde yazma işlemi desteklemez (salt okunurdur)."""
        pass

    def sil(self, kapsam: str, ad: str) -> None:
        """Süreç kaynağı üzerinde silme işlemi desteklemez (salt okunurdur)."""
        pass

    def yazilabilir(self, kapsam: str) -> bool:
        """Süreç kaynağı salt okunur olduğundan her zaman False döndürür."""
        return False

    def yayinla(self) -> None:
        """Süreç kaynağı yayım yapmak için bir mekanizmaya sahip değildir."""
        pass

def kaynak_sec(kaynak_secimi: str | None = None) -> Kaynak:
    """Verilen kaynak seçimine göre uygun Kaynak implementasyonunu döndürür.

    Argümanlar:
        kaynak_secimi: "windows", "dosya", "surec" veya "windows" hariç "null"/"none".
            "windows" değerine veya None olarak geçerli bir değer verilmediğinde, OS kontrolü yapılır.
            "YOL_KAYNAK=dosya:<yol>" ortam değişkeniyle geçerli bir dosya yolu belirtilebilir.

    Döndürülen:
        Yazma yetkisi (yazilabilir) ile birlikte oku, yaz, sil, yayinla metodlarını içeren bir Kaynak.
    """
    env = os.environ.get("YOL_KAYNAK", "").strip()
    if kaynak_secimi is not None:
        env = f"yol:{kaynak_secimi}"

    if env.startswith("dosya:"):
        yol = Path(env[6:]) if len(env) > 6 else None
        return DosyaKaynak(yol)

    if env == "surec" or (kaynak_secimi == "surec"):
        return SurecKaynak()

    if env == "windows" or (kaynak_secimi == "windows") or (kaynak_secimi is None and os.name == "nt"):
        return WindowsKaynak()

    # Varsayılan seçenek
    return SurecKaynak()
@dataclass
class Kaynak(Protocol):
    """İki kapsam için okuma, yazma, silme, varlık denetimi ve yayını destekler."""

    def oku(self, kapsam: str) -> dict[str, Deger]:
        """Verilen kapsam ("kullanici", "sistem" veya "surec") için depolanan değerleri dict olarak döndürür."""

    def yaz(self, kapsam: str, ad: str, deger: Deger) -> None:
        """Verilen kapsam için adlı değişkeni verilen değere ayarlar."""

    def sil(self, kapsam: str, ad: str) -> None:
        """Verilen kapsam için adlı değişkeni siler."""

    def yazilabilir(self, kapsam: str) -> bool:
        """Verilen kapsamdaki değişkenleri düzenleyebilecek yetkiye sahip olup olmadığımızı döndürür."""

    def yayinla(self) -> None:
        """Başka süreçler için değişikliği duyurur (örneğin Windows'ta çevreleme mesajı gönderir)."""