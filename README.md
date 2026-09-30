# orkestra

Ajan Orkestrasi: bunny/nemotron/deepseek ajanlari icin gorev kuyrugu, kota takibi ve web panel.

Durum: **Dalga C** (web panel + kota) bitti. Sirada Dalga D (planner + rapor ayristirma).
Calisma zamani bagimliligi yalnizca **Flask**; testler icin `pytest` ve `playwright`.

## Kurulum

```bash
python3 -m pip install -r requirements.txt      # calistirmak icin (flask)
python3 -m pip install -r requirements-dev.txt  # testler icin (+ pytest, playwright)
```

## Komutlar

```bash
orkestra ver --ajan bunny-coder "README.md dosyasini incele"   # görev ekle
orkestra liste                                              # tüm görevler
orkestra liste --durum bekliyor                             # duruma göre filtre
orkestra iptal 2                                            # görevi iptal et
orkestra tekrar 2                                           # hatalı görevi yeniden dene

# Dalga B: gerçek çalıştırma
orkestra calistir-bir --model stealth/space-bunny-alpha --cwd /tmp/orkestra_e2e
orkestra calistir --limit 10                                # bekleyenleri sırayla çalıştır
orkestra kurtar                                             # yarım kalan görevleri düzelt
orkestra rapor 1                                            # son koşunun raporu

# Dalga C: web paneli + kota
orkestra kota-guncelle                                      # cor proxy.log'u oku, kotayi guncelle
orkestra kota                                               # model basina bugunku istek/limit/durum
orkestra kota --json                                        # ayni bilgi JSON olarak
orkestra web                                                # paneli 127.0.0.1:8780'de baslat
orkestra web --port 8780 --db ~/.orkestra/orkestra.db \
             --cikti-dizini ~/.orkestra/runs --cor-log ~/.orkestra/proxy.log
```

Paket doğrudan da çalışabilir: `python3 -m orkestra ...`

Veritabanı yolu: `--db YOL` ile verilir, yoksa `ORKESTRA_DB`, yoksa
`~/.orkestra/orkestra.db`.

Ortam değişkenleri: `ORKESTRA_DB` (veritabanı), `COR_LOG` (cor `proxy.log` yolu),
`ORKESTRA_CLAUDE_CMD` (çalıştırılacak komut, `shlex` ile bölünür; testlerde sahte
`claude` betiği için kullanılır).

## Çalıştırıcı

`ClaudeRunner` `claude -p`'yi alt süreç olarak çalıştırır:

- **İstem STDIN'den gider**, komut satırına konmaz — `ps`'te görünmez, uzunluk sınırı yoktur.
- Sabit bayraklar: `--permission-mode acceptEdits`,
  `--allowedTools Read,Write,Edit,Bash,Glob,Grep`, istenirse `--model <model>`.
  `--permission-mode bypassPermissions` **asla** kullanılmaz.
- Birleşik stdout+stderr **maskelenerek** `~/.orkestra/runs/<task_id>-<zaman>.log`
  dosyasına yazılır (dizin 0700, dosya 0600). `rapor` bu yolu gösterir, metni maskeli basar.
  Çıktı 5 MiB'yi aşarsa dosyanın sonu tutulur, başa `[kırpıldı]` notu düşer.
- **Ajan tanımı**: `<cwd>/.claude/agents/<ajan>.md` ya da `~/.claude/agents/<ajan>.md` varsa
  `claude`'a iletilir. Bu ortamda `--agent` bayrağı desteklendiği için **ajan adı** `--agent`
  ile geçilir; `--agent` yoksa dosya gövdesi (frontmatter hariç) `--append-system-prompt`
  ile verilir. Tanım dosyası **yoksa yalnızca istem gönderilir** ve log'un **ilk satırına**
  `[uyari] ajan tanimi bulunamadi: <ad> (yalnizca istem gonderildi)` yazılır — davranış
  değişmez, ama eksik talimat kaydı görünür olur.
- **Zaman aşımı**: süre dolarsa süreç *grubu* önce `SIGTERM`, 5 sn sonra `SIGKILL` ile
  öldürülür (çocuk süreç bırakılmaz). Sonuç `hata="zaman-asimi"`, çıkış kodu 124.
  Yeniden denemez; kullanıcı `orkestra tekrar` diyebilir.
