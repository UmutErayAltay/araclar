# atlas — Repo Sağlık Atlası

Bir kök dizindeki tüm git repolarını tarar, her birinin sağlık durumunu SQLite'a yazar,
CLI ile tablo olarak gösterir ve **salt okunur bir web paneli** ile görüntüler.
**Dalga A** (çekirdek tarayıcı + DB), **Dalga B** (sızıntı ve geçmiş taraması) ve
**Dalga C** (TODO borcu + web paneli) uygulanmıştır.

## Ne yapar

`atlas tara` verdiğiniz dizinleri gezer, içinde `.git` olan her klasörü bir repo sayar ve
şunları SQLite'a yazar:

| Alan | Anlamı |
|---|---|
| `dirty` | `git status --porcelain` satır sayısı (izlenmeyen dosyalar dahil) |
| `unpushed` | Push edilmemiş commit sayısı (aşağıdaki kuraya bakın) |
| `branch` | Mevcut dal; detached ise `(detached)` |
| `last_commit_at` | Son commit tarihi, ISO8601 UTC |
| `has_remote` | Uzak (remote) tanımlı mı |

`unpushed` kuralı:
- Upstream varsa → `@{u}..HEAD` arası commit sayısı.
- Upstream yok, remote var **ve yerelde `refs/remotes/` altında en az bir ref
  varsa** → HEAD'in hiçbir remote ref'inde olmayan commit sayısı.
- Upstream yok, remote var ama **yerelde hiç uzak-takip ref'i yoksa** →
  `?` (bilinmiyor). Aşağıdaki "Bilinen sınır" başlığına bakın.
- **Remote hiç yoksa** → depodaki toplam commit sayısı. (Yerelde duran işin
  göstergesi; "push bekliyor" anlamına gelmez. Bu yüzden `liste --sadece-yarim`
  bu durumu filtreye almaz.)

## Bilinen sınır: `?` ne demek

`unpushed` **yalnızca yerel ref'lere** bakar. `git fetch` çalıştırmaz (ağ erişimi
bilerek yok), dolayısıyla uzakla ilgili her şey *bu makinenin daha önce indirdiği
`refs/remotes/*` ref'lerinden* ibarettir.

Bazı ortamlarda (ör. proxy üzerinden klonlanan/pushlanan repolar) remote tanımlı
olsa da yerelde **hiç `refs/remotes/` ref'i bulunmaz**. O durumda "kaç commit
push edilmemiş" sorusunun cevabı gerçekten bilinmez: `--remotes` hiçbir şeyi
dışlamaz ve tüm commitleri döndürür, ama doğru sonuç 0 da olabilir (hepsi
push edilmiş olabilir). atlas bu durumda **sayı uydurmaz**, `?` gösterir:

```
danis   main   0   ?   2026-09-28 20:03  /home/user/danis
? = uzak-takip bilgisi yok (git fetch gerekir); atlas fetch yapmaz.
```

Bu bir hata değil, ölçülebilir bir bilgidir. Çözüm atlas'ta değil, repoda:
`git fetch` (veya `git fetch origin`) bir kez çalıştırılırsa ref'ler dolar ve
atlas bir sonraki taramada gerçek sayıyı gösterir. Bu sırada `?` olan repo
`liste --sadece-yarim` çıktısına **giremez** — "yarım iş" olduğu bilinmiyor, bu
yüzden listelenmemek doğrudur.

## Kurulum

Python 3.11+ ve `git` gerekir. Tek çalışma zamanı bağımlılığı **Flask**'tır
(web paneli için); tüm tarama kodu yalnızca standart kütüphaneyle çalışır.

```bash
python3 -m atlas tara --root /home/user   # pip kurulumu gerekmez
```

İsteğe bağlı olarak paket olarak kurmak için:

```bash
pip install -e .
atlas tara --root /home/user
```

Geliştirme/test:

```bash
pip install -r requirements-dev.txt
python3 -m pytest -q
```

## Kullanım

```bash
# Tüm repoları tara (varsayılan derinlik 3)
atlas tara --root /home/user

# Birden fazla kök ve özel derinlik
atlas tara --root ~/Desktop --root ~/Projeler --derinlik 2

# Listele
atlas liste
atlas liste --sadece-yarim          # yalnızca commit'lenmemiş veya push bekleyenler

# Sızıntı taraması (ayrı komut; git durumunu etkilemez)
atlas sizinti --root /home/user
atlas bulgular --siddet yuksek

# TODO/FIXME borcu (Dalga C)
atlas borc --root /home/user
atlas borc --repo ornek-repo

# ÜÇÜNÜ TEK KOMUTTA: tara + sizinti + borc
atlas guncelle --root /home/user

# Salt okunur web paneli (yalnızca 127.0.0.1)
atlas web --port 8770
```

