# ne-izlesem

Film/dizi/anime/kitap takip listesi + kişisel bir web pano — kurulumsuz,
tek kullanıcılık. FastAPI + SQLite backend, vanilla JS + Jinja2 frontend.

## Kurulum ve çalıştırma

```bash
pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

Tarayıcıda `http://127.0.0.1:8000` açılır. Veriler `data/ne-izlesem.db`
(SQLite, `.gitignore`'da) dosyasında tutulur.

## Kullanım

- Üstteki formdan başlık + tür (film/dizi/anime/kitap) + durum
  (planlanan/izleniyor/tamamlandı/bırakıldı) seçip ekle.
- Kartlar üzerinde: durumu değiştir, 1-5 yıldız ver, not düş — hepsi
  sayfa yenilenmeden anında kaydedilir.
- Üstteki çipler ve arama kutusuyla tür/durum/başlığa göre filtrele.

## Test

```bash
pip install -r requirements-dev.txt
pytest
```

24 test: `app/db.py`'nin CRUD/filtre/arama mantığı gerçek SQLite ile
(`tmp_path`, mock yok), `app/routes/items.py`'nin tüm uç noktaları
FastAPI `TestClient` ile (doğrulama hataları, 404'ler dahil).

## Mimari

- `app/db.py` — SQLite şeması + CRUD yardımcıları.
- `app/routes/items.py` — `/api/items` CRUD uç noktaları (Pydantic doğrulama).
- `app/main.py` — FastAPI app, static/template bağlama, `GET /`.
- `app/templates/`, `app/static/` — SPA tarzı tek sayfa arayüz (framework yok).
- `docs/API.md` — tam API sözleşmesi.

## Yol haritası

- **Faz B**: TMDB (film/dizi) + Open Library (kitap) API entegrasyonu —
  başlık arama, poster/kapak, TMDB'nin resmi "nerede izlenir" verisiyle
  (Netflix, Prime Video, vb.) lisanslı platform linkleri.
- **Faz C**: Ruh haline göre öneri motoru (cor üzerinden LLM, TMDB aday
  havuzu, zaten eklenenleri eleme).

Not: korsan içerik barındıran sitelere (fullhdfilmcehennemi, animecix vb.)
otomatik link üretme özelliği bilinçli olarak kapsam dışı bırakıldı.
