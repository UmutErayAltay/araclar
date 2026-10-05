"""baslat / durdur testleri -- en kritik dosya: surec baslatma ve GUVENLIK.

Yalniz `python3 -m http.server` (GECICI port) ve `python3 -c` ile biten komutlar
calisir; gercek servisler (cor/kule/liman/postgres) HICBIR testte calismaz.
Ag YOK. Yazma YALNIZCA tmp_path altindadir: SERVIS_DIZINI ve tanim dosyasi
geciciye yonlendirilir, kullanici ~/.servis HIC OKUNMAZ/YAZILMAZ.

Baglayici kurallar bunlari dogrular:
 - baslat->durum calisiyor->durdur->durum durdu dongusu
 - zaten calisan ATLANIR
 - port dolu ama pid dosyamiz olmayan servise DOKUNULMAZ
 - pid yeniden kullanilmissa (cmdline uyusmuyor) DOKUNULMAZ
 - SIGTERM'e yanit vermeyene SIGKILL YALNIZ --zorla ile
 - --kuru hicbir sey baslatmaz/oldurmez

Baslatilan her surec finally ile TEMIZLENIR; test sonunda surek BIRAKILMAZ.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
from conftest import (
    bos_port,
    dinleyici_ac,
    http_server_tanimi,
    ortam,
    pid_oku,
    port_acik,
    run_module_cli,
    surec_yasiyor,
    tanim_yaz,
    temizle,
    topla,
)

from servis import surec as surec_modul
from servis.tanim import yukle

pytestmark = pytest.mark.usefixtures("izole_dizin")


@pytest.fixture
def izole_dizin(tmp_path, monkeypatch):
    """SERVIS_DIZINI'ni geciciye cevirir: kullanici ~/.servis YAZILMAZ.

    Bu olmadan bir test, kullanicinin gercek pid dosyalarina bakardi.
    """
    dizin = tmp_path / "durum"
    monkeypatch.setenv("SERVIS_DIZINI", str(dizin))
    return dizin


@pytest.fixture
def temiz_surecler():
    """Test sonunda ASIL SUREC KALMASIN diye baslatilan pid'leri toplar."""
    izlenen: list[int] = []

    def izle(pid: int | None) -> None:
        if pid:
            izlenen.append(pid)

    try:
        yield izle
    finally:
        for pid in reversed(izlenen):
            temizle(pid)
            topla(pid)


# --------------------------------------------------------------------------
# baslat -> durum -> durdur -> durum dongusu
# --------------------------------------------------------------------------


def test_baslat_durdur_dongusu(tmp_path, temiz_surecler):
    """Tam dongu: baslat -> calisiyor -> durdur -> durdu."""
    port = bos_port()
    tanim = tanim_yaz(tmp_path / "servisler.toml", {"web": http_server_tanimi("web", port)})
    servis = yukle(tanim)["web"]

    sonuc = surec_modul.baslat(servis)
    temiz_surecler(sonuc.get("pid"))
    try:
        assert sonuc["sonuc"] == surec_modul.CALISTI, sonuc
        assert port_acik(port)
        assert pid_oku(tmp_path, "web") == sonuc["pid"]
        assert surec_modul.baslat(servis)["sonuc"] == surec_modul.ZATEN_CALISIYOR

        from servis import durum as durum_modul

        assert durum_modul.olc(servis)["durum"] == durum_modul.CALISIYOR

        durdur = surec_modul.durdur(servis)
        assert durdur["sonuc"] == surec_modul.DURDU_SONUC, durdur
        assert not port_acik(port), "durdurma sonrasi port kapali olmali"
        assert pid_oku(tmp_path, "web") is None, "pid dosyasi silinmeli"
        assert durum_modul.olc(servis)["durum"] == durum_modul.DURDU
    finally:
        temiz_surecler(sonuc.get("pid"))


