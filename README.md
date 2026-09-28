# anlat

Bir **git deposunu** tarayıp, o deponun hikâyesini çıkaran bir araç: commit geçmişi,
bağımlılık dosyalarının değişiklikleri ve dokümanlardan **Türkçe yazılı teknik
anlatı** üretir. `sesli` komutuyla aynı anlatıyı NotebookLM'e kaynak olarak ekleyip
gerçek bir **sesli özet (Audio Overview)** de hazırlar.

Yazılımın nasıl doğduğunu, hangi teknolojinin ne zaman ve neden seçildiğini
duymak istiyorsan bu araç tam senin için.

---

## Kurulum

Python 3.11+ ve `git` gerekir. Python tarafında üçüncü parti paket yoktur; tüm
ağ çağrıları standart kütüphanenin `urllib`'i ile yapılır.

```bash
pip install -r requirements.txt
```

## Kullanım ÖNCESİ: NotebookLM köprü sunucusu

> ⚠️ **Önemli mimari karar:** Bu repo NotebookLM'i kendisi çalıştırmaz, tarayıcı
> otomasyonu yapmaz, Google'a bağlanmaz. NotebookLM otomasyon paketi
> (`@roomi-fields/notebooklm-mcp`) bu reponun içine **vendor'lanmamıştır** ve
> kaynak kodu burada bulunmaz. Sen kendi makinende ayrıca kurup bir HTTP
> sunucusu olarak çalıştırırsın; bu repo yalnızca o sunucuya HTTP istekleriyle
> konuşan ince bir Python istemcisidir.

Köprü sunucusunu **kendi makinende, ayrı bir terminalde** kur ve çalıştır:

```bash
npm install @roomi-fields/notebooklm-mcp   # bir kerelik
npm run setup-auth                        # BİR KERELİK: tarayıcı açılır, elle Google girişi yapılır
npm run start:http                        # her kullanımdan önce ayakta olmalı (varsayılan http://127.0.0.1:3000)
```

`npm run start:http` çalışırken terminali açık bırak. `anlat` komutunu bu
süreçte başka bir terminalden çalıştır.

`setup-auth` gerçek bir Google giriş akışıdır ve tarayıcı gerektirir; bu
projedeki hiçbir komut onu tetiklemez, sadece sen elle başlatırsın.

### Güvenlik ve sorumluluk

* `@roomi-fields/notebooklm-mcp` **üçüncü parti, bağımsız bir projedir**. Bakım
  durumu ve güvenlik geçmişi (CVE) senin sorumluluğundadır; kullanmadan önce
  kendi gözünle incele ve sürümünü sabitle.
* Bu paket Google'ın *dahili* arayüzlerini tarayıcı otomasyonuyla sürer. Bu
  Google'ın hizmet şartlarıyla çelişebilir ve hesabınla ilgili sonuç doğurabilir.
  Sorumluluk tamamen sendedir.
* Sunucu varsayılan olarak `0.0.0.0` üzerinden dinler; yalnızca kendi
  makinende kullanıyorsan `HTTP_HOST=127.0.0.1` ile daralt.

---

## Komutlar

### `anlat` — yazılı anlatı

```bash
python3 cli.py anlat <repo-yolu> [--out DOSYA.md]
```

Depoyu tarar, yazılı teknik anlatıyı üretir ve `<repo-yolu>/ANLATI.md` dosyasına
yazar. NotebookLM'e ihtiyaç duymaz.

```bash
python3 cli.py anlat /home/user/bir-proje
```

### `sesli` — yazılı anlatı + sesli özet

```bash
python3 cli.py sesli <repo-yolu> [--notebook-ami AD] [--out DOSYA.mp3]
```

Adım adım:

1. Köprü sunucusunun ayakta ve giriş yapılmış olduğunu kontrol eder — değilse
   **en başta** durur, yarım iş yapmaz.
2. Depoyu tarar, yazılı anlatıyı üretir ve `ANLATI.md` olarak kaydeder.
3. NotebookLM'de bir notebook oluşturur.
4. Anlatıyı bu notebook'a metin kaynağı olarak ekler.
5. Audio Overview'u üretir. **Bu işlem birkaç dakika sürebilir**; Google'ın
   gerçek sesli üretimini bekliyoruz, sabırlı ol.
6. Ses dosyasını indirir (varsayılan `<repo-yolu>/ANLATI.mp3`).

```bash
python3 cli.py sesli /home/user/bir-proje --notebook-adi "Projemin hikayesi"
```

Yararlı seçenekler:

| Seçenek | Varsayılan | Açıklama |
| --- | --- | --- |
| `--bridge-url` | `http://127.0.0.1:3000` | Köprü sunucusunun adresi |
| `--dil` | `tr` | Sesli özetin dili. Sunucu reddederse `--dil ""` ile boş bırakılabilir |
| `--out` | `<repo>/ANLATI.mp3` | Ses dosyasının nereye yazılacağı |
| `--timeout` | `900` | Köprü istekleri için zaman aşımı (saniye) |
| `--base-url`, `--model` | — | Yazılı anlatıyı üreten LLM bağlantısı |

---

## Testler

```bash
pytest tests/ -v
```

Köprü testleri gerçek bir ağ çağrısı yapmaz; Python'ın `http.server`'ı ile
localhost üzerinde sahte bir köprü sunucusu kurar ve istemcinin ona karşı
gerçekten doğru istekleri attığını sınar.

## Dizin düzeni

```
cli.py               komut satırı arayüzü (anlat, sesli)
generator/scanner.py git taraması — ham sinyal toplama
generator/narrator.py ham sinyalden yazılı anlatı üretimi
bridge/client.py     NotebookLM köprü sunucusuna ince HTTP istemcisi
tests/               testler (gerçek dosya sistemi, gerçek git, sahte HTTP sunucusu)
```
