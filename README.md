# atlas — Repo Sağlık Atlası

Bir kök dizindeki tüm git repolarını tarar, her birinin sağlık durumunu SQLite'a yazar ve
CLI ile tablo olarak gösterir. **Dalga A** (çekirdek tarayıcı + DB) uygulanmıştır.

## Ne yapar

`atlas tara` verdiğiniz dizinleri gezer, içinde `.git` olan her klasörü bir repo sayar ve
şunları SQLite'a yazar:

| Alan | Anlamı |
|---|---|
| `dirty` | `git status --porcelain` satır sayısı (izlenmeyen dosyalar dahil) |
| `unpushed` | Push edilmemiş commit sayısı (aşağıdaki kuraya bakın) |
| `branch` | Mevcut dal; detached ise `(detached)` |
| `last_commit_at` | Son commit tarihi, ISO8601 UTC |
| `has_remote` | Uzak (remote) tanımlı mı |

`unpushed` kuralı:
- Upstream varsa → `@{u}..HEAD` arası commit sayısı.
- Upstream yok ama remote varsa → HEAD'in hiçbir remote ref'inde olmayan commit sayısı.
- **Remote hiç yoksa** → depodaki toplam commit sayısı. (Yerelde duran işin
  göstergesi; "push bekliyor" anlamına gelmez. Bu yüzden `liste --sadece-yarim`
  bu durumu filtreye almaz.)

## Kurulum

Python 3.11+ ve `git` gerekir. Çalışma zamanında hiçbir üçüncü taraf kütüphane yoktur
(yalnızca standart kütüphane).

```bash
python3 -m atlas tara --root /home/user   # pip kurulumu gerekmez
```

İsteğe bağlı olarak paket olarak kurmak için:

```bash
pip install -e .
atlas tara --root /home/user
```

Geliştirme/test:

```bash
pip install -r requirements-dev.txt
python3 -m pytest -q
```

## Kullanım

```bash
# Tüm repoları tara (varsayılan derinlik 3)
atlas tara --root /home/user

# Birden fazla kök ve özel derinlik
atlas tara --root ~/Desktop --root ~/Projeler --derinlik 2

# Listele
atlas liste
atlas liste --sadece-yarim          # yalnızca commit'lenmemiş veya push bekleyenler
```

**Veritabanı yolu:** `--db` ile verilmezse `ATLAS_DB` ortam değişkeni, o da yoksa
`~/.atlas/atlas.db`. Üst dizin yoksa otomatik oluşturulur.

**Kök dizinler:** `--root` verilmezse `~/.atlas/config.toml` içindeki `roots`
listesi kullanılır:

```toml
roots = ["/home/user/projeler", "~/Desktop"]
```

`findings`, `readme_status` ve `todos` tabloları şemaları Dalga B/C/D için şimdiden
boş olarak oluşturulmuştur; bu dalda doldurulmaz.

## Güvenlik notu

- **Salt okunur.** Taranan repolara hiçbir şey yazılmaz. atlas yalnızca okuyan git
  komutlarını çalıştırır (`status`, `log`, `rev-parse`, `rev-list`, `symbolic-ref`,
  `remote`). `push`, `fetch`, `pull`, `reset`, `checkout`, `clean`, `gc` gibi komutlar
  kodda yoktur ve çalıştırılması teknik olarak engellenir. Git her seferinde
  `GIT_OPTIONAL_LOCKS=0` ile çağrılır, böylece `status` bile index'i tazelemez.
- Bu davranış testlerle kanıtlanır: taranan repoların `.git` içeriği, çalışma ağacı ve
  index dosyası tarama öncesi ve sonrası bayt bayt aynıdır.
- Bir repo bozuk/erişilemez ise atlanır ve uyarı olarak stderr'a yazılır; tüm tarama
  çökmez, çıkış kodu yine `0`'dır.
- Uzak sunucuya hiçbir ağ isteği yapılmaz (`fetch` yasaktır); yalnızca yerel
  `origin` bilgisi okunur.
- Bu dalda web sunucusu yoktur. (Dalga C'de yalnızca `127.0.0.1`'e bağlanacaktır.)
- Sızıntı bulguları (Dalga B) veritabanına daima maskelenmiş yazılacaktır; ham sır
  hiçbir çıktıya veya DB'ye gitmez.
