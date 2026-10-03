# devtemizle

Repolardaki `node_modules` / `__pycache__` / sanal ortam klasörlerini bulur, yaşına göre temizler. **Varsayılan kuru çalıştırmadır** — `--uygula` verilmeden tek bir dosya sistemi değişikliği yapılmaz. Yalnız Python standart kütüphanesi (3.11+).

## Ne yapar

`tara` adayları bulup `~/.devtemizle/son.json`'a raporlar (silmez), `goster` son raporu okur (yeniden taramaz), `sil` tazeden tarar ve `--uygula` varsa siler.

Aday türleri: `node_modules`, `__pycache__`, `.pytest_cache`, `.venv`, `venv`. Bir adayın **içine girilmez** (iç içe `node_modules` ayrı sayılmaz), `.git` içine de girilmez. Yaş = aday dizininin mtime'ı ile `.git/index` + `.git/HEAD` mtime'larının **en büyüğü** (son kullanılma). `--yas` **varsayılan 7 gün**; `0` filtreyi kapatır. Repo listesi verilmezse atlas DB'den gelir (`ATLAS_DB` ya da `~/.atlas/atlas.db`); `--root` verilirse o kökteki repolar derinlik 3'e kadar bulunur.

## Kurulum ve kullanım

```bash
cd devtemizle && pip install -e .    # ya da kurulum yapmadan: python -m devtemizle

devtemizle tara --root ~/Documents/projeler          # sadece tara, silme yok
devtemizle goster                                     # son rapor
devtemizle sil --root ~/Documents/projeler            # KURU çalıştırma
devtemizle sil --root ~/Documents/projeler --uygula   # gerçekten sil
devtemizle sil --tur node_modules --yas 30 --uygula   # filtreli
```

Rapor `~/.devtemizle/son.json`'a yazılır (`DEVTEMIZLE_DIR` ile dizin değişir); yazma atomiktir (geçici dosya + `os.replace`).

## Gerçek çıktı

`repoA`: 10 gün eski `node_modules` + `.venv`, 1 günlük `__pycache__` + `.pytest_cache`, `node_modules` bir junction. `repoB`: `pyvenv.cfg`'siz `venv`.

```console
$ devtemizle tara --root /tmp/dt_fake
2 repo bulundu, taraniyor...
repo           tur            boyut    yas(gun)  durum
.pytest_cache  .pytest_cache  0 B      1         silinebilir
.venv          .venv          17 B     10        silinebilir
node_modules   node_modules   39.1 KB  10        silinebilir
__pycache__    __pycache__    8.8 KB   1         silinebilir
node_modules   node_modules   0 B      0         baglanti
venv           venv           0 B      1         pyvenv-yok
ozet: 6 aday, 47.9 KB toplam, 47.9 KB silinebilir, 2 atlandi

$ devtemizle sil --root /tmp/dt_fake
KURU CALISTIRMA: 2 klasor silinecekti (39.1 KB). Silmek icin --uygula ekleyin.
  - ...\dt_fake\repoA\.venv  17 B  .venv
```

Kuru çalıştırma sonrası `repoA`'daki `.pytest_cache`, `.venv`, `node_modules` ve `src/__pycache__` duruyordu. `silinebilir` toplamı `atlandi` olanları içermez.

## Durumlar

| `durum` | Anlamı |
|---|---|
| `silinebilir` | Aday; yaş/tür filtresi geçerse silinir |
| `baglanti` | Symlink veya Windows junction — **hedefine dokunulmaz**, boyut 0 |
| `pyvenv-yok` | Adı `.venv`/`venv` ama `pyvenv.cfg` yok → sanal ortam **değildir** |

`sil --json` çıktısındaki `atlanan[].neden` bunlara ek olarak `tur-disi` (`--tur` listesinde değil) ve `yeni` (`--yas` eşiğinden genç) olur.

## Dürüstlük / güvenlik kuralları

Bunlar sözleşmedir, kod bunları zorlar:

- **`--uygula` olmadan hiçbir şey silinmez**; kuru çalıştırma `KURU CALISTIRMA` ile başlar.
- **Bağlantı hedefi silinmez** — `baglanti` olarak atlanır, `resolve()` edilmez.
- **Repo kökü dışına silinmez**: `yol.resolve().relative_to(repo.resolve())` tutmuyorsa `silinemedi(repo-disi)`.
- **`pyvenv.cfg`'siz sanal ortam silinmez** — adlandırma tek kanıt değildir.
- **Kilitli klasör yutulmaz**: yazma izni verilip bir kez daha denenir, yine silinemezse `silinemedi(kilitli: ...)`.
- **Atlas DB `mode=ro` ile açılır** — yazmaz, şema kurmaz.
- **Kapsam dışı:** Docker imajları/katmanları, WSL dosyaları, `~/.npm` ve pip cache'i taranmaz. Kule paneli kartı **v1'de yok**; kule bu aracı çalıştırmaz.

## Çıkış kodları

| `0` | Tamam — **`silinemedi` hata değildir**, sayılar raporda durur |
| `2` | Kullanım/keşif hatası: yol yok, atlas DB yok/okunamadı, repo yok, `--yas` negatif, rapor yok |

## Testler

```bash
python -m pytest -q
```
