# orkestra

Ajan Orkestrasi: bunny/nemotron/deepseek ajanlari icin gorev kuyrugu, kota takibi ve web panel.

Durum: **Dalga A** (görev modeli, kuyruk, CLI) bitti. Gerçek `claude` çalıştırıcısı ve web panel
Dalga B/C'de. Yalnızca Python 3.11 standart kütüphanesi kullanılır (bağımlılık yok).

## Kurulum

```bash
python3 -m pip install -r requirements-dev.txt   # sadece test için
```

## Komutlar

```bash
orkestra ver --ajan bunny-coder "README.md dosyasini incele"   # görev ekle
orkestra liste                                              # tüm görevler
orkestra liste --durum bekliyor                             # duruma göre filtre
orkestra iptal 2                                            # görevi iptal et
orkestra tekrar 2                                           # hatalı görevi yeniden dene
orkestra calistir-bir                                       # B dalgasında gelecek (çıkış 2)
```

Paket doğrudan da çalışabilir: `python3 -m orkestra ...`

Veritabanı yolu: `--db YOL` ile verilir, yoksa `ORKESTRA_DB`, yoksa
`~/.orkestra/orkestra.db`.

## Durum makinesi

`bekliyor` → `calisiyor` → `bitti` | `hata` | `onay-bekliyor` | `iptal`

`onay-bekliyor` → `bekliyor` | `iptal`, `hata` → `bekliyor` (yeniden deneme).
`bitti` ve `iptal` son durumlardır. Geçersiz geçiş `GecersizGecis` fırlatır, DB değişmez.

## Güvenlik

Görev metni anahtar/`.env` kalıbı içeremez; reddedilen metin hata mesajına **yansıtılmaz**
(maskelenir). `orkestra/runner.py` içindeki `FakeRunner` kurgusal bir çalıştırıcıdır — gerçek
`claude` Dalga A'da hiç çağrılmaz.

## Testler

```bash
python3 -m pytest -q
```