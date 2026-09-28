"""TMDB'ye konuşan ince HTTP istemcisi.

Tasarım notları:
  * Ekstra bağımlılık yok: `urllib.request` (anlat/bridge/client.py ile aynı
    yaklaşım). `base_url` test'lerde yerel bir `http.server`'a çevrilebilir.
  * Anahtar yoksa sessiz sahte/boş sonuç DÖNMEZ: `TMDBNotConfiguredError`
    yükselir. HTTP/JSON hataları da `TMDBError` olur. Tek istisna: "arama
    sonucu yok" ve "bölgede abonelik sağlayıcısı yok" — bunlar sözleşmede
    boş liste olarak tanımlıdır.
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

DEFAULT_BASE_URL = "https://api.themoviedb.org/3"
DEFAULT_TIMEOUT = 10.0

POSTER_BASE_URL = "https://image.tmdb.org/t/p/"
POSTER_SIZE = "w342"
LOGO_SIZE = "w92"
LANGUAGE = "tr-TR"

CONNECT_HELP = (
    "TMDB'ye bağlanılamadı — ağ bağlantısını ve TMDB_API_KEY ortam değişkenini "
    "kontrol et (anahtarını themoviedb.org hesabından alabilirsin)."
)


class TMDBError(RuntimeError):
    """TMDB ile konuşulurken HTTP/JSON hatası ya da beklenmeyen gövde oluştu."""


class TMDBNotConfiguredError(TMDBError):
    """İstemci anahtarsız kurulmaya çalışıldı."""


def _poster_url(path: str | None, size: str) -> str | None:
    return f"{POSTER_BASE_URL}{size}{path}" if path else None


def _year_from(date: Any) -> int | None:
    head = str(date)[:4]
    return int(head) if head.isdigit() else None


class TMDBClient:
    """TMDB v3 arama ve "nerede izlerim" sağlayıcı uçları için ince istemci."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        if not api_key or not api_key.strip():
            raise TMDBNotConfiguredError("TMDB_API_KEY ayarlanmamış")
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    # ------------------------------------------------------------------ #
    # Taşıma katmanı
    # ------------------------------------------------------------------ #

    def _get(self, path: str, query: dict[str, str]) -> dict[str, Any]:
        """Tek bir GET atar ve çözülmüş JSON sözlüğünü döner.

        Bağlantı, HTTP ve JSON hataları `TMDBError` olur; hiçbir koşulda boş
        sözlük dönme.
        """
        params = dict(query)
        params["api_key"] = self.api_key
        url = f"{self.base_url}{path}?{urllib.parse.urlencode(params)}"

        request = urllib.request.Request(
            url, headers={"accept": "application/json"}, method="GET"
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise TMDBError(f"TMDB {path} için HTTP {exc.code} döndü: {detail}") from exc
        except (urllib.error.URLError, socket.timeout, OSError) as exc:
            raise TMDBError(f"{CONNECT_HELP} (Detay: {exc})") from exc

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise TMDBError(
                f"TMDB'den beklenmeyen yanıt biçimi ({path}): {raw[:500]}"
            ) from exc
        if not isinstance(parsed, dict):
            raise TMDBError(f"TMDB beklenmeyen bir gövde döndü ({path}): {raw[:500]}")
        return parsed

    # ------------------------------------------------------------------ #
    # Uçlar
    # ------------------------------------------------------------------ #

    def search(self, query: str, media_type: str, limit: int = 8) -> list[dict[str, Any]]:
        """`/search/{movie|tv}` → `[{title, year, poster_url, external_id, overview}]`.

        Eşleşen tek bir film/dizi yoksa boş liste döner (bu bir hatadır değil).
        TMDB sayfa başına 20 sonuç döner — arama-öneri dropdown'u için
        `limit` ile kırpılır.
        """
        if not query or not query.strip():
            raise TMDBError("arama sorgusu boş olamaz")

        payload = self._get(f"/search/{media_type}", {"query": query, "language": LANGUAGE})
        results = payload.get("results")
        if not isinstance(results, list):
            return []
        return [self._to_result(item) for item in results[:limit] if isinstance(item, dict)]

    def discover(
        self, media_type: str, genre_id: int, page: int = 1
    ) -> list[dict[str, Any]]:
        """`/discover/{movie|tv}` → `[{title, year, poster_url, external_id, overview}]`.

        Ruh haline göre öneri motorunun aday havuzunu besler: `with_genres`
        ile türe göre süzüp popülerliğe göre sıralarız.

        `search`'ten iki farkı var: kırpma (`limit`) YOK — aday havuzu için
        TMDB'nin varsayılan sayfa boyutu (genelde 20) olduğu gibi döner.
        """
        payload = self._get(
            f"/discover/{media_type}",
            {
                "with_genres": str(genre_id),
                "language": LANGUAGE,
                "sort_by": "popularity.desc",
                "page": str(page),
            },
        )
        results = payload.get("results")
        if not isinstance(results, list):
            return []
        return [self._to_result(item) for item in results if isinstance(item, dict)]

    def watch_providers(
        self, media_type: str, tmdb_id: str, region: str
    ) -> list[dict[str, Any]]:
        """`/{media_type}/{id}/watch/providers` → `[{provider_name, logo_url, link}]`.

        Yalnızca `flatrate` (abonelik) sağlayıcıları döner; `buy`/`rent`
        dahil edilmez. Bölgede veri yoksa boş liste döner — hata değildir.
        """
        code = (region or "").strip().upper()
        payload = self._get(
            f"/{media_type}/{tmdb_id}/watch/providers", {"language": LANGUAGE}
        )

        results = payload.get("results")
        if not isinstance(results, dict):
            return []
        entry = results.get(code)
        if not isinstance(entry, dict):
            return []

        link = entry.get("link") if isinstance(entry.get("link"), str) else None
        flatrate = entry.get("flatrate")
        if not isinstance(flatrate, list):
            return []
        return [
            {
                "provider_name": item.get("provider_name") or None,
                "logo_url": _poster_url(item.get("logo_path"), LOGO_SIZE),
                "link": link,
            }
            for item in flatrate
            if isinstance(item, dict)
        ]

    # ------------------------------------------------------------------ #
    # Eşleme
    # ------------------------------------------------------------------ #

    @staticmethod
    def _to_result(raw: dict[str, Any]) -> dict[str, Any]:
        media_id = raw.get("id")
        return {
            "title": raw.get("title") or raw.get("name") or None,
            "year": _year_from(raw.get("release_date") or raw.get("first_air_date") or ""),
            "poster_url": _poster_url(raw.get("poster_path"), POSTER_SIZE),
            "external_id": str(media_id) if media_id is not None else None,
            "overview": raw.get("overview") or None,
        }