- **Yeniden deneme yalnızca ağ hatalarında**: 502/503/504, `ECONNRESET`, `ETIMEDOUT`,
  `ENOTFOUND`, `EAI_AGAIN`, `socket hang up`, `Unable to connect`, `network error`,
  `fetch failed`. Üstel geri çekilme 2/4 sn, en fazla 3 deneme; sonunda `hata="ag-hatasi (3 deneme)"`.
- **İzin reddi asla yeniden denemez ve asla aşılmaz**: çıktıda izin/sınıflandırıcı reddi
  kalıbı varsa görev `onay-bekliyor` olur. Reddi anlatan satırlar log'da kalır.

Kuyruk tarafında `bekliyor → calisiyor` geçişi **atomiktir** (tek `UPDATE ... WHERE durum='bekliyor'`
+ `rowcount` kontrolü); iki süreç aynı anda çalıştırırsa aynı görevi ikisi birden alamaz.

## Durum makinesi

`bekliyor` → `calisiyor` → `bitti` | `hata` | `onay-bekliyor` | `iptal`

`onay-bekliyor` → `bekliyor` | `iptal`, `hata` → `bekliyor` (yeniden deneme).
`bitti` ve `iptal` son durumlardır. Geçersiz geçiş `GecersizGecis` fırlatır, DB değişmez.

## Kota (Dalga C)

Kaynak: cor'un **`proxy.log`** dosyası (varsayılan `/root/.claude-openrouter/proxy.log`).
Gerçek log biçimi şudur (istem/anahtar **içermez**):

```
[2026-09-30T06:15:25.675Z] openrouter -> stealth/space-bunny-alpha (stream)
[2026-09-26T09:02:11.400Z] openrouter -> nvidia/nemotron-3-ultra-550b-a55b:free
```

Zaman damgası ISO8601 **UTC** (milisaniye, `Z` sonlu); bu yüzden gün sınırı **UTC**'dir.
Ayrıştırıcı **yalnızca bu biçimi** tanır; `proxy dinliyor`, `SIGTERM`, hata gibi diğer
satırları atlar ve **sayar** (`N satır tanınmadı`) — asla uydurma değer üretmez.

- **Artımlı okuma**: son okunan bayt `quota_offsets(kaynak, konum, boyut)` tablosunda durur.
  Dosya küçüldüyse (döndürme/kesme) başa dönülür; **yarım son satır** bir sonraki tura kalır.
- Günlük istek sayıları `quota_snapshots(model, gun, istek, maliyet)` tablosuna yazılır.
  cor log'unda **maliyet bulunmadığı** için `maliyet` her zaman **0**'dır.

**Limitler** `~/.orkestra/kota.toml` dosyasından okunur:

```toml
[limitler]
"nvidia/nemotron-3-ultra-550b-a55b:free" = 50   # hesap-geneli günlük kota
```

Dosya yoksa/bozuksa varsayılan kullanılır: `nvidia/nemotron-3-ultra-550b-a55b:free = 50`.
Durum: yüzde = istek / limit; **≥ %80 `uyari`**, **≥ %100 `asildi`**, limiti olmayan model
`limitsiz`. (Eşikler yüksekten düşüğe denenir; %100 `asildi` verir.)

**Çapraz doğrulama**: cor'un kendi `http://127.0.0.1:8787/dashboard/api/metrics-summary`
ucu ile bugünkü model başı sayılar karşılaştırılabilir (yalnız **okunur**, hiçbir şey yazılmaz).
Bu uç **RAM'de** sayaç tutar ve proxy yeniden başlayınca sıfırlanır; `proxy.log` ise
eklemelidir — bu yüzden "log'un son yeniden başlatmadan sonraki satır sayısı" ile
"metrics toplamı" karşılaştırılmalıdır (dalga C raporunda bu fark ölçülmüştür).

## Web paneli (Dalga C)

```bash
orkestra web --port 8780 --cikti-dizini ~/.orkestra/runs
# -> http://127.0.0.1:8780
```

