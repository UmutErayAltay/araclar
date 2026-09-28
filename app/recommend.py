"""Ruh haline göre öneri motoru.

Akış: ruh hali kelimesi → TMDB genre id'leri (`MOOD_GENRE_MAP`) → iki
`discover` çağrısıyla aday havuzu → kullanıcının listesinde olanlar elenir →
en fazla 15 aday cor'a gönderilir → cor en fazla 5 tanesini seçer ve her
biri için tek cümlelik Türkçe gerekçe yazar.

İki kural her yerde geçerli:
  * "Eşleşme yok" diye hata VERMİYORUZ — bilinmeyen bir ruh hali bile
    Drama havuzundan aday üretir, çünkü "hiçbir şey bulunamadı" demektense
    bir şey önermek yeğdir.
  * Boş/bozuk cevapta sahte öneri UYDURMUYORUZ: `RecommendationError`
    yükselir, üst katman bunu 502'ye çevirir.
"""

from __future__ import annotations

import itertools
import json
from typing import Any, Protocol, runtime_checkable

from app.llm import LLMClient, LLMError

# Sözleşmedeki tablo BİREBİR: anahtar kelimeler (substring), movie/tv genre id.
# Sıra önemlidir — ilk eşleşen kazanır.
MOOD_GENRE_MAP: dict[str, dict[str, int]] = {
    "hafif,eğlenceli,rahatlatıcı,komedi": {"movie": 35, "tv": 35},
    "gerilim,heyecan,gizem": {"movie": 53, "tv": 9648},
    "korku": {"movie": 27, "tv": 9648},
    "romantik,aşk": {"movie": 10749, "tv": 18},
    "aksiyon": {"movie": 28, "tv": 10759},
    "bilim kurgu,fantastik,uzay": {"movie": 878, "tv": 10765},
    "duygusal,ağlatan,dram": {"movie": 18, "tv": 18},
    "aile,çocuk": {"movie": 10751, "tv": 10751},
}

# Hiçbir anahtar kelime geçmiyorsa: Drama (movie 18, tv 18).
DEFAULT_GENRE: dict[str, int] = {"movie": 18, "tv": 18}

MAX_CANDIDATES_TO_LLM = 15
MAX_SUGGESTIONS = 5

# `discover` sonuçları bu kaynaktan geliyor; öneri kartındaki "ekle" düğmesi
# bu alanı `POST /api/items`'a taşıyor.
EXTERNAL_SOURCE = "tmdb"

# TMDB `media_type` → uygulamadaki `Item.kind` etiketi.
KIND_BY_MEDIA_TYPE = {"movie": "film", "tv": "dizi"}


class RecommendationError(RuntimeError):
    """Öneri üretilemedi — sessizce sahte/boş öneri dönmüyoruz."""


@runtime_checkable
class DiscoverClient(Protocol):
    """`recommend()`'in TMDB istemcisinden beklediği en küçük arayüz."""

    def discover(
        self, media_type: str, genre_id: int, page: int = 1
    ) -> list[dict[str, Any]]: ...


def genre_for_mood(mood: str) -> dict[str, int]:
    """Ruh hali metninden `{movie, tv}` genre id'lerini bulur.

    Eşleşme bulunamazsa Drama'ya düşer — hata fırlatmaz, çünkü sözleşme
    "her zaman bir aday havuzu üretilebilmeli" diyor.
    """
    lowered = (mood or "").lower()
    for keywords, genres in MOOD_GENRE_MAP.items():
        for keyword in keywords.split(","):
            if keyword.strip() and keyword.strip() in lowered:
                return genres
    return DEFAULT_GENRE


def _build_pool(
    tmdb_client: DiscoverClient, genres: dict[str, int]
) -> list[dict[str, Any]]:
    """İki `discover` çağrısını ALTERNATİF harmanlayıp her adaya `kind` etiketi ekler.

    Ardışık birleştirme (önce tüm movie'ler, sonra tüm tv'ler) bozuktur:
    `discover` TMDB'nin varsayılan sayfa boyutunu (~20) döndürdüğü için
    `MAX_CANDIDATES_TO_LLM`'lik kırpma yalnızca movie'lerle dolar ve dizi
    adayları LLM'e hiç ulaşmaz. Sıra bu yüzden `movie[0], tv[0], movie[1],
    tv[1], ...` olur; bir liste bitince diğerinden devam eder.
    """
    tagged: list[list[dict[str, Any]]] = []
    for media_type in ("movie", "tv"):
        kind = KIND_BY_MEDIA_TYPE[media_type]
        tagged.append(
            [
                {**item, "kind": kind}
                for item in (tmdb_client.discover(media_type, genres[media_type]) or [])
                if isinstance(item, dict) and item.get("title")
            ]
        )

    # `zip_longest` kısa olan liste bittiğinde `None` üretir; onları atıyoruz.
    return [
        item
        for group in itertools.zip_longest(*tagged)
        for item in group
        if item is not None
    ]


