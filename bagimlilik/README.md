# bagimlilik

Tüm repolarda `pip-audit` ve `npm audit` çalıştırıp **tek raporda** toplar. Repoları
okur, **hiçbirine yazmaz**. Yalnız Python standart kütüphanesi (Python 3.11+).

## Ne yapar

`bagimlilik tara` verdiğiniz kökleri gezer, içindeki her git reposunu bulur (derinlik 3)
ve her repodaki pip/npm manifestlerini denetler:

| Bulunan | Nasıl denetlenir |
|---|---|
| `requirements*.txt` | `pip-audit -r` ile **yerinde okunur** |
| `pyproject.toml` | `[project].dependencies` geçici bir requirements dosyasına yazılır, o denetlenir |
| `package.json` + kilidi | `npm audit` **geçici dizinde** çalışır |
| `.csproj`, `build.gradle*`, `go.mod`, `Cargo.toml`, `pom.xml` | yalnız **listelenir**, denetlenmez |

Repo listesi verilmezse atlas DB'den gelir (`ATLAS_DB` veya `~/.atlas/atlas.db`).
Kök bir repo değil ama kendisi projeyse (requirements/pyproject/package.json) kendisi sayılır.

## Kurulum

```bash
cd bagimlilik
pip install -e .            # ya da kurulum yapmadan: python3 -m bagimlilik
pip install pip-audit       # pip tarafı için dış araç (kurulu değilse 'arac-yok' çıkar)
```

npm tarafı için Node/npm gerekir. İkisi de yoksa rapor hata değil, `denetlenemedi` olur.

## Kullanım

```bash
# Tüm repoları tara (varsayılan: atlas DB'deki yollar)
bagimlilik tara
bagimlilik tara --root ~/Documents/projeler
bagimlilik tara --root ~/Desktop --root ~/Projeler --paralel 8 --zaman-asimi 300
bagimlilik tara --atlas-db /yol/atlas.db --json

# Son raporu göster (yeniden denetlemez)
bagimlilik goster
bagimlilik goster --json
```

Rapor `~/.bagimlilik/son.json`'a yazılır (`BAGIMLILIK_DIR` ile dizin değişir).
Yazma atomiktir (geçici dosya + `os.replace`); `goster` yalnız bu dosyayı okur.

Gerçek çıktı (kısaltılmış — aradaki satırlar atlanmıştır):

```console
$ python3 -m bagimlilik goster
tarih: 2026-10-02T23:05:59+00:00
repo                       kaynak                             durum                       K  Y   O   D   toplam
Anlat                      pip:requirements.txt               temiz                       0  0   0   0   0
BlogSitesi                 npm:blog-frontend/package.json     acik                        3  35  17  14  69
GeminiEklenti              npm:package.json                   acik                        1  14  5   2   22
borsa projesi              pip:requirements-web.txt           temiz                       0  0   0   0   0
readbunny                  pip:requirements.txt               acik                        ?  ?   ?   ?   10
cor                        npm:package.json                   acik                        1  1   3   0   5
araclar                    pip:harita/requirements.txt        temiz                       0  0   0   0   0
  ... (arada atlanan satırlar) ...
ITRequest                  npm:package.json                   acik                        6  16  9   1   32
    - @babel/core  [dusuk] GHSA-4x5r-pxfx-6jf8 -> mevcut
    - @babel/plugin-transform-modules-systemjs  [yuksek] GHSA-fv7c-fp4j-7gwp -> mevcut
ozet: 39 repo -> 12 temiz, 7 acikli, 0 denetlenemedi, 20 manifestsiz  (K/Y/O/D = kritik/yuksek/orta/dusuk; ? = pip-audit siddet vermez)
```

`readbunny` satırındaki `?` pip-audit'in şiddet vermediğidir (aşağıda). Açık
denetimlerin altında en fazla 3 bulgu listelenir; tamamı `--json` çıktısındadır.

## Durumlar

Her satır bir **denetlenen manifest'i** gösterir (`denetim`), repo değil.

| Durum | Anlamı |
|---|---|
| `temiz` | Denetim çalıştı, açık bulunmadı |
| `acik` | Açık bulundu (bulgu sayısı `toplam` sütununda) |
| `denetlenemedi(neden)` | **Denetim yapılamadı** — sonuç yok, temiz demek değil |

`neden` değerleri:

