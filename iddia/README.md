# iddia

Repo README'lerindeki **somut iddiaları** kodun gerçekliğiyle karşılaştırır. **Tamamen salt okunurdur** — hiçbir komut dosya sistemi değişikliği yapmaz; `--uygula` bayrağı ve yazma yapan alt komut **yoktur**. Yalnız Python standart kütüphanesi (3.11+).

## Ne yapar

`README.md` içindeki dört tür somut iddiayı regex ve sayımla denetler. LLM kullanılmaz, tahmin yürütülmez:

| `tur` | İddia örneği | Gerçek nasıl bulunur |
|---|---|---|
| `test-sayisi` | "1200 test", "~42 tests" | test dosyalarındaki `def test_` (py) / `it(`+`test(` (js) sayısı |
| `dosya-yolu` | "`app/main.py` çalıştırır" | repo içinde o yolun var olup olmadığı |
| `cli-bayragi` | "`--uygula` ile silinir" | o dizinin kaynak dosyalarında geçip geçmediği |
| `sayi-kaynak` | "9 komut sunuyor" | argparse `add_parser(` sayısı |

Sapma kuralı: `|iddia − gerçek| > max(2, 0.1 × gerçek)` ise bulgudur. Küçük sayılarda 2'lik taban, "1–2 test farkı"nı gürültüden çıkarır.

Her bulgu: `repo`, `README yolu:satır`, `tur`, iddia metni (≤100 karakter) ve bulunan gerçek.

## Kurulum ve kullanım

```bash
cd iddia && pip install -e .    # ya da kurulum yapmadan: python -m iddia

iddia tara --kok ~/Documents/projeler
iddia tara --kok ~/a ~/b --json     # birden fazla kök, JSON çıktı
```

`--kok` zorunludur ve tekrar edilebilir. Kökün altında **derinlik 3'e kadar** içindeki git repoları (`.git` klasörü **veya dosyası** — worktree/alt modül) bulunur; bulunan bir repoya içine girilmez. `node_modules`, `.git`, `.venv`, `venv`, `__pycache__`, `dist`, `build`, `.pytest_cache` atlanır. **1 MB'tan büyük** ve **ikili** (NUL içeren) dosyalar okunmaz — PNG veya minify bundle yanlış bulgu üretmez.

## Gerçek çıktı

```console
$ iddia tara --kok /home/user
21 repo tarandi; salt-okunur.
repo       readme              tur          iddia             gercek
orkestra   README.md:265       cli-bayragi  --hedef           kaynakta yok
danis      README.md:125       test-sayisi  114 test -> 3023 test
bagimlilik README.md:137       dosya-yolu   app/collectors/x.py  yol yok
ozet: 3 bulgu (1 cli-bayragi, 1 dosya-yolu, 1 test-sayisi)
```

`--json` aynı veriyi `{"surum", "bulgu_sayisi", "repo_sayisi", "tur_sayimi", "bulgular"}` olarak yazar (`ensure_ascii=False`).

## Dürüstlük / güvenlik kuralları

Bunlar sözleşmedir, kod bunları zorlar:

- **Salt okunur**: hiçbir yol dosya yazmaz, silmez veya değiştirmez. Yazma bayrağı yoktur.
- **Emin olunamayan türden bulgu üretilmez.** Test dosyası yoksa `test-sayisi`, argparse yoksa `sayi-kaynak` denetlenmez — yanlış pozitif, bulgudan kötüdür.
- **`sayi-kaynak` yalnız "N komut" için çalışır.** "9 kaynak", "8 modül", "5 endpoint" gibi kalıplar için güvenilir sayım yöntemi yoktur; o türler hiç üretilmez.
- **Atlanan yollar**: URL, glob (`*`), yer tutucu (`<...>`, `{...}`), komut satırı, ortam değişkeni (`ANAHTARLIK_DIR/tuz`), CIDR (`127.0.0.0/8`), tarih yer tutucusu (`YYYY-MM-DD.md`), uzantı listesi (`png/jpg/gif`), sürüm (`v1.2`), kök dışı (`../gizli.py`).
- **Gitignore'lu yollar** (`.env`, `.gitignore`, `node_modules/…`) bulgu üretmez — yalnızca kullanım tarifidir.
- **Veri kasası notları denetlenmez**: `daily/`, `notes/`, `knowledge/` gibi kullanıcı verisi dizinlerinin altındaki README'ler bir araç sözleşmesi değildir.
- **Fenced kod blokları iddia sayılmaz**; satır numarası yine de kullanıcının gördüğü satırdır.
- **Tırnak içindeki metin bir örnektir, iddia değildir** — `"1200 test" diye örnek veren` bir doküman kendi test sayısını iddia etmiyordur. Yalnızca *sayı* türlerinde (test/komut) uygulanır; tırnak içindeki **yol** (`"`app/main.py`"`) bu turda sayılır, çünkü o kalıbın kendisi bir iddiadır.
- **Monorepo'da test sayısı araç başına sayılır**: `harita/README.md` "10 test" dediğinde `harita/tests/` sayılır, komşu aracın 900 testi toplama girmez. Kökteki README ise tüm repoyu kapsar.
- **Paket iç içe monorepo'lar**: `danis/README.md` "`danis/llm.py`" derken gerçek dosya `danis/danis/llm.py` olabilir — yol, repo içinde bir *sonuç* olarak da aranır.
- **Kapsam dışı:** README'ler dışındaki dokümantasyon (docs/, docstring), yorum satırları, çeviri dosyaları denetlenmez.

## Çıkış kodları

| `0` | Tarama bitti, **bulgu yok** |
| `1` | Tarama bitti, **en az bir bulgu var** |
| `2` | Kullanım/keşif hatası: yol yok, repo bulunamadı, `--kok` verilmemiş |

Hatalar `Hata: ...` biçiminde **stderr**'a yazılır; iz (traceback) basılmaz.

## Testler

```bash
python -m pytest -q
```

Testler `tmp_path` altında sahte repo kurar; gerçek git çalıştırılmaz, ağ yoktur. Dört türün her biri için pozitif (iddia aykırı → bulgu) ve negatif (iddia doğru / tolerans içinde / sayılamaz → bulgu yok) testi vardır. `tree_hash` ile taramanın dosya sistemini değiştirmediği de kanıtlanır.