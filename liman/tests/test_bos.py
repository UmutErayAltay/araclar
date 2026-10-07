"""`liman.bos`: aralik cozumleme + gercek bind denerek bos port bulma.

Gercek ag YOK: testler yalnizca `127.0.0.1` uzerinde gecici bind DENER ve
soketi hemen kapatir (baglanti kurmaz).
"""

from __future__ import annotations

import socket

import pytest

from liman import bos


# -- aralik_coz --------------------------------------------------------------


@pytest.mark.parametrize("metin,beklenen", [("8000-8999", (8000, 8999)), ("1-65535", (1, 65535))])
def test_aralik_coz_gecerli(metin: str, beklenen: tuple[int, int]) -> None:
    assert bos.aralik_coz(metin) == beklenen


@pytest.mark.parametrize(
    "metin",
    [
        "8000",  # tire yok
        "8000-8999-9000",  # fazla parca
        "abc-8999",  # sayi degil
        "8000-",  # eksik
        "0-8999",  # 0 gecersiz
        "8000-65536",  # 65535 ustu
        "8999-8000",  # baslangic > bitis
    ],
)
def test_aralik_coz_gecersiz(metin: str) -> None:
    with pytest.raises(ValueError, match="geçersiz aralık"):
        bos.aralik_coz(metin)


def test_aralik_coz_hata_mesaji_turkce() -> None:
    with pytest.raises(ValueError) as hata:
        bos.aralik_coz("yanlis")
    assert "geçersiz aralık" in str(hata.value)


# -- bos_portlar -------------------------------------------------------------


def _dolu_soket() -> tuple[socket.socket, int]:
    """Gercekten DOLU bir port: port 0'a bind + listen, portunu dondurur."""
    soket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    soket.bind(("127.0.0.1", 0))
    soket.listen(1)
    return soket, int(soket.getsockname()[1])


def test_dolu_port_bos_listede_yok() -> None:
    """Dolu port, `bos_portlar` sonucunda ASLA gorunmemeli."""
    soket, port = _dolu_soket()
    try:
        assert port not in bos.bos_portlar(aralik=(port, port + 5), adet=10)
    finally:
        soket.close()


def test_aralik_tamamen_dolu_liste_bos() -> None:
    """Dolu portla tek basina bir aralik: bos port BULUNAMAZ."""
    soket, port = _dolu_soket()
    try:
        assert bos.bos_portlar(aralik=(port, port), adet=1) == []
    finally:
        soket.close()


def test_adet_siniri() -> None:
    """`adet` kadar bulununca DURUR (araligi bitirmez)."""
    portlar = bos.bos_portlar(aralik=(8500, 8600), adet=3)
    assert len(portlar) == 3
    assert portlar == sorted(portlar)
    assert all(8500 <= p <= 8600 for p in portlar)


def test_bos_portlar_varsayilan_aralik() -> None:
    portlar = bos.bos_portlar(adet=2)
    assert len(portlar) == 2
    assert all(bos.VARSAYILAN_ARALIK[0] <= p <= bos.VARSAYILAN_ARALIK[1] for p in portlar)
