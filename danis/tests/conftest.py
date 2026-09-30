"""Paylaşılan test yardımcıları.

Felsefe (docs/API.md): mock YOK. cor testleri stdlib `http.server` ile
kaldırılan bir sahte proxy'ye GERÇEK soket üzerinden gider; dosya testleri
gerçek örnek dosyaları kullanır.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterator

import pytest

from danis.llm import CorLLMClient

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def messages_response(text: str) -> dict[str, Any]:
    """Anthropic uyumlu `/v1/messages` gövdesi."""
    return {"id": "msg_1", "type": "message", "content": [{"type": "text", "text": text}]}


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

    def __init__(self, responses: list[tuple[int, Any]] | None = None) -> None:
        super().__init__(("127.0.0.1", 0), FakeCorHandler)
        self.responses: list[tuple[int, Any]] = responses or [
            (200, messages_response("tamam"))
        ]
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
def fake_cor_server() -> Iterator[FakeCorServer]:
    server = FakeCorServer()
    try:
        yield server
    finally:
        server.close()


@pytest.fixture
def cli_cor(fake_cor_server: FakeCorServer, monkeypatch: pytest.MonkeyPatch) -> FakeCorServer:
    """CLI'nin kullandığı istemciyi sahte sunucuya yönlendirir.

    `danis.llm` ortam değişkenlerini import anında okur (ne-izlesem ile aynı
    desen), bu yüzden `monkeypatch.setenv` sonradan işe yaramaz; istemcinin
    KURUCUSUNU değiştirip base_url'i veriyoruz. İstek yine GERÇEK soketten
    geçer — mock değil.
    """
    from danis import cli

    def _kurucu(**kwargs: Any) -> CorLLMClient:
        kwargs.setdefault("base_url", fake_cor_server.base_url)
        kwargs.setdefault("timeout", 10.0)
        return CorLLMClient(**kwargs)

    monkeypatch.setattr(cli, "CorLLMClient", _kurucu)
    return fake_cor_server
