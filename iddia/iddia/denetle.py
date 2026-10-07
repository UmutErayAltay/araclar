"""Denetim: README'deki somut iddialari kodun gercegiyle karsilastirir.

Dort tur denetlenir (hepsi regex + sayim; LLM YOK):
 1. `test-sayisi` : "N test(s)" iddiasi vs test dosyalarindaki gercek test sayisi.
 2. `dosya-yolu`  : `kod bicimli` yol iddiasi vs repoda o yolun var olmasi.
 3. `cli-bayragi` : `--bayrak` iddiasi vs kaynak dosyalarda o dizinin gecmesi.
 4. `sayi-kaynak` : "N komut" vs argparse `add_parser(` sayisi.

Guvenlik (baglayici kural): arac SALT OKUNURDUR; hicbir islev dosya yazmaz.
Yalniz bulgu metni uretilir, hicbir dosya degismez.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from .kesif import MAKS_BOYUT, SKIP_DIRS, okunabilir

#: Iddia metni kisa tutulur (cikti tablosu okunabilir kalsin).
EN_FAZLA_METIN = 100

#: Sapma kurali: |iddia - gercek| > max(2, 0.1*gercek)  ->  bulgu.
#: Kucuk sayilarda 2'lik taban, "1-2 test farki"ni gurultuden cikarir.
TOLERANS = 0.1
TOLERANS_TABAN = 2

#: README adlari (buyuk/kucuk harf duyarsiz): `README.md`, `readme.rst`...
README_ADLARI = frozenset(
    {"readme", "readme.md", "readme.rst", "readme.txt", "readme.markdown"}
)

#: Kaynak dosya uzantilari (bayrak iddialari icin taranacak kod).
KOD_UZANTILARI = frozenset(
    {
        ".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".sh", ".bash",
        ".rb", ".go", ".rs", ".java", ".kt", ".php", ".pl", ".lua", ".ps1",
    }
)

#: Giris noktasi olan dosya adlari (uzantidan bagimsiz): bir CLI'nin bayraklari
#: cogu zaman burada tanimlanir. "kok" gibi bayraklari bunlar sayesinde gorunur.
GIRIS_ADLARI = frozenset({"__main__.py", "setup.py", "noxfile.py", "gulpfile.js"})

#: Kod DEGIL, kullanici/ekip VERISI olan dizinler. Iki yerde kullanilir:
#:  - README bu dizinlerin ALTINDAYSA denetlenmez (bilgi kasasi notu degil),
#:  - iddia edilen yol bu parcalardan gecIYORSA bulgu uretilmez.
VERI_DIZINLERI = frozenset(
    {
        "vault", "günlük", "gunluk", "daily", "notes", "notlar", "knowledge",
        "concepts", "connections", "journal", "sessions", "memory", "archive",
        "arsiv", "static", "receipts", "threads", "100-inbox", "300-projects",
        "400-archive", "500-knowledge", "600-arsenal", "000-inbox",
    }
)

#: Ortam/editor yapilandirma dizinleri: repo icinde olsa bile "olmali" denmez.
ARAC_DIZINLERI = frozenset(
    {".claude", ".agents", ".obsidian", ".omp", ".vscode", ".idea", ".devcontainer"}
)

#: Yapay uretim dizinleri: varliklari bir sozlesme degil, bir yan etkidir.
URETILEN_DIZINLERI = frozenset(
    {
        "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox",
        ".nox", "htmlcov", "coverage", "node_modules", "dist", "target", "site-packages",
    }
)

#: Yapay uretim DOSYALARI (venv/derleme artigi): repoda bulunmasi normaldir.
URETILEN_ADLARI = frozenset({"pyvenv.cfg", ".coverage", ".ds_store", "thumbs.db"})

#: Bir yol parçası bu adlardan biriyse o token bir liste/enum I'dir ("png/jpg/gif"),
#: yol degil: `png` bir klasor adi olamaz.
_UZANTI_ADLARI = frozenset(
    {
        "py", "js", "ts", "json", "md", "txt", "yml", "yaml", "toml", "sh", "png",
        "jpg", "jpeg", "gif", "webp", "svg", "html", "css", "xml", "csv", "lock",
    }
)

#: Ortam degiskeni: `ANAHTARLIK_DIR/tuz`, `HOME/.config`.
_ORTAM_DEGISKENI = re.compile(r"[A-Z][A-Z0-9]*(_[A-Z0-9]+)+")

#: Sayi/ CIDR/ surum parcasi: `127.0.0.0/8`, `1/2`.
_SAYI_PARCA = re.compile(r"[0-9.]+")

#: Tarih yer tutucusu: `YYYY-MM-DD.md`.
_TARIH_YER_TUTUCU = re.compile(r"[A-Z]{2,}")

#: Test dosyasi kaliplari.
PY_TEST_ADI = re.compile(r"^(test_.*|.*_test)\.py$")
JS_TEST_UZANTILARI = frozenset({".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"})
JS_TEST_SONEKI = (
    ".test.js", ".spec.js", ".test.ts", ".spec.ts", ".test.tsx", ".spec.tsx",
    ".test.jsx", ".spec.jsx", ".test.mjs", ".spec.mjs",
)

#: Bicimlendirilmis kod bloklari (``` ... ```): iclerindeki metin iddia SAYILMAZ.
#: (README ornegi kod blogunda "0 tests" yaziyordu; bunu iddia saymak yanlisti.)
_KOD_BLOKU = re.compile(r"```.*?```|~~~.*?~~~", re.DOTALL)

#: Tirnak icindeki metin: bir ORNEKTIR, iddia degil. ("1200 test" diye ornek veren
#: bir dokuman, kendi test sayisini iddia etmiyordur.)
_ALINTILI = re.compile(r'"[^"\n]*"|“[^”\n]*”|\'[^\'\n]*\'')

#: Satir ici kod: `kod`  (dosya yolu iddialari buradan gelir).
_SATIRICI_KOD = re.compile(r"`([^`\n]+)`")

#: Test sayisi iddiasi: "120 test", "~120 tests", "42 unit tests".
_TEST_SAYISI = re.compile(
    r"(?<![\w.])~?(\d{1,6})\s+(?:unit\s+|integration\s+)?tests?\b", re.IGNORECASE
)

#: CLI bayragi iddiasi: `--kok`, `--uygula`.
_BAYRAK = re.compile(r"(?<![\w-])--[a-z][a-z0-9]*(?:-[a-z0-9]+)*")

#: Sayi-kaynak iddiasi (yalniz "N komut"): argparse alt komut sayimiyla eslesir.
_KOMUT_SAYISI = re.compile(r"(?<![\w.])(\d{1,4})\s+(?:alt\s+)?komut(?:lar)?\b", re.IGNORECASE)

#: Dosya yolu kalibi: harf/rakam/nokta ile baslar, "/" veya uzanti icerir, bosluk YOK.
_YOL_KALIBI = re.compile(r"^[A-Za-z0-9._][A-Za-z0-9._+~-]*(?:/[A-Za-z0-9._+~%-]+)*/?$")

#: Surum/derleme numarasi gibi tek noktali token: ".py" gibi uzanti DEGIL.
_SURUM = re.compile(r"^v?\d+(?:\.\d+)*$")

#: Yolda olabilen ama yol OLMAYAN yer tutucu/glob/URL isaretleri.
#: ("/" haric: "a/b" normal yoldur.)
_YOL_DEGIL_ISARETLER = ("*", "<", ">", "{", "}", "$", "~", "\\", "|", "://", "@")

#: Gitignore'lu olabilecek yollar: repoda olmayabilir, bulgu URETILMEZ.
#: (README'de `.env` yazmak yalnizca kullanim tarifidir, iddia degil.)
_GITIGNORE_ADI = frozenset(
    {
        "env", ".env", ".env.local", ".envrc", ".gitignore", ".gitattributes", ".git",
        ".dockerignore", ".npmignore", ".editorconfig", ".eslintrc", ".prettierrc",
        ".gitkeep", ".gitmodules", ".venv", "venv", "node_modules", "id_rsa", "id_ed25519",
        ".bash_history", "secrets", ".secrets", "credentials",
    }
)

#: Bunlar gitignore'lu ya da uretim/derleme artigi: repoda olmasi beklenmez.
_GITIGNORE_UZANTI = (
    ".log", ".tmp", ".swp", ".key", ".pem", ".p12", ".pfx", ".pyc", ".pyo",
    ".sqlite", ".db", ".lock", ".bak", ".orig", ".coverage", ".secret",
)

#: Bagimlilik kilit dosyalari: kurulum ciktisi, "bu dosya repoda olmali" iddiasi
#: YAPILAMAZ (imza degistirir, kullanilmayabilir, dogru olsa bile yazilir).
_BAGIMLILIK_DOSYALARI = frozenset(
    {
        "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
        "uv.lock", "Pipfile.lock", "Cargo.lock", "composer.lock", "go.sum",
        "package.json", "requirements.txt", "requirements-dev.txt",
        "pyproject.toml", "setup.cfg", "Cargo.toml", "Gemfile",
    }
)

#: Markdown gurultusu: gercek bayrak degil.
_BAYRAK_GURULTU = frozenset({"--", "---"})

#: Noktasiz yol iddialarinda gercekten "uzanti" sayilan kalanlar. Bunlarin disinda
#: tek noktali tek parcali token ("v1.2") surum/sozcuk parcasi sayilir.
_BILinen_UZANTI = re.compile(
    r"^[A-Za-z0-9._+-]+\.(py|pyi|js|mjs|cjs|jsx|ts|tsx|json|yml|yaml|toml|ini|cfg|sh|md|rst|txt|go|rb|rs|java|kt|php|pl|lua|c|h|cpp|hpp|css|html|sql|lock|env)$",
    re.IGNORECASE,
)

#: `dosya-yolu` turunun KESINLIK kapisi: bir kod parcasi ancak bir KAYNAK/A YAR
#: uzantisiyla bitiyorsa ya da "/" ile biten bir klasor yoluysa yol iddiasidir.
#: Bunun disindaki her sey (duz dosya adi, model kimligi, MIME turu, git ici yol)
#: README'de gecen ama bu turun konusu olmayan bir metindir.
KAYNAK_UZANTILARI = frozenset(
    {
        ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".sh", ".md",
        ".json", ".yml", ".yaml", ".toml", ".html", ".css", ".sql",
    }
)

#: MIME tipleri: `text/html`, `application/json` bir yol DEGIL, medya tipidir.
_MIME_KALIBI = re.compile(r"^(text|application|image|audio|video|font|model)/")

#: Bu arac tarama kokunden (ornegin `--kok /home/user`) o kokun ALTINDAKI diger
#: repolari gorur. Bir README'nin `corclient/anlat/` gibi yollari BASKA bir
#: repoya aittir: bu repo icinde "yol yok" bulgusu yanlis pozitiftir.
#: Kullanici dizini evrenseldir; taranan her agacin ustu de bu listeye girer.
EV_DIZINLERI = frozenset({"home", "Users", "user", "mnt", "opt", "srv", "var", "tmp"})


class _Repo:
    """Bir repoya ait salt-okunur veri onbellegi (dosya listesi + metinler)."""

    def __init__(self, kok: Path):
        self.kok = kok
        self._dosyalar: list[Path] | None = None
        self._kaynak: list[str] | None = None
        self._goreli_yollar: list[Path] | None = None

    @property
    def ust_dizinler(self) -> set[str]:
        """Repo kokundeki (ve bir alt duzeydeki) dizin adlari.

        `dosya-yolu` kesinlik kuralinda "ust klasor var ama yolun kendisi yok"
        bayatlik belirtisidir; bu dizinler o kontrol icin gereklidir.
        """
        return {p.name.lower() for p in self.kok.iterdir() if p.is_dir()}

    def kardes_adlari(self) -> set[str]:
        """Tarama kokundeki bu repoyla kardes olan diger repo adlari.

        `corclient/anlat/` gibi bir yol, taranan `corclient` reposunda degil
        kardes `anlat` reposunda yer alir: bulgu uretilmemelidir.
        """
        adlar = set(EV_DIZINLERI)
        ust = self.kok.parent
        try:
            kardesler = list(ust.iterdir())
        except OSError:
            return adlar
        for yol in kardesler:
            if yol == self.kok or not yol.is_dir():
                continue
            if (yol / ".git").exists():
                adlar.add(yol.name.lower())
                for ic in yol.iterdir():
                    if ic.is_dir():
                        adlar.add(ic.name.lower())
        return adlar

    @property
    def dosyalar(self) -> list[Path]:
        """Repo govdesindeki okunabilir dosyalar (SKIP_DIRS haric, govdeye girilmez)."""
        if self._dosyalar is None:
            self._dosyalar = [yol for yol in _yuruyerek(self.kok) if yazili_metin(yol)]
        return self._dosyalar

    @property
    def kaynak(self) -> list[str]:
        """Okunabilir kaynak/giris dosyasi metinleri (bayrak iddialari icin)."""
        if self._kaynak is None:
            self._kaynak = [
                icerik
                for yol in self.dosyalar
                if yol.suffix.lower() in KOD_UZANTILARI or yol.name.lower() in GIRIS_ADLARI
                for icerik in (okunabilir(yol),)
                if icerik is not None
            ]
        return self._kaynak

    def yol_var(self, yol: str) -> bool:
        """Iddia edilen yol repoda var mi?

        Iki kabul:
        - kok altinda dogrudan (`kok/yol`), ya da
        - repo icinde bir yol SONECU olarak (paket ic ice kurulmus monorepo'lar:
          `danis/README.md` "`danis/llm.py`" derken gercek dosya
          `danis/danis/llm.py` olabilir).
        `..` ile kok disina cikan iddialar guvenle reddedilir.
        """
        if ".." in yol.split("/"):
            return False
        try:
            if (self.kok / yol).exists():
                return True
        except OSError:
            return False
        son = "/" + yol.rstrip("/")
        return any(p.as_posix().endswith(son) for p in self._goreli()) or any(
            p.name == yol.rstrip("/") for p in self._goreli()
        )

    def _goreli(self) -> list[Path]:
        """Repo kokune gore yollar (onbellekli)."""
        if self._goreli_yollar is None:
            self._goreli_yollar = []
            for yol in _yuruyerek(self.kok):
                try:
                    self._goreli_yollar.append(yol.relative_to(self.kok))
                except ValueError:
                    continue
        return self._goreli_yollar

    def readmeler(self) -> list[tuple[Path, str]]:
        """(yol, metin) ciftleri; okunamayan/ikili README'ler ATLANIR."""
        ciftler = []
        for yol in self.dosyalar:
            if yol.name.lower() in README_ADLARI:
                icerik = okunabilir(yol)
                if icerik is not None:
                    ciftler.append((yol, icerik))
        return ciftler

    def kod_ici_readme(self) -> list[tuple[Path, str]]:
        """Yalniz KODUN icindeki README'ler: veri kasasi notlari denetlenmez."""
        sonuc = []
        for yol, icerik in self.readmeler():
            parcalar = [k.lower() for k in yol.relative_to(self.kok).parts[:-1]]
            if set(parcalar) & VERI_DIZINLERI:
                continue
            sonuc.append((yol, icerik))
        return sonuc


