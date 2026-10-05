"""Durum olcumu testleri: port, pid, saglik_url, tablo, --json.

Gercek servisler CALISMAZ. `python3 -m http.server` yalniz GECICI portlarda
(tmp_path) acilir ve test sonunda KAPATILIR. Ag yok (saglik_url 127.0.0.1).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest
from conftest import (
    HEDEF_DEGIL,
    KULLANIM_HATASI,
    bos_port,
    dinleyici_ac,
    http_server_tanimi,
    ortam,
    pid_dosyasi,
    port_acik,
    run_module_cli,
    tanim_yaz,
)

from servis import durum as durum_modul
from servis.tanim import yukle


@pytest.fixture
def izole_dizin(tmp_path, monkeypatch):
    """SERVIS_DIZINI'ni geciciye cevirir: kullanici ~/.servis YAZILMAZ."""
    dizin = tmp_path / "durum"
    monkeypatch.setenv("SERVIS_DIZINI", str(dizin))
    return dizin


@pytest.fixture
def baslanan_server():
    """Gercek bir `python3 -m http.server` acar; test sonunda KAPATIR.

    Bu dosya kodun gercekten yapabilecegini kanitlamak icin gercek bir surec
    baslatir -- cogu test bunu kullanmaz, yalniz surec yasamini dogrular.
    """
    port = bos_port()
    surec = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    bitis = time.monotonic() + 15
    while time.monotonic() < bitis and not port_acik(port):
        time.sleep(0.05)
    assert port_acik(port), "gecici http.server acilmadi"
    try:
        yield port, surec.pid
    finally:
        try:
            os.killpg(os.getpgid(surec.pid), 15)
        except (ProcessLookupError, OSError):
            try:
                surec.kill()
            except ProcessLookupError:
                pass
        surec.wait(timeout=10)


# --------------------------------------------------------------------------
# port yoklama
# --------------------------------------------------------------------------


def test_kapali_port_dinlenmiyor(izole_dizin):
    """Kimsenin dinlemedigi port kapali sayilir."""
    assert durum_modul.port_dinleniyor(bos_port()) is False


def test_dinleyici_aciksa_port_dolu(izole_dizin):
    """Bizim pid dosyamiz olmasa bile port dolu -- durum olcumu yapar."""
    port = bos_port()
    sock = dinleyici_ac(port)
    try:
        assert durum_modul.port_dinleniyor(port) is True
    finally:
        sock.close()


# --------------------------------------------------------------------------
# pid dosyasi okuma
# --------------------------------------------------------------------------


def test_pid_dosyasi_olmayan_servis(izole_dizin):
    """Pid dosyasi yoksa pid None (dosyaya dokunmadan)."""
    assert durum_modul.pid_oku("yok-boyle-bir-servis") is None


@pytest.mark.parametrize("icerik", ["1234\n", "  1234  \n", "1234"])
def test_pid_dosyasi_okunur(izole_dizin, tmp_path, icerik):
    """Beyaz bosluklu/normal pid dosyasi okunur."""
    pid_dosyasi(tmp_path, "tek", icerik)
    assert durum_modul.pid_oku("tek") == 1234


@pytest.mark.parametrize("icerik", ["", "abc", "-5", "0", "12.5"])
def test_pid_dosyasi_bozuk(izole_dizin, tmp_path, icerik):
    """Bozuk/olmayan pid icerigi None doner -- istisna DEGILDIR."""
    pid_dosyasi(tmp_path, "tek", icerik)
    assert durum_modul.pid_oku("tek") is None


def test_pid_dosyasi_dizine_zarar_vermez(izole_dizin):
    """Pid dosyasi oluşturulmaz; dizin yalniz sorulur."""
    assert not durum_modul.pid_yolu("tek").exists()


# --------------------------------------------------------------------------
# surec yasamontrolu
# --------------------------------------------------------------------------


def test_kendi_surecimiz_yasliyor(izole_dizin):
    """Ayakta olan pid True."""
    assert durum_modul.surec_yasiyor(os.getpid()) is True


def test_olmayan_pid_yasamiyor(izole_dizin):
    """Olmayan pid False (sinyal gonderilmez, sadece sorulur)."""
    assert durum_modul.surec_yasiyor(4_000_000) is False


@pytest.mark.parametrize("pid", [0, -1])
def test_gecersiz_pid(izole_dizin, pid):
    """0/negatif pid 'yok' sayilir."""
    assert durum_modul.surec_yasiyor(pid) is False


# --------------------------------------------------------------------------
# saglik_url
# --------------------------------------------------------------------------


def test_saglik_url_olmaz(izole_dizin):
    """Tanimda saglik_url yoksa None (tablo '-' gosterir)."""
    assert durum_modul.saglik_yok(None) is None
    assert durum_modul.saglik_yok("") is None


