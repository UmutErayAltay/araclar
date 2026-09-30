"""app/external/tmdb.py testleri.

Gerçek TMDB ağına gidilMEZ; Python stdlib'in `http.server`'ı ile gerçek bir
soket üzerinde çalışan sahte bir TMDB sunucusu kaldırılır (anlat'ın
bridge/client.py test deseni). Böylece istek/cevap ayrımı ve hata yolu
mock'lanmadan localhost üzerinden sınanır.
"""

from __future__ import annotations

import json
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

from app.external.tmdb import (
    DEFAULT_BASE_URL,
    TMDBClient,
    TMDBError,
    TMDBNotConfiguredError,
)

API_KEY = "test-key"


class FakeTMDBHandler(BaseHTTPRequestHandler):
    """Sahte TMDB: kaydettiği istekleri testlere açar."""

    protocol_version = "HTTP/1.1"

    def log_message(self, *args: Any) -> None:  # pytest çıktısını kirletmesin
        return

    @property
    def fake(self) -> "FakeTMDBServer":
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


class FakeTMDBServer(ThreadingHTTPServer):
    """Gövde tablosu ve istek günlüğü tutan sahte TMDB sunucusu."""

    daemon_threads = True

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), FakeTMDBHandler)
        # path -> bytes (200) ya da (status, bytes) çifti (hata senaryoları)
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
def fake_tmdb() -> FakeTMDBServer:
    server = FakeTMDBServer()
    try:
        yield server
    finally:
        server.close()


def client_for(server: FakeTMDBServer) -> TMDBClient:
    return TMDBClient(api_key=API_KEY, base_url=server.base_url, timeout=10.0)


def movie_payload(**overrides: Any) -> dict[str, Any]:
    entry = {
        "id": 438631,
        "title": "Dune",
        "release_date": "2021-10-22",
        "poster_path": "/d5NXSklXo0qyIYkgV94XAgMIckC.jpg",
        "overview": "Bir çöl gezegeninde iktidar savaşı.",
    }
    entry.update(overrides)
    return {"results": [entry]}


# --------------------------------------------------------------------- #
# Kurucu
# --------------------------------------------------------------------- #


def test_missing_api_key_raises_not_configured() -> None:
    """Anahtarsız istemci sessizce sahte sonuç dönmemeli."""
    with pytest.raises(TMDBNotConfiguredError):
        TMDBClient(api_key="")
    with pytest.raises(TMDBNotConfiguredError):
        TMDBClient(api_key="   ")
    with pytest.raises(TMDBNotConfiguredError):
        TMDBClient()


def test_not_configured_is_a_tmdb_error() -> None:
    assert issubclass(TMDBNotConfiguredError, TMDBError)


def test_default_base_url() -> None:
    assert DEFAULT_BASE_URL == "https://api.themoviedb.org/3"
    assert TMDBClient(api_key=API_KEY).base_url == "https://api.themoviedb.org/3"


# --------------------------------------------------------------------- #
# search
# --------------------------------------------------------------------- #


def test_search_movie_maps_result_and_builds_poster_url(fake_tmdb: FakeTMDBServer) -> None:
    fake_tmdb.json_body("/search/movie", movie_payload())
    tmdb = client_for(fake_tmdb)

    results = tmdb.search("dune", "movie")

    assert results == [
        {
            "title": "Dune",
            "year": 2021,
            "poster_url": "https://image.tmdb.org/t/p/w342/d5NXSklXo0qyIYkgV94XAgMIckC.jpg",
            "external_id": "438631",
            "overview": "Bir çöl gezegeninde iktidar savaşı.",
        }
    ]


def test_search_sends_api_key_and_query(fake_tmdb: FakeTMDBServer) -> None:
    fake_tmdb.json_body("/search/movie", movie_payload())
    client_for(fake_tmdb).search("dune", "movie")

    request = fake_tmdb.requests[-1]
    assert request["path"] == "/search/movie"
    assert request["query"]["query"] == "dune"
    assert request["query"]["api_key"] == API_KEY


def test_search_tv_uses_name_and_first_air_date(fake_tmdb: FakeTMDBServer) -> None:
    fake_tmdb.json_body(
        "/search/tv",
        {
            "results": [
                {
                    "id": 94605,
                    "name": "Arcane",
                    "first_air_date": "2021-11-06",
                    "poster_path": "/fqldf2t8ztc9aiwn3k6mlX3tvRT.jpg",
                    "overview": "İki kız kardeş.",
                }
            ]
        },
    )

    results = client_for(fake_tmdb).search("arcane", "tv")

    assert fake_tmdb.requests[-1]["path"] == "/search/tv"
    assert results[0]["title"] == "Arcane"
    assert results[0]["year"] == 2021
    assert results[0]["external_id"] == "94605"


