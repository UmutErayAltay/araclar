"""app/external/openlibrary.py testleri.

Gerçek Open Library ağına gidilMEZ; stdlib `http.server` ile gerçek bir soket
üzerinde çalışan sahte bir sunucu kullanılır (anlat'ın bridge/client.py test
deseni).
"""

from __future__ import annotations

import json
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

from app.external.openlibrary import (
    DEFAULT_BASE_URL,
    OpenLibraryClient,
    OpenLibraryError,
)


class FakeOpenLibraryHandler(BaseHTTPRequestHandler):
    """Sahte Open Library: kaydettiği istekleri testlere açar."""

    protocol_version = "HTTP/1.1"

    def log_message(self, *args: Any) -> None:  # pytest çıktısını kirletmesin
        return

    @property
    def fake(self) -> "FakeOpenLibraryServer":
        return self.server  # type: ignore[no-any-return]

    def do_GET(self) -> None:  # noqa: N802 - stdlib arayüzü
        parsed = urllib.parse.urlparse(self.path)
        query = dict(urllib.parse.parse_qsl(parsed.query))
        self.fake.requests.append({"path": parsed.path, "query": query})

        body = self.fake.bodies.get(parsed.path, b"")
        if isinstance(body, bytes):
            status = 200
            content_type = self.fake.content_type
        else:
            status, body = body
            content_type = "application/json"

        self.send_response(status)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class FakeOpenLibraryServer(ThreadingHTTPServer):
    """Gövde tablosu ve istek günlüğü tutan sahte Open Library sunucusu."""

    daemon_threads = True

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), FakeOpenLibraryHandler)
        self.bodies: dict[str, Any] = {}
        self.requests: list[dict[str, Any]] = []
        self.content_type = "application/json"
        self._thread = threading.Thread(target=self.serve_forever, daemon=True)
        self._thread.start()

    @property
    def base_url(self) -> str:
        host, port = self.server_address[0], self.server_address[1]
        return f"http://{host}:{port}"

    def json_body(self, path: str, payload: dict[str, Any]) -> None:
        self.bodies[path] = json.dumps(payload).encode("utf-8")

    def raw_body(self, path: str, body: bytes, content_type: str = "text/html") -> None:
        self.bodies[path] = body
        self.content_type = content_type

    def error_body(self, path: str, status: int, payload: dict[str, Any]) -> None:
        self.bodies[path] = (status, json.dumps(payload).encode("utf-8"))

    def close(self) -> None:
        self.shutdown()
        self.server_close()
        self._thread.join(timeout=5)


@pytest.fixture
def fake_ol() -> FakeOpenLibraryServer:
    server = FakeOpenLibraryServer()
    try:
        yield server
    finally:
        server.close()


def client_for(server: FakeOpenLibraryServer) -> OpenLibraryClient:
    return OpenLibraryClient(base_url=server.base_url, timeout=10.0)


def book_payload(**overrides: Any) -> dict[str, Any]:
    doc = {
        "key": "/works/OL12345W",
        "title": "Dune",
        "author_name": ["Frank Herbert"],
        "first_publish_year": 1965,
        "cover_i": 8231856,
    }
    doc.update(overrides)
    return {"docs": [doc]}


# --------------------------------------------------------------------- #
# Kurucu
# --------------------------------------------------------------------- #


def test_no_api_key_required() -> None:
    """Open Library anahtar gerektirmez — kurucu anahtarsız çalışmalı."""
    assert OpenLibraryClient().base_url == DEFAULT_BASE_URL
    assert DEFAULT_BASE_URL == "https://openlibrary.org"


# --------------------------------------------------------------------- #
# search
# --------------------------------------------------------------------- #


def test_search_maps_result_and_builds_cover_url(fake_ol: FakeOpenLibraryServer) -> None:
    fake_ol.json_body("/search.json", book_payload())
    client = client_for(fake_ol)

    results = client.search("dune")

    assert results == [
        {
            "title": "Dune",
            "author": "Frank Herbert",
            "year": 1965,
            "poster_url": "https://covers.openlibrary.org/b/id/8231856-M.jpg",
            "external_id": "/works/OL12345W",
        }
    ]


def test_search_sends_q(fake_ol: FakeOpenLibraryServer) -> None:
    fake_ol.json_body("/search.json", book_payload())
    client_for(fake_ol).search("dune")

    request = fake_ol.requests[-1]
    assert request["path"] == "/search.json"
    assert request["query"]["q"] == "dune"


def test_search_without_cover_gives_null_poster_url(fake_ol: FakeOpenLibraryServer) -> None:
    """`cover_i` yoksa kapak URL'i uydurulmamalı."""
    payload = book_payload()
    del payload["docs"][0]["cover_i"]
    fake_ol.json_body("/search.json", payload)

    results = client_for(fake_ol).search("dune")

    assert results[0]["poster_url"] is None
    assert results[0]["title"] == "Dune"


def test_search_without_author_gives_null(fake_ol: FakeOpenLibraryServer) -> None:
    fake_ol.json_body("/search.json", book_payload(author_name=[]))
    assert client_for(fake_ol).search("dune")[0]["author"] is None


def test_search_empty_results_returns_empty_list(fake_ol: FakeOpenLibraryServer) -> None:
    fake_ol.json_body("/search.json", {"docs": [], "numFound": 0})
    assert client_for(fake_ol).search("bulunamayan") == []


def test_search_http_404_raises(fake_ol: FakeOpenLibraryServer) -> None:
    fake_ol.error_body("/search.json", 404, {"error": "not found"})

    with pytest.raises(OpenLibraryError, match="HTTP 404"):
        client_for(fake_ol).search("dune")


def test_search_broken_json_raises(fake_ol: FakeOpenLibraryServer) -> None:
    fake_ol.raw_body("/search.json", b"<html>not json</html>")

    with pytest.raises(OpenLibraryError, match="yanıt biçimi"):
        client_for(fake_ol).search("dune")


def test_search_connection_refused_raises() -> None:
    client = OpenLibraryClient(base_url="http://127.0.0.1:9", timeout=5.0)

    with pytest.raises(OpenLibraryError):
        client.search("dune")


def test_search_blank_query_raises() -> None:
    with pytest.raises(OpenLibraryError, match="boş olamaz"):
        OpenLibraryClient().search("   ")