def test_baslat_pid_ve_log_dosyasi(tmp_path, temiz_surecler):
    """Baslatma pid dosyasi ve log dosyasi yazar (log stdout+stderr)."""
    port = bos_port()
    tanim = tanim_yaz(tmp_path / "servisler.toml", {"web": http_server_tanimi("web", port)})
    servis = yukle(tanim)["web"]

    sonuc = surec_modul.baslat(servis)
    temiz_surecler(sonuc.get("pid"))
    try:
        assert sonuc["sonuc"] == surec_modul.CALISTI, sonuc
        assert (tmp_path / "durum" / "pid" / "web.pid").is_file()
        assert (tmp_path / "durum" / "log" / "web.log").is_file()
        # http.server istege bagli bilgi yazar; log dosyasi BOS olmamali.
        assert (tmp_path / "durum" / "log" / "web.log").stat().st_size > 0
    finally:
        temiz_surecler(sonuc.get("pid"))
        surec_modul.durdur(servis)


def test_baslat_sonrasi_surec_gercekten_yasliyor(tmp_path, temiz_surecler):
    """Baslatilan pid gercekten ayaktadir (sahte pid yazilmaz)."""
    port = bos_port()
    tanim = tanim_yaz(tmp_path / "servisler.toml", {"web": http_server_tanimi("web", port)})
    servis = yukle(tanim)["web"]

    sonuc = surec_modul.baslat(servis)
    temiz_surecler(sonuc.get("pid"))
    try:
        assert surec_yasiyor(sonuc["pid"])
    finally:
        surec_modul.durdur(servis)


def test_baslat_yeniden_baslatmaz(tmp_path, temiz_surecler):
    """Calisan servise ikinci baslat atlanir; yeni surec dogmaz."""
    port = bos_port()
    tanim = tanim_yaz(tmp_path / "servisler.toml", {"web": http_server_tanimi("web", port)})
    servis = yukle(tanim)["web"]

    ilk = surec_modul.baslat(servis)
    temiz_surecler(ilk.get("pid"))
    try:
        ikinci = surec_modul.baslat(servis)
        assert ikinci["sonuc"] == surec_modul.ZATEN_CALISIYOR
        assert pid_oku(tmp_path, "web") == ilk["pid"], "pid degismemeli"
    finally:
        surec_modul.durdur(servis)


# --------------------------------------------------------------------------
# bekle_sn / basarisiz baslatma
# --------------------------------------------------------------------------


def test_bekle_sn_zaman_asimi_hemen_cikan_komut(tmp_path):
    """Hemen sonlanan komut -> bekle_sn dolmasin, 'basarisiz' + cikis kodu mesaji."""
    port = bos_port()
    tanim = tanim_yaz(
        tmp_path / "servisler.toml",
        {
            "patlak": {
                "port": port,
                "baslat": [sys.executable, "-c", "raise SystemExit(3)"],
                "bekle_sn": 20,
            }
        },
    )
    servis = yukle(tanim)["patlak"]
    baslangic = time.monotonic()
    sonuc = surec_modul.baslat(servis)
    sure = time.monotonic() - baslangic

    assert sonuc["sonuc"] == surec_modul.BASARISIZ, sonuc
    assert "3" in sonuc["mesaj"], sonuc["mesaj"]
    assert sure < 10, f"bekle_sn=20 olmasina ragmen {sure:.1f} sn bekledi"
    # Basarisizlikta kalma pid dosyasi BIRAKILMAZ.
    assert pid_oku(tmp_path, "patlak") is None


def test_bekle_sn_zaman_asimi_port_acilmaz(tmp_path, temiz_surecler):
    """Port acilmazsa bekle_sn sonunda 'basarisiz'; surec yine de yasliyor olabilir."""
    port = bos_port()
    tanim = tanim_yaz(
        tmp_path / "servisler.toml",
        {
            "sessiz": {
                "port": port,
                "baslat": [sys.executable, "-c", "import time; time.sleep(30)"],
                "bekle_sn": 1,
            }
        },
    )
    servis = yukle(tanim)["sessiz"]
    sonuc = surec_modul.baslat(servis)
    temiz_surecler(sonuc.get("pid"))
    try:
        assert sonuc["sonuc"] == surec_modul.BASARISIZ, sonuc
        assert "acilmadi" in sonuc["mesaj"]
        assert surec_yasiyor(sonuc["pid"]), "surec yine de ayakta (izlemeli)"
    finally:
        surec_modul.durdur(servis, zorla=True)


