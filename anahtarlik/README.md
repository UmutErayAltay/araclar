# anahtarlik

Tüm repolardaki gizli anahtarları (API key / token / parola) tarar ve **tek envanterde**
toplar: anahtarın **adı**, hangi dosyada olduğu, ve **tuzlu parmak izi**. Repoları okur,
**hiçbirine yazmaz**. Yalnız Python standart kütüphanesi (Python 3.11+).

## Ne yapar

`.env*` dosyalarındaki `AD=deger` satırlarını okur, `deger`'i `sha256(tuz + deger)` ile
özetleyip **ilk 8 hex karakteri** (`3fa1c09e` gibi) saklar ve ham değeri hemen bırakır.
Ekran, JSON, hata mesajı ve hook çıktısı — hiçbirinde ham değer yoktur, yalnız **ad + iz**.
Aynı parmak izi iki repoda birden görünürse aynı sırdır: tek kazada ikisi birden yanar;
tablonun altındaki `ayni deger` sayacı bunu listeler.

İki sınır, sözleşmenin parçası:

- **Tuz makineye özeldir** (`ANAHTARLIK_DIR/tuz`, varsayılan `~/.anahtarlik/tuz`, 0600).
  Bu yüzden izler **makineler arası karşılaştırılamaz**; envanteri başka yere göndermek
  karşı tarafa doğrudan eşleştirme imkânı vermez.
- **8 karakterden kısa değerler iz almaz**, `kisa` olarak görünür — 8 karakterlik alfabe
  kaba kuvvetle bulunur.

## Kurulum

```bash
cd anahtarlik
pip install -e .            # ya da kurulum yapmadan: python -m anahtarlik
gh auth login               # yalnız `fark` için: GitHub CLI
```

`fark` dışındaki hiçbir komut `gh` ya da git gerektirmez.

## Kullanım

```bash
# Tüm repoları tara (varsayılan: atlas DB'deki yollar)
anahtarlik tara
anahtarlik tara --root ~/Documents/projeler --root ~/Desktop
anahtarlik tara --atlas-db /yol/atlas.db --json

anahtarlik goster           # son envanteri göster (yeniden taramaz)

# Rotasyon takibi
anahtarlik not OPENAI_API_KEY --tarih 2026-09-01 --aciklama "donduruldu"
anahtarlik eski --gun 90    # notu olmayan ya da 90 günü geçmiş anahtarlar

# GitHub ile fark (gh gerekir)
anahtarlik fark --repo ~/Documents/projeler/ornek-api
```

Repo listesi verilmezse atlas DB'den gelir (`ATLAS_DB` veya `~/.atlas/atlas.db`).
Envanter `~/.anahtarlik/envanter.json`, rotasyon notları `notlar.json`'a yazılır —
`ANAHTARLIK_DIR` verilirse o dizin kullanılır. Yazma atomiktir (geçici dosya + `os.replace`); `goster` yalnız okur.

`not` anahtar **adına** göre çalışır; aynı ada ikinci not eskisinin üstüne yazar.

## `fark`: dört küme

GitHub API **değer vermez**, yalnız ad karşılaştırılır. `gh secret list` sadece isim
döndürür; değeri okumaya çalışılmaz.