def test_saglikli_url(baslanan_server):
    """Gercek http.server'a GET 200 doner -> saglikli."""
    port, _ = baslanan_server
    assert durum_modul.saglik_yok(f"http://127.0.0.1:{port}/") == durum_modul.SAGLIKLI


def test_sagliksiz_404(baslanan_server):
    """404 saglikli DEGILDIR (200-399 sart)."""
    port, _ = baslanan_server
    assert durum_modul.saglik_yok(f"http://127.0.0.1:{port}/yok-boyle-bir-yol") == durum_modul.SAGLIKSIZ


def test_saglik_kapali_port(izole_dizin):
    """Kapali port -> baglanti hatasi -> sagliksiz (istisna degil)."""
    assert durum_modul.saglik_yok(f"http://127.0.0.1:{bos_port()}/") == durum_modul.SAGLIKSIZ


def test_saglik_proxy_kullanmaz(baslanan_server, monkeypatch):
    """Yerel adreslere proxy UYGULANMAZ (localhost asla proxy'lenmez)."""
    port, _ = baslanan_server
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:1")
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    assert durum_modul.saglik_yok(f"http://127.0.0.1:{port}/") == durum_modul.SAGLIKLI


# --------------------------------------------------------------------------
# olc(): uclu durumlar
# --------------------------------------------------------------------------


def test_durdu_olcumu(izole_dizin, tmp_path):
    """Port kapali, pid dosyasi yok -> durdu."""
    port = bos_port()
    tanim = tanim_yaz(tmp_path / "servisler.toml", {"tek": http_server_tanimi("tek", port)})
    olcum = durum_modul.olc(yukle(tanim)["tek"])
    assert olcum["durum"] == durum_modul.DURDU
    assert olcum["port_aci"] is False
    assert olcum["pid"] is None
    assert olcum["saglik"] == durum_modul.SAGLIK_YOK


def test_calisiyor_olcumu(izole_dizin, tmp_path, baslanan_server):
    """Port acik + pid dosyamizda canli pid -> calisiyor.

    Gercek surec baslatilir ve fixture onu KAPATIR.
    """
    port, pid = baslanan_server
    pid_dosyasi(tmp_path, "tek", f"{pid}\n")
    tanim = tanim_yaz(tmp_path / "servisler.toml", {"tek": http_server_tanimi("tek", port)})
    olcum = durum_modul.olc(yukle(tanim)["tek"])
    assert olcum["durum"] == durum_modul.CALISIYOR
    assert olcum["pid"] == pid
    assert olcum["port_aci"] is True


def test_port_dolu_bilinmeyen(izole_dizin, tmp_path):
    """Port dolu ama bizim pid dosyamiz yok -> port-dolu-bilinmeyen.

    BU DURUMA DOKUNULMAZ; durum yalnizca bildirir.
    """
    port = bos_port()
    sock = dinleyici_ac(port)
    try:
        tanim = tanim_yaz(tmp_path / "servisler.toml", {"tek": http_server_tanimi("tek", port)})
        olcum = durum_modul.olc(yukle(tanim)["tek"])
        assert olcum["durum"] == durum_modul.PORT_DOLU_BILINMEYEN
        assert olcum["pid"] is None
        assert olcum["pid_dosyasindaki"] is None
    finally:
        sock.close()


def test_olu_pid_ile_port_dolu(izole_dizin, tmp_path):
    """Port dolu ama pid dosyamizdaki pid OLMUS -> yine port-dolu-bilinmeyen."""
    port = bos_port()
    sock = dinleyici_ac(port)
    pid_dosyasi(tmp_path, "tek", "4000000\n")  # kesinlikle yasayan degil
    try:
        tanim = tanim_yaz(tmp_path / "servisler.toml", {"tek": http_server_tanimi("tek", port)})
        olcum = durum_modul.olc(yukle(tanim)["tek"])
        assert olcum["durum"] == durum_modul.PORT_DOLU_BILINMEYEN
        assert olcum["pid"] is None
        assert olcum["pid_dosyasindaki"] == 4_000_000, "dosyadaki deger kaydedilir"
    finally:
        sock.close()


def test_olcumu_salt_okunur(izole_dizin, tmp_path):
    """olc() hicbir dosya YAZMAZ, pid dosyasi olusturmaz."""
    port = bos_port()
    tanim = tanim_yaz(tmp_path / "servisler.toml", {"tek": http_server_tanimi("tek", port)})
    durum_modul.olc(yukle(tanim)["tek"])
    assert not izole_dizin.exists(), "olc() SERVIS_DIZINI'ni olusturmamali"


# --------------------------------------------------------------------------
# tablo / --json
# --------------------------------------------------------------------------


def test_tablo_bos(izole_dizin):
    """Bos listede yalniz baslik yazilir (tablo bozulmaz)."""
    assert durum_modul.tablo([]).split() == ["ad", "port", "durum", "pid", "saglik"]


