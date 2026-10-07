"""`danis/llm.py` testleri.

Gerçek cor'a GİDİLMEZ. İki düzeyde sahte kullanılır:
  * `_post_once` değiştirilerek retry/davranış mantığı sınanır
    (ne-izlesem/tests/test_llm.py ile aynı yaklaşım).
  * `fake_cor_server` ise stdlib `http.server` ile kaldırılan sahte proxy'ye
    karşı GERÇEK soket üzerinden gider — istek gövdesi ve `/v1/messages`
    yolu mock'lanmadan sınanır.
"""

from __future__ import annotations

import pytest

from conftest import FakeCorServer, messages_response
from danis.llm import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    CorLLMClient,
    LLMClient,
    LLMError,
)


# --------------------------------------------------------------------- #
# Yapılandırma
# --------------------------------------------------------------------- #


def test_defaults_match_contract() -> None:
    client = CorLLMClient()
    assert client.base_url == "http://127.0.0.1:8787"
    assert client.model == "nvidia/nemotron-3-ultra-550b-a55b:free"
    assert DEFAULT_BASE_URL == "http://127.0.0.1:8787"
    assert DEFAULT_MODEL == "nvidia/nemotron-3-ultra-550b-a55b:free"


def test_trailing_slash_is_stripped() -> None:
    assert CorLLMClient(base_url="http://127.0.0.1:8787/").base_url == "http://127.0.0.1:8787"


def test_client_satisfies_protocol() -> None:
    assert isinstance(CorLLMClient(), LLMClient)


# --------------------------------------------------------------------- #
# Sahte HTTP sunucusuna karşı (GERÇEK soket)
# --------------------------------------------------------------------- #


def test_client_against_fake_http_server(fake_cor_server: FakeCorServer) -> None:
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


def test_real_5xx_is_retried_against_fake_server() -> None:
    """Retry gerçekten HTTP üzerinden de devreye giriyor (mock'suz)."""
    fake_cor_server = FakeCorServer(
        responses=[(503, {"error": "yok"}), (200, messages_response("ok oldu"))]
    )
    try:
        client = CorLLMClient(
            base_url=fake_cor_server.base_url, timeout=10.0, retry_backoff=0.0
        )
        assert client.complete("selam") == "ok oldu"
        assert fake_cor_server.hits == 2
    finally:
        fake_cor_server.close()


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
