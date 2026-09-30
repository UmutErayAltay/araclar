"""`narrator.CorLLMClient`: ortak istemci (`_corclient`) üzerinden, GERÇEK yerel soketle.

Mevcut birim testleri `_post_once`'u taklit ettiği için `LLMError -> NarratorError`
dönüşümünü (ve gövdedeki 8000 token / model değerini) yalnız kapalı duran entegrasyon
testleri görebiliyordu. Bunlar 127.0.0.1'deki sahte cor'a gider; gerçek ağ YOK.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from generator import narrator
from generator.narrator import CorLLMClient, NarratorError

OK = {"content": [{"type": "text", "text": "merhaba"}]}


@pytest.fixture
def sahte_cor():
    sunucular: list[ThreadingHTTPServer] = []

    def kur(yanitlar):
        durum = {"n": 0, "istekler": []}

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):  # noqa: D401
                return

            def do_POST(self):  # noqa: N802
                uzunluk = int(self.headers.get("content-length") or 0)
                durum["istekler"].append((self.path, json.loads(self.rfile.read(uzunluk))))
                kod, veri = yanitlar[min(durum["n"], len(yanitlar) - 1)]
                durum["n"] += 1
                govde = veri if isinstance(veri, bytes) else json.dumps(veri).encode()
                self.send_response(kod)
                self.send_header("content-length", str(len(govde)))
                self.end_headers()
                self.wfile.write(govde)

        sv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=sv.serve_forever, daemon=True).start()
        sunucular.append(sv)
        return f"http://127.0.0.1:{sv.server_address[1]}", durum

    yield kur
    for sv in sunucular:
        sv.shutdown()
        sv.server_close()


def _istemci(url: str, **kw) -> CorLLMClient:
    return CorLLMClient(base_url=url, retry_backoff=0.0, **kw)


def test_basari_govde_ve_yol(sahte_cor) -> None:
    url, d = sahte_cor([(200, OK)])
    assert _istemci(url, model="kurgusal/model").complete("selam") == "merhaba"
    yol, govde = d["istekler"][0]
    assert yol == "/v1/messages"
    assert govde["model"] == "kurgusal/model"
    assert govde["max_tokens"] == 8000 == narrator.MAX_TOKENS
    assert govde["messages"] == [{"role": "user", "content": "selam"}]


def test_http_hatasi_narrator_error_ve_tekrar_denenmez(sahte_cor) -> None:
    url, d = sahte_cor([(404, {"e": "yok"})])
    with pytest.raises(NarratorError, match="HTTP 404"):
        _istemci(url).complete("x")
    assert d["n"] == 1


def test_5xx_tekrar_denenir_ve_sonunda_narrator_error(sahte_cor) -> None:
    url, d = sahte_cor([(502, {"e": 1})])
    with pytest.raises(NarratorError, match="HTTP 502"):
        _istemci(url, max_retries=2).complete("x")
    assert d["n"] == 3


def test_5xx_sonra_basari(sahte_cor) -> None:
    url, d = sahte_cor([(503, {"e": 1}), (200, OK)])
    assert _istemci(url).complete("x") == "merhaba"
    assert d["n"] == 2


@pytest.mark.parametrize(
    "yanit, parca",
    [
        ((200, {"content": [{"type": "text", "text": "   "}]}), "boş yanıt"),
        ((200, b"<html>"), "yanıt biçimi"),
        ((200, {"x": 1}), "yanıt biçimi"),
    ],
)
def test_bozuk_yanitlar_narrator_error(sahte_cor, yanit, parca) -> None:
    url, d = sahte_cor([yanit])
    with pytest.raises(NarratorError, match=parca):
        _istemci(url).complete("x")
    assert d["n"] == 1


def test_kapali_port_narrator_error_ve_cor_claude_ipucu() -> None:
    with pytest.raises(NarratorError, match="bağlanılamadı") as h:
        CorLLMClient(base_url="http://127.0.0.1:9", timeout=3.0, max_retries=0).complete("x")
    assert "cor claude" in str(h.value)


def test_narrator_error_ortak_llm_error_alt_sinifi() -> None:
    from generator._corclient import LLMError

    assert issubclass(NarratorError, LLMError)
    assert isinstance(CorLLMClient(), narrator.LLMClient)


def test_varsayilanlar_korundu() -> None:
    c = CorLLMClient()
    assert (c.model, c.timeout, c.max_retries, c.retry_backoff) == (narrator.DEFAULT_MODEL, 300.0, 3, 3.0)
    assert c.izinli_konaklar == narrator.IZINLI_KONAKLAR  # loopback dışı adresler reddedilir


@pytest.mark.parametrize(
    "adres", ["http://ornek.com:8787", "http://192.168.1.10:8787", "http://0.0.0.0:8787", "https://api.ornek.com"]
)
def test_loopback_disi_adres_narrator_error_ile_reddedilir(adres: str) -> None:
    """Kurulumda reddedilir ve hata `NarratorError`'dır (CLI `except NarratorError` ile yakalar)."""
    with pytest.raises(NarratorError, match="loopback"):
        CorLLMClient(base_url=adres)


def test_gecersiz_sema_narrator_error() -> None:
    with pytest.raises(NarratorError):
        CorLLMClient(base_url="ftp://127.0.0.1:8787")


@pytest.mark.parametrize(
    "adres", ["http://127.0.0.1:8787", "http://localhost:8787", "http://[::1]:8787", "http://LOCALHOST:8787"]
)
def test_loopback_adresler_kabul(adres: str) -> None:
    assert CorLLMClient(base_url=adres).base_url == adres
