# araclar

Yerel **cor** proxy'sine (`POST /v1/messages`) konuşan küçük Python araçlarının tek
deposu. Ortak parça, hepsinin kullandığı **tek LLM istemcisidir** (`corclient.py`);
araçlar bu istemciyi kendi paketlerine senkronlanan bir kopya olarak taşır.

> Not: Bu depo önceki adıyla `corclient` idi; adı `araclar` oldu (eski bağlantılar GitHub'da
> yönlenir). `corclient.py` ortak istemci modülünün adıdır ve değişmedi. Eski ayrı repolar
> (`atlas`, `harita`, `orkestra`, `danis`, `anlat`) boşaltıldı; kod artık burada, klasörlerinde.

## İçindekiler

| Klasör | Ne işe yarar |
|---|---|
| `corclient.py`, `tools/`, `tests/` | Ortak cor istemcisi (tek kaynak) + senkron aracı + bunların testleri |
| `atlas/` | Repo sağlık atlası: git repolarını tarar, yarım iş / bayat README / sızıntı bulgularını gösterir |
| `harita/` | Markdown vault'unu not grafiği, arama ve haftalık özet olarak gösterir |
| `orkestra/` | Ajan görev kuyruğu, kota takibi, kanıt değerlendirme ve web panel |
| `danis/` | Terminalde hata asistanı + "bu dosyayı cor'a sor" (Windows `.exe` derlemesi var) |
| `anlat/` | Git deposunun geçmişinden Türkçe teknik anlatı üretir; NotebookLM ile sesli özet hazırlar |
| `tekrar/` | Vault bilgi notlarından aralıklı tekrar kartları üretir, her gün Telegram'a gönderir (Leitner aralıkları) |
| `portfolyo/` | Allowlist'li, tek dosyalık statik portfolyo sayfası üretir (ağ yok, sızıntı denetimi var) |

Bu depoda olmayan ama aynı istemciyi kullanan projeler: `ne-izlesem` (film/kitap takip ürünü, ayrı repoda; kopyası
`python3 tools/sync.py ../ne-izlesem/app/_corclient.py` ile güncellenir) ve `readbunny` (kendi istemcisi var).

Her klasör **bağımsız bir projedir**: kendi `README.md`, `pyproject.toml` ve testi var.
Testler klasörün içinden koşulur (kökteki `pytest` yalnızca ortak istemciyi sınar):

```bash
python3 -m pytest -q                      # kök: ortak istemci + senkron + tüm kopyaların güncelliği
cd atlas && python3 -m pytest -q          # bir proje
```

## Ortak istemci nasıl paylaşılıyor (vendoring)

Projeler bilerek **yalnız standart kütüphane** kullanır ve kendi başına kurulabilir/derlenebilir
olmalıdır (ör. `danis` PyInstaller ile tek `.exe` olur). Bu yüzden istemci bir pip bağımlılığı
değil; `corclient.py` **kopyalanır**: her projenin paketinde `_corclient.py` vardır ve
ilk satırında kaynağın sha256'sı yazar. Proje içindeki `llm.py` ise yalnızca o projeye özgü
varsayılanları (model, token sayısı, zaman aşımı, konak denetimi) taşıyan ince bir kabuktur.

Kopya **elle düzenlenmez**. Düzeltme her zaman `corclient.py`'de yapılır:

```bash
python3 tools/sync.py --hepsi            # kaynağı tüm projelere yansıt
python3 tools/sync.py --check --hepsi    # sapma varsa çıkış kodu 1
```

Kökteki `tests/test_monorepo_kopyalar.py`, tüm kopyaların güncel olduğunu ve listede olmayan
bir kopya bulunmadığını sınar; yansıtmayı unutmak testi kırar. CRLF (Windows `autocrlf`)
farkı hash'i bozmaz.

## Proje varsayılanları

| Proje | `DEFAULT_MODEL` | `MAX_TOKENS` | timeout | konak denetimi | başlat ipucu |
|---|---|---|---|---|---|
| atlas | `stealth/space-bunny-alpha` | 2000 | 60 | loopback | `cor start` |
| harita | `stealth/space-bunny-alpha` | 2000 | 60 | loopback + `0.0.0.0` | `cor start` |
| orkestra | `nvidia/nemotron-3-ultra-550b-a55b:free` | 4000 | 120 | loopback | `cor start` |
| danis | `stealth/space-bunny-alpha` | 2000 | 60 | loopback | `cor` |
| anlat | `stealth/space-bunny-alpha` | 8000 | 300 | loopback | `cor claude` |

Loopback denetimi, kullanıcı verisi yanlışlıkla başka bir makineye gitmesin diye cor adresi
`127.0.0.1`/`localhost`/`::1` dışındaysa istemciyi kurarken hata verir. `COR_BASE_URL` ve
`COR_MODEL` ortam değişkenleri varsayılanları değiştirir (`anlat` bunları okumaz, `--base-url`/`--model` bayraklarını kullanır; adres yine loopback olmalı).

`anlat`'ta da konak denetimi açık: loopback dışı `--base-url` CLI'da `Hata:` mesajı ve çıkış kodu 1 verir (traceback yok).

## CI

`.github/workflows/danis-build-windows.yml`: `danis/` veya `corclient.py` değişince Windows'ta
`danis.exe` derler ve `--help` ile sınar. Yalnızca GitHub'ın Windows çalıştırıcısında çalışır;
sonucu Actions sekmesinden görürsünüz.

Ayrıntılı tasarım gerekçesi ve kabul kriterleri: [`SOZLESME.md`](SOZLESME.md).
