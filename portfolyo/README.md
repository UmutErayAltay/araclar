# portfolyo

Herkese açık GitHub repolarından **statik portfolyo sitesi** üretir: `index.html` (kategorilere
ayrılmış proje kartları, istatistikler, paylaşım meta etiketleri, favicon) ve isteğe bağlı olarak
elle yazılmış markdown **yazılarından** sayfalar. JS yok, dış kaynak yok (font/CDN/analitik yok).
Yalnızca Python standart kütüphanesi (Python 3.10+).

Ağa **yalnızca** `veri: "api"` olan repolar (ya da `--api` bayrağı) için ve yalnızca sabit konak
`api.github.com`'a çıkılır; aksi hâlde hiç ağ kullanılmaz.

## Gizlilik modeli (bağlayıcı)

- **Allowlist:** yalnız yapılandırmada listelenen repolar girer ve her birinde açıkça
  `"herkese_acik": true` yazmak zorundasın. Yoksa/`false` ise araç hata verir ("özel repo yayınlanmaz").
- **Vault içeriği hiç girmez.** Sayfaya yalnız yapılandırmadaki metinler, repo verisi (commit sayısı,
  tarihler, haftalık etkinlik, diller) ve — **yalnız `readme: true`** işaretli repolarda — README'nin
  ilk paragrafı girer. Yazılar yalnız `yazilar/` klasörüne elle koyduğun dosyalardan gelir.
- **API modunda özel repo asla yayınlanmaz:** yanıtta `private` açıkça `false` değilse (ya da
  `visibility` `public` değilse) o repo için veri alınmaz, kart yalnız yapılandırma metniyle çizilir.
  Token (`GITHUB_TOKEN`) yalnız `Authorization` başlığında gider; hiçbir çıktıya yazılmaz.
