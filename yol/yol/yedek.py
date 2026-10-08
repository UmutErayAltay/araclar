from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from yol.kaynak import Deger
class Yedek:
    """Tek bir yedek (anlık görüntü) için veri yapısı."""

    def __init__(self, id: str, kapsamlar: dict[str, dict[str, Deger]]) -> None:
        self.id = id
        self.kapsamlar = kapsamlar  # {"kullanici": {...}, "sistem": {...}}

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kapsamlar": {
                kapsam: {ad: {"metin": d.metin, "genisler": d.genisler} for ad, d in degerler.items()}
                for kapsam, degerler in self.kapsamlar.items()
            }
        }

    @classmethod
    def from_dict(cls, veri: dict[str, Any]) -> "Yedek":
        kapsamlar: dict[str, dict[str, Deger]] = {}
        for kapsam, degerler in veri.get("kapsamlar", {}).items():
            kapsamlar[kapsam] = {ad: Deger(**d) for ad, d in degerler.items()}
        return cls(veri["id"], kapsamlar)
class YedekDeposu:
    """Çoklu Yedek'i yöneten sınıf (en son 30)."""

    def __init__(self, yedek_dizini: Path | str | None = None) -> None:
        if yedek_dizini is None:
            yedek_dizini = Path.home() / ".yol" / "yedek"
        self.yedek_dizini = Path(yedek_dizini)
        self.yedek_dizini.mkdir(parents=True, exist_ok=True)

    def _yedek_dosya_yolu(self, id: str) -> Path:
        return self.yedek_dizini / f"{id}.json"

    def en_son_30_yedek(self) -> list["Yedek"]:
        """En son 30 yedek dosyasını ID bazında sıralayarak döndürür (en son olan en başta)."""
        import glob

        dosyalar = sorted(glob.glob(str(self.yedek_dizini / "*.json")), reverse=True)
        yedekler: list["Yedek"] = []
        for dosya in dosyalar[:30]:
            try:
                with open(dosya, "r", encoding="utf-8") as f:
                    veri = json.load(f)
                    yedekler.append(Yedek.from_dict(veri))
            except (OSError, json.JSONDecodeError):
                continue
        # ID'ye göre (int olarak) azalan sırada sırala, int dönüştürülemezse atla
        def _id_key(y: "Yedek") -> int:
            try:
                return int(y.id)
            except ValueError:
                # Hata durumunda varsayılan büyük bir değer döndür
                return 9999999

        yedekler.sort(key=_id_key, reverse=True)
        return yedekler

    def en_son_yedek(self) -> Yedek | None:
        yedekler = self.en_son_30_yedek()
        return yedekler[0] if yedekler else None

    def ekle(self, yedek: Yedek) -> None:
        """Yeni bir yedek dosyasını yazar. Var olanı üzerine yazar."""
        dosya = self._yedek_dosya_yolu(yedek.id)
        try:
            with open(dosya, "w", encoding="utf-8") as f:
                json.dump(yedek.to_dict(), f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def kaldir(self, id: str) -> None:
        """Belirtilen yedeği kaldırır."""
        dosya = self._yedek_dosya_yolu(id)
        try:
            dosya.unlink()
        except OSError:
            pass

    def geri_al(self, id: str) -> dict[str, dict[str, Deger]]:
        """Belirtilen yedekten farkı önizemek için durumunu döndürür."""
        hedef_yedek = None
        for y in self.en_son_30_yedek():
            if y.id == id:
                hedef_yedek = y
                break
        if hedef_yedek is None:
            return {}
        mevcut_yedek = self.en_son_yedek()
        fark: dict[str, dict[str, Deger]] = {}
        for kapsam in ["kullanici", "sistem"]:
            mevcut_kapsam = mevcut_yedek.kapsamlar.get(kapsam, {}) if mevcut_yedek else {}
            hedef_kapsam = hedef_yedek.kapsamlar.get(kapsam, {})
            # Farkı yalnızca hedef yedeğin mevcut yedeğe göre olmadığı kapsamdaki değişkenler için hesapla
            if mevcut_kapsam != hedef_kapsam:
                fark[kapsam] = hedef_kapsam
        return fark

from datetime import datetime

class Gunluk:
    """Yol işlemlerinin CLI olmayan günlük kaydı (JSONL)."""

    def __init__(self, gunluk_dosya: Path | str | None = None) -> None:
        if gunluk_dosya is None:
            gunluk_dosya = Path.home() / ".yol" / "gunluk.jsonl"
        self.gunluk_dosya = Path(gunluk_dosya)
        self.gunluk_dosya.parent.mkdir(parents=True, exist_ok=True)

    def ekle(self, kapsam: str, ad: str, eylem: str) -> None:
        """Bir günlük kaydı ekler."""
        kayit = {
            "zaman": datetime.utcnow().isoformat() + "Z",
            "kapsam": kapsam,
            "ad": ad,
            "eylem": eylem
        }
        try:
            with open(self.gunluk_dosya, "a", encoding="utf-8") as f:
                f.write(json.dumps(kayit) + "\n")
        except OSError:
            pass