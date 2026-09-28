# danis

Terminalde çalışan, iki işi olan küçük bir yardımcı. LLM'e `cor` üzerinden
sorar — anahtar gerekmez, internet gerektiren ayrı bir sağlayıcı yok.

1. **Terminal hata asistanı** — bir komut başarısız olunca `danis` yazarsın,
   cor'a sorup kısa bir teşhis + tek satırlık düzeltme önerisi basar.
2. **"Bu dosyayı danis'e sor"** — `danis dosya rapor.pdf "özetle"` yerel bir
   dosyanın (txt/md/pdf/docx) metnini çıkarıp cevabı basar. Windows'ta
   dosyaya sağ tıklayıp menüden de çağrılabilir.

Yanıtlar kısa gelir (en fazla birkaç cümle). Amaç ekrana metin doldurmak
değil, "ne oldu, bir sonraki komutum ne olsun" sorusunu iki saniyede
yanıtlamak.

## Kurulum

```bash
pip install -r requirements.txt          # pypdf + python-docx
cd /path/to/danis
python3 -m danis.cli hata "git psh origin main" 127
```

`pyproject.toml` yalnızca pytest ayarları için var; içinde `build-system`
yok, yani `pip install -e .` **çalıştırılamaz** ve bir `danis` komutu PATH'e
kurulmaz. Bu yüzden her yerde modül olarak çağrılır: `python3 -m danis.cli ...`.

`cor` proxy ayrı bir servis; `cor` ile başlatılır. İstemci şu iki ortam
değişkenini okur:

| Değişken | Varsayılan |
|---|---|
| `COR_BASE_URL` | `http://127.0.0.1:8787` |
| `COR_MODEL` | `stealth/space-bunny-alpha` |

## Shell entegrasyonu (bash / zsh)

`shell/danis.sh` her komuttan sonra son komutun metnini `DANIS_LAST_CMD`'ye,
çıkış kodunu `DANIS_LAST_EXIT`'e yazar. Kanca `~/.bashrc` (veya `~/.zshrc`)
dosyasına tek satırla eklenir:

```bash
# ~/.bashrc  (zsh için ~/.zshrc)
[ -f /path/to/danis/shell/danis.sh ] && source /path/to/danis/shell/danis.sh
```

Yeni bir terminal açtıktan sonra:

```
$ ls /var/olmayan-dizin
ls: cannot access ...   (stderr, danis'ın işi değil)
❌ (çıkış 2) — danis
$ danis
🔎 TEŞHİS: Belirtilen dizin mevcut değil...
```

Dikkat: hata olduğunda otomatik LLM çağrısı **yapılmaz**, sadece ipucu basılır.
Nedeni ücretsiz olsa da her başarısız `grep` için bir istek demek; kararı
kullanıcı verir. Argüman verirsen doğrudan CLI'ya gider:
`danis dosya rapor.pdf "özetle"`.

PowerShell için aynı mantık `shell/danis.ps1` dosyasında; profiline ekle:

```powershell
notepad $PROFILE     # sonuna ekle:  . C:\path\to\danis\shell\danis.ps1
```

## Windows: sağ tık menüsü

`danis.exe` PATH'te değilse yolunu vererek kur:

```powershell
.\shell\install-context-menu.ps1 -DryRun                  # önce .reg içeriğini göster, KAYDETME
.\shell\install-context-menu.ps1 -ExePath C:\tools\danis.exe
```

`HKEY_CLASSES_ROOT` bir sistem anahtarı olduğu için **yönetici PowerShell'i**
gerekir. `-DryRun` gerçekten hiçbir şey yazmaz, sadece üretilecek `.reg`'i
basar — önce onu okumak her zaman iyi. Kaldırmak için
`HKEY_CLASSES_ROOT\*\shell\exefile\DanisaSor` anahtarını silmek yeterli.
Menü girdisi yalnızca `.exe` dosyalarında görünür (`\shell\exefile`), hepsinde
değil.

## Windows: `danis.exe` indirme

GitHub → Actions → son başarılı çalıştırma → **danis-win** artifact'ı. Tek
`.exe`, kurulum gerekmez. Bir PowerShell isteminde açmak için:

```powershell
.\danis.exe hata "git psh origin main" 127
```

## Bilinen sınırlamalar

- **stderr/stdout otomatik yakalanmıyor.** LLM'e yalnızca komut metni ve çıkış
  kodu gidiyor. `No such file or directory` gibi asıl hata mesajını danis
  görmez — teşhisi komutun kendisinden ve çıkış kodundan çıkarır. Her komutu
  `tee`/alt-kabuk ile sarmalamak genel amaçlı bir shell hook'unda invaziv ve
  riskli olduğu için bilerek yapılmadı.
- **PowerShell hook'u hiç çalıştırılmadı.** `shell/danis.ps1` bu geliştirme
  ortamında (Linux container) tek satır bile çalıştırılmadı — `pwsh` yok.
  `shell/danis.sh` ile satır satır simetrik yazıldı ve testler metin
  simetrisini kontrol ediyor, ama ilk gerçek kullanımda küçük bir düzeltme
  gerekebilir.
- **zsh dalı da test edilmedi.** Hook'taki zsh bloğu yazıldı, ancak bu ortamda
  `zsh` kurulu değil; `tests/test_shell_hook.py` bu yüzden onu *atlar*. Bash
  dalı gerçek alt süreçle test edilir.
- **Resim ve ikili dosyalar desteklenmiyor.** `danis dosya` metin türlerini
  okur; `.png`/`.zip`/`.exe` net bir hatayla reddedilir, NUL bayt içeren
  "metin" dosyaları da ikili sayılır. Önce OCR ile metne çevirmek gerekir
  (bkz. kısayol projesi) — bu bağımlılık değil, sadece yönlendirme.
- **Metin 12.000 karaktere kırpılır.** Çok uzun dosyaların sonu okunmaz;
  kırpıldıysa sona `[... kırpıldı ...]` eklenir.
- **Windows `.exe` doğrulanmamış.** Linux'ta PyInstaller ile üretilen ELF
  çalıştırıldı (build zinciri ve giriş noktası çalışıyor); Windows
  artifact'i ancak push sonrası Actions sekmesinde gerçekten koşuyor.

## Geliştirme

```bash
pip install -r requirements-dev.txt
python3 -m pytest -v
```

114 test, mock yok: bash hook gerçek alt süreçle, dosya çıkarma gerçek örnek
dosyalarla, HTTP katmanı yerel sahte `http.server` ile doğrulanır.
`@pytest.mark.integration` işaretli testler gerçek cor proxy'sine gider —
cor kapalıysa `python3 -m pytest -m "not integration"`.

## Mimari

- `danis/llm.py` — cor proxy'sine konuşan istemci (stdlib `urllib`, retry yalnız HTTP 5xx'te).
- `danis/hata_analiz.py` — hata prompt'u + `TEŞHİS:`/`DÜZELTME:` ayrıştırma.
- `danis/dosya_metni.py` — txt/md/pdf/docx metin çıkarma, ikili dosya reddi.
- `danis/context_menu.py` — `.reg` içeriğinin üretimi (Windows'a bağımlı değil, test edilebilir).
- `danis/cli.py` — argparse; iki alt komut.
- `docs/API.md` — tam sözleşme.