def test_baslatilamayan_komut(tmp_path):
    """Boyle bir komut yoksa 'basarisiz', istisna degil."""
    port = bos_port()
    tanim = tanim_yaz(
        tmp_path / "servisler.toml",
        {"yok": {"port": port, "baslat": [str(tmp_path / "boyle-bir-dosya-yok")]}},
    )
    sonuc = surec_modul.baslat(yukle(tanim)["yok"])
    assert sonuc["sonuc"] == surec_modul.BASARISIZ
    assert "baslatilamadi" in sonuc["mesaj"]


def test_baslat_olmayan_cwd(tmp_path):
    """cwd yoksa baslatma yapilmaz (hata 'basarisiz')."""
    port = bos_port()
    tanim = tanim_yaz(
        tmp_path / "servisler.toml",
        {"web": http_server_tanimi("web", port, dizin=tmp_path / "yok-boyle-bir-dizin")},
    )
    sonuc = surec_modul.baslat(yukle(tanim)["web"])
    assert sonuc["sonuc"] == surec_modul.BASARISIZ
    assert "cwd" in sonuc["mesaj"]
    assert pid_oku(tmp_path, "web") is None


def test_baslat_saglik_url_olan_servis(tmp_path, temiz_surecler):
    """saglik_url tanimliysa saglikli olana kadar beklenir."""
    port = bos_port()
    ayarlar = http_server_tanimi("web", port)
    ayarlar["saglik_url"] = f"http://127.0.0.1:{port}/"
    tanim = tanim_yaz(tmp_path / "servisler.toml", {"web": ayarlar})

    servis = yukle(tanim)["web"]
    sonuc = surec_modul.baslat(servis)
    temiz_surecler(sonuc.get("pid"))
    try:
        from servis import durum as durum_modul

        assert sonuc["sonuc"] == surec_modul.CALISTI, sonuc
        assert durum_modul.olc(servis)["saglik"] == durum_modul.SAGLIKLI
    finally:
        surec_modul.durdur(servis)


def test_baslat_404_saglikli_sayilmaz(tmp_path, temiz_surecler):
    """saglik_url 404 donerse servis sagliksiz sayilir -> basarisiz."""
    port = bos_port()
    ayarlar = http_server_tanimi("web", port)
    ayarlar["saglik_url"] = f"http://127.0.0.1:{port}/yok-boyle-bir-yol"
    tanim = tanim_yaz(tmp_path / "servisler.toml", {"web": ayarlar})

    servis = yukle(tanim)["web"]
    sonuc = surec_modul.baslat(servis)
    temiz_surecler(sonuc.get("pid"))
    try:
        assert sonuc["sonuc"] == surec_modul.BASARISIZ, sonuc
    finally:
        surec_modul.durdur(servis, zorla=True)


# --------------------------------------------------------------------------
# GUVENLIK: port dolu ama pid dosyamiz yok -> ASLA dokunma
# --------------------------------------------------------------------------


def test_port_dolu_bilinmeyen_servise_dokunulmaz(tmp_path):
    """Pid dosyamiz olmayan dinleyiciye durdur YAPMAZ.

    Bu, aracin en onemli guvenlik kuralidir: port dolu olsa bile yalniz kendi
    pid dosyamizdaki surece sinyal gondeririz.
    """
    port = bos_port()
    sock = dinleyici_ac(port)
    tanim = tanim_yaz(tmp_path / "servisler.toml", {"yaban": http_server_tanimi("yaban", port)})
    servis = yukle(tanim)["yaban"]

    # Bizim pid dosyamiz YOK: dinleyici "baskasinin" portu.
    assert pid_oku(tmp_path, "yaban") is None
    try:
        sonuc = surec_modul.durdur(servis, zorla=True)
        assert sonuc["sonuc"] == surec_modul.PORT_DOLU_BILINMEYEN, sonuc
        assert "dokunulmadi" in sonuc["mesaj"]
        # Dinleyici HALA ayakta ve port hala dolu.
        assert port_acik(port), "baskasinin dinleyicisi OLMEDI (asla kapatilmamali)"
    finally:
        sock.close()


