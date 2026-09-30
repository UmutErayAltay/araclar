"""`GET /api/search` ve `GET /api/items/{id}/watch` route testleri.

Gerçek ağa gidilmez: `get_tmdb_client` / `get_openlibrary_client`
bağımlılıkları sahte istemcilerle override edilir. `TMDB_API_KEY` yokken
503 alınması istenen testlerde bağımlılık override KALDIRILIR ve ortam
değişkeni `monkeypatch` ile silinir — böylece gerçek anahtar yolu sınanır.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.external.openlibrary import OpenLibraryError
from app.external.tmdb import TMDBError
from app.routes.items import get_tmdb_client
from app.routes.search import get_openlibrary_client


class FakeTMDB:
    """Gerçek ağa gitmeden `TMDBClient` arayüzünü taklit eder."""

    def __init__(self, results=None, providers=None, error: Exception | None = None) -> None:
        self.results = results if results is not None else []
        self.providers = providers if providers is not None else []
        self.error = error
        self.calls: list[tuple] = []

    def search(self, query: str, media_type: str) -> list[dict[str, Any]]:
        self.calls.append((query, media_type))
        if self.error:
            raise self.error
        return self.results

    def watch_providers(self, media_type: str, tmdb_id: str, region: str) -> list[dict[str, Any]]:
        self.calls.append((media_type, tmdb_id, region))
        if self.error:
            raise self.error
        return self.providers


class FakeOpenLibrary:
    def __init__(self, results=None, error: Exception | None = None) -> None:
        self.results = results if results is not None else []
        self.error = error
        self.calls: list[tuple] = []

    def search(self, query: str) -> list[dict[str, Any]]:
        self.calls.append((query,))
        if self.error:
            raise self.error
        return self.results


@pytest.fixture
def fake_tmdb_client():
    """Sahte TMDB'yi bağımlılığa takar; test içinde `override` ile erişilir."""

    def _install(fake: FakeTMDB) -> FakeTMDB:
        from app.main import app

        app.dependency_overrides[get_tmdb_client] = lambda: fake
        return fake

    return _install


@pytest.fixture
def without_tmdb_key(monkeypatch):
    """`TMDB_API_KEY` yokken bağımlılık override'ı olmayan durumu kurar."""
    from app.main import app

    monkeypatch.delenv("TMDB_API_KEY", raising=False)
    app.dependency_overrides.pop(get_tmdb_client, None)


# --------------------------------------------------------------------- #
# GET /api/search
# --------------------------------------------------------------------- #


def test_search_film_uses_tmdb_movie(client, fake_tmdb_client) -> None:
    results = [
        {
            "title": "Dune",
            "year": 2021,
            "poster_url": "https://image.tmdb.org/t/p/w342/a.jpg",
            "external_id": "438631",
            "overview": "özet",
        }
    ]
    fake = fake_tmdb_client(FakeTMDB(results=results))

    res = client.get("/api/search", params={"kind": "film", "q": "dune"})

    assert res.status_code == 200
    assert res.json() == {"results": [{**results[0], "external_source": "tmdb"}]}
    assert fake.calls == [("dune", "movie")]


def test_search_dizi_uses_tmdb_tv(client, fake_tmdb_client) -> None:
    fake = fake_tmdb_client(FakeTMDB())

    res = client.get("/api/search", params={"kind": "dizi", "q": "arcane"})

    assert res.status_code == 200
    assert fake.calls == [("arcane", "tv")]


def test_search_results_are_tagged_with_external_source(client, fake_tmdb_client) -> None:
    """Frontend `external_source`'u sonuçtan okuyup POST/PATCH'e taşıyor —
    eksik olursa `Item.external_source` hep null kalır ve /watch hep 404 verir."""
    from app.main import app

    fake_tmdb_client(FakeTMDB(results=[{"title": "Dune", "year": 2021,
                                         "poster_url": None, "external_id": "438631",
                                         "overview": None}]))
    res_film = client.get("/api/search", params={"kind": "film", "q": "dune"})
    assert res_film.json()["results"][0]["external_source"] == "tmdb"

    fake_ol = FakeOpenLibrary(results=[{"title": "Dune", "author": None, "year": None,
                                        "poster_url": None, "external_id": "/works/OL1W"}])
    app.dependency_overrides[get_openlibrary_client] = lambda: fake_ol
    res_kitap = client.get("/api/search", params={"kind": "kitap", "q": "dune"})
    assert res_kitap.json()["results"][0]["external_source"] == "openlibrary"


