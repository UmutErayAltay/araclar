# yol — PATH ve ortam değişkeni düzenleyici (plan)

Windows'un "Ortam Değişkenleri" penceresinin düzgün hali. PATH'teki ölü, tekrarlanan ve
gölgelenen girdileri bulur; hangi `python`/`node`'un gerçekten çalıştığını gösterir;
değişiklikleri önizleyip **yedek alarak** uygular; tek tıkla geri alır.

`ortam/` ile farkı: `ortam` kodun okuduğu değişkenleri belgelerle karşılaştırır (salt okunur,
repo odaklı). `yol` makinenin kendi ortam değişkenlerini yönetir (yazar, kullanıcı odaklı).

Bağlayıcılar: çekirdek **yalnız stdlib** (`winreg`, `ctypes`); web paneli Flask (`[web]`
extra); depo kökündeki `TASARIM.md`. Değer içeriği loglara/rapora yazılmaz; gizli görünen
değişkenler (`*KEY*`, `*TOKEN*`, `*SECRET*`, `*PASSWORD*`, `*PASS*`, `*PWD*` hariç `PWD`
kendisi, `*CREDENTIAL*`) panelde maskeli gelir, göster düğmesiyle açılır.

## 1. Kaynak katmanı (`kaynak.py`)

```python
class Kaynak(Protocol):
    def oku(self, kapsam: str) -> dict[str, Deger]        # kapsam: "kullanici" | "sistem"
    def yaz(self, kapsam: str, ad: str, deger: Deger) -> None
    def sil(self, kapsam: str, ad: str) -> None
    def yazilabilir(self, kapsam: str) -> bool
    def yayinla(self) -> None                            # değişikliği diğer süreçlere duyur

@dataclass(frozen=True)
class Deger:
    metin: str
    genisler: bool   # REG_EXPAND_SZ mi (True) REG_SZ mi (False)
```

- `WindowsKaynak`: kullanıcı `HKCU\Environment`, sistem
  `HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment`.
  **Tip korunur**: `REG_EXPAND_SZ` ise öyle yazılır (`%USERPROFILE%` gibi ifadeler genişletilmeden
  saklanır). Yazmadan sonra `SendMessageTimeoutW(HWND_BROADCAST, WM_SETTINGCHANGE, 0,
  "Environment", SMTO_ABORTIFHUNG, 5000)` (ctypes). Sistem kapsamı yönetici değilse
  `yazilabilir("sistem") == False` (`ctypes.windll.shell32.IsUserAnAdmin()`); v1'de sistem
  kapsamına yalnız yönetici yazar, değilse panel "salt okunur — yönetici olarak açın" der.
- `DosyaKaynak`: JSON dosyası (`{"kullanici": {...}, "sistem": {...}}`) — testler, Linux
  demosu ve ekran görüntüleri için. `YOL_KAYNAK=dosya:<yol>` ile seçilir.
- `SurecKaynak` (Linux/mac varsayılanı): `os.environ`, salt okunur, tek kapsam "surec".
  Panel "bu platformda yalnız okunur" şeridi gösterir.

Seçim: `os.name == "nt"` → Windows; değilse `YOL_KAYNAK` yoksa Süreç.

## 2. Analiz (`analiz.py`) — saf fonksiyonlar, kaynak bağımsız

PATH girdisi başına (kullanıcı ve sistem ayrı listeler, sıra korunur):

