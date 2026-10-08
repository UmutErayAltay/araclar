# araclar — web paneli tasarım rehberi

Bu depodaki her yerel web paneli (liman, devtemizle, yol, …) bu kurallara uyar. Panel
tek başına da açılır, kule içinde iframe sekmesi olarak da. Referans uygulama:
`liman/liman/web/` (şablon, `stil.css`, `panel.js`). Yeni panel yazarken önce o üç dosyayı
oku, token adlarını ve sınıf kalıplarını oradan al.

## 1. Görünüm: "AI yapmış gibi durmasın"

Kaçınılacaklar (bilinçli): simsiyah zemin + tek parlak neon vurgu, gradient hero alanı,
her şeyin aşırı yuvarlak olması (radius en çok 8px), Inter/Space Grotesk gibi web fontu
(sistem fontu kullanılır), emoji başlıklar, her şeyi ortalamak, gölge yığınları, cam efekti.

Hedef: sade bir sistem aracı. Sol hizalı, yoğun ama nefes alan tablo; üstte 3–4 özet
kartı; renk yalnız anlam taşıdığında.

## 2. Renk tokenları (liman ile birebir)

Okabe-Ito tabanlı, renk körlüğüne dayanıklı, kontrast ≥ 4.5:1.

| Token | Açık | Koyu | Anlam |
|---|---|---|---|
| `--zemin` | `#f7f8fa` | `#0f1115` | sayfa |
| `--panel` | `#ffffff` | `#151922` | kart / bölüm |
| `--panel-acik` | `#eef1f6` | `#1c2130` | hover, kod zemini |
| `--yazi` | `#1c2029` | `#e6e6e6` | metin |
| `--ikincil` | `#556070` | `#9aa3b2` | açıklama |
| `--kenar` | `#d3d9e2` | `#232833` | çizgi |
| `--vurgu` | `#0072b2` | `#56b4e9` | bağlantı, birincil düğme |
| `--basari` | `#00704a` | `#009E73` | güvenli / tamam |
| `--uyari` | `#a35b00` | `#E69F00` | dikkat |
| `--hata` | `#b03000` | `#D55E00` | tehlike / silme |

Tema `prefers-color-scheme` ile gelir; ayrıca `:root[data-theme="dark"|"light"]` ile
zorlanabilir (kule iframe'e tema geçirirse). Durum **asla yalnız renkle** anlatılmaz:
her rozetin metni de vardır ("güvenli", "dikkat", "yok", "tekrar").

## 3. Yerleşim

- Üst şerit: araç adı (h1, 17px) + tek satır açıklama + sağda birincil eylem.
- Özet kartları: `.kart-izgara` (auto-fill, min 184px). Büyük sayı tabular-nums.
- Bölümler `.bolum` kutuları; tablo `.tablo-sarayici` içinde kendi içinde yatay kayar.
- 390px genişlikte sayfa yatay taşmaz; tablolar kayar, kartlar tek sütuna iner.
- Sayılar sağa hizalı (`td.sayi`), boyutlar insan okunur (`1.4 GB`), tarihler göreli
  ("12 gün önce") ve `title` içinde tam ISO.
- Boş durum: ne olmadığını ve ne yapılacağını söyleyen tek cümle + eylem düğmesi.
- Yükleniyor durumu: iskelet satırlar ya da ilerleme çubuğu (`<progress>`), dönen ikon yok.

## 4. Etkileşim

- Yıkıcı eylem (silme, PATH yazma) iki adımlıdır: önce **önizleme** (ne değişecek, kaç bayt,
  hangi dosya), sonra açık onay düğmesi (`--hata` kenarlı, metni eylemi söyler:
  "3 klasörü sil (2.1 GB)"). `confirm()` kullanılmaz; sayfa içi onay paneli.
- Klavye: tüm kontroller Tab ile erişilir, `:focus-visible` halkası görünür.
- Bildirim: sayfa içi `role="status"` alanı; alert() yok.

## 5. Güvenlik (bağlayıcı, atlas/liman ile aynı)

- Sunucu koda sabit `127.0.0.1`'e bağlanır. `Host` başlığı `127.0.0.1[:port]`/`localhost[:port]`
  değilse 403 (DNS rebinding).
- CSP: `default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:;
  frame-ancestors 'none'` — `KULE_FRAME_ORIGIN` (yalnız `http://127.0.0.1:PORT` veya
  `http://localhost:PORT` kalıbı) verilirse `frame-ancestors` o kökene açılır.
  Satır içi `<script>`/`style=""` YOK.
- Durum değiştiren her istek POST'tur ve: `Origin` başlığı sunucunun kendi kökeni (veya
  `KULE_FRAME_ORIGIN`) değilse 403; ayrıca sayfaya gömülü CSRF jetonu (`X-CSRF` başlığı,
  sunucu başlangıcında `secrets.token_urlsafe(32)`) eşleşmeli.
- İstemciden gelen dosya yolu doğrudan kullanılmaz: sunucu son taramanın kimliklerini
  (`id`) kabul eder, yolu kendi listesinden çözer.

## 6. Doğrulama

Görsel iş Playwright ekran görüntüsüyle kapanır: masaüstü 1280×800 ve mobil 390×844,
açık ve koyu tema. Ekran görüntülerinde gerçek kullanıcı yolu / adı / anahtar olmaz:
sahte (fixture) veriyle çekilir.
