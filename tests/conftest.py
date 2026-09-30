"""Ortak sahte cor sunucusu (GERÇEK soket, `127.0.0.1`, boş port).

Gerçek cor'a GİDİLMEZ; `http.server` ile kaldırılan bir sahte proxy'ye gider.
Böylece istek YOLU, BAŞLIKLARI ve gövde mock'lanmadan sınanır.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Iterator

import pytest


def messages_response(text: str) -> dict[str, Any]:
    """Anthropic uyumlu `/v1/messages` gövdesi."""
    return {"id": "msg_1", "type": "message", "content": [{"type": "text", "text": text}]}


class FakeCorHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args: Any) -> None:  # pytest çıktısını kirletmesin
        return

    def do_POST(self) -> None:  # noqa: N802 — stdlib arayüzü
        server: "FakeCorServer" = self.server  # type: ignore[assignment]
        uzunluk = int(self.headers.get("content-length") or 0)
        ham = self.rfile.read(uzunluk)
        try:
            govde: Any = json.loads(ham.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            govde = {"_ham": ham.decode("utf-8", errors="replace")}
        server.requests.append(
            {
                "path": self.path,
                "method": self.command,
                "content_type": self.headers.get("content-type"),
                "body": govde,
            }
        )

        kod, payload = server.responses[min(server.hits, len(server.responses) - 1)]
        server.hits += 1
        veri = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")

        self.send_response(kod)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(veri)))
        self.end_headers()
        self.wfile.write(veri)


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


def pytest_configure(config: Any) -> None:
    config.addinivalue_line("markers", "sadece_yerel: yalnız 127.0.0.1 sahte sunucu kullanır")


@pytest.fixture
def sahte_cor() -> Iterator[FakeCorServer]:
    server = FakeCorServer()
    try:
        yield server
    finally:
        server.close()
