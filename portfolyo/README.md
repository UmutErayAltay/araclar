# portfolyo

Herkese açık GitHub repolarından **tek dosyalık statik portfolyo sayfası** (`index.html`) üretir.
Ağ kullanmaz, JS yok, dış kaynak yok (font/CDN/analitik yok). Yalnızca Python standart kütüphanesi
(Python 3.10+) ve yerel `git`.

## Gizlilik modeli (bağlayıcı)

- **Allowlist:** yalnız yapılandırmada listelenen repolar girer ve her birinde açıkça
  `"herkese_acik": true` yazmak zorundasın. Yoksa/`false` ise araç hata verir ("özel repo yayınlanmaz").
- **Vault içeriği hiç girmez.** Sayfaya yalnız yapılandırmadaki metinler, `git` geçmişinden sayılar
  (commit sayısı, tarihler, haftalık etkinlik, dosya uzantısından diller) ve — **yalnız `readme: true`**
  işaretli repolarda — README'nin ilk paragrafı girer.
- **Sızıntı kapısı:** üretilen HTML yazılmadan önce taranır (API anahtarı, JWT, Telegram/GitHub/AWS
  token'ı, özel anahtar, yerel dosya yolu, e-posta, özel ağ adresi, dış kaynak). Bir bulgu varsa
  **hiçbir dosya yazılmaz**, çıkış kodu `4` olur, bulgu maskeli gösterilir.
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
```

`portfolyo.json` biçimi (`portfolyo.ornek.json` dosyasına bak):

| Alan | Açıklama |
|---|---|
| `sahip.ad`, `unvan`, `hakkinda` | Sayfa başlığı ve tanıtım (`hakkinda`'da boş satır = yeni paragraf) |
| `sahip.github` | GitHub kullanıcı adın; repo bağlantıları buradan türetilir |
| `repolar[].ad` | Repo adı |
| `repolar[].herkese_acik` | **Zorunlu, `true`**: bu repo herkese açık |
| `repolar[].aciklama`, `etiketler` | Kartta görünen metin (en çok 300 karakter / 8 etiket) |
| `repolar[].klon` | İsteğe bağlı yerel klon yolu: commit sayısı, haftalık etkinlik ve diller buradan okunur |
| `repolar[].readme` | `true` ise README'nin ilk paragrafı da kartta görünür (varsayılan `false`) |

Klon yoksa kart yalnız yapılandırma metnini gösterir. Kartlar son commit tarihine göre dizilir.

## Yayınlama (sen yaparsın)

GitHub Pages ücretsiz planda yalnız **public** repodan yayın yapar. Kişisel site için repo adı
`<kullanıcı>.github.io` olmalıdır. Bu araç repo açmaz ve push etmez; adımlar:

1. Public bir repo aç (`<kullanıcı>.github.io`).
2. `portfolyo uret portfolyo.json --cikti <o reponun klasörü>` çalıştır.
3. `index.html` ve `.nojekyll` dosyalarını commit'le, push'la; Pages ayarında dalı seç.

Yayından önce `index.html`'i bir kez gözle oku: kapı yalnız bilinen desenleri yakalar.

## Çıkış kodları

`0` başarı · `2` yapılandırma/kullanım hatası · `4` sızıntı denetimi bulgu verdi

## Test

```bash
python3 -m pytest -q
```
