"""Web paneli testleri: Flask test istemcisi, gercek sunucu yok.

Izolasyon: DEVTEMIZLE_DIR tmp_path'e yonlenir; onbellek ve docker taramalari
monkeypatch ile bos doner. pip / npm / docker HICBIR zaman calistirilmaz.
"""

from __future__ import annotations

import os
import re
import threading
from pathlib import Path

import pytest

pytest.importorskip("flask")

from devtemizle import is_akisi  # noqa: E402
from devtemizle import onbellek as onbellek_modulu  # noqa: E402
from devtemizle.web import uygulama_olustur  # noqa: E402

CSRF_DESENI = re.compile(r'<meta name="csrf" content="([^"]+)"')


# ------------------------------------------------------------------ yardimcilar

@pytest.fixture
def izole(tmp_path, monkeypatch):
    """Sahte repo agaci + izole rapor dizini. Gercek ev dizini kullanilmaz."""
    monkeypatch.setenv("DEVTEMIZLE_DIR", str(tmp_path / "raporlar"))
    monkeypatch.delenv("KULE_FRAME_ORIGIN", raising=False)
    monkeypatch.setattr(onbellek_modulu, "onbellek_tara", lambda: [])
    monkeypatch.setattr(
        onbellek_modulu,
        "docker_boyutlari",
        lambda: {"var": False, "imaj": 0, "konteyner": 0, "volume": 0, "build_cache": 0, "hata": None},
    )

    kok = tmp_path / "kok"
    repo = kok / "ornek-uygulama"
    (repo / ".git").mkdir(parents=True)
    (repo / "package.json").write_text("{}", encoding="utf-8")
    (repo / "node_modules").mkdir()
    (repo / "node_modules" / "x.js").write_text("x" * 1000, encoding="utf-8")
    return kok, repo


def _istemci(kok: Path):
    app = uygulama_olustur(kokler=[kok])
    return app, app.test_client()


def _csrf(istemci) -> str:
    cevap = istemci.get("/")
    eslesme = CSRF_DESENI.search(cevap.get_data(as_text=True))
    assert eslesme, "csrf meta etiketi yok"
    return eslesme.group(1)


def _basliklar(csrf: str | None, origin: str = "http://localhost") -> dict:
    basliklar = {"Origin": origin}
    if csrf is not None:
        basliklar["X-CSRF"] = csrf
    return basliklar


def _bekle(app, zaman_asimi: float = 15.0) -> None:
    """Arka plan isini bitirmesini bekler (iş parçacığına katılır)."""
    is_parcacigi = app.config.get("DEVTEMIZLE_IS")
    if is_parcacigi is not None:
        is_parcacigi.join(timeout=zaman_asimi)
        assert not is_parcacigi.is_alive(), "arka plan isi zaman asimina ugradi"


def _tara(app, istemci, csrf: str) -> None:
    cevap = istemci.post("/api/tara", json={"onbellek": False}, headers=_basliklar(csrf))
    assert cevap.status_code == 202
    _bekle(app)


def _aday(istemci, tur: str) -> dict:
    rapor = istemci.get("/api/rapor").get_json()["rapor"]
    return next(a for a in rapor["adaylar"] if a["tur"] == tur)


# ------------------------------------------------------------- guvenlik basliklari

def test_host_yabanci_ise_403(izole):
    kok, _ = izole
    _, istemci = _istemci(kok)
    cevap = istemci.get("/", base_url="http://saldiri.example")
    assert cevap.status_code == 403


def test_host_loopback_kabul(izole):
    kok, _ = izole
    _, istemci = _istemci(kok)
    cevap = istemci.get("/", base_url="http://127.0.0.1:8796")
    assert cevap.status_code == 200


def test_csp_basligi_var_ve_frame_ancestors_none(izole):
    kok, _ = izole
    _, istemci = _istemci(kok)
    csp = istemci.get("/").headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp
    assert "script-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert istemci.get("/").headers["X-Content-Type-Options"] == "nosniff"
    assert istemci.get("/").headers["Referrer-Policy"] == "no-referrer"