**Veritabanı yolu:** `--db` ile verilmezse `ATLAS_DB` ortam değişkeni, o da yoksa
`~/.atlas/atlas.db`. Üst dizin yoksa otomatik oluşturulur.

**Kök dizinler:** `--root` verilmezse `~/.atlas/config.toml` içindeki `roots`
listesi kullanılır:

```toml
roots = ["/home/user/projeler", "~/Desktop"]
```

`findings` ve `todos` tabloları Dalga B ve C'de doldurulur; `readme_status` şeması
Dalga D için hazır durumda ama henüz doldurulmaz.

## Sızıntı taraması (Dalga B)

`atlas sizinti` her repoyu **iki yerden** tarar: çalışma ağacı (`git ls-files` ile
yalnızca *izlenen* dosyalar) ve `git log -p -U0` çıktısındaki **eklenen satırlar**
(varsayılan son 500 commit, `--gecmis N` ile ayarlanır).

```bash
# Tüm repoları tara (geçmiş dahil) ve DB'ye yaz
atlas sizinti --root /home/user

# Yalnızca belirli bir repo / daha az geçmiş
atlas sizinti --repo orkestra --gecmis 100

# Bulguları tablo olarak listele
atlas bulgular
atlas bulgular --siddet yuksek
atlas bulgular --tur api-anahtari
```

Bulgu türleri ve önemleri:

