"""`app/recommend.py` testleri.

Ne gerçek TMDB'ye ne de gerçek cor'a gidilir: sahte bir `discover` istemcisi
ve `LLMClient` protokolüne uyan sabit-yanıt bir sınıf kullanılır (anlat'ın
`test_narrator.py` deseni).
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.llm import LLMClient
from app.recommend import (
    DEFAULT_GENRE,
    MAX_CANDIDATES_TO_LLM,
    MOOD_GENRE_MAP,
    RecommendationError,
    build_prompt,
    genre_for_mood,
    recommend,
)


# --------------------------------------------------------------------- #
# Sahte istemciler
# --------------------------------------------------------------------- #


def movie(title: str, external_id: str = "1", overview: str | None = "özet") -> dict[str, Any]:
    return {
        "title": title,
        "year": 2020,
        "poster_url": f"https://image.tmdb.org/t/p/w342/{external_id}.jpg",
        "external_id": external_id,
        "overview": overview,
    }


def series(title: str, external_id: str = "1", overview: str | None = "dizi özeti") -> dict[str, Any]:
    return {
        "title": title,
        "year": 2021,
        "poster_url": f"https://image.tmdb.org/t/p/w342/{external_id}.jpg",
        "external_id": external_id,
        "overview": overview,
    }


class FakeTMDB:
    """`discover` arayüzünü taklit eder; kaydettiği genre id'lerini testlere açar."""

    def __init__(self, movies=None, shows=None, error: Exception | None = None) -> None:
        self.movies = movies if movies is not None else []
        self.shows = shows if shows is not None else []
        self.error = error
        self.calls: list[tuple[str, int]] = []

    def discover(self, media_type: str, genre_id: int, page: int = 1) -> list[dict[str, Any]]:
        self.calls.append((media_type, genre_id))
        if self.error:
            raise self.error
        return self.movies if media_type == "movie" else self.shows


class FakeCor:
    """Sabit bir metin döndüren sahte LLMClient (ağa dokunmaz)."""

    model = "fake-model"

    def __init__(self, response: str) -> None:
        self.response = response
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.response


def picks(*titles: str) -> str:
    return json.dumps(
        [{"title": t, "reason": f"{t} bu ruh haline uyuyor."} for t in titles],
        ensure_ascii=False,
    )


# --------------------------------------------------------------------- #
# Protokol
# --------------------------------------------------------------------- #


def test_fake_cor_satisfies_llm_client_protocol() -> None:
    assert isinstance(FakeCor("[]"), LLMClient)


# --------------------------------------------------------------------- #
# MOOD_GENRE_MAP — sözleşmedeki tablo
# --------------------------------------------------------------------- #


def test_mood_genre_map_matches_contract() -> None:
    assert MOOD_GENRE_MAP == {
        "hafif,eğlenceli,rahatlatıcı,komedi": {"movie": 35, "tv": 35},
        "gerilim,heyecan,gizem": {"movie": 53, "tv": 9648},
        "korku": {"movie": 27, "tv": 9648},
        "romantik,aşk": {"movie": 10749, "tv": 18},
        "aksiyon": {"movie": 28, "tv": 10759},
        "bilim kurgu,fantastik,uzay": {"movie": 878, "tv": 10765},
        "duygusal,ağlatan,dram": {"movie": 18, "tv": 18},
        "aile,çocuk": {"movie": 10751, "tv": 10751},
    }


@pytest.mark.parametrize(
    "mood,expected",
    [
        ("akşam biraz komedi istiyorum", {"movie": 35, "tv": 35}),
        ("bugün hafif bir şey", {"movie": 35, "tv": 35}),
        ("rahatlatıcı bir film", {"movie": 35, "tv": 35}),
        ("heyecan istiyorum", {"movie": 53, "tv": 9648}),
        ("karanlık bir gizem", {"movie": 53, "tv": 9648}),
        ("korku yapımı", {"movie": 27, "tv": 9648}),
        ("romantik", {"movie": 10749, "tv": 18}),
        ("aşk hikayesi", {"movie": 10749, "tv": 18}),
        ("bol aksiyon", {"movie": 28, "tv": 10759}),
        ("bilim kurgu", {"movie": 878, "tv": 10765}),
        ("uzay macerası", {"movie": 878, "tv": 10765}),
        ("fantastik", {"movie": 878, "tv": 10765}),
        ("duygusal", {"movie": 18, "tv": 18}),
        ("ağlatan", {"movie": 18, "tv": 18}),
        ("çocuk filmi", {"movie": 10751, "tv": 10751}),
        ("ailece", {"movie": 10751, "tv": 10751}),
    ],
)
def test_genre_for_mood(mood: str, expected: dict[str, int]) -> None:
    assert genre_for_mood(mood) == expected