def test_olu_pid_dosyasi_ile_port_dolu(tmp_path):
    """Pid dosyamizdaki pid olu ise durdur onu 'zaten durdu' sayar.

    Olmus bir pid zaten hedef durumdadir; port dolu olsa bile sinyal GIDMEZ.
    """
    port = bos_port()
    sock = dinleyici_ac(port)
    (tmp_path / "durum" / "pid").mkdir(parents=True, exist_ok=True)
    (tmp_path / "durum" / "pid" / "yaban.pid").write_text("4000000\n", encoding="utf-8")
    tanim = tanim_yaz(tmp_path / "servisler.toml", {"yaban": http_server_tanimi("yaban", port)})

    try:
        sonuc = surec_modul.durdur(yukle(tanim)["yaban"], zorla=True)
        assert sonuc["sonuc"] == surec_modul.ZATEN_DURDU, sonuc
        assert port_acik(port), "baskasinin dinleyicisi OLMEDI"
    finally:
        sock.close()


def test_baslat_port_doluysa_yine_baslatmaz(tmp_path):
    """Port dolu/bilinmeyen servise baslat da dokunmaz; durum bildirir.

    baslat, hedef duruma gelmedigi icin sureci baslatip basarisiz olur; ama
    ONCEDEN calisiyor sayilmadigi icin port dolu bir yabancinin uzerine
    ikinci surec ACILMAZ (port zaten dolu oldugu icin zaten acilamaz).
    """
    port = bos_port()
    sock = dinleyici_ac(port)
    tanim = tanim_yaz(tmp_path / "servisler.toml", {"yaban": http_server_tanimi("yaban", port, bekle_sn=1)})
    try:
        sonuc = surec_modul.baslat(yukle(tanim)["yaban"])
        if sonuc.get("pid"):
            temizle(sonuc["pid"])
        assert sonuc["sonuc"] == surec_modul.BASARISIZ, sonuc
        assert port_acik(port)
    finally:
        sock.close()


# --------------------------------------------------------------------------
# GUVENLIK: pid yeniden kullanimi (cmdline uyusmuyor)
# --------------------------------------------------------------------------


def test_pid_cmdline_uyusmuyor_dokunulmaz(tmp_path, temiz_surecler):
    """Pid dosyamiz yanlis bir surece aitse durdur O SURECE DOKUNMAZ.

    Simule: pid dosyasina, tanimdaki komuttan FARKLI bir surecin pid'i yazilir
    (pid yeniden kullanim taklidi).
    """
    port = bos_port()
    # Tanimimiz "http.server" diye bir komut bekliyor; pid dosyasindaki surec ise
    # python3 -> argv[0] temel adi TUTMADI.
    tanim = tanim_yaz(
        tmp_path / "servisler.toml",
        {"web": {"port": port, "baslat": ["http.server", str(port), "--bind", "127.0.0.1"]}},
    )
    servis = yukle(tanim)["web"]

    # Tanimimiz http.server; pid dosyasina python3 -c ile AYRI bir surec yaziyoruz.
    yanlis = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    temiz_surecler(yanlis.pid)
    try:
        (tmp_path / "durum" / "pid").mkdir(parents=True, exist_ok=True)
        (tmp_path / "durum" / "pid" / "web.pid").write_text(f"{yanlis.pid}\n", encoding="utf-8")

        assert not surec_modul.cmdline_uyusuyor(yanlis.pid, "http.server"), "ayirt etmeli"
        sonuc = surec_modul.durdur(servis, zorla=True)
        assert sonuc["sonuc"] == surec_modul.UYUSMUYOR, sonuc
        assert "dokunulmadi" in sonuc["mesaj"]
        assert surec_yasiyor(yanlis.pid), "yanlis surec OLMEDI (dokunulmamali)"
        assert pid_oku(tmp_path, "web") == yanlis.pid, "pid dosyasi silinmemeli"
    finally:
        temiz_surecler(yanlis.pid)


def test_cmdline_uyusuyor_kendi_surecimiz(tmp_path):
    """Kendimizin cmdline'i tanimdaki baslat[0] ile eslesir."""
    argv0 = surec_modul._argv0_duruyor([sys.executable, "-m", "http.server"])
    assert surec_modul.cmdline_uyusuyor(os.getpid(), argv0)


def test_cmdline_uyusmuyor_yanlis_isim(tmp_path):
    """Baska bir programin adi eslesmez."""
    assert not surec_modul.cmdline_uyusuyor(os.getpid(), "http.server")


def test_cmdline_okunamazsa_uyusuyor_sayilir():
    """/proc yoksa/okunamazsa dogrulama yapilamaz -> guvenli varsayim."""
    assert surec_modul.cmdline_oku(4_000_000) is None
    assert surec_modul.cmdline_uyusuyor(4_000_000, "http.server") is True