def test_kule_origin_gecerliyse_kullanilir(izole, monkeypatch):
    kok, _ = izole
    monkeypatch.setenv("KULE_FRAME_ORIGIN", "http://127.0.0.1:8796")
    _, istemci = _istemci(kok)
    csp = istemci.get("/").headers["Content-Security-Policy"]
    assert "frame-ancestors http://127.0.0.1:8796" in csp
    assert "frame-ancestors 'none'" not in csp


def test_kule_origin_gecersizse_yok_sayilir(izole, monkeypatch):
    kok, _ = izole
    monkeypatch.setenv("KULE_FRAME_ORIGIN", "https://kotu.example")
    _, istemci = _istemci(kok)
    csp = istemci.get("/").headers["Content-Security-Policy"]
    assert "frame-ancestors 'none'" in csp
    assert "kotu.example" not in csp


def test_sayfa_csrf_iceriyor_ve_satir_ici_script_yok(izole):
    kok, _ = izole
    _, istemci = _istemci(kok)
    cevap = istemci.get("/")
    govde = cevap.get_data(as_text=True)
    assert CSRF_DESENI.search(govde)
    assert '<html lang="tr">' in govde
    # Satir ici <script> (src'siz) ve style= niteligi yasak.
    assert not re.search(r"<script(?![^>]*\ssrc=)[^>]*>", govde)
    assert " style=" not in govde
    assert "<style" not in govde


def test_post_csrf_yoksa_403(izole):
    kok, _ = izole
    _, istemci = _istemci(kok)
    cevap = istemci.post("/api/tara", json={"onbellek": False}, headers=_basliklar(None))
    assert cevap.status_code == 403
    assert "hata" in cevap.get_json()


def test_post_yanlis_csrf_403(izole):
    kok, _ = izole
    _, istemci = _istemci(kok)
    cevap = istemci.post("/api/tara", json={}, headers=_basliklar("yanlis-jeton"))
    assert cevap.status_code == 403


def test_post_yanlis_origin_403(izole):
    kok, _ = izole
    _, istemci = _istemci(kok)
    csrf = _csrf(istemci)
    cevap = istemci.post("/api/tara", json={}, headers=_basliklar(csrf, origin="http://evil.example"))
    assert cevap.status_code == 403


def test_post_origin_eksikse_403(izole):
    kok, _ = izole
    _, istemci = _istemci(kok)
    csrf = _csrf(istemci)
    cevap = istemci.post("/api/tara", json={}, headers={"X-CSRF": csrf})
    assert cevap.status_code == 403


def test_get_disindaki_yontem_405(izole):
    kok, _ = izole
    _, istemci = _istemci(kok)
    assert istemci.put("/api/tara").status_code == 405


# --------------------------------------------------------------- tarama akisi

def test_bos_durum_ve_bos_rapor(izole):
    kok, _ = izole
    _, istemci = _istemci(kok)
    durum = istemci.get("/api/durum").get_json()
    assert durum["is"] == "bos"
    rapor = istemci.get("/api/rapor").get_json()
    assert rapor["rapor"] is None
    assert set(rapor["ozet"]) >= {"geri_kazanilabilir", "dikkat_gerektiren", "aday_sayisi"}
    assert rapor["silinen_idler"] == []


def test_tara_202_ve_rapor_node_modules_bulur(izole):
    kok, repo = izole
    app, istemci = _istemci(kok)
    csrf = _csrf(istemci)
    _tara(app, istemci, csrf)

    durum = istemci.get("/api/durum").get_json()
    assert durum["is"] == "bos"
    assert durum["hata"] is None
    assert durum["son_sonuc"]["repo_sayisi"] == 1

    aday = _aday(istemci, "node_modules")
    assert aday["atlandi"] is None
    assert aday["risk"] == "guvenli"
    assert re.fullmatch(r"[0-9a-f]{8,40}", aday["id"])
    assert aday["grup"] == "js"
    assert aday["yeniden"] == "npm install"
    assert Path(aday["yol"]) == repo / "node_modules"


def test_istemci_kok_gonderemez(izole):
    """Sunucu kokleri sabittir; gonderilen 'kokler' alani yok sayilir."""
    kok, _ = izole
    app, istemci = _istemci(kok)
    csrf = _csrf(istemci)
    cevap = istemci.post(
        "/api/tara", json={"onbellek": False, "kokler": ["/etc"]}, headers=_basliklar(csrf)
    )
    assert cevap.status_code == 202
    _bekle(app)
    rapor = istemci.get("/api/rapor").get_json()["rapor"]
    assert rapor["repolar"]
    assert all(Path(r["yol"]).is_relative_to(kok) for r in rapor["repolar"])


