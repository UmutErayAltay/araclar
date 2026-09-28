"""`GET /api/recommend` route testleri.

Ne gerçek TMDB'ye ne cor'a gidilmez: `get_tmdb_client` / `get_cor_client`
bağımlılıkları sahte istemcilerle override edilir. `TMDB_API_KEY` yokken 503
alınması istenen testte override KALDIRILIR ve ortam değişkeni silinir —
`tests/test_search_route.py` ile aynı desen.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.external.tmdb import TMDBError
from app.llm import LLMError
from app.routes.items import get_tmdb_client
from app.routes.recommend import get_cor_client

SUGGESTION = {
    "title": "Dune",
    "kind": "film",
    "reason": "Çöl gezegeninde iktidar savaşı.",
    "external_source": "tmdb",
    "external_id": "438631",
    "poster_url": "https://image.tmdb.org/t/p/w342/438631.jpg",
}

DUNE = {
    "title": "Dune",
    "year": 2021,
    "poster_url": "https://image.tmdb.org/t/p/w342/438631.jpg",
    "external_id": "438631",
    "overview": "Bir çöl gezegeninde iktidar savaşı.",
}


class FakeTMDB:
    def __init__(self, results=None, shows=None, error: Exception | None = None) -> None:
        self.results = results if results is not None else []
        self.shows = shows if shows is not None else []
        self.error = error
        self.calls: list[tuple[str, int]] = []

    def discover(self, media_type: str, genre_id: int, page: int = 1) -> list[dict[str, Any]]:
        self.calls.append((media_type, genre_id))
        if self.error:
            raise self.error
        return self.results if media_type == "movie" else self.shows


class FakeCor:
    def __init__(self, response: str = "[]", error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if self.error:
            raise self.error
        return self.response


def dune_pick() -> str:
    return json.dumps([{"title": "Dune", "reason": SUGGESTION["reason"]}], ensure_ascii=False)


class PartiallyFailingTMDB:
    """`movie` çalışır, `tv` patlar — kısmi başarısızlık senaryosu."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def discover(self, media_type: str, genre_id: int, page: int = 1) -> list[dict[str, Any]]:
        self.calls.append((media_type, genre_id))
        if media_type == "tv":
            raise TMDBError("TMDB /discover/tv için HTTP 500 döndü")
        return [DUNE]


@pytest.fixture
def fakes():
    """Sahte TMDB + sahte cor takar; test içinde ikisine de erişilir.

    `cor` parametresi özellikle `None` geçilebilsin diye "verilmedi" anlamına
    gelen bir ayıraç (sentinel) kullanır.
    """
    from app.main import app

    installed: dict[str, Any] = {}
    UNSET = object()

    def _install(tmdb=None, cor=UNSET):
        fake_tmdb = tmdb if tmdb is not None else FakeTMDB(results=[DUNE])
        fake_cor = FakeCor(dune_pick()) if cor is UNSET else cor
        app.dependency_overrides[get_tmdb_client] = lambda: fake_tmdb
        app.dependency_overrides[get_cor_client] = lambda: fake_cor
        installed["tmdb"], installed["cor"] = fake_tmdb, fake_cor
        return installed

    yield _install


@pytest.fixture
def without_tmdb_key(monkeypatch):
    """`TMDB_API_KEY` yokken bağımlılık override'ı olmayan durumu kurar."""
    from app.main import app

    monkeypatch.delenv("TMDB_API_KEY", raising=False)
    app.dependency_overrides.pop(get_tmdb_client, None)
    app.dependency_overrides.pop(get_cor_client, None)


# --------------------------------------------------------------------- #
# Başarılı senaryo
# --------------------------------------------------------------------- #


def test_recommend_success(client, fakes) -> None:
    installed = fakes()

    res = client.get("/api/recommend", params={"mood": "bilim kurgu"})

    assert res.status_code == 200
    assert res.json() == {"suggestions": [SUGGESTION]}
    assert installed["tmdb"].calls == [("movie", 878), ("tv", 10765)]
    assert "bilim kurgu" in installed["cor"].prompts[0]


def test_recommend_uses_mood_genre_map(client, fakes) -> None:
    installed = fakes()

    client.get("/api/recommend", params={"mood": "korku"})

    assert installed["tmdb"].calls == [("movie", 27), ("tv", 9648)]