def _strip_code_fence(text: str) -> str:
    """```json ... ``` ile sarılmış yanıtın kod bloğunu ayıklar."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    stripped = stripped[3:]
    if stripped[:4].lower() == "json":
        stripped = stripped[4:]
    if stripped.rstrip().endswith("```"):
        stripped = stripped.rstrip()[:-3]
    return stripped.strip()


def _parse_suggestions(raw: str) -> list[dict[str, str]]:
    """cor'un metnini `[{"title", "reason"}, ...]` listesine çevirir.

    Bozuk/boş JSON'da `RecommendationError` yükselir.
    """
    payload = _strip_code_fence(raw or "")
    try:
        parsed = json.loads(payload)
    except (json.JSONDecodeError, TypeError) as exc:
        raise RecommendationError(
            f"öneri motoru okunabilir bir JSON dönmedi: {payload[:200]}"
        ) from exc

    if not isinstance(parsed, list):
        raise RecommendationError(
            f"öneri motoru JSON dizisi yerine başka bir biçim döndü: {payload[:200]}"
        )
    return [item for item in parsed if isinstance(item, dict)]


def build_prompt(mood: str, candidates: list[dict[str, Any]]) -> str:
    """Adayları ve ruh halini cor'a verilecek Türkçe istem metnine çevirir."""
    lines = [f'Kullanıcının ruh hali: "{mood.strip()}"', "", "=== ADAYLAR ==="]
    for index, candidate in enumerate(candidates, start=1):
        line = f"{index}. {candidate['title']}"
        if candidate.get("kind") == "dizi":
            line += " (dizi)"
        if candidate.get("overview"):
            line += f" — {candidate['overview']}"
        lines.append(line)

    lines += [
        "",
        "=== TALİMAT ===",
        "Yukarıdaki adaylar arasından kullanıcının ruh haline en uyan EN FAZLA "
        f"{MAX_SUGGESTIONS} tanesini seç.",
        "Yanıtın SADECE bir JSON dizisi olsun; kod bloğu, açıklama ya da başka "
        "metin EKLEME. Biçim tam olarak şöyle:",
        '[{"title": "<adaylardan birebir bir başlık>", "reason": "<tek cümle Türkçe gerekçe>"}]',
        'title alanına listede BULUNMAYAN bir başlık yazma; reason alanı tek cümle olsun.',
    ]
    return "\n".join(lines)


def recommend(
    mood: str,
    existing_titles: list[str],
    tmdb_client: DiscoverClient,
    cor_client: LLMClient,
) -> list[dict[str, Any]]:
    """Ruh haline göre en fazla 5 öneri döner.

    Boş havuz, bozuk LLM yanıtı veya havuzla eşleşmeyen başlıklar
    `RecommendationError` yükseltir — sessiz boş/sahte liste DÖNMEZ.
    """
    genres = genre_for_mood(mood)
    candidates = _build_pool(tmdb_client, genres)

    already_watching = {title.strip().lower() for title in (existing_titles or []) if title}
    candidates = [c for c in candidates if c["title"].strip().lower() not in already_watching]

    if not candidates:
        raise RecommendationError(
            "bu ruh haline uygun, henüz eklemediğin bir aday bulunamadı"
        )

    try:
        raw = cor_client.complete(build_prompt(mood, candidates[:MAX_CANDIDATES_TO_LLM]))
    except LLMError:
        raise
    except Exception as exc:  # sahte istemci vb. beklenmeyen hatalar
        raise RecommendationError(f"öneri motoruna ulaşılamadı: {exc}") from exc

    picks = _parse_suggestions(raw)

    by_title = {c["title"].strip().lower(): c for c in candidates}
    suggestions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for pick in picks:
        if len(suggestions) >= MAX_SUGGESTIONS:
            break
        title = pick.get("title")
        # Uydurma başlıkları SESSİZCE atla — havuzda olmayan bir şeyi ekleme.
        candidate = by_title.get(str(title).strip().lower()) if isinstance(title, str) else None
        if candidate is None or candidate["title"] in seen:
            continue
        seen.add(candidate["title"])
        suggestions.append(
            {
                "title": candidate["title"],
                "kind": candidate["kind"],
                "reason": (pick.get("reason") or "").strip() or None,
                "external_source": EXTERNAL_SOURCE,
                "external_id": candidate.get("external_id"),
                "poster_url": candidate.get("poster_url"),
            }
        )

    if not suggestions:
        raise RecommendationError(
            "öneri motorundan gelen başlıkların hiçbiri aday havuzuyla eşleşmedi"
        )
    return suggestions
