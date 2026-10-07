"""CLI sozlesmesi: tablo, `--json`, `bos`, `kim`, gecersiz girdi.

Tarama kaynagi `psutil.net_connections` uzerinden sahtelenir: hicbir test
GERCEK port taramaz. `web` komutu burada calistirilmaz (gercek surec ister).
"""

from __future__ import annotations

import json

import pytest

from conftest import SahteSurec, baglanti
from liman import cli

#: Turkce karakterli ad: `--json`in ensure_ascii=False oldugunu kanitlamak icin.
SUREC = SahteSurec("öğrenci", ["öğrenci", "--oku"])


@pytest.fixture
def sahte_portlar(monkeypatch: pytest.MonkeyPatch):
    """`psutil.net_connections`'i verilen sahte satirlarla degistirir.

    `liman.tarama` psutil'i modul olarak kullandigi icin bu, `dinleyenler()`in
    varsayilan kaynagini da sahteler.
    """

    def kur(*baglantilar) -> list:
        satir_listesi = list(baglantilar)
        monkeypatch.setattr(
            "liman.tarama.psutil.net_connections",
            lambda kind="inet": list(satir_listesi),
        )
        return satir_listesi

    return kur


@pytest.fixture
def tablo_hazir(sahte_portlar, sahte_surec):
    """Uc satirlik sabit tablo (biri disa acik)."""

    def kur() -> None:
        sahte_surec({100: SUREC, 101: SUREC})
        sahte_portlar(
            baglanti(3000, ip="0.0.0.0", pid=101),  # disa acik, etiketsiz
            baglanti(8770, pid=100),  # yerel, etiketli
            baglanti(5432, pid=100),  # yerel, etiketli
        )

    return kur


def _satir(cikti: str, port: str) -> str:
    return next(s for s in cikti.splitlines() if port in s)


# -- argümansız tablo --------------------------------------------------------


def test_tablo_sutunlari_ve_ozet(tablo_hazir, capsys) -> None:
    tablo_hazir()
    assert cli.main([]) == 0
    cikti = capsys.readouterr().out
    for baslik in ("PORT", "PROTO", "KAPSAM", "SÜREÇ", "PID", "BAĞLI", "ETİKET"):
        assert baslik in cikti
    assert "3 dinleyen, 1 dışa açık" in cikti


def test_tablo_disa_acik_isareti(tablo_hazir, capsys) -> None:
    """Disa acik satirin basinda `!` vardir; yerel satirda YOKTUR."""
    tablo_hazir()
    cli.main([])
    cikti = capsys.readouterr().out
    assert _satir(cikti, "3000").startswith("!")
    assert "dışa açık" in _satir(cikti, "3000")
    assert not _satir(cikti, "8770").startswith("!")
    assert "yerel" in _satir(cikti, "8770")


def test_tablo_etiketler(tablo_hazir, capsys) -> None:
    tablo_hazir()
    cli.main([])
    cikti = capsys.readouterr().out
    assert "atlas" in cikti and "postgres" in cikti


def test_tablo_sutunlari_hizali(tablo_hazir, capsys) -> None:
    """Baslik ve veri satirlari ayni SUTUN BASLANGICLARINDAN hizalanir."""
    tablo_hazir()
    cli.main([])
    satirlar = capsys.readouterr().out.splitlines()
    baslik_proto = satirlar[0].index("PROTO")
    # Her veri satirinda "tcp"/"udp" de ayni sutunda baslamali.
    veri_satirlari = [s for s in satirlar if "tcp" in s or "udp" in s]
    assert len(veri_satirlari) == 3
    for satir in veri_satirlari:
        assert satir.index("tcp") == baslik_proto


def test_dinleyen_yoksa_metin(sahte_portlar, capsys) -> None:
    sahte_portlar()  # hicbir dinleyici yok
    assert cli.main([]) == 0
    assert "Dinleyen port yok." in capsys.readouterr().out


# -- --json ------------------------------------------------------------------


def test_json_sema(tablo_hazir, capsys) -> None:
    tablo_hazir()
    assert cli.main(["--json"]) == 0
    veri = json.loads(capsys.readouterr().out)
    assert set(veri) == {"dinleyenler", "ozet"}
    assert veri["ozet"] == {"toplam": 3, "disa_acik": 1, "yerel": 2}
    assert set(veri["dinleyenler"][0]) == {
        "proto", "ip", "port", "pid", "surec", "komut", "bagli",
        "kapsam", "etiket", "uyari",
    }
    assert [s["port"] for s in veri["dinleyenler"]] == [3000, 5432, 8770]


def test_json_turkce_kacissiz(tablo_hazir, capsys) -> None:
    """ensure_ascii=False: Turkce karakterler JSON'da \\u kacisi olmadan cikar."""
    tablo_hazir()
    cli.main(["--json"])
    ham = capsys.readouterr().out
    assert "öğrenci" in ham
    assert "\\u" not in ham


# -- kim ---------------------------------------------------------------------


def test_kim_bosta_cikis_1(tablo_hazir, capsys) -> None:
    tablo_hazir()
    assert cli.main(["kim", "1234"]) == 1
    assert "Port 1234 boşta." in capsys.readouterr().out


def test_kim_dolu_cikis_0(tablo_hazir, capsys) -> None:
    tablo_hazir()
    assert cli.main(["kim", "8770"]) == 0
    cikti = capsys.readouterr().out
    assert "8770" in cikti and "atlas" in cikti


def test_kim_gecersiz_port_cikis_2(tablo_hazir, capsys) -> None:
    tablo_hazir()
    assert cli.main(["kim", "abc"]) == 2
    assert "Hata:" in capsys.readouterr().err


def test_kim_port_araligi_disi_cikis_2(tablo_hazir, capsys) -> None:
    tablo_hazir()
    assert cli.main(["kim", "70000"]) == 2
    assert "Hata:" in capsys.readouterr().err


# -- bos ---------------------------------------------------------------------


def test_bos_gecersiz_aralik_cikis_2(capsys) -> None:
    assert cli.main(["bos", "--aralik", "yanlis"]) == 2
    assert "Hata:" in capsys.readouterr().err


def test_bos_gecersiz_adet_cikis_2(capsys) -> None:
    assert cli.main(["bos", "--adet", "0"]) == 2
    assert "Hata:" in capsys.readouterr().err


def test_bos_basarili_satir_satir_cikis_0(capsys) -> None:
    assert cli.main(["bos", "--aralik", "8600-8620", "--adet", "2"]) == 0
    portlar = [int(s) for s in capsys.readouterr().out.split()]
    assert len(portlar) == 2
    assert all(8600 <= p <= 8620 for p in portlar)
