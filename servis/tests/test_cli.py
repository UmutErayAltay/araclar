"""CLI sozlesmesi: `python -m servis` GERCEKTEN subprocess olarak calistirilir.

Tanim dosyasi (--tanim / SERVIS_TANIM) ve SERVIS_DIZINI geciciye yonlendirilir:
kullanicinin ~/.servis dizini hicbir testte okunmaz/yazilmaz. Yazma yalniz
tmp_path altindadir; baslatilan surecler test sonunda KAPATILIR.

Kurallar burada sinanir: cikis kodlari (0/1/2), 'Hata: ...' + tracebacksiz kullanim
hatasi, --kuru yazmaz, --json gecerli JSON, tum tablo durumlarini yazar.
"""

from __future__ import annotations

import json
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
    surec_yasiyor,
    tanim_yaz,
    temizle,
)

from servis import surec as surec_modul
from servis.tanim import yukle


@pytest.fixture
def temiz_surecler():
    """CLI'nin baslattigi surecleri test sonunda KAPATIR."""
    izlenen: list[int] = []

    def izle(pid: int | None) -> None:
        if pid:
            izlenen.append(pid)

    try:
        yield izle
    finally:
        for pid in reversed(izlenen):
            temizle(pid)


def _tanim(tmp_path: Path, servisler: dict) -> Path:
    return tanim_yaz(tmp_path / "servisler.toml", servisler)


# --------------------------------------------------------------------------
# durum
# --------------------------------------------------------------------------


def test_durum_tablo_ve_cikis_1(tmp_path):
    """Duren servis: tablo yazilir, cikis 1, traceback YOK."""
    port = bos_port()
    tanim = _tanim(tmp_path, {"web": http_server_tanimi("web", port)})
    proc = run_module_cli("durum", "--tanim", str(tanim), cwd=tmp_path, env_ek=ortam(tmp_path, tanim))
    assert proc.returncode == HEDEF_DEGIL, proc.stderr
    assert "Traceback" not in proc.stderr
    assert "durdu" in proc.stdout


def test_durum_json_cikis_1(tmp_path):
    """--json gecerli JSON yazar (tablo degil)."""
    port = bos_port()
    tanim = _tanim(tmp_path, {"web": http_server_tanimi("web", port)})
    proc = run_module_cli("durum", "--tanim", str(tanim), "--json", cwd=tmp_path, env_ek=ortam(tmp_path, tanim))
    assert proc.returncode == HEDEF_DEGIL
    veri = json.loads(proc.stdout)
    assert veri[0]["ad"] == "web"
    assert veri[0]["durum"] == "durdu"
    assert veri[0]["port"] == port


def test_durum_tek_ad(tmp_path):
    """Verilen ad gosterilir; tanimsiz ad cikis 2."""
    tanim = _tanim(
        tmp_path,
        {"bir": http_server_tanimi("bir", bos_port()), "iki": http_server_tanimi("iki", bos_port())},
    )
    proc = run_module_cli("durum", "bir", "--tanim", str(tanim), "--json", cwd=tmp_path, env_ek=ortam(tmp_path, tanim))
    assert proc.returncode == HEDEF_DEGIL
    assert [o["ad"] for o in json.loads(proc.stdout)] == ["bir"]


def test_durum_ad_verilmezse_tumu(tmp_path):
    """Ad verilmezse tum tanimli servisler alfabetik sirada."""
    tanim = _tanim(
        tmp_path,
        {"zeta": http_server_tanimi("zeta", bos_port()), "alfa": http_server_tanimi("alfa", bos_port())},
    )
    proc = run_module_cli("durum", "--tanim", str(tanim), "--json", cwd=tmp_path, env_ek=ortam(tmp_path, tanim))
    assert [o["ad"] for o in json.loads(proc.stdout)] == ["alfa", "zeta"]


