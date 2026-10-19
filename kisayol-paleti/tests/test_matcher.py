"""kisayol/matcher.py testleri.

`build_items` için gerçek repo klasörleri tmp_path'te kurulur; `filter_items`
tamamen saftır, dosya sistemine dokunmaz.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from kisayol.matcher import build_items, filter_items, format_item


def _make_repo(path: Path) -> Path:
    (path / ".git").mkdir(parents=True)
    return path


def _labels(items) -> list[str]:
    return [i["label"] for i in items]


# --- build_items ---------------------------------------------------------


def test_build_items_returns_config_items(tmp_path):
    config = {"items": [{"label": "kule testleri", "cwd": "~/kule", "command": "pytest"}]}

    items = build_items(config)

    assert _labels(items) == ["kule testleri"]
    assert items[0]["command"] == "pytest"


def test_build_items_merges_discovered_repos(tmp_path):
    repo = _make_repo(tmp_path / "kule")
    config = {
        "items": [{"label": "testler", "cwd": str(tmp_path), "command": "pytest"}],
        "discover_roots": [str(tmp_path)],
    }

    items = build_items(config)

    assert _labels(items) == ["testler", "kule"]
    assert items[1]["cwd"] == str(repo)


def test_build_items_config_item_wins_over_discovered_same_cwd(tmp_path):
    """Aynı cwd'de iki item varsa config'teki kazanır, ikinci kez listelenmez."""
    repo = _make_repo(tmp_path / "kule")
    config = {
        "items": [{"label": "kule testlerini çalıştır", "cwd": str(repo), "command": "pytest"}],
        "discover_roots": [str(tmp_path)],
    }

    items = build_items(config)

    assert _labels(items) == ["kule testlerini çalıştır"]
    assert items[0]["command"] == "pytest"


def test_build_items_keeps_several_commands_for_one_repo(tmp_path):
    """Aynı repoda birden fazla komut — aracın ana kullanımı, hepsi kalmalı."""
    cwd = str(tmp_path)
    config = {
        "items": [
            {"label": "kule sunucusunu başlat", "cwd": cwd, "command": "uvicorn"},
            {"label": "kule testlerini çalıştır", "cwd": cwd, "command": "pytest"},
        ]
    }

    assert _labels(build_items(config)) == [
        "kule sunucusunu başlat",
        "kule testlerini çalıştır",
    ]


def test_build_items_equivalent_paths_dedupe_against_discovery(tmp_path):
    """`/a/b`, `/a/b/` ve `/a/./b` aynı repo sayılır: keşif onu ikinci kez eklemez."""
    repo = _make_repo(tmp_path / "kule")
    config = {
        "items": [
            {"label": "noktalı", "cwd": str(repo), "command": "a"},
            {"label": "sondaki-slash", "cwd": str(repo) + "/", "command": "b"},
            {"label": "nokta", "cwd": str(repo / "."), "command": "c"},
        ],
        "discover_roots": [str(tmp_path)],
    }

    assert _labels(build_items(config)) == ["noktalı", "sondaki-slash", "nokta"]


def test_build_items_keeps_items_without_cwd(tmp_path):
    config = {
        "items": [
            {"label": "saat", "command": "date"},
            {"label": "ses", "command": "say hi"},
        ]
    }

    assert _labels(build_items(config)) == ["saat", "ses"]


def test_build_items_normalizes_missing_fields(tmp_path):
    config = {"items": [{"label": "kule", "cwd": "~/kule"}], "discover_roots": []}

    item = build_items(config)[0]

    assert item["label"] == "kule"
    assert item["command"]  # eksik komut için kabuk fallback'i
    assert item["tags"] == []


def test_build_items_label_falls_back_to_cwd_basename(tmp_path):
    config = {
        "items": [
            {"cwd": "~/kule", "command": "true"},
            {"label": "~", "cwd": "~/baska-proje"},
            {"label": "", "cwd": "/tmp/notlar"},
        ]
    }

    assert _labels(build_items(config)) == ["kule", "baska-proje", "notlar"]


def test_build_items_tolerates_garbage_config(tmp_path):
    assert build_items({}) == []
    assert build_items({"items": "olmayan", "discover_roots": "x"}) == []


def test_build_items_discover_roots_none(tmp_path):
    """discover_roots: null (YAML'da boş) patlama yaratmamalı."""
    config = {"items": [{"label": "a", "cwd": "/x", "command": "true"}], "discover_roots": None}

    assert _labels(build_items(config)) == ["a"]


# --- filter_items ---------------------------------------------------------


@pytest.fixture
def items() -> list[dict]:
    return [
        {"label": "kule sunucusunu başlat", "cwd": "/a", "command": "uvicorn", "tags": ["server"]},
        {"label": "kule testlerini çalıştır", "cwd": "/a", "command": "pytest", "tags": ["test"]},
        {"label": "kisayol paleti", "cwd": "/b", "command": "kp", "tags": []},
        {"label": "notlar", "cwd": "/c", "command": "vim", "tags": ["notlar"]},
    ]


def test_filter_items_empty_query_returns_all(items):
    assert filter_items(items, "") == items
    assert filter_items(items, "   ") == items


def test_filter_items_exact_substring(items):
    assert filter_items(items, "kule") == items[:2]


def test_filter_items_is_case_insensitive(items):
    assert _labels(filter_items(items, "KULE")) == ["kule sunucusunu başlat", "kule testlerini çalıştır"]


def test_filter_items_exact_label_ranks_first(items):
    assert _labels(filter_items(items, "notlar"))[0] == "notlar"


def test_filter_items_fuzzy_subsequence(items):
    assert "kule sunucusunu başlat" in _labels(filter_items(items, "ksb"))


def test_filter_items_reranks_by_relevance(items):
    """'kule' ikisinde de geçiyor ama tam 'kule' etiketli olan önde."""
    scored = [
        {"label": "kule", "cwd": "/a", "command": "true", "tags": []},
        {"label": "kule sunucusunu başlat", "cwd": "/a", "command": "uvicorn", "tags": []},
    ]

    assert _labels(filter_items(scored, "kule")) == ["kule", "kule sunucusunu başlat"]


def test_filter_items_matches_tags(items):
    assert _labels(filter_items(items, "test")) == ["kule testlerini çalıştır"]
    assert _labels(filter_items(items, "server")) == ["kule sunucusunu başlat"]


def test_filter_items_matches_command(items):
    assert "kisayol paleti" in _labels(filter_items(items, "kp"))


def test_filter_items_no_match_returns_empty(items):
    assert filter_items(items, "zzzqqq") == []


def test_filter_items_is_deterministic(items):
    once = _labels(filter_items(items, "kule"))
    twice = _labels(filter_items(items, "kule"))

    assert once == twice


def test_filter_items_does_not_mutate_input(items):
    before = [dict(i) for i in items]

    filter_items(items, "kule")

    assert items == before


def test_filter_items_empty_input():
    assert filter_items([], "kule") == []


# --- format_item ----------------------------------------------------------


def test_format_item_starts_with_label_for_grepping():
    line = format_item({"label": "kule testleri", "cwd": "/a", "command": "pytest", "tags": ["test"]})

    assert line.startswith("kule testleri")
    assert "pytest" in line
    assert "test" in line


def test_format_item_omits_empty_fields():
    line = format_item({"label": "kule", "cwd": "/a", "command": "true", "tags": []})

    assert line == "kule · true"


def test_format_item_preserves_original_casing_of_command():
    """`--list` ne çalıştıracağını olduğu gibi göstermeli: $EDITOR küçülmez."""
    line = format_item({"label": "not", "cwd": "/a", "command": "$EDITOR", "tags": []})

    assert line == "not · $EDITOR"