| Değer | Anlamı |
|---|---|
| `arac-yok` | pip-audit veya npm bulunamadı |
| `zaman-asimi` | `--zaman-asimi` saniyesinde bitmedi |
| `kilit-yok` | `package.json` var, `package-lock.json` yok |
| `cikti-bozuk` | Arac JSON'u ayrıştırılamadı |
| `hata` | Beklenmeyen hata (tek repo taramayı düşürmez) |

Özet satırındaki `manifestsiz` = **hiç denetim üretmemiş** repo. İki sebeple olur:
manifest hiç yok (ör. yalnız `.md` dosyası olan repo) **ya da** manifest var ama
denetlenemeyen ekosistemde (ör. yalnız `go.mod`/`pom.xml`). İkinci hâlde dosya adı
JSON'daki `desteklenmeyen` listesinde görünür.

## Dürüstlük kuralları

Bunlar sözleşmedir, kod bunları zorlar:

- **`denetlenemedi` asla `temiz` sayılmaz.** Özet sayacı ikisini ayrı tutar.
- **Karar aracın çıkış kodundan değil, stdout JSON'undan çıkar.** `pip-audit` açık
  bulunca `1` döner; bu bir denetim sonucudur, hatadır. bagimlilik bu kod bakmaz,
  JSON ayrıştırılabiliyorsa denetimi başarılı sayar ve `0` döner.
- **`pip-audit` şiddet vermez.** Açık bulsa da kritik/yüksek/orta/düşük sayamaz; bu
  dört sütun `?` çıkar. Gerçek şiddet yalnız npm tarafında vardır.
- **npm `toplam` ile listelenen bulgu sayısı farklı olabilir.** `toplam` npm'nin
  kendi sayımıdır; liste yalnız gerçek bildirimi olan kayıtları içerir (zincir
  girdileri hariç).

## Çıkış kodları

| Kod | Anlamı |
|---|---|
| `0` | Tarama tamam — **açık bulmak de hata değildir** |
| `2` | Kullanım/keşif hatası: repo bulunamadı, atlas DB yok, geçersiz değer, rapor yok |

## Güvenlik notu

- **Repolara hiçbir şey yazılmaz.** `requirements.txt` `-r` ile yerinde *okunur*.
  `pyproject` bağımlılıkları ve `package.json`/`package-lock.json` kopyaları
  `tempfile` ile açılan geçici dizine yazılır, `npm audit` orada çalışır. `node_modules`
  kurulmaz, kilit dosyası değişmez.
- **Amaçları ağa çıkar.** atlas'ın "ağsız" sözleşmesinin tam tersi: bu araç bilerek
  `pip-audit` (PyPI advisory) ve `npm audit` (npm registry) üzerinden dışarı çıkar.
  Kurulum sırasında paketler indirilir. Ağsız çalışması gerekiyorsa bu araç değil,
  atlas'tur.
- `--progress-spinner off` **şarttır**: pip-audit'in ilerleme metni stdout'a karışıp
  JSON çıktısını bozuyor. Elle çağırıyorsanız da ekleyin.
- Atlas DB `mode=ro` ile açılır — yazmaz, şema kurmaz.
- Tek bir repo çökerse tarama düşmez; o satır `denetlenemedi(hata)` olur, çıkış kodu
  yine `0`'dır.
- Bir denetim zaman aşımına uğrarsa o denetim `zaman-asimi` olur; diğer repolar
  etkilenmez. Kısmi sonuç gösterilmez — o denetim için hiçbir bulgu raporlanmaz.

## Kule paneli

Kule'de bu araç için bir kart var (`app/collectors/bagimlilik_status.py`). Kart
`bagimlilik` aracını çalıştırmaz, yalnız rapor dosyasını (`~/.bagimlilik/son.json`)
okur. `config.yaml`:

```yaml
bagimlilik:
  dosya: "~/.bagimlilik/son.json"
```

Kart yalnız **sayı ve zaman** gösterir: taranan repo, açıklı repo, kritik+yüksek
toplamı, denetlenemeyen denetim sayısı ve son taramanın yaşı. Paket adı, açık
kimliği ve dosya yolu kule'ye girmez. Rapor henüz yoksa kart "erişilemiyor" der,
panel düşmez, Telegram uyarısı da üretilmez. Tarama kule'den tetiklenmez;
`bagimlilik tara` elle (ya da zamanlanmış bir görevle) çalıştırılır.

## Testler

```bash
python3 -m pytest -q
```
