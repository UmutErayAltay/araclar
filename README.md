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
```

- `label` **zorunlu değil** — boşsa veya `~` ise `cwd`'nin son bileşeni kullanılır.
- `command` verilmezse login shell'in açılır (`$SHELL`).
- `cwd` ve `discover_roots` değerlerinde `~` ve `$ENV_DEĞİŞKENİ` genişletilir.
- `tags` yalnızca arama yüzeyini genişletir; sonucu etkilemez.

`discover_roots` altındaki her git reposu, "repoya gir" kısayolu olarak
palette eklenir: komutu, o dizinde açılan shell'dir. Bir repo için özel bir
komut yazmak istersen `items` içine **aynı `cwd`** ile ekle — config'teki
kazanır, keşif onu tekrar etmez.

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
mantığını içerir ve test edilebilir, `cli.py` ise yalnızca questionary ile
sorar ve subprocess ile çalıştırır.

## Lisans

Kişisel kullanım için; lisans belirtilmemiş.
