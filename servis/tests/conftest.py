"""servis testleri icin ortak yardimcilar. Hicbir mock kutuphanesi yok.

Ag YOK: saglik_url testleri de 127.0.0.1 uzerindeki GECICI http.server'a gider.
Gercek servisler (cor/kule/liman/postgres) HICBIR testte CALISMAZ; testler
`python3 -m http.server` kullanir. Yazma (baslat/durdur) yalniz tmp_path
altinda olur: SERVIS_DIZINI ve tanim dosyasi geciciye yonlendirilir.
"""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

KULLANIM_HATASI = 2
HEDEF_DEGIL = 1

#: Testlerde SIGTERM beklemesi 1 sn; gercek kullanimda varsayilan 10 sn kalir.
TEST_DURDUR_BEKLE_SN = "1"


@pytest.fixture(autouse=True)
def hizli_durdur_beklemesi():
    """Tum testlerde SERVIS_DURDUR_BEKLE_SN=1 (yoksa SIGTERM beklemesi 10 sn)."""
    eski = os.environ.get("SERVIS_DURDUR_BEKLE_SN")
    os.environ["SERVIS_DURDUR_BEKLE_SN"] = TEST_DURDUR_BEKLE_SN
    try:
        yield
    finally:
        if eski is None:
            os.environ.pop("SERVIS_DURDUR_BEKLE_SN", None)
        else:
            os.environ["SERVIS_DURDUR_BEKLE_SN"] = esli


def bos_port() -> int:
    """Su an KIMSE tarafindan baglanmamis bir port numarasi dondurur.

    Testlerde kullanilacak sunucu portlari sabit TUTULMAZ; aksi halde baska bir
    surece cakisma durumunda test yaniltici gecer.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def dinleyici_ac(port: int) -> socket.socket:
    """Portu gercekten dinleyen bir soket acar (bizim pid dosyamiz YOK).

    'port dolu ama bilinmeyen' senaryosu icin: `servis durdur` bunu OLMALI.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", port))
    sock.listen(8)
    return sock


def tanim_yaz(
    yol: Path,
    servisler: dict[str, dict],
    *,
    govde: str | None = None,
) -> Path:
    """Tanim dosyasini yazar. `govde` verilirse TAM OLARAK o yazilir (bozuk TOML testi)."""
    yol.parent.mkdir(parents=True, exist_ok=True)
    if govde is not None:
        yol.write_text(textwrap.dedent(govde), encoding="utf-8")
        return yol

    satirlar = []
    for ad, ayarlar in servisler.items():
        satir = [f"[servis.{ad}]"]
        for anahtar, deger in ayarlar.items():
            # argv listeleri de icinde tirnak ve backslash olabilir: repr() degil
            # JSON kullanilir (Python string literal'i TOML basic string ile ayni).
            satir.append(f"{anahtar} = {json.dumps(deger, ensure_ascii=False)}")
        satirlar.append("\n".join(satir))
    yol.write_text("\n\n".join(satirlar) + "\n", encoding="utf-8")
    return yol