def yazili_metin(yol: Path) -> bool:
    """Dosya kucuk ve duz bir dosya mi? (Icerik kontrolu okunabilir()'da.)"""
    try:
        return yol.is_file() and not yol.is_symlink() and yol.stat().st_size <= MAKS_BOYUT
    except OSError:
        return False


def _yuruyerek(kok: Path):
    """os.walk sarmalayici: govdeye girilmez, baglantilar ve buyuk dosyalar atlanir."""
    for mevcut, dizinler, dosyalar in os.walk(
        kok, topdown=True, followlinks=False, onerror=lambda _e: None
    ):
        ust = Path(mevcut)
        dizinler[:] = sorted(
            d for d in dizinler if d not in SKIP_DIRS and not os.path.islink(ust / d)
        )
        for ad in sorted(dosyalar):
            yol = ust / ad
            if os.path.islink(yol):
                continue  # baglanti dosya: repo disini gosterebilir
            try:
                if yol.stat().st_size > MAKS_BOYUT:
                    continue  # ikili/cok buyuk: atlanir
            except OSError:
                continue
            yield yol


def _satirlar(metin: str, alinti: bool = True) -> list[str]:
    """Satirlari aynen korur (kod blogu bosaltilir ama SATIR SAYISI degismez).

    Blok icerigi yerine satir basina TEK BOS SATIR konur: boylece bulgunun
    `readme:satir` alani, kullaniciya kod blogunun disinda gordugu satiri verir.
    `alinti=True` ise tirnak icindeki ornek metinler de bosaltilir.
    """

    def bosalt(eslesme: re.Match) -> str:
        return "\n" * eslesme.group(0).count("\n")

    satirlar = _KOD_BLOKU.sub(bosalt, metin)
    if alinti:
        satirlar = _ALINTILI.sub(bosalt, satirlar)
    return satirlar.splitlines()


