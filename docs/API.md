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

# Faz B — dış veri (TMDB + Open Library) + legal "nerede izlerim"

Faz A'nın üzerine eklenir, mevcut sözleşmeyi BOZMAZ (geriye dönük uyumlu).
Aynı dosya-sahipliği kuralı geçerli: backend sadece `.py`, frontend sadece
`app/templates/` + `app/static/`.

## `Item` — yeni alanlar (hepsi opsiyonel, hepsi null olabilir)

| Alan | Tip | Not |
| --- | --- | --- |
| `poster_url` | str veya null | TMDB poster ya da Open Library kapak görseli |
| `external_source` | str veya null | `"tmdb" \| "openlibrary"` |
| `external_id` | str veya null | TMDB id (film/dizi/anime) ya da Open Library work key (kitap) |

`POST /api/items` ve `PATCH /api/items/{id}` artık bu üç alanı da kabul
eder, zorunlu değildir — kullanıcı arama sonucundan seçmeden de elle
başlık yazıp ekleyebilir (Faz A davranışı hâlâ geçerli).

## Yeni backend modülleri

- `app/external/tmdb.py` — `TMDBClient` sınıfı. Kurucu `api_key`
  (zorunlu, yoksa `TMDBNotConfiguredError` fırlatır — sessiz sahte
  sonuç YOK), `base_url` (varsayılan `https://api.themoviedb.org/3`,
  test'lerde fake bir yerel `http.server`'a çevrilebilir), `timeout`.
  Metodlar: `search(query, media_type)` (`media_type`: `"movie"` veya
  `"tv"`) → `[{title, year, poster_url, external_id, overview}, ...]`
  (TMDB `/search/movie` veya `/search/tv`, poster_url
  `https://image.tmdb.org/t/p/w342{poster_path}` şeklinde kurulur,
  `poster_path` null ise `poster_url` de null). `watch_providers(media_type,
  tmdb_id, region)` → `[{provider_name, logo_url, link}, ...]` (TMDB
  `/{media_type}/{id}/watch/providers`, `region` koduna göre `flatrate`
  sağlayıcıları — `buy`/`rent` DAHİL ETME, sadece abonelik/flatrate;
  o bölgede veri yoksa boş liste döndür, hata değil). HTTP/JSON hatalarında
  `TMDBError` fırlat, koşulsuz boş liste dönme.
- `app/external/openlibrary.py` — `OpenLibraryClient` sınıfı, API key
  GEREKMEZ. `search(query)` → `[{title, author, year, poster_url,
  external_id}, ...]` (Open Library `/search.json?q=...`, kapak
  `https://covers.openlibrary.org/b/id/{cover_i}-M.jpg`, `external_id`
  = `key` alanı, örn. `/works/OL12345W`). Aynı hata deseni: `OpenLibraryError`.

## Yeni uç noktalar

- `GET /api/search?kind=&q=` → `{"results": [...]}`. `kind` zorunlu
  (`film`/`dizi`/`anime` → TMDB, `anime` ve `film` `media_type="movie"`,
  `dizi` `media_type="tv"`; `kitap` → Open Library). `q` zorunlu, boşsa
  422. TMDB için `TMDB_API_KEY` ortam değişkeni yoksa 503 +
  `{"detail": "TMDB_API_KEY ayarlanmamış"}` — sahte/boş sonuç DÖNME.
  Her sonuç nesnesine sunucu tarafında `external_source` (`"tmdb"` veya
  `"openlibrary"`) eklenir — frontend `POST/PATCH /api/items`'a bunu
  doğrudan taşır; eklenmezse `Item.external_source` hep null kalır ve
  `/watch` hep 404 döner (bu Faz B'nin ilk sürümünde gerçekten yaşanan
  bir hataydı, testle sabitlendi).
- `GET /api/items/{id}/watch?region=` → `{"providers": [...]}`.
  `region` opsiyonel, varsayılan ortam değişkeni `WATCH_REGION`
  (varsayılan `"TR"`). Öğenin `kind`i `kitap` ise veya `external_id`/
  `external_source` boşsa 404 + açıklayıcı mesaj (kitaba "nerede
  izlerim" anlamsız, sessizce boş liste dönme — kullanıcı neden
  olmadığını bilsin). `TMDB_API_KEY` yoksa yine 503.

## Test beklentisi

