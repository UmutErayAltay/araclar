"""`liman.tarama`: gruplama, tekillestirme, kapsam, hata toleransi, siralama, ozet.

Gercek ag YOK: tum veri `conftest.baglanti` ile uretilen sahte satirlardir.
"""

from __future__ import annotations

import socket

import psutil
import pytest

from conftest import SahteSurec, baglanti
from liman import tarama

SUREC = SahteSurec("python3", ["python3", "-m", "liman"])


def test_tcp_dinleyen_kaydedilir(sahte_kaynak, sahte_surec) -> None:
    sahte_surec({100: SUREC})
    satirlar = tarama.dinleyenler(sahte_kaynak(baglanti(8787)))
    assert len(satirlar) == 1
    s = satirlar[0]
    assert (s["proto"], s["ip"], s["port"], s["pid"]) == ("tcp", "127.0.0.1", 8787, 100)
    assert s["surec"] == "python3"
    assert s["komut"] == "python3 -m liman"
    assert s["uyari"] is None
    assert s["bagli"] == 0
    assert s["kapsam"] == "yerel"
    assert s["etiket"] == "cor"


def test_tcp_yalniz_listen(sahte_kaynak, sahte_surec) -> None:
    """ESTABLISHED/TIME_WAIT satirlari dinleyici DEGILDIR."""
    sahte_surec({100: SUREC})
    kaynak = sahte_kaynak(
        baglanti(8080, status="ESTABLISHED", raddr=("127.0.0.1", 5555)),
        baglanti(8080, status="TIME_WAIT", raddr=("127.0.0.1", 5556)),
        baglanti(8080, status="LISTEN"),
    )
    satirlar = tarama.dinleyenler(kaynak)
    assert [(s["port"], s["proto"]) for s in satirlar] == [(8080, "tcp")]


def test_udp_raddr_bos(sahte_kaynak, sahte_surec) -> None:
    """UDP'de uzak adresi dolu satir dinleyici degildir."""
    sahte_surec({100: SUREC})
    kaynak = sahte_kaynak(
        baglanti(53, tur=socket.SOCK_DGRAM, ip="0.0.0.0", status=None, raddr=("127.0.0.1", 5555)),
        baglanti(53, tur=socket.SOCK_DGRAM, ip="0.0.0.0", status=None),
    )
    satirlar = tarama.dinleyenler(kaynak)
    assert [(s["proto"], s["port"], s["kapsam"]) for s in satirlar] == [("udp", 53, "disa_acik")]
    assert satirlar[0]["bagli"] == 0  # UDP'de bagli sayisi her zaman 0


def test_tekillestirme_proto_ip_port(sahte_kaynak, sahte_surec) -> None:
    """Ayni (proto, ip, port) birden fazla satirsa TEK kayit olur."""
    sahte_surec({100: SUREC, 101: SUREC, 102: SUREC})
    kaynak = sahte_kaynak(
        baglanti(8770, pid=100),
        baglanti(8770, pid=101),
        baglanti(8770, ip="0.0.0.0", pid=102),  # farkli ip: AYRI kayit
    )
    satirlar = tarama.dinleyenler(kaynak)
    anahtarlar = [(s["proto"], s["ip"], s["port"]) for s in satirlar]
    assert len(anahtarlar) == len(set(anahtarlar)) == 2


@pytest.mark.parametrize("ip", ["127.0.0.1", "127.0.0.53", "::1"])
def test_kapsam_yerel(ip: str) -> None:
    assert tarama.kapsam_bul(ip) == "yerel"


@pytest.mark.parametrize("ip", ["0.0.0.0", "::", "192.168.1.5"])
def test_kapsam_disa_acik(ip: str) -> None:
    assert tarama.kapsam_bul(ip) == "disa_acik"


def test_access_denied_cokmez_uyari_doldur(sahte_kaynak, sahte_surec) -> None:
    """Yetki yoksa satir ATILMAZ; surec/komut bos, uyari aciklar."""
    sahte_surec({100: psutil.AccessDenied(pid=100)})
    s = tarama.dinleyenler(sahte_kaynak(baglanti(3000, pid=100)))[0]
    assert s["port"] == 3000
    assert s["surec"] is None and s["komut"] is None
    assert s["uyari"] == tarama.UYARI_YETKI


