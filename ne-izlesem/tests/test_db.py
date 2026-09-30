import sqlite3

from app.db import (
    create_item,
    delete_item,
    get_connection,
    get_item,
    init_db,
    list_items,
    update_item,
)


def test_create_and_get_item(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    item = create_item(conn, title="Dune", kind="film", status="planlanan")
    assert item["id"] is not None
    assert item["title"] == "Dune"
    assert item["status"] == "planlanan"
    assert item["created_at"] == item["updated_at"]
    assert get_item(conn, item["id"]) == item


def test_get_item_missing_returns_none(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    assert get_item(conn, 999) is None


def test_list_items_filters_by_kind_and_status(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    create_item(conn, title="Dune", kind="film", status="planlanan")
    create_item(conn, title="Arcane", kind="dizi", status="izleniyor")
    create_item(conn, title="Duna Kitabı", kind="kitap", status="planlanan")

    assert len(list_items(conn)) == 3
    films = list_items(conn, kind="film")
    assert [i["title"] for i in films] == ["Dune"]
    planlanan = list_items(conn, status="planlanan")
    assert len(planlanan) == 2


def test_list_items_search_is_case_insensitive_substring(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    create_item(conn, title="Dune", kind="film", status="planlanan")
    create_item(conn, title="Duna Kitabı", kind="kitap", status="planlanan")
    create_item(conn, title="Arcane", kind="dizi", status="izleniyor")

    results = list_items(conn, q="DUN")
    assert {r["title"] for r in results} == {"Dune", "Duna Kitabı"}


def test_list_items_search_escapes_sql_wildcards(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    create_item(conn, title="100% Wolf", kind="anime", status="planlanan")
    create_item(conn, title="Normal Show", kind="dizi", status="planlanan")

    results = list_items(conn, q="100%")
    assert [r["title"] for r in results] == ["100% Wolf"]


def test_list_items_ordered_by_updated_at_desc(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    first = create_item(conn, title="A", kind="film", status="planlanan")
    create_item(conn, title="B", kind="film", status="planlanan")
    update_item(conn, first["id"], note="güncellendi")

    items = list_items(conn)
    assert items[0]["id"] == first["id"]


def test_update_item_changes_fields_and_updated_at(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    item = create_item(conn, title="Dune", kind="film", status="planlanan")
    updated = update_item(conn, item["id"], rating=5, status="tamamlandi")
    assert updated["rating"] == 5
    assert updated["status"] == "tamamlandi"
    assert updated["title"] == "Dune"
    assert updated["updated_at"] >= item["updated_at"]


def test_update_item_missing_returns_none(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    assert update_item(conn, 999, rating=3) is None


def test_delete_item_removes_row(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    item = create_item(conn, title="Dune", kind="film", status="planlanan")
    assert delete_item(conn, item["id"]) is True
    assert get_item(conn, item["id"]) is None


def test_delete_item_missing_returns_false(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    assert delete_item(conn, 999) is False


# --------------------------------------------------------------------- #
# Faz B: dış veri kolonları ve idempotent göç
# --------------------------------------------------------------------- #


def _columns(conn) -> set[str]:
    return {row["name"] for row in conn.execute("PRAGMA table_info(items)")}


def _create_faz_a_db(path) -> None:
    """Faz A sözleşmesindeki (dış kolonları olmayan) tabloyu kuran yardımcı."""
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            kind TEXT NOT NULL,
            status TEXT NOT NULL,
            rating INTEGER,
            note TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "INSERT INTO items (title, kind, status, created_at, updated_at) "
        "VALUES ('Eski Film', 'film', 'planlanan', '2026-01-01T00:00:00+00:00', "
        "'2026-01-01T00:00:00+00:00')"
    )
    conn.commit()
    conn.close()


def test_init_db_adds_external_columns_to_fresh_db(tmp_path):
    conn = get_connection(tmp_path / "yeni.db")
    assert {"poster_url", "external_source", "external_id"} <= _columns(conn)


def test_init_db_migrates_faz_a_database(tmp_path):
    """Faz A'dan kalan DB dosyası dış kolonlarla genişletilmeli, veri korunmalı."""
    path = tmp_path / "eski.db"
    _create_faz_a_db(path)

    conn = get_connection(path)
    try:
        assert {"poster_url", "external_source", "external_id"} <= _columns(conn)
        item = get_item(conn, 1)
        assert item["title"] == "Eski Film"
        assert item["poster_url"] is None
        assert item["external_source"] is None
        assert item["external_id"] is None
    finally:
        conn.close()


def test_init_db_migration_is_idempotent(tmp_path):
    """Göç ikinci kez çalıştığında hata vermemeli, kolon çoğalmamalı."""
    path = tmp_path / "eski.db"
    _create_faz_a_db(path)

    for _ in range(3):
        conn = get_connection(path)
        conn.close()

    conn = get_connection(path)
    try:
        names = [row["name"] for row in conn.execute("PRAGMA table_info(items)")]
        assert names.count("poster_url") == 1
        assert names.count("external_source") == 1
        assert names.count("external_id") == 1
    finally:
        conn.close()


def test_create_item_stores_external_fields(tmp_path):
    conn = get_connection(tmp_path / "t.db")

    item = create_item(
        conn,
        title="Dune",
        kind="film",
        poster_url="https://image.tmdb.org/t/p/w342/a.jpg",
        external_source="tmdb",
        external_id="438631",
    )

    assert item["poster_url"] == "https://image.tmdb.org/t/p/w342/a.jpg"
    assert item["external_source"] == "tmdb"
    assert item["external_id"] == "438631"


def test_create_item_external_fields_default_to_none(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    item = create_item(conn, title="Dune", kind="film")

    assert item["poster_url"] is None
    assert item["external_source"] is None
    assert item["external_id"] is None


def test_update_item_changes_external_fields(tmp_path):
    conn = get_connection(tmp_path / "t.db")
    item = create_item(conn, title="Dune", kind="film")

    updated = update_item(conn, item["id"], external_id="438631", external_source="tmdb")

    assert updated["external_id"] == "438631"
    assert updated["external_source"] == "tmdb"