def _kisalt(metin: str) -> str:
    """Bulgu metnini EN_FAZLA_METIN karaktere kirp (tek satir)."""
    tek = " ".join(metin.split())
    return tek if len(tek) <= EN_FAZLA_METIN else tek[: EN_FAZLA_METIN - 1] + "…"


def _bulgu(repo: Path, readme: Path, satir: int, tur: str, iddia: str, gercek: str) -> dict:
    return {
        "repo": str(repo),
        "readme": f"{readme.relative_to(repo).as_posix()}:{satir}",
        "tur": tur,
        "iddia": _kisalt(iddia),
        "gercek": _kisalt(gercek),
    }


# --------------------------------------------------------------------------
# Gercek sayimlar
# --------------------------------------------------------------------------


def test_sayisi(repo: Path, kapsam: Path | None = None) -> int | None:
    """Verilen kapsamdaki gercek test sayisi; test dosyasi YOKSA None.

    python: `def test_` sayisi. js/ts: `it(` / `test(` cagrisi sayisi.
    """
    python_adet = js_adet = 0
    kok = Path(kapsam) if kapsam is not None else Path(repo)
    for yol in _Repo(repo).dosyalar:
        try:
            goreli = yol.relative_to(kok)
        except ValueError:
            continue  # kapsam disi: komsu aracin testi sayilmaz
        icerik = okunabilir(yol)
        if icerik is None:
            continue
        ad, uzanti = yol.name.lower(), yol.suffix.lower()
        parcalar = [k.lower() for k in goreli.parts[:-1]]
        if uzanti == ".py" and PY_TEST_ADI.match(ad):
            python_adet += len(re.findall(r"^\s*def\s+test_", icerik, re.MULTILINE))
        elif uzanti in JS_TEST_UZANTILARI and (
            ad.endswith(JS_TEST_SONEKI)
            or bool(set(parcalar) & {"test", "tests", "__tests__", "spec"})
        ):
            js_adet += len(re.findall(r"\b(?:it|test)\s*\(", icerik))
    toplam = python_adet + js_adet
    return toplam or None


