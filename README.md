# orkestra

Ajan Orkestrasi: bunny/nemotron/deepseek ajanlari icin gorev kuyrugu, kota takibi ve web panel.

Durum: **Dalga B** (headless `claude` çalıştırıcısı) bitti. Web panel ve kota Dalga C'de.
Yalnızca Python 3.11 standart kütüphanesi kullanılır (bağımlılık yok).

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

# Dalga B: gerçek çalıştırma
orkestra calistir-bir --model stealth/space-bunny-alpha --cwd /tmp/orkestra_e2e
orkestra calistir --limit 10                                # bekleyenleri sırayla çalıştır
orkestra kurtar                                             # yarım kalan görevleri düzelt
orkestra rapor 1                                            # son koşunun raporu
```

Paket doğrudan da çalışabilir: `python3 -m orkestra ...`

Veritabanı yolu: `--db YOL` ile verilir, yoksa `ORKESTRA_DB`, yoksa
`~/.orkestra/orkestra.db`.

Ortam değişkenleri: `ORKESTRA_DB` (veritabanı), `ORKESTRA_CLAUDE_CMD` (çalıştırılacak komut,
`shlex` ile bölünür; testlerde sahte `claude` betiği için kullanılır).

## Çalıştırıcı

`ClaudeRunner` `claude -p`'yi alt süreç olarak çalıştırır:

- **İstem STDIN'den gider**, komut satırına konmaz — `ps`'te görünmez, uzunluk sınırı yoktur.
- Sabit bayraklar: `--permission-mode acceptEdits`,
  `--allowedTools Read,Write,Edit,Bash,Glob,Grep`, istenirse `--model <model>`.
  `--permission-mode bypassPermissions` **asla** kullanılmaz.
- Birleşik stdout+stderr **maskelenerek** `~/.orkestra/runs/<task_id>-<zaman>.log`
  dosyasına yazılır (dizin 0700, dosya 0600). `rapor` bu yolu gösterir, metni maskeli basar.
  Çıktı 5 MiB'yi aşarsa dosyanın sonu tutulur, başa `[kırpıldı]` notu düşer.
- **Ajan tanımı**: `<cwd>/.claude/agents/<ajan>.md` ya da `~/.claude/agents/<ajan>.md` varsa
  `claude`'a iletilir. Bu ortamda `--agent` bayrağı desteklendiği için **ajan adı** `--agent`
  ile geçilir; `--agent` yoksa dosya gövdesi (frontmatter hariç) `--append-system-prompt`
  ile verilir. Tanım dosyası yoksa yalnızca istem gönderilir.
- **Zaman aşımı**: süre dolarsa süreç *grubu* önce `SIGTERM`, 5 sn sonra `SIGKILL` ile
  öldürülür (çocuk süreç bırakılmaz). Sonuç `hata="zaman-asimi"`, çıkış kodu 124.
  Yeniden denemez; kullanıcı `orkestra tekrar` diyebilir.
- **Yeniden deneme yalnızca ağ hatalarında**: 502/503/504, `ECONNRESET`, `ETIMEDOUT`,
  `ENOTFOUND`, `EAI_AGAIN`, `socket hang up`, `Unable to connect`, `network error`,
  `fetch failed`. Üstel geri çekilme 2/4 sn, en fazla 3 deneme; sonunda `hata="ag-hatasi (3 deneme)"`.
- **İzin reddi asla yeniden denemez ve asla aşılmaz**: çıktıda izin/sınıflandırıcı reddi
  kalıbı varsa görev `onay-bekliyor` olur. Reddi anlatan satırlar log'da kalır.

Kuyruk tarafında `bekliyor → calisiyor` geçişi **atomiktir** (tek `UPDATE ... WHERE durum='bekliyor'`
+ `rowcount` kontrolü); iki süreç aynı anda çalıştırırsa aynı görevi ikisi birden alamaz.

## Durum makinesi

`bekliyor` → `calisiyor` → `bitti` | `hata` | `onay-bekliyor` | `iptal`

`onay-bekliyor` → `bekliyor` | `iptal`, `hata` → `bekliyor` (yeniden deneme).
`bitti` ve `iptal` son durumlardır. Geçersiz geçiş `GecersizGecis` fırlatır, DB değişmez.

## Güvenlik

Görev metni anahtar/`.env` kalıbı içeremez; reddedilen metin hata mesajına **yansıtılmaz**
(maskelenir). `sk-` anahtar kalıbı sol sınırdan başlar ve eşleşen parçada en az bir rakam
ister; böylece `flask-sqlalchemy-migrate-extension` gibi meşru paket adları yanlış
pozitif üretmez. Runner çıktısı, koşu hatası ve kanıt yolları kayda **maskelenerek** yazılır.
`orkestra/runner.py` içindeki `FakeRunner` kurgusal bir çalıştırıcıdır — testler `claude`
yerine sahte bir betik kullanır.

## Testler

```bash
python3 -m pytest -q
```