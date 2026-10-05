# haftalik

Birden çok repodaki **son N günün commit'lerini** toplar ve yerel **cor LLM'i** ile
**Türkçe haftalık özete** çevirir. Repoları **salt okunur** okur (`git log`); hiçbir
repoya yazmaz. Yalnız Python standart kütüphanesi (Python 3.11+).

## Ne yapar

Verilen kök dizinlerin altındaki repoları bulur (kök bir repo ise yalnız onu; değilse
`kök`ten derinlik **3**'e kadar iner), her birinde son `--gun` günün commit'lerini
okur ve dört şeyi toplar: commit sayısı, eklenen/silen satır, her commit'in
kısası/yazarı/tarihi/konusu. Commit'i olmayan repo **listelenmez**.

Toplanan veriden bir istem kurulur ve cor'a gönderilir; dönen metin Markdown
haftalık özete dönüştürülür: `# Haftalık özet (tarih aralığı)` başlığı, her aktif
repo için 1-3 cümle, sonunda `## Öne çıkanlar` başlığı altında 3-5 madde.

İki sınır, sözleşmenin parçası:

- **Tarih filtresi Python'da yapılır**, `git --since` ile değil. Git geçmişte ilerlerken
  pencere dışına ilk çıktığı commit'te **dalları keser**; HEAD'i eski olan bir repoda
  yeni commit'ler sessizce kaybolurdu. Log sınırsız alınır, `commit date`'e göre süzülür.
- **İstem en çok ~12000 karakterdir.** Fazlası repo başına en yeni 40 commit'e
  kısaltılır ve kısaltma **istem içinde belirtilir** — LLM kısaltılmış veriyi
  "hepsi buymuş" sanmasın.

## Kurulum

```bash
cd haftalik
pip install -e .            # ya da kurulum yapmadan: python -m haftalik
```

Özet üretmek için yerel cor proxy'si gerekir (yoksa `--sadece-topla` çalışır):

```bash
cor start                   # http://127.0.0.1:8787
```

## Kullanım

```bash
# Tüm repoları tara ve haftalık özet üret (stdout'a yazar)
haftalik uret --kok ~/Documents/projeler
haftalik uret --kok ~/projeler --kok ~/is --gun 14 --model stealth/space-bunny-alpha

# LLM'e hiç gitmeden toplanan veriyi Markdown olarak bas (çevrimdışı)
haftalik uret --kok ~/projeler --sadece-topla

# Özeti dosyaya yaz (VAR OLMAYAN dosyaya; üzerine yazmaz)
haftalik uret --kok ~/projeler --cikti haftalik-2026-W41.md

# Telegram'a gönder
haftalik uret --kok ~/projeler --telegram
```

`--sadece-topla` toplama aşamasının **ham** çıktısıdır: repo başına commit sayısı,
`+eklenen/-silinen` satır sayısı ve her commit'in konu satırı. LLM'e hiç gidilmez;
bu yüzden cor kapalıyken ve testlerde kullanılır.

`--cikti` verilmişse özet **o dosyaya** yazılır. Dosya zaten varsa **üzerine
yazılmaz**, kullanım hatası verilir (çıkış `2`). Verilmemişse metin `stdout`'a basılır.

## `--telegram`

`tekrar`'ın deseninin aynısı: MarkdownV2 kaçışı, 4096 karakter sınırı (aşan özet
boşluklardan bölünür, tek satır bile sığmıyorsa `…` ile kısaltılır), hiçbir durumda
`raise` etmez.

| Ortam değişkeni | Anlamı |
| --- | --- |
| `HAFTALIK_TELEGRAM_BOT_TOKEN` | Bot token (ör. `123456:ABC...`) |
| `HAFTALIK_TELEGRAM_CHAT_ID` | Hedef sohbet kimliği |

İkisi de ayarlı değilse `Hata: ...` basılır ve çıkış kodu `2`'dir. Token ve chat_id
**hiçbir çıktıya sızmaz** — ne başarı mesajına, ne hata metnine, ne log'a.

## Güvenlik notları

- **Toplama salt okunurdur.** Yalnız `git log` çalışır, `shell=False` argüman listesiyle;
  `GIT_OPTIONAL_LOCKS=0` ile git index'i kilitlemez/yazmaz. `.git` dışına hiçbir yerde
  yazılmaz.
- **Dosya yazan tek eylem `--cikti`'dir**, o da yalnız var olmayan bir dosyaya.
- **Loopback dışı cor adresi reddedilir**: `konak_kontrol` yalnız `127.0.0.1`,
  `localhost`, `::1` kabul eder. Commit verisi dışarı çıkmaz.
- **LLM'e hiçbir gizli değer girmez.** Gönderilen tek şey commit kısa yazarı/tarihi/
  konusu ve satır sayılarıdır.
- cor kapalıysa ham veri bir dosyaya **yazılmaz**; yalnız
  `Hata: cor proxy'sine bağlanılamadı (cor start)` basılır (çıkış `1`).

## Çıkış kodları

| Kod | Durum |
| --- | --- |
| `0` | Özet üretildi (ya da `--sadece-topla` çıktısı yazıldı/basıldı) |
| `1` | cor erişilemedi / boş özet döndü / commit'i olan repo yok / Telegram gönderilemedi |
| `2` | Kullanım hatası: yol bulunamadı, `--gun < 1`, `--cikti` dosyası zaten var, Telegram ortam değişkenleri yok |

Hatalar `stderr`'e `Hata: ...` olarak yazılır; **traceback basılmaz**.

## `_corclient.py` hakkında

`haftalik/_corclient.py` **elle düzenlenmez**. LLM istemcisinin tek kaynağı kök
dizindeki `corclient.py`'dir; bu kopya `tools/sync.py` ile üretilir:

```bash
python3 tools/sync.py haftalik/haftalik/_corclient.py        # yeniden üret
python3 tools/sync.py --check haftalik/haftalik/_corclient.py  # sapma var mı?
```

Sapma (drift) başlıktaki `sha256` ile yakalanır. Değiştirmek istersen kök
`corclient.py`'yi düzelt, sonra `sync.py`'yi çalıştır. `llm.py` yalnız ince kabuktur
(`DEFAULT_BASE_URL` / `DEFAULT_MODEL` / `IZINLI_KONAKLAR` / `CorLLMClient`).

## Testler

```bash
python3 -m pytest -q
```

Gerçek ağ ve gerçek cor **yoktur**: LLM istemcisi `llm.CorLLMClient` monkeypatch'lenir,
Telegram gönderimi sahte göndericiye bağlanır. Git repoları `tmp_path` içinde gerçek
`git init` ile kurulur (`GIT_AUTHOR_DATE` / `GIT_COMMITTER_DATE` ile sahte tarihli
commit'ler), çıktı dosyaları yalnız geçici dizinde yazılır. `~/` altındaki gerçek
repolar hiçbir testte okunmaz veya değiştirilmez.