def test_recommend_unknown_mood_falls_back_to_drama(client, fakes) -> None:
    installed = fakes()

    res = client.get("/api/recommend", params={"mood": "pazartesi"})

    assert res.status_code == 200
    assert installed["tmdb"].calls == [("movie", 18), ("tv", 18)]


def test_recommend_excludes_titles_already_in_watchlist(client, fakes) -> None:
    """Listede olan başlık önerilmemeli — kullanıcı prompt'a aday olarak görmemeli."""
    client.post("/api/items", json={"title": "Dune", "kind": "film"})
    installed = fakes()

    res = client.get("/api/recommend", params={"mood": "bilim kurgu"})

    assert res.status_code == 502
    assert "henüz eklemediğin bir aday bulunamadı" in res.json()["detail"]
    assert installed["cor"].prompts == []  # havuz boşaldıysa cor'a hiç gidilmedi


def test_recommend_mood_is_trimmed(client, fakes) -> None:
    installed = fakes()

    res = client.get("/api/recommend", params={"mood": "  komedi  "})

    assert res.status_code == 200
    assert installed["tmdb"].calls == [("movie", 35), ("tv", 35)]


# --------------------------------------------------------------------- #
# Doğrulama ve eksik yapılandırma
# --------------------------------------------------------------------- #


def test_missing_mood_422(client) -> None:
    res = client.get("/api/recommend")
    assert res.status_code == 422


def test_blank_mood_422(client) -> None:
    res = client.get("/api/recommend", params={"mood": "   "})
    assert res.status_code == 422
    assert res.json()["detail"] == "mood boş olamaz"


def test_without_tmdb_key_503(client, without_tmdb_key) -> None:
    res = client.get("/api/recommend", params={"mood": "komedi"})

    assert res.status_code == 503
    assert res.json()["detail"] == "TMDB_API_KEY ayarlanmamış"


# --------------------------------------------------------------------- #
# Öneri motoru hataları — sessiz boş liste YOK
# --------------------------------------------------------------------- #


def test_cor_client_none_502(client, fakes) -> None:
    fakes(tmdb=FakeTMDB(results=[DUNE]), cor=None)

    res = client.get("/api/recommend", params={"mood": "komedi"})

    assert res.status_code == 502
    assert res.json()["detail"] == "öneri motoruna ulaşılamadı"


def test_cor_connection_error_502(client, fakes) -> None:
    fakes(tmdb=FakeTMDB(results=[DUNE]), cor=FakeCor(error=LLMError("cor proxy'ye bağlanılamadı")))

    res = client.get("/api/recommend", params={"mood": "komedi"})

    assert res.status_code == 502
    assert res.json()["detail"] == "öneri motoruna ulaşılamadı"


def test_cor_broken_json_502(client, fakes) -> None:
    fakes(tmdb=FakeTMDB(results=[DUNE]), cor=FakeCor("bu JSON değil"))

    res = client.get("/api/recommend", params={"mood": "komedi"})

    assert res.status_code == 502
    assert "JSON" in res.json()["detail"]


def test_empty_candidate_pool_502(client, fakes) -> None:
    fakes(tmdb=FakeTMDB(results=[]), cor=FakeCor("[]"))

    res = client.get("/api/recommend", params={"mood": "komedi"})

    assert res.status_code == 502
    assert "henüz eklemediğin bir aday bulunamadı" in res.json()["detail"]


def test_tmdb_error_502(client, fakes) -> None:
    fakes(tmdb=FakeTMDB(error=TMDBError("TMDB /discover/movie için HTTP 500 döndü")))

    res = client.get("/api/recommend", params={"mood": "komedi"})

    assert res.status_code == 502
    assert "HTTP 500" in res.json()["detail"]


def test_tv_discover_failure_502(client, fakes) -> None:
    """İlk discover geçse de ikincisi patlarsa da 502 — yarım sonuç uydurulmaz."""
    fakes(tmdb=PartiallyFailingTMDB(), cor=FakeCor(dune_pick()))

    res = client.get("/api/recommend", params={"mood": "komedi"})

    assert res.status_code == 502
    assert "/discover/tv" in res.json()["detail"]
