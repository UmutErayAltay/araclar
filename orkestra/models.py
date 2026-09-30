"""Görev/koşu modelleri ve durum makinesi.

Durum adları DB'de ASCII Türkçe olarak saklanır (`calisiyor`), böylece komut
satırından `sh` üzerinden bakıldığında da okunur; arayüz metinleri ayrı.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class Durum(str, Enum):
    BEKLIYOR = "bekliyor"
    CALISIYOR = "calisiyor"
    BITTI = "bitti"
    HATA = "hata"
    ONAY_BEKLIYOR = "onay-bekliyor"
    IPTAL = "iptal"


GECISLER: dict[Durum, frozenset[Durum]] = {
    Durum.BEKLIYOR: frozenset({Durum.CALISIYOR, Durum.IPTAL}),
    Durum.CALISIYOR: frozenset(
        {Durum.BITTI, Durum.HATA, Durum.ONAY_BEKLIYOR, Durum.IPTAL}
    ),
    Durum.ONAY_BEKLIYOR: frozenset({Durum.BEKLIYOR, Durum.IPTAL}),
    Durum.HATA: frozenset({Durum.BEKLIYOR}),
    Durum.BITTI: frozenset(),
    Durum.IPTAL: frozenset(),
}

SON_DURUMLAR = (Durum.BITTI, Durum.IPTAL)


class OrkestraHata(Exception):
    """Tüm orkestra hatalarının atası."""


class GecersizGecis(OrkestraHata):
    """İstenen durum geçişi durum makinesinde tanımlı değil."""


class GecersizGirdi(OrkestraHata):
    """Ajan adı veya istem giriş doğrulamasından geçemedi."""


class GorevBulunamadi(OrkestraHata):
    """Verilen kimlikle bir görev yok."""


def utc_simdi() -> str:
    """ISO8601 UTC zaman damgası (saniye çözünürlüğü, `Z` sonlu)."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def gecis_gecerli(mevcut: Durum, yeni: Durum) -> bool:
    return yeni in GECISLER[Durum(mevcut)]


def gecisleri(mevcut: Durum) -> list[Durum]:
    """Verilen durumdan gidilebilecek durumlar (sıralı, test edilebilir)."""
    return sorted(GECISLER[Durum(mevcut)], key=lambda d: d.value)


@dataclass(frozen=True)
class Task:
    id: int
    ajan: str
    istem: str
    durum: Durum
    olusturma: str

    @classmethod
    def satirdan(cls, satir) -> "Task":
        return cls(
            id=satir["id"],
            ajan=satir["ajan"],
            istem=satir["istem"],
            durum=Durum(satir["durum"]),
            olusturma=satir["olusturma"],
        )

    @property
    def onizleme(self) -> str:
        """Liste çıktısı için kısaltılmış istem."""
        tek = " ".join(self.istem.split())
        return tek if len(tek) <= 60 else tek[:60] + "..."


@dataclass(frozen=True)
class Run:
    id: int
    task_id: int
    baslangic: str
    bitis: str | None
    cikis_kodu: int | None
    cikti_yolu: str | None
    kanit_yollari: list[str]
    hata: str | None


@dataclass
class RunSonuc:
    """Bir koşunun sonucu (Runner.protocol'un döndürdüğü değer)."""

    cikis_kodu: int = 0
    cikti: str | None = None
    kanit_yollari: list[str] = field(default_factory=list)
    hata: str | None = None
    onay_gerekli: bool = False