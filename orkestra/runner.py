"""Çalıştırıcı arayüzü.

`Runner` protokolü dalga B'de `ClaudeRunner` ile doldurulacak; gerçek `claude`
ÇAĞRILMAZ. `FakeRunner` ürünün parçası olan senaryolu (kurgusal) çalıştırıcıdır.
"""

from __future__ import annotations

from typing import Callable, Protocol, runtime_checkable

from .models import RunSonuc, Task


@runtime_checkable
class Runner(Protocol):
    def calistir(self, task: Task) -> RunSonuc:
        """Görevi çalıştırır ve sonucu döndürür."""
        ...


class FakeRunner:
    """Senaryoya göre sonuç üreten kurgusal çalıştırıcı.

    `senaryo`: `basari` (varsayılan) | `hata` | `onay-gerekli` | `istisna`
    Alternatif olarak `calistir_ile` tek seferlik bir taklit verilebilir.
    """

    SENARYOLAR = ("basari", "hata", "onay-gerekli", "istisna")

    def __init__(
        self,
        senaryo: str = "basari",
        cikti_on: str = "Kurgusal calistirma tamamlandi.",
        kanit_on: list[str] | None = None,
        calistir_ile: Callable[[Task], RunSonuc] | None = None,
    ):
        if calistir_ile is None and senaryo not in self.SENARYOLAR:
            raise ValueError(f"bilinmeyen senaryo: {senaryo}")
        self.senaryo = senaryo
        self.cikti_on = cikti_on
        self.kanit_on = list(kanit_on) if kanit_on is not None else ["/kurgusal/kanit.png"]
        self._calistir_ile = calistir_ile
        self.gorevler: list[Task] = []

    def calistir(self, task: Task) -> RunSonuc:
        self.gorevler.append(task)
        if self._calistir_ile is not None:
            return self._calistir_ile(task)
        if self.senaryo == "basari":
            return RunSonuc(cikis_kodu=0, cikti=self.cikti_on, kanit_yollari=list(self.kanit_on))
        if self.senaryo == "hata":
            return RunSonuc(cikis_kodu=1, hata="kurgusal hata: islem basarisiz")
        if self.senaryo == "onay-gerekli":
            return RunSonuc(cikis_kodu=2, onay_gerekli=True, hata="kullanici onayi gerekiyor")
        raise RuntimeError("kurgusal calistirici istisna firlatti")