| bulgu | tanım | önerilen eylem |
|---|---|---|
| `yok` | genişletilmiş yol bir dizin değil | kaldır |
| `bos` | boş girdi (`;;`) | kaldır |
| `tekrar` | aynı kapsamda daha önce geçti (karşılaştırma: `%VAR%` genişletilmiş, `os.path.normcase`, sondaki `\` atılmış) | kaldır (ilkini tut) |
| `sistemde-var` | kullanıcı girdisi sistem PATH'inde zaten var | kaldır |
| `goreli` | mutlak değil (`.`, `bin`) | uyar |
| `uzun` | toplam PATH > 2047 karakter (bazı araçların sınırı) | özet uyarısı |

Etkin PATH sırası Windows'ta: **sistem önce, kullanıcı sonra**. `komutlar(ad)` bu sırayla
`PATHEXT` uzantılarını deneyip tüm eşleşmeleri döner; ilki "kazanan", gerisi "gölgede".
Varsayılan izlenen komutlar: `python`, `python3`, `py`, `pip`, `node`, `npm`, `npx`, `git`,
`java`, `javac`, `code`, `claude`, `cor`, `docker`, `uv`, `cargo`.
Özel tespit: kazanan `python`/`python3`
`…\Microsoft\WindowsApps\` altındaysa bulgu `store-taklidi` ("Microsoft Store kısayolu
gerçek Python'u gölgeliyor; Ayarlar → Uygulama yürütme diğer adları'ndan kapatın").

`temizlik_onerisi(kullanici_path, sistem_path) -> list[Degisiklik]`: yalnız **kullanıcı**
kapsamında `yok`/`bos`/`tekrar`/`sistemde-var` girdilerini kaldıran değişiklik listesi.
Sistem kapsamında öneri üretilir ama yalnız yönetici uygulayabilir.

## 3. Değişiklik ve yedek (`degisiklik.py`, `yedek.py`)

```python
@dataclass
class Degisiklik:
    kapsam: str; ad: str
    eski: Deger | None; yeni: Deger | None   # None = yok / silinecek
```

`uygula(kaynak, degisiklikler)`:
1. Her değişikliğin `eski` değeri kaynaktan **tazeden okunur**; uyuşmazsa hiçbir şey yazılmaz,
   `CakismaHatasi` ("değişken siz düzenlerken başka yerden değişti").
2. Yedek: `~/.yol/yedek/<UTC zaman damgası>.json` — etkilenen kapsamların **tam** anlık
   görüntüsü (tip bilgisiyle). Yedek yazılamazsa uygulama yapılmaz.
3. Yazma, sonra `yayinla()`. Bir yazma başarısız olursa o ana kadar yazılanlar yedekten
   geri yüklenir ve hata raporlanır.
4. `~/.yol/gunluk.jsonl`: zaman, ad, kapsam, eylem (değer YAZILMAZ, yalnız PATH için
   eklenen/çıkan girdiler yazılır — PATH gizli değildir).

`geri_al(kaynak, yedek_id)`: yedeği önizleme farkıyla döner; onaylanınca yedekteki duruma
döndürür (o da önce yeni bir yedek alır). Son 30 yedek tutulur.

## 4. CLI (`yol`)

```
yol denetle [--json]                 # bulgu tablosu + özet
yol nerede <komut>...                # kazanan + gölgedekiler
yol temizle [--uygula]               # kullanıcı PATH önerisi; varsayılan kuru (fark yazdırır)
yol ekle <dizin> [--basa] [--uygula] # kullanıcı PATH'ine ekle (dizin yoksa hata)
yol kaldir <dizin> [--uygula]
yol yedekler | yol geri-al <id> [--uygula]
yol web [--port 8797] [--ac]
```

## 5. Web paneli (Flask, port 8797) — `TASARIM.md` bağlayıcı

Üst şerit: "yol" + "PATH ve ortam değişkenleri" + platform/kapsam rozeti ("Windows ·
kullanıcı: yazılabilir · sistem: salt okunur").

Özet kartları: PATH girdisi (kullanıcı/sistem) · Sorunlu girdi · Gölgelenen komut ·
Son yedek ("2 saat önce").

Sekmeler (sayfa içi, `role="tablist"`):

1. **PATH** — iki liste (Sistem, Kullanıcı) etkin sırayla; her satır: sıra no, yol (genişletilmiş
   hali altında küçük metinle, `%VAR%` korunmuş hali üstte), bulgu rozetleri (metinli),
   yukarı/aşağı, kaldır düğmeleri. "Ekle" alanı (yol yazılır, sunucu var mı diye doğrular).
   "Önerilen temizliği uygula" düğmesi değişiklikleri **taslağa** koyar.
2. **Komutlar** — izlenen komut tablosu: komut, kazanan yol, gölgedeki sayısı (açılınca
   liste), bulgu (`store-taklidi`). Üstte serbest arama ("bir komut ara").
3. **Değişkenler** — kapsam filtresi + arama; satır: ad, değer (gizliyse maskeli + göster),
   tip (`genisler`), düzenle/sil. Yeni değişken ekleme formu. Uzun değerler kısaltılır.
4. **Yedekler** — liste (zaman, etkilenen ad sayısı), "farkı gör", "geri al".

**Taslak çubuğu (yapışkan alt):** bekleyen değişiklik sayısı + `Önizle` → fark paneli
(PATH için eklenen/çıkan girdi listesi, diğerleri için eski→yeni; gizli değerler maskeli)
→ `N değişikliği uygula` (yedek alınır notuyla). Uygulama sonrası "yeni açılan terminaller
değişikliği görür; açık olanları yeniden başlatın" bilgisi.

API: `GET /api/durum` (kapsamlar + bulgular + komutlar), `GET /api/yedekler`,
`GET /api/yedek/<id>/fark`, `POST /api/onizle` (değişiklik listesi → fark),
`POST /api/uygula` (değişiklik listesi + her birinin beklenen `eski` değeri),
`POST /api/geri-al/<id>`, `POST /api/dizin-var` (`{yol}` → bool; yalnız var/yok döner).
POST'larda Origin + CSRF; değer dönen uçlar gizli değerleri `goster=1` olmadan maskeler.

## 6. Testler

- `test_analiz.py`: tüm bulgu türleri, `%VAR%` genişletme, büyük/küçük harf, sondaki `\`,
  etkin sıra (sistem önce), PATHEXT, WindowsApps tespiti (sahte dizin ağacıyla).
- `test_degisiklik.py` (DosyaKaynak): yedek önce yazılır, çakışmada yazmaz, yarıda hata →
  geri yükleme, `genisler` tipi korunur, günlükte değer yok.
- `test_kaynak_windows.py`: `@pytest.mark.skipif(os.name != "nt")` — gerçek `HKCU\Environment`
  üzerinde `YOL_TEST_<rastgele>` değişkeni yazar/okur/siler (REG_EXPAND_SZ dahil), `finally`
  ile temizler. PATH'e DOKUNMAZ.
- `test_web.py`: Host/CSP/Origin/CSRF, maskeleme, çakışma 409.
- `test_web_e2e.py` (CI dışı): DosyaKaynak fixture'ıyla gerçek sunucu + Playwright;
  ekran görüntüleri `yol/ekran/`.
- CI: `testler.yml` matrisine `yol`; ayrıca yeni `yol-windows.yml` iş akışı
  (`windows-latest`, yalnız `yol/**` değişince) birim testlerini **gerçek winreg** ile koşar.

## 7. kule

`TOOLS["yol"] = {"port": 8797, "args": ["web", "--port", "8797"]}` + sekme (ana oturum).

## 8. Dalgalar

| Dalga | İş | Ajan |
|---|---|---|
| A | iskelet (`pyproject`, `README` taslağı), `kaynak.py`, `analiz.py`, `degisiklik.py`, `yedek.py`, CLI + birim testleri + `yol-windows.yml` | backend |
| B | Flask sunucu + API ∥ şablon/CSS/JS | backend ∥ frontend |
| C | e2e + ekran görüntüleri + README + CI matrisi | tester |
| D | kule sekmesi | ana oturum |

Bilinen sınır: Linux bulut oturumunda gerçek Windows yazma yolu yalnız CI'da doğrulanır;
gerçek makinede ilk kullanım önce `yol temizle` (kuru) ile.