def test_olmayan_pidin_cmdlinesi_yok():
    """Olmayan pid icin cmdline None."""
    assert surec_modul.cmdline_oku(4_000_000) is None


# --------------------------------------------------------------------------
# zorla / SIGTERM yanitsiz surec
# --------------------------------------------------------------------------


def test_sigterm_i_yoksay_surec_yalniz_zorla_ile_olur(tmp_path, temiz_surecler):
    """SIGTERM'i yoksayan surec --zorla OLMADAN birakilir."""
    port = bos_port()
    # SIGTERM'i yoksayan, SIGKILL'e gerek duyan sahte surec.
    kod = (
        "import signal,time,sys\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "sys.stderr.write('catisma basladi\\n'); sys.stderr.flush()\n"
        "time.sleep(300)\n"
    )
    tanim = tanim_yaz(
        tmp_path / "servisler.toml",
        {"direnc": {"port": port, "baslat": [sys.executable, "-c", kod], "bekle_sn": 1}},
    )
    servis = yukle(tanim)["direnc"]

    baslat = surec_modul.baslat(servis)
    temiz_surecler(baslat.get("pid"))
    assert baslat["sonuc"] == surec_modul.BASARISIZ, "port acilmadi -> basarisiz (izlemeye alir)"

    ilk = surec_modul.durdur(servis)  # --zorla YOK
    assert ilk["sonuc"] == surec_modul.DURMADI, ilk
    assert "--zorla" in ilk["mesaj"], ilk["mesaj"]
    assert surec_yasiyor(baslat["pid"]), "durmadan sonra hala ayakta olmali"

    ikinci = surec_modul.durdur(servis, zorla=True)
    topla(baslat["pid"])  # SIGKILL sonrasi zombi kalmasin
    assert ikinci["sonuc"] == surec_modul.DURDU_SONUC, ikinci
    assert not surec_yasiyor(baslat["pid"]), "--zorla ile OLMELI"


def test_zorla_olmadan_pid_dosyasi_kalir(tmp_path, temiz_surecler):
    """Basarisiz durdurmada pid dosyasi SILINMEZ (sonra --zorla deneyebilirsin)."""
    port = bos_port()
    kod = "import signal,time,sys\nsignal.signal(signal.SIGTERM, signal.SIG_IGN)\ntime.sleep(300)\n"
    tanim = tanim_yaz(
        tmp_path / "servisler.toml",
        {"direnc": {"port": port, "baslat": [sys.executable, "-c", kod], "bekle_sn": 1}},
    )
    servis = yukle(tanim)["direnc"]
    baslat = surec_modul.baslat(servis)
    temiz_surecler(baslat.get("pid"))
    try:
        assert surec_modul.durdur(servis)["sonuc"] == surec_modul.DURMADI
        assert pid_oku(tmp_path, "direnc") == baslat["pid"], "pid dosyasi korunmali"
    finally:
        surec_modul.durdur(servis, zorla=True)


# --------------------------------------------------------------------------
# tanimdaki `durdur` komutu (or. cor stop)
# --------------------------------------------------------------------------


def test_durdur_komutu_calistirilir(tmp_path, temiz_surecler):
    """Tanimda `durdur` varsa pid sinyali yerine O komut calisir.

    Komut servisi gercekten durdurur (isaret yazar) -- boylece `durdur`
    bekledigi iki kosulu da (surec olu, port kapali) saglar.
    """
    port = bos_port()
    isaret = tmp_path / "durdur-cagrildi"
    pid_dosya = tmp_path / "durum" / "pid" / "web.pid"
    kod = (
        "import os, signal\n"
        f"open({str(isaret)!r}, 'w').write('x')\n"
        f"pid = int(open({str(pid_dosya)!r}).read())\n"
        "os.killpg(os.getpgid(pid), signal.SIGTERM)\n"
    )
    tanim = tanim_yaz(
        tmp_path / "servisler.toml",
        {"web": {**http_server_tanimi("web", port), "durdur": [sys.executable, "-c", kod]}},
    )
    servis = yukle(tanim)["web"]

    baslat = surec_modul.baslat(servis)
    temiz_surecler(baslat.get("pid"))
    try:
        assert baslat["sonuc"] == surec_modul.CALISTI
        sonuc = surec_modul.durdur(servis)
        assert isaret.is_file(), "tanimdaki durdur komutu calismali"
        assert sonuc["sonuc"] == surec_modul.DURDU_SONUC, sonuc
        assert "durdur komutu" in sonuc["mesaj"]
        # SIGTERM gonderildi; surecin gercekten bitmesi birkac surebilir.
        bitis = time.monotonic() + 5
        while time.monotonic() < bitis and surec_yasiyor(baslat["pid"]):
            time.sleep(0.05)
        topla(baslat["pid"])
        assert not surec_yasiyor(baslat["pid"]), "durdur komutu sureci bitirmis olmali"
    finally:
        temiz_surecler(baslat.get("pid"))


