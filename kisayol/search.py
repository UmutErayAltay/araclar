"""Vault + kod repolarında tam metin arama: "bunu hangi projede yaptım?"

İki motor var ve ikisi de aynı işi yapar, arayüzü tektir:

  * `rg` PATH'teyse `subprocess` ile çağrılır. `rg` `.gitignore`'ı zaten
    saygıyla karşılar, gizli dosyaları varsayılan olarak atlar, binary içerik
    bulmaz — bu yüzden fallback'in de aynı kuralları uygulaması gerekir,
    yoksa aynı sorgu iki makinede iki farklı cevap verir.
  * `rg` yoksa saf Python: `os.walk` + alt dizi karşılaştırması. Ağır bir
    bağımlılık (embedding, vektör DB, LLM) yok; hız ve basitlik öncelikli.

Eşleştirme **düz metindir** (`rg --fixed-strings`): `c++`, `(not)` gibi bir
sorguda regex sözdizimi hatası alıp kullanıcıya boş sonuç göstermektense
aradığı metni arar. Büyük/küçük harf `rg --smart-case` kuralına uyar: sorguda
büyük harf varsa duyarlı, yoksa duyarsız.

Bu modül **asla raise etmez** (Dalga A'nın kuralı): var olmayan/erişilemeyen
kök, okunamayan dosya, bozuk `rg` çıktısı ya da `rg`'nin askıya düşmesi sessizce
atlanır. `rg` çalıştırılamadığında arama Python motoruna düşer, yani `kp` hiçbir
zaman exception'a düşmez.

`.gitignore` **yalnızca `rg` tarafından** uygulanır; Python fallback'inde taklit
edilmez. Bu kasıtlı ve "beklenmeyen bir tutarsızlık" değil: `kp ara`'nın cevabı
"bu kod/notes sürüm kontrolünde mi" sorusudur. Bırakılan (ignored) bir dosya —
`config.yaml`, `.env`, `*.log` — çalışma ağacında duran gizli/yerel dosyalardır,
arama cevabında görünmemeleri doğrudur. Bu yüzden modüller arası eşitlik
gereksinimi *aynı motorun* iki kez çalıştırılmasıyla test edilir; iki motor
karşılaştırılırken de testler bunu açıkça hesaba katar (bkz. tests/test_search.py).

`.gitignore`'daki bu farkın dışında iki motor **aynı dosyaları** bulmak zorundadır:
gizli dosya/dizinler (`SKIP_HIDDEN`), sembolik bağlar, `build/` gibi ağır dizinler
ve binary içerik iki motorda da aynı şekilde elenir. Arama yüzeyi farklılaşırsa
"hangi makinede çalıştım" sorusunun cevabı da değişir.

Okuma tarafında iki savunma vardır ve ikisi de `open`den **önce** çalışır:
sembolik bağlar (kök dışına çıkabilirler) ve normal olmayan dosyalar (FIFO'da
`open` yazıcı bekler ve sonsuza kadar asılı kalır) atlanır. Sınır koymadan
`--no-ripgrep` ile çalışan bir kullanıcı, vault'unda bir log borusu bulunan bir
makinede takılı kalırdı.
"""
from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
from pathlib import Path
from typing import Any, Iterable, Iterator, NamedTuple

from kisayol.discovery import SKIP_DIR_NAMES

#: Kök bir git reposu değilse (not/vault dizini) sonuçlarda görünen etiket.
VAULT_LABEL = "vault"

#: Dosya başına en fazla bu kadar satır. Minified tek satırlık bir dosya
#: tek başına yüz binlerce sonuç üretip `--limit`'i anlamsız kılardı; `rg` için
#: `--max-count`, Python için döngü kesme.
MAX_HITS_PER_FILE = 20

#: `rg` askıya düşerse (ağ mount'u, sonsuz döngü) sonsuza kadar beklemeyelim.
RG_TIMEOUT = 30.0

#: Bir dosyanın binary sayılıp sayılmayacağına bakılan ilk bayt sayısı.
BINARY_SNIFF_BYTES = 8192

