"""Leitner kutulu tekrar kart depo (JSON dosyası).

ARALIKLAR: gün cinsinden tekrar aralıkları.
Depo: atomik yazma, POSIX'te 0o600, bozuk dosya asla sessizce ezilmez.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass, asdict
from datetime import date, timedelta
from pathlib import Path
from typing import Sequence


ARALIKLAR = (1, 3, 7, 14, 30, 60)  # gün


class DepoHatasi(Exception):
    """Depo işlemlerinde oluşan hata (bozuk JSON, yanlış tür, eksik alan)."""


@dataclass
class Kart:
    """Tekrar kartı."""

    id: str
    kaynak: str
    kaynak_sha256: str
    soru: str
    cevap: str
    kutu: int = 0
    sonraki: str = ""  # ISO tarih "YYYY-MM-DD"
    son_gosterim: str | None = None
    zor_sayisi: int = 0


class Depo:
    """Kart deposu (JSON dosya)."""

    def __init__(self, yol: Path) -> None:
        self._yol = Path(yol)
        self.kartlar: list[Kart] = []
        self._load()

    @classmethod
    def varsayilan(cls) -> "Depo":
        """Varsayılan depo yolu: $TEKRAR_DIR/kartlar.json, yoksa ~/.tekrar/kartlar.json."""
        tekrardir = os.environ.get("TEKRAR_DIR")
        if tekrardir:
            yol = Path(tekrardir) / "kartlar.json"
        else:
            yol = Path.home() / ".tekrar" / "kartlar.json"
        return cls(yol)

    def _load(self) -> None:
        """Dosyayı okur, doğrular. Bozuksa DepoHatasi fırlatır (yazmaz)."""
        if not self._yol.is_file():
            self.kartlar = []
            return

        try:
            raw = self._yol.read_text(encoding="utf-8")
        except OSError as exc:
            raise DepoHatasi(f"Depo dosyası okunamadı: {self._yol}") from exc

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise DepoHatasi(f"Depo dosyası bozuk JSON: {self._yol} ({exc})") from exc

        # Şema doğrulama
        if not isinstance(data, dict):
            raise DepoHatasi(f"Depo kök nesne bir dict değil: {self._yol}")
        if data.get("surum") != 1:
            raise DepoHatasi(f"Depo sürümü desteklenmiyor: {self._yol}")

        kartlar_data = data.get("kartlar")
        if not isinstance(kartlar_data, list):
            raise DepoHatasi(f"Depo 'kartlar' alanı bir liste değil: {self._yol}")

        kartlar: list[Kart] = []
        for i, k in enumerate(kartlar_data):
            if not isinstance(k, dict):
                raise DepoHatasi(f"Kart #{i} bir dict değil: {self._yol}")

            # Zorunlu alanlar: KATI tür denetimi (dönüştürme yok; hata mesajına değer yazılmaz)
            for alan in ("id", "kaynak", "kaynak_sha256", "soru", "cevap", "sonraki"):
                if not isinstance(k.get(alan), str):
                    raise DepoHatasi(f"Kart #{i} '{alan}' eksik ya da metin değil: {self._yol}")
            kutu = k.get("kutu")
            if not isinstance(kutu, int) or isinstance(kutu, bool) or not 0 <= kutu < len(ARALIKLAR):
                raise DepoHatasi(f"Kart #{i} 'kutu' geçersiz: {self._yol}")
            zor_sayisi = k.get("zor_sayisi", 0)
            if not isinstance(zor_sayisi, int) or isinstance(zor_sayisi, bool) or zor_sayisi < 0:
                raise DepoHatasi(f"Kart #{i} 'zor_sayisi' geçersiz: {self._yol}")
            kart_id, kaynak, kaynak_sha256 = k["id"], k["kaynak"], k["kaynak_sha256"]
            soru, cevap, sonraki = k["soru"], k["cevap"], k["sonraki"]
            son_gosterim = k.get("son_gosterim")

            for alan, deger in (("sonraki", sonraki), ("son_gosterim", son_gosterim)):
                if alan == "son_gosterim" and deger is None:
                    continue
                try:
                    date.fromisoformat(deger)
                except (TypeError, ValueError) as exc:
                    raise DepoHatasi(f"Kart #{i} '{alan}' geçersiz tarih: {self._yol}") from exc

            kartlar.append(Kart(
                id=kart_id,
                kaynak=kaynak,
                kaynak_sha256=kaynak_sha256,
                soru=soru,
                cevap=cevap,
                kutu=kutu,
                sonraki=sonraki,
                son_gosterim=son_gosterim,
                zor_sayisi=zor_sayisi,
            ))

        self.kartlar = kartlar

    def kaydet(self) -> None:
        """Atomik yaz: tmp dosya + os.replace; üst klasörü oluştur; POSIX'te 0o600."""
        self._yol.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "surum": 1,
            "kartlar": [asdict(k) for k in self.kartlar],
        }
        json_text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))

        # Atomik yazım
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=self._yol.parent,
            delete=False,
            prefix=".kartlar.",
            suffix=".tmp",
        ) as tmp:
            tmp.write(json_text)
            tmp_path = Path(tmp.name)

        try:
            # POSIX'te 0o600
            if hasattr(os, "chmod"):
                try:
                    os.chmod(tmp_path, 0o600)
                except OSError:
                    pass
            os.replace(tmp_path, self._yol)
        except Exception:
            # Hata durumunda tmp'yi temizle
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise

    def ekle(self, kaynak: str, kaynak_sha256: str, ciftler: Sequence[tuple[str, str]], bugun: date) -> list[Kart]:
        """Yeni kartları ekler. Aynı id zaten varsa atlar. Gerçekten eklenenleri döndürür."""
        eklenenler: list[Kart] = []
        mevcut_idler = {k.id for k in self.kartlar}

        for soru, cevap in ciftler:
            # id = sha256((kaynak + "\n" + soru).encode()).hexdigest()[:12]
            hash_input = (kaynak + "\n" + soru).encode()
            kart_id = hashlib.sha256(hash_input).hexdigest()[:12]

            if kart_id in mevcut_idler:
                continue

            kart = Kart(
                id=kart_id,
                kaynak=kaynak,
                kaynak_sha256=kaynak_sha256,
                soru=soru,
                cevap=cevap,
                kutu=0,
                sonraki=bugun.isoformat(),
                son_gosterim=None,
                zor_sayisi=0,
            )
            self.kartlar.append(kart)
            mevcut_idler.add(kart_id)
            eklenenler.append(kart)

        return eklenenler

    def kaynak_degisti_mi(self, kaynak: str, sha256: str) -> bool:
        """Kaynağın hiç kartı yoksa True; kartların kaynak_sha256'sı farklıysa True."""
        kaynak_kartlari = [k for k in self.kartlar if k.kaynak == kaynak]
        if not kaynak_kartlari:
            return True
        return any(k.kaynak_sha256 != sha256 for k in kaynak_kartlari)

    def kaynagi_sil(self, kaynak: str) -> int:
        """Belirli kaynağa ait tüm kartları silir. Silinen sayısını döndürür."""
        onceki = len(self.kartlar)
        self.kartlar = [k for k in self.kartlar if k.kaynak != kaynak]
        return onceki - len(self.kartlar)

    def vadesi_gelen(self, bugun: date, adet: int) -> list[Kart]:
        """Sonraki <= bugun olan kartları döndürür.

        Sıralama: sonraki artan, sonra kutu artan, sonra id.
        Aynı kaynaktan en çok 2 kart. Toplam adet ile sınırlı.
        adet <= 0 ise boş liste.
        """
        if adet <= 0:
            return []

        bugun_str = bugun.isoformat()
        uygun = [k for k in self.kartlar if k.sonraki <= bugun_str]

        # Sıralama: sonraki artan, sonra kutu artan, sonra id
        uygun.sort(key=lambda k: (k.sonraki, k.kutu, k.id))

        # Aynı kaynaktan en çok 2 kart
        kaynak_sayac: dict[str, int] = {}
        secilen: list[Kart] = []

        for kart in uygun:
            if kaynak_sayac.get(kart.kaynak, 0) >= 2:
                continue
            kaynak_sayac[kart.kaynak] = kaynak_sayac.get(kart.kaynak, 0) + 1
            secilen.append(kart)
            if len(secilen) >= adet:
                break

        return secilen

    def goruldu(self, kart_id: str, bugun: date) -> None:
        """Kartı görüldü olarak işaretler: kutu++, sonraki = bugun + aralık, son_gosterim = bugun."""
        for kart in self.kartlar:
            if kart.id == kart_id:
                aralik = ARALIKLAR[kart.kutu] if kart.kutu < len(ARALIKLAR) else ARALIKLAR[-1]
                kart.sonraki = (bugun + timedelta(days=aralik)).isoformat()
                kart.kutu = min(kart.kutu + 1, len(ARALIKLAR) - 1)
                kart.son_gosterim = bugun.isoformat()
                break  # Bilinmeyen id: sessizce geç

    def zor(self, kart_id: str, bugun: date) -> bool:
        """Kartı zor olarak işaretler: kutu=0, sonraki=bugun+1, zor_sayisi++, son_gosterim=bugun.

        Kart bulunursa True, bulunamazsa False döndürür.
        """
        for kart in self.kartlar:
            if kart.id == kart_id:
                kart.kutu = 0
                kart.sonraki = (bugun + timedelta(days=1)).isoformat()
                kart.zor_sayisi += 1
                kart.son_gosterim = bugun.isoformat()
                return True
        return False

    def ozet(self, bugun: date) -> dict:
        """Depo özeti: toplam, vadesi_gelen, kutular başına sayı, kaynak_sayisi."""
        bugun_str = bugun.isoformat()
        vadesi_gelen_sayisi = sum(1 for k in self.kartlar if k.sonraki <= bugun_str)

        kutular: dict[int, int] = {}
        for k in self.kartlar:
            kutular[k.kutu] = kutular.get(k.kutu, 0) + 1

        kaynak_sayisi = len({k.kaynak for k in self.kartlar})

        return {
            "toplam": len(self.kartlar),
            "vadesi_gelen": vadesi_gelen_sayisi,
            "kutular": kutular,
            "kaynak_sayisi": kaynak_sayisi,
        }