| Küme | Anlamı |
|---|---|
| `workflow_var_gh_yok` | **Workflow kullanıyor, GitHub'da TANIMSIZ — CI kırılır.** En önemlisi |
| `gh_var_workflow_kullanmiyor` | GitHub'da tanımlı, hiçbir workflow kullanmıyor (ölü secret) |
| `yerel_var_gh_yok` | Yerel `.env`'de var, GitHub'da yok |
| `gh_var_yerel_yok` | GitHub'da var, yerel `.env`'de yok (CI'da çalışıyor, lokalde yok) |

`GITHUB_TOKEN` workflow'lardan çıkarılır ama karşılaştırmaya katılmaz (GitHub her
push'ta kendi üretir). **Render v1'de yok** — bilinçli: Render API anahtarı da ayrı bir
sır olurdu ve bu dört kümeye hiç girmezdi.

## Hook (push sızıntısı engeli)

```bash
anahtarlik hook-kur --repo ~/Documents/projeler/ornek-web
anahtarlik hook-kur --repo . --uygula
anahtarlik hook-kur --repo . --uygula --ortak
```

**Varsayılan kuru çalıştırma**: `--uygula` verilmedikçe dosya sistemine hiç dokunulmaz,
sadece yapılacak iş bildirilir.

- **Yabancı bir `pre-push` varsa ASLA üstüne yazılmaz** (`yabanci-hook-var`). Kendi
  hook'unuz zaten varsa `guncel` der, tekrar yazmaz (idempotent).
- **`core.hooksPath` repo dışını gösteriyorsa** (genelde global ayar) o dizin **TÜM
  repolarda** çalışır; bu yüzden `--ortak` verilmeden oraya yazılmaz
  (`ortak-hooks-dizini`).
- **Tuzak:** global `core.hooksPath` varken `.git/hooks/pre-push`'a kurulan hook git
  tarafından **hiç çalıştırılmaz** — sessizce hiçbir koruma olmaz. `hook-kur` çıktısındaki
  `yol`/`hooks_dizini` alanları hangi dizine yazılacağını gösterir; önce ona bakın.

Hook kendi hatasında push'u engellemez: git okunamazsa bulgu yok sayılır, python
bulunamazsa stderr'e açık uyarı yazılır (`push taranmadan gonderildi (koruma KAPALI)`).
Bulgular yalnız `dosya:satir tur [maskeli:tur]` biçimindedir; diff çıktısı modülün
içinde kalır, hiçbir hata mesajına girmez.

Hook modülü depo kökünden değil, kurulumda yazılan **mutlak yoldan** ve `python -P` ile
yükler: push edilen depoda `anahtarlik/` adlı bir klasör olsa bile o çalıştırılmaz.

`.env` dosyasının push'a girmesi **kendisi bir bulgudur**; içeriği okunmaz, satırları
taranmaz. Bulgu varsa push engellenir; geçici olarak `git push --no-verify` ile atlanır.

## Durumlar (hook-kur) ve çıkış kodları

| Durum | Anlamı | Çıkış |
|---|---|---|
| `yok` | Kurulacak, yazılmadı (kuru çalıştırma) | `0` |
| `yazildi` | Hook yazıldı | `0` |
| `guncel` | Zaten güncel | `0` |
| `eski-surum` | Bizim hook'un eski (güvensiz) sürümü; `--uygula` yeniler | `2` |
| `yabanci-hook-var` | Yabancı hook var — üstüne yazılmadı | `2` |
| `simgeler` | `pre-push` bir sembolik bağ; üstüne yazılmadı | `2` |
| `ortak-hooks-dizini` | Global hooks dizini; `--ortak` gerekli | `2` |
| `git-depo-degil` | Verilen yol git deposu değil | `2` |
| `okunamadi` / `yazilamadi` | Dosya okunamadı / yazılamadı | `2` |

| Kod | Anlamı |
|---|---|
| `0` | Başarı — `tara`/`goster`/`not`/`eski`/`fark` tamam |
| `1` | **Yalnız `hook-tara`**: push'ta gizli anahtar izlenimi var, push engellendi |
| `2` | Kullanım/keşif hatası: repo yok, atlas DB yok, envanter dosyası okunamaz/yazılamaz, `fark` için `gh` yok ya da origin github.com değil |

`fark` durumları: `tamam` (0), `github-degil`, `gh-yok`, `hata` → `2`.

## Dürüstlük ve güvenlik notu

- **Eşit parmak izi "aynı değer" demektir** — aynı makinede, aynı tuzla. Ama 8 hex
  karakterde çarpışma olasılığı sıfır değildir; iki farklı değer teorik olarak aynı izi
  verebilir. Karar verirken "büyük olasılıkla aynı", kesin değil.
- **Tuz dosyası kaybolursa** üretilen yeni izler eskilerle **anlamsızlaşır**: aynı değer
  artık farklı iz görünür, `ayni deger` sayacı sessizce boşalır. Tuzu yedekleyebilirsiniz,
  ama paylaşmayın.
- **Ağ yalnız `fark`'ta**, orada da sadece `gh` üzerinden. `tara`, `goster`, `not`, `eski`
  ve hook tamamen çevrimdışı çalışır.
- **Kapsam dar:** yalnız `.env*` dosyalarındaki `AD=deger` satırları. Kaynak kodun içine
  gömülü anahtarlar, `package.json`/kilit dosyaları, üretim ortamı değişkenleri bu
  sürümde kapsam dışıdır. Repo kökünden 4 dizin derinliğine kadar iner, `.git`,
  `node_modules`, `.venv`, `dist` vb. atlanır, 1 MB'den büyük dosya okunmaz.

## Testler

```bash
python -m pytest -q
```