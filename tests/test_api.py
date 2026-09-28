def test_get_items_empty(client):
    res = client.get("/api/items")
    assert res.status_code == 200
    assert res.json() == {"items": []}


def test_create_item_defaults_status_to_planlanan(client):
    res = client.post("/api/items", json={"title": "Dune", "kind": "film"})
    assert res.status_code == 201
    body = res.json()
    assert body["title"] == "Dune"
    assert body["status"] == "planlanan"
    assert body["rating"] is None


def test_create_item_blank_title_422(client):
    res = client.post("/api/items", json={"title": "   ", "kind": "film"})
    assert res.status_code == 422
    assert isinstance(res.json()["detail"], str)


def test_create_item_invalid_kind_422(client):
    res = client.post("/api/items", json={"title": "X", "kind": "belgesel"})
    assert res.status_code == 422


def test_create_item_invalid_rating_422(client):
    res = client.post("/api/items", json={"title": "X", "kind": "film", "rating": 9})
    assert res.status_code == 422


def test_list_items_filter_by_kind(client):
    client.post("/api/items", json={"title": "Dune", "kind": "film"})
    client.post("/api/items", json={"title": "Arcane", "kind": "dizi"})
    res = client.get("/api/items?kind=dizi")
    assert res.status_code == 200
    items = res.json()["items"]
    assert [i["title"] for i in items] == ["Arcane"]


def test_list_items_invalid_kind_query_422(client):
    res = client.get("/api/items?kind=belgesel")
    assert res.status_code == 422


def test_list_items_search(client):
    client.post("/api/items", json={"title": "Dune", "kind": "film"})
    client.post("/api/items", json={"title": "Arcane", "kind": "dizi"})
    res = client.get("/api/items?q=dun")
    assert [i["title"] for i in res.json()["items"]] == ["Dune"]


def test_patch_item_updates_only_given_fields(client):
    created = client.post("/api/items", json={"title": "Dune", "kind": "film"}).json()
    res = client.patch(f"/api/items/{created['id']}", json={"status": "tamamlandi", "rating": 4})
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "tamamlandi"
    assert body["rating"] == 4
    assert body["title"] == "Dune"


def test_patch_item_missing_404(client):
    res = client.patch("/api/items/999", json={"rating": 3})
    assert res.status_code == 404


def test_patch_item_invalid_status_422(client):
    created = client.post("/api/items", json={"title": "Dune", "kind": "film"}).json()
    res = client.patch(f"/api/items/{created['id']}", json={"status": "izlendi"})
    assert res.status_code == 422


def test_delete_item_removes_it(client):
    created = client.post("/api/items", json={"title": "Dune", "kind": "film"}).json()
    res = client.delete(f"/api/items/{created['id']}")
    assert res.status_code == 204
    assert client.get("/api/items").json()["items"] == []


def test_delete_item_missing_404(client):
    res = client.delete("/api/items/999")
    assert res.status_code == 404


def test_index_page_serves_html(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "Ne İzlesem" in res.text


# --------------------------------------------------------------------- #
# Faz B: dış veri alanları (Faz A davranışı bozulmadan)
# --------------------------------------------------------------------- #


def test_create_item_without_external_fields(client):
    """Faz A davranışı: dış alanlar verilmeden de eklenebilmeli."""
    res = client.post("/api/items", json={"title": "Dune", "kind": "film"})
    body = res.json()
    assert body["poster_url"] is None
    assert body["external_source"] is None
    assert body["external_id"] is None


def test_create_item_stores_external_fields(client):
    res = client.post(
        "/api/items",
        json={
            "title": "Dune",
            "kind": "film",
            "poster_url": "https://image.tmdb.org/t/p/w342/a.jpg",
            "external_source": "tmdb",
            "external_id": "438631",
        },
    )
    body = res.json()
    assert res.status_code == 201
    assert body["external_source"] == "tmdb"
    assert body["external_id"] == "438631"
    assert body["poster_url"] == "https://image.tmdb.org/t/p/w342/a.jpg"


def test_create_kitap_item_with_openlibrary_fields(client):
    res = client.post(
        "/api/items",
        json={
            "title": "Dune",
            "kind": "kitap",
            "external_source": "openlibrary",
            "external_id": "/works/OL12345W",
        },
    )
    assert res.status_code == 201
    assert res.json()["external_id"] == "/works/OL12345W"


def test_patch_item_updates_external_fields(client):
    created = client.post("/api/items", json={"title": "Dune", "kind": "film"}).json()

    res = client.patch(
        f"/api/items/{created['id']}",
        json={"external_source": "tmdb", "external_id": "438631", "poster_url": "https://x/a.jpg"},
    )

    assert res.status_code == 200
    body = res.json()
    assert body["external_source"] == "tmdb"
    assert body["external_id"] == "438631"
    assert body["title"] == "Dune"
