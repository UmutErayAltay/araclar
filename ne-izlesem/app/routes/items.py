import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator

from app.db import (
    VALID_KINDS,
    VALID_STATUSES,
    create_item,
    delete_item,
    get_connection,
    get_item,
    list_items,
    update_item,
)
from app.external.tmdb import TMDBClient, TMDBError

router = APIRouter()

TMDB_NOT_CONFIGURED_MESSAGE = "TMDB_API_KEY ayarlanmamış"
DEFAULT_WATCH_REGION = "TR"

# `kind` → TMDB `media_type`. `anime` TMDB'de `movie` altında aranır.
MEDIA_TYPE_BY_KIND = {"film": "movie", "anime": "movie", "dizi": "tv"}


def get_db():
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


def get_tmdb_client() -> Optional[TMDBClient]:
    """`TMDB_API_KEY`'den istemci üretir; anahtar yoksa `None` döner.

    Anahtar eksikliğini burada istisnaya çevirmiyoruz: bağımlılıklar route
    gövdesinden ÖNCE çözüldüğü için bu istisna, `kind=kitap` gibi TMDB'ye
    hiç gidilmeyen istekleri de 503'e düşürürdü. Bunun yerine `None`
    döndürüp 503'ü route içinde, gerçekten TMDB çağrısı yapılacakken fırlatıyoruz.
    """
    api_key = os.environ.get("TMDB_API_KEY", "").strip()
    if not api_key:
        return None
    return TMDBClient(api_key=api_key)


def _kind_message() -> str:
    return f"kind şunlardan biri olmalı: {sorted(VALID_KINDS)}"


def _status_message() -> str:
    return f"status şunlardan biri olmalı: {sorted(VALID_STATUSES)}"


class ItemCreate(BaseModel):
    title: str
    kind: str
    status: str = "planlanan"
    rating: Optional[int] = None
    note: Optional[str] = None
    poster_url: Optional[str] = None
    external_source: Optional[str] = None
    external_id: Optional[str] = None

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("title boş olamaz")
        return v.strip()

    @field_validator("kind")
    @classmethod
    def kind_valid(cls, v: str) -> str:
        if v not in VALID_KINDS:
            raise ValueError(_kind_message())
        return v

    @field_validator("status")
    @classmethod
    def status_valid(cls, v: str) -> str:
        if v not in VALID_STATUSES:
            raise ValueError(_status_message())
        return v

    @field_validator("rating")
    @classmethod
    def rating_range(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not (1 <= v <= 5):
            raise ValueError("rating 1-5 arasında olmalı")
        return v


class ItemUpdate(BaseModel):
    title: Optional[str] = None
    kind: Optional[str] = None
    status: Optional[str] = None
    rating: Optional[int] = None
    note: Optional[str] = None
    poster_url: Optional[str] = None
    external_source: Optional[str] = None
    external_id: Optional[str] = None

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.strip():
            raise ValueError("title boş olamaz")
        return v.strip() if v is not None else v

    @field_validator("kind")
    @classmethod
    def kind_valid(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in VALID_KINDS:
            raise ValueError(_kind_message())
        return v

    @field_validator("status")
    @classmethod
    def status_valid(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in VALID_STATUSES:
            raise ValueError(_status_message())
        return v

    @field_validator("rating")
    @classmethod
    def rating_range(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not (1 <= v <= 5):
            raise ValueError("rating 1-5 arasında olmalı")
        return v


@router.get("/api/items")
def get_items(
    kind: Optional[str] = None,
    status: Optional[str] = None,
    q: Optional[str] = None,
    conn=Depends(get_db),
):
    if kind is not None and kind not in VALID_KINDS:
        raise HTTPException(status_code=422, detail=_kind_message())
    if status is not None and status not in VALID_STATUSES:
        raise HTTPException(status_code=422, detail=_status_message())
    return {"items": list_items(conn, kind=kind, status=status, q=q)}


@router.post("/api/items", status_code=201)
def post_item(payload: ItemCreate, conn=Depends(get_db)):
    return create_item(
        conn,
        title=payload.title,
        kind=payload.kind,
        status=payload.status,
        rating=payload.rating,
        note=payload.note,
        poster_url=payload.poster_url,
        external_source=payload.external_source,
        external_id=payload.external_id,
    )


@router.patch("/api/items/{item_id}")
def patch_item(item_id: int, payload: ItemUpdate, conn=Depends(get_db)):
    fields = payload.model_dump(exclude_unset=True)
    if not fields:
        existing = get_item(conn, item_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="öğe bulunamadı")
        return existing
    updated = update_item(conn, item_id, **fields)
    if updated is None:
        raise HTTPException(status_code=404, detail="öğe bulunamadı")
    return updated


@router.delete("/api/items/{item_id}", status_code=204)
def delete_item_route(item_id: int, conn=Depends(get_db)):
    if not delete_item(conn, item_id):
        raise HTTPException(status_code=404, detail="öğe bulunamadı")
    return None


@router.get("/api/items/{item_id}/watch")
def get_item_watch(
    item_id: int,
    region: Optional[str] = None,
    conn=Depends(get_db),
    tmdb=Depends(get_tmdb_client),
):
    """Bir öğe için bölgedeki abonelik (flatrate) sağlayıcılarını döner.

    Sahte/boş liste dönmüyoruz: kitap türü ya da dış veri bağlantısı olmayan
    öğe 404, `TMDB_API_KEY` yoksa 503.
    """
    item = get_item(conn, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="öğe bulunamadı")
    if item["kind"] == "kitap":
        raise HTTPException(
            status_code=404, detail="kitap için 'nerede izlerim' anlamsız"
        )
    if not item["external_id"] or not item["external_source"]:
        raise HTTPException(
            status_code=404,
            detail="bu öğe bir dış kaynağa bağlı değil; önce dış aramadan seçilmelidir",
        )

    media_type = MEDIA_TYPE_BY_KIND.get(item["kind"])
    if media_type is None:
        raise HTTPException(status_code=404, detail="bu tür için sağlayıcı aranmaz")

    effective_region = (region or os.environ.get("WATCH_REGION") or DEFAULT_WATCH_REGION).strip()

    if tmdb is None:
        raise HTTPException(status_code=503, detail=TMDB_NOT_CONFIGURED_MESSAGE)

    try:
        providers = tmdb.watch_providers(media_type, item["external_id"], effective_region)
    except TMDBError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"providers": providers}