#: Gizli dosya/dizinler iki motorda da atlanır. `rg` bunu varsayılan olarak
#: yapar (bayrak verilmez); Python motoru de aynı kuralı uygular (`_is_skippable`
#: hem dosya adına hem dizin adına bakar). Bu bir seçim: Umut'un vault'unda
#: notlar `🏰 300-Projects/...` gibi emoji'li dizinlerde yaşıyor (gizli *değil*,
#: unicode) ve bunlar her iki motorda da bulunur.
#:
#: Kök dizinin kendisi istisnadır: kullanıcı `search_roots`'a nokta ile başlayan
#: bir yol yazdıysa (`.vault`, `~/.notes`) o *bilerek* seçilmiştir, `rg` de
#: böyle bir kökün içini tümüyle tarar. Kural yalnızca kökün *altındakilere*
#: uygulanır, yoksa `.vault` config'leyen kullanıcı hiçbir sonuç alamazdı.
SKIP_HIDDEN = True

_RG_FLAGS = (
    "--line-number",
    "--no-heading",
    "--smart-case",
    "--fixed-strings",
    "--color",
    "never",
    "--no-messages",
)


def _rg_skip_globs() -> list[str]:
    """SKIP_DIR_NAMES'i `rg`'ye glob olarak geçirir.

    `rg` bu dizinleri kendiliğinden atlamaz (`.gitignore` yalnızca gerçek bir
    git reposunun içinde uygulanır; vault dizini repo değildir). Python motoru
    `SKIP_DIR_NAMES`'i zaten atlıyor, bu glob'lar olmadan iki motor aynı soruya
    farklı cevap verirdi: `rg` bir `build/` klasörünü tarar, Python taramaaz.
    Liste `discovery.SKIP_DIR_NAMES`'ten türetilir — iki motorun atladığı
    dizinler tek kaynaktan gelir.
    """
    return [f"--glob=!{name}/**" for name in sorted(SKIP_DIR_NAMES)]


class SearchHit(NamedTuple):
    """Tek bir eşleşme satırı. `path` mutlaktır, `root_label` nereden
    geldiğini söyler (`vault` ya da repo adı) — kullanıcı sonucu açarken
    nereye bakacağını bilmeli."""

    path: str
    line_number: int
    line: str
    root_label: str


def search(
    query: str,
    roots: Iterable[Any],
    *,
    use_ripgrep: bool | None = None,
    max_per_file: int = MAX_HITS_PER_FILE,
) -> list[SearchHit]:
    """Köklerin altında `query`yi içeren satırları döndürür.

    Sıralama dosya mtime'ına göredir (en yeni önce): "en son ne yapmıştık"
    sorusunun cevabı, en son dokunulan dosyada aranır. Aynı dosyada satır
    numarası, eşitlikte yol ve etiket belirler — çıktı kararlıdır.

    `use_ripgrep=None` (varsayılan) motoru PATH'e bakar; `True`/`False` testlerin
    iki yolu da gerçekten çalıştırması içindir. `rg` yoksa, bozuksa ya da
    hata kodu döndürürse Python motoruna düşülür — çökme yerine sonuç.

    Boş sorgu veya hiç kök yoksa boş liste döner — hata değil, çağıran katman
    kendi mesajını basar.
    """
    text = (query or "").strip()
    if not text:
        return []

    limit = max(1, int(max_per_file))
    engine = _use_ripgrep(use_ripgrep)
    hits: list[SearchHit] = []

    for root, label in _normalize_roots(roots):
        try:
            if not root.is_dir():
                continue
        except OSError:
            continue
        scan = _search_ripgrep if engine else _search_python
        try:
            hits.extend(scan(root, label, text, limit))
        except OSError:
            continue

    return _sort_hits(hits)


def _use_ripgrep(use_ripgrep: bool | None) -> bool:
    """`None` iken PATH'e bakar; `rg` yoksa saf Python motoru seçilir."""
    if use_ripgrep is not None:
        return use_ripgrep
    return shutil.which("rg") is not None