`app/external/tmdb.py` ve `app/external/openlibrary.py` gerçek bir
yerel `http.server` sahte sunucusuna karşı test edilir (anlat/bridge
projesindeki desenin aynısı — `unittest.mock` YOK). Gerçek TMDB/Open
Library ağına giden testler `@pytest.mark.integration` ile işaretlenir
ve varsayılan çalıştırmada atlanır (repo'da henüz gerçek bir
`TMDB_API_KEY` yok — kullanıcı kendi anahtarını themoviedb.org'dan
alıp ortam değişkeni olarak eklemeli, bu Faz'ın bilinen açık ucu).

## Arayüz beklentisi

- Ekleme formundaki başlık kutusuna yazarken (debounce ~300ms) açılır
  bir arama sonucu listesi (`GET /api/search`) — küçük poster + başlık
  + yıl. Bir sonuca tıklanınca form alanları (title, poster_url,
  external_source, external_id) otomatik doldurulur; kullanıcı yine de
  elle yazıp Enter'a basarak dış aramaya hiç dokunmadan da ekleyebilir
  (Faz A davranışı kaybolmaz).
- Kartlarda `poster_url` varsa küçük bir kapak görseli (yoksa mevcut
  metin-only kart tasarımı aynen kalır).
- Kartlarda, `external_id` dolu ve `kind != kitap` olan öğelerde
  "Nerede izlerim?" butonu → tıklanınca `GET /api/items/{id}/watch`
  çağrılır, dönen sağlayıcılar (Netflix, Prime Video, vb.) logo +
  link olarak kart içinde/altında gösterilir. Sağlayıcı yoksa
  "bu bölgede bir abonelik seçeneği bulunamadı" mesajı.
- `TMDB_API_KEY` yokluğundan gelen 503'ler kullanıcıya net bir mesajla
  gösterilir (mevcut toast mekanizması yeterli), sayfa çökmez.

# Faz C — ruh haline göre öneri motoru

## Yeni backend modülü

- `app/external/tmdb.py`'ye YENİ bir metod eklenir (mevcut `search`/
  `watch_providers`'a dokunma): `discover(media_type: str, genre_id: int,
  page: int = 1) -> list[dict]` → `/discover/{media_type}` (`with_genres`,
  `language=tr-TR`, `sort_by=popularity.desc`), dönüş şekli `search()` ile
  AYNI (`{title, year, poster_url, external_id, overview}`). Aynı hata
  deseni (`TMDBError`), aynı `limit`/kırpma yaklaşımı yok (aday havuzu
  için TMDB'nin varsayılan sayfa boyutu — genelde 20 — yeterli).
- `app/recommend.py` — sabit bir `MOOD_GENRE_MAP` sözlüğü (anahtar:
  küçük harf Türkçe ruh hali kelimesi, değer: `{"movie": genre_id,
  "tv": genre_id}`). Aşağıdaki tabloyu BİREBİR kullan (TMDB'nin resmi
  genre id'leri, uydurma):

  | Anahtar kelimeler (girişte substring arar) | movie genre_id | tv genre_id |
  | --- | --- | --- |
  | hafif, eğlenceli, rahatlatıcı, komedi | 35 (Comedy) | 35 (Comedy) |
  | gerilim, heyecan, gizem | 53 (Thriller) | 9648 (Mystery) |
  | korku | 27 (Horror) | 9648 (Mystery) |
  | romantik, aşk | 10749 (Romance) | 18 (Drama) |
  | aksiyon | 28 (Action) | 10759 (Action & Adventure) |
  | bilim kurgu, fantastik, uzay | 878 (Science Fiction) | 10765 (Sci-Fi & Fantasy) |
  | duygusal, ağlatan, dram | 18 (Drama) | 18 (Drama) |
  | aile, çocuk | 10751 (Family) | 10751 (Family) |
  | (eşleşme yoksa varsayılan) | 18 (Drama) | 18 (Drama) |

  Eşleştirme: `mood.lower()` içinde yukarıdaki anahtar kelimelerden biri
  substring olarak geçiyorsa o satır kullanılır (ilk eşleşen kazanır,
  sırayı tablodaki gibi koru); hiçbiri geçmiyorsa varsayılan (Drama)
  satırı kullanılır — asla "eşleşme yok" diye hata verme, her zaman bir
  aday havuzu üretilebilmeli.

  `recommend(mood: str, existing_titles: list[str], tmdb_client,
  cor_client) -> list[dict]`. Akış: `MOOD_GENRE_MAP`'ten genre_id'leri
  bul, `tmdb_client.discover("movie", movie_genre_id)` VE
  `tmdb_client.discover("tv", tv_genre_id)` ile aday havuzu kur — SIRAYLA
  HARMANLA (`movie[0], tv[0], movie[1], tv[1], ...`, biri biterse
  diğerinden devam), ARDIŞIK BİRLEŞTİRME (önce tüm movie, sonra tüm tv)
  YAPMA — movie sayfası tek başına 15'lik sınırı doldurup tv'yi hiç
  LLM'e ulaştırmayabilir. movie sonuçlarına `kind="film"`, tv sonuçlarına
  `kind="dizi"` etiketi ekle. Harmanlanmış havuzdan `existing_titles`'ta
  (case-insensitive tam eşleşme) olanları ele. Kalan adaylardan (en fazla
  ilk 15'i cor'a gönder — tüm havuzu değil, prompt'u şişirme) cor
  üzerinden (bkz. `app/llm.py`) en
  fazla 5 tanesini seçtirip her biri için tek cümlelik Türkçe gerekçe
  üretilir. Aday havuzu boşsa (her iki discover de boş VEYA hepsi
  `existing_titles`'ta) `RecommendationError("bu ruh haline uygun,
  henüz eklemediğin bir aday bulunamadı")` fırlat. cor boş/bozuk cevap
  dönerse yine `RecommendationError` — sessizce sahte/boş öneri UYDURMA.

- `app/llm.py` — `anlat` projesindeki `generator/narrator.py::CorLLMClient`
  ile AYNI desen (stdlib `urllib`, `POST {COR_BASE_URL}/v1/messages`,
  retry SADECE 5xx'te, `LLMClient` Protocol ile test'te sahte istemci
  enjekte edilebilir). `COR_BASE_URL` ortam değişkeni (varsayılan
  `http://127.0.0.1:8787`), `COR_MODEL` (varsayılan
  `stealth/space-bunny-alpha`).

  Prompt sözleşmesi: `recommend()` cor'a adayların `title` + `overview`
  (varsa) listesini ve kullanıcının ruh halini vererek, YANITIN
  SADECE bir JSON dizisi olmasını iste (kod bloğu/açıklama YOK):
  `[{"title": "<adaylardan birebir bir başlık>", "reason": "<tek cümle
  Türkçe gerekçe>"}, ...]`, en fazla 5 eleman. `recommend()` bu JSON'u
  ayrıştırır (markdown kod bloğu ile sarılmışsa \`\`\` işaretlerini
  kırpıp yine dener), her `title`'ı aday havuzuyla eşleştirir (birebir
  eşleşmeyeni SESSİZCE ATLA, uydurma başlık ekleme), sonucu adayın
  `kind`/`poster_url`/`external_id`/`external_source` alanlarıyla
  birleştirip döner. JSON ayrıştırılamazsa veya eşleşen hiçbir aday
  kalmazsa `RecommendationError`.

## Yeni uç nokta

- `GET /api/recommend?mood=` → `{"suggestions": [{"title", "kind",
  "reason", "external_source", "external_id", "poster_url"}, ...]}`.
  `mood` zorunlu, boşsa 422. `TMDB_API_KEY` yoksa 503. cor'a
  ulaşılamazsa 502 + `{"detail": "öneri motoruna ulaşılamadı"}`
  (sessiz boş liste YOK).

## Test beklentisi

`app/recommend.py` sahte bir `tmdb_client` (Protocol/duck-typing,
gerçek TMDB'ye gitmeden) VE sahte bir `cor_client` (anlat'taki
`LLMClient` Protocol deseninin aynısı) ile test edilir — gerçek cor
bağlantısı gerektiren tek bir test `@pytest.mark.integration` ile
işaretlenir.

## Arayüz beklentisi

- Üstte ikinci bir hızlı form: "Ruh halin ne?" serbest metin kutusu +
  "Öner" butonu → `GET /api/recommend` çağrılır, sonuçlar ayrı bir
  "Öneriler" bölümünde (kartlardan görsel olarak ayrışan, ör. hafif
  farklı arka plan) gösterilir — her öneri kartında başlık, poster,
  gerekçe cümlesi, ve tek tıkla mevcut listeye ekleme butonu (`POST
  /api/items`, `status="planlanan"`).
- Yükleniyor durumu (öneri motoru birkaç saniye sürebilir) net bir
  şekilde gösterilir, sayfa donmuş gibi hissettirmez.