def http_server_tanimi(ad: str, port: int, *, bekle_sn: float = 3.0, dizin: Path | None = None) -> dict:
    """`python3 -m http.server PORT --bind 127.0.0.1` ile calisan sahte servis tanimi.

    `bekle_sn` varsayilani 3 sn: yerel http.server 1 sn'de ayağa kalkar; 20 sn
    beklemek yalnizca test takimini uzatirdi.
    """
    ayarlar: dict = {
        "port": port,
        "baslat": [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
        "bekle_sn": bekle_sn,
    }
    if dizin is not None:
        ayarlar["cwd"] = str(dizin)
    return ayarlar


def run_module_cli(*args: str, cwd: Path | None = None, env_ek: dict[str, str] | None = None):
    """`python -m servis ...` komutunu GERCEKTEN subprocess olarak calistirir.

    SERVIS_DIZINI / SERVIS_TANIM / HOME once temizlenir, sonra testin
    yonlendirdigi degerler yazilir: kullanici ~/.servis'i hicbir testte
    okunmaz/yazilmaz.
    """
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT)
    for ad in ("SERVIS_DIZINI", "SERVIS_TANIM"):
        env.pop(ad, None)
    env["HOME"] = env["USERPROFILE"] = str(cwd or REPO_ROOT)
    env["SERVIS_DURDUR_BEKLE_SN"] = TEST_DURDUR_BEKLE_SN
    env.update(env_ek or {})
    return subprocess.run(
        [sys.executable, "-m", "servis", *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        env=env,
        timeout=90,
    )


def ortam(tmp_path: Path, tanim: Path) -> dict[str, str]:
    """CLI alt surecine verilecek izole ortam (tanim + gecici durum dizini)."""
    return {
        "SERVIS_TANIM": str(tanim),
        "SERVIS_DIZINI": str(tmp_path / "durum"),
    }


def pid_dosyasi(tmp_path: Path, ad: str, icerik: str | None) -> Path:
    """SERVIS_DIZINI/pid/<ad>.pid yolunu yazar (icerik None -> dosya olusturulmaz)."""
    yol = tmp_path / "durum" / "pid" / f"{ad}.pid"
    yol.parent.mkdir(parents=True, exist_ok=True)
    if icerik is not None:
        yol.write_text(icerik, encoding="utf-8")
    return yol


def pid_oku(tmp_path: Path, ad: str) -> int | None:
    """Pid dosyasini okur; yoksa/bozuksa None. Surec yasamini kontrol ETMEZ."""
    try:
        return int((tmp_path / "durum" / "pid" / f"{ad}.pid").read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def port_acik(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def surec_yasiyor(pid: int) -> bool:
    """Sinyal 0 ile bakar; ZOMBIE ('Z') "yasiyor" sayilmaz.

    Testin baslattigi sureclerimiz cocugumuzdur: oldukten sonra, beklemedigimiz
    icin girdi tablosunda 'Z' olarak kalirlar. `os.kill(pid, 0)` bir zombiye
    hata vermedigi icin, kontrol edilmezse "hala ayakta" sanilir ve testler
    yanlis basar. Bu yuzden /proc durum alanina da bakilir -- servis kodu
    (`servis.durum.surec_yasiyor`) ayni isi yapar.
    """
    if not pid or pid <= 1:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # var, ama bize ait degil
    return not zombie(pid)


def zombie(pid: int) -> bool:
    """/proc/<pid>/stat durum alani 'Z' ise surec bitmis (zombie) demektir."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    kapanis = stat.rfind(")")
    if kapanis == -1:
        return False
    alanlar = stat[kapanis + 1 :].split()
    return bool(alanlar) and alanlar[0] == "Z"


def topla(pid: int | None) -> None:
    """Cocugumuzu girdi tablosundan toplar (zombi kalmasin).

    `subprocess.Popen` nesnesi olmadan Popen() ile baslatilan surecler icin
    yapilir; beklemezse zombi olarak kalir ve isimizle birlikte sonsuza dek
    yer kaplar. SIGKILL gonderdikten sonra cagrilir.
    """
    if not pid or pid <= 1:
        return
    for _ in range(50):  # en fazla ~1 sn
        try:
            os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            return  # zaten toplanmis / bizim cocugumuz degil
        except OSError:
            return
        if not zombie(pid):
            return
        time.sleep(0.02)


def temizle(pid: int | None) -> None:
    """Testin baslatip SONRASI ONCESI unuttugu surecleri kapatir (SIGKILL)."""
    if not pid or pid <= 1 or not surec_yasiyor(pid):
        return
    import signal as _signal

    try:
        os.killpg(os.getpgid(pid), _signal.SIGKILL)
    except (ProcessLookupError, OSError):
        try:
            os.kill(pid, _signal.SIGKILL)
        except (ProcessLookupError, OSError):
            pass
    topla(pid)