def test_search_anime_uses_tmdb_movie(client, fake_tmdb_client) -> None:
    """Sözleşmeye göre `anime` de `media_type="movie"`."""
    fake = fake_tmdb_client(FakeTMDB())

    client.get("/api/search", params={"kind": "anime", "q": " cowboy bebop"})

    assert fake.calls == [("cowboy bebop", "movie")]


def test_search_kitap_uses_openlibrary(client, fake_tmdb_client) -> None:
    from app.main import app

    results = [
        {
            "title": "Dune",
            "author": "Frank Herbert",
            "year": 1965,
            "poster_url": "https://covers.openlibrary.org/b/id/1-M.jpg",
            "external_id": "/works/OL12345W",
        }
    ]
    fake_ol = FakeOpenLibrary(results=results)
    app.dependency_overrides[get_openlibrary_client] = lambda: fake_ol

    res = client.get("/api/search", params={"kind": "kitap", "q": "dune"})

    assert res.status_code == 200
    assert res.json() == {"results": [{**results[0], "external_source": "openlibrary"}]}
    assert fake_ol.calls == [("dune",)]


def test_search_kitap_ignores_query_whitespace(client) -> None:
    from app.main import app

    fake_ol = FakeOpenLibrary()
    app.dependency_overrides[get_openlibrary_client] = lambda: fake_ol

    client.get("/api/search", params={"kind": "kitap", "q": "  dune  "})

    assert fake_ol.calls == [("dune",)]


def test_search_missing_kind_422(client) -> None:
    res = client.get("/api/search", params={"q": "dune"})
    assert res.status_code == 422


def test_search_invalid_kind_422(client) -> None:
    res = client.get("/api/search", params={"kind": "belgesel", "q": "dune"})
    assert res.status_code == 422
    assert "kind" in res.json()["detail"]


def test_search_missing_q_422(client) -> None:
    res = client.get("/api/search", params={"kind": "film"})
    assert res.status_code == 422


def test_search_blank_q_422(client) -> None:
    res = client.get("/api/search", params={"kind": "film", "q": "   "})
    assert res.status_code == 422
    assert "q boş olamaz" in res.json()["detail"]


def test_search_without_tmdb_key_503(client, without_tmdb_key) -> None:
    res = client.get("/api/search", params={"kind": "film", "q": "dune"})

    assert res.status_code == 503
    assert res.json()["detail"] == "TMDB_API_KEY ayarlanmamış"


def test_search_kitap_works_without_tmdb_key(client, without_tmdb_key) -> None:
    """Kitap araması TMDB'ye gitmediği için anahtar olmadan da çalışmalı."""
    from app.main import app

    fake_ol = FakeOpenLibrary(results=[{"title": "Dune", "external_id": "/works/OL1W"}])
    app.dependency_overrides[get_openlibrary_client] = lambda: fake_ol

    res = client.get("/api/search", params={"kind": "kitap", "q": "dune"})

    assert res.status_code == 200
    assert res.json()["results"][0]["title"] == "Dune"


def test_search_tmdb_error_502(client, fake_tmdb_client) -> None:
    """Dış servis hatası 502 olur — boş/sahte sonuç dönülmez."""
    fake_tmdb_client(FakeTMDB(error=TMDBError("TMDB /search/movie için HTTP 500 döndü")))

    res = client.get("/api/search", params={"kind": "film", "q": "dune"})

    assert res.status_code == 502


def test_search_openlibrary_error_502(client) -> None:
    from app.main import app

    app.dependency_overrides[get_openlibrary_client] = lambda: FakeOpenLibrary(
        error=OpenLibraryError("Open Library /search.json için HTTP 500 döndü")
    )

    res = client.get("/api/search", params={"kind": "kitap", "q": "dune"})

    assert res.status_code == 502


def test_search_empty_result_is_200_with_empty_list(client, fake_tmdb_client) -> None:
    """Gerçekten sonuç yoksa 200 + boş liste (hata değil, uydurma değil)."""
    fake_tmdb_client(FakeTMDB(results=[]))

    res = client.get("/api/search", params={"kind": "film", "q": "zzzz"})

    assert res.status_code == 200
    assert res.json() == {"results": []}


# --------------------------------------------------------------------- #
# GET /api/items/{id}/watch
# --------------------------------------------------------------------- #


PROVIDERS = [
    {
        "provider_name": "Netflix",
        "logo_url": "https://image.tmdb.org/t/p/w92/n.jpg",
        "link": "https://www.themoviedb.org/movie/1/watch?locale=TR",
    }
]


