# olubag

Projelerde **bildirilip hiç kullanılmayan bağımlılıkları** bulur (Python ve JS). **Tamamen salt okunur** — hiçbir dosyayı değiştirmez, yazma bayrağı yoktur. Yalnız Python standart kütüphanesi (3.11+).

## Ne yapar

`tara` verilen köklerin altındaki git repolarını bulur, her repoda bildirilen bağımlılıkları okur ve kaynak dosyalardaki gerçek `import`/`require` kullanımıyla karşılaştırır. Kullanılmayan her paket için `kullanilmayan` bulgusu verir.

**Bildirilen** yerler: `requirements*.txt`, `pyproject.toml` (`[project].dependencies` + `optional-dependencies`), `package.json` (`dependencies`).

**Kullanılan** yerler: Python kaynakları `ast` ile **çalıştırılmadan** okunur (`import X`, `from X import`); JS kaynakları metin taramasıyla (`require('x')`, `import x from 'x'`, `import('x')`).

Repo listesi verilmezse atlas DB'den gelir (`ATLAS_DB` ya da `~/.atlas/atlas.db`); `--kok` verilirse o kökteki repolar **derinlik 3**'e kadar bulunur. `node_modules`, `.git`, `.venv`, `venv`, `__pycache__`, `dist`, `build`, `.pytest_cache` atlanır; 1 MB'dan büyük ve ikili dosyalar okunmaz.

## Kurulum ve kullanım

```bash
cd olubag && pip install -e .    # ya da kurulum yapmadan: python -m olubag

olubag tara --kok ~/Documents/projeler
olubag tara --kok ~/a --kok ~/b --json
```

## Gerçek çıktı

```console
$ olubag tara --kok /tmp/ob_fake
repo                      dosya:satir       paket     tur
/tmp/ob_fake/projeler/r1  pyproject.toml:4  requests  kullanilmayan
/tmp/ob_fake/projeler/r1  pyproject.toml:4  rich      kullanilmayan
ozet: 1 repo, 2 kullanilmayan, 0 belirsiz
```

## Paket adı ↔ import adı eşlemesi

Paket adı ile import adı her zaman aynı değildir. Küçük bir tablo kullanılır:

| Bildirilen | Import | | Bildirilen | Import |
|---|---|---|---|---|
| `pyyaml` | `yaml` | | `python-dateutil` | `dateutil` |
| `python-multipart` | `multipart` | | `opencv-python` | `cv2` |
| `pillow` | `PIL` | | `python-dotenv` | `dotenv` |
| `beautifulsoup4` | `bs4` | | `psycopg[binary]` | `psycopg` |
| `scikit-learn` | `sklearn` | | `psycopg2-binary` | `psycopg2` |
| `dnspython` | `dns` | | `setuptools` | `pkg_resources` |
| `python-docx` | `docx` | | `python-pptx` | `pptx` |

Tabloda yoksa kural: **import adı = paket adı**, `-` → `_` ile (`flask-sqlalchemy` → `flask_sqlalchemy`). Adlar küçük harfe indirgenerek karşılaştırılır.

## İzin listesi (bulgu değildir)

Şunlar koda hiç import edilmeseler de "plugin gibi" çalıştıkları için **asla `kullanilmayan` sayılmaz**: `pytest`, `ruff`, `mypy`, `black`, `hatchling`, `setuptools`, `wheel`, `pip`, `nox`, `tox`, `coverage`, `pre-commit`, `twine`, `flake8`, `isort`, `pylint`, `pluggy`, `hatch`, `pip-tools`, `virtualenv`, `build` — ve `pytest-*` önekli tüm eklentiler.

## Bulgu türleri

| `tur` | Anlamı |
|---|---|
| `kullanilmayan` | Bildirilmiş ama kaynak dosyalarda hiç kullanılmamış |
| `belirsiz` | Kodda `__import__()` / `importlib.import_module()` (veya JS'te `require.resolve` / `createRequire`) var; adı çalıştırmadan çözülemez |

`belirsiz` bir **itiraz değil, tespittir**: "kesin kullanılmıyor" denemez, o yüzden `kullanilmayan` sayacına girmez. Kullanılan paket hiçbir koşulda işaretlenmez — belirsizlik yalnız kullanılmayan pakete uygulanır.

## Dürüstlük / güvenlik kuralları

- **Salt okunur**: hiçbir dosya yazılmaz, silinmez veya değiştirilmez; `--uygula` bayrağı **yoktur** (bilerek yok).
- **Kaynak kod çalıştırılmaz**: Python `ast` ile ayrıştırılır. Sözdizimi hatalı dosya atlanır (uydurma bulgu üretmez).
- **JS `devDependencies` taramada hiç yok sayılır** — yalnız `dependencies` bildirimi denetlenir.
- **Aynı paket iki dosyada da bildirilmişse tek kez raporlanır**; satır, ilk bildirildiği dosyadandır.
- **Secret değerleri hiçbir çıktıya girmez** — bu araç yalnız paket adı ve dosya:satır üretir.
- **Atlas DB `mode=ro` ile açılır** — yazmaz, şema kurmaz.

## Çıkış kodları

| `0` | Bulgu yok |
| `1` | Bulgu var (`kullanilmayan` veya `belirsiz`) — CI'ya bağlanabilir |
| `2` | Kullanım/keşif hatası: yol yok, repo yok, atlas DB yok/okunamadı (`Hata: ...` stderr'e, traceback yok) |

## Testler

```bash
cd olubag && python3 -m pytest -q
```