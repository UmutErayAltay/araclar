# danis — sözleşme

İki özellik, tek paylaşılan çekirdek:

1. **Terminal Hata Asistanı** — bir shell komutu başarısız olunca `danis hata`
   komutu, cor üzerinden ücretsiz bir LLM'e sorup kısa bir teşhis + düzeltme
   önerisi bastırır.
2. **"Bu Dosyayı cor'a Sor"** — `danis dosya <yol> [soru]` komutu, yerel bir
   dosyanın (txt/md/pdf/docx) metnini çıkarıp cor'a sorar, cevabı basar.
   Windows'ta sağ-tık bağlam menüsünden de çağrılabilir.

Dil: Python 3.11+. Ek bağımlılık minimum tutulur (pypdf, python-docx dışında
stdlib). Neden Python (C# değil, `kisayol` gibi): bu iki özellik derin
Windows API kancası (global keyboard hook, OCR motoru) gerektirmiyor — sadece
HTTP + dosya okuma + hafif shell entegrasyonu. Python hem bu container'da
tam test edilebilir hem de ekosistemin geri kalanıyla (ne-izlesem, readbunny,
kule) tutarlı.

## Dizin yapısı

```
danis/
  danis/
    __init__.py
    llm.py            # CorLLMClient — ne-izlesem/app/llm.py ile AYNI desen
    hata_analiz.py     # prompt inşa + LLM yanıtını ayrıştırma (hata özelliği)
    dosya_metni.py     # dosya metni çıkarma (txt/md/pdf/docx)
    cli.py             # argparse: `danis hata`, `danis dosya`
  shell/
    danis.sh           # bash/zsh hook — gerçek bash ile test edilir
    danis.ps1          # PowerShell profile hook — bu container'da TEST EDİLEMEZ, dikkatle elle yazılır
    context-menu.reg.template   # Windows kayıt defteri şablonu (yer tutuculu)
    install-context-menu.ps1    # şablonu gerçek yollarla doldurup .reg olarak yazan + kaydeden script
  tests/
    conftest.py
    test_llm.py
    test_hata_analiz.py
    test_dosya_metni.py
    test_cli_hata.py
    test_cli_dosya.py
    test_cli_encoding.py # gerçek subprocess, PYTHONIOENCODING=cp1252
    test_shell_hook.py   # gerçek bash subprocess, danis.sh source edilir
  docs/API.md            # bu dosya
  .github/workflows/build-windows.yml   # PyInstaller onefile → danis.exe artifact
  README.md
  requirements.txt
  requirements-dev.txt
  pyproject.toml
  .gitignore
```

## `danis/llm.py` — `CorLLMClient`

`/home/user/ne-izlesem/app/llm.py` dosyasıyla BİREBİR aynı desen (dosyayı
oku, aynı yapıyı kopyala/uyarla): stdlib `urllib`, `POST {base_url}/v1/messages`
Anthropic uyumlu istek, yalnız HTTP 5xx'te retry, `LLMClient` Protocol'ü ile
test'te sahte istemci enjeksiyonu, boş yanıt `LLMError`. Ortam değişkenleri:
`COR_BASE_URL` (varsayılan `http://127.0.0.1:8787`), `COR_MODEL` (varsayılan
`nvidia/nemotron-3-ultra-550b-a55b:free`).

## `danis/hata_analiz.py`

```python
def prompt_olustur(komut: str, cikis_kodu: int) -> str: ...
def yaniti_ayikla(ham_metin: str) -> dict:  # {"teshis": str, "duzeltme": str | None}
```

- `prompt_olustur`: LLM'e Türkçe, KISA (en fazla 3 cümle teşhis + varsa tek
  satır düzeltme komutu) cevap iste. Modelden **katı biçim** iste:
  ```
  TEŞHİS: <1-3 cümle>
  DÜZELTME: <tek satır komut ya da "yok">
  ```
  (JSON değil düz metin — terminalde okunabilirlik önceliği; ayrıştırma iki
  satır başlığına göre yapılır.)
- `yaniti_ayikla`: yukarıdaki biçimi ayrıştırır; TEŞHİS/DÜZELTME satırları
  yoksa ham metnin tamamını `teshis` alanına koyar, `duzeltme=None` (LLM
  formatı tam uymasa bile kullanıcı en azından ham cevabı görür — sessiz
  başarısızlık YOK).

**Kapsam sınırı (bilerek):** v1'de stderr/stdout otomatik yakalanmıyor —
yalnızca komut metni + çıkış kodu LLM'e gidiyor. Neden: her komutu
tee/subshell ile sarmalamak invaziv ve riskli (genel amaçlı bir shell
hook'unda). Komut metni + çıkış kodu çoğu yaygın hata (yazım hatası, yanlış
bayrak, eksik alt komut) için zaten yeterli bağlam. README'de açıkça
belirtilir, gizlenmez.

