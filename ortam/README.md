# ortam

Ortam değişkeni denetçisi. Kodun okuduğu ortam değişkenlerini **çıkarır**,
`.env.example` / README / `docker-compose` ile **karşılaştırır** ve
eksik–fazla eşleşmeleri tabloya döker. **Salt okunurdur** — hiçbir komut dosya
yazmaz, silmez veya düzenlemez. Yalnız Python standart kütüphanesi (3.11+).

**Değişken değerleri hiçbir zaman okunmaz, hiçbir çıktıya girmez.** Yalnız
**ad**, **dosya:satır** ve bulgu türü raporlanır. `--uygula` bayrağı **yoktur**:
yazacak eylem olan bir komut bu araçta bulunmuyor.

## Ne yapar

Her repo için iki taraf toplanır ve karşılaştırılır:

| Taraf | Kaynak |
|---|---|
| **Kod** | Python `os.environ["X"]`, `os.environ.get("X"…)`, `os.getenv("X"…)`; JS/TS `process.env.X`, `process.env["X"]`; Go `os.Getenv("X")`, `os.LookupEnv("X")` |
| **Belge** | `.env.example` / `.env.sample` / `env.example` satırları, README'deki büyük-harfli adlar, `docker-compose*.yml` `environment:` girdileri ve `${AD}` referansları |
| **Git** | `git ls-files` (izlenen `.env`), `.gitignore` kapsamı |

`.env.example`'da tanımlı olup **README/compose'de de geçen** adlar yalnız
`belgelenmemis` filtresinde "belgelenmiş" sayılır; `kullanilmayan` filtresi
sadece `.env.example` tanımlarına bakar.

## Bulgu türleri

| Tür | Anlamı |
|---|---|
| `belgelenmemis` | Kodda kullanılıyor, `.env.example`'da **da** README'de **de** adı geçmiyor. Yeni ortam değişkeni eklendi, şablon güncellenmedi |
| `kullanilmayan` | `.env.example`'da tanımlı ama kodda hiç kullanılmıyor (ölü tanım) |
| `env_gitignorede_degil` | Repoda yerel `.env*` dosyası var ama `.gitignore` `.env`'i kapsamıyor — bir `git add .` sızdırır |
| `env_izleniyor` | `git ls-files` içinde gerçek `.env` (örnek olmayan) **izleniyor** — **yüksek önem**, gizli değer depoda |

Genel/standart değişkenler (`PATH`, `HOME`, `USER`, `PWD`, `TMPDIR`, `LANG`,
`CI`, `NODE_ENV`, `TMP`, `TEMP`…) `belgelenmemis` üretmez.

`.env.example`, `.env.sample`, `.env.template` gibi **örnek/sablon** dosyalar
`env_izleniyor` sayılmaz: şablonu commit'lemek normaldir. Gerçek `.env.production`
ise sızıntıdır.

## Kurulum ve kullanım

```bash
cd ortam && pip install -e .    # ya da kurulum yapmadan: python -m ortam

ortam tara --kok ~/Documents/projeler
ortam tara --kok ~/Documents/projeler --kok ~/Desktop
ortam tara --kok ~/Documents/projeler --json
```

`--kok` bir veya birden fazla kök dizin alır, **tekrarlanabilir**. Kökün altında
derinlik 3'e kadar inilerek `.git` klasörü olan repolar bulunur. `node_modules`,
`.git`, `.venv`, `venv`, `__pycache__`, `dist`, `build`, `.pytest_cache`
atlanır; 1 MB'den büyük ve ikili dosyalar okunmaz.

## Gerçek çıktı

```console
$ ortam tara --kok /tmp/ortam_deneme
1 repo bulundu, taraniyor...
tur                    repo  ad            dosya:satir
env_izleniyor          r1    -             .env
env_gitignorede_degil  r1    -             .env
belgelenmemis          r1    MISSING_ONE   app.py:3
kullanilmayan          r1    UNUSED_THING  -
ozet: 4 bulgu, 1 repo
```

`.env` içindeki gerçek değer ne tabloda ne JSON'da ne hata mesajında görünür.

## Çıkış kodları

| Kod | Anlamı |
|---|---|
| `0` | Tarama tamam, **bulgu yok** |
| `1` | Tarama tamam, **en az bir bulgu var** |
| `2` | Kullanım/keşif hatası: `--kok` verilmemiş, yol bulunamadı, repo bulunamadı. `Hata: …` stderr'e yazılır, **traceback basılmaz** |

## Dürüstlük / güvenlik kuralları

Bunlar sözleşmedir, kod bunları zorlar:

- **Salt okunur.** `tara` hiçbir dosyayı yazmaz/silmez; ağaç karmasıyla test edilir.
- **Değerler asla çıkmaz.** `.env` dosyalarının *içeriği hiç okunmaz* — yalnız
  varlıkları/adaları raporlanır. Kaynak koddaki satır da yalnız AD + satır no'ya indirgenir.
- **`git` yalnız okur.** `GIT_OPTIONAL_LOCKS=0` ile index kilitlenmez/yazılmaz.
- **Yazmak isteyen eylem yoktur.** `--uygula` bayrağı bu araçta **yoktur**; kural gereği
  bu araçta hiçbir dosya yazan eylem bulunmaz.
- **Git yoksa bulgu üretilmez.** `git` yoksa/çalışamazsa `env_izleniyor` sessizce boş
  döner — yanlış pozitif üretmektense yokluk tercih edilir.
- **Yorum satırları kapsam dışı.** `# X = os.getenv("X")` bir kullanım değildir; tarandığında
  yanlış pozitif üretirdi.
- **Kapsam dışı:** shell betikleri (`$VAR`), Kubernetes manifestleri, gerçek ortam
  değerleri, CI secret'ları bu sürümde incelenmez.

## Testler

```bash
python -m pytest -q
```

Testler `tmp_path` altında sahte repolar kurar; ağ yok, gerçek `~/` dizinine
yazma yok. Her bulgu türü için pozitif **ve** negatif test vardır.
