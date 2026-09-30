# corclient

Yerel cor proxy'sine (`POST /v1/messages`) konuşan ince LLM istemcisinin **tek kaynağı**.

Bu istemci daha önce `atlas`, `harita`, `orkestra`, `danis` ve `ne-izlesem`
paketlerinde birer kopyası olarak yaşıyordu. Bu repo o kopyaları **tek dosyaya**
indirir; tüketici repolar kaynağı kopyalayıp kendi `llm.py` ince kabuğunu korur.

## Neden bağımlılık değil (vendoring kararı)

`pip install corclient` **seçilmedi**:

- Tüm repolar bilerek **yalnız stdlib** (`urllib`) kullanıyor; ek kurulum adımı istemiyorlar.
- `danis` herkese açık bir repo ve GitHub Actions'ta Windows `.exe` derliyor; özel bir
  repoya bağımlılık CI'ı kırılabilir.
- Her repo kendi test paketini **tek başına** koşabilmeli.

Bunun yerine `tools/sync.py` ile kaynak, her tüketicinin paketine `_corclient.py`
adıyla kopyalanır. Bu, "5 kopya" yerine **"1 kaynak + 5 doğrulanabilir yansıma"**dır.
Kopya **elle düzenlenmez**; sapma senkron başlığındaki `sha256` ile yakalanır.

## Dürüst sınır

Bu bir bağımlılık değil, senkronlanan bir kopya düzenidir. Yani bir hatayı düzeltmek
**yine 5 repoya yansıtılmalıdır** — ama artık tek komutla (`sync.py`) ve sapma olursa
`--check` **kırmızı** döner. Tek doğruluk kaynağı kazanılmıştır; tek yazma yeri
kazanılmamıştır.

## Kullanım (tüketici repo)

Kaynağı kendi paketinize kopyalayın:

```bash
python3 tools/sync.py ../atlas/atlas/_corclient.py ../harita/harita/_corclient.py
```

Sapma denetimi (CI'ya koyun):

```bash
python3 tools/sync.py --check ../atlas/atlas/_corclient.py
```

Sapma varsa çıkış kodu `1` döner ve hangi hedefin neden kırıldığını stderr'e yazar.
Hedef yollar komut satırı argümanıdır; koda **gömülmez** (yerel yol sızıntısı yok).

Kopyaladıktan sonra `llm.py` ince kabuğunuz şu ismi dışa vermeye devam eder:
`LLMError`, `LLMClient`, `CorLLMClient`, `konak_kontrol`, `IZINLI_KONAKLAR`,
`DEFAULT_BASE_URL`, `DEFAULT_MODEL`, `MAX_TOKENS`. Mevcut testler ve CLI'lar böylece
**değişmeden** çalışır.

## Tüketici tablosu

| Repo | `DEFAULT_MODEL` | `MAX_TOKENS` | timeout | konak denetimi | başlat ipucu |
|---|---|---|---|---|---|
| atlas | `stealth/space-bunny-alpha` | 2000 | 60 | loopback | `cor start` |
| harita | `stealth/space-bunny-alpha` | 2000 | 60 | loopback **+ `0.0.0.0`** | `cor start` |
| orkestra | `nvidia/nemotron-3-ultra-550b-a55b:free` | 4000 | 120 | loopback | `cor start` |
| danis | `stealth/space-bunny-alpha` | 2000 | 60 | **yok** (`izinli_konaklar=None`) | `cor` |
| ne-izlesem | `stealth/space-bunny-alpha` | 2000 | 60 | **yok** (`izinli_konaklar=None`) | `cor claude` |

`danis` ve `ne-izlesem` bugün konak denetimi **yapmıyor**; bu refactor davranışı
değiştirmiyor, mevcut kararı koruyor. Bu iki araç kullanıcı dosyasını `COR_BASE_URL`'in
gösterdiği yere gönderir; diğer üçü loopback dışını reddeder. Tutarlılık istenirse
`izinli_konaklar=IZINLI_KONAKLAR` yapmak tek satırlık değişikliktir — ancak uzak cor
kullanan (WSL→Windows gibi) kurulumları kırabilir; bu karar ana oturumunundur.

## Geliştirme

```bash
python3 -m pytest -q
```

Testler gerçek bir yerel HTTP sunucusuna (`http.server`, `127.0.0.1`, boş port) gider.
Gerçek cor'a hiçbir ağ çağrısı yapılmaz; tüm veri kurgusaldır.
