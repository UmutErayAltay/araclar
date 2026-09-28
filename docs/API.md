# API sözleşmesi — Faz A (çekirdek + web arayüzü)

Backend (`app/main.py`, `app/db.py`, `app/routes/items.py`) ile frontend
(`app/templates/`, `app/static/`) bu sözleşmeye göre paralel geliştirilir.
Frontend sadece bu sözleşmeye dokunur, backend'in .py dosyalarına dokunmaz;
backend sadece .py dosyalarına dokunur, template/static dosyalarına dokunmaz.

## Veri modeli — `Item`

| Alan | Tip | Zorunlu | Not |
| --- | --- | --- | --- |
| `id` | int | sunucu üretir | autoincrement |
| `title` | str | evet | boş olamaz |
| `kind` | str | evet | `"film" \| "dizi" \| "anime" \| "kitap"` |
| `status` | str | evet | `"planlanan" \| "izleniyor" \| "tamamlandi" \| "birakildi"`, varsayılan `"planlanan"` |
| `rating` | int veya null | hayır | 1-5, aralık dışıysa 422 |
| `note` | str veya null | hayır | serbest metin |
| `created_at` | str (ISO 8601) | sunucu üretir | |
| `updated_at` | str (ISO 8601) | sunucu üretir | her PATCH'te güncellenir |

## Uç noktalar

- `GET /api/items?kind=&status=&q=` → `{"items": [Item, ...]}`
  `kind`/`status` verilirse tam eşleşme filtresi, `q` verilirse `title` üzerinde
  case-insensitive substring arama. Hepsi opsiyonel, birlikte de kullanılabilir.
  Sonuç `updated_at` DESC sıralı (en son dokunulan en üstte).
- `POST /api/items` gövde `{"title", "kind", "status"?, "rating"?, "note"?}`
  → 201 + oluşan `Item`. `title` boşsa veya `kind`/`status` geçersiz bir
  değerse 422 + `{"detail": "..."}`.
- `PATCH /api/items/{id}` gövde — güncellenecek alanların HERHANGİ BİR ALT
  KÜMESİ (`title`, `kind`, `status`, `rating`, `note`) → 200 + güncel `Item`.
  Id yoksa 404. Geçersiz `status`/`kind`/`rating` yine 422.
- `DELETE /api/items/{id}` → 204. Id yoksa 404.
- `GET /` → `app/templates/index.html` render eder (sunucu tarafında veri
  gömülmez, sayfa açılışta `GET /api/items` çağırır — SPA tarzı, tam sayfa
  yenilemeden ekleme/silme/durum değişikliği yapılabilir).

## Hata biçimi

Her hata gövdesi `{"detail": "insan-okunur Türkçe mesaj"}`. FastAPI'nin
varsayılan `HTTPException` biçimini kullan, özel bir zarf uydurma.

## Depolama

SQLite, dosya yolu `data/ne-izlesem.db` (proje köküne göre, `data/` zaten
`.gitignore`'da). Tablo adı `items`. Bağlantı `app/db.py` içinde tek bir
yerden açılıp kapatılır; test'ler ayrı bir geçici dosya/`:memory:` kullanır,
gerçek dosyayı asla kirletmez.

## Arayüz beklentisi ("güzel bir arayüz")

- Üstte hızlı ekleme formu (başlık + tür seçici + durum seçici) — tek satır,
  form gönderiminde sayfa yenilenmeden `POST /api/items` çağrılır ve liste
  güncellenir.
- Tür ve durum için tıklanabilir filtre çipleri + serbest metin arama kutusu.
- Kartlar grid halinde: başlık, tür rozeti, durum rozeti (renk kodlu),
  1-5 yıldız (tıklanabilir, `PATCH` tetikler), not alanı (inline düzenlenebilir),
  sil butonu (onaysız — tek kullanıcılık kişisel araç, kule/kısayol-paleti'nde
  de aynı yaklaşım var).
- Responsive: dar ekranda kartlar tek sütuna düşsün.
- Boş liste durumunda "henüz bir şey eklemedin" tarzı boş durum mesajı.