## `danis/dosya_metni.py`

```python
def metni_cikar(dosya_yolu: Path) -> str: ...  # uzantıya göre yönlendirir
```

- `.txt`, `.md`, `.py`, `.json`, `.csv` ve bilinmeyen metin uzantıları → doğrudan oku (UTF-8, hata durumunda `errors="replace"`).
- `.pdf` → `pypdf.PdfReader`, sayfa sayfa `extract_text()` birleştir.
- `.docx` → `python-docx`, paragraf metinlerini birleştir.
- Desteklenmeyen uzantı (ör. resim) → `DosyaTuruDesteklenmiyorError` fırlat,
  CLI bunu kullanıcıya net Türkçe mesajla göstersin ("Bu dosya türü
  desteklenmiyor: .png. Önce OCR ile metne çevirin (örn. kısayol projesi)."
  — **kisayol'a gerçek entegrasyon kurmuyoruz, sadece kullanıcıya yönlendirme
  metni**, bu bir bağımlılık değil).
- Çıkarılan metin `MAX_KARAKTER = 12000` karakterde kırpılır (LLM prompt
  boyutu için), kırpıldıysa sona `\n\n[... kırpıldı ...]` eklenir.
- Boş/whitespace-only metin → `BosDosyaError`.

## `danis/cli.py`

```
danis hata <komut metni> <cikis_kodu>
danis dosya <dosya_yolu> [soru]
```

- `danis hata "git psh origin main" 127` → `hata_analiz.prompt_olustur` ile
  prompt kurar, `CorLLMClient().complete()` çağırır, `yaniti_ayikla` ile
  ayrıştırır, stdout'a:
  ```
  🔎 TEŞHİS: ...
  ✅ DÜZELTME: ...
  ```
  basar (DÜZELTME yoksa o satırı hiç basma). `LLMError` yakalanır, kullanıcıya
  "cor'a ulaşılamadı: <sebep>" mesajı basılır, **çıkış kodu 1** (sessiz
  başarı YOK).
- `danis dosya rapor.pdf "özetle"` → `metni_cikar` + LLM'e (soru verilmediyse
  varsayılan "Bu dosyayı 3-5 cümleyle özetle.") sorar, cevabı basar. Dosya
  yoksa / desteklenmeyen tür / boşsa açık hata mesajı + çıkış kodu 1.
- Her iki komut da `argparse` ile; `-h/--help` çalışır durumda olmalı.

### Kodlama sözleşmesi (Türkçe çıktı)

Tüm kullanıcıya dönük metin Türkçedir ve Türkçe noktasız `ı` (U+0131) içerir.
Windows'ta stdout bir **konsola değil boruya** (yönlendirme, CI log toplama)
bağlandığında Python ANSI kod sayfasına (varsayılan `cp1252`) düşer; `cp1252`
`ı`yı kodlayamadığı için `danis --help` `UnicodeEncodeError` ile çöker ve
`Build Windows` işinin smoke test adımını düşürürdü.

Bu yüzden `main()`, `argparse` çalışmadan **önce** `_utf8_akislari_zorla()` ile
`sys.stdout`/`sys.stderr`'ı `encoding="utf-8", errors="replace"` olarak sabitler.
`errors="replace"` bilinçlidir: kodlanamayan bir karakterde çökmek yerine yer
tutucuyla devam edilir. Tek noktada yapılır — `shell/danis.sh` ve `danis.ps1`
`python3 -m danis.cli` çağırdığı için ikisi de aynı `main()`'den geçer.

`PYTHONIOENCODING=cp1252` altında `stdout` `strict`, `stderr` ise
`backslashreplace` ile başlar: yani **asıl çökme stdout'tadır**; stderr zaten
çökmeyip Türkçe harfleri `ı` biçiminde bozuk basardı. Sabitleme ikisini de
düzeltir. `tests/test_cli_encoding.py` bu sözleşmeyi GERÇEK alt süreçle korur
(mock yok).

## `shell/danis.sh` (bash/zsh)

- `PROMPT_COMMAND`'a eklenen bir fonksiyon: her komuttan sonra `$?`'yi
  `DANIS_LAST_EXIT`'e, `$(history 1)`'den ayıklanan son komut metnini
  `DANIS_LAST_CMD`'ye yazar (kendi başına `danis`/`history` çağrılarını hariç
  tutar ki sonsuz döngü/gürültü olmasın).
