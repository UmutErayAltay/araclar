"""`GET /api/recommend` — ruh haline göre öneri uç noktası."""

from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from app.db import list_items
from app.external.tmdb import TMDBError
from app.llm import CorLLMClient, LLMError
from app.recommend import RecommendationError, recommend
from app.routes.items import TMDB_NOT_CONFIGURED_MESSAGE, get_db, get_tmdb_client

router = APIRouter()

COR_UNREACHABLE_MESSAGE = "öneri motoruna ulaşılamadı"


def get_cor_client() -> CorLLMClient:
    """`COR_BASE_URL`/`COR_MODEL`'den istemci üretir.

    `COR_BASE_URL` tanımlı değilse varsayılan localhost adresine düşer; proxy
    çalışmıyorsa istek 502'ye döner, sahte öneri dönülmez. Test'lerde
    `app.dependency_overrides` ile değiştirilir.
    """
    return CorLLMClient(
        base_url=os.environ.get("COR_BASE_URL", "http://127.0.0.1:8787"),
        model=os.environ.get("COR_MODEL", "stealth/space-bunny-alpha"),
    )


@router.get("/api/recommend")
def recommend_route(
    mood: str,
    conn=Depends(get_db),
    tmdb=Depends(get_tmdb_client),
    cor=Depends(get_cor_client),
):
    """`mood` zorunlu, boşsa 422. `TMDB_API_KEY` yoksa 503, cor'a ulaşılamazsa 502.

    Sessiz boş liste DÖNMÜYORUZ: aday havuzu boşsa ya da cor bozuk/boş yanıt
    dönerse 502 + açıklayıcı mesaj.
    """
    if not mood or not mood.strip():
        raise HTTPException(status_code=422, detail="mood boş olamaz")
    if tmdb is None:
        raise HTTPException(status_code=503, detail=TMDB_NOT_CONFIGURED_MESSAGE)
    if cor is None:
        raise HTTPException(status_code=502, detail=COR_UNREACHABLE_MESSAGE)

    existing_titles = [item["title"] for item in list_items(conn)]

    try:
        suggestions = recommend(mood.strip(), existing_titles, tmdb, cor)
    except LLMError as exc:
        # Gerçek neden log'a kalsın; kullanıcıya sözleşmedeki mesaj gitsin.
        raise HTTPException(status_code=502, detail=COR_UNREACHABLE_MESSAGE) from exc
    except (RecommendationError, TMDBError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {"suggestions": suggestions}
