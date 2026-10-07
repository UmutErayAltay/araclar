# servis

Yerel servis yığınını (`cor`, `kule`, `liman`, `readbunny-postgres`) tek komutla başlatır, durdurur ve durumunu gösterir. Yalnız Python standart kütüphanesi (3.11+, `tomllib` dahil). **Kabuk çalıştırmaz** — `baslat`/`durdur` argv listeleri olduğu gibi `subprocess`'e gider, `/bin/sh -c` hiçbir zaman devreye girmez.

Varsayılan tanım yolu: `SERVIS_TANIM` ortam değişkeni, yoksa `~/.servis/servisler.toml`.

## Kurulum ve kullanım

```bash
cd servis && pip install -e .    # ya da kurulum yapmadan: python -m servis

cp servisler.toml.ornek ~/.servis/servisler.toml   # tanım dosyasını hazırla

servis durum                      # tüm servisler: port + pid + sağlık
servis durum cor liman            # yalnız bu ikisi
servis baslat                     # zaten çalışanlar atlanır
servis durdur                     # yalnız kendi pid dosyamızdakiler
servis baslat --kuru              # ne yapılacak? (hiçbir şey başlatmaz)
servis durdur cor --zorla         # SIGTERM'e yanıt vermeyene SIGKILL
servis durum --json               # tablo yerine JSON
servis durum --tanim /yol/servisler.toml
```

Ad verilmezse tüm tanımlı servisler alfabetik sırayla işlenir.

## Tanım dosyası

Her servis bir `[servis.<ad>]` tablosudur:

| Alan | Zorunlu | Anlamı |
|---|---|---|
| `port` | evet | 1-65535, servisin dinlediği yerel port (127.0.0.1 üzerinden yoklanır) |
| `baslat` | evet | argv listesi, kabuk yok |
| `cwd` | hayır | çalışma dizini; `~` açılır |
| `durdur` | hayır | verilirse pid sinyali yerine bu komut çalışır (örn. `["cor","stop"]`) |
| `bekle_sn` | hayır | port açılana kadar beklenecek saniye (varsayılan 20) |
| `saglik_url` | hayır | varsa GET ile yoklanır; 200-399 sağlıklı sayılır. **Yalnız 127.0.0.1/localhost** adreslerine gider |

```toml
[servis.cor]
port = 8787
baslat = ["cor", "start"]
cwd = "~/projeler/cor"
durdur = ["cor", "stop"]
saglik_url = "http://127.0.0.1:8787/health"
```

Servis adı bir dosya yoluna dönüşemez: boş, `.`, `..`, `/` veya `\` içeren adlar reddedilir.

## Durumlar

| `durum` | Anlamı |
|---|---|
| `calisiyor` | Port açık **ve** bizim pid dosyamızdaki süreç yaşıyor |
| `durdu` | Port kapalı |
| `port-dolu-bilinmeyen` | Port dolu ama bizim pid dosyamız yok ya da o pid ölmüş — **başkası kullanıyor olabilir, BUNA DOKUNULMAZ** |

`saglik` sütunu: `saglikli`, `sagliksiz`, ya da tanımda yoksa `-`.

## Güvenlik

Bunlar sözleşmedir, kod bunları zorlar:

- **Durdurma yalnız kendi pid dosyasındaki süreci yapar.** `~/.servis/pid/<ad>.pid` yoksa hiçbir sürece sinyal gönderilmez.
- **Port dolu ama bizim pid dosyamız yoksa hiçbir şey yapılmaz** — ne `durdur`, ne `baslat` o portu tutan yabancıya dokunur.
- **Pid yeniden kullanımı korunur:** Linux'ta öldürmeden önce `/proc/<pid>/cmdline` tanımdaki `baslat[0]` ile karşılaştırılır; uyuşmazsa dokunulmaz (`pid-cmdline-uyusmuyor`).
- **Ölmüş pid'e sinyal gönderilmez** — pid yeniden kullanılmış olabilir; `zaten durdu` sayılır.
- **Keyfi süreç öldürme yok.** SIGTERM, 10 sn bekle, hâlâ ayaktaysa **yalnız `--zorla`** ile SIGKILL.
- **Zombie süreç "yaşıyor" sayılmaz** — `os.kill(pid, 0)` buna hata vermez, `SERVIS_DIZINI` yazan kodu bu yüzden `/proc/<pid>/stat` durum alanını da okur.
- **`--kuru` hiçbir şey yapmaz**, ne başlatır ne öldürür; ne pid ne log dosyası yazar.
- Başlatılan süreç `start_new_session=True` ile kendi grubunu alır; durdurmada süreç grubuna sinyal gider, böylece servisin alt süreçleri de kapanır.
- `saglik_url` yalnız `127.0.0.1`/`localhost` adreslerine gidebilir (proxy kullanılmaz), dış ağa çıkılmaz.

## Dizinler ve ortam değişkenleri

Varsayılan `~/.servis/` altında: `pid/<ad>.pid` ve `log/<ad>.log` (başlangıçta stdout+stderr buraya akar).

| Değişken | Anlamı |
|---|---|
| `SERVIS_TANIM` | Tanım dosyası yolu (yoksa `~/.servis/servisler.toml`) |
| `SERVIS_DIZINI` | pid/log dizini (yoksa `~/.servis`) |

`--tanim` her ikisini de geçersiz kılar.

## Çıkış kodları

| Kod | Anlamı |
|---|---|
| `0` | İstenen tüm servisler hedef durumda |
| `1` | En az biri hedefte değil (`durdu`, `basarisiz`, `durmadi`, …) |
| `2` | Kullanım/tanım hatası: tanım dosyası yok, bozuk TOML, geçersiz alan, tanımsız servis adı |

Hatalar `Hata: ...` biçiminde **stderr**'e yazılır; traceback basılmaz.

## Testler

```bash
python -m pytest -q
```

Gerçek servisler (cor/kule/liman/postgres) **hiçbir testte çalışmaz**. Testler `python3 -m http.server` ve `python3 -c` kullanır, portlar `socket.bind(0)` ile boş seçilir; tanım dosyası ve `SERVIS_DIZINI` `tmp_path`'e yönlendirilir. Ağ yoktur. Başlatılan her süreç `finally` ile temizlenir.