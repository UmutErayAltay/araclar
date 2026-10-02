# corclient — sözleşme (v0.1)

Amaç: `atlas`, `harita`, `orkestra`, `danis`, `ne-izlesem` (+ sonradan `anlat`) repolarında **5 ayrı kopya**
olarak yaşayan yerel-cor LLM istemcisini (`llm.py`, ~120-146 satır) TEK kaynağa indirmek.
**Davranış değiştirmeyen refactor**: her repo kendi mevcut test paketiyle, TEST DEĞİŞTİRİLMEDEN
geçmeli.

## 1. Mimari karar: bağımlılık değil, tek dosya + senkron (vendoring)

`pip install corclient` tarzı gerçek bağımlılık SEÇİLMEDİ. Nedenler:
- Tüm repolar bilerek **yalnız stdlib** (`urllib`); ek kurulum adımı yok.
- `danis` GitHub Actions'ta Windows `.exe` derliyor; CI'ın yalnız bu depodaki dosyalarla
  çalışması gerekir, ayrı bir pakete bağımlılık CI'ı kırar.
- Bulut oturumunda yeni özel repodan `pip install` yapılamıyor; her repo testi tek başına
  koşabilmeli.

Bunun yerine: kaynak `corclient/corclient.py` (tek dosya). Her tüketici repo onu kendi paketi
içine `_corclient.py` adıyla **kopyalar** (`tools/sync.py`), başına bir senkron başlığı yazılır.
Kopya ELLE DÜZENLENMEZ; sapma (drift) testle yakalanır.

Bu, "5 kopya" yerine "1 kaynak + 5 doğrulanabilir yansıma"dır. Dürüst sınır: hata düzeltmesi
yine 5 repoya yansıtılmalıdır, ama tek komutla (`sync.py`) ve sapma olursa test KIRMIZI olur.

## 2. Kaynak dosya: `corclient.py`

Yalnız stdlib. Python **>=3.10** uyumlu (`from __future__ import annotations`; `tomllib`,
`except*` vb. YOK). Dış adres/anahtar/yerel yol YOK.