def test_search_null_poster_path_gives_null_poster_url(fake_tmdb: FakeTMDBServer) -> None:
    """`poster_path` null ise uydurma kapak URL'i kurulmamalı."""
    fake_tmdb.json_body("/search/movie", movie_payload(poster_path=None))
    results = client_for(fake_tmdb).search("dune", "movie")

    assert results[0]["poster_url"] is None
    assert results[0]["title"] == "Dune"  # diğer alanlar etkilenmez


def test_search_empty_results_returns_empty_list(fake_tmdb: FakeTMDBServer) -> None:
    fake_tmdb.json_body("/search/movie", {"results": [], "total_results": 0})
    assert client_for(fake_tmdb).search("bulunamayan", "movie") == []


def test_search_http_404_raises(fake_tmdb: FakeTMDBServer) -> None:
    fake_tmdb.error_body("/search/movie", 404, {"status_message": "not found"})

    with pytest.raises(TMDBError, match="HTTP 404"):
        client_for(fake_tmdb).search("dune", "movie")


def test_search_broken_json_raises(fake_tmdb: FakeTMDBServer) -> None:
    fake_tmdb.raw_body("/search/movie", b"<html>not json</html>")

    with pytest.raises(TMDBError, match="yanıt biçimi"):
        client_for(fake_tmdb).search("dune", "movie")


def test_search_connection_refused_raises() -> None:
    tmdb = TMDBClient(api_key=API_KEY, base_url="http://127.0.0.1:9", timeout=5.0)

    with pytest.raises(TMDBError):
        tmdb.search("dune", "movie")


def test_search_blank_query_raises() -> None:
    with pytest.raises(TMDBError, match="boş olamaz"):
        TMDBClient(api_key=API_KEY).search("  ", "movie")


# --------------------------------------------------------------------- #
# discover
# --------------------------------------------------------------------- #


def test_discover_sends_genre_language_sort_and_page(fake_tmdb: FakeTMDBServer) -> None:
    fake_tmdb.json_body("/discover/movie", movie_payload())
    client_for(fake_tmdb).discover("movie", 878)

    request = fake_tmdb.requests[-1]
    assert request["path"] == "/discover/movie"
    assert request["query"]["with_genres"] == "878"
    assert request["query"]["language"] == "tr-TR"
    assert request["query"]["sort_by"] == "popularity.desc"
    assert request["query"]["page"] == "1"
    assert request["query"]["api_key"] == API_KEY


def test_discover_honours_page_argument(fake_tmdb: FakeTMDBServer) -> None:
    fake_tmdb.json_body("/discover/movie", movie_payload())
    client_for(fake_tmdb).discover("movie", 28, page=3)

    assert fake_tmdb.requests[-1]["query"]["page"] == "3"


def test_discover_maps_results_like_search(fake_tmdb: FakeTMDBServer) -> None:
    """Dönüş şekli `search()` ile birebir aynı olmalı."""
    fake_tmdb.json_body("/discover/movie", movie_payload())

    assert client_for(fake_tmdb).discover("movie", 878) == [
        {
            "title": "Dune",
            "year": 2021,
            "poster_url": "https://image.tmdb.org/t/p/w342/d5NXSklXo0qyIYkgV94XAgMIckC.jpg",
            "external_id": "438631",
            "overview": "Bir çöl gezegeninde iktidar savaşı.",
        }
    ]


def test_discover_tv_uses_name_and_first_air_date(fake_tmdb: FakeTMDBServer) -> None:
    fake_tmdb.json_body(
        "/discover/tv",
        {
            "results": [
                {
                    "id": 94605,
                    "name": "Arcane",
                    "first_air_date": "2021-11-06",
                    "poster_path": None,
                    "overview": "İki kız kardeş.",
                }
            ]
        },
    )

    results = client_for(fake_tmdb).discover("tv", 10765)

    assert fake_tmdb.requests[-1]["path"] == "/discover/tv"
    assert results == [
        {
            "title": "Arcane",
            "year": 2021,
            "poster_url": None,
            "external_id": "94605",
            "overview": "İki kız kardeş.",
        }
    ]


def test_discover_does_not_truncate_page(fake_tmdb: FakeTMDBServer) -> None:
    """Aday havuzu için kırpma YOK — TMDB'nin sayfa boyutu olduğu gibi döner."""
    fake_tmdb.json_body(
        "/discover/movie",
        {"results": [movie_payload(id=1000 + i)["results"][0] for i in range(20)]},
    )

    assert len(client_for(fake_tmdb).discover("movie", 18)) == 20