| Tür | Önem | Ne arar |
|---|---|---|
| `api-anahtari` | yüksek | `sk-…`, `AKIA…`, `ghp_…`, `xoxb-…`, `sk_live_…`, `AIza…`, JWT (`eyJ….….…`), `sb_secret_…`, etiketli değer (`API_KEY = …`) |
| `api-anahtari` | bilgi | `sb_publishable_…` (yayınlanabilir anahtar; istemci tarafında herkese açık olması **tasarım gereği**) |
| `ozel-anahtar` | yüksek | `-----BEGIN … PRIVATE KEY-----` **başlığının ardından 1–5 satırda ≥32 karakterlik base64 gövdesi** |
| `ozel-anahtar` | bilgi | Yalnız **başlık** var (test fixture'ı, dedektör kodu, dokümantasyon) — "başlık var, gövde yok — elle kontrol et" |
| `env-izlenen` | yüksek | Git'in **izlediği** `.env`, `.env.local` … (`.env.example` hariç) |
| `kisisel-yol` | orta | `C:\Users\<ad>`, `/Users/<ad>/`, `/home/<ad>/` |
| `e-posta` | düşük | Gerçek e-posta (noreply/example imzaları hariç) |
| `gorsel-elle-kontrol` | bilgi | Git'in izlediği **tüm** `png/jpg/jpeg/gif/webp/svg` (üretim dizinleri hariç) |

Üç incelik:

- **`.env` içeriği hiç okunmaz.** Bulgu yalnızca *yol* bilgisidir; sır olabilecek
  içerik hiçbir yere taşınmaz.
- **Görseller için OCR yok.** Bulgu, dosyanın varlığı + "elle kontrol et" notudur.
  Karar bilinçlidir: yeni bir bağımlılık (pytesseract) getirmemek için. Tek bir
  repoda 50'den fazla görsel varsa dosya başına bulgu yerine **tek bir özet**
  bulgu yazılır (liste boğulmasın).
- **`tests/` yolu bir kademe düşürür** (`api-anahtari`, `ozel-anahtar`,
  `kisisel-yol`, `e-posta`); bulgu **atlanmaz**. `env-izlenen` ve
  `gorsel-elle-kontrol` bu kuralın dışındadır: ilki içerik okunmadığı için
  dosyanın varlığı zaten sırdır, ikincisi zaten `bilgi`.

`atlas tara` ile `atlas sizinti` **ayrı komutlardır**: git durumu temizlenmeden
sızıntı bulguları silinmez, ve tersi. Bir repo yeniden taranınca yalnızca **o
repo'nun** eski bulguları silinip yenileri yazılır (tek transaction).

### Maskeleme (bağlayıcı kural)

Ham sır **hiçbir yere** yazılmaz: DB'ye, `stdout`/`stderr`'a, log'a, istisna
mesajına veya traceback'e. Bulgu nesnesi yalnızca `atlas/leaks.py` içindeki tek
bir fonksiyonda (`bulgu_olustur`) üretilir; eşleşen ham metin o fonksiyonun yerel
değişkenidir ve dışarı verilmez.

- Sırlar **tümüyle** silinir: `sk-…xxxx` gibi parça bırakmak da sızıntıdır.
- Yollar `C:\Users\<kullanıcı>`, `/home/<kullanıcı>/`; e-posta `<e-posta>` olur.
- **Savunma katmanı:** tespit edilmemiş olsa bile, 24+ karakterlik ve içinde en az
  bir rakam bulunan her `[A-Za-z0-9_-]` dizisi `[maskeli:uzun-deger]` olur. `/`
  ve `.` sınıf dışı olduğu için yol/URL parçaları bölünmez ve olduğu gibi
  kalır; URL içindeki `key=`/`token=`/`apikey=` değerleri ise maskelenir.
- `snippet_redacted` en fazla 120 karakterdir: satırın tamamı maskelenir, sonra
  **ilk eşleşmenin etrafındaki** pencereye (~40 önce, ~60 sonra) kırpılır ve
  kesilen uçlara `…` konur. Kırpma ham sırın parçasını açığa çıkaramaz.

Bu kural testle kanıtlanır: sahte sırlarla kurulan bir fixture repoda tarama
yapıldıktan sonra DB dosyasının **ham baytlarında**, iki komutun **stdout/stderr**
çıktısında ve pytest çıktısında sahte sırın **hiçbir parçası** (ilk 6 karakter
dâhil) bulunmadığı otomatik olarak doğrulanır.

## Güvenlik notu

- **Salt okunur.** Taranan repolara hiçbir şey yazılmaz. atlas yalnızca okuyan git
  komutlarını çalıştırır (`status`, `log`, `rev-parse`, `rev-list`, `symbolic-ref`,
  `remote`, `for-each-ref`, `ls-files`). `push`, `fetch`, `pull`, `reset`,
  `checkout`, `clean`, `gc`, `show`, `cat-file`, `grep` gibi komutlar kodda yoktur
  ve çalıştırılması teknik olarak engellenir. Git her seferinde
  `GIT_OPTIONAL_LOCKS=0` ile çağrılır, böylece `status` bile index'i tazelemez.
- Bu davranış testlerle kanıtlanır: taranan repoların `.git` içeriği, çalışma ağacı ve
  index dosyası tarama öncesi ve sonrası bayt bayt aynıdır. `atlas sizinti` için de
  ayrı bir kanıt testi vardır: bir koruma (guard) script'i her git çağrısını kaydeder
  ve izin listesindeki alt komut dışındaki her şeyi reddeder.
- İkili dosyalar (ilk 8 KiB içinde NUL) ve 1 MiB'tan büyük dosyalar atlanır; sembolik
  linkler takip edilmez. Repo başına toplam süre 120 saniyeyi aşarsa "kısmi
  tarama" uyarısı verilir (hata değildir; bulgular korunur).
- Bir repo bozuk/erişilemez ise atlanır ve uyarı olarak stderr'a yazılır; tüm tarama
  çökmez, çıkış kodu yine `0`'dır.
- Uzak sunucuya hiçbir ağ isteği yapılmaz (`fetch` yasaktır); yalnızca yerel
  `origin` bilgisi okunur.
- `atlas borc` ve `atlas guncelle` de aynı güvence altındadır: `todo.py` **yeni
  git alt komutu talep etmez**, yalnızca `ls-files` + standart dosya okuması
  kullanır. Bu, izin listesiyle (guard script'i) ayrıca test edilir.

## TODO / FIXME borcu (Dalga C)

`atlas borc` git'in **izlediği** metin dosyalarında `\b(TODO|FIXME|XXX|HACK)\b`
içeren satırları bulur ve `todos` tablosuna yazar. Metin **160 karakterle
kırpılır** ve DB'ye yazılmadan önce maskeleme fonksiyonundan geçer (todo yorumu
`# API_KEY = …` bir sır taşıyabilir).

- Kelime sınırı `\b` ile uygulanır ve büyük/küçük harf duyarsızdır: `TODOS`,
  `todo_list`, `myTODO`, `hacked` gibi **bileşik** adlar elenir; `// fixme:` gibi
  gerçek yazımlar yakalanır.
- İkili (ilk 8 KiB içinde NUL), 1 MiB'tan büyük ve `node_modules/.venv/vendor/
  dist/build` altındaki dosyalar atlanır; sembolik linkler takip edilmez.
- Repo yeniden taranınca **yalnız o repoya ait** eski kayıtlar silinip yeniler
  (tek transaction) — `findings` ile aynı kural.

### `atlas guncelle`

`tara` + `sizinti` + `borc` üçünü **tek komutta** sırayla çalıştırır ve üç
tabloyu doldurur. Mevcut komutların davranışı değişmez: `guncelle` yalnızca onları
çağırır, yeni bir tarama yöntemi değildir.

```bash
atlas guncelle --root /home/user            # üç tablo birden
atlas guncelle --root ~/Desktop --gecmis 200
```

## Web paneli (Dalga C)

`atlas web` aynı DB'yi **salt okunur** açan yerel bir panel başlatır:

```bash
atlas web --db ~/.atlas/atlas.db --port 8770
```

| Sayfa | İçerik |
|---|---|
| `/` | Özet kartları (repo, kirli, push bekleyen, push bilinmeyen, bulgu sayıları, toplam todo, son tarama) |
| `/yarim-is` | Üç bölüm: kirli · pushlanmamış commit'i **bilinen** · push durumu **bilinmeyen** |
| `/sizinti` | Bulgular; `?siddet=` `?tur=` `?repo=` süzgeçleri, sayfa başı 100 |
| `/borc` | Repo başına TODO yoğunluğu çubuğu + tüm kayıtlar |
| `/repo/<id>` | Repo kartı + o repoya ait bulgular ve TODO'lar (`id` = satır numarası, **ad değil**) |
| `/api/ozet`, `/api/yarim-is`, `/api/bulgular`, `/api/borc`, `/saglik` | JSON (aynı süzgeçler) |

Panel **repolara dokunmaz ve tarama tetiklemez** — yalnızca DB'yi okur. Veri
24 saatten eskiyse uyarı gösterir. Ekran görüntülerini yenilemek için
`atlas guncelle` çalıştırılır.

### Panel güvenlik modeli

- Sunucu **koda sabit** `127.0.0.1` adresine bağlanır; `--host` seçeneği **yoktur**.
- `Host` başlığı `127.0.0.1[:port]` / `localhost[:port]` değilse **403** döner ve
  istek **bağlantı açılmadan** reddedilir (DNS rebinding koruması).
- Veritabanı `mode=ro` (URI) ile açılır; panel hiçbir koşulda yazmaz.
- Tüm rotalar **yalnızca GET**'tir; diğer metotlar 405 döner (CSRF yüzeyi yoktur).
- Rota yüzeyi **sayısal id/sayfa** ile sınırlıdır; dosya sistemi yolu alan rotalar
  yoktur.
- `Content-Security-Policy: default-src 'none'; script-src 'self'; style-src 'self';
  img-src 'self' data:; connect-src 'self'; base-uri 'none'; form-action 'none';
  frame-ancestors 'none'` her yanıtta bulunur; ayrıca `X-Content-Type-Options:
  nosniff`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store`.
  **Satır içi script/stil yoktur**; JS/CSS `static/` altındadır.
- Repo adı, dosya adı, snippet ve todo metni **güvenilmeyen veridir**: Jinja
  autoescape açık, JS'te `innerHTML` yoktur (`textContent`/`setAttribute`).
- Ekrana basılan **her** `snippet_redacted` ve `text`, basılmadan **önce** bir kez
  daha maskeleme fonksiyonundan geçer (savunma katmanı: DB'de ham sır olsa bile
  ekrana çıkmaz). Testle kanıtlanır.
- Rozetler yalnızca renge dayanmaz: her rozet hem renk hem **metin** taşır.
  Grafikler sıfır bağımlılık SVG'dır (CDN yok).

Bu güvence testlerle kanıtlanır: 405/403/404, güvenlik başlıkları, `mode=ro`,
reddedilen isteğin DB açmaması, XSS yükleri, ham sırın hiçbir yanıtta
(ilk 6 karakteri dâhil) görünmemesi ve panelin/CLI'nin repoları bayt bayt
değiştirmemesi.

## Ekran görüntüleri

Aşağıdakiler **kurgusal veriyle** üretilmiştir: repo adları, yollar ve kişiler
uydurmadır; gerçek repo adı, yol, anahtar veya e-posta **yoktur**. Üretici:
`python3 scripts/ekran_goruntusu.py`.

### Özet (masaüstü)

![Özet — masaüstü](docs/ekran/ozet-masaustu.png)

### Yarım iş

![Yarım iş](docs/ekran/yarim-is.png)

### Sızıntı bulguları

![Sızıntı — masaüstü](docs/ekran/sizinti-masaustu.png)

### TODO / FIXME borcu

![Borç](docs/ekran/borc.png)

### Özet (mobil, 390 px)

![Özet — mobil](docs/ekran/ozet-mobil.png)
