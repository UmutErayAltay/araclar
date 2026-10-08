# devtemizle v0.2 — "disk avcısı" planı

v0.1 yalnız repo içindeki 5 klasör türünü (`node_modules`, `__pycache__`, `.pytest_cache`,
`.venv`, `venv`) CLI ile raporlayıp siliyordu. v0.2 hedefi: **geliştirici makinesinde yer
kaplayan her şeyi** bulmak, ne kadar geri kazanılacağını ve neyin güvenle silinebileceğini
açıkça göstermek ve bunu güzel bir yerel web panelinden yapmak.

Değişmeyenler (bağlayıcı): varsayılan kuru çalıştırma; `--uygula`/onay olmadan dosya sistemi
değişmez; bağlantı (symlink/junction) izlenmez ve silinmez; çekirdek **yalnız stdlib**
(web paneli opsiyonel `Flask` bağımlılığı, `pip install -e .[web]`); mevcut testler
değiştirilmeden geçer (davranış korunur, yalnız genişler).

## 1. Aday türleri: kural tablosu (`turler.py`, yeni)

`tara.py`'deki sabit `ADAYLAR` sözlüğü yerine tek bir kural tablosu:

```python
@dataclass(frozen=True)
class Tur:
    ad: str                 # klasör adı (eşleşme tam ad, büyük/küçük harf duyarlı)
    grup: str               # "js" | "python" | "rust" | "jvm" | "genel"
    risk: str               # "guvenli" | "dikkat"
    kanit: tuple[str, ...]  # kardeş dosya/klasörlerden en az biri bulunmalı (boşsa kanıt gerekmez)
    aciklama: str           # panelde gösterilen tek cümle ("npm install ile geri gelir")
    yeniden: str            # geri getirme komutu ("npm install", "cargo build", …)
```