def test_genre_for_mood_is_case_insensitive() -> None:
    assert genre_for_mood("KORKU") == {"movie": 27, "tv": 9648}
    assert genre_for_mood("Komedi") == {"movie": 35, "tv": 35}


def test_first_match_wins_in_table_order() -> None:
    """'komedi gerilim' — tabloda komedi satırı önce geldiği için o kazanır."""
    assert genre_for_mood("komedi ve gerilim") == {"movie": 35, "tv": 35}


def test_unknown_mood_falls_back_to_drama_never_errors() -> None:
    assert genre_for_mood("pazartesi sabahı") == DEFAULT_GENRE == {"movie": 18, "tv": 18}
    assert genre_for_mood("") == DEFAULT_GENRE
    assert genre_for_mood("   ") == DEFAULT_GENRE


# --------------------------------------------------------------------- #
# Aday havuzu
# --------------------------------------------------------------------- #


def test_recommend_queries_both_media_types_with_mapped_genres() -> None:
    tmdb = FakeTMDB(movies=[movie("Başlangıç", "10")], shows=[series("Dark", "20")])
    cor = FakeCor(picks("Başlangıç", "Dark"))

    recommend("korku", [], tmdb, cor)

    assert tmdb.calls == [("movie", 27), ("tv", 9648)]


def test_recommend_tags_candidates_with_kind() -> None:
    tmdb = FakeTMDB(movies=[movie("Kırmızı Şeyler", "10")], shows=[series("Yeşil Şeyler", "20")])
    cor = FakeCor(picks("Kırmızı Şeyler", "Yeşil Şeyler"))

    result = recommend("dram", [], tmdb, cor)

    by_title = {s["title"]: s for s in result}
    assert by_title["Kırmızı Şeyler"]["kind"] == "film"
    assert by_title["Yeşil Şeyler"]["kind"] == "dizi"


def test_recommend_merges_candidate_metadata() -> None:
    tmdb = FakeTMDB(movies=[movie("Dune", "438631")])
    cor = FakeCor(picks("Dune"))

    (suggestion,) = recommend("bilim kurgu", [], tmdb, cor)

    assert suggestion == {
        "title": "Dune",
        "kind": "film",
        "reason": "Dune bu ruh haline uyuyor.",
        "external_source": "tmdb",
        "external_id": "438631",
        "poster_url": "https://image.tmdb.org/t/p/w342/438631.jpg",
    }


def test_recommend_caps_prompt_at_15_candidates() -> None:
    tmdb = FakeTMDB(movies=[movie(f"Film {i}", str(i)) for i in range(30)])
    cor = FakeCor(picks("Film 0"))

    recommend("dram", [], tmdb, cor)

    prompt = cor.prompts[0]
    assert "Film 14" in prompt
    assert "Film 15" not in prompt
    # Adaylar "1. Film 0" biçiminde numaralanır; talimat bloğunda "Film" geçmez.
    assert prompt.count(". Film ") == MAX_CANDIDATES_TO_LLM


# --------------------------------------------------------------------- #
# Havuz harmanlama — movie ve tv ALTERNATİF sırayla
# --------------------------------------------------------------------- #


def prompt_candidate_lines(cor: FakeCor) -> list[str]:
    """`=== ADAYLAR ===` ile `=== TALİMAT ===` arasındaki aday satırlarını verir.

    Satır biçimi: `"{n}. {title}"` + dizilere `" (dizi)"` + varsa `" — {overview}"`.
    `kind` prompt'a yazılmadığı için sıra yalnızca bu satırlardan okunabiliyor.
    """
    block = cor.prompts[0].split("=== ADAYLAR ===")[1].split("=== TALİMAT ===")[0]
    return [line.strip() for line in block.splitlines() if line.strip()]


def prompt_candidate_kinds(cor: FakeCor) -> list[str]:
    return ["dizi" if " (dizi)" in line else "film" for line in prompt_candidate_lines(cor)]


def prompt_candidate_titles(cor: FakeCor) -> list[str]:
    return [
        line.split(". ", 1)[1].split(" (dizi)")[0].split(" — ")[0]
        for line in prompt_candidate_lines(cor)
    ]