def test_durum_port_dolu_bilinmeyen(tmp_path):
    """Port dolu ama bizim pid dosyamiz yok -> 'port-dolu-bilinmeyen'."""
    port = bos_port()
    sock = dinleyici_ac(port)
    tanim = _tanim(tmp_path, {"yaban": http_server_tanimi("yaban", port)})
    try:
        proc = run_module_cli("durum", "--tanim", str(tanim), "--json", cwd=tmp_path, env_ek=ortam(tmp_path, tanim))
        assert proc.returncode == HEDEF_DEGIL
        assert json.loads(proc.stdout)[0]["durum"] == "port-dolu-bilinmeyen"
    finally:
        sock.close()


# --------------------------------------------------------------------------
# baslat / durdur uzerinden tam dongu (CLI seviyesinde)
# --------------------------------------------------------------------------


def test_cli_baslat_durdur_dongusu(tmp_path, temiz_surecler):
    """Uctan uca: baslat -> durum calisiyor -> durdur -> durum durdu."""
    port = bos_port()
    tanim = _tanim(tmp_path, {"web": http_server_tanimi("web", port)})
    env = ortam(tmp_path, tanim)

    baslat = run_module_cli("baslat", "--tanim", str(tanim), cwd=tmp_path, env_ek=env)
    assert baslat.returncode == 0, baslat.stderr
    try:
        assert port_acik(port)
        pid = int((tmp_path / "durum" / "pid" / "web.pid").read_text(encoding="utf-8").strip())
        temiz_surecler(pid)

        durum = run_module_cli("durum", "--tanim", str(tanim), "--json", cwd=tmp_path, env_ek=env)
        assert durum.returncode == 0, durum.stderr
        assert json.loads(durum.stdout)[0]["durum"] == "calisiyor"

        durdur = run_module_cli("durdur", "--tanim", str(tanim), cwd=tmp_path, env_ek=env)
        assert durdur.returncode == 0, durdur.stderr
        assert not port_acik(port)
    finally:
        # CLI normalde durdurur; test yine de temizler.
        run_module_cli("durdur", "--tanim", str(tanim), "--zorla", cwd=tmp_path, env_ek=env)

    durum = run_module_cli("durum", "--tanim", str(tanim), "--json", cwd=tmp_path, env_ek=env)
    assert json.loads(durum.stdout)[0]["durum"] == "durdu"


def test_cli_baslat_zaten_calisiyor_atlanir(tmp_path, temiz_surecler):
    """Zaten calisan servise ikinci 'baslat' atlanir (cikis 0), yeni pid dogmaz."""
    port = bos_port()
    tanim = _tanim(tmp_path, {"web": http_server_tanimi("web", port)})
    env = ortam(tmp_path, tanim)

    ilk = run_module_cli("baslat", "--tanim", str(tanim), cwd=tmp_path, env_ek=env)
    assert ilk.returncode == 0, ilk.stderr
    try:
        pid = int((tmp_path / "durum" / "pid" / "web.pid").read_text(encoding="utf-8").strip())
        temiz_surecler(pid)
        ikinci = run_module_cli("baslat", "--tanim", str(tanim), "--json", cwd=tmp_path, env_ek=env)
        assert ikinci.returncode == 0, ikinci.stderr
        assert json.loads(ikinci.stdout)[0]["sonuc"] == "zaten-calisiyor"
        pid_aynen = int((tmp_path / "durum" / "pid" / "web.pid").read_text(encoding="utf-8").strip())
        assert pid_aynen == pid, "pid degismemeli"
    finally:
        run_module_cli("durdur", "--tanim", str(tanim), "--zorla", cwd=tmp_path, env_ek=env)