def test_tara_onbellek_bool_degilse_400(izole):
    kok, _ = izole
    _, istemci = _istemci(kok)
    csrf = _csrf(istemci)
    cevap = istemci.post("/api/tara", json={"onbellek": "evet"}, headers=_basliklar(csrf))
    assert cevap.status_code == 400


def test_ikinci_tara_calisirken_409(izole, monkeypatch):
    kok, _ = izole
    bekle = threading.Event()
    girildi = threading.Event()

    def yavas_tarama(*args, **kw):
        girildi.set()
        bekle.wait(timeout=10)
        return {"adaylar": [], "repolar": []}

    monkeypatch.setattr(is_akisi, "tam_tarama", yavas_tarama)
    app, istemci = _istemci(kok)
    csrf = _csrf(istemci)

    ilk = istemci.post("/api/tara", json={}, headers=_basliklar(csrf))
    assert ilk.status_code == 202
    assert girildi.wait(timeout=10)

    ikinci = istemci.post("/api/tara", json={}, headers=_basliklar(csrf))
    assert ikinci.status_code == 409
    assert istemci.get("/api/durum").get_json()["is"] == "tarama"

    bekle.set()
    _bekle(app)
    assert istemci.get("/api/durum").get_json()["is"] == "bos"


def test_tarama_hatasi_durumda_saklanir(izole, monkeypatch):
    kok, _ = izole

    def patlar(*args, **kw):
        raise RuntimeError("bilerek")

    monkeypatch.setattr(is_akisi, "tam_tarama", patlar)
    app, istemci = _istemci(kok)
    csrf = _csrf(istemci)
    assert istemci.post("/api/tara", json={}, headers=_basliklar(csrf)).status_code == 202
    _bekle(app)
    durum = istemci.get("/api/durum").get_json()
    assert durum["is"] == "bos"
    assert durum["hata"]
    assert "RuntimeError" in durum["hata"]


def test_ilerleme_geri_cagrisi_adimlari(izole):
    kok, _ = izole
    adimlar: list[tuple[str, int, int]] = []
    is_akisi.tam_tarama(
        [kok], onbellek=False, ilerleme=lambda a, i, n: adimlar.append((a, i, n))
    )
    adlar = [a[0] for a in adimlar]
    assert adlar[0] == "kesif"
    assert ("repo", 1, 1) in adimlar
    assert adlar[-1] == "rapor"


# -------------------------------------------------------------------- silme

def test_sil_gecersiz_kimlik_400(izole):
    kok, _ = izole
    _, istemci = _istemci(kok)
    csrf = _csrf(istemci)
    for govde in ({"idler": ["../../etc/passwd"]}, {"idler": ["ZZZZZZZZ"]},
                  {"idler": []}, {"idler": "abc"}, {}):
        cevap = istemci.post("/api/sil", json=govde, headers=_basliklar(csrf))
        assert cevap.status_code == 400, govde


def test_sil_yol_kabul_etmez(izole):
    """Istemci 'yol' gonderse bile yalnizca 'idler' kullanilir; yol alani yok sayilir."""
    kok, repo = izole
    app, istemci = _istemci(kok)
    csrf = _csrf(istemci)
    _tara(app, istemci, csrf)
    cevap = istemci.post(
        "/api/sil", json={"idler": ["deadbeef12345678"], "yol": str(repo)}, headers=_basliklar(csrf)
    )
    assert cevap.status_code == 202
    _bekle(app)
    assert (repo / "node_modules").is_dir()


def test_sil_gercek_aday_siler_ve_gorunumden_cikarir(izole):
    kok, repo = izole
    app, istemci = _istemci(kok)
    csrf = _csrf(istemci)
    _tara(app, istemci, csrf)
    aday = _aday(istemci, "node_modules")

    cevap = istemci.post("/api/sil", json={"idler": [aday["id"]]}, headers=_basliklar(csrf))
    assert cevap.status_code == 202
    _bekle(app)

    assert not (repo / "node_modules").exists()
    durum = istemci.get("/api/durum").get_json()
    silindi_idler = [a["id"] for a in durum["son_sonuc"]["silindi"]]
    assert aday["id"] in silindi_idler

    gorunum = istemci.get("/api/rapor").get_json()
    assert aday["id"] in gorunum["silinen_idler"]
    assert all(a["id"] != aday["id"] for a in gorunum["rapor"]["adaylar"])


