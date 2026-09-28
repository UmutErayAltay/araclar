from app.db import (
    create_item,
    delete_item,
    get_connection,
    get_item,
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