def test_cli_baslat_basarisiz_cikis_1(tmp_path):
    """Hemen sonlanan komut -> 'basarisiz' + log son satirlari + cikis 1."""
    import sys

    port = bos_port()
    tanim = _tanim(
        tmp_path,
        {"patlak": {"port": port, "baslat": [sys.executable, "-c", "raise SystemExit(1)"], "bekle_sn": 20}},
    )
    proc = run_module_cli("baslat", "--tanim", str(tanim), cwd=tmp_path, env_ek=ortam(tmp_path, tanim))
    assert proc.returncode == HEDEF_DEGIL
    assert "basarisiz" in proc.stdout
    assert "Traceback" not in proc.stderr


def test_cli_baslat_bekle_sn_zaman_asimi(tmp_path, temiz_surecler):
    """Port acilmayan servis 'basarisiz', cikis 1 (surec yine de izlenir)."""
    import sys

    port = bos_port()
    tanim = _tanim(
        tmp_path,
        {"sessiz": {"port": port, "baslat": [sys.executable, "-c", "import time; time.sleep(30)"], "bekle_sn": 1}},
    )
    env = ortam(tmp_path, tanim)
    try:
        proc = run_module_cli("baslat", "--tanim", str(tanim), cwd=tmp_path, env_ek=env)
        assert proc.returncode == HEDEF_DEGIL
        assert "basarisiz" in proc.stdout
        try:
            pid = int((tmp_path / "durum" / "pid" / "sessiz.pid").read_text(encoding="utf-8").strip())
            temiz_surecler(pid)
        except (OSError, ValueError):
            pass
    finally:
        run_module_cli("durdur", "sessiz", "--tanim", str(tanim), "--zorla", cwd=tmp_path, env_ek=env)


def test_cli_durdur_port_dolu_bilinmeyene_dokunmaz(tmp_path):
    """CLI seviyesinde: pid dosyasi olmayan dinleyiciye durdur YAPMAZ."""
    port = bos_port()
    sock = dinleyici_ac(port)
    tanim = _tanim(tmp_path, {"yaban": http_server_tanimi("yaban", port)})
    try:
        proc = run_module_cli("durdur", "--tanim", str(tanim), "--zorla", "--json", cwd=tmp_path, env_ek=ortam(tmp_path, tanim))
        assert proc.returncode == HEDEF_DEGIL
        assert json.loads(proc.stdout)[0]["sonuc"] == "port-dolu-bilinmeyen"
        assert port_acik(port), "baskasinin dinleyicisi OLMEDI"
    finally:
        sock.close()


def test_cli_durdur_pid_cmdline_uyusmaz(tmp_path, temiz_surecler):
    """Pid yeniden kullanimi: cmdline uymazsa CLI dokunmaz, cikis 1."""
    import sys
    import subprocess

    port = bos_port()
    yaban = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    temiz_surecler(yaban.pid)
    try:
        pid_dosyasi(tmp_path, "web", f"{yaban.pid}\n")
        # Tanim "http.server" bekliyor; pid dosyasindaki surec python3 -> UYUSMUYOR.
        tanim = _tanim(
            tmp_path,
            {"web": {"port": port, "baslat": ["http.server", str(port), "--bind", "127.0.0.1"]}},
        )
        proc = run_module_cli("durdur", "--tanim", str(tanim), "--zorla", "--json", cwd=tmp_path, env_ek=ortam(tmp_path, tanim))
        assert proc.returncode == HEDEF_DEGIL
        assert json.loads(proc.stdout)[0]["sonuc"] == "pid-cmdline-uyusmuyor"
        assert surec_yasiyor(yaban.pid), "yanlis surec OLMEDI"
    finally:
        temiz_surecler(yaban.pid)


def test_cli_durdur_zaten_durdu_cikis_0(tmp_path):
    """Calismayan ve pid dosyasi olmayan servisi durdur -> 'zaten durdu', cikis 0."""
    port = bos_port()
    tanim = _tanim(tmp_path, {"web": http_server_tanimi("web", port)})
    proc = run_module_cli("durdur", "--tanim", str(tanim), cwd=tmp_path, env_ek=ortam(tmp_path, tanim))
    assert proc.returncode == 0, proc.stderr
    assert "zaten-durdu" in proc.stdout


