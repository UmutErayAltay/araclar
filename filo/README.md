# filo

Bir görev metnini (prompt dosyası) N repoya **paralel** dağıtır; her repo için yerel `cor claude` alt süreci (headless Claude Code, cor proxy üzerinden) çalıştırır, raporları tek klasörde toplar.

Tek seferlik toplu çalıştırıcıdır — kalıcı kuyruk **değildir** (`orkestra/` kuyruğu tutar; filo onunla bağlantı kurmaz). Yalnız Python standart kütüphanesi (3.11+).

## Ne yapar

`--repo` ile verilen dizinlerde, `--kok` ile kök altında derinlik 1-2'de bulunan `.git` klasörü olan dizinlerde çalışır. Her repo için görev metni **stdin**'den alt sürece gider, stdout+stderr tek dosyaya (`<cikti>/<repo_adi>.md`) harmanlanır. Bitişte `<cikti>/OZET.md` yazılır.

## Kurulum ve kullanım

```bash
cd filo && pip install -e .    # ya da kurulum yapmadan: python -m filo

filo calistir --gorev GOREV.txt --repo ~/projeler/a ~/projeler/b
filo calistir --gorev GOREV.txt --kok ~/projeler --paralel 4
filo calistir --gorev GOREV.txt --kok ~/projeler --kuru      # planı göster, hiçbir şey çalıştırma
filo calistir --gorev GOREV.txt --kok ~/projeler --json      # makine-okunur özet
```

Seçenekler:

| Seçenek | Anlamı |
|---|---|
| `--gorev GOREV.TXT` | Zorunlu. Dağıtılacak görev metni dosyası (UTF-8, boş olamaz) |
| `--repo DIZIN` | Tek tek repo (çoklu verilebilir) |
| `--kok DIZIN` | Altındaki repoları keşfet (çoklu verilebilir; derinlik 1-2) |
| `--paralel N` | Paralel alt süreç sayısı, **1..8** (varsayılan 4) |
| `--cikti DIZIN` | Rapor dizini (varsayılan `./filo-ciktilari/<zaman-damgasi>/`) |
| `--model M` | Model (varsayılan `$COR_MODEL`, yoksa `nvidia/nemotron-3-ultra-550b-a55b:free`) |
| `--duzenle` | Yazma/araç çalıştırma yetkisi ver (varsayılan **salt okunur**) |
| `--zaman-asimi SN` | Repo başına zaman aşımı (varsayılan 900) |
| `--cor AD` | `cor` komutu (varsayılan `cor`) |
| `--kuru` | Hiçbir alt süreç başlatmadan hangi repoda hangi argv'nin çalışacağını göster |
| `--json` | Özeti stdout'a JSON olarak yaz |

En az biri `--repo` ya da `--kok` zorunludur; ikisi de yoksa hata (çıkış 2). Varsayılan çıktı dizini yoksa oluşturulur; **mevcüt dosya üzerine yazılmaz** — aynı ad varsa hata.

## Gerçek çıktı

Üç repo: ikisi ok, biri alt süreç hatası verdi (`exit 3`), biri zaman aşımına uğradı.

```console
$ filo calistir --gorev GOREV.txt --kok ~/projeler --cikti /tmp/filo-cikti
3 repo, paralellik 4, araclar: Read,Glob,Grep
repo                durum         sure(sn)  rapor              boyut
atlas               ok            12.41      /tmp/filo-cikti/atlas.md   4.1 KB
harita              hata          3.02       /tmp/filo-cikti/harita.md  312 B
liman               zaman-asimi   900.11     /tmp/filo-cikti/liman.md   0 B

ozet: {'toplam': 3, 'ok': 1, 'hata': 1, 'zaman-asimi': 1}
cikti: /tmp/filo-cikti
ozet dosyasi: /tmp/filo-cikti/OZET.md
```

`OZET.md` aynı tabloyu Markdown olarak, hata satırlarıyla birlikte saklar. `--json` aynı bilgiyi stdout'a verir:

