"""README bayatlığı: "kod ilerledi ama README güncellenmedi mi?" — SAYIYLA.

TANIMLAR (bağlayıcı; bu docstring, eşik sabitleri ve README aynıdır)
====================================================================

README
    Kök dizindeki `README.md|README.rst|README.txt|README` — bu sırayla İLK
    bulunan. Hiçbiri yoksa `seviye = "yok"`.

readme_commit
    README'yi en son değiştiren commit (`git log -1 --format=%H -- <readme>`).
    Hiç commit'lenmemişse NULL ve seviye `yok`.

DAVRANIŞ COMMIT'İ
    `readme_commit..HEAD` aralığında, merge commit'ler SAYILMAZ ve:
      * mesajı `docs|chore|style|test|ci` (+ isteğe bağlı `(kapsam)`) ile
        başlayanlar sayılmaz; VE
      * en az bir dosyası KOD dosyasıdır.

    KOD dosyası: uzantı `.py .js .jsx .ts .tsx .go .rs .java .kt .c .cc
    .cpp .h .hpp .cs .rb .php .sh .sql .html .css .vue .svelte` VE yolu
    `tests/ test/ docs/ examples/ .github/` altında DEĞİL VE dosya adı
    README/CHANGELOG/LICENSE değil.

    Commit mesajında anahtar kelime ZORUNLU DEĞİLDİR: gerçek repolarda
    mesajlar Türkçe ve "Dalga C: …" biçimindedir; `fix|feat` beklenseydi
    hepsi kaçırılırdı. Bu yüzden yalnızca YANLIŞ POZİTİF üreten önekler
    elenir (`HARICI_ONEKLER`).

screenshot_age_days
    README'deki YEREL görsel referansları (`![..](yol)` ve `<img src="yol">`;
    `http(s)` ve `data:` hariç; yol repo içinde çözülür, `..` ile repo DIŞINA
    çıkan yol REDDEDİLİR) içinden VAR OLAN izlenen dosyaların en YENİsinin
    son commit tarihi ile HEAD'deki son DAVRANIŞ commit'inin tarihi arasındaki
    gün farkıdır (negatifse 0). README yerel görsel içermiyorsa NULL.
    Referans verilen ama depoda OLMAYAN görsel sayısı `eksik_gorsel`'dir.

skor = davranis_commit + (screenshot_age_days // 10
                           eger screenshot_age_days is not None
                           ve davranis_commit >= 1 ise, aksi halde 0)

SEVİYE EŞİKLERİ (sabit; testle kilitlenir)
    taze    : skor < 3
    eskiyor : 3 <= skor < 8
    bayat   : skor >= 8
    yok     : README yok (veya commit'lenmemiş)

Tarama en fazla son `TARAMA_LIMIT` (2000) commit'e bakar. Sınır aşılırsa
`neden = "sinir"` yazılır ve seviye `"sinir"` olur (skor `SKOR_ALT_SINIR`):
daha fazla davranış commit'i olabilirdi — tahmin değil, ALT SINIR işareti.

Hata durumu: boş repo, HEAD yok, kabuk klon (iç `.git` dizini olmayan),
git okuma hatası → istisna FIRLATILMAZ; `seviye = None` ve `neden` doludur
(`tarandi = False`).

Salt-okunurluk: `scan.ALLOWED_GIT_SUBCOMMANDS` listesine YENİ alt komut
EKLENMEZ (yalnızca `log`; görsel doğrulaması için `ls-files`, zaten izinli).
Repolara hiçbir şey yazılmaz.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, NamedTuple

from .scan import GitError, run_git

# --------------------------------------------------------------------------
# Sabitler (EŞİKLER) — docstring ve README ile senkron
# --------------------------------------------------------------------------

#: Kökte aranan README adları, BU SIRAYLA. İlk bulunan kazanır.
README_ADLARI = ("README.md", "README.rst", "README.txt", "README")

#: Seviye eşikleri.
TAZE_UST_SINIR = 3
ESKIYOR_UST_SINIR = 8

SEVIYELER = ("taze", "eskiyor", "bayat", "yok")

#: Sınır aşıldığında yazılan seviye (bilinen değil).
SEVIYE_SINIR = "sinir"

#: Görsel yaşının skora katkısı: her tam 10 gün için 1 puan.
GORSEL_BOLME = 10

#: Tarama penceresi: en fazla bu kadar commit'e bakılır.
TARAMA_LIMIT = 2000

#: Sınır aşıldığında göstergelenen skor ALT SINIRI.
SKOR_ALT_SINIR = ESKIYOR_UST_SINIR

#: KOD dosyası uzantıları. Bir davranış commit'i en az bir BUNLARDAN birini
#: içermelidir.
KOD_UZANTILARI = frozenset(
    {
        ".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java", ".kt",
        ".c", ".cc", ".cpp", ".h", ".hpp", ".cs", ".rb", ".php", ".sh",
        ".sql", ".html", ".css", ".vue", ".svelte",
    }
)

#: KOD sayılmayan dizinler: yol bu segmentlerden birini İÇERİYORSA kod değil.
KOD_DISI_DIZINLER = frozenset({"tests", "test", "docs", "examples", ".github"})

#: Kod dosyası olsa bile davranış sayılmayan dosya adları (stems, küçük harf).
KOD_DISI_ADLAR = frozenset({"readme", "changelog", "license"})

#: Mesajı bu kelimelerle başlayan commit'ler davranış DEĞİLDİR.
#: `docs:`, `docs (api):`, `DOCS(web):` — hepsi eşleşir.
HARICI_ONEKLER = ("docs", "chore", "style", "test", "ci")
HARICI_ONEK_DESENI = re.compile(r"^(?:%s)\b" % "|".join(HARICI_ONEKLER), re.IGNORECASE)

#: Markdown görsel: `![alt](yol "başlık")`.
_MD_GORSEL = re.compile(r"!\[[^\]]*\]\(\s*<?([^)>\s]+)>?(?:\s+[\"'][^)\"']*[\"'])?\s*\)")
#: HTML görsel: `<img src="yol">` (tırnaklı).
_HTML_GORSEL = re.compile(r"<img\b[^>]*?\bsrc\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE)

#: `..` çözümü için tekrar tavanı (pratik güvenlik sınırı).
YOL_TAVAN = 8

#: `neden` değerleri (boşsa `None`).
NEDEN_SINIR = "sinir"
NEDEN_BOS_REPO = "bos-repo"
NEDEN_KABUK_KLON = "kabuk-klon"
NEDEN_README_YOK = "readme-yok"
NEDEN_README_COMMITLENMEMIS = "readme-commitlenmemis"
NEDEN_GIT_HATASI = "git-hatasi"

#: `git log` ayraçları. Commit mesajında geçebilecek karakterlerden (`|`, `:`)
#: kaçınmak için AYRI başlangıç/kapanış kullanılır (leaks.GECMIS_AYRAC ile
#: aynı disiplin): ayraç satır başında benzersizdir.
AYRAC = "@@ATLAS-RM:"
AYRAC_SON = ":RM-ATLAS@@"


# --------------------------------------------------------------------------
# Yardımcılar
# --------------------------------------------------------------------------


def seviye_hesapla(skor: int) -> str:
    """Skor → seviye. Eşikler `TAZE_UST_SINIR` / `ESKIYOR_UST_SINIR`."""
    if skor < TAZE_UST_SINIR:
        return "taze"
    if skor < ESKIYOR_UST_SINIR:
        return "eskiyor"
    return "bayat"


def kod_dosyasi_mi(dosya: str) -> bool:
    """Verilen repo-relative yol bir KOD dosyası mı?

    Üç koşul birden gerekir: KOD uzantısı, kod dışı dizin DEĞİL, ad
    README/CHANGELOG/LICENSE DEĞİL. Yol `/` ile normalize edilir (Windows
    `\\` ayracı); `PurePosixPath` kullanılır çünkü git yolları daima
    `/` ile yazılır.
    """
    temiz = (dosya or "").replace(chr(92), "/").strip()
    if not temiz:
        return False
    parcalar = [p for p in PurePosixPath(temiz).parts if p not in (".", "/")]
    if not parcalar:
        return False
    if any(seg in KOD_DISI_DIZINLER for seg in parcalar[:-1]):
        return False
    son = parcalar[-1]
    if son.lower().split(".", 1)[0] in KOD_DISI_ADLAR:
        return False
    return PurePosixPath(son).suffix.lower() in KOD_UZANTILARI


def harici_onek_mi(mesaj: str) -> bool:
    """Commit mesajı `docs|chore|style|test|ci` ile mi başlıyor?"""
    return bool(HARICI_ONEK_DESENI.match((mesaj or "").lstrip()))


def gun_farki(baslangic: datetime, bitis: datetime) -> int:
    """İki tarih arası TAM gün farkı (bitiş daha eskiyse 0)."""
    fark = (bitis - baslangic).days
    return fark if fark > 0 else 0


def _coz(iso: str | None) -> datetime | None:
    """ISO8601 metnini `datetime`'a çevirir (UTC); bozuk/boşsa `None`."""
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _iso(dt: datetime | None) -> str | None:
    return None if dt is None else dt.astimezone(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------
# Görsel referansları
# --------------------------------------------------------------------------


def gorsel_yollari(metin: str) -> list[str]:
    """README metnindeki YEREL görsel referanslarını çıkarır (sıra korunur).

    `http(s)://`, `//protokol-relative` ve `data:` referansları DIŞ kaynaktır
    ve YOK sayılır. Tekrarlar bir kez yazılır.
    """
    yerel: list[str] = []
    for ham in (*_MD_GORSEL.findall(metin or ""), *_HTML_GORSEL.findall(metin or "")):
        yol = ham.strip()
        if not yol or yol.startswith("#") or yol.startswith("<"):
            continue
        if yol.lower().startswith(("http://", "https://", "data:", "//")):
            continue
        if yol not in yerel:
            yerel.append(yol)
    return yerel


def repo_icinde_mi(repo: Path, yol: str) -> bool:
    """Görsel yolu repo İÇİNDE mi? (`..` ile dışarı çıkan yol REDDEDİLİR.)

    `..` çözümü `YOL_TAVAN` kez denenir; sınırdan sonra da hâlâ dışarıdaysa
    reddedilir. Sembolik linkler `Path.resolve()` ile izlenmez; çözümlenmiş
    yolun repo kökü altında olması yeterlidir.
    """
    try:
        aday = (repo / yol).resolve()
        kok = repo.resolve()
    except (OSError, RuntimeError, ValueError):
        return False
    deneme = 0
    while deneme <= YOL_TAVAN:
        if aday == kok or kok in aday.parents:
            return True
        if aday.parent == aday:
            return False
        aday = aday.parent
        deneme += 1
    return False


# --------------------------------------------------------------------------
# git okumaları (yalnızca `log` + `ls-files`; ikisi de izinli)
# --------------------------------------------------------------------------


def readme_bul(kok: Path) -> Path | None:
    """Kökteki README'yi bulur (İLK bulunan); yoksa `None`."""
    for ad in README_ADLARI:
        yol = Path(kok) / ad
        try:
            if yol.is_file():
                return yol
        except OSError:  # pragma: no cover — erişilemeyen ad
            continue
    return None


def _readme_dosya_adlari(repo: Path) -> tuple[list[str], Path | None]:
    """(izlenen README adları, diskte bulunan ilk README)."""
    try:
        from .leaks import ls_files

        izlenen = [p.replace(chr(92), "/") for p in ls_files(repo)]
    except GitError:
        izlenen = []
    adaylar = [d for d in izlenen if d in README_ADLARI]
    return adaylar, readme_bul(repo)


def _son_tarih(repo: Path, yol: str) -> datetime | None:
    """`yol` dosyasını en son değiştiren commit'in `cI` tarihi (yoksa `None`)."""
    try:
        ham = run_git(repo, ["log", "-1", "--format=%cI", "--", yol])
    except GitError:
        return None
    return _coz(ham.strip() or None)


def _readme_commit(repo: Path) -> tuple[str | None, str | None]:
    """(readme_commit hash, commit tarihi ISO). Commit'lenmemişse `(None, None)`."""
    izlenen, diskteki = _readme_dosya_adlari(repo)
    for ad in izlenen:
        try:
            ham = run_git(repo, ["log", "-1", "--format=%H", "--", ad])
        except GitError:
            continue
        commit = ham.strip() or None
        if commit:
            return commit, _iso(_son_tarih(repo, ad))
    # İzlenen README yok: diskteki dosyaya bak (git dizini bozuk olabilir).
    if diskteki is not None:
        return None, None
    return None, None


def _log_bicim() -> str:
    """`git log --format=…`: `<AYRAC>hash|tarih<AYRAC_SON>%s` + dosyalar.

    KAPANIŞ ayracı mesajdan ÖNCE gelir: öylece commit mesajı, ayraçtan
    etkilenmez (bir mesajın içinde `|` ya da `:@@` bulunabilir) ve dosya
    adları mesajın ilk satırından sonra başlar. Aradaki `|` yalnız HASH ve
    TARİH ayırır (ikisi de `|` içermez) → `split("|", 2)` güvenlidir.
    """
    return f"--format={AYRAC}%H|%cI|{AYRAC_SON}%s"


def _log_kayitlari(repo: Path, baslangic: str | None, limit: int) -> tuple[list[dict[str, Any]], bool]:
    """(kayıtlar, sınır aşıldı mı). `baslangic` = `readme_commit`.

    Kayıt ayracı `AYRAC` ile AYRILIR (kapanış ayracı mesajin icinde kalir).
    """
    args = ["log", "--no-merges", "--name-only", "-n", str(limit), _log_bicim()]
    if baslangic:
        args.append(f"{baslangic}..HEAD")
    try:
        ham = run_git(repo, args)
    except GitError:
        return [], False

    kayitlar: list[dict[str, Any]] = []
    # Bloklar `AYRAC` ile AYRILIR; her blok icinde `AYRAC_SON` kapanisi vardir.
    # ONCE kapanis ayrilir, SONRA alanlar bolunur — tersi yapilirsa mesaj kaybolur.
    for govde in ham.split(AYRAC):
        if not govde or "|" not in govde:
            continue
        ust, _ayir, mesaj_ve_dosyalar = govde.partition(AYRAC_SON)
        parcalar = ust.split("|", 2)
        if len(parcalar) != 3:
            continue
        commit, tarih, mesaj = parcalar
        # Mesaj satir sonunda biter; ardindan bos satir + dosya adlari gelir.
        satir_listesi = mesaj_ve_dosyalar.split("\n")
        mesaj = satir_listesi[0].rstrip() if satir_listesi else ""
        dosyalar = [s.strip().replace(chr(92), "/") for s in satir_listesi[1:] if s.strip()]
        kayitlar.append(
            {
                "commit": commit,
                "tarih": _coz(tarih),
                "mesaj": mesaj,
                "dosyalar": dosyalar,
            }
        )
    return kayitlar, len(kayitlar) >= limit


def davranis_commitleri(
    repo: Path, *, baslangic: str | None, limit: int = TARAMA_LIMIT
) -> tuple[list[dict[str, Any]], bool]:
    """`baslangic..HEAD` aralığındaki DAVRANIŞ commit'leri + sınır bayrağı.

    Merge commit'ler `--no-merges` ile dışlanır. Mesaj öneki elenenler
    (`docs|chore|style|test|ci`) ve en az bir KOD dosyası içermeyenler
    DAVRANIS SAYILMAZ. `limit` aşılırsa ikinci değer `True` döner.
    """
    kayitlar, sinir = _log_kayitlari(repo, baslangic, limit)
    davranis = [
        k for k in kayitlar
        if any(kod_dosyasi_mi(d) for d in k["dosyalar"]) and not harici_onek_mi(k["mesaj"])
    ]
    return davranis, sinir


def gorsel_yasi(
    repo: Path, readme: Path, *, davranis_tarihi: datetime | None
) -> tuple[int | None, int]:
    """(görsel yaşı gün, eksik görsel sayısı).

    README'de yerel görsel yoksa `(None, 0)`. Var olan İZLENEN görsellerin
    en YENİ commit tarihi ile son davranış commit'inin tarihi farkıdır.
    Davranış commit'i hiç yoksa HEAD tarihi kullanılır (bu durumda ek katkı
    tanım gereği zaten 0'dır).
    """
    try:
        metin = readme.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None, 0
    referanslar = gorsel_yollari(metin)
    if not referanslar:
        return None, 0

    try:
        from .leaks import ls_files

        izlenen = {p.replace(chr(92), "/") for p in ls_files(repo)}
    except GitError:
        izlenen = set()

    var_olan: list[str] = []
    eksik = 0
    for yol in referanslar:
        if not repo_icinde_mi(repo, yol):
            continue  # `..` kaçışı / dış kaynak: ne izlenir ne eksik
        goreli = yol.replace(chr(92), "/").lstrip("/")
        if goreli in izlenen and (repo / goreli).is_file():
            var_olan.append(goreli)
        else:
            eksik += 1
    if not var_olan:
        return None, eksik

    tarih = davranis_tarihi
    if tarih is None:
        try:
            ham = run_git(repo, ["log", "-1", "--format=%cI"])
        except GitError:
            return None, eksik
        tarih = _coz(ham.strip() or None)

    en_yeni: datetime | None = None
    for dosya in var_olan:
        dt = _son_tarih(repo, dosya)
        if dt is not None and (en_yeni is None or dt > en_yeni):
            en_yeni = dt
    if en_yeni is None or tarih is None:
        return None, eksik
    return gun_farki(en_yeni, tarih), eksik


# --------------------------------------------------------------------------
# Tarama sonucu
# --------------------------------------------------------------------------


class ReadmeDurumu(NamedTuple):
    """Bir repo'nun README bayatlığı özeti (DB satırı + tablo satırı)."""

    repo: str
    readme_yolu: str | None
    readme_commit: str | None
    readme_commit_tarihi: str | None
    davranis_commit: int
    screenshot_age_days: int | None
    skor: int
    seviye: str | None
    eksik_gorsel: int
    neden: str | None
    tarandi: bool

    def db_satiri(self) -> dict[str, Any]:
        return dict(self._asdict())


def tara_repo(repo: Path, *, limit: int = TARAMA_LIMIT) -> ReadmeDurumu:
    """Tek repo'nun README bayatlığını hesaplar. Hata FIRLATMAZ.

    Boş repo / HEAD yok / kabuk klon / git okuma hatası → `seviye = None`
    ve `neden` dolu (`tarandi = False`). Repo YALNIZCA OKUNUR.
    `limit` tarama penceresidir (testte küçültülebilir).
    """
    repo = Path(repo)
    temel = ReadmeDurumu(
        repo=str(repo), readme_yolu=None, readme_commit=None,
        readme_commit_tarihi=None, davranis_commit=0, screenshot_age_days=None,
        skor=0, seviye=None, eksik_gorsel=0, neden=None, tarandi=False,
    )
    if not (repo / ".git").exists():
        return temel._replace(neden=NEDEN_KABUK_KLON)

    from .scan import _has_commits

    try:
        if not _has_commits(repo):
            return temel._replace(neden=NEDEN_BOS_REPO)
    except GitError:
        return temel._replace(neden=NEDEN_GIT_HATASI)

    readme = readme_bul(repo)
    if readme is None:
        return temel._replace(neden=NEDEN_README_YOK, seviye="yok", tarandi=True)
    readme_yolu = readme.relative_to(repo).as_posix()

    # Önce İZLENEN bir README aranır; `ls-files` sonucu boş çıkarsa (dosya
    # `git add` EDILMEMIS), diskteki README "commit'lenmemis" sayilir. Aksi
    # halde `git log -- <yol>` çıktısı boş olur ve commit YANLISLIKLA "ilk
    # commit"e giderdi — yani "son commit'ten beri 0 kod commit'i" gibi görünür.
    commit, commit_tarihi = _readme_commit(repo)
    if commit is None:
        return temel._replace(
            readme_yolu=readme_yolu,
            neden=NEDEN_README_COMMITLENMEMIS,
            seviye="yok",
            tarandi=True,
        )

    davranis, sinir = davranis_commitleri(repo, baslangic=commit, limit=limit)
    tarihler = [k["tarih"] for k in davranis if k["tarih"] is not None]
    son_davranis = max(tarihler) if tarihler else None

    yas, eksik = gorsel_yasi(repo, readme, davranis_tarihi=son_davranis)
    adet = len(davranis)
    ek = (yas // GORSEL_BOLME) if (yas is not None and adet >= 1) else 0
    skor = adet + ek
    if sinir and skor < SKOR_ALT_SINIR:
        skor = SKOR_ALT_SINIR

    return ReadmeDurumu(
        repo=str(repo),
        readme_yolu=readme_yolu,
        readme_commit=commit,
        readme_commit_tarihi=commit_tarihi,
        davranis_commit=adet,
        screenshot_age_days=yas,
        skor=skor,
        seviye=SEVIYE_SINIR if sinir else seviye_hesapla(skor),
        eksik_gorsel=eksik,
        neden=NEDEN_SINIR if sinir else None,
        tarandi=True,
    )


def tara_roots(
    roots: Iterable[Path], *, depth: int = 3
) -> tuple[dict[str, ReadmeDurumu], list[tuple[Path, str]]]:
    """(repo yolu → durum, hatalar). Mevcut `scan` keşfini YENİDEN KULLANIR."""
    from .scan import find_repo_paths

    sonuc: dict[str, ReadmeDurumu] = {}
    hatalar: list[tuple[Path, str]] = []
    for repo in find_repo_paths(roots, depth=depth):
        try:
            durum = tara_repo(repo)
        except Exception as exc:  # beklenmeyen: taramayı çökertme
            hatalar.append((repo, type(exc).__name__))
            continue
        sonuc[durum.repo] = durum
    return sonuc, hatalar


def sirala(durumlar: Iterable[ReadmeDurumu]) -> list[ReadmeDurumu]:
    """Skora AZALAN sıralama; eşitlikte ve `yok`ta ada göre."""
    return sorted(
        durumlar,
        key=lambda d: (-d.skor, d.seviye in (None, "yok"), Path(d.repo).name.lower()),
    )