def test_discover_empty_results_returns_empty_list(fake_tmdb: FakeTMDBServer) -> None:
    fake_tmdb.json_body("/discover/movie", {"results": [], "total_results": 0})
    assert client_for(fake_tmdb).discover("movie", 18) == []


def test_discover_http_error_raises(fake_tmdb: FakeTMDBServer) -> None:
    fake_tmdb.error_body("/discover/movie", 500, {"status_message": "boom"})

    with pytest.raises(TMDBError, match="HTTP 500"):
        client_for(fake_tmdb).discover("movie", 18)


def test_discover_broken_json_raises(fake_tmdb: FakeTMDBServer) -> None:
    fake_tmdb.raw_body("/discover/movie", b"<html>not json</html>")

    with pytest.raises(TMDBError, match="yanıt biçimi"):
        client_for(fake_tmdb).discover("movie", 18)


# --------------------------------------------------------------------- #
# watch_providers
# --------------------------------------------------------------------- #

PROVIDERS_PATH = "/movie/438631/watch/providers"


def test_watch_providers_returns_flatrate_only(fake_tmdb: FakeTMDBServer) -> None:
    """`buy`/`rent` dahil edilmemeli — sadece abonelik (flatrate)."""
    fake_tmdb.json_body(
        PROVIDERS_PATH,
        {
            "id": 438631,
            "results": {
                "TR": {
                    "link": "https://www.themoviedb.org/movie/438631/watch?locale=TR",
                    "flatrate": [
                        {
                            "provider_id": 8,
                            "provider_name": "Netflix",
                            "logo_path": "/netflix.jpg",
                        }
                    ],
                    "rent": [{"provider_id": 2, "provider_name": "Apple TV", "logo_path": "/apple.jpg"}],
                    "buy": [{"provider_id": 2, "provider_name": "Apple TV", "logo_path": "/apple.jpg"}],
                }
            },
        },
    )

    providers = client_for(fake_tmdb).watch_providers("movie", "438631", "TR")

    assert providers == [
        {
            "provider_name": "Netflix",
            "logo_url": "https://image.tmdb.org/t/p/w92/netflix.jpg",
            "link": "https://www.themoviedb.org/movie/438631/watch?locale=TR",
        }
    ]
    assert all(p["provider_name"] != "Apple TV" for p in providers)


def test_watch_providers_missing_region_returns_empty_list(fake_tmdb: FakeTMDBServer) -> None:
    """Bölgede veri yoksa hata değil boş liste."""
    fake_tmdb.json_body(
        PROVIDERS_PATH,
        {"results": {"TR": {"flatrate": [{"provider_name": "Netflix"}]}}},
    )

    assert client_for(fake_tmdb).watch_providers("movie", "438631", "US") == []


def test_watch_providers_no_flatrate_key_returns_empty_list(fake_tmdb: FakeTMDBServer) -> None:
    """Sadece `buy`/`rent` olan bölge abonelik listesi sayılırsa boş dönmeli."""
    fake_tmdb.json_body(
        PROVIDERS_PATH,
        {
            "results": {
                "TR": {
                    "buy": [{"provider_name": "Apple TV"}],
                    "rent": [{"provider_name": "Google Play"}],
                }
            }
        },
    )

    assert client_for(fake_tmdb).watch_providers("movie", "438631", "TR") == []


def test_watch_providers_region_is_normalized(fake_tmdb: FakeTMDBServer) -> None:
    fake_tmdb.json_body(
        PROVIDERS_PATH, {"results": {"TR": {"flatrate": [{"provider_name": "Netflix"}]}}}
    )

    assert len(client_for(fake_tmdb).watch_providers("movie", "438631", "tr")) == 1


def test_watch_providers_http_error_raises(fake_tmdb: FakeTMDBServer) -> None:
    fake_tmdb.error_body(PROVIDERS_PATH, 500, {"status_message": "boom"})

    with pytest.raises(TMDBError, match="HTTP 500"):
        client_for(fake_tmdb).watch_providers("movie", "438631", "TR")


def test_watch_providers_broken_json_raises(fake_tmdb: FakeTMDBServer) -> None:
    fake_tmdb.raw_body(PROVIDERS_PATH, b"{{{")
    with pytest.raises(TMDBError, match="yanıt biçimi"):
        client_for(fake_tmdb).watch_providers("movie", "438631", "TR")