def test_pool_interleaves_movies_and_series_by_rank() -> None:
    """movie[0], tv[0], movie[1], tv[1] … — ardışık birleştirme YAPILMAZ."""
    tmdb = FakeTMDB(
        movies=[movie(f"Film {i}", str(i)) for i in range(3)],
        shows=[series(f"Dizi {i}", str(100 + i)) for i in range(3)],
    )
    cor = FakeCor(picks("Film 0", "Dizi 0"))

    recommend("dram", [], tmdb, cor)

    assert prompt_candidate_kinds(cor) == [
        "film", "dizi",
        "film", "dizi",
        "film", "dizi",
    ]
    # Sıra gerçekten rank'e göre: ilk iki aday movie[0] ve tv[0].
    lines = prompt_candidate_lines(cor)
    assert lines[0].startswith("1. Film 0 ")
    assert lines[1].startswith("2. Dizi 0 (dizi)")


def test_interleaving_lets_series_reach_the_15_cap() -> None:
    """Regresyon: ardışık birleştirmede 15'lik sınırı DİZİLER doldururdu.

    TMDB `discover` ~20 sonuç döndürdüğü için iki sayfa dolu film havuzu
    kırpmanın tamamını alıyordu ve "dizi öner" hiç çalışmıyordu.
    """
    tmdb = FakeTMDB(
        movies=[movie(f"Film {i}", str(i)) for i in range(20)],
        shows=[series(f"Dizi {i}", str(100 + i)) for i in range(20)],
    )
    cor = FakeCor(picks("Dizi 7"))

    recommend("dram", [], tmdb, cor)

    kinds = prompt_candidate_kinds(cor)
    assert len(kinds) == MAX_CANDIDATES_TO_LLM
    # 15 tek sayı → bir fazla film, bir fazla az dizi; ikisi de havuzda.
    assert kinds.count("film") == 8
    assert kinds.count("dizi") == 7
    lines = prompt_candidate_lines(cor)
    # Dizi adayları prompt'a GERÇEKTEN girdi: en sondaki dizi 14. sırada.
    assert any(line.startswith("14. Dizi 6 (dizi)") for line in lines)
    # Sınırın hemen dışındaki 15. dizi girdi değil — kırpma harmanlanmış
    # sırayı kesti, ardışık birleştirmenin yaptığı gibi havuzun başını yedi.
    assert not any("Dizi 7" in line for line in lines)


def test_interleaving_continues_with_the_exhausted_list() -> None:
    """tv listesi daha kısaysa kalan movie'ler boşluksuz devam eder."""
    tmdb = FakeTMDB(
        movies=[movie(f"Film {i}", str(i)) for i in range(4)],
        shows=[series("Dizi 0", "100")],
    )
    cor = FakeCor(picks("Film 3"))

    recommend("dram", [], tmdb, cor)

    assert prompt_candidate_titles(cor) == ["Film 0", "Dizi 0", "Film 1", "Film 2", "Film 3"]
    assert prompt_candidate_kinds(cor) == ["film", "dizi", "film", "film", "film"]


def test_interleaving_survives_an_empty_tv_result() -> None:
    """tv `discover` boş dönerse havuz yalnızca filmlerden oluşur, hata vermez."""
    tmdb = FakeTMDB(movies=[movie("Dune", "1"), movie("Gattaca", "2")], shows=[])
    cor = FakeCor(picks("Dune"))

    (suggestion,) = recommend("bilim kurgu", [], tmdb, cor)

    assert suggestion["kind"] == "film"
    assert prompt_candidate_kinds(cor) == ["film", "film"]


def test_interleaving_filters_existing_titles_before_the_cap() -> None:
    """`existing_titles` elemesi harmanlanmadan SONRA, kırpma yapılmadan önce.

    Yani elenen bir aday, diğerlerinin sırasını kaydırıp 15'lik sınırda boş
    yer bırakmamalı — sınırın içi hep dolu kalmalı.
    """
    tmdb = FakeTMDB(
        movies=[movie(f"Film {i}", str(i)) for i in range(4)],
        shows=[series(f"Dizi {i}", str(100 + i)) for i in range(4)],
    )
    cor = FakeCor(picks("Dizi 3"))

    recommend("dram", ["Film 0", "Dizi 0"], tmdb, cor)

    assert prompt_candidate_titles(cor) == [
        "Film 1", "Dizi 1", "Film 2", "Dizi 2", "Film 3", "Dizi 3",
    ]
    assert prompt_candidate_kinds(cor) == ["film", "dizi", "film", "dizi", "film", "dizi"]


