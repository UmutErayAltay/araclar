Build the core of `yol`, a PATH / environment-variable editor (Windows-first, testable on Linux).
Product plan: see context file PLAN.md (Turkish). `yol/kaynak.py` is DONE and is the source layer — use its API exactly, do not rewrite it.

Constraints: Python 3.11+, stdlib only. Turkish identifiers like the existing code (e.g. `analiz`, `bulgu`), ASCII-only comments, `from __future__ import annotations`, short module docstring. Never swallow errors silently. Never write variable VALUES to logs (only names; PATH entry add/remove lists are OK because PATH is not secret).

## yol/analiz.py (pure functions; no I/O except the injected callables)

```python
UZUN_SINIR = 2047
IZLENEN = ("python","python3","py","pip","node","npm","npx","git","java","javac","code","claude","cor","docker","uv","cargo")

@dataclass
class Girdi:
    kapsam: str        # "sistem" | "kullanici" | "surec"
    sira: int          # 0-based index inside its own scope list
    ham: str           # raw text as stored (may contain %VAR%)
    genis: str         # expanded text
    bulgular: list[str]  # subset of: "yok","bos","tekrar","sistemde-var","goreli"

def genislet(metin: str, ortam: Mapping[str,str], windows: bool) -> str
    # windows=True: replace %NAME% case-insensitively from ortam (unknown %X% left as-is).
    # windows=False: os.path.expandvars-like $NAME / ${NAME} using ortam (not os.environ).
def anahtar(yol: str, windows: bool) -> str
    # comparison key: strip trailing "\\" and "/" (but keep a bare root like "C:\\" or "/"),
    # windows: casefold and replace "/" with "\\".
def parcala(metin: str, ayirici: str) -> list[str]   # split, keep empty entries (they are "bos")
def girdileri_analiz(kapsamlar: dict[str, str], ayirici: str, ortam: Mapping[str,str], windows: bool,
                     dizin_var: Callable[[str], bool] = os.path.isdir) -> list[Girdi]
    # kapsamlar maps scope -> raw PATH text, in EFFECTIVE order (dict order; caller passes sistem first).
    # bos: entry.strip()=="" ; yok: not bos and not dizin_var(genis);
    # tekrar: same anahtar seen earlier IN THE SAME scope; sistemde-var: scope=="kullanici" and anahtar present in "sistem" scope;
    # goreli: not bos and not absolute (windows: must match r"^[A-Za-z]:[\\/]" or start with "\\\\"; posix: startswith "/").
def etkin_dizinler(girdiler: list[Girdi]) -> list[str]   # genis of non-bos entries in order, first occurrence per anahtar
def komut_ara(ad: str, dizinler: list[str], windows: bool, pathext: list[str],
              dosya_var: Callable[[str], bool]) -> list[str]
    # all matches in order. windows: if ad already ends with an ext in pathext (case-insens) try ad itself, else try ad+ext for each ext in order.
    # posix: dir/ad if dosya_var(path). Join with "\\" on windows, "/" otherwise (do not use os.path.join - must work cross-platform in tests).
def store_taklidi(yol: str) -> bool   # casefold contains "\\microsoft\\windowsapps\\"
def komut_raporu(dizinler, windows, pathext, dosya_var, adlar=IZLENEN) -> list[dict]
    # [{"ad","kazanan": str|None,"golgede": [..],"bulgu": "store-taklidi"|None}] ; bulgu only for python/python3/py whose kazanan is store_taklidi.
def temizlik_onerisi(ham_path: str, girdiler: list[Girdi], ayirici: str, kapsam: str = "kullanici") -> str | None
    # new raw PATH text for `kapsam` with entries flagged yok/bos/tekrar/sistemde-var removed, order and raw text of kept entries preserved.
    # returns None if nothing to remove.
def ozet(girdiler, komutlar, toplam_uzunluk: int) -> dict
    # {"girdi": {scope: count}, "sorunlu": n, "golgelenen": n (komut with golgede), "uzun": toplam_uzunluk > UZUN_SINIR}
```

## yol/gizli.py
```python
DESENLER = ("KEY","TOKEN","SECRET","PASSWORD","PASSWD","PASS","PWD","CREDENTIAL","AUTH","PRIVATE")
def gizli_mi(ad: str) -> bool   # upper-case substring match; but ad.upper() in {"PWD","OLDPWD"} -> False
def maskele(metin: str) -> str  # "" -> "" ; otherwise fixed "••••••••" (never leak length)
```

