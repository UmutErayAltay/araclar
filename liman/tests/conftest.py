"""Sahte `net_connections` verisi ureten ortak yardimcilar.

Gercek ag YOK: hicbir test uzak bir adrese baglanmaz, port TARAMAZ.
`bos.py` testleri disinda gercek socket YALNIZCA yerel gecici bind
denemeleri icin kullanilir.
"""

from __future__ import annotations

import socket
from typing import Any, NamedTuple

import psutil
import pytest


class Baglanti(NamedTuple):
    """psutil'in `sconn` yapisina benzeyen basit sahte baglanti satiri."""

    fd: int | None
    family: Any
    type: int
    laddr: Any
    raddr: Any
    status: str | None
    pid: int | None


def baglanti(
    port: int,
    *,
    tur: int = socket.SOCK_STREAM,
    ip: str = "127.0.0.1",
    status: str | None = "LISTEN",
    pid: int | None = 100,
    raddr: Any = None,
) -> Baglanti:
    """Tek bir sahte baglanti satiri uretir."""
    return Baglanti(
        fd=None,
        family=socket.AF_INET,
        type=tur,
        laddr=(ip, port),
        raddr=raddr,
        status=status,
        pid=pid,
    )


class SahteSurec:
    """`psutil.Process`in SADECE ad/komut okuyan taklidi."""

    def __init__(self, ad: str, komut: list[str]) -> None:
        self._ad = ad
        self._komut = komut

    def name(self) -> str:
        return self._ad

    def cmdline(self) -> list[str]:
        return self._komut


@pytest.fixture
def sahte_surec(monkeypatch: pytest.MonkeyPatch):
    """`psutil.Process`'i verilen haritaya gore degistirir.

    Harita: pid -> `SahteSurec` (okunur) veya hata nesnesi (`AccessDenied`).
    Haritada olmayan pid `NoSuchProcess` firlatir (surec olmus olabilir).
    """

    def kur(hazir: dict[int, Any]) -> None:
        def sahte_process(pid: int) -> Any:
            sonuc = hazir.get(pid)
            if sonuc is None:
                raise psutil.NoSuchProcess(pid)
            if isinstance(sonuc, BaseException):
                raise sonuc
            return sonuc

        monkeypatch.setattr("liman.tarama.psutil.Process", sahte_process)

    return kur


@pytest.fixture
def sahte_kaynak():
    """`tarama.dinleyenler(sagneye)` cagrisina verilecek kaynak uretici."""

    def kur(*baglantilar: Baglanti):
        return lambda: list(baglantilar)

    return kur
