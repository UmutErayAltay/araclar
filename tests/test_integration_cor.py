"""İsteğe bağlı gerçek cor entegrasyon testi.

Varsayılan `pytest` koşusunda ATLANIR (pyproject.toml: -m "not integration").
Çalıştırmak için:  pytest -m integration
"""

from __future__ import annotations

import json
import socket

import pytest

from app.llm import DEFAULT_BASE_URL, CorLLMClient
from app.recommend import build_prompt, recommend


def cor_reachable(base_url: str = DEFAULT_BASE_URL) -> bool:
    host, port = "127.0.0.1", int(base_url.rsplit(":", 1)[1])
    with socket.socket() as sock:
        sock.settimeout(1.0)
        return sock.connect_ex((host, port)) == 0


CANDIDATES = [
    {
        "title": "Dune",
        "kind": "film",
        "year": 2021,
        "overview": "Bir çöl gezegeninde iktidar savaşı.",
        "external_id": "438631",
        "poster_url": None,
    },
    {
        "title": "Arrival",
        "kind": "film",
        "year": 2016,
        "overview": "Dünya dışı ziyaretçiler ve dil.",
        "external_id": "329865",
        "poster_url": None,
    },
]


@pytest.mark.integration
def test_real_cor_returns_parsable_json() -> None:
    """Gerçek proxy gerçekten sözleşmedeki JSON dizisini döndürüyor mu?"""
    if not cor_reachable():
        pytest.skip("cor proxy bu ortamda erişilebilir değil")

    raw = CorLLMClient(timeout=120.0).complete(build_prompt("bilim kurgu", CANDIDATES))

    assert json.loads(raw.strip().strip("`").removeprefix("json"))


@pytest.mark.integration
def test_real_end_to_end_recommendation() -> None:
    if not cor_reachable():
        pytest.skip("cor proxy bu ortamda erişilebilir değil")

    class RealTMDB:
        def discover(self, media_type, genre_id, page=1):
            return CANDIDATES if media_type == "movie" else []

    suggestions = recommend(
        "bilim kurgu", [], RealTMDB(), CorLLMClient(timeout=300.0)
    )

    assert 1 <= len(suggestions) <= 5
    for suggestion in suggestions:
        assert suggestion["title"] in {c["title"] for c in CANDIDATES}
        assert suggestion["external_source"] == "tmdb"