Dışa açık adlar (hepsi `__all__`'da):

```python
__surum__ = "0.1.0"
DEFAULT_BASE_URL   # os.environ.get("COR_BASE_URL", "http://127.0.0.1:8787")
DEFAULT_MODEL      # os.environ.get("COR_MODEL", "stealth/space-bunny-alpha")
IZINLI_KONAKLAR = frozenset({"127.0.0.1", "localhost", "::1", "[::1]"})

class LLMError(RuntimeError):
    status: int | None      # HTTP hatasında kod, aksi halde None
    def __init__(self, mesaj: str, status: int | None = None) -> None

@runtime_checkable
class LLMClient(Protocol):
    def complete(self, prompt: str) -> str: ...

def konak_kontrol(base_url: str, izinli: frozenset[str] = IZINLI_KONAKLAR) -> str
    # şema http/https değilse veya konak izinli değilse LLMError; konak adını döner

class CorLLMClient:
    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        timeout: float = 120.0,
        max_retries: int = 3,
        retry_backoff: float = 3.0,
        *,
        max_tokens: int = 4000,
        izinli_konaklar: frozenset[str] | None = IZINLI_KONAKLAR,
        baslat_ipucu: str = "cor start",
    ) -> None
    def _post_once(self, prompt: str) -> str
    def complete(self, prompt: str) -> str
```

İlk 5 parametrenin **sırası ve adı** mevcut 5 kopyadakiyle aynıdır (konumsal çağrılar kırılmaz).

### 2.1 Davranış kuralları (mevcut kopyalarla BİREBİR)

1. `izinli_konaklar` bir küme ise kurucu `konak_kontrol` çağırır, loopback dışı → `LLMError`
   (mesajda "loopback" geçer). `None` ise konak denetimi YAPILMAZ (bkz. 4. bölüm, açık karar).
   Şema denetimi (http/https) de `konak_kontrol` içindedir, yani **yalnız küme verildiğinde**
   yapılır (danis/ne-izlesem bugün hiç denetlemiyor; davranış korunur).
2. `POST {base_url}/v1/messages`, başlık `content-type: application/json`, gövde:
   `{"model", "max_tokens", "messages":[{"role":"user","content":prompt}]}`. `base_url` sondaki `/`
   atılır. Başka başlık/alan EKLENMEZ.
3. `urllib.error.HTTPError` → `LLMError("cor proxy HTTP {kod} döndü: {ilk 500 karakter}", status=kod)`.
   `URLError`/`OSError` → `LLMError("cor proxy'ye ({base_url}) bağlanılamadı: {hata}. Önce `{baslat_ipucu}` ile proxy'yi başlatmayı deneyin.")`.
4. Yanıt `json.loads` + `["content"][0]["text"]`; `JSONDecodeError/KeyError/IndexError/TypeError` →
   `LLMError("cor proxy'den beklenmeyen yanıt biçimi: {ilk 500 karakter}")`.
5. Metin boş/yalnız boşluksa → `LLMError("LLM boş yanıt döndürdü (muhtemelen max_tokens kısa kaldı). Sahte yanıt üretmek yerine hata fırlatıldı.")`.
   SAHTE YANIT ÜRETİLMEZ.
6. `complete`: `max_retries + 1` deneme. **Yalnız 5xx** yeniden denenir: `hata.status` 500-599 ise
   VEYA `status is None` ve mesajda `HTTP 5` geçiyorsa (mevcut testler `_post_once`'ı `status`suz
   `LLMError("cor proxy HTTP 502 ...")` ile monkeypatch ediyor; bu yol korunmalı). Bekleme
   `retry_backoff * 2**deneme`; `time.sleep` kullan (testler `time.sleep`'i yama yapabilir); her
   beklemede stderr'e `Geçici sağlayıcı hatası, {bekleme:.0f}s sonra tekrar denenecek ({n}/{max}): {hata}`.
   Son denemede veya 5xx değilse hata aynen yükseltilir.
7. Modül `import time, urllib.request, urllib.error, json, sys, os` biçiminde MODÜL olarak içe aktarır
   (testler `llm.urllib.request.urlopen`'ı ve `time.sleep`'i yamalıyor; `from x import y` ile
   bağlama YAPMA).

## 3. Senkron mekanizması

- `tools/sync.py YOL [YOL ...]` : kaynak dosyayı her YOL'a yazar. İlk satır:
  `# SENKRON corclient surum=<__surum__> sha256=<kaynak baytlarının sha256'sı>` ardından
  kaynak BAYTLARI DEĞİŞTİRİLMEDEN.
- `tools/sync.py --check YOL [YOL ...]` : her YOL için (a) başlık var mı, (b) başlıktaki sha256
  dosya gövdesiyle tutuyor mu (ELLE düzenleme), (c) başlıktaki sha256 bu repodaki GÜNCEL kaynakla
  tutuyor mu (eski sürüm). Herhangi biri yanlışsa çıkış kodu 1 ve hangi YOL'un neden kırıldığı.
  Hedef yolu repoya GÖMÜLMEZ (yerel yol sızıntısı yok); komut satırı argümanıdır.
- Tüketici repo testi (`tests/test_corclient_senkron.py`, her tüketiciye eklenir): kendi
  `_corclient.py`'sinin başlığındaki sha256'nın gövdeyle tuttuğunu doğrular (elle düzenlemeyi
  yakalar; corclient reposuna erişmez).

## 4. Tüketici ince kabuğu (`llm.py` KALIR)

Her repoda `llm.py` silinmez; kamuya açık adlar (`LLMError`, `LLMClient`, `CorLLMClient`,
`konak_kontrol`, `IZINLI_KONAKLAR`, `DEFAULT_BASE_URL`, `DEFAULT_MODEL`, `MAX_TOKENS`) ve içe
aktarılan modül adları (`urllib`, `time`, `sys`, `json`, `os`) o modülde yaşamaya devam eder;
böylece mevcut testler/CLI'lar DEĞİŞMEZ. `CorLLMClient`, `_corclient.CorLLMClient`'in alt
sınıfıdır ve eski varsayılanları verir:

| Repo | DEFAULT_MODEL | MAX_TOKENS | timeout | konak denetimi | başlat ipucu |
|---|---|---|---|---|---|
| atlas | `stealth/space-bunny-alpha` | 2000 | 60 | loopback | `cor start` |
| harita | `stealth/space-bunny-alpha` | 2000 | 60 | loopback **+ `0.0.0.0`** | `cor start` |
| orkestra | `nvidia/nemotron-3-ultra-550b-a55b:free` | 4000 | 120 | loopback | `cor start` |
| danis | `stealth/space-bunny-alpha` | 2000 | 60 | loopback (8. bölümde sıkılaştırıldı) | `cor` |
| ne-izlesem | `stealth/space-bunny-alpha` | 2000 | 60 | loopback (8. bölümde sıkılaştırıldı) | `cor claude` |

`DEFAULT_MODEL` her repoda `os.environ.get("COR_MODEL", <yukarıdaki>)`; `DEFAULT_BASE_URL`
`os.environ.get("COR_BASE_URL", "http://127.0.0.1:8787")`.

### Açık karar (Umut'un): danis ve ne-izlesem'de konak denetimi YOK
Bugünkü davranış korunuyor (refactor davranış değiştirmez). Ama bu iki araç kullanıcı
dosyasını/listesini `COR_BASE_URL`'in gösterdiği yere gönderir; diğer üçü loopback dışını reddeder.
Tutarlılık için `izinli_konaklar=IZINLI_KONAKLAR` yapmak tek satırlık değişiklik; uzak cor
kullanan (ör. WSL→Windows) bir kurulum varsa kırılır. **Ana oturum bunu Umut'a sorar; ajan
kendi başına değiştirmez.**

## 5. Kabul kriterleri

**corclient reposu**
- `python3 -m pytest -q` yeşil; testler yerel sahte HTTP sunucusuyla (gerçek soket,
  `127.0.0.1`, boş port). Kapsam: başarılı çağrı (gövde/başlık/model/max_tokens), 4xx TEKRAR
  DENENMEZ (erişim sayısı 1), 5xx `max_retries` kadar denenir ve sonra yükselir, 5xx sonra başarı,
  `status`suz `HTTP 5xx` mesajlı monkeypatch yolu retry eder, boş yanıt, bozuk JSON, eksik
  `content`, kapalı port mesajı (`baslat_ipucu` geçer), loopback dışı ret, şema ret, `izinli_konaklar=None`
  ile dış konak kabul, `0.0.0.0` yalnız küme verilirse kabul, sondaki `/` atılır, `LLMClient`
  Protocol `isinstance`, `status` alanı.
- `sync.py`: yazma, başlık biçimi, `--check` üç bozulma durumunu (başlık yok / gövde elle
  düzenlendi / eski sürüm) YAKALAR; her biri için test. **Bu testler bozuk durumda gerçekten
  kırılmalı** (mutasyon: gövdeye bir karakter ekle → `--check` 1 döner).
- Kaynakta `print` yalnız retry stderr satırı; ağ çağrısı yalnız `urlopen`.

**Her tüketici repo** (ana oturum yapar; ajan DEĞİL)
- Mevcut test paketi DEĞİŞTİRİLMEDEN, referans sayıyla AYNI sonuçla geçer (aşağıdaki sayılar
  e2e/integration_cor HARİÇ): atlas 697 passed/3 skipped, harita 505, orkestra 788, danis
  113 passed/1 skipped, ne-izlesem 175.
- Yeni: `tests/test_corclient_senkron.py` (elle düzenleme → kırmızı; mutasyonla doğrulanır).
- `llm.py` satır sayısı belirgin düşer; tekrar eden gövde kalmaz.

## 6. Kapsam dışı (bilerek)

- `anlat/generator/narrator.py` (kendi `NarratorError`'ı, 8000 token, 300 sn) ve
  `readbunny/app/summarizer.py` (başka HTTP kütüphanesi, `SummarizeError`): istisna türleri ve
  semantikleri farklı; ayrı karar. Bu dalgada DOKUNULMAZ.
- `system` mesajı, streaming, otomatik model değiştirme, kota sayacı: EKLENMEZ.
- Test paketlerinde mevcut testi silme/gevşetme: YASAK.

## 7. Yasaklar (ajan için)

- Yalnız `/home/user/corclient` altına yaz. Başka repoya, vault'a, `~` altına YAZMA (tmp_path hariç).
- Commit/push YOK (ana oturum yapar). `git push --force` YOK.
- Gerçek cor/ağ çağrısı YOK (testler sahte sunucuyla). Gerçek vault içeriği YOK.
- Anahtar, yerel yol, oturum id'si repoya girmez (fixture'lar dahil).
- Her yeni test için "bozuk kodda bu kırılır mı" diye kendin dene; raporda hangi testlerin
  mutasyona karşı kırıldığını listele.

## 8. Monorepo'ya taşıma (2026-09-30, sonradan)

Bu sözleşme başta ayrı repolar için yazıldı (her tüketici kendi reposunda). Sonra Umut, `atlas`,
`harita`, `orkestra`, `danis`, `ne-izlesem` projelerinin bu repoya klasör olarak taşınmasına karar
verdi (`git subtree add`, commit geçmişi korunarak; `danis` artık özel). Sonuçları:

- Yukarıdaki "tüketici repo" ifadeleri artık `corclient/<proje>/` klasörleridir; vendoring (1. bölüm)
  bilerek korundu: projeler bağımsız kurulabilir/derlenebilir kalsın (`danis` tek `.exe`).
- `tools/sync.py --hepsi` ve `tests/test_monorepo_kopyalar.py` eklendi: artık kopyaların **güncelliği**
  de aynı repoda test edilir (ayrı repolar döneminde yalnız "elle düzenlendi mi" görülebiliyordu).
- **4. bölümdeki açık karar kapandı:** `danis` ve `ne-izlesem` de loopback dışı adresi reddeder
  (`izinli_konaklar=IZINLI_KONAKLAR`). Uzak cor kullanan (ör. WSL→Windows) kurulum bu iki araçta artık
  kurulumda hata alır; bilerek kabul edildi.
- `danis`'in Windows CI'ı `.github/workflows/danis-build-windows.yml` olarak köke taşındı
  (`working-directory: danis`, yol filtreli). Windows'ta henüz koşturulmadı.
- `readbunny` kapsam dışı kaldı (6. bölüm geçerli): güvenlik denetiminden geçmiş temizlenmiş hata mesajları, `requests` kütüphanesi ve tekrar deneme yok.
- **`anlat` sonradan eklendi (aynı gün):** klasör olarak taşındı ve istemcisi ortak kaynağa geçti. Farkı: kendi
  `NarratorError`'ı var; `NarratorError`, `LLMError`'un alt sınıfı yapıldı ve `_post_once` her `LLMError`'u
  `NarratorError`'a çevirir (çağıran kod ve yeniden deneme mantığı değişmedi). Tek davranış farkı boş yanıt mesajının
  metni ("Sahte anlatı…" → "Sahte yanıt…"); gövde (8000 token), timeout (300 sn), hata türü ve deneme sayısı aynı.
  Konak denetimi başta bilerek kapalıydı (`izinli_konaklar=None`); sonra Umut açtı (aşağıdaki not).

## 9. ne-izlesem monorepo'dan çıkarıldı (2026-09-30, sonradan)

Kapsam tutarsızdı: `ne-izlesem` (film/kitap takip uygulaması) araç değil ayrı bir ürün ve diğer projelerle bağı
yalnızca ortak istemci. `git subtree split` ile geçmişi ayrıştırıldı, sıkılaştırma (loopback) dahil güncel hali
kendi reposuna hızlı-ileri (fast-forward) push edildi (orijinal commit zincirinin devamı; eski repo silinmemeli).
Bu repodan kaldırıldı; geçmişte (2. bölümdeki taşıma commit'leri) izi durur.

- `ne-izlesem` kendi `app/_corclient.py` kopyasını taşımaya devam eder. Güncellemek için bu repodan:
  `python3 tools/sync.py ../ne-izlesem/app/_corclient.py` (klasör yan yana klonluysa), sonra o repoda commit.
  Bu kopyanın güncelliği artık `tests/test_monorepo_kopyalar.py` kapsamında DEĞİL; yalnızca ne-izlesem'in kendi
  senkron testi (elle düzenleme) onu korur. Bu, bilerek kabul edilen bir zayıflamadır.

**anlat'ta loopback açıldı (2026-09-30, sonradan):** `izinli_konaklar=IZINLI_KONAKLAR`. Denetim kurucuda çalıştığı
ve CLI istemciyi `try` DIŞINDA kuruyordu; bu yüzden (1) kabuk kurulumdaki `LLMError`'u `NarratorError`'a çevirir,
(2) `cli.py` iki yerde (`anlat`, `sesli`) istemci kurulumunu `try` içine aldı (yoksa uzak `--base-url` traceback verirdi).
Testler: kurucu reddi, CLI `Hata:` + kod 1 + `ANLATI.md` yazılmaması; denetimi kapatma, dönüşümü kaldırma ve
kurucuyu `try` dışına alma mutasyonlarının üçü de testleri kırar. Artık tüm projeler loopback dışı adresi reddeder.