## yol/yedek.py
```python
def dizin() -> Path            # YOL_DIR env or ~/.yol
YEDEK_SAYISI = 30
ID_RE = re.compile(r"^\d{8}T\d{6}\d{6}Z$")   # e.g. 20261008T153000123456Z (UTC, microseconds)
def yedek_al(kaynak: Kaynak, kapsamlar: Iterable[str]) -> str
    # snapshot = {"id","zaman": iso,"kaynak": kaynak.ad,"kapsamlar": {scope: {name: Deger.sozluk()}}}
    # write atomically to dizin()/"yedek"/f"{id}.json" (tempfile+os.replace). Any OSError -> raise YedekHatasi.
    # ids must be unique even when called twice in the same microsecond (bump until unused). Prune oldest beyond YEDEK_SAYISI.
def yedekler() -> list[dict]   # newest first: [{"id","zaman","kapsamlar": {scope: count}}]; skip unreadable files
def yedek_oku(id: str) -> dict # validate ID_RE first (else YedekHatasi) — prevents path traversal; returns snapshot with Deger objects
def gunluk_ekle(kayit: dict) -> None  # append one JSON line to dizin()/"gunluk.jsonl", adds "zaman"
class YedekHatasi(RuntimeError)
```

## yol/degisiklik.py
```python
@dataclass(frozen=True)
class Degisiklik:
    kapsam: str; ad: str
    eski: Deger | None   # expected current value (None = expected absent)
    yeni: Deger | None   # None = delete
    def sozluk(self) -> dict ; @classmethod sozlukten(cls, d) -> Degisiklik
class CakismaHatasi(RuntimeError)     # value changed since it was read
class YetkiHatasi(RuntimeError)       # scope not writable
class UygulamaHatasi(RuntimeError)    # write failed; .geri_yuklendi: bool
def uygula(kaynak, degisiklikler: list[Degisiklik]) -> str   # returns backup id
    # 1. empty list -> ValueError. every kapsam must be kaynak.yazilabilir -> else YetkiHatasi (nothing written).
    # 2. re-read each affected scope ONCE; compare current value vs d.eski (None vs absent) -> CakismaHatasi listing names (nothing written).
    # 3. yedek_al(kaynak, affected scopes) — if it raises, nothing is written (propagate YedekHatasi).
    # 4. apply in order (yaz or sil). On any exception: restore every already-applied change to its d.eski (write or delete),
    #    then raise UygulamaHatasi(geri_yuklendi=<restore succeeded>) chained from the original error.
    # 5. kaynak.yayinla() (errors here are reported but do not undo: raise nothing, return id; log "yayinla_hatasi" in gunluk).
    # 6. gunluk_ekle per change: {"kapsam","ad","eylem": "ekle"|"degistir"|"sil","yedek": id} and, for name PATH (case-insensitive),
    #    "eklenen"/"cikan" entry lists computed with analiz.parcala using kaynak.ayirici. NEVER other values.
def geri_al_plani(kaynak, yedek_id: str) -> list[Degisiklik]
    # diff current state vs snapshot for the snapshot's scopes: names whose value differs or that exist only on one side.
    # eski = current value, yeni = snapshot value (None if absent in snapshot).
def path_farki(eski: str, yeni: str, ayirici: str) -> dict   # {"eklenen": [...], "cikan": [...]} order-preserving, multiset-aware is not needed (set semantics on raw text)
```

## yol/durum.py (shared by CLI and the future web panel)
```python
def platform_bilgisi(kaynak) -> dict   # {"kaynak": kaynak.ad, "windows": bool, "ayirici", "kapsamlar": [{"ad","yazilabilir"}]}
def path_durumu(kaynak, ortam=None, dizin_var=os.path.isdir, dosya_var=os.path.isfile, pathext=None) -> dict
    # reads "PATH" (case-insensitive name lookup per scope; Windows uses "Path" often) from each scope in kaynak.kapsamlar() order
    # (WindowsKaynak/DosyaKaynak give sistem then kullanici). ortam defaults to os.environ merged with all scope values (scope values win).
    # pathext defaults to (ortam PATHEXT or ".COM;.EXE;.BAT;.CMD").split(";") on windows, [] otherwise.
    # returns {"girdiler": [asdict(Girdi)], "komutlar": komut_raporu(...), "ozet": ozet(...), "oneri": {scope: new_text} only for writable "kullanici" when temizlik_onerisi not None,
    #          "path_adlari": {scope: actual stored name or None}}
def degiskenler(kaynak, goster: bool = False) -> list[dict]
    # [{"kapsam","ad","deger": masked unless goster or not gizli,"gizli": bool,"genisler": bool,"uzunluk": len}] sorted by kapsam then ad.casefold()
```