- `DANIS_LAST_EXIT != 0` ise **otomatik LLM çağrısı YAPMAZ** (maliyet/gürültü
  riski) — sadece stderr'e kısa bir ipucu basar: `❌ (çıkış $DANIS_LAST_EXIT) — danis` .
- `danis` adında bir shell fonksiyonu tanımlar: argümansız çağrılırsa
  `DANIS_LAST_CMD`/`DANIS_LAST_EXIT`'i kullanarak `python3 -m danis.cli hata
  "$DANIS_LAST_CMD" "$DANIS_LAST_EXIT"` çağırır (paket kurulu olmalı, `pip
  install -e .` veya PyPI/exe sonrası `danis` komutu PATH'te).
- **Test edilebilirlik:** `tests/test_shell_hook.py` gerçek bir bash alt
  süreci başlatıp `source shell/danis.sh`, sonra kasıtlı başarısız bir komut
  (`ls /var/olmayan-dizin-xyz`) çalıştırıp `echo $DANIS_LAST_EXIT`/`echo
  $DANIS_LAST_CMD` çıktısını doğrular — mock yok, gerçek bash.

## `shell/danis.ps1` (PowerShell)

`danis.sh` ile AYNI davranış: `$function:prompt`'a `$LASTEXITCODE` takibi
ekler, `danis` fonksiyonu tanımlar. **Bu container'da `pwsh` yok, test
edilemez** — README'de ve kod başında açık yorumla belirtilir (ne-izlesem'in
TMDB_API_KEY durumuna benzer, bilinen ve kabul edilen bir sınır, gizlenmez).
Mantığın `danis.sh` ile birebir simetrik olması elle gözden geçirilir.

## Windows sağ-tık entegrasyonu

- `shell/context-menu.reg.template`: `HKEY_CLASSES_ROOT\*\shell\DanisaSor`
  altına `command` = `"<DANIS_EXE_YOLU>" dosya "%1"` yazan şablon,
  `<DANIS_EXE_YOLU>` yer tutucusu.
- `shell/install-context-menu.ps1`: kullanıcıdan/otomatik olarak `danis.exe`
  gerçek yolunu bulur (PATH veya kendi dizini), şablonu doldurup geçici bir
  `.reg` üretir, `reg import` çalıştırır. **Bu da Windows'a özgü, container'da
  test edilemez** — script'in kendisi elle gözden geçirilir, `-WhatIf`
  benzeri bir `-DryRun` bayrağı ile üretilen `.reg` içeriğini yazdırıp
  gerçekten import ETMEDEN de çalıştırılabilir olmalı (bu kısmı, DryRun
  modunu, container'da test edebiliriz: dosya içeriği string olarak
  doğrulanır).

## `.github/workflows/build-windows.yml`

`windows-latest` runner'da `pip install -r requirements.txt pyinstaller`,
`pyinstaller --onefile --name danis danis/cli.py` (entry point `danis/cli.py`
içine `if __name__ == "__main__": main()` eklenir), üretilen `dist/danis.exe`
artifact olarak yüklenir. `kule`/`kisayol`'daki gibi push/PR tetikleyicili.
Bu workflow GERÇEK CI'da çalışıp doğrulanacak (bu container'da test edilemez,
ama push sonrası Actions sekmesinde gerçek sonucu görülür — dürüstçe
belirtilmeli, "test ettim" denmemeli).

## Test felsefesi (mevcut ekosistemle aynı)

Mock YOK: gerçek bash subprocess, gerçek örnek dosyalar (küçük bir .txt/.md/
.pdf/.docx tests/fixtures/ altında), cor için yerel sahte `http.server`
(ne-izlesem/tests'teki desendeki gibi). `tests/test_cli_encoding.py` de aynı
felsefeyle GERÇEK alt süreç başlatır — `PYTHONIOENCODING=cp1252` verilerek
Windows'taki dar kod sayfası taklit edilir. `@pytest.mark.integration` gerçek
cor proxy'sine karşı (bu container'da `cor start` ile MEVCUT, çalıştırılabilir)
— varsayılan `pytest` çalıştırmasında bu marker'lı testler de dahil (cor
gerçekten burada çalışıyor, atlamaya gerek yok; sadece CI'da cor yoksa diye
`addopts` ile decoupled bırakılabilir, agent karar verebilir).

## Hata/başarı sözleşmesi

- Hiçbir fonksiyon "başarılı" dönüp sessizce boş/anlamsız veri üretmez.
- LLM boş yanıt / format dışı yanıt verirse kullanıcıya HAM yanıt gösterilir,
  asla uydurulmuş bir "DÜZELTME" basılmaz.
- CLI hata durumlarında her zaman çıkış kodu ≠ 0.
