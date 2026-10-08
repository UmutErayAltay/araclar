from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from yol.kaynak import Deger, Kaynak, kaynak_sec
@dataclass
class Degisiklik:
    """Bir ortam değişkeni için bir değişiklik (ekle, sil, değiştir)."""

    kapsam: str
    ad: str
    eski: Deger | None
    yeni: Deger | None
class Degisiklikler:
    """Birçok Degisiklik'ü yönetmek için yardımcı sınıf."""

    def __init__(self, degisiklikler: list[Degisiklik]) -> None:
        self.degisiklikler = degisiklikler

    @property
    def sayi(self) -> int:
        return len(self.degisiklikler)

    def ozet(self) -> str:
        eksi, artı, degisti = 0, 0, 0
        for d in self.degisiklikler:
            if d.yeni is None:
                eksi += 1
            elif d.eski is None:
                artı += 1
            else:
                degisti += 1
        return f"{eksi} kaldırıldı, {artı} eklendi, {degisti} değiştirildi"

    def to_dict(self) -> list[dict[str, Any]]:
        sonuc = []
        for d in self.degisiklikler:
            sonuc.append({
                "kapsam": d.kapsam,
                "ad": d.ad,
                "eski": {"metin": d.eski.metin, "genisler": d.eski.genisler} if d.eski else None,
                "yeni": {"metin": d.yeni.metin, "genisler": d.yeni.genisler} if d.yeni else None
            })
        return sonuc

    @classmethod
    def from_dict(cls, veri: list[dict[str, Any]]) -> Degisiklikler:
        degisiklikler: list[Degisiklik] = []
        for item in veri:
            eski = Deger(**item["eski"]) if item["eski"] else None
            yeni = Deger(**item["yeni"]) if item["yeni"] else None
            degisiklikler.append(Degisiklik(
                kapsam=item["kapsam"],
                ad=item["ad"],
                eski=eski,
                yeni=yeni
            ))
        return cls(degisiklikler)
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
        """En son 30 yedek dosyasını tarih bazında sıralayarak döndürür."""
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
def _beklenmeyen_degisiklik_kontrolu(kaynak: Kaynak, degisiklik: Degisiklik) -> bool:
    """Bir değişikliğin, kaynak alt komut tarafından değiştirilip değiştirilmediğini kontrol eder."""
    if degisiklik.eski is None:
        return False  # Ekleme — zaten mevcut olmalı
    mevcut = kaynak.oku(degisiklik.kapsam).get(degisiklik.ad)
    if mevcut is None:
        return True  # Değişken silindi
    if mevcut.metin != degisiklik.eski.metin or mevcut.genisler != degisiklik.eski.genisler:
        return True  # Değişken değiştirildi
    return False
def uygulama_yap(kaynak: Kaynak, degisiklikler: Degisiklikler, gunluk: Gunluk, yedek_deposu: YedekDeposu) -> list[Degisiklik]:
    """Değişiklikleri kaynak üzerinde uygular ve geri alma için yedek alır.

    Argümanlar:
        kaynak: Temel Kaynak implementasyonu
        degisiklikler: Uygulanacak değişiklikler
        gunluk: İşlemleri günlüğe kaydetmek için
        yedek_deposu: Yedek almak/alarmak için

    Döndürülen:
        Başarıyla uygulanan değişikliklerin listesi.

    Oluşturan:
        DegisiklikHatasi: Beklenmeyen bir değişiklik tespit edildiğinde.
    """
    uygulamalanan: list[Degisiklik] = []

    # Önce her bir değişikliğin eski halini taze olarak okur
    degisiklik_sözlük: dict[str, dict[str, Degisiklik]] = {}
    for d in degisiklikler.degisiklikler:
        key = f"{d.kapsam}:{d.ad}"
        degisiklik_sözlük[key] = d

    # Her kapsamdaki mevcut tüm değişkenleri bir kerede okur
    mevcut_degerler: dict[str, dict[str, Deger]] = {}
    for kapsam in ["kullanici", "sistem"]:
        mevcut_degerler[kapsam] = kaynak.oku(kapsam)

    # Her bir değişikliği uygula
    for d in degisiklikler.degisiklikler:
        # Beklenmeyen değişiklik kontrolü
        if _beklenmeyen_degisiklik_kontrolu(kaynak, d):
            raise DegisiklikHatasi(
                f"Beklenmeyen değişiklik: {d.kapsam}:{d.ad} siz düzenlerken başka bir alt komut tarafından değiştirildi."
            )

        # Yedek
        if d == degisiklikler.degisiklikler[0]:  # Sadece ilk değişiklik için yedek al (tüm bir durum)
            yedek_dosya = yedek_deposu.en_son_yedek()
            if yedek_dosya is None:
                # İlk yedek — tüm mevcut değişkenleri al
                yedek_dosya = Yedek(f"{int(time.time())}", mevcut_degerler)
                yedek_deposu.ekle(yedek_dosya)

        # İşlemi uygula
        if d.yeni is None:
            kaynak.sil(d.kapsam, d.ad)
            gunluk.ekle(d.kapsam, d.ad, "sil")
        else:
            kaynak.yaz(d.kapsam, d.ad, d.yeni)
            gunluk.ekle(d.kapsam, d.ad, "yaz")

        uygulamalanan.append(d)

    # Yayın
    kaynak.yayınla()
    return uygulamalanan
class DegisiklikHatasi(Exception):
    """Beklenmeyen bir değişiklik tespit edildiğinde oluşturulur."""
    pass