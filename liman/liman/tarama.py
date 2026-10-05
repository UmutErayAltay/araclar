"""Yerel TCP/UDP dinleyicilerini tarar; satirlari CLI ve web paneli birlikte kullanir.

SALT OKUNUR: hicbir baglanti kapatilmaz, hicbir surec durdurulmaz, aga cikilmaz.
Surec bilgisi okunamazsa (yetki yok, surec olu) satir ATILMAZ: `surec`/`komut`
bos kalir ve `uyari` nedeni soyler.
"""

from __future__ import annotations

import ipaddress
import socket
from typing import Any, Callable, Iterable

import psutil

from .bilinen import etiket

#: Varsayilan tarama kaynagi: calisan sureclerin tum INET baglantilari.
#: Testler bunun yerine sahte bir kaynak enjekte eder.
Kaynak = Callable[[], Iterable[Any]]

#: Surec bilgisi okunamadi: satiri atmayiz, nedeni soyleriz.
UYARI_YETKI = "süreç bilgisi okunamadı (yetki yok)"

#: PID yoksa (kernel suresi, kimlik bilgisi silinmis): surec/komut bilinmez.
UYARI_PID_YOK = "süreç bilgisi yok (pid yok)"

#: `komut` alaninin en fazla karakteri; uzun satirlar "…" ile kesilir.
KOMUT_UST_SINIR = 80


def kapsam_bul(ip: str) -> str:
    """Adres yerel mi disa acik mi? (127.0.0.0/8 ve ::1 = yerel)."""
    try:
        adres = ipaddress.ip_address(ip)
    except ValueError:
        return "disa_acik"
    return "yerel" if adres.is_loopback else "disa_acik"


def _kisalt(metin: str) -> str:
    return metin if len(metin) <= KOMUT_UST_SINIR else metin[:KOMUT_UST_SINIR - 1] + "…"


def _surec_bilgi(pid: int | None) -> tuple[str | None, str | None, str | None]:
    """(surec, komut, uyari); okunamazsa surec/komut `None`, uyari dolu."""
    if pid is None:
        return None, None, UYARI_PID_YOK
    try:
        surec = psutil.Process(pid)
        return surec.name(), _kisalt(" ".join(surec.cmdline())) or None, None
    except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
        return None, None, UYARI_YETKI


def dinleyenler(kaynak: Kaynak | None = None) -> list[dict[str, Any]]:
    """Dinleyen satirlari: port numarasina, sonra proto'ya gore sirali.

    TCP icin yalniz `LISTEN` durumu; UDP icin uzak adresi (`raddr`) bos olanlar
    (bir UDP "baglantisi" kurmaz, dinleyicinin uzak adresi yoktur).
    """
    kay = (lambda: psutil.net_connections(kind="inet")) if kaynak is None else kaynak
    baglantilar = list(kay())

    # Ayni yerel port icin ESTABLISHED TCP baglantilarinin sayisi.
    bagli_sayi: dict[int, int] = {}
    for c in baglantilar:
        if getattr(c, "type", None) != socket.SOCK_STREAM:
            continue
        if getattr(c, "status", None) != "ESTABLISHED" or getattr(c, "laddr", None) is None:
            continue
        bagli_sayi[int(c.laddr[1])] = bagli_sayi.get(int(c.laddr[1]), 0) + 1

    gorulen: set[tuple[str, str, int]] = set()
    satirlar: list[dict[str, Any]] = []
    for c in baglantilar:
        proto = "tcp" if getattr(c, "type", None) == socket.SOCK_STREAM else "udp"
        if proto == "tcp":
            if getattr(c, "status", None) != "LISTEN":
                continue
        elif getattr(c, "raddr", None) is not None:
            # UDP'de raddr doluysa bu konusma (kaynak) ucu, dinleyici degil.
            continue

        laddr = getattr(c, "laddr", None)
        if laddr is None:
            continue
        ip, port = str(laddr[0]), int(laddr[1])
        if (proto, ip, port) in gorulen:
            continue
        gorulen.add((proto, ip, port))

        surec, komut, uyari = _surec_bilgi(getattr(c, "pid", None))
        satirlar.append(
            {
                "proto": proto,
                "ip": ip,
                "port": port,
                "pid": getattr(c, "pid", None),
                "surec": surec,
                "komut": komut,
                "bagli": bagli_sayi.get(port, 0) if proto == "tcp" else 0,
                "kapsam": kapsam_bul(ip),
                "etiket": etiket(port),
                "uyari": uyari,
            }
        )

    satirlar.sort(key=lambda s: (s["port"], s["proto"]))
    return satirlar


def ozet(satirlar: list[dict[str, Any]]) -> dict[str, int]:
    """Toplam / disa_acik / yerel sayilari."""
    return {
        "toplam": len(satirlar),
        "disa_acik": sum(1 for s in satirlar if s["kapsam"] == "disa_acik"),
        "yerel": sum(1 for s in satirlar if s["kapsam"] == "yerel"),
    }