Panel **yalnızca görüntüler**; iptal/tekrar CLI'dadır (CSRF yüzeyi yok).
Rotalar: `/` (kuyruk), `/gorev/<id>` (görev + koşular + log'un son 200 satırı), `/kota`
(kota kartları + 14 günlük SVG grafik), `/api/gorevler`, `/api/gorev/<id>`, `/api/kota`,
`/saglik`.

### Güvenlik modeli (bağlayıcı)

- **Yalnızca `127.0.0.1`**: adres **koda sabit**; `--host` seçeneği **yoktur**.
- **`Host` doğrulaması**: başlık `127.0.0.1[:port]` / `localhost[:port]` değilse **403**,
  ve reddedilen istek **bağlantı açılmadan** döner (hiçbir sorgu yapılmaz) — DNS rebinding koruması.
- **Salt görüntüleme**: DB `mode=ro` (URI) ile açılır, panel hiçbir koşulda **yazmaz**.
- **Yalnızca GET**: diğer metotlar 405. CSRF yüzeyi yok.
- **Güvenlik başlıkları** (her yanıtta):
  `Content-Security-Policy: default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'`,
  `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store`.
- **Satır içi script/stil yok**: JS/CSS `static/`ten gelir; grafik sıfır-bağımlılık SVG'dir (CDN yok).
- **Güvenilmeyen içerik**: `istem`, `ajan`, `hata` ve log içeriği güvenilmeyendir; Jinja
  autoescape açık, JS `innerHTML` **kullanmaz** (`textContent`), log `<pre>` içinde basılır.
- **Log yolu kaçışı**: DB'deki log yolu yalnız **çözümlenmiş** hâli `--cikti-dizini` ALTINDA
  ise okunur (`resolve()` + `is_relative_to`); `..`, mutlak dışı yol ve **dışarıya sembolik
  link** reddedilir → "log okunamadı".
- **Maskeleme**: ekrana çıkan HER metin (log dahil) `guard.maskele()`'den geçer.
- **Görsel**: koyu tema, **Okabe-Ito** renk körü-güvenli paleti; durum/model renkleri bu
  paletten, rozetler ayrıca **metin** de yazar. 390 px'de tablolar kart olur, yatay
  kaydırma çubuğu çıkmaz; etiketler ≥ 11 px ve birbirini kesmez.

## Ekran görüntüleri

`docs/ekran/` altındaki görüntüler **kurgusal** veriyle üretilmiştir (gerçek yol/anahtar/
e-posta yok). Yeniden üretmek için:

```bash
PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers python3 scripts/ekran_goruntusu.py
```

| Dosya | Ne gösterir |
|---|---|
| `kuyruk-masaustu.png` | Kuyruk tablosu (durum rozetleri, istem önizleme, filtre) |
| `gorev-detay.png` | Görev detayı: alanlar, koşular, log'un son satırları |
| `kota-masaustu.png` | Kota kartları + son 14 günün günlük istek grafiği (limit çizgisi) |
| `kuyruk-mobil.png` | Kuyruk 390 px'te kart görünümü |
| `kota-mobil.png` | Kota 390 px'te kart + grafik |

## Güvenlik (genel)

Görev metni anahtar/`.env` kalıbı içeremez; reddedilen metin hata mesajına **yansıtılmaz**
(maskelenir). `sk-` anahtar kalıbı sol sınırdan başlar ve eşleşen parçada en az bir rakam
ister; böylece `flask-sqlalchemy-migrate-extension` gibi meşru paket adları yanlış
pozitif üretmez. Runner çıktısı, koşu hatası ve kanıt yolları kayda **maskelenerek** yazılır.
`orkestra/runner.py` içindeki `FakeRunner` kurgusal bir çalıştırıcıdır — testler `claude`
yerine sahte bir betik kullanır.

## Testler

```bash
python3 -m pytest -q                    # birim + Flask test-client (varsayilan)
python3 -m pytest -q -m e2e             # Playwright, gercek orkestra web süreci
```

e2e testleri sayfaların çizildiğini, konsol/`pageerror` **boş** olduğunu, XSS yükünün
çalışmadığını (`window.__xss` tanımsız), 1440×900 ve 390×844'te **yatay kaydırma olmadığını**,
metinlerin kırpılmadığını, beyaz varsayılan kontrol bulunmadığını, kontrastın ≥ 4.5:1
olduğunu ve SVG etiketlerinin okunaklı/kutuda kaldığını doğrular.