def test_no_such_process_cokmez(sahte_kaynak, sahte_surec) -> None:
    """Haritada olmayan pid (surec olmus): yine uyari, satir kalir."""
    sahte_surec({})
    s = tarama.dinleyenler(sahte_kaynak(baglanti(3000, pid=4242)))[0]
    assert s["uyari"] == tarama.UYARI_YETKI


def test_pid_yok_uayri(sahte_kaynak, sahte_surec) -> None:
    sahte_surec({})
    s = tarama.dinleyenler(sahte_kaynak(baglanti(3000, pid=None)))[0]
    assert s["pid"] is None and s["surec"] is None
    assert s["uyari"] == tarama.UYARI_PID_YOK


def test_bagli_sayisi(sahte_kaynak, sahte_surec) -> None:
    """Ayni yerel port icin ESTABLISHED TCP sayisi `bagli` olur."""
    sahte_surec({100: SUREC})
    kaynak = sahte_kaynak(
        baglanti(8770, status="LISTEN"),
        baglanti(8770, status="ESTABLISHED", raddr=("127.0.0.1", 1)),
        baglanti(8770, status="ESTABLISHED", raddr=("127.0.0.1", 2)),
        baglanti(8770, status="ESTABLISHED", raddr=("127.0.0.1", 3)),
        baglanti(8790, status="LISTEN"),
    )
    satirlar = {s["port"]: s for s in tarama.dinleyenler(kaynak)}
    assert satirlar[8770]["bagli"] == 3
    assert satirlar[8790]["bagli"] == 0


def test_siralama_port_then_proto(sahte_kaynak, sahte_surec) -> None:
    """Once port; ayni portta once proto."""
    sahte_surec({100: SUREC})
    kaynak = sahte_kaynak(
        baglanti(9000, tur=socket.SOCK_DGRAM, status=None),
        baglanti(8000, tur=socket.SOCK_DGRAM, status=None),
        baglanti(8000, tur=socket.SOCK_STREAM, status="LISTEN"),
        baglanti(7000, tur=socket.SOCK_STREAM, status="LISTEN"),
    )
    satirlar = tarama.dinleyenler(kaynak)
    assert [(s["port"], s["proto"]) for s in satirlar] == [
        (7000, "tcp"),
        (8000, "tcp"),
        (8000, "udp"),
        (9000, "udp"),
    ]


def test_komut_kesilir(sahte_kaynak, sahte_surec) -> None:
    """Komut 80 karakteri asarsa "…" ile kesilir."""
    sahte_surec({100: SahteSurec("sh", ["sh"] + ["x" * 10] * 20)})
    komut = tarama.dinleyenler(sahte_kaynak(baglanti(3000, pid=100)))[0]["komut"]
    assert len(komut) == tarama.KOMUT_UST_SINIR
    assert komut.endswith("…")


def test_bos_komut_none(sahte_kaynak, sahte_surec) -> None:
    """Bos cmdline: komut yerine bos yazi degil `None`."""
    sahte_surec({100: SahteSurec("kernel", [])})
    s = tarama.dinleyenler(sahte_kaynak(baglanti(3000, pid=100)))[0]
    assert s["surec"] == "kernel"
    assert s["komut"] is None
    assert s["uyari"] is None


def test_ozet(sahte_kaynak, sahte_surec) -> None:
    sahte_surec({100: SUREC})
    kaynak = sahte_kaynak(
        baglanti(8770),
        baglanti(3000, ip="0.0.0.0"),
        baglanti(8080, ip="192.168.1.5"),
        baglanti(9000, ip="::1"),
    )
    assert tarama.ozet(tarama.dinleyenler(kaynak)) == {
        "toplam": 4,
        "disa_acik": 2,
        "yerel": 2,
    }


def test_ozet_bos_liste() -> None:
    assert tarama.ozet([]) == {"toplam": 0, "disa_acik": 0, "yerel": 0}