def _normalize_roots(roots: Iterable[Any]) -> list[tuple[Path, str]]:
    """Kökleri (mutlak yol, etiket) çiftlerine çevirir; tekrarları atar.

    Aynı kök iki kez yazılmışsa (ya da bir kök diğerinin altındaysa) sonuçlar
    iki motor arasında da farklılaşmasın diye kök başına bir kez taranır.
    """
    normalized: list[tuple[Path, str]] = []
    seen: set[str] = set()

    for raw in roots or []:
        if not isinstance(raw, (str, os.PathLike)) or not str(raw).strip():
            continue
        path = Path(os.path.expanduser(str(raw).strip()))
        if not path.is_absolute():
            path = Path.cwd() / path
        key = os.path.normpath(str(path))
        if key in seen:
            continue
        seen.add(key)
        normalized.append((path, _root_label(path)))

    return normalized


def _root_label(root: Path) -> str:
    """Kök bir git reposu ise adı, değilse `vault`."""
    try:
        if (root / ".git").exists():
            return root.name or str(root)
    except OSError:
        pass
    return VAULT_LABEL


def _search_ripgrep(root: Path, label: str, query: str, limit: int) -> list[SearchHit]:
    """`rg`'yi kökün içinde çalıştırır, `path:satır:satır` çıktısını çözer."""
    rg = shutil.which("rg")
    if not rg:
        return _search_python(root, label, query, limit)

    argv = [
        rg,
        *_RG_FLAGS,
        *_rg_skip_globs(),
        "--max-count",
        str(limit),
        "-e",
        query,
        ".",
    ]
    try:
        proc = subprocess.run(
            argv,
            cwd=str(root),
            capture_output=True,
            timeout=RG_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        # Bozuk kurulum ya da askıya düşme: kullanıcı sonuçsuz kalmasın.
        return _search_python(root, label, query, limit)

    if proc.returncode not in (0, 1):  # 0: eşleşme var, 1: eşleşme yok
        return _search_python(root, label, query, limit)

    output = (proc.stdout or b"").decode("utf-8", errors="replace")
    hits = [_parse_rg_line(line, root, label) for line in output.splitlines()]
    return [hit for hit in hits if hit is not None]


def _parse_rg_line(line: str, root: Path, label: str) -> SearchHit | None:
    """`./app/main.py:12:telegram` → SearchHit. Anlaşılmayan satırlar atlanır.

    `rg` kökün içinde çalıştığı için göreli yol verir; `path` mutlak olmalı —
    kullanıcı satırı görüp dosyayı açmak istediğinde yapıştırdığı yol doğrudan
    işe yaramalı.
    """
    parts = line.split(":", 2)
    if len(parts) < 3:
        return None
    path, number, text = parts
    try:
        line_number = int(number)
    except ValueError:
        return None
    relative = path[2:] if path.startswith("./") else path
    return SearchHit(str(root / relative), line_number, text.rstrip("\r\n"), label)


def _search_python(root: Path, label: str, query: str, limit: int) -> list[SearchHit]:
    """Saf Python fallback: `os.walk` + satır satır alt dizi karşılaştırması."""
    matcher = _make_matcher(query)
    if matcher is None:
        return []

    hits: list[SearchHit] = []
    for path in _iter_files(root):
        for line_number, text in _scan_file(path, matcher, limit):
            hits.append(SearchHit(str(path), line_number, text, label))
    return hits


def _make_matcher(query: str) -> re.Pattern[str] | None:
    """`--fixed-strings --smart-case`in Python karşılığı: büyük harf varsa
    duyarlı, yoksa duyarsız düz metin."""
    flags = 0 if any(ch.isupper() for ch in query) else re.IGNORECASE
    try:
        return re.compile(re.escape(query), flags)
    except re.error:  # pragma: no cover - escape edilmiş kalıp burada çökmez
        return None


def _iter_files(root: Path) -> Iterator[Path]:
    """Kökün altındaki *normal* dosyaları üretir; ağır/gizli dizinlere inmez.

    `os.walk`'in `onerror`i boş: erişilemeyen dizin programı durdurmaz, sadece
    o dal taranmaz (Dalga A'daki keşifle aynı tavır).

    Dosyalar da süzülür, sadece dizinler değil: aksi hâlde kökün içindeki
    `.env`/`.htpasswd` gibi gizli dosyalar Python motoruna sızar, `rg` ise
    (varsayılan olarak) bunları hiç göstermez — aynı sorgu iki makinede iki
    farklı cevap verirdi. Aynı sebeple sembolik bağ atlanır: `rg` bağı izlemez,
    Python `os.walk`'ı izler ve bağın gösterdiği dosyayı ikinci kez, hatta
    döngüsel bağlarda sonsuza kadar raporlar.
    """
    for dirpath, dirnames, filenames in os.walk(str(root), onerror=lambda _e: None):
        dirnames[:] = [d for d in dirnames if not _is_skippable(d, is_dir=True)]
        for name in sorted(filenames):
            if not _is_skippable(name):
                yield Path(dirpath) / name


def _is_skippable(name: str, *, is_dir: bool = False) -> bool:
    """Adı ya da dosya türü bu girişi arama dışı bırakıyor mu?

    `is_dir` yalnızca ad tabanlı kuralın (SKIP_DIR_NAMES) dizinlere özgü
    olması için ayrım taşır: `build` adlı bir *dosya* normal dosyadır, `build/`
    dizini ise atlanır — `rg`'nin `--glob=!build/**` davranışı da böyledir.
    """
    if is_dir and name in SKIP_DIR_NAMES:
        return True
    return SKIP_HIDDEN and name.startswith(".")


def _is_readable_regular_file(path: Path) -> bool:
    """Sadece normal dosya mı? Sembolik bağ ve özel dosyalar elenir.

    **Neden `stat`?** `open()` FIFO'da (named pipe) yazıcı gelene kadar bloklanır
    — vault'ta `/var/run/docker.sock` ya da bir log borusu `open`i sonsuza
    kadar asılı tutar ve `kp ara` hiç dönmemeye başlar. Kontrol `open`'dan
    ÖNCE yapılmalıdır, çünkü sorun tam olarak `open`in bloklanmasıdır.

    `follow_symlinks=False`: bağın *kendisi* sorulur. `rg` sembolik bağları
    izlemez, biz de izlemeyelim — yoksa bir bağ klasör dışına çıkıp kökün
    dışından sonuç getirebilir. Sıfırlanmayan yarım yazılmış dosya (orphan inode)
    zaten `S_ISREG` değildir ve atlanır.
    """
    try:
        return stat.S_ISREG(os.stat(path, follow_symlinks=False).st_mode)
    except OSError:
        return False  # stat edilen de yok (kırık bağ) ya da erişilemiyor


def _scan_file(path: Path, matcher: re.Pattern[str], limit: int) -> list[tuple[int, str]]:
    """Binary dosyaları ve okunamayanları atlayarak eşleşen satırları verir."""
    # `open`den ÖNCE: FIFO/soket/cihazda open bloklanır (bkz. _is_readable_regular_file).
    if not _is_readable_regular_file(path):
        return []

    try:
        with path.open("rb") as f:
            if b"\0" in f.read(BINARY_SNIFF_BYTES):
                return []  # `rg` de null byte'lu içeriği binary sayar
    except OSError:
        return []

    found: list[tuple[int, str]] = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for line_number, line in enumerate(f, start=1):
                if matcher.search(line):
                    found.append((line_number, line.rstrip("\r\n")))
                if len(found) >= limit:
                    break
    except OSError:
        pass
    return found


def _sort_hits(hits: list[SearchHit]) -> list[SearchHit]:
    """En son değiştirilen dosya önce; eşitlikte yol/satır/etiket (kararlılık)."""
    mtimes: dict[str, float] = {}
    for hit in hits:
        if hit.path not in mtimes:
            mtimes[hit.path] = _mtime(hit.path)
    return sorted(
        hits,
        key=lambda h: (-mtimes[h.path], h.path, h.line_number, h.root_label),
    )


def _mtime(path: str) -> float:
    try:
        return os.stat(path).st_mtime
    except OSError:
        return 0.0
