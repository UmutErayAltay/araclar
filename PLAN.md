---
title: Vault Zihin Haritası
created: 2026-09-30
modified: 2026-09-30
type: project-plan
status: planned
tags: [proje-plani, vault, graf, arama, obsidian, flask, sqlite]
---
# Vault Zihin Haritası (`harita`)

Bu vault'u (Markdown + çift köşeli parantezli wikilink'ler) okuyup web'de graf olarak gösteren, anlamsal arama yapan ve
"bu hafta ne yaptım" özeti üreten salt-okunur araç. Obsidian'ın grafı `search` filtresi yüzünden
düğümleri gizlemişti (2026-09-21); aynı sorunları kendi aracımızla görünür kılmak istiyoruz.

**Durum:** planlandı, kod yok. Repo adı önerisi: `harita`.
Bağlantılar: `vault-durum` skill'i (`.agents/skills/vault-durum/SKILL.md`, kırık link/yetim not mantığı için okunur),
[[cor-bulut-oturumu-agent-tool-erisimsizligi-headless-cozum]], [[ne-izlesem-delegasyon-modeli-ajan-kendi-dogrular]].

## Amaç
- Vault'taki notlar ve aralarındaki bağlantıları graf olarak göster (renk: `tags`/klasör, boyut: bağlantı sayısı).
- Kırık link, yetim not, en sık etiket listeleri.
- Anlamsal arama ("borsa modeli neden başarısız oldu" → ilgili notlar).
- Haftalık özet: `daily/` + `Threads.md` + `Last-Session.md` → cor ile Türkçe "bu hafta ne yaptım".

## Kapsam dışı
Vault'a yazma (not düzenleme/oluşturma yok), Obsidian eklentisi, senkronizasyon, çoklu vault.

## Mimari
- Python 3.11, Flask, `sqlite3`, stdlib. Ayrıştırma elle (regex): frontmatter (`---` bloğu), takma adlı wikilink'ler, `#etiket`.
- Dizin: `harita/parse.py`, `index.py` (SQLite: `notes`, `links`, `tags`, `chunks`), `graph.py`, `search.py`, `digest.py`, `llm.py` (cor istemcisi), `web/` (Flask, tek sayfa graf + arama), `cli.py`, `tests/`.
- Hariç tutulanlar (varsayılan): `.obsidian/`, `receipts/`, `.git/`, `📥 000-Inbox/Dump/`, `.claude/`.
- Graf çizimi: kuvvet-yönlendirmeli yerleşimi stdlib/JS ile SVG (önce zero-dependency, yavaşsa d3 CDN kararı Umut'a sorulur).
- Anlamsal arama: ilk aşama TF-IDF/BM25 (bağımlılıksız, garanti çalışır); embedding bir sonraki dalgada (cor üzerinden embedding endpoint'i varsa, yoksa `sentence-transformers` opsiyonel).

## Güvenlik ve gizlilik (bağlayıcı)
- Vault kişisel: web yalnızca `127.0.0.1`, hiçbir içerik dışarı gönderilmez. cor'a giden özet istemlerinde `Kurallar.md`/kimlik notları HARİÇ.
- Anahtar/parola desenleri (`sk-`, `password`) içeren satırlar indekse ve özete girmez.
- Vault'a yazma yolu kodda yok (testle kanıtla: indeksleme sonrası vault dosyalarının hash'i değişmez).

## Dalgalar
**Dalga A — ayrıştırıcı + SQLite indeks**
- `harita indeksle <vault>` → notlar, linkler, etiketler; `harita kirik`, `harita yetim`, `harita etiketler`.
- Kabul: fixture mini-vault (Türkçe karakter, emoji klasör adları, takma adlı link, kırık link) ile ≥30 test; gerçek vault'ta çalıştırılıp sayılar rapora yazılır.

**Dalga B — web graf**
- `/` graf (sürükle/yakınlaştır, düğüme tıkla → not özeti + bağlantılar), `/kirik`, `/yetim`. Sol hizalı, koyu tema.
- Kabul: Playwright ekran görüntüsü KURGUSAL mini-vault ile alınır ve okunur (gerçek not başlığı görüntüye girmez); 1000+ düğümde çizim 3 sn altında.

**Dalga C — arama**
- BM25 tam-metin + `harita ara "sorgu"`; web arama kutusu, sonuçta parça vurgusu.
- Kabul: fixture'da sorgu → beklenen not ilk 3'te; Türkçe İ/ı büyük-küçük harf normalizasyonu testli.

**Dalga D — haftalık özet**
- `harita ozet --hafta` : son 7 günün daily/Threads/Last-Session'ı → cor özeti. cor yoksa madde işaretli ham liste.
- Kabul: sahte LLM ile test; cor açıksa gerçek denemede çıktı okunup değerlendirilir.

## Bulut oturumu talimatı
Vault bulut oturumuna repo olarak gelir (`Mt3Ui55OS`). İlk mesaj örneği: "Mt3Ui55OS vault'unu oku, `Vault-Zihin-Haritasi.md` Dalga A'yı `/home/user/harita`'da yap; indeksi gerçek vault üzerinde de dene."
Oturum: notu ve Threads'i oku → `cor start` dene → repo yoksa prefilled URL ver → dalgayı yap ve testleri KOŞ → projeyi pushla → vault'ta Durum satırı + `Threads.md` + `Last-Session.md` güncelle, vault'u pushla.

## Açık kararlar (Umut'a sor)
- Graf için d3 CDN kabul mü, yoksa zero-dependency SVG mi?
- Embedding için yeni bağımlılık (`sentence-transformers`) kabul mü?
- Özet çıktısı vault'a not olarak yazılsın mı (şu an yazma yok)?
