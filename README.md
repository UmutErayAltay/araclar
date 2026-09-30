# atlas — Repo Sağlık Atlası

Bir kök dizindeki tüm git repolarını tarar, her birinin sağlık durumunu SQLite'a yazar ve
CLI ile tablo olarak gösterir. **Dalga A** (çekirdek tarayıcı + DB) ve
**Dalga B** (sızıntı ve geçmiş taraması) uygulanmıştır.

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

Python 3.11+ ve `git` gerekir. Çalışma zamanında hiçbir üçüncü taraf kütüphane yoktur
(yalnızca standart kütüphane).

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
```

**Veritabanı yolu:** `--db` ile verilmezse `ATLAS_DB` ortam değişkeni, o da yoksa
`~/.atlas/atlas.db`. Üst dizin yoksa otomatik oluşturulur.

**Kök dizinler:** `--root` verilmezse `~/.atlas/config.toml` içindeki `roots`
listesi kullanılır:

```toml
roots = ["/home/user/projeler", "~/Desktop"]
```

`findings`, `readme_status` ve `todos` tabloları şemaları Dalga B/C/D için şimdiden
boş olarak oluşturulmuştur; `readme_status` ve `todos` bu dalda doldurulmaz.

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
| `ozel-anahtar` | yüksek | `-----BEGIN … PRIVATE KEY-----` |
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
- Bu dalda web sunucusu yoktur. (Dalga C'de yalnızca `127.0.0.1`'e bağlanacaktır.)