def test_cli_zorla_olmadan_durmadi(tmp_path, temiz_surecler):
    """SIGTERM'i yoksayan surec: --zorla yoksa 'durmadi', cikis 1."""
    import sys

    port = bos_port()
    kod = "import signal,time\nsignal.signal(signal.SIGTERM, signal.SIG_IGN)\ntime.sleep(300)\n"
    tanim = _tanim(tmp_path, {"direnc": {"port": port, "baslat": [sys.executable, "-c", kod], "bekle_sn": 1}})
    env = ortam(tmp_path, tanim)
    try:
        run_module_cli("baslat", "--tanim", str(tanim), cwd=tmp_path, env_ek=env)
        proc = run_module_cli("durdur", "--tanim", str(tanim), cwd=tmp_path, env_ek=env)
        assert proc.returncode == HEDEF_DEGIL
        assert "durmadi" in proc.stdout
        assert "--zorla" in proc.stdout
    finally:
        run_module_cli("durdur", "--tanim", str(tanim), "--zorla", cwd=tmp_path, env_ek=env)


# --------------------------------------------------------------------------
# --kuru (hicbir sey yazmaz)
# --------------------------------------------------------------------------


def test_cli_kuru_baslat_hicbir_sey_baslatmaz(tmp_path):
    """--kuru: port acilmaz, pid dosyasi YAZILMAZ, KURU CALISTIRMA yazilir."""
    port = bos_port()
    tanim = _tanim(tmp_path, {"web": http_server_tanimi("web", port)})
    proc = run_module_cli("baslat", "--tanim", str(tanim), "--kuru", cwd=tmp_path, env_ek=ortam(tmp_path, tanim))
    assert proc.returncode == 0, proc.stderr
    assert "KURU CALISTIRMA" in proc.stdout
    assert "kuru" in proc.stdout
    assert not port_acik(port)
    assert not (tmp_path / "durum" / "pid").exists(), "kuru calistirmada pid dosyasi YAZILMAMALI"


def test_cli_kuru_durdur_hicbir_sey_oldurmez(tmp_path, temiz_surecler):
    """--kuru: calisan surec KALIR, port KAPANMAZ, pid dosyasi SILINMEZ."""
    import sys

    port = bos_port()
    tanim = _tanim(tmp_path, {"web": http_server_tanimi("web", port)})
    env = ortam(tmp_path, tanim)
    run_module_cli("baslat", "--tanim", str(tanim), cwd=tmp_path, env_ek=env)
    try:
        pid = int((tmp_path / "durum" / "pid" / "web.pid").read_text(encoding="utf-8").strip())
        temiz_surecler(pid)
        proc = run_module_cli("durdur", "--tanim", str(tanim), "--kuru", cwd=tmp_path, env_ek=env)
        assert proc.returncode == 0, proc.stderr
        assert "KURU CALISTIRMA" in proc.stdout
        assert surec_yasiyor(pid), "kuru calistirmada surec OLDURULMEMELI"
        assert port_acik(port), "kuru calistirmada port KAPANMAMALI"
    finally:
        run_module_cli("durdur", "--tanim", str(tanim), "--zorla", cwd=tmp_path, env_ek=env)


def test_cli_kuru_json(tmp_path):
    """--kuru --json: sonuc 'kuru'."""
    port = bos_port()
    tanim = _tanim(tmp_path, {"web": http_server_tanimi("web", port)})
    proc = run_module_cli("baslat", "--tanim", str(tanim), "--kuru", "--json", cwd=tmp_path, env_ek=ortam(tmp_path, tanim))
    assert proc.returncode == 0
    assert json.loads(proc.stdout)[0]["sonuc"] == "kuru"


# --------------------------------------------------------------------------
# kullanim hatasi: cikis 2, 'Hata: ...', traceback YOK
# --------------------------------------------------------------------------