def test_sil_baglanti_asla_silinmez(izole, tmp_path):
    kok, repo = izole
    # node_modules yerine repo disi bir dizine baglanti.
    (repo / "node_modules" / "x.js").unlink()
    (repo / "node_modules").rmdir()
    disari = tmp_path / "disari-dizin"
    disari.mkdir()
    (disari / "onemli.txt").write_text("dokunma", encoding="utf-8")
    try:
        (repo / "node_modules").symlink_to(disari, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("sembolik baglanti olusturulamadi")

    app, istemci = _istemci(kok)
    csrf = _csrf(istemci)
    _tara(app, istemci, csrf)
    aday = _aday(istemci, "node_modules")
    assert aday["atlandi"] == "baglanti"

    cevap = istemci.post("/api/sil", json={"idler": [aday["id"]]}, headers=_basliklar(csrf))
    assert cevap.status_code == 202
    _bekle(app)

    assert (disari / "onemli.txt").read_text(encoding="utf-8") == "dokunma"
    ozet = istemci.get("/api/durum").get_json()["son_sonuc"]
    assert ozet["silindi"] == []
    assert any(a["yol"] == aday["yol"] and a["neden"] == "baglanti" for a in ozet["atlanan"])


def test_sil_raporda_olmayan_kimlik_atlanir(izole):
    kok, repo = izole
    app, istemci = _istemci(kok)
    csrf = _csrf(istemci)
    _tara(app, istemci, csrf)

    bilinmeyen = "deadbeef12345678"
    cevap = istemci.post("/api/sil", json={"idler": [bilinmeyen]}, headers=_basliklar(csrf))
    assert cevap.status_code == 202
    _bekle(app)

    ozet = istemci.get("/api/durum").get_json()["son_sonuc"]
    assert ozet["silindi"] == []
    assert any(a["yol"] == bilinmeyen and a["neden"] == "raporda-yok" for a in ozet["atlanan"])
    assert (repo / "node_modules").is_dir()


def test_dikkat_aday_varsayilan_silinmez(izole):
    kok, repo = izole
    # dist: kanit (package.json) var, risk "dikkat".
    (repo / "dist").mkdir()
    (repo / "dist" / "bundle.js").write_text("y", encoding="utf-8")
    app, istemci = _istemci(kok)
    csrf = _csrf(istemci)
    _tara(app, istemci, csrf)
    aday = _aday(istemci, "dist")
    assert aday["risk"] == "dikkat"

    istemci.post("/api/sil", json={"idler": [aday["id"]]}, headers=_basliklar(csrf))
    _bekle(app)
    assert (repo / "dist").is_dir()
    ozet = istemci.get("/api/durum").get_json()["son_sonuc"]
    assert any(a["yol"] == aday["yol"] and a["neden"] == "risk-dikkat" for a in ozet["atlanan"])

    istemci.post(
        "/api/sil", json={"idler": [aday["id"]], "dikkat_dahil": True}, headers=_basliklar(csrf)
    )
    _bekle(app)
    assert not (repo / "dist").exists()


def test_sil_ikinci_is_calisirken_409(izole, monkeypatch):
    kok, _ = izole
    app, istemci = _istemci(kok)
    csrf = _csrf(istemci)
    _tara(app, istemci, csrf)

    bekle = threading.Event()
    monkeypatch.setattr(
        "devtemizle.web.sunucu.sil_idler",
        lambda *a, **kw: (bekle.wait(timeout=10), {"silindi": [], "silinemedi": [],
                                                  "atlanan": [], "bosalan_bayt": 0,
                                                  "onbellek_sonuclari": []})[1],
    )
    ilk = istemci.post("/api/sil", json={"idler": ["deadbeef12345678"]}, headers=_basliklar(csrf))
    assert ilk.status_code == 202
    ikinci = istemci.post("/api/sil", json={"idler": ["deadbeef12345678"]}, headers=_basliklar(csrf))
    assert ikinci.status_code == 409
    bekle.set()
    _bekle(app)
