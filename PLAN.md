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

**Durum:** Dalga A, B, B.1, C, C.1, D ve **E** tamam (2026-09-30). Dalga E: **`harita durum --json`** — kule entegrasyonu için sözleşmeye uygun tek JSON nesnesi (yalnız sayı/bool/ISO-8601; not başlığı-içeriği-yolu asla girmez), YALNIZCA mevcut indeksi `mode=ro` ile okur, indekslemeyi tetiklemez, ağa çıkmaz; `indeks_yok` → `hata` + çıkış 1, bilinmeyen için `null` (0 değil). Sayılar mevcut koddan yeniden kullanılır (`toplam_sayaclar`, `yetim_ayir`; `tutarlilik_uyari` = `bulgular_uret` uyarı sayısı). `son_indeks` için `indeks_meta` tablosu eklendi. **Yan yol bulunan kusur düzeltildi:** `harita tutarlilik --bugun` bayrağı ayrıştırılıyor ama `bulgular_uret`'e İLETİLMİYORDU (bayrak sessizce yok sayılıyordu); düzeltildi ve yalnız bu kusurdan yeşil kalan bir test gerçekçi kümeye çevrildi. Dalga D: **BM25 tam-metin arama** — `harita ara "sorgu"` + web `/ara` ve `/api/ara`. Yerel ve ağsız (cor çağrılmaz, soket açılmaz). BM25 `k1=1.2`, `b=0.75`; alan ağırlıkları başlık ×4, alias ×4, etiket ×3, yol ×1.5, gövde ×1. Türkçe: NFC → `İ`→`i`/`I`→`ı` → katlama (`ı ç ğ ö ş ü`); sorgu ve belge aynı işlemden geçer, "IŞIK"↔"ışık"↔"isik" ve "ISPARTA"↔"İsparta" aynı terimdir. Kök modu (F5, ilk 5 karakter: "borsanın"/"borsada" → "borsa"); `--tam` kök kesmeyi kapatır ve indeks tam sözcükleri de tutar. Sorgu sözdizimi: VEYA-ağırlıklı terimler, `"tam ifade"` (ardışık geçmeli filtre), `-terim` (hariç), `etiket:ad`, `klasor:ad`; bozuk sözdizimi çökmez. Sonuç = tek not + en iyi parça + ~200 karakter vurgulu alıntı; gizli satırlar İNDEKSTE süzülür ve ALINTI katmanında ikinci kez elenir (iki katman ayrı testli). Sıralama değerlendirmesi (`scripts/ara_degerlendirme.py`, 52 not / 54 sorgu, naif alt-dize taban VEKİLİ — Obsidian ölçülmedi): BM25 MRR **0.935** vs naif **0.779**, ilk-3 **0.963** vs **0.870**; en büyük fark "yaygın+nadir karışım" sınıfında (0.812 vs 0.237). Performans: 1200 notluk sentetik vault'ta sorgu medyan ~6 ms, **p95 ~37 ms** (hedef <150 ms); gerçek vault'ta (299 not) medyan ~7 ms, p95 ~10 ms, gizli-desen eşleşen alıntı **0**. `tutarlilik` çıktısına **"Kontrol edilenler"** bölümü eklendi (eşleşen not↔repo çifti, kaynak, güven, kural başına değerlendirilen çift sayısı; `--json`'da da) — bulgular değişmedi. **Kalan bilinen sınırlar:** (1) Graf etiket/daire binmesi — ana oturumca doğrulandı, bilinen kusur, bu dalgada **dokunulmadı** (Obsidian'da zaten var). (2) Kök modunun F5 yanlış eşleşmeleri (README'de listeli). (3) 4 karakterli sözcükler kök üretmez (`veri` → `verisi` bulmaz). (4) Kural 4 yalnız "vault'ta HİÇ anılmayan" repoları bildirir; anılıp durum sözcüklü proje notu olmayan repolar susturuluyor (bilgi seviyesinde ikinci kademe eklenebilir). (5) Windows doğrulanamadı. Sıradaki: Dalga E yok — öneri: (a) kural 4'e ikinci kademe, (b) aramaya gömülü/bağlantı grafiğinden yeniden sıralama, (c) Windows test koşumu.
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

**Dalga C — haftalık özet + vault↔repo tutarlılığı** (sıra 2026-09-30'da değişti: graf/arama Obsidian'da zaten var, Obsidian'ın yapamadığı işler öne alındı)
- `harita ozet --hafta`: son 7 günün daily/Threads/Last-Session'ı → cor özeti. Varsayılan hiçbir şey dışarı göndermez (ham liste); cor'a yalnızca açık `--cor` bayrağıyla gider; `Kurallar.md`/`Core.md`/kimlik notları HER ZAMAN hariç, sır satırları süzülür. Özet vault'a yazılmaz.
- `harita tutarlilik`: proje notlarının durumu (`status:`/`**Durum:**`) ve `Threads.md` ile atlas DB'sindeki gerçek repo durumu (commit, dirty, son commit tarihi) çelişiyor mu? Salt okunur, öneri metni üretir.
- Kabul: sahte LLM ile testler; gerçek vault + gerçek atlas DB üzerinde çalıştırılıp bulgular incelenir, yanlış pozitifler ayıklanır.

**Dalga D — arama** ✅ TAMAM (2026-09-30)
- BM25 tam-metin + `harita ara "sorgu"`; web `/ara` arama kutusu, sonuçta parça vurgusu.
- Türkçe İ/ı normalizasyonu + katlama; kök modu ve `--tam`; ifade/hariç/etiket/klasör filtreleri.
- Kabul: fixture'da sorgu → beklenen not ilk 3'te; Türkçe İ/ı testli; sorgu p95 < 150 ms.
  Gerçekleşti: 520 test yeşil; sentetik p95 ~37 ms, gerçek vault p95 ~10 ms.

## Bulut oturumu talimatı
Vault bulut oturumuna repo olarak gelir (`Mt3Ui55OS`). İlk mesaj örneği: "Mt3Ui55OS vault'unu oku, `Vault-Zihin-Haritasi.md` Dalga A'yı `/home/user/harita`'da yap; indeksi gerçek vault üzerinde de dene."
Oturum: notu ve Threads'i oku → `cor start` dene → repo yoksa prefilled URL ver → dalgayı yap ve testleri KOŞ → projeyi pushla → vault'ta Durum satırı + `Threads.md` + `Last-Session.md` güncelle, vault'u pushla.

## Açık kararlar (Umut'a sor)
- Graf için d3 CDN kabul mü, yoksa zero-dependency SVG mi?
- Embedding için yeni bağımlılık (`sentence-transformers`) kabul mü?
- Özet çıktısı vault'a not olarak yazılsın mı (şu an yazma yok)?
