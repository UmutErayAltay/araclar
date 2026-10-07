"""Bos port bulma: gercek `socket.bind` dener, tahmin YAPMAZ.

`SO_REUSEADDR` KULLANILMAZ: yeniden kullanım açık olsaydı, TIME_WAIT'ta yatan
bir port "bos" görünür ve az sonra baglanan bir servis çökerdi.
"""

from __future__ import annotations

import socket

#: `liman bos` varsayilan araligi: gelistirme portlari.
VARSAYILAN_ARALIK = (8000, 8999)

#: `liman bos` varsayilan adedi.
VARSAYILAN_ADET = 10

_EN_KUCUK_PORT = 1
_EN_BUYUK_PORT = 65535


def aralik_coz(metin: str) -> tuple[int, int]:
    """`"8000-8999"` -> `(8000, 8999)`. Gecersizse Turkce `ValueError`."""
    parcalar = metin.split("-")
    if len(parcalar) != 2:
        raise ValueError(f"geçersiz aralık: {metin} (beklenen biçim: 8000-8999)")
    try:
        bas, bit = int(parcalar[0]), int(parcalar[1])
    except ValueError:
        raise ValueError(f"geçersiz aralık: {metin} (portlar sayı olmalı)") from None
    for port in (bas, bit):
        if not _EN_KUCUK_PORT <= port <= _EN_BUYUK_PORT:
            raise ValueError(f"geçersiz aralık: {metin} (portlar 1-65535 aralığında olmalı)")
    if bas > bit:
        raise ValueError(f"geçersiz aralık: {metin} (başlangıç büyükten küçük)")
    return bas, bit


def bos_portlar(
    aralik: tuple[int, int] = VARSAYILAN_ARALIK,
    adet: int = VARSAYILAN_ADET,
    host: str = "127.0.0.1",
) -> list[int]:
    """Aralıktaki portlari sirayla dener; `adet` kadar bos bulunca durur.

    Baglanti KURULMAZ (yalniz `bind`); baglanti acilan her soket hemen kapatilir.
    """
    bas, bit = aralik
    bulunan: list[int] = []
    for port in range(bas, bit + 1):
        soket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            soket.bind((host, port))
        except OSError:
            continue  # bu port dolu
        else:
            bulunan.append(port)
            if len(bulunan) >= adet:
                break
        finally:
            soket.close()
    return bulunan