def test_recommend_prompt_contains_mood_and_overview() -> None:
    tmdb = FakeTMDB(movies=[movie("Dune", "1", overview="Bir çöl gezegeninde iktidar savaşı.")])
    cor = FakeCor(picks("Dune"))

    recommend("bilim kurgu", [], tmdb, cor)

    prompt = cor.prompts[0]
    assert "bilim kurgu" in prompt
    assert "Bir çöl gezegeninde iktidar savaşı." in prompt
    assert "Dune" in prompt


# --------------------------------------------------------------------- #
# existing_titles filtresi
# --------------------------------------------------------------------- #


def test_recommend_filters_existing_titles() -> None:
    tmdb = FakeTMDB(
        movies=[movie("Dune", "1"), movie("Gattaca", "2")],
        shows=[series("Dark", "3")],
    )
    cor = FakeCor(picks("Dune", "Gattaca", "Dark"))

    result = recommend("bilim kurgu", ["Dune", "dark"], tmdb, cor)

    assert [s["title"] for s in result] == ["Gattaca"]


def test_existing_titles_filter_is_case_insensitive_exact_match() -> None:
    tmdb = FakeTMDB(movies=[movie("Dune", "1"), movie("Dune: Part Two", "2")])
    cor = FakeCor(picks("Dune", "Dune: Part Two"))

    result = recommend("fantastik", ["DUNE"], tmdb, cor)

    # "Dune" elendi; "Dune: Part Two" substring olsa da tam eşleşme değil, kaldı.
    assert [s["title"] for s in result] == ["Dune: Part Two"]


# --------------------------------------------------------------------- #
# cor yanıtının ayrıştırılması
# --------------------------------------------------------------------- #


def test_parses_plain_json_array() -> None:
    tmdb = FakeTMDB(movies=[movie("Dune", "1")])
    cor = FakeCor('[{"title": "Dune", "reason": "Çöl gezegeninde iktidar savaşı."}]')

    (suggestion,) = recommend("bilim kurgu", [], tmdb, cor)

    assert suggestion["reason"] == "Çöl gezegeninde iktidar savaşı."


def test_parses_json_wrapped_in_markdown_code_fence() -> None:
    """cor sık sık yanıtı ```json ... ``` içine sarar — kırpıp yeniden denenmeli."""
    tmdb = FakeTMDB(movies=[movie("Dune", "1")])
    fenced = "```json\n" + picks("Dune") + "\n```"
    cor = FakeCor(fenced)

    (suggestion,) = recommend("bilim kurgu", [], tmdb, cor)

    assert suggestion["title"] == "Dune"


def test_parses_bare_code_fence_without_language() -> None:
    tmdb = FakeTMDB(movies=[movie("Dune", "1")])
    cor = FakeCor("```\n" + picks("Dune") + "\n```")

    (suggestion,) = recommend("bilim kurgu", [], tmdb, cor)

    assert suggestion["title"] == "Dune"


def test_caps_result_at_five_suggestions() -> None:
    tmdb = FakeTMDB(movies=[movie(f"Film {i}", str(i)) for i in range(10)])
    cor = FakeCor(picks(*[f"Film {i}" for i in range(10)]))

    result = recommend("dram", [], tmdb, cor)

    assert len(result) == 5


def test_duplicate_picks_are_collapsed() -> None:
    tmdb = FakeTMDB(movies=[movie("Dune", "1"), movie("Gattaca", "2")])
    cor = FakeCor(picks("Dune", "Dune", "Gattaca"))

    result = recommend("bilim kurgu", [], tmdb, cor)

    assert [s["title"] for s in result] == ["Dune", "Gattaca"]


def test_fabricated_title_is_silently_skipped() -> None:
    """cor'un uydurduğu başlık havuzda yok — sessizce atlanır, listeye giremez."""
    tmdb = FakeTMDB(movies=[movie("Dune", "1"), movie("Gattaca", "2")])
    cor = FakeCor(picks("Dune", "Uydurma Film", "Gattaca"))

    result = recommend("bilim kurgu", [], tmdb, cor)

    assert [s["title"] for s in result] == ["Dune", "Gattaca"]


