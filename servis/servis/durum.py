"""Durum olcumu: port dinleniyor mu, bizim pid'imiz yasiyor mu, saglik_url ne diyor.

Salt-okunur: hicbir surec baslatmaz, oldurmez, pid dosyasi silmez.
"""

from __future__ import annotations

import os
import socket
import urllib.error
import urllib.request
from pathlib import Path

from .tanim import Servis

PORT_ZAMAN_ASIMI_SN = 0.5
SAGLIK_ZAMAN_ASIMI_SN = 3.0

CALISIYOR = "calisiyor"
DURDU = "durdu"
PORT_DOLU_BILINMEYEN = "port-dolu-bilinmeyen"

#: saglik_url sonucu: saglikli / sagliksiz / yok (tanimda yok)
SAGLIKLI = "saglikli"
SAGLIKSIZ = "sagliksiz"
SAGLIK_YOK = "-"

#: yerel adreslere giderken proxy'e girmeyiz (localhost asla proxy'lenmez).
_ACILIYOR = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def dizin() -> Path:
    """SERVIS_DIZINI ile degistirilebilir; varsayilan ~/.servis."""
    return Path(os.environ.get("SERVIS_DIZINI") or (Path.home() / ".servis")).expanduser()


def pid_yolu(ad: str) -> Path:
    return dizin() / "pid" / f"{ad}.pid"


def log_yolu(ad: str) -> Path:
    return dizin() / "log" / f"{ad}.log"


def pid_oku(ad: str) -> int | None:
    """Pid dosyasini okur. Bozuk/olmayan dosya -> None (dosyaya dokunmaz)."""
    try:
        metin = pid_yolu(ad).read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return None
    try:
        pid = int(metin)
    except ValueError:
        return None
    return pid if pid > 0 else None


def port_dinleniyor(port: int) -> bool:
    """127.0.0.1:port'a baglanabiliyorsek biri dinliyor demektir."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(PORT_ZAMAN_ASIMI_SN)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def surec_yasiyor(pid: int) -> bool:
    """Sinyal 0 ile var mi diye bakar (SIGTERM gondermez).

    Zombie ('Z') durumu YASAMIYOR sayilir: surec bitti ama bizim onu
    beklemedigimiz icin girdi tablosunda bekliyor -- `os.kill(pid, 0)` buna
    hata vermez, yanlislikla "ayakta" sanilir.
    """
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # var, ama bize ait degil
    return not zombie(pid)


def zombie(pid: int) -> bool:
    """Linux /proc/<pid>/stat durum alani 'Z' ise surec bitmis (zombie) demektir."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    # "pid (komut) S ..." -- komut parantez icinde olabilir, durum ondan SONRA gelir.
    kapanis = stat.rfind(")")
    if kapanis == -1:
        return False
    alanlar = stat[kapanis + 1 :].split()
    return bool(alanlar) and alanlar[0] == "Z"


def saglik_yok(deger: str | None) -> str | None:
    """saglik_url GET -> 200-399 saglikli, aksi halde sagliksiz (ag yoksa sagliksiz)."""
    if not deger:
        return None
    istek = urllib.request.Request(deger, method="GET")
    try:
        with _ACILIYOR.open(istek, timeout=SAGLIK_ZAMAN_ASIMI_SN) as yanit:
            return SAGLIKLI if 200 <= yanit.status <= 399 else SAGLIKSIZ
    except (urllib.error.URLError, OSError, ValueError):
        return SAGLIKSIZ


def olc(servis: Servis) -> dict:
    """Tek servisin olcum karti (yazma yapmaz)."""
    port_aci = port_dinleniyor(servis.port)
    pid = pid_oku(servis.ad)
    pid_ayakta = pid is not None and surec_yasiyor(pid)

    if port_aci and pid_ayakta:
        durum = CALISIYOR
    elif port_aci:
        # Port dolu ama bizim pid dosyamiz yok ya da o pid olmus.
        durum = PORT_DOLU_BILINMEYEN
    else:
        durum = DURDU

    return {
        "ad": servis.ad,
        "port": servis.port,
        "durum": durum,
        "pid": pid if pid_ayakta else None,
        "pid_dosyasindaki": pid,
        "port_aci": port_aci,
        "saglik": saglik_yok(servis.saglik_url) or SAGLIK_YOK,
    }


def tablo(olcumler: list[dict]) -> str:
    """Insan-okur metin tablosu."""
    basliklar = ["ad", "port", "durum", "pid", "saglik"]
    satirlar = [
        [o["ad"], str(o["port"]), o["durum"], str(o["pid"] or "-"), o["saglik"]]
        for o in olcumler
    ]
    genislik = [
        max(len(basliklar[i]), *(len(s[i]) for s in satirlar)) if satirlar else len(basliklar[i])
        for i in range(len(basliklar))
    ]

    def birlestir(hucre: list[str]) -> str:
        return "  ".join(hucre[i].ljust(genislik[i]) for i in range(len(hucre))).rstrip()

    return "\n".join([birlestir(basliklar), *(birlestir(s) for s in satirlar)]) if satirlar else birlestir(basliklar)