## yol/cli.py  (`yol` command; argparse; exit codes 0 ok, 1 findings/refused, 2 usage error)
- `yol denetle [--json]` — table: scope, #, entry (raw), findings; then command table (ad, kazanan, golgede count, bulgu); then one-line summary. Exit 1 if any problem entry.
- `yol nerede <komut>...` — winner + shadowed paths per command (searches with the same rules); exit 1 if not found.
- `yol temizle [--uygula]` — shows path_farki of the suggestion for "kullanici"; without --uygula prints "kuru calistirma" and changes nothing; with --uygula calls uygula() and prints backup id.
- `yol ekle <dizin> [--basa] [--uygula]` / `yol kaldir <dizin> [--uygula]` — on "kullanici" PATH; ekle refuses non-existing dir and duplicates (anahtar compare); kaldir matches by anahtar of genislet. Preserve Deger.genisler of existing PATH; new PATH value is genisler=True on Windows if it contains "%", else keep existing flag.
- `yol yedekler` and `yol geri-al <id> [--uygula]` (shows plan; applies with --uygula).
- `yol web [--port 8797] [--ac]` — `from .web import calistir` inside try/except ImportError -> print "web paneli icin: pip install -e .[web]" exit 2.
- global `--kaynak` option overrides kaynak_sec (e.g. `dosya:/tmp/x.json`).
- Errors from KaynakHatasi/CakismaHatasi/YetkiHatasi/YedekHatasi/UygulamaHatasi -> message on stderr, exit 1. No tracebacks for these.
- Output UTF-8 (`sys.stdout.reconfigure(encoding="utf-8")` guarded with hasattr).

## Files also to write
- yol/__init__.py (`__version__ = "0.1.0"`), yol/__main__.py (`from .cli import main; raise SystemExit(main())`)
- tests (pytest, use tmp_path, monkeypatch YOL_DIR; DosyaKaynak fixtures; NO real winreg except in test_kaynak_windows.py):
  - tests/conftest.py: fixture `yol_dir` (monkeypatch YOL_DIR to tmp), fixture `dosya_kaynak(tmp_path)` writing a JSON with windows=True, ayirici=";", sistem Path REG_EXPAND_SZ and kullanici Path.
  - tests/test_analiz.py: every finding type; %VAR% expansion case-insensitive; anahtar trailing slash/case; effective order sistem then kullanici; PATHEXT resolution with fake dosya_var; store_taklidi; temizlik_onerisi keeps raw text & order and returns None when clean; posix mode with ":".
  - tests/test_gizli.py, tests/test_yedek.py (atomic write, prune to 30, unique ids, invalid id rejected incl. "../x"), tests/test_degisiklik.py (backup before write; conflict writes nothing; YetkiHatasi; failure mid-way restores via a fake kaynak whose 2nd yaz raises; genisler type preserved; gunluk contains no secret value — assert a secret value string never appears in gunluk.jsonl; geri_al_plani roundtrip).
  - tests/test_cli.py (via main([...]) with --kaynak dosya:..., capsys): denetle exit codes, temizle dry-run changes nothing, temizle --uygula writes and creates backup, ekle/kaldir, geri-al roundtrip, web without flask -> exit 2 (monkeypatch builtins import of yol.web to raise ImportError if Flask is installed).
  - tests/test_kaynak_windows.py: `pytestmark = pytest.mark.skipif(os.name != "nt", ...)`; real HKCU: write/read/delete a variable named f"YOL_TEST_{uuid4().hex[:8]}" with REG_SZ and REG_EXPAND_SZ (value "%USERPROFILE%\\x" must read back unexpanded and genisler=True); cleanup in finally; never touch PATH.
  - tests/test_kaynak.py: DosyaKaynak roundtrip + atomic, SurecKaynak read-only raises KaynakHatasi, kaynak_sec parsing.