```console
$ filo calistir --gorev GOREV.txt --repo ~/projeler/a --json
{
  "surum": 1,
  "tarih": "2026-10-05T11:02:44+00:00",
  "cikti": "/home/user/projeler/filo-ciktilari/2026-10-05T11-02-44Z",
  "kuru": false,
  "ozet": {"toplam": 1, "ok": 1, "hata": 0, "zaman-asimi": 0},
  "sonuclar": [
    {"repo": "/home/user/projeler/a", "ad": "a", "durum": "ok", "sure_sn": 8.02,
     "rapor": ".../a.md", "rapor_boyut": 1802, "cikis_kodu": 0, "hata": null}
  ],
  "ozet_dosyasi": ".../OZET.md"
}
```

## Dürüstlük / güvenlik kuralları

Bunlar sözleşmedir, kod bunları zorlar:

- **Varsayılan salt okunurdur**: izinli araçlar `Read,Glob,Grep`. Yazma ancak `--duzenle` ile açılır (`Read,Write,Edit,Bash,Glob,Grep`).
- **`--dangerously-skip-permissions` ve `bypassPermissions` ASLA kurulamaz.** `argv_olustur()` diziyi kurar, sonra yasaklı dizeleri tarar; bulursa hata fırlatır (sessizce geçmez). Testler bunu doğrular.
- **commit / push / checkout yapılmaz.** Görev metni alt sürece olduğu gibi aktarılır; kurulumda böyle bir komut eklenmez. İzin kipi `acceptEdits`'tir, bypass değildir.
- **`shell=False`, argv listesi** — kabuk yorumlaması, `;`/`|` enjeksiyonu yoktur.
- **Zaman aşımında süreç grubu öldürülür**: önce SIGTERM, 5 sn sonra SIGKILL. Uyanan alt süreç ana süreci asılı bırakmaz.
- **Hata izolasyonu**: bir repo hata verse ya da zaman aşımına uğrase diğerleri çalışmaya devam eder; sonuç o satırda `hata`/`zaman-asimi` olur.
- **Üst sınır `--paralel 8`**: ücretsiz modellerin kotasını korumak için. 8 üstü reddedilir (çıkış 2). Sınır denetimi `--kuru` yolunda da çalışır: kuru çalıştırma da geçersiz bir paralelliği sessizce kabul etmez.
- **`--kuru` hiçbir alt süreç başlatmaz** ve çıktı dizini yaratmaz.
- **Mevcut dosya üzerine yazılmaz** — rapor ya da `OZET.md` adı çakışırsa hata (çıkış 2). İki repo aynı ada sahipse de hata verilir.
- **Raporda gizli değer yoktur**: özet yalnızca repo yolu, durum, süre, rapor dosyası ve boyut tutar; alt sürecin ham metni sadece kendi dosyasında kalır.

## Durumlar

| `durum` | Anlamı |
|---|---|
| `ok` | Alt süreç çıkış kodu 0 |
| `hata` | Alt süreç sıfırdan farklı bitti, ya da `cor` çalıştırılamadı (kayıp/izin) |
| `zaman-asimi` | `--zaman-asimi` doldu; süreç grubu öldürüldü |

## Çıkış kodları

| `0` | Hepsi `ok` |
| `1` | Biri bile `hata` ya da `zaman-asimi` |
| `2` | Kullanım/kesif hatası: `--repo`/`--kok` yok, yol bulunamadı, görev dosyası okunamadı/boş, `--paralel` 1..8 dışı, çıktı adı çakışması |

Hata mesajları `Hata: ...` ile stderr'e yazılır; **traceback basılmaz**.

## Kapsam dışı

`filo` bir kuyruk değildir: görev önceliği, kota takibi, kalıcı durum, yeniden deneme politikası yoktur. Bir repo çökerse o iş **yeniden çalıştırılmaz** — çıktı dizinindeki rapor elle incelenir.

## Testler

```bash
python -m pytest -q
```

Gerçek `cor` **yoktur**: her test geçici dizinde (tmp_path) sahte repolar ve sahte bir `cor` betiği kurar (sabit rapor yazan, `exit 3` veren, `exit 9` veren, uyuyan). Ağ yoktur, gerçek git çalıştırılmaz, yazma etkileri yalnızca `tmp_path` altındadır.