def _create_linked_item(client, kind="film", external_id="438631", source="tmdb") -> dict:
    res = client.post(
        "/api/items",
        json={
            "title": "Dune",
            "kind": kind,
            "poster_url": "https://image.tmdb.org/t/p/w342/a.jpg",
            "external_source": source,
            "external_id": external_id,
        },
    )
    assert res.status_code == 201
    return res.json()


def test_watch_success(client, fake_tmdb_client) -> None:
    item = _create_linked_item(client)
    fake = fake_tmdb_client(FakeTMDB(providers=PROVIDERS))

    res = client.get(f"/api/items/{item['id']}/watch")

    assert res.status_code == 200
    assert res.json() == {"providers": PROVIDERS}
    assert fake.calls == [("movie", "438631", "TR")]


def test_watch_uses_default_region_tr(client, fake_tmdb_client) -> None:
    item = _create_linked_item(client)
    fake = fake_tmdb_client(FakeTMDB())

    client.get(f"/api/items/{item['id']}/watch")

    assert fake.calls[-1][2] == "TR"


def test_watch_respects_region_query_param(client, fake_tmdb_client) -> None:
    item = _create_linked_item(client)
    fake = fake_tmdb_client(FakeTMDB())

    res = client.get(f"/api/items/{item['id']}/watch", params={"region": "US"})

    assert res.status_code == 200
    assert fake.calls[-1][2] == "US"


def test_watch_respects_region_env(client, fake_tmdb_client, monkeypatch) -> None:
    item = _create_linked_item(client)
    fake = fake_tmdb_client(FakeTMDB())
    monkeypatch.setenv("WATCH_REGION", "DE")

    client.get(f"/api/items/{item['id']}/watch")

    assert fake.calls[-1][2] == "DE"


def test_watch_dizi_uses_tv_media_type(client, fake_tmdb_client) -> None:
    item = _create_linked_item(client, kind="dizi", external_id="94605")
    fake = fake_tmdb_client(FakeTMDB())

    client.get(f"/api/items/{item['id']}/watch")

    assert fake.calls[-1][0] == "tv"


def test_watch_kitap_404(client, fake_tmdb_client) -> None:
    """Kitaba 'nerede izlerim' anlamsız — sessiz boş liste değil, 404."""
    item = _create_linked_item(client, kind="kitap", source="openlibrary")
    fake = fake_tmdb_client(FakeTMDB())

    res = client.get(f"/api/items/{item['id']}/watch")

    assert res.status_code == 404
    assert "anlamsız" in res.json()["detail"]
    assert fake.calls == []


def test_watch_missing_external_id_404(client, fake_tmdb_client) -> None:
    created = client.post("/api/items", json={"title": "Dune", "kind": "film"}).json()
    fake = fake_tmdb_client(FakeTMDB())

    res = client.get(f"/api/items/{created['id']}/watch")

    assert res.status_code == 404
    assert "dış kaynağa bağlı değil" in res.json()["detail"]
    assert fake.calls == []


def test_watch_missing_external_source_404(client, fake_tmdb_client) -> None:
    created = client.post(
        "/api/items",
        json={"title": "Dune", "kind": "film", "external_id": "438631"},
    ).json()
    fake = fake_tmdb_client(FakeTMDB())

    res = client.get(f"/api/items/{created['id']}/watch")

    assert res.status_code == 404
    assert fake.calls == []


def test_watch_item_missing_404(client, fake_tmdb_client) -> None:
    fake_tmdb_client(FakeTMDB())
    assert client.get("/api/items/999/watch").status_code == 404


def test_watch_without_tmdb_key_503(client, without_tmdb_key) -> None:
    item = _create_linked_item(client)

    res = client.get(f"/api/items/{item['id']}/watch")

    assert res.status_code == 503
    assert res.json()["detail"] == "TMDB_API_KEY ayarlanmamış"


def test_watch_tmdb_error_502(client, fake_tmdb_client) -> None:
    item = _create_linked_item(client)
    fake_tmdb_client(FakeTMDB(error=TMDBError("TMDB watch/providers için HTTP 500 döndü")))

    res = client.get(f"/api/items/{item['id']}/watch")

    assert res.status_code == 502


def test_watch_no_providers_is_empty_list(client, fake_tmdb_client) -> None:
    """Bölgede abonelik yoksa 200 + boş liste (sözleşmede hata değil)."""
    item = _create_linked_item(client)
    fake_tmdb_client(FakeTMDB(providers=[]))

    res = client.get(f"/api/items/{item['id']}/watch")

    assert res.status_code == 200
    assert res.json() == {"providers": []}