def test_pick_with_empty_reason_is_kept_with_null() -> None:
    tmdb = FakeTMDB(movies=[movie("Dune", "1")])
    cor = FakeCor('[{"title": "Dune", "reason": "   "}]')

    (suggestion,) = recommend("bilim kurgu", [], tmdb, cor)

    assert suggestion["reason"] is None


# --------------------------------------------------------------------- #
# Hata durumları — sessiz sahte öneri yok
# --------------------------------------------------------------------- #


def test_broken_json_raises() -> None:
    tmdb = FakeTMDB(movies=[movie("Dune", "1")])
    cor = FakeCor("bu bir JSON değil, açıklama metni")

    with pytest.raises(RecommendationError, match="JSON"):
        recommend("bilim kurgu", [], tmdb, cor)


def test_non_array_json_raises() -> None:
    tmdb = FakeTMDB(movies=[movie("Dune", "1")])
    cor = FakeCor('{"title": "Dune", "reason": "tek nesne olmamalı"}')

    with pytest.raises(RecommendationError):
        recommend("bilim kurgu", [], tmdb, cor)


def test_empty_response_raises() -> None:
    tmdb = FakeTMDB(movies=[movie("Dune", "1")])
    cor = FakeCor("   ")

    with pytest.raises(RecommendationError):
        recommend("bilim kurgu", [], tmdb, cor)


def test_empty_json_array_raises() -> None:
    """cor boş liste dönerse sahte öneri uydurmayız."""
    tmdb = FakeTMDB(movies=[movie("Dune", "1")])
    cor = FakeCor("[]")

    with pytest.raises(RecommendationError, match="eşleşmedi"):
        recommend("bilim kurgu", [], tmdb, cor)


def test_all_picks_fabricated_raises() -> None:
    tmdb = FakeTMDB(movies=[movie("Dune", "1")])
    cor = FakeCor(picks("Hiçbiri yok"))

    with pytest.raises(RecommendationError, match="eşleşmedi"):
        recommend("bilim kurgu", [], tmdb, cor)


def test_empty_candidate_pool_raises() -> None:
    with pytest.raises(RecommendationError, match="henüz eklemediğin bir aday bulunamadı"):
        recommend("dram", [], FakeTMDB(), FakeCor("[]"))


def test_candidate_pool_entirely_existing_raises() -> None:
    """Amaç: hem `discover` boş döndüğünde hem de hepsi zaten listedeyken aynı hata."""
    tmdb = FakeTMDB(movies=[movie("Dune", "1")], shows=[series("Dark", "2")])

    with pytest.raises(RecommendationError, match="henüz eklemediğin bir aday bulunamadı"):
        recommend("dram", ["Dune", "dark"], tmdb, FakeCor("[]"))


def test_cor_connection_error_is_wrapped() -> None:
    from app.llm import LLMError

    class ExplodingCor:
        def complete(self, prompt: str) -> str:
            raise LLMError("cor proxy'ye bağlanılamadı: refused")

    tmdb = FakeTMDB(movies=[movie("Dune", "1")])

    with pytest.raises(LLMError):
        recommend("bilim kurgu", [], tmdb, ExplodingCor())


def test_unexpected_cor_error_is_wrapped() -> None:
    class WeirdCor:
        def complete(self, prompt: str) -> str:
            raise RuntimeError("bilinmeyen")

    tmdb = FakeTMDB(movies=[movie("Dune", "1")])

    with pytest.raises(RecommendationError, match="öneri motoruna ulaşılamadı"):
        recommend("bilim kurgu", [], tmdb, WeirdCor())


def test_tmdb_error_propagates() -> None:
    """TMDB hatası recommend() içinde yutulmaz — route 502'ye çevirir."""
    from app.external.tmdb import TMDBError

    tmdb = FakeTMDB(error=TMDBError("TMDB /discover/movie için HTTP 500 döndü"))

    with pytest.raises(TMDBError):
        recommend("dram", [], tmdb, FakeCor("[]"))


# --------------------------------------------------------------------- #
# Prompt
# --------------------------------------------------------------------- #


def test_build_prompt_demands_bare_json() -> None:
    prompt = build_prompt("komedi", [movie("Dune", "1")])

    assert "SADECE bir JSON dizisi" in prompt
    assert "kod bloğu" in prompt
    assert "EN FAZLA 5" in prompt
    assert "Dune" in prompt


def test_build_prompt_labels_series() -> None:
    prompt = build_prompt("dram", [{**series("Dark", "2"), "kind": "dizi"}])

    assert "Dark (dizi)" in prompt