def test_durdur_komutu_calismazsa(tmp_path, temiz_surecler):
    """Tanimdaki durdur komutu yoksa calisamiyorsa hata, istisna degil."""
    port = bos_port()
    tanim = tanim_yaz(
        tmp_path / "servisler.toml",
        {
            "web": {
                **http_server_tanimi("web", port),
                "durdur": [str(tmp_path / "boyle-bir-dosya-yok"), "stop"],
            }
        },
    )
    servis = yukle(tanim)["web"]
    baslat = surec_modul.baslat(servis)
    temiz_surecler(baslat.get("pid"))
    try:
        assert baslat["sonuc"] == surec_modul.CALISTI
        sonuc = surec_modul.durdur(servis)
        assert sonuc["sonuc"] == surec_modul.DURMADI, sonuc
        assert surec_yasiyor(baslat["pid"]), "surec hala ayakta (dokunulmadi)"
    finally:
        temiz_surecler(baslat.get("pid"))


def test_durdur_sonrasi_pid_dosyasi_silinir(tmp_path, temiz_surecler):
    """Basarili durdurmadan sonra pid dosyasi SILINIR."""
    port = bos_port()
    tanim = tanim_yaz(tmp_path / "servisler.toml", {"web": http_server_tanimi("web", port)})
    servis = yukle(tanim)["web"]
    baslat = surec_modul.baslat(servis)
    temiz_surecler(baslat.get("pid"))
    try:
        assert baslat["sonuc"] == surec_modul.CALISTI
        assert surec_modul.durdur(servis)["sonuc"] == surec_modul.DURDU_SONUC
        assert not (tmp_path / "durum" / "pid" / "web.pid").exists()
    finally:
        temiz_surecler(baslat.get("pid"))


def test_pid_dosyasi_olmayan_durdur(tmp_path):
    """Pid dosyasi yoksa ve port kapaliysa 'zaten durdu'."""
    port = bos_port()
    tanim = tanim_yaz(tmp_path / "servisler.toml", {"web": http_server_tanimi("web", port)})
    sonuc = surec_modul.durdur(yukle(tanim)["web"])
    assert sonuc["sonuc"] == surec_modul.ZATEN_DURDU
    assert not port_acik(port)


# --------------------------------------------------------------------------
# --kuru
# --------------------------------------------------------------------------


def test_kuru_baslat_hicbir_sey_baslatmaz(tmp_path):
    """--kuru: surec baslatilmaz, pid dosyasi YAZILMAZ, port kapanmaz."""
    port = bos_port()
    tanim = tanim_yaz(tmp_path / "servisler.toml", {"web": http_server_tanimi("web", port)})
    sonuc = surec_modul.baslat(yukle(tanim)["web"], kuru=True)
    assert sonuc["sonuc"] == surec_modul.KURU
    assert "baslatilacak" in sonuc["mesaj"]
    assert not port_acik(port), "kuru calistirmada port ACILMAMALI"
    assert pid_oku(tmp_path, "web") is None