def alt_komut_sayisi(repo: Path) -> int | None:
    """argparse `add_parser(` cagrisi sayisi; yoksa None (bulgu uretilmez)."""
    toplam = 0
    for metin in _Repo(repo).kaynak:
        toplam += metin.count("add_parser(")
    return toplam or None


def bayrak_var(repo: Path, bayrak: str) -> bool:
    """Bayrak adi herhangi bir kaynak dosyada geciliyor mu? (kaynak = KOD_UZANTILARI)"""
    return any(bayrak in metin for metin in _Repo(repo).kaynak)


def _kapsam(repo: Path, readme: Path) -> Path:
    """README'nin test iddialari icin sayilacagi kapsam: en yakin paket dizini.

    `harita/README.md` -> `harita/` (komsu araclarin testleri sayilmaz).
    `README.md` (kokte) -> repo kokunun kendisi (tum testler sayilir).
    """
    try:
        parcalar = readme.relative_to(repo).parts[:-1]
    except ValueError:
        return repo
    return repo.joinpath(*parcalar) if parcalar else repo


# --------------------------------------------------------------------------
# Tur 1: test sayisi iddiasi
# --------------------------------------------------------------------------


def test_sayisi_bulgu(repo: Path, readme: Path, metin: str) -> list[dict]:
    """README icindeki "N test" iddialarini test dosyalarinin gercek sayisiyla karsilastirir.

    Monorepo'da (bir koke birden fazla araç konmus) testler arac basina ayrilir:
    `harita/README.md` "10 test" dediginde `harita/tests/` sayilir, komsu aracin
    testleri DEGIL. Aksi halde her arac, komsularinin testlerini de iceren toplam
    bir sayiya karsilik gelirdi ve HEPSI yanlis bulgu uretilirdi.
    """
    onbellek = _Repo(repo)
    # README'nin ait oldugu kapsam: en yakin paket dizini.
    kapsam = _kapsam(repo, readme)
    gercek = test_sayisi(repo, kapsam)
    if not gercek:
        return []  # bu kapsamda test dosyasi yok: bulgu URETILMEZ (yanlis pozitif)
    bulgular = []
    for no, satir in enumerate(_satirlar(metin), start=1):
        for eslesme in _TEST_SAYISI.finditer(satir):
            iddia = int(eslesme.group(1))
            if abs(iddia - gercek) <= max(TOLERANS_TABAN, TOLERANS * gercek):
                continue  # tolerans icinde: sapma yok
            bulgular.append(
                _bulgu(repo, readme, no, "test-sayisi", eslesme.group(0).strip(), f"{gercek} test")
            )
    return bulgular