def test_tablo_sutun_hizali(izole_dizin, tmp_path):
    """Tablo basligi ve satirlari sutun sutun hizali."""
    port = bos_port()
    tanim = tanim_yaz(
        tmp_path / "servisler.toml",
        {
            "kisa": http_server_tanimi("kisa", port),
            "cok-uzun-bir-servis-adi": http_server_tanimi("uzun", port + 1),
        },
    )
    olcumler = [durum_modul.olc(s) for s in yukle(tanim).values()]
    satirlar = durum_modul.tablo(olcumler).splitlines()
    assert len(satirlar) == 3, satirlar
    # Sutunlar iki boslukla ayrilir; 'durum' her satirdaki ayni sutunda olmali.
    sutunlar = [re.split(r"\s{2,}", satir.strip()) for satir in satirlar]
    assert sutunlar[0][2] == "durum"
    assert all(satir[2] == durum_modul.DURDU for satir in sutunlar[1:]), sutunlar


def test_durum_json_cikis_1(izole_dizin, tmp_path):
    """Duren servis varsa tablo + cikis 1; hicbiri calismiyorsa durdu yazilir."""
    port = bos_port()
    tanim = tanim_yaz(tmp_path / "servisler.toml", {"tek": http_server_tanimi("tek", port)})
    proc = run_module_cli("durum", "--tanim", str(tanim), "--json", cwd=tmp_path, env_ek=ortam(tmp_path, tanim))
    assert proc.returncode == HEDEF_DEGIL, proc.stderr
    assert "Traceback" not in proc.stderr, proc.stderr
    import json

    veri = json.loads(proc.stdout)
    assert veri[0]["ad"] == "tek"
    assert veri[0]["durum"] == durum_modul.DURDU


def test_durum_json_tek_calisan_cikis_0(izole_dizin, tmp_path, baslanan_server):
    """Tumu calisiyorsa cikis 0."""
    port, pid = baslanan_server
    pid_dosyasi(tmp_path, "tek", f"{pid}\n")
    tanim = tanim_yaz(tmp_path / "servisler.toml", {"tek": http_server_tanimi("tek", port)})
    proc = run_module_cli("durum", "--tanim", str(tanim), "--json", cwd=tmp_path, env_ek=ortam(tmp_path, tanim))
    assert proc.returncode == 0, proc.stderr


def test_durum_tablosu_cikis_1(izole_dizin, tmp_path):
    """Traceback YOK; tablo basligi yazilir, cikis 1."""
    port = bos_port()
    tanim = tanim_yaz(tmp_path / "servisler.toml", {"tek": http_server_tanimi("tek", port)})
    proc = run_module_cli("durum", "--tanim", str(tanim), cwd=tmp_path, env_ek=ortam(tmp_path, tanim))
    assert proc.returncode == HEDEF_DEGIL, proc.stderr
    assert "Traceback" not in proc.stderr, proc.stderr
    assert "durdu" in proc.stdout
    assert "ad" in proc.stdout and "saglik" in proc.stdout


def test_durum_port_dolu_bilinmeyen_dokunmaz(izole_dizin, tmp_path):
    """Port dolu/bilinmeyen servise durum HIC dokunmaz (salt okunur)."""
    port = bos_port()
    sock = dinleyici_ac(port)
    try:
        tanim = tanim_yaz(tmp_path / "servisler.toml", {"tek": http_server_tanimi("tek", port)})
        proc = run_module_cli("durum", "--tanim", str(tanim), cwd=tmp_path, env_ek=ortam(tmp_path, tanim))
        assert proc.returncode == HEDEF_DEGIL
        assert durum_modul.PORT_DOLU_BILINMEYEN in proc.stdout
        assert not (tmp_path / "durum" / "pid").exists(), "durum pid dosyasi YAZMAMALI"
    finally:
        sock.close()


def test_durum_yok_tanim_cikis_2(tmp_path):
    """Tanim dosyasi yoksa 'Hata:' + cikis 2 (traceback yok)."""
    proc = run_module_cli(
        "durum", "--tanim", str(tmp_path / "yok.toml"), cwd=tmp_path, env_ek=ortam(tmp_path, tmp_path / "yok.toml")
    )
    assert proc.returncode == KULLANIM_HATASI
    assert proc.stderr.startswith("Hata:"), proc.stderr
    assert "Traceback" not in proc.stderr


def test_durum_tanim_service_dizin_ortam_degiskeni(izole_dizin, tmp_path):
    """SERVIS_TANIM ile tanim secilir; SERVIS_DIZINI pid/log dizinidir."""
    port = bos_port()
    tanim = tanim_yaz(tmp_path / "servisler.toml", {"tek": http_server_tanimi("tek", port)})
    proc = run_module_cli("durum", "--json", cwd=tmp_path, env_ek=ortam(tmp_path, tanim))
    assert proc.returncode == HEDEF_DEGIL
    import json

    assert json.loads(proc.stdout)[0]["ad"] == "tek"