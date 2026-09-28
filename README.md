# kp — kısayol paleti

Terminalden, fuzzy-search ile sık kullandığın proje ve komutları bulup
çalıştıran kişisel bir palet. Bir kısayol = bir etiket + bir çalışma
dizini + bir komut. `kp` çalıştır, harfleri yaz, seç, komut o dizinde
çalışsın.

## Kurulum

```bash
git clone <bu-repo> && cd kisayol-paleti
python -m pip install -e ".[dev]"     # geliştirme için
# ya da sadece çalıştırmak için:
python -m pip install -e .
```

Python >= 3.11 gerekir. Bağımlılıklar: `questionary` (interaktif seçim) ve
`pyyaml` (config okuma).

## Yapılandırma

`kp` ilk çalıştırmada boş bir paletle karşılaşır ve nereden başlayacağını
söyler. Hazır şablonu kopyala:

```bash
mkdir -p ~/.config/kisayol
cp config.yaml.example ~/.config/kisayol/config.yaml
```

Sonra `config.yaml`'ı düzenle:

```yaml
items:
  - label: kule sunucusunu başlat     # arama sonuçlarında görünen ad
    cwd: ~/kule                       # komutun çalışacağı dizin (~ genişletilir)
    command: uvicorn app.main:app --reload
    tags: [kule, server]             # opsiyonel: etiketler de aranır

discover_roots:                       # opsiyonel
  - ~/projeler                        # altındaki .git'li klasörler otomatik eklenir

search_roots:                         # opsiyonel (kp ara için)
  - ~/Mt3Ui55OS                       # not vault'u
  - ~/kule
```

- `label` **zorunlu değil** — boşsa veya `~` ise `cwd`'nin son bileşeni kullanılır.
- `command` verilmezse login shell'in açılır (`$SHELL`).
- `cwd`, `discover_roots` ve `search_roots` değerlerinde `~` ve
  `$ENV_DEĞİŞKENİ` genişletilir.
- `tags` yalnızca arama yüzeyini genişletir; sonucu etkilemez.

`discover_roots` altındaki her git reposu, "repoya gir" kısayolu olarak
palette eklenir: komutu, o dizinde açılan shell'dir. Bir repo için özel bir
komut yazmak istersen `items` içine **aynı `cwd`** ile ekle — config'teki
kazanır, keşif onu tekrar etmez.

`search_roots` ise farklı bir iş görür: `discover_roots` yalnızca `.git`'i
olan klasörleri ararken, `search_roots` altındaki **tüm dosyaların içeriği**
taranır. Vault notlarını (`~/Mt3Ui55OS`) ve kod repolarını aynı listede
tutabilirsin.

Config dosyasının yolunu değiştirmek için:

```bash
KISAYOL_CONFIG=/istediğin/yol/config.yaml kp     # kalıcı için export et
kp --config /istediğin/yol/config.yaml           # tek seferlik
```

## Kullanım

```bash
kp              # interaktif: harf yaz, filtrelenir, Enter ile seç
kp --list       # seçim yok: paleti satır satır yazdırır (script'lenebilir)
kp --help
```

## Arama: `kp ara`

Vault notlarında ve kod repolarında aynı anda tam metin araması yapar —
"bunu hangi projede yaptım?" sorusunun cevabı saniyeler içinde:

```bash
kp ara telegram                        # en fazla 50 sonuç
kp ara "fatura pdf" --limit 10        # en fazla 10 sonuç
kp ara telegram --no-ripgrep          # saf Python motorunu zorla
```

Her sonuç `[kök] yol:satır_no: satır` biçimindedir:

```bash
[kule] /home/user/kule/app/main.py:42: telegram botu burada
[Mt3Ui55OS] /home/user/Mt3Ui55OS/🔮 850-Companion/Threads.md:701: ifadeyi doğrula
[vault] /home/user/notlar/📌 fikirler.md:3: telegram notu
```

- Baştaki **kök etiketi** sonucun nereden geldiğini söyler: kök bir git reposuysa
  **repo adı**, değilse `vault`. (Umut'un vault'u `~/Mt3Ui55OS` kendisi de bir git
  reposu olduğu için `[Mt3Ui55OS]` olarak görünür.)
- Sonuçlar **dosya değiştirme zamanına** göre sıralanır (en yeni önce) —
  "en son ne yapmıştık" sorusunun cevabı en üstte.
- Sorgu **düz metindir**, regex değil: `kp ara "c++"` çalışır.
- Büyük harf varsa duyarlı, yoksa duyarsız arar (ripgrep'in `--smart-case` kuralı).
- `search_roots` tanımlı değilse ya da sorgu boşsa anlamlı bir mesajla çıkar.
- Bulunmayan/erişilemeyen kökler sessizce atlanır.

### ripgrep

`rg` (ripgrep) PATH'teyse kullanılır — çok hızlıdır ve `.gitignore`, gizli
dosyalar ve binary dosyaları zaten kendi kurallarıyla ele alır:

```bash
# Debian/Ubuntu
sudo apt install ripgrep
# macOS
brew install ripgrep
```

`rg` **yoksa** `kp` kendi saf Python taramasına düşer: sonuç aynı, yalnızca
büyük vault'larda yavaş olabilir (tipik olarak birkaç kat, saniyeler değil
dakikalar). Kurulum önerilir ama zorunlu değildir.

İki motor arasındaki tek bilinçli fark `.gitignore`'dır: `rg` onu uygular
(bırakılan `config.yaml`, `.env`, `*.log` dosyaları sonuçlarda görünmez), saf
Python motoru uygulamaz. Aynı makinede iki motoru karşılaştırmak için:

```bash
kp ara telegram | sort > /tmp/rg.txt
kp ara telegram --no-ripgrep | sort > /tmp/py.txt
diff /tmp/rg.txt /tmp/py.txt
```

`kp --list` çıktısı script'lenebilir — etiket, tag'ler ve komut ` · ` ile
ayrılmış tek satırdadır:

```bash
kp --list | grep kule
```

İnteraktif seçicide yazdığın harfler listeyi filtreler (Backspace geri alır,
ok tuşları gezinir). `j`/`k` navigasyonu kapalıdır — bu tuşlar yazılan metnin
bir parçası olabilsin diye; filtreleme için kısayol rakamları da kullanılmaz.

Seçilen komut `cwd` dizininde, stdio miras alınarak çalışır: yani `vim`,
`psql`, `tail -f`, `pytest -p no:cacheprovider` gibi interaktif komutlar
normal terminal gibi davranır. Komutun çıkış kodu `kp`'nin çıkış kodu olur.
Ctrl-C / ESC ile vazgeçersen hiçbir komut çalıştırılmaz (çıkış kodu 130).

## Geliştirme

```bash
python -m pytest -v
```

Katmanlar birbirinden ayrıdır: `config.py` ve `discovery.py` yalnızca veri
toplar ve **asla raise etmez** (eksik config, erişilemeyen kök gibi durumlar
sessizce boş listeye dönüşür), `matcher.py` tüm fuzzy eşleştirme ve sıralama
mantığını içerir, `search.py` ise aramayı (ripgrep köprüsü + saf Python
fallback) uygular ve ikisi de test edilebilir; `cli.py` yalnızca questionary
ile sorar, subprocess ile çalıştırır ve arama sonuçlarını biçimlendirir.

## Lisans

Kişisel kullanım için; lisans belirtilmemiş.