# --------------------------------------------------------------------------
# Tur 2: dosya/klasor yolu iddiasi
# --------------------------------------------------------------------------


def _yol_adayi(token: str, repo: _Repo) -> str | None:
    """Bu kod parcasi bir yol iddiasi mi? Degilse None."""
    token = token.strip()
    if not token or " " in token or token.startswith("-"):
        return None  # bosluklu = komut satiri; tireli = bayrak/anahtar
    if any(isaret in token for isaret in _YOL_DEGIL_ISARETLER):
        return None  # URL, glob (*), yer tutucu (<...>, {...}), shell degiskeni
    if not _YOL_KALIBI.match(token):
        return None

    ham = token.rstrip("/").split("/")
    parcalar = [p.lower() for p in ham]
    if ".." in parcalar:
        return None  # ust dizin gezintisi: yol iddiasi sayilmaz
    if parcalar[-1] in _BAGIMLILIK_DOSYALARI:
        return None  # bagimlilik kilidi/manifesti: iddia sayilamaz

    # Yer tutucu/enum parcalari: "YYYY-MM-DD.md", "png/jpg/gif", "Kurallar/Core/Soul".
    # Yer tutucu kontrolu KABUK HALIYLE yapilir: "YYYY" buyuk harfle yazilir.
    if any(_TARIH_YER_TUTUCU.search(p.rsplit(".", 1)[0]) for p in ham):
        return None
    if any(p in _UZANTI_ADLARI for p in parcalar[:-1]):
        return None  # "png/jpg/jpeg" bir dosya turu listesi, yol degil
    if any(_SAYI_PARCA.fullmatch(p) for p in parcalar):
        return None  # "127.0.0.0/8" bir CIDR/blog, yol degil
    # Ortam degiskeni KABUK HALIYLE olmak zorunda: token buyuk harfle basliyor mu?
    if _ORTAM_DEGISKENI.match(ham[0]):
        return None  # "ANAHTARLIK_DIR/tuz": ortam degiskeninden kurulan yol

    if set(parcalar) & _GITIGNORE_ADI:
        return None  # ".env", "node_modules/x": gitignore'lu olabilir
    if set(parcalar) & (VERI_DIZINLERI | ARAC_DIZINLERI | URETILEN_DIZINLERI):
        return None  # "daily/", ".claude/", "__pycache__": veri/arac/uretim dizini
    if parcalar[-1] in URETILEN_ADLARI:
        return None  # "pyvenv.cfg": uretim artigi, repoda olmasi beklenmez
    if parcalar[-1].endswith(_GITIGNORE_UZANTI):
        return None  # uretim/derleme artigi

    if not _kaynak_uzantili_yol(token, parcalar, repo):
        return None
    return token