- **Sızıntı kapısı:** üretilen HTML yazılmadan önce taranır (API anahtarı, JWT, Telegram/GitHub/AWS
  token'ı, özel anahtar, yerel dosya yolu, e-posta, özel ağ adresi, dış kaynak). Bir bulgu varsa
  **hiçbir dosya yazılmaz** (ana sayfa ve tüm yazı sayfaları birlikte değerlendirilir), çıkış kodu `4`
  olur, bulgu maskeli gösterilir. `<link` yalnız `data:` favicon olarak serbesttir.
- Bağlantılar yapılandırmadan **türetilir** (`https://github.com/<github>/<repo>`); rastgele URL
  verilemez. Tüm metin HTML-kaçışlanır, sayfada CSP meta etiketi vardır.
- Yerel klon yolları çıktıya ve hata mesajlarına yazılmaz.

## Kurulum

```bash
cd portfolyo
pip install -e .
```

## Kullanım

```bash
cp portfolyo.ornek.json portfolyo.json     # kendi bilgilerinle düzenle
portfolyo kontrol portfolyo.json            # yapılandırmayı doğrula (dosya yazmaz)
portfolyo uret portfolyo.json --kuru --cikti site   # denetle, yazma
portfolyo uret portfolyo.json --cikti site          # site/index.html + site/.nojekyll
portfolyo uret portfolyo.json --api --cikti site    # `veri` belirtilmeyen repolar için GitHub API'si
portfolyo uret portfolyo.json --yazilar yazilar --cikti site   # + site/yazilar/<ad>.html
```

`portfolyo.json` biçimi (`portfolyo.ornek.json` dosyasına bak):

| Alan | Açıklama |
|---|---|
| `sahip.ad`, `unvan`, `hakkinda` | Sayfa başlığı ve tanıtım (`hakkinda`'da boş satır = yeni paragraf) |
| `sahip.github` | GitHub kullanıcı adın; repo bağlantıları buradan türetilir |
| `sahip.site_url` | İsteğe bağlı `https://` adresi; `og:url` meta etiketinde kullanılır |
| `kategoriler` | İsteğe bağlı, görünme sırasıyla kategori adları (en çok 8). Verilmezse tek ızgara çizilir |
| `siralama` | `manuel` (varsayılan: yapılandırma sırası) ya da `aktivite` (son commit'e göre) |
| `repolar[].ad` | Repo adı |
| `repolar[].herkese_acik` | **Zorunlu, `true`**: bu repo herkese açık |
| `repolar[].aciklama`, `etiketler` | Kartta görünen metin (en çok 300 karakter / 8 etiket) |
| `repolar[].kategori` | `kategoriler` listesinden biri; verilmezse "Diğer" (en sonda) |
| `repolar[].veri` | `yok` / `klon` / `api`. Verilmezse `klon` yolu varsa `klon`, yoksa `yok` |
| `repolar[].klon` | İsteğe bağlı yerel klon yolu: commit sayısı, haftalık etkinlik ve diller buradan okunur |
| `repolar[].readme` | `true` ise README'nin ilk paragrafı da kartta görünür (varsayılan `false`) |

Veri yoksa (ya da okunamazsa) kart yalnız yapılandırma metnini gösterir. API verisinde diller yüzde
olarak gösterilir; GitHub haftalık istatistiği hazırlamadıysa etkinlik grafiği çizilmez.
Sıfır repo'lu kategori çizilmez.

## Yazılar

`--yazilar KLASOR` ile `KLASOR/*.md` dosyaları `yazilar/<ad>.html` sayfalarına çevrilir ve ana
sayfaya "Yazılar" bölümü (tarih azalan) eklenir. Dosya adı `^[a-z0-9-]+\.md$` olmalıdır.

```markdown
---
baslik: Başlık (en çok 120 karakter)
tarih: 2026-10-01
ozet: Liste ve paylaşım önizlemesi için özet (en çok 200 karakter)
etiketler: [python, test]
herkese_acik: true
---
## Alt başlık

Paragraf, **kalın**, *italik*, `kod`, [bağlantı](https://example.com).
```

- **`herkese_acik: true` zorunludur**; yoksa/`false` ise yazı taslaktır ve yayınlanmaz (bilgi satırı
  basılır). Yayına açık işaretli ama bozuk bir yazı hatadır (çıkış `2`).
- Markdown **alt kümesi**: `##`/`###` başlık, paragraf, `-`/`*` ve `1.` listeleri, ``` kod blokları,
  `>` alıntı, satır içi kod/kalın/italik, `[metin](https://…)` ya da göreli bağlantı.
  **Ham HTML ve görsel yok**; her metin işaretlemeden önce kaçışlanır; `javascript:`/`http:` bağlantılar
  hata verir.
- Yazı sayfaları ana sayfayla aynı CSP, meta etiketleri ve sızıntı kapısından geçer.

## Yayınlama (sen yaparsın)

GitHub Pages ücretsiz planda yalnız **public** repodan yayın yapar. Kişisel site için repo adı
`<kullanıcı>.github.io` olmalıdır. Bu araç repo açmaz ve push etmez.

**Elle:** `portfolyo uret ... --cikti <repo klasörü>`, ardından üretilen dosyaları commit'le/push'la.

**Kendi kendini güncelleyen (önerilen):** site repoya üreticiyi (`generator/portfolyo/`), `portfolyo.json`
ve `yazilar/` klasörünü koy; üretilmiş HTML'i commit'leme. Bir GitHub Actions iş akışı her push'ta ve
haftalık olarak `portfolyo uret portfolyo.json --api --yazilar yazilar --cikti _site` çalıştırıp
`actions/deploy-pages` ile yayınlar (Pages kaynağı **GitHub Actions** olmalı). Üretici hata verirse
(yapılandırma hatası, sızıntı bulgusu) yayın yapılmaz, eski site yerinde kalır. `GITHUB_TOKEN` ile
yapılan push Pages derlemesini tetiklemediği için üretilmiş dosyayı repoya geri commit'leme yöntemi
kullanılmaz. Üretici değişince `generator/` klasörünü bu repodan elle yeniden kopyala.

Yayından önce üretilen sayfayı bir kez gözle oku: kapı yalnız bilinen desenleri yakalar.

## Çıkış kodları

`0` başarı · `2` yapılandırma/kullanım hatası · `4` sızıntı denetimi bulgu verdi

## Test

```bash
python3 -m pytest -q
```
