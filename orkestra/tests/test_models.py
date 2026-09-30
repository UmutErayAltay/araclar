"""Durum makinesi: her gecerli ve her gecersiz gecis."""

import itertools
import re
from datetime import datetime, timezone

import pytest

from orkestra.models import (
    Durum,
    GECISLER,
    SON_DURUMLAR,
    gecis_gecerli,
    gecisleri,
    utc_simdi,
)

GECERLI = {
    (Durum.BEKLIYOR, Durum.CALISIYOR),
    (Durum.BEKLIYOR, Durum.IPTAL),
    (Durum.CALISIYOR, Durum.BITTI),
    (Durum.CALISIYOR, Durum.HATA),
    (Durum.CALISIYOR, Durum.ONAY_BEKLIYOR),
    (Durum.CALISIYOR, Durum.IPTAL),
    (Durum.ONAY_BEKLIYOR, Durum.BEKLIYOR),
    (Durum.ONAY_BEKLIYOR, Durum.IPTAL),
    (Durum.HATA, Durum.BEKLIYOR),
}

TUM_CIFTLER = list(itertools.product(list(Durum), repeat=2))
GECERSIZ = [c for c in TUM_CIFTLER if c not in GECERLI]


def test_durum_degerleri_sozlesmesi():
    assert [d.value for d in Durum] == [
        "bekliyor",
        "calisiyor",
        "bitti",
        "hata",
        "onay-bekliyor",
        "iptal",
    ]


def test_dokuz_gecerli_gecis_tanimli():
    assert set(GECISLER) == set(Durum)
    assert {(k, v) for k, g in GECISLER.items() for v in g} == GECERLI
    assert len(GECERLI) == 9


def test_son_durumlar_terminal():
    assert set(SON_DURUMLAR) == {Durum.BITTI, Durum.IPTAL}
    for durum in SON_DURUMLAR:
        assert GECISLER[durum] == frozenset()


@pytest.mark.parametrize(
    "mevcut,yeni", sorted(GECERLI, key=lambda c: (c[0].value, c[1].value))
)
def test_gecerli_gecisler(mevcut, yeni):
    assert gecis_gecerli(mevcut, yeni)
    assert yeni in gecisleri(mevcut)


@pytest.mark.parametrize("mevcut,yeni", GECERSIZ)
def test_gecersiz_gecis(mevcut, yeni):
    assert not gecis_gecerli(mevcut, yeni)
    assert yeni not in gecisleri(mevcut)


def test_kapsam_sayimi_27_gecersiz_cift():
    assert len(TUM_CIFTLER) == 36
    assert len(GECERSIZ) == 27


def test_kendi_kendine_gecis_gecersiz():
    assert not gecis_gecerli(Durum.BEKLIYOR, Durum.BEKLIYOR)
    assert not gecis_gecerli(Durum.HATA, Durum.HATA)


def test_onay_bekliyor_dogrudan_calisiyora_gidemez():
    assert gecis_gecerli(Durum.ONAY_BEKLIYOR, Durum.BEKLIYOR)
    assert gecis_gecerli(Durum.BEKLIYOR, Durum.CALISIYOR)
    assert not gecis_gecerli(Durum.ONAY_BEKLIYOR, Durum.CALISIYOR)


def test_hata_yeniden_deneme_yolu():
    assert gecis_gecerli(Durum.HATA, Durum.BEKLIYOR)
    assert not gecis_gecerli(Durum.HATA, Durum.CALISIYOR)
    assert not gecis_gecerli(Durum.HATA, Durum.ONAY_BEKLIYOR)


def test_gecisleri_listesi_sirali():
    assert gecisleri(Durum.CALISIYOR) == [
        Durum.BITTI,
        Durum.HATA,
        Durum.IPTAL,
        Durum.ONAY_BEKLIYOR,
    ]
    assert gecisleri(Durum.BITTI) == []
    assert gecisleri(Durum.HATA) == [Durum.BEKLIYOR]


def test_utc_simdi_iso8601_utc():
    damga = utc_simdi()
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", damga)
    ayristir = datetime.strptime(damga, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    assert ayristir.tzinfo == timezone.utc


def test_durum_metinleri_db_icin_ascii_kisa():
    assert all(d.value.isascii() for d in Durum)