from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from app.db import VALID_KINDS
from app.external.openlibrary import OpenLibraryClient, OpenLibraryError
from app.external.tmdb import TMDBError
from app.routes.items import MEDIA_TYPE_BY_KIND, TMDB_NOT_CONFIGURED_MESSAGE, get_tmdb_client

router = APIRouter()


def get_openlibrary_client() -> OpenLibraryClient:
    """Open Library anahtar gerektirmez; bağımlılık yalnızca test override'ı içindir."""
    return OpenLibraryClient()


def get_kind_message() -> str:
    return f"kind şunlardan biri olmalı: {sorted(VALID_KINDS)}"


@router.get("/api/search")
def search_external(
    kind: str,
    q: str,
    tmdb=Depends(get_tmdb_client),
    openlibrary=Depends(get_openlibrary_client),
):
    """`kind`e göre TMDB ya da Open Library'de arar ve `{"results": [...]}` döner.

    `q` boşsa 422, `kind` geçersizse 422. `TMDB_API_KEY` yoksa (ve tür
    `kitap` değilse) 503 — sahte/boş sonuç dönülmez.
    """
    if not q or not q.strip():
        raise HTTPException(status_code=422, detail="q boş olamaz")
    if kind not in VALID_KINDS:
        raise HTTPException(status_code=422, detail=get_kind_message())

    query = q.strip()
    if kind == "kitap":
        try:
            results = openlibrary.search(query)
        except OpenLibraryError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return {"results": _tag_source(results, "openlibrary")}

    if tmdb is None:
        raise HTTPException(status_code=503, detail=TMDB_NOT_CONFIGURED_MESSAGE)

    try:
        results = tmdb.search(query, MEDIA_TYPE_BY_KIND[kind])
    except TMDBError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"results": _tag_source(results, "tmdb")}


def _tag_source(results: list[dict], source: str) -> list[dict]:
    """Her sonuca hangi dış kaynaktan geldiğini ekler.

    Frontend `POST/PATCH /api/items`'a `external_source`'u bu alandan
    okuyup gönderiyor — eklenmezse `Item.external_source` hep null kalır
    ve "nerede izlerim" 404'e düşer (external_source zorunlu).
    """
    return [{**result, "external_source": source} for result in results]