| ad | grup | risk | kanıt | yeniden |
|---|---|---|---|---|
| `node_modules` | js | guvenli | `package.json` | `npm install` |
| `.next` / `.nuxt` / `.turbo` / `.parcel-cache` / `.svelte-kit` | js | guvenli | `package.json` | `npm run build` |
| `__pycache__`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache` | python | guvenli | — | otomatik |
| `.tox`, `.nox` | python | guvenli | `tox.ini`/`noxfile.py`/`pyproject.toml` | `tox` |
| `.venv`, `venv` | python | guvenli **yalnız** `pyproject.toml`/`requirements*.txt`/`Pipfile`/`poetry.lock`/`uv.lock` varsa; yoksa `dikkat` ("bağımlılık listesi yok, yeniden kurulamayabilir") | `pyvenv.cfg` (mevcut kural) | `pip install -r …` |
| `target` | rust | guvenli | `Cargo.toml` | `cargo build` |
| `build` | jvm/genel | dikkat | `build.gradle*`/`pom.xml`/`CMakeLists.txt`/`setup.py` | proje derlemesi |
| `.gradle` | jvm | guvenli | `build.gradle*`/`settings.gradle*` | otomatik |
| `dist` | genel | dikkat | `package.json`/`pyproject.toml`/`setup.py` | derleme |
| `htmlcov`, `coverage` | genel | guvenli | — / `package.json` | test koşusu |

Kanıtı olmayan eşleşme **aday değildir** (rapora `atlandi: "kanit-yok"` ile girer). `dikkat`
türler panelde varsayılan **seçili gelmez**, CLI `sil` bunları yalnız `--dikkat-dahil` ile alır.
İç içe kural: bir adayın içine girilmez (mevcut davranış), `.git` atlanır.

## 2. Genel önbellekler (`onbellek.py`, yeni)

Repo dışında, kullanıcı başına bir kez bulunan önbellekler. Yol çözümü platforma göre
(`os.name == "nt"` → `%LOCALAPPDATA%`, `%APPDATA%`; diğer → `~/.cache`, `XDG_CACHE_HOME`).
Ortam değişkeni varsa (ör. `PIP_CACHE_DIR`, `npm_config_cache`, `UV_CACHE_DIR`,
`CARGO_HOME`, `GRADLE_USER_HOME`) o yol kullanılır.

| ad | Windows | Linux/mac | temizleme | risk |
|---|---|---|---|---|
| pip | `%LOCALAPPDATA%\pip\Cache` | `~/.cache/pip` | `pip cache purge` varsa onu, yoksa klasör | guvenli |
| npm | `%LOCALAPPDATA%\npm-cache` | `~/.npm/_cacache` | `npm cache clean --force` | guvenli |
| yarn | `%LOCALAPPDATA%\Yarn\Cache` | `~/.cache/yarn` | `yarn cache clean` | guvenli |
| pnpm store | `%LOCALAPPDATA%\pnpm\store` | `~/.local/share/pnpm/store` | `pnpm store prune` | guvenli |
| uv | `%LOCALAPPDATA%\uv\cache` | `~/.cache/uv` | `uv cache clean` | guvenli |
| cargo registry | `%USERPROFILE%\.cargo\registry` | `~/.cargo/registry` | klasör (`cache/`, `src/`) | guvenli |
| gradle | `%USERPROFILE%\.gradle\caches` | `~/.gradle/caches` | klasör | guvenli |
| playwright | `%LOCALAPPDATA%\ms-playwright` | `~/.cache/ms-playwright` | — | **dikkat** (tarayıcılar yeniden indirilir) |
| huggingface | `%USERPROFILE%\.cache\huggingface` | `~/.cache/huggingface` | — | **dikkat** (modeller GB'larca, yeniden indirilir) |

Docker: `docker system df --format json` çalışırsa (ikili PATH'te ve daemon açıksa) imaj /
konteyner / yerel volume / build cache boyutları **yalnız raporlanır**; panel kopyalanabilir
`docker system prune` komutunu gösterir ama **çalıştırmaz** (volume kaybı riski). Docker yoksa
satır "docker bulunamadı" olarak sessiz geçer, hata değil.

Komutla temizlemede: komut `shutil.which` ile bulunur, `subprocess.run([...], shell=False,
timeout=300)`; komut yoksa ya da hata dönerse klasör silmeye düşülmez, sonuç "komut başarısız"
raporlanır (önbellek dizini başka sürecin kilidi altında olabilir).

## 3. Keşif (`kesif.py` genişler)

- Mevcut iki yol korunur (atlas DB, `--root` derinlik 3).
- `--root` birden çok verilebilir (zaten), `--derinlik N` eklenir (varsayılan 3, en çok 8).
- Yeni `--ev` bayrağı: kullanıcı ev dizininden derinlik 5 tarama; şu dizinlere **girilmez**:
  `AppData`, `Library`, `.cache`, `.local`, `.npm`, `.cargo`, `.rustup`, `.gradle`, `OneDrive*`,
  `$Recycle.Bin`, `node_modules` (repo değil), gizli dizinler (`.` ile başlayan; `.git` hariç).
  Repo = içinde `.git` (dizin veya dosya) olan dizin.
- Her repo için ek meta (rapor + panel): son commit tarihi (`git log -1 --format=%ct`, 5 sn
  zaman aşımı; git yoksa `.git/HEAD` mtime), çalışma ağacı kirli mi (`git status --porcelain`
  boş değil mi). Kirli repo panelde rozetle gösterilir (silmeyi engellemez; aday türleri
  yeniden üretilebilir şeylerdir).

## 4. Rapor modeli (`rapor.py` genişler, geriye uyumlu)

`son.json` yeni alanlar alır, eski alanlar aynen kalır (`goster` eski raporu da okur):

```json
{
  "surum": 2, "olusturma": "...", "sure_sn": 12.4,
  "adaylar": [{"id": "a1b2c3d4", "repo": "...", "yol": "...", "tur": "node_modules",
               "grup": "js", "risk": "guvenli", "boyut": 0, "son_erisim": "...",
               "yas_gun": 0.0, "atlandi": null, "yeniden": "npm install"}],
  "onbellekler": [{"id": "...", "ad": "pip", "yol": "...", "boyut": 0, "risk": "guvenli",
                   "komut": ["pip", "cache", "purge"], "var": true}],
  "docker": {"var": true, "imaj": 0, "konteyner": 0, "volume": 0, "build_cache": 0} ,
  "repolar": [{"yol": "...", "son_commit": "...", "kirli": false, "aday_boyut": 0}]
}
```

`id` = yol + tür'ün sha1'inin ilk 12 hex'i (kararlı). Silme API'si yalnız `id` kabul eder.

Silinenler `~/.devtemizle/gunluk.jsonl`'a satır satır eklenir (zaman, yol, tür, boyut, sonuç):
panelde "geçmiş: toplam X GB geri kazanıldı" kartı buradan.

## 5. CLI (geriye uyumlu)

```
devtemizle tara [--root YOL]... [--ev] [--derinlik N] [--onbellek] [--json]
devtemizle goster [--json]
devtemizle sil [--root ...] [--tur T]... [--yas G] [--dikkat-dahil] [--onbellek AD]... [--uygula]
devtemizle web [--port 8796] [--ac]
```

`--onbellek` taramaya genel önbellekleri ekler. `sil --onbellek pip --uygula` yalnız o
önbelleği temizler. Mevcut bayrakların anlamı değişmez.

## 6. Web paneli (`devtemizle/web/`, Flask, port 8796)

Güvenlik ve görsel kurallar: depo kökündeki `TASARIM.md` (bağlayıcı). Referans: `liman/liman/web/`.

Sayfa yapısı (tek sayfa, sekmesiz):

1. **Üst şerit:** "devtemizle" + "Geliştirici çöpünü bul, güvenle temizle" + sağda
   `Tara` düğmesi (tarama sürerken `<progress>` + "142 repo taranıyor…" metni).
2. **Özet kartları (4):** Geri kazanılabilir (güvenli toplam) · Dikkat gerektiren ·
   Taranan repo / aday sayısı · Şimdiye kadar temizlenen (günlükten).
3. **Dağılım çubuğu:** tek yatay yığılmış çubuk, gruplara göre (js / python / rust / jvm /
   genel / önbellekler); her parça etiketli (renk + metin), altında lejant. SVG, satır içi
   stil yok (sınıflarla renk).
4. **Repolar tablosu:** repo başına bir satır (ad, son commit "4 ay önce", kirli rozeti,
   aday sayısı, toplam boyut ↓ sıralı); satıra tıklayınca altında adayları açılır
   (`<details>` ile, JS'siz de çalışır). Her aday satırında: onay kutusu, tür, boyut, yaş,
   risk rozeti, "geri getirme: `npm install`" küçük metni.
   Filtre çubuğu: tür grubu, en az yaş (gün), yalnız güvenli, arama (repo adı).
   Hızlı seçim: "30 günden eski tüm güvenli adayları seç".
5. **Genel önbellekler tablosu:** ad, yol (kısaltılmış, tam yol `title`'da), boyut, risk,
   temizleme yöntemi ("`pip cache purge` çalıştırılır"), onay kutusu.
6. **Docker kutusu:** boyutlar + kopyalanabilir komut, "panel bunu çalıştırmaz" notu.
7. **Alt onay paneli (yapışkan):** seçim varsa görünür: "7 öğe seçildi · 3.2 GB" +
   `Önizle` → listeyi gösteren onay paneli → `7 öğeyi sil (3.2 GB)` (`--hata` kenarlı).
   Silme sırasında ilerleme; bitince sonuç özeti (silinen / kilitli / atlanan) ve tablo tazelenir.

API (JSON, hepsi `127.0.0.1`, Host denetimi, CSP):
- `GET /` sayfa · `GET /api/rapor` son rapor · `GET /api/durum` tarama/silme ilerlemesi
- `POST /api/tara` `{kokler?: [...], ev: bool, onbellek: bool}` → arka plan iş parçacığı;
  aynı anda tek tarama (ikinci istek 409). Kökler sunucu başlarken verilen `--root`'lar
  ve `--ev` ile sınırlıdır; istemci keyfi yol veremez (yalnız bu kümeden seçer).
- `POST /api/sil` `{idler: [...], onbellekler: [...]}` → son rapordan çözülür, mevcut
  `sil` güvenlik denetimleri (repo altı mı, bağlantı mı, aday hâlâ var mı) **tekrar** yapılır.
  Origin + CSRF zorunlu.

`KULE_FRAME_ORIGIN` desteklenir (liman/atlas ile aynı fonksiyon).

## 7. kule entegrasyonu (ayrı depo: `/home/user/kule-public`)

`app/launcher.py` `TOOLS`'a `"devtemizle": {"port": 8796, "args": ["web", "--port", "8796"]}`,
`script.py` `TOOLS` listesi, `page.py` sekme düğmesi + kart + iframe paneli (liman blokları
kopyalanır), `tests/test_launcher.py` ad/port listeleri, `ERR_AD_YOK` mesajı.
Bunu ana oturum yapar (küçük, mekanik), ajan değil.

## 8. Testler

- Mevcut `tests/` olduğu gibi geçer.
- `test_turler.py`: her tür için kanıtlı/kanıtsız fixture; `dikkat` varsayılan dışı; venv
  bağımlılık listesi yoksa `dikkat`.
- `test_onbellek.py`: sahte `HOME`/`LOCALAPPDATA` ile yol çözümü (Windows yolları `os.name`
  monkeypatch ile), env değişkeni önceliği; komut yolu `subprocess.run` monkeypatch ile
  (gerçek `pip cache purge` ÇALIŞTIRILMAZ); docker yoksa sessiz.
- `test_kesif.py` ek: `--ev` hariç tutma listesi, derinlik sınırı.
- `test_web.py` (Flask test client): Host 403, CSP başlığı, KULE_FRAME_ORIGIN, POST Origin/CSRF
  403, `/api/sil` yalnız id kabul eder, raporda olmayan id → atlanır, bağlantı silinmez,
  tarama 409.
- `tests/test_web_e2e.py` (CI'da koşmaz): gerçek sunucu + Playwright, sahte fixture ağacı;
  ekran görüntüleri `devtemizle/ekran/` (masaüstü+mobil, açık+koyu; seçim + onay paneli açık
  hali dahil).

CI: `.github/workflows/testler.yml` matrisine `devtemizle` eklenir (`pip install pytest Flask`).

## 9. Dalgalar (ajan dağıtımı)

| Dalga | İş | Ajan |
|---|---|---|
| A | `turler.py`, `tara.py` kural tablosuna geçiş, `kesif.py` (`--ev`, derinlik, repo meta), `onbellek.py`, `rapor.py` v2, `sil.py` (id + önbellek + günlük), CLI + birim testleri | backend |
| B | `web/` Flask sunucu + şablon + `stil.css` + `panel.js`, `test_web.py` | backend (sunucu/API) ∥ frontend (şablon/CSS/JS) — sözleşme: §6 API |
| C | e2e + ekran görüntüleri, README güncelle, CI matrisi, hata düzeltme | tester |
| D | kule sekmesi | ana oturum |
