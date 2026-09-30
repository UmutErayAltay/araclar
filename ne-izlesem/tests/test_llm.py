"""`app/llm.py` testleri.

Gerçek cor'a GİDİLMEZ. İki düzeyde sahte kullanılır:
  * `_post_once` monkeypatch'lenerek retry/davranış mantığı sınanır
    (anlat'ın `test_narrator.py`'deki yaklaşımın aynısı).
  * `test_cor_client_against_fake_http_server` ise stdlib `http.server` ile
    kaldırılan sahte bir proxy'ye karşı GERÇEK soket üzerinden gider —
    istek gövdesi ve `/v1/messages` yolu mock'lanmadan sınanır.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

from app.llm import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    CorLLMClient,
    LLMClient,
    LLMError,
)


# --------------------------------------------------------------------- #
# Sahte HTTP sunucusu
# --------------------------------------------------------------------- #


class FakeCorHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args: Any) -> None:  # pytest çıktısını kirletmesin
        return

    def do_POST(self) -> None:  # noqa: N802 - stdlib arayüzü
        server: "FakeCorServer" = self.server  # type: ignore[assignment]
        length = int(self.headers.get("content-length") or 0)
        server.requests.append(
            {
                "path": self.path,
                "body": json.loads(self.rfile.read(length).decode("utf-8")),
            }
        )

        status, payload = server.responses[min(server.hits, len(server.responses) - 1)]
        server.hits += 1
        body = json.dumps(payload).encode("utf-8")

        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class FakeCorServer(ThreadingHTTPServer):
    """Sıralı yanıt listesi ve istek günlüğü tutan sahte cor proxy."""

    daemon_threads = True

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), FakeCorHandler)
        self.responses: list[tuple[int, Any]] = [(200, messages_response("tamam"))]
        self.requests: list[dict[str, Any]] = []
        self.hits = 0
        self._thread = threading.Thread(target=self.serve_forever, daemon=True)
        self._thread.start()

    @property
    def base_url(self) -> str:
        host, port = self.server_address[0], self.server_address[1]
        return f"http://{host}:{port}"

    def close(self) -> None:
        self.shutdown()
        self.server_close()
        self._thread.join(timeout=5)


@pytest.fixture
def fake_cor_server() -> FakeCorServer:
    server = FakeCorServer()
    try:
        yield server
    finally:
        server.close()


def messages_response(text: str) -> dict[str, Any]:
    """Anthropic uyumlu `/v1/messages` gövdesi."""
    return {"id": "msg_1", "type": "message", "content": [{"type": "text", "text": text}]}


# --------------------------------------------------------------------- #
# Yapılandırma
# --------------------------------------------------------------------- #


def test_defaults_match_contract() -> None:
    client = CorLLMClient()
    assert client.base_url == "http://127.0.0.1:8787"
    assert client.model == "stealth/space-bunny-alpha"
    assert DEFAULT_BASE_URL == "http://127.0.0.1:8787"
    assert DEFAULT_MODEL == "stealth/space-bunny-alpha"


def test_trailing_slash_is_stripped() -> None:
    assert CorLLMClient(base_url="http://127.0.0.1:8787/").base_url == "http://127.0.0.1:8787"


def test_client_satisfies_protocol() -> None:
    assert isinstance(CorLLMClient(), LLMClient)


# --------------------------------------------------------------------- #
# Sahte HTTP sunucusuna karşı
# --------------------------------------------------------------------- #


def test_cor_client_against_fake_http_server(fake_cor_server: FakeCorServer) -> None:
    fake_cor_server.responses = [(200, messages_response("merhaba dunya"))]
    client = CorLLMClient(base_url=fake_cor_server.base_url, timeout=10.0)

    assert client.complete("selam") == "merhaba dunya"

    request = fake_cor_server.requests[-1]
    assert request["path"] == "/v1/messages"
    assert request["body"]["model"] == DEFAULT_MODEL
    assert request["body"]["messages"] == [{"role": "user", "content": "selam"}]


def test_http_404_raises_without_retry(fake_cor_server: FakeCorServer) -> None:
    fake_cor_server.responses = [(404, {"error": "yok"})]
    client = CorLLMClient(base_url=fake_cor_server.base_url, timeout=10.0, retry_backoff=0.0)

    with pytest.raises(LLMError, match="HTTP 404"):
        client.complete("selam")
    assert fake_cor_server.hits == 1  # 4xx kalıcıdır, tekrar denenmez


def test_unexpected_body_shape_raises(fake_cor_server: FakeCorServer) -> None:
    fake_cor_server.responses = [(200, {"beklenmeyen": "biçim"})]
    client = CorLLMClient(base_url=fake_cor_server.base_url, timeout=10.0)

    with pytest.raises(LLMError, match="yanıt biçimi"):
        client.complete("selam")


def test_empty_text_raises_instead_of_faking(fake_cor_server: FakeCorServer) -> None:
    """HTTP 200 olsa bile boş metin başarısızlıktır — sahte yanıt dönmüyoruz."""
    fake_cor_server.responses = [(200, messages_response("   "))]
    client = CorLLMClient(base_url=fake_cor_server.base_url, timeout=10.0)

    with pytest.raises(LLMError, match="boş yanıt"):
        client.complete("selam")


def test_connection_refused_raises() -> None:
    client = CorLLMClient(base_url="http://127.0.0.1:9", timeout=5.0)

    with pytest.raises(LLMError, match="bağlanılamadı"):
        client.complete("selam")


# --------------------------------------------------------------------- #
# Retry — SADECE 5xx
# --------------------------------------------------------------------- #


def test_transient_5xx_is_retried_then_succeeds() -> None:
    client = CorLLMClient(retry_backoff=0.0)
    calls = {"n": 0}

    def fake_post(prompt: str) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            raise LLMError("cor proxy HTTP 502 döndü: upstream bos")
        return "tamam"

    client._post_once = fake_post  # type: ignore[method-assign]

    assert client.complete("prompt") == "tamam"
    assert calls["n"] == 2


def test_persistent_5xx_gives_up_after_max_retries() -> None:
    client = CorLLMClient(retry_backoff=0.0, max_retries=2)
    calls = {"n": 0}

    def fake_post(prompt: str) -> str:
        calls["n"] += 1
        raise LLMError("cor proxy HTTP 502 döndü: upstream bos")

    client._post_once = fake_post  # type: ignore[method-assign]

    with pytest.raises(LLMError, match="502"):
        client.complete("prompt")
    assert calls["n"] == 3  # ilk deneme + 2 tekrar


def test_connection_error_is_not_retried() -> None:
    """Bağlantı hatası kalıcıdır; yeniden denenmemeli."""
    client = CorLLMClient(retry_backoff=0.0)
    calls = {"n": 0}

    def fake_post(prompt: str) -> str:
        calls["n"] += 1
        raise LLMError("cor proxy'ye bağlanılamadı: refused")

    client._post_once = fake_post  # type: ignore[method-assign]

    with pytest.raises(LLMError, match="bağlanılamadı"):
        client.complete("prompt")
    assert calls["n"] == 1


def test_4xx_against_fake_server_is_not_retried(fake_cor_server: FakeCorServer) -> None:
    fake_cor_server.responses = [(429, {"error": "cok hizli"})]
    client = CorLLMClient(
        base_url=fake_cor_server.base_url, timeout=10.0, max_retries=2, retry_backoff=0.0
    )

    with pytest.raises(LLMError, match="HTTP 429"):
        client.complete("selam")
    assert fake_cor_server.hits == 1