def _kaynak_uzantili_yol(token: str, parcalar: list[str], repo: _Repo) -> bool:
    """KESINLIK KAPISI: bu yol gercekten dosya/klasor yolu iddiasi mi?

    Uc katmanli eleme (yanlis pozitifi %95 azaltir, gercek iddialari gecirir):

      1. Sekil: yolun EN AZ BIR "/" icermesi gerekir. "`settings.json`",
         "`Core.md`", "`beyin.py`" gibi duz dosya adlari baska konumda da
         dogru olabilir; hangi dosyadan bahsedildigi BELLI DEGILDIR.

      2. Tur: ya bir kaynak/ayar uzantisıyla bitmeli (`.py .ts .md ...`)
         ya da "/" ile biten bir klasor yolu olmali. Boylece MIME tipleri
         (`text/html`), model kimlikleri (`stealth/space-bunny-alpha`) ve
         durum adlari (`failed/error`) elenir.

      3. Baglam: iddia edilen yolun ust klasoru repoda VARSA bu bir BAYAT/
         TASINMIS yoldur ve bulgu uretilir (asil istenen sinyal). Ust
         klasor yoksa ancak yol bir kaynak uzantisıyla bitiyorsa yine
         denetlenir; boylece tek segmentli alt yollar (`beyin/x.py`) ve
         kardes repoya ait yollar ele alinir.
    """
    if "/" not in token:
        return False  # duz dosya adi: konumu bilinmeden dogrulanamaz
    if token.startswith("/"):
        return False  # mutlak yol: bu repo hakkinda iddia degil
    if _MIME_KALIBI.match(token):
        return False  # "text/html": medya tipi
    if any(isaret in token for isaret in ("..", "~", "$", "*", "<", "{")):
        return False  # ust dizin/glob/yer tutucu/shell degiskeni

    klasor = token.endswith("/")
    uzanti = Path(token.rstrip("/")).suffix.lower()
    kaynak_uzantisi = uzanti in KAYNAK_UZANTILARI
    if not (klasor or kaynak_uzantisi):
        return False  # ne klasor ne kaynak dosyasi: yol iddiasi degil

    ust = parcalar[0]
    if ust in repo.kardes_adlari():
        return False  # "corclient/anlat/": kardes repo, bu repo degil
    if ust in repo.ust_dizinler:
        return True  # ust klasor var, yol yok: BAYAT yol (istenen sinyal)
    return kaynak_uzantisi  # ust klasor yoksa yalniz kaynak dosyasi denetlenir