def test_kuru_durdur_hicbir_sey_oldurmez(tmp_path, temiz_surecler):
    """--kuru: calisan surec OLDURULMEZ, pid dosyasi KALIR."""
    port = bos_port()
    tanim = tanim_yaz(tmp_path / "servisler.toml", {"web": http_server_tanimi("web", port)})
    servis = yukle(tanim)["web"]
    baslat = surec_modul.baslat(servis)
    temiz_surecler(baslat.get("pid"))
    try:
        assert baslat["sonuc"] == surec_modul.CALISTI
        sonuc = surec_modul.durdur(servis, kuru=True)
        assert sonuc["sonuc"] == surec_modul.KURU
        assert "durdurulacak" in sonuc["mesaj"]
        assert surec_yasiyor(baslat["pid"]), "kuru calistirmada surec OLDURULMEMELI"
        assert port_acik(port), "kuru calistirmada port KAPANMAMALI"
        assert pid_oku(tmp_path, "web") == baslat["pid"], "pid dosyasi SILINMEMELI"
    finally:
        surec_modul.durdur(servis, zorla=True)


def test_kuru_durdur_pid_yoksa(tmp_path):
    """Kuru calistirmada pid dosyasi yoksa 'zaten durdu' yonlendirmesi yazar."""
    port = bos_port()
    tanim = tanim_yaz(tmp_path / "servisler.toml", {"web": http_server_tanimi("web", port)})
    sonuc = surec_modul.durdur(yukle(tanim)["web"], kuru=True)
    assert sonuc["sonuc"] == surec_modul.KURU
    assert "zaten durdu" in sonuc["mesaj"]


def test_kuru_durdur_port_doluysa_dokunmaz(tmp_path):
    """Kuru calistirmada port dolu/bilinmeyen servise de dokunulmaz."""
    port = bos_port()
    sock = dinleyici_ac(port)
    tanim = tanim_yaz(tmp_path / "servisler.toml", {"yaban": http_server_tanimi("yaban", port)})
    try:
        sonuc = surec_modul.durdur(yukle(tanim)["yaban"], zorla=True, kuru=True)
        assert sonuc["sonuc"] == surec_modul.KURU
        assert port_acik(port), "dokunulmamali"
    finally:
        sock.close()


# --------------------------------------------------------------------------
# log yardimcilari
# --------------------------------------------------------------------------


def test_log_son_satirlar_yok(tmp_path):
    """Log dosyasi yoksa bos liste (istisna degil)."""
    assert surec_modul.log_son_satirlar("yok-boyle-bir-servis") == []


def test_log_son_satirlar_son_n(tmp_path):
    """Log'un son N satiri doner."""
    log = tmp_path / "durum" / "log" / "web.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("\n".join(f"satir {i}" for i in range(1, 21)), encoding="utf-8")
    assert surec_modul.log_son_satirlar("web", 5) == [f"satir {i}" for i in range(16, 21)]


# --------------------------------------------------------------------------
# gercek surece bagli: surec grubu sinyali (cocuk surecli senaryo)
# --------------------------------------------------------------------------


def test_baslat_cocuk_sureci_de_kapatir(tmp_path, temiz_surecler):
    """start_new_session: durdurma surec GRUBUNU sinyaller, cocuklar da kapanir.

    Servis cogu zaman kendi altinda alt surecler baslatir (veritabani vb.).
    """
    port = bos_port()
    cocuk_dosya = tmp_path / "cocuk.pid"
    kod = (
        "import subprocess,sys,time\n"
        "alt = subprocess.Popen([sys.executable,'-c','import time; time.sleep(300)'])\n"
        f"open({str(cocuk_dosya)!r},'w').write(str(alt.pid))\n"
        "time.sleep(300)\n"
    )
    tanim = tanim_yaz(
        tmp_path / "servisler.toml",
        {"web": {"port": port, "baslat": [sys.executable, "-c", kod], "bekle_sn": 1}},
    )
    servis = yukle(tanim)["web"]
    baslat = surec_modul.baslat(servis)
    temiz_surecler(baslat.get("pid"))
    try:
        assert baslat["sonuc"] == surec_modul.BASARISIZ  # port acilmadi
        assert cocuk_dosya.is_file(), "cocuk surec baslatilmadi"
        cocuk_pid = int(cocuk_dosya.read_text(encoding="utf-8").strip())
        temiz_surecler(cocuk_pid)

        assert surec_modul.durdur(servis)["sonuc"] == surec_modul.DURDU_SONUC
        bitis = time.monotonic() + 5
        while time.monotonic() < bitis and surec_yasiyor(cocuk_pid):
            time.sleep(0.1)
        assert not surec_yasiyor(cocuk_pid), "cocuk surec de kapanmali (grup sinyali)"
    finally:
        temiz_surecler(baslat.get("pid"))