# harita

Markdown vault'unu okuyup **not grafiğini** çıkaran salt-okunur araç.
Dalga A: ayrıştırıcı + SQLite indeks + CLI. Bağımlılık yok (yalnızca Python 3.11 stdlib).

## Ne yapar

- Vault'u tarar (`*.md`), **hiçbir dosyayı değiştirmez** — yalnızca okur.
- Her notu ayrıştırır: `title`/`aliases`/`tags` frontmatter'ı, `#etiket`ler,
  `[[wikilink]]`ler (`[[not#başlık|görünen]]` ve `![[gömülü]]` dâhil).
- Linkleri Obsidian mantığıyla çözer: dosya adı → frontmatter `title` → takma ad.
  Çözülemeyenler **kırık link** olur.
- Gövdeyi ~800 karakterlik parçalara böler (arama için hazır).

## Kurulum

```bash
python3 -m pip install -e .          # ya da: pip install -r requirements-dev.txt
```

Geliştirme/test için: `python3 -m pip install -r requirements-dev.txt`

## Kullanım

```bash
# indeksle (ilk seferde)
harita indeksle /path/to/vault

# raporlar
harita kirik             # çözülemeyen linkler: kaynak → hedef
harita yetim             # ne link alan ne link veren notlar
harita etiketler --ilk 10 # en sık etiketler
```

Veritabanı yolunu `--db` ile ya da `HARITA_DB` ortam değişkeniyle belirle:

```bash
harita indeksle /path/to/vault --db /tmp/harita.db
harita --db /tmp/harita.db kirik      # --db alt komuttan da önceden verilebilir
```

`--db` verilmezse `~/.harita/harita.db` kullanılır. **Veritabanı vault'un
içine yazılmaz.**

## Gizlilik

- Vault'a **hiçbir yazma yolu yoktur**; dosyalar salt-okunur açılır.
- `sk-…`, `password=`, `api_key=…`, `-----BEGIN … PRIVATE KEY-----` gibi desenleri
  içeren satırlar gövdeden ve parçalardan **çıkarılır** (yerine sabit bir not konur).
- Emoji ve Türkçe karakterli klasör/dosya adları sorunsuz çalışır (Unicode NFC +
  Türkçe büyük/küçük harf duyarsız eşleştirme: `I/ı` ve `İ/i`).

## Testler

```bash
python3 -m pytest -q
```

Testler yalnızca `tmp_path` içinde **kurgusal** notlar yazar; gerçek vault
içeriği testlere hiç girmez.

## Dalga durumu

Dalga A tamam (ayrıştırıcı + indeks + CLI). Dalga B/C/D (web graf, arama, haftalık
özet) henüz yok.