def test_yok_tanim_dosyasi_cikis_2(tmp_path):
    """Tanim dosyasi yok: cikis 2, 'Hata:' + ornek yonlendirmesi, traceback YOK."""
    yok = tmp_path / "yok.toml"
    proc = run_module_cli("durum", "--tanim", str(yok), cwd=tmp_path, env_ek=ortam(tmp_path, yok))
    assert proc.returncode == KULLANIM_HATASI
    assert proc.stderr.startswith("Hata:")
    assert "servisler.toml.ornek" in proc.stderr
    assert "Traceback" not in proc.stderr


def test_bozuk_toml_cikis_2(tmp_path):
    """Bozuk TOML: cikis 2, traceback YOK."""
    tanim = tanim_yaz(tmp_path / "servisler.toml", None, govde="[servis.web\nport = = 1\n")
    proc = run_module_cli("durum", "--tanim", str(tanim), cwd=tmp_path, env_ek=ortam(tmp_path, tanim))
    assert proc.returncode == KULLANIM_HATASI
    assert proc.stderr.startswith("Hata:")
    assert "bozuk TOML" in proc.stderr
    assert "Traceback" not in proc.stderr


def test_gecersiz_tanim_alanlari_cikis_2(tmp_path):
    """Gecersiz alan (port 0) cikis 2, traceback YOK."""
    tanim = _tanim(tmp_path, {"web": {"port": 0, "baslat": ["x"]}})
    proc = run_module_cli("durum", "--tanim", str(tanim), cwd=tmp_path, env_ek=ortam(tmp_path, tanim))
    assert proc.returncode == KULLANIM_HATASI
    assert "Hata:" in proc.stderr
    assert "Traceback" not in proc.stderr


def test_tanimsiz_servis_adi_cikis_2(tmp_path):
    """Olmayan servis adi: cikis 2, tanimli adlar hatada listelenir."""
    tanim = _tanim(tmp_path, {"web": http_server_tanimi("web", bos_port())})
    proc = run_module_cli("durum", "olmayan", "--tanim", str(tanim), cwd=tmp_path, env_ek=ortam(tmp_path, tanim))
    assert proc.returncode == KULLANIM_HATASI
    assert "olmayan" in proc.stderr
    assert "web" in proc.stderr
    assert "Traceback" not in proc.stderr


def test_komut_yok_cikis_2(tmp_path):
    """Alt komut verilmezse argparse hata verir (cikis 2, traceback YOK)."""
    proc = run_module_cli(cwd=tmp_path)
    assert proc.returncode == KULLANIM_HATASI
    assert "Traceback" not in proc.stderr


def test_bilinmeyen_komut_cikis_2(tmp_path):
    """Bilinmeyen alt komut argparse hatasidir (cikis 2)."""
    proc = run_module_cli("uydurma", cwd=tmp_path)
    assert proc.returncode == KULLANIM_HATASI
    assert "Traceback" not in proc.stderr


# --------------------------------------------------------------------------
# SERVIS_TANIM / SERVIS_DIZINI ortam degiskenleri
# --------------------------------------------------------------------------


def test_servis_tanim_ortam_degiskeni(tmp_path):
    """--tanim verilmezse SERVIS_TANIM kullanilir."""
    port = bos_port()
    tanim = _tanim(tmp_path, {"web": http_server_tanimi("web", port)})
    env = {"SERVIS_TANIM": str(tanim), "SERVIS_DIZINI": str(tmp_path / "durum")}
    proc = run_module_cli("durum", "--json", cwd=tmp_path, env_ek=env)
    assert proc.returncode == HEDEF_DEGIL
    assert json.loads(proc.stdout)[0]["ad"] == "web"


