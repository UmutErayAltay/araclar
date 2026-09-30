"""Open Library'ye konuşan ince HTTP istemcisi.

Tasarım notları:
  * Ekstra bağımlılık yok: `urllib.request` (anlat/bridge/client.py ile aynı
    yaklaşım). `base_url` test'lerde yerel bir `http.server`'a çevrilebilir.
  * API key GEREKMEZ. Aynı hata deseni: bağlantı/HTTP/JSON hatasında
    `OpenLibraryError`; eşleşen kitap yoksa boş liste.
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

DEFAULT_BASE_URL = "https://openlibrary.org"
DEFAULT_TIMEOUT = 10.0

COVER_BASE_URL = "https://covers.openlibrary.org/b/id/"

CONNECT_HELP = (
    "Open Library'ye bağlanılamadı — ağ bağlantısını kontrol et."
)


class OpenLibraryError(RuntimeError):
    """Open Library ile konuşulurken HTTP/JSON hatası ya da beklenmeyen gövde oluştu."""


class OpenLibraryClient:
    """Open Library kitap araması için ince istemci."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    # ------------------------------------------------------------------ #
    # Taşıma katmanı
    # ------------------------------------------------------------------ #

    def _get(self, path: str, query: dict[str, str]) -> dict[str, Any]:
        """Tek bir GET atar ve çözülmüş JSON sözlüğünü döner."""
        url = f"{self.base_url}{path}?{urllib.parse.urlencode(query)}"

        request = urllib.request.Request(
            url, headers={"accept": "application/json"}, method="GET"
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise OpenLibraryError(
                f"Open Library {path} için HTTP {exc.code} döndü: {detail}"
            ) from exc
        except (urllib.error.URLError, socket.timeout, OSError) as exc:
            raise OpenLibraryError(f"{CONNECT_HELP} (Detay: {exc})") from exc

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise OpenLibraryError(
                f"Open Library'den beklenmeyen yanıt biçimi ({path}): {raw[:500]}"
            ) from exc
        if not isinstance(parsed, dict):
            raise OpenLibraryError(
                f"Open Library beklenmeyen bir gövde döndü ({path}): {raw[:500]}"
            )
        return parsed

    # ------------------------------------------------------------------ #
    # Uç
    # ------------------------------------------------------------------ #

    def search(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        """`/search.json?q=...` → `[{title, author, year, poster_url, external_id}]`.

        Open Library sayfa başına varsayılan olarak 100 sonuç döner — bu bir
        arama-öneri dropdown'u için fazla, `limit` ile kırpılır.
        """
        if not query or not query.strip():
            raise OpenLibraryError("arama sorgusu boş olamaz")

        payload = self._get("/search.json", {"q": query, "limit": str(limit)})
        docs = payload.get("docs")
        if not isinstance(docs, list):
            return []
        return [self._to_result(doc) for doc in docs[:limit] if isinstance(doc, dict)]

    # ------------------------------------------------------------------ #
    # Eşleme
    # ------------------------------------------------------------------ #

    @staticmethod
    def _to_result(raw: dict[str, Any]) -> dict[str, Any]:
        authors = raw.get("author_name")
        author = (
            authors[0] if isinstance(authors, list) and authors and isinstance(authors[0], str) else None
        )
        cover_id = raw.get("cover_i")
        year = raw.get("first_publish_year")
        return {
            "title": raw.get("title") or None,
            "author": author,
            "year": year if isinstance(year, int) else None,
            "poster_url": f"{COVER_BASE_URL}{cover_id}-M.jpg" if cover_id is not None else None,
            "external_id": raw.get("key") or None,
        }
