"""Web paneli: rota sözleşmesi, guvenlik basliklari, Host/CSP/405, JS temizligi.

Sunucu GERCEK process olarak BASLATILMAZ: Flask test client kullanilir.
Tarama kaynagi `app_olustur(kaynak)` ile sahtelenir.
"""

from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

from conftest import SahteSurec, baglanti
from liman.web import sunucu
from liman.web.sunucu import app_olustur

WEB_KOK = Path(sunucu.__file__).parent


@pytest.fixture
def kaynak():
    """Panelin tarama kaynagi: iki dinleyici (biri disa acik)."""
    return lambda: [
        baglanti(3000, ip="0.0.0.0", pid=101),
        baglanti(8770, pid=100),
    ]


@pytest.fixture
def web_client(kaynak):
    return app_olustur(kaynak).test_client()


@pytest.fixture(autouse=True)
def temiz_kule(monkeypatch: pytest.MonkeyPatch) -> None:
    """KULE_FRAME_ORIGIN testler arasi sizmasin."""
    monkeypatch.delenv("KULE_FRAME_ORIGIN", raising=False)


# -- rotalar -----------------------------------------------------------------


def test_ana_sayfa_200(web_client) -> None:
    cevap = web_client.get("/")
    assert cevap.status_code == 200
    govde = cevap.get_data(as_text=True)
    assert "liman" in govde
    assert "8770" in govde and "3000" in govde


def test_api_durum_200_sema(web_client) -> None:
    cevap = web_client.get("/api/durum")
    assert cevap.status_code == 200
    veri = json.loads(cevap.get_data(as_text=True))
    assert set(veri) == {"dinleyenler", "ozet", "bos"}
    assert veri["ozet"] == {"toplam": 2, "disa_acik": 1, "yerel": 1}
    assert isinstance(veri["bos"], list)
    assert all(isinstance(p, int) for p in veri["bos"])


def test_api_durum_turkce_kacissiz(web_client) -> None:
    """ensure_ascii=False: kapsam metni panelde ham gelir."""
    ham = web_client.get("/api/durum").get_data(as_text=True)
    assert "\\u" not in ham


def test_bos_listesi_sayfalama_her_zaman(web_client) -> None:
    """`bos` listesi her istekte yeniden hesaplanir (aralik + adet)."""
    veri = json.loads(web_client.get("/api/durum").get_data(as_text=True))
    assert len(veri["bos"]) == sunucu.BOS_ADET
    assert all(sunucu.BOS_ARALIK[0] <= p <= sunucu.BOS_ARALIK[1] for p in veri["bos"])


# -- guvenlik ----------------------------------------------------------------


def test_kotu_host_403(web_client) -> None:
    cevap = web_client.get("/", headers={"Host": "evil.example"})
    assert cevap.status_code == 403


def test_kotu_host_api_da_403(web_client) -> None:
    assert web_client.get("/api/durum", headers={"Host": "evil.example"}).status_code == 403


def test_localhost_ve_ip_kabul(web_client) -> None:
    assert web_client.get("/", headers={"Host": "127.0.0.1:8795"}).status_code == 200
    assert web_client.get("/", headers={"Host": "localhost"}).status_code == 200


def test_yalniz_get_405(web_client) -> None:
    assert web_client.post("/").status_code == 405
    assert web_client.post("/api/durum").status_code == 405


def test_405_gutvenlik_basligi_tasi(web_client) -> None:
    cevap = web_client.post("/")
    assert cevap.headers["X-Content-Type-Options"] == "nosniff"


def test_csp_basligi_script_src_self(web_client) -> None:
    csp = web_client.get("/").headers["Content-Security-Policy"]
    assert "script-src 'self'" in csp
    assert "style-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp


def test_guvenlik_basliklari(web_client) -> None:
    basliklar = web_client.get("/").headers
    assert basliklar["X-Content-Type-Options"] == "nosniff"
    assert basliklar["Referrer-Policy"] == "no-referrer"
    assert basliklar["Cache-Control"] == "no-store"


def test_kule_frame_origin_gecerli_acilir(monkeypatch: pytest.MonkeyPatch, web_client) -> None:
    monkeypatch.setenv("KULE_FRAME_ORIGIN", "http://127.0.0.1:8790")
    csp = web_client.get("/").headers["Content-Security-Policy"]
    assert "frame-ancestors http://127.0.0.1:8790" in csp
    assert "frame-ancestors 'none'" not in csp


def test_kule_frame_origin_gecersiz_acmaz(monkeypatch: pytest.MonkeyPatch, web_client) -> None:
    """KULE dışı origin CSP'yi BOSZMAZ: frame-ancestors 'none' kalir."""
    for kotu in ("http://evil.example", "https://127.0.0.1:8790", "http://127.0.0.1", "javascript:alert(1)"):
        monkeypatch.setenv("KULE_FRAME_ORIGIN", kotu)
        csp = web_client.get("/").headers["Content-Security-Policy"]
        assert "frame-ancestors 'none'" in csp, kotu


def test_sablonlarda_inline_script_yok() -> None:
    """CSP `script-src 'self'`: sablonda satir ici <script> OLMAMALI."""
    for sablon in (WEB_KOK / "sablonlar").glob("*.html"):
        icerik = sablon.read_text(encoding="utf-8")
        assert "<script>" not in icerik, sablon.name
        assert "style=" not in icerik, sablon.name


@pytest.mark.parametrize(
    "dosya",
    ["panel.js", "temel.html", "ana.html"],
)
def test_dom_api_kullanimi_yok(dosya: str) -> None:
    """DOM METIN olarak kurulur: HTML yazan API hicbir dosyada GECMEZ."""
    icerik = (WEB_KOK / ("static/" + dosya if dosya.endswith(".js") else "sablonlar/" + dosya)).read_text(
        encoding="utf-8"
    )
    for yasak in ("innerHTML", "insertAdjacentHTML", "document.write", "outerHTML"):
        assert yasak not in icerik, f"{dosya}: {yasak}"