def test_tanim_argumani_ortam_degiskenini_eker(tmp_path):
    """--tanim, SERVIS_TANIM'i gecersiz kilar (oncelik sirasi)."""
    port = bos_port()
    tanim = _tanim(tmp_path, {"web": http_server_tanimi("web", port)})
    env = {"SERVIS_TANIM": str(tmp_path / "yok.toml"), "SERVIS_DIZINI": str(tmp_path / "durum")}
    proc = run_module_cli("durum", "--tanim", str(tanim), "--json", cwd=tmp_path, env_ek=env)
    assert proc.returncode == HEDEF_DEGIL, proc.stderr
    assert json.loads(proc.stdout)[0]["ad"] == "web"


def test_servis_dizini_pid_dosyalarini_orada_tutar(tmp_path, temiz_surecler):
    """SERVIS_DIZINI degistirilince pid dosyalari oraya yazilir."""
    port = bos_port()
    tanim = _tanim(tmp_path, {"web": http_server_tanimi("web", port)})
    ozel = tmp_path / "ozel-dizin"
    env = {"SERVIS_TANIM": str(tanim), "SERVIS_DIZINI": str(ozel)}
    proc = run_module_cli("baslat", cwd=tmp_path, env_ek=env)
    assert proc.returncode == 0, proc.stderr
    try:
        assert (ozel / "pid" / "web.pid").is_file(), "pid dosyasi SERVIS_DIZINI'nde olmali"
        assert (ozel / "log" / "web.log").is_file()
        temiz_surecler(int((ozel / "pid" / "web.pid").read_text(encoding="utf-8").strip()))
    finally:
        run_module_cli("durdur", "--tanim", str(tanim), "--zorla", cwd=tmp_path, env_ek=env)


def test_ornek_tanim_dosyasi_durum_calisir(tmp_path):
    """Paketle gelen servisler.toml.ornek durum komutunu PATLATMAZ.

    Ornekteki yollar yer tutucu; hicbiri calisiyor olmak zorunda degil.
    """
    ornek = Path(__file__).resolve().parents[1] / "servisler.toml.ornek"
    proc = run_module_cli("durum", "--tanim", str(ornek), cwd=tmp_path, env_ek=ortam(tmp_path, ornek))
    assert "Traceback" not in proc.stderr, proc.stderr
    assert proc.returncode in (0, HEDEF_DEGIL), proc.stderr
    for ad in ("cor", "kule", "liman", "readbunny-postgres"):
        assert ad in proc.stdout, proc.stdout


def test_ornek_tanim_dosyasi_basar_sifir_kaldirilir(tmp_path, temiz_surecler):
    """--tanim verilmezse env yoksa ~/.servis/servisler.toml aranir (ornek yonlendirmesi)."""
    # HOME geciciye cevrildiginden tanim bulunamaz -> 'Hata: ...' cikis 2.
    proc = run_module_cli("durum", cwd=tmp_path)
    assert proc.returncode == KULLANIM_HATASI
    assert "servisler.toml.ornek" in proc.stderr


# --------------------------------------------------------------------------
# --json her komutta gecerli JSON
# --------------------------------------------------------------------------


def test_json_uc_komutta_da_gecerli(tmp_path, temiz_surecler):
    """durum/baslat/durdur --json gecerli JSON yazar."""
    port = bos_port()
    tanim = _tanim(tmp_path, {"web": http_server_tanimi("web", port)})
    env = ortam(tmp_path, tanim)
    for args in (["durum"], ["baslat"], ["durdur"]):
        proc = run_module_cli(*args, "--tanim", str(tanim), "--json", cwd=tmp_path, env_ek=env)
        assert proc.returncode in (0, HEDEF_DEGIL), proc.stderr
        veri = json.loads(proc.stdout)  # gecerli JSON olmali
        assert isinstance(veri, list) and veri[0]["ad"] == "web"
        temiz_surecler(veri[0].get("pid"))
    # Artik pidsiz kalmasin.
    run_module_cli("durdur", "--tanim", str(tanim), "--zorla", cwd=tmp_path, env_ek=env)