def dosya_yolu_bulgu(repo: Path, readme: Path, metin: str) -> list[dict]:
    """Tirnak icindeki yollar BURADA sayilir: "`app/main.py`" kalibi iddianin kendisidir."""
    onbellek = _Repo(repo)
    bulgular = []
    for no, satir in enumerate(_satirlar(metin, alinti=False), start=1):
        for eslesme in _SATIRICI_KOD.finditer(satir):
            yol = _yol_adayi(eslesme.group(1), onbellek)
            if yol is None or onbellek.yol_var(yol):
                continue
            bulgular.append(
                _bulgu(repo, readme, no, "dosya-yolu", eslesme.group(1).strip(), "yol yok")
            )
    return bulgular


# --------------------------------------------------------------------------
# Tur 3: CLI bayragi iddiasi
# --------------------------------------------------------------------------


def bayrak_bulgu(repo: Path, readme: Path, metin: str) -> list[dict]:
    bulgular = []
    for no, satir in enumerate(_satirlar(metin), start=1):
        for eslesme in _BAYRAK.finditer(satir):
            bayrak = eslesme.group(0)
            if bayrak in _BAYRAK_GURULTU or bayrak_var(repo, bayrak):
                continue  # markdown gurultusu veya kaynakta gecisiyor: dogrulanmis
            bulgular.append(_bulgu(repo, readme, no, "cli-bayragi", bayrak, "kaynakta yok"))
    return bulgular


# --------------------------------------------------------------------------
# Tur 4: sayi-kaynak iddiasi (yalniz "N komut" <-> argparse alt komut)
# --------------------------------------------------------------------------


def sayi_kaynak_bulgu(repo: Path, readme: Path, metin: str) -> list[dict]:
    gercek = alt_komut_sayisi(repo)
    if not gercek:
        return []  # argparse sayilamiyor: bu turde bulgu URETILMEZ
    bulgular = []
    for no, satir in enumerate(_satirlar(metin), start=1):
        for eslesme in _KOMUT_SAYISI.finditer(satir):
            iddia = int(eslesme.group(1))
            if abs(iddia - gercek) <= max(TOLERANS_TABAN, TOLERANS * gercek):
                continue
            bulgular.append(
                _bulgu(
                    repo, readme, no, "sayi-kaynak", eslesme.group(0).strip(), f"{gercek} alt komut"
                )
            )
    return bulgular


# --------------------------------------------------------------------------
# Giris noktasi
# --------------------------------------------------------------------------

#: (tur, islev) sirasi: bulgular bu sirayla uretilir.
TURLER = (
    ("test-sayisi", test_sayisi_bulgu),
    ("dosya-yolu", dosya_yolu_bulgu),
    ("cli-bayragi", bayrak_bulgu),
    ("sayi-kaynak", sayi_kaynak_bulgu),
)


def denetle(repolar: list[Path]) -> list[dict]:
    """Tum repolarda dort turun bulgularini dondurur (dosya sistemi DEGISMEZ)."""
    bulgular: list[dict] = []
    for repo in repolar:
        repo = Path(repo)
        for readme, metin in _Repo(repo).kod_ici_readme():
            for _tur, islev in TURLER:
                bulgular.extend(islev(repo, readme, metin))
    # Ayni README/satir/tur/iddia: TEKILLESTIR (raporda tekrar satir olmaz).
    benzersiz: dict[tuple, dict] = {}
    for b in bulgular:
        benzersiz.setdefault((b["repo"], b["readme"], b["tur"], b["iddia"]), b)
    return sorted(benzersiz.values(), key=lambda b: (b["repo"], b["readme"], b["tur"]))