"""Sizinti taramasi: calisma agaci + git gecmisi, MASKELENMIS bulgular.

BAĞLAYICI KURAL — ham sır HİÇBİR YERE ÇIKMAZ: DB'ye, stdout/stderr'a, log'a,
istisna mesajına veya traceback'e. Eşleşen ham metin yalnızca
`bulgu_olustur`/`_snippet` üzerinde YEREL değişkenlerdir ve dışarı çıkmaz;
dönen tek şey maskelenmiş bir sözlüktür (`snippet_redacted`).

Bulgu nesnesi YALNIZCA `bulgu_olustur` içinde üretilir. Maskeleme DÖRT adımlıdır
ve SIRALAMA ÖNEMLİDİR:
  1. Sağlayıcı desenleri (sırrın TAMAMINI siler, `[maskeli:sir]`).
  2. Etiketli değer desenleri (`API_KEY = …` → `[maskeli:api-anahtari]`).
  3. Kişisel yol, e-posta.
  4. SAVUNMA KATMANI: tespit edilmemiş olsa bile 24+ karakterlik, rakam içeren
     her `[A-Za-z0-9_-]` dizisi `[maskeli:uzun-deger]` olur.
  5. `snippet_redacted`, eşleşmenin ETRAFINDAKİ ~100 karakterlik pencereye
     KIRPILIR; kesilen uçlara `…` konur. Kırpma maskelemeden SONRA yapılır.
"""

from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path
from typing import Any, Iterable, NamedTuple

from .scan import ALLOWED_GIT_SUBCOMMANDS, GitError, find_repo_paths, git_env

#: Kesinlikle bulgu OLMAYAN e-posta imzaları.
EPOSTA_ISTISNA = frozenset({"noreply@anthropic.com", "git@github.com", "postmaster@localhost"})

#: Alan adı bazlı istisna (`...@example.com` gibi yer tutucular).
EPOSTA_ISTISNA_ALANADLARI = frozenset(
    {"users.noreply.github.com", "localhost", "example.com", "example.org", "example.net"}
)

#: `api_key = <deger>` deseninde deger yer tutucu ise bulgu DEĞİLDİR.
#: `process.env.X` / `os.environ[...]` gibi KOD referanslari da yer tutucudur:
#: bunlar sır DEGILDIR, degisken okunur.
YER_TUTUCU_DESENI = re.compile(
    r"x{3,}|<[^>]*>|\$\{[^}]*\}|\$[A-Z_][A-Z0-9_]*|your[_-]|"
    r"example|placeholder|changeme|dummy|sample|redacted|"
    r"todo|none|null|insert|replace|test|demo|asdf|foo|bar|"
    r"abc123|123456|passwd|password|"
    r"process\.env|os\.environ|getenv|ENV\[|env\[|os\.get",
    re.IGNORECASE,
)

#: Bu ekler `.env` izlemesini düşürür.
ENV_DOSYA_ADI_ISTISNA = (".example", ".sample", ".template", ".dist", ".defaults")

#: Test/fixture yolları: bulgular bir kademe düşürülür ama ATLANMAZ.
TEST_YOLU_KIRINTILARI = ("tests/", "test/", "fixtures/", "__tests__/", "examples/", "testdata/")

#: Test yolunda bir kademe düşürülmüş hali.
BIR_KADEME_DUSUK = {"yuksek": "dusuk", "orta": "bilgi", "dusuk": "bilgi", "bilgi": "bilgi"}

#: `tests/` altındaki türler bir kademe düşürülür. `env-izlenen` ve
#: `gorsel-elle-kontrol` BİLEREK DIŞARIDA: ilki içerik okunmadığı için dosyanın
#: varlığı zaten sırdır (düşürmek yanlış negatif olurdu), ikincisi zaten
#: `bilgi`. `ozel-anahtar` test fixture'ındaysa `dusuk`'a iner — bir testin
#: kendi ürettiği sahte anahtardır (bkz. `harita/tests/conftest.py`).
TEST_YOLU_DUSURULEN_TURLER = frozenset({"api-anahtari", "ozel-anahtar", "kisisel-yol", "e-posta"})

#: `snippet_redacted` üst sınırı (maskelemeden SONRA kırpılır).
SNIPPET_MAX = 120
#: Pencere, TESPİT EDİLEN eşleşmenin etrafında kurulur: eşleşmeden önce bu
#: kadar, sonrası bu kadar karakter. 120'lik tavanın içinde kalır.
PENCERE_ON = 40
PENCERE_SON = 60

#: Ham satır BAŞTAN kesilmez — kesmek, satırın sonundaki sırları gizlerdi.
#: Bu sınır yalnızca TEORİK bir güvenlik tavanıdır (diff çıktısı denetimsiz
#: büyüyebilir). Tüm desenler DOĞRUSALDır (iç içe çakışan niceleyici yoktur),
#: dolayısıyla 50k karakterlik tekrarlı bir satırda bile katastrofik geri izleme
#: olmaz; ölçüm `test_uzun_satir_yavasligi` ile doğrulanır.
SATIR_UST_SINIR = 200_000

#: Repo başına toplam süre üst sınırı; aşılırsa "kısmi tarama" uyarısı.
REPO_SURE_UST_SINIR = 120.0

#: Commit ayracı: `git log --format` çıktısında commit'ler arasında kendi
#: satırında görünür ve `+` ile başlamadığı için taranmaz. Kontrol karakteri
#: KULLANILMAZ: `str.splitlines()` \x1e/\x1c/\x1f gibi karakterlerde de böler ve
#: ham log sırasına beklenmedik satırlar karışır.
GECMIS_AYRAC = "@@ATLAS-COMMIT:"
GECMIS_AYRAC_SON = ":ATLAS-COMMIT@@"
GECMIS_AYRAC_DESENI = re.compile(r"^@@ATLAS-COMMIT:([0-9a-f]{7,40}):ATLAS-COMMIT@@$", re.MULTILINE)

#: Izlenen dosya listesi (`git ls-files -z`, izlenmeyen dosyalar kapsam dışı).
#: Alt komut `ALLOWED_GIT_SUBCOMMANDS` içinde olmak ZORUNDA (aşağıda doğrulanır).
LS_FILES_SUBCOMMAND = "ls-files"

#: `--format` çıktısı ayraç olarak kullanılır; kısa hash yeterli.
GECMIS_LOG_BICIM = f"--format={GECMIS_AYRAC}%h{GECMIS_AYRAC_SON}"


# --------------------------------------------------------------------------
# Maskeleme
# --------------------------------------------------------------------------

#: KURAL: bir maskeleme deseni, onu TESPİT eden desenden DAR olmamalıdır —
#: tespit edilen her şey en az o kadar geniş maskeyle silinmelidir. Aksi halde
#: ham sır maskelenmeden `snippet_redacted` içine düşer.
#:
#: Ters yön de önemlidir: maske TESPİTTEN geniş olursa masum metni de bozar.
#: Gerçek vault taramasında `sk-[A-Za-z0-9_-]{4,}` maskesi `<task-notification>`
#: metnini `<ta[maskeli:...]>` yapmıştı. Bu yüzden `sk-` maskesi tespitle AYNI
#: koşulu taşır (en az bir rakam + 20+ karakter).
#:
#: Değiştirme metinleri `lambda` ile verilir: `re.sub` şablonunda `\U` gibi
#: kaçışlar hata verir (Windows yolu), lambda'da metin olduğu gibi yazılır.
_SIR_ISARETI = "[maskeli:api-anahtari]"

_SK_MASKE = re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{20,}")

#: Sağlayıcı gövdeleri. Tespit desenleriyle AYNI ön koşulu taşır.
_SAGLAYICI_MASKE_DESENLERI: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"[A-Za-z0-9+/]{64,}={0,2}"), "[maskeli:sir]"),
    (
        _SK_MASKE,
        lambda m: _SIR_ISARETI if any(k.isdigit() for k in m.group(0)) else m.group(0),
    ),
    (re.compile(r"AKIA[0-9A-Z]{8,}"), _SIR_ISARETI),
    (re.compile(r"gh[pousr]_[A-Za-z0-9]{8,}"), _SIR_ISARETI),
    (re.compile(r"xox[baprs]-[A-Za-z0-9-]{8,}"), _SIR_ISARETI),
    (re.compile(r"sb_(?:publishable|secret)_[A-Za-z0-9_-]{8,}"), _SIR_ISARETI),
    (re.compile(r"sk_(?:live|test)_[A-Za-z0-9]{8,}"), _SIR_ISARETI),
    (re.compile(r"AIza[0-9A-Za-z_-]{16,}"), _SIR_ISARETI),
    (
        re.compile(r"eyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}"),
        _SIR_ISARETI,
    ),
)

#: Etiketli değer maskesi. `API Key for the credential: <değer>` gibi satırları
#: da kapsayabilmelidir; bu yüzden etiket ile `:=` arasında 40 karaktere kadar
#: metin tolere edilir. Yazma koşulu TESPİT süzgeçlerinin BİLEŞİMİDİR:
#: maske hiçbir zaman tespitten DAR olamaz, ama tespit dışı masum metni de
#: bozmaz (ör. "Token kullanilir: thisfunctionalitychanged" bozulmaz).
_ETIKETLI_DEGER_MASKE = re.compile(
    r"(?i)\b(api[ _-]?key|apikey|credential|secret|token|passwd|password)\b"
    r"[^\n:=]{0,40}[:=]\s*[\"']?[A-Za-z0-9_\-/+.=~]{16,}[\"']?(?![A-Za-z0-9_$])(?!\s*\()"
)


def _etiketli_deger_maske(m: re.Match) -> str:
    if not (_yer_tutucu_değil(m) and _rakamli(m)):
        return m.group(0)
    return f"{m.group(1)}={_SIR_ISARETI}"


_YOL_DESENLERI: tuple[tuple[re.Pattern, Any], ...] = (
    (re.compile(r"(?i)C:\\+Users\\+[^\\/\s\"'<>]+"), lambda m: "C:\\Users\\<kullanici>"),
    (re.compile(r"/Users/[^/\s\"'<>]+"), lambda m: "/Users/<kullanici>"),
    (re.compile(r"/home/[^/\s\"'<>]+"), lambda m: "/home/<kullanici>"),
)

_EPOSTA_DESENI = re.compile(
    r"(?<![\w.+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![\w.-])"
)


def _eposta_istisna(adres: str) -> bool:
    kucuk = adres.lower()
    return kucuk in EPOSTA_ISTISNA or kucuk.rsplit("@", 1)[-1] in EPOSTA_ISTISNA_ALANADLARI


def _eposta_maske(m: re.Match) -> str:
    return m.group(0) if _eposta_istisna(m.group(0)) else "<e-posta>"


#: SAVUNMA KATMANI (son adım). Tespit edilmemiş olsa bile sır gibi görünen
#: HER dizi silinir: 24+ karakterlik `[A-Za-z0-9_-]` ve içinde en az bir rakam.
#: `/` ve `.` sınıfa dahil DEĞİLDİR; bu yüzden yol/URL parçaları bölünür ve
#: kısa parçalar (`example.com`, `import-2026-07-part-024`) olduğu gibi kalır.
_UZUN_DEGER_MASKE = re.compile(r"[A-Za-z0-9_-]{24,}")
_UZUN_DEGER_ISARETI = "[maskeli:uzun-deger]"


def _uzun_deger_maske(m: re.Match) -> str:
    if not any(k.isdigit() for k in m.group(0)):
        return m.group(0)  # rakamsız kebab-case cümle/parca: dokunma
    return _UZUN_DEGER_ISARETI


_MASKE_ADIMLARI: tuple[tuple[re.Pattern, Any], ...] = (
    *_SAGLAYICI_MASKE_DESENLERI,
    (_ETIKETLI_DEGER_MASKE, _etiketli_deger_maske),
    *_YOL_DESENLERI,
    (_EPOSTA_DESENI, _eposta_maske),
    (_UZUN_DEGER_MASKE, _uzun_deger_maske),
)


def _gecit(
    metin: str, desen: re.Pattern, degistir: Any
) -> tuple[str, list[tuple[int, int, int, int]]]:
    """Tek maske adımını uygular.

    Döner: `(yeni metin, [(eski_bas, eski_bit, yeni_bas, yeni_uzunluk), ...])`.
    Dönen liste, sonraki adımlarda koordinatların kaydırılmasında kullanılır.
    """
    cikti: list[str] = []
    duzenlemeler: list[tuple[int, int, int, int]] = []
    konum = 0
    kayma = 0
    for m in desen.finditer(metin):
        yeni = degistir(m) if callable(degistir) else degistir
        yeni_bas = m.start() + kayma
        cikti.append(metin[konum : m.start()])
        cikti.append(yeni)
        duzenlemeler.append((m.start(), m.end(), yeni_bas, len(yeni)))
        kayma += len(yeni) - (m.end() - m.start())
        konum = m.end()
    cikti.append(metin[konum:])
    return "".join(cikti), duzenlemeler


def _nokta_tasi(p: int, duzenlemeler: list[tuple[int, int, int, int]]) -> int:
    """Eski koordinattaki `p` noktasını, düzenlemelerden sonraki konuma taşır."""
    kayma = 0
    for eski_bas, eski_bit, yeni_bas, _uz in duzenlemeler:
        if p < eski_bas:
            break
        if p >= eski_bit:
            kayma += (yeni_bas + _uz) - eski_bit
        else:  # p maskenin İÇİNDE kaldı: yeni konuma yatır
            return yeni_bas + kayma
    return p + kayma


def _maske_izlemeli(metin: str) -> tuple[str, list[tuple[int, int]]]:
    """Ham metni TAMAMEN maskelenmiş metne çevirir + maske aralıklarını verir.

    Aralıklar YENİ koordinattadır; çağıran, tespit eşleşmesinin nereye
    düştüğünü bulup pencereyi oranın ETRAFINDA kurar.
    """
    araliklar: list[tuple[int, int]] = []
    for desen, degistir in _MASKE_ADIMLARI:
        metin, duzenlemeler = _gecit(metin, desen, degistir)
        if duzenlemeler:
            araliklar = [
                (_nokta_tasi(ab, duzenlemeler), _nokta_tasi(abit, duzenlemeler))
                for ab, abit in araliklar
            ]
            araliklar.extend((nb, nb + uz) for _eb, _ebit, nb, uz in duzenlemeler)
    return metin, araliklar


def maske(metin: str) -> str:
    """Ham metni TAMAMEN maskelenmiş metne çevirir (kırpmadan ÖNCE)."""
    return _maske_izlemeli(metin)[0]


def _kirp(metin: str) -> str:
    """Maskelenmiş metni `SNIPPET_MAX` karaktere indirir (EN SON adım)."""
    if len(metin) <= SNIPPET_MAX or metin.endswith("…"):
        return metin
    return metin[: SNIPPET_MAX - 1] + "…"


def _merkez(araliklar: list[tuple[int, int]], eslesme: tuple[int, int] | None) -> int:
    """Pencerenin kurulacağı konum: tespit eşleşmesinin yeni koordinatı.

    Eşleşme maskeyle değişmemişse (ör. `-----BEGIN … PRIVATE KEY-----` başlığı)
    ilk maske aralığı kullanılır; böylece snippet'ta en az bir `[maskeli`
    işareti bulunur.
    """
    if eslesme is not None:
        bas, bit = eslesme
        for ab, a_bit in araliklar:
            if ab <= bas < a_bit or ab < bit <= a_bit:
                return ab
    return araliklar[0][0] if araliklar else 0


def _snippet(ham: str, eslesme: tuple[int, int] | None) -> str:
    """Eşleşmenin ETRAFINDAKI pencereyi, maskelenmiş hâliyle üretir.

    SIRALAMA: (1) satırın TAMAMI maskelenir — pencere, sırın ortasından
    başlasa bile ham parça sızmaz; (2) maske aralıklarından pencere konumu
    bulunur; (3) pencere kesilir ve kesilen uçlara `…` konur. Pencere bir maske
    işaretinin İÇİNDE kalıyorsa o işaret BÖLÜNMEZ (tamamı alınır).
    """
    if not ham:
        return ""
    maskeli, araliklar = _maske_izlemeli(ham)
    p = _merkez(araliklar, eslesme)
    on = max(0, p - PENCERE_ON)
    son = min(len(maskeli), p + PENCERE_ON + PENCERE_SON)
    for ab, a_bit in araliklar:
        if ab < on < a_bit:
            on = ab
        if ab < son < a_bit:
            son = a_bit
    parca = maskeli[on:son]
    if on:
        parca = "…" + parca
    if son < len(maskeli):
        parca = parca + "…"
    return _kirp(parca)


# --------------------------------------------------------------------------
# BULGU ÜRETİMİ — TEK NOKTA
# --------------------------------------------------------------------------

def bulgu_olustur(
    *,
    kind: str,
    severity: str,
    file: str | None,
    line: int | None,
    commit: str | None,
    ham_metin: str | None = None,
    eslesme: tuple[int, int] | None = None,
    test_yolu: bool = False,
    siradan_ev_yolu: bool = False,
) -> dict[str, Any]:
    """BULGU NESNESİ YALNIZCA BURADA ÜRETİLİR.

    `ham_metin` (varsa) buraya GİRER ve buradan ÇIKMAZ: önce maskelenir, sonra
    eşleşmenin etrafındaki pencereye kırpılır. Dönen sözlük DB'ye yazılabilir
    ve stdout'a basılabilir.
    """
    if siradan_ev_yolu and kind == "kisisel-yol":
        # `/home/user/...` bu container'ın sıradan yolu; gerçek kişisel yol değil.
        severity = "dusuk"
    if test_yolu and kind in TEST_YOLU_DUSURULEN_TURLER:
        severity = BIR_KADEME_DUSUK.get(severity, severity)
    return {
        "kind": kind,
        "severity": severity,
        "file": file,
        "line": line,
        "commit": commit,
        "snippet_redacted": _snippet(ham_metin, eslesme) if ham_metin else None,
    }


def bulgu_satiri(bulgu: Any) -> str:
    """DB satırından (dict veya `sqlite3.Row`) `dosya:satir` metni üretir."""
    dosya = bulgu["file"] or "-"  # sqlite3.Row da `[]` ile erişir
    satir = bulgu["line"]
    return f"{dosya}:{satir}" if satir is not None else dosya


# --------------------------------------------------------------------------
# Tespit desenleri (tümü doğrusal)
# --------------------------------------------------------------------------

_DESEN_SK = re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{20,}")
#: Supabase: YAYINLANABİLİR anahtar istemci tarafında herkese açık olması
#: TASARIM GEREĞİDİR (bilgi); `sb_secret_` ise gerçek sırdır (yüksek).
_DESEN_SB_PUBLISHABLE = re.compile(r"sb_publishable_[A-Za-z0-9_-]{20,}")
_DESEN_SB_SECRET = re.compile(r"sb_secret_[A-Za-z0-9_-]{20,}")
_DESEN_AWS = re.compile(r"AKIA[0-9A-Z]{16}")
_DESEN_GH = re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}")
_DESEN_SLACK = re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}")
_DESEN_STRIPE = re.compile(r"sk_(?:live|test)_[A-Za-z0-9]{16,}")
_DESEN_GOOGLE = re.compile(r"AIza[0-9A-Za-z_-]{35}")
_DESEN_JWT = re.compile(
    r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"
)
_DESEN_ANAHTAR_DEGER = re.compile(
    r"(?i)\b(api[_-]?key|secret|token|password|passwd)\b[\"']?\s*[:=]\s*"
    # Deger tirnak icinde ya da tirnaksiz; degER sonrasi imle satirlayici
    # gelmemeli. `apiKey = resolveOpenRouterKey(config)` bir fonksiyon CAGRISI
    # degil gecici bir degerdir: bu yuzden `(?![A-Za-z0-9_$])` ve `(?!\s*\()`
    # eklenir. Gercek bir sır (tirnakta ya da degisken sonunda) bu sinirlari
    # gecer.
    r"[\"']?[A-Za-z0-9/+_.~-]{16,}[\"']?(?![A-Za-z0-9_$])(?!\s*\()"
)
#: ETİKETLİ DEĞER: etiket ile `:=` arasında EN ÇOK 40 karakter olabilir.
#: Böylece `API Key for the credential: <değer>` gibi satırlar kendi başına
#: tespit edilir. Değer 24+ karakter ve içinde EN AZ BİR RAKAM olmalıdır
#: (yer tutucu/kod referansı süzgeçleri aynen geçerlidir).
_DESEN_ETIKETLI_DEGER = re.compile(
    r"(?i)\b(api[ _-]?key|apikey|credential|secret|token|passwd|password)\b"
    r"[^\n:=]{0,40}[:=]\s*[\"']?(?P<deger>[A-Za-z0-9_\-/+.=~]{24,})"
    r"[\"']?(?![A-Za-z0-9_$])(?!\s*\()"
)
_DESEN_OZEL_ANAHTAR = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY")
_DESEN_YOL_WINDOWS = re.compile(r"C:\\Users\\[^\\\s\"']+")
_DESEN_YOL_USERS = re.compile(r"/Users/[^/\s\"']+/")
_DESEN_YOL_HOME = re.compile(r"/home/[^/\s\"']+/")
_DESEN_EPOSTA = _EPOSTA_DESENI

_SIRADAN_EV_YOLU = re.compile(r"^/home/user/", re.IGNORECASE)
_EV_YOLU_ONEKI = re.compile(r"^/home/", re.IGNORECASE)


def _rakam_var(eslesme: re.Match) -> bool:
    """`sk-` eşleşmesinde en az BİR rakam olmalı.

    Kebab-case kelimeleri (`flask-`, `task-`, `risk-`) eler; aksi halde
    `sk-sqlalchemy-migrate-extension` gibi metinler yanlış pozitif olurdu.
    """
    return any(k.isdigit() for k in eslesme.group(0))


def _rakamli(eslesme: re.Match) -> bool:
    """Etiketli değerin KENDİSİ en az bir rakam içermeli (`deger` grubu)."""
    deger = eslesme.groupdict().get("deger")
    if deger is None:
        deger = eslesme.group(0)
    return any(k.isdigit() for k in deger)


def _yer_tutucu_değil(eslesme: re.Match) -> bool:
    return not YER_TUTUCU_DESENI.search(eslesme.group(0))


def _anahtar_deger_gibi(eslesme: re.Match) -> bool:
    """`anahtar = deger` eslesmesi gercek bir anahtara BENZIYOR mu?

    Sozluk/gunluk metinlerinde `Token: <sozcuk>` siklikla gecer (vault gunluk
    dosyalarinda gozlemlendi). Gercek bir sir ya rakam icerir ya buyuk harf
    karisimidir ya da tirnakli/tireli bir bicimdedir; Duz kucuk harfli sozcuk
    dizisi sirdir.
    """
    g = eslesme.group(0)
    deger = g.split("=", 1)[-1].split(":", 1)[-1].strip("\"' ")
    if any(k.isdigit() for k in deger):
        return True
    if any(k.isupper() for k in deger):
        return True
    # Tirnakli deger (`api_key = "..."`) guvenilir kabul edilir.
    return bool(re.search(r"[\"']", deger)) or ("-" in deger) or ("_" in deger)


def _eposta_gecerli(eslesme: re.Match) -> bool:
    return not _eposta_istisna(eslesme.group(0))


def _ev_yolu_mu(eslesme: re.Match) -> bool:
    """`/home/<ad>/` her zaman kişisel yol adayıdır.

    `/home/user/` (container'ın sıradan yolu) de EŞLEŞİR ama önem `dusuk`
    olur; bu ayrım `bulgu_olustur(siradan_ev_yolu=...)` ile yapılır.
    """
    return bool(_EV_YOLU_ONEKI.match(eslesme.group(0)))


#: (kind, severity, desen, süzgeç). Süzgeç `None` ise ek koşul yoktur.
#: `api-anahtari` desenleri tespit sırasında denenir; ilk geçen eşleşmede durulur.
TESPIT_DESENLERI: tuple[tuple[str, str, re.Pattern, Any], ...] = (
    ("api-anahtari", "yuksek", _DESEN_SK, _rakam_var),
    ("api-anahtari", "yuksek", _DESEN_SB_SECRET, None),
    ("api-anahtari", "yuksek", _DESEN_AWS, None),
    ("api-anahtari", "yuksek", _DESEN_GH, None),
    ("api-anahtari", "yuksek", _DESEN_SLACK, None),
    ("api-anahtari", "yuksek", _DESEN_STRIPE, None),
    ("api-anahtari", "yuksek", _DESEN_GOOGLE, None),
    ("api-anahtari", "yuksek", _DESEN_JWT, None),
    # `sb_publishable_` tasarım gereği herkese açıktır: yine de kayda gider.
    ("api-anahtari", "bilgi", _DESEN_SB_PUBLISHABLE, None),
    (
        "api-anahtari",
        "yuksek",
        _DESEN_ANAHTAR_DEGER,
        lambda m: _yer_tutucu_değil(m) and _anahtar_deger_gibi(m),
    ),
    (
        "api-anahtari",
        "yuksek",
        _DESEN_ETIKETLI_DEGER,
        lambda m: _yer_tutucu_değil(m) and _rakamli(m),
    ),
    ("ozel-anahtar", "yuksek", _DESEN_OZEL_ANAHTAR, None),
    ("kisisel-yol", "orta", _DESEN_YOL_WINDOWS, None),
    ("kisisel-yol", "orta", _DESEN_YOL_USERS, None),
    ("kisisel-yol", "orta", _DESEN_YOL_HOME, _ev_yolu_mu),
    ("e-posta", "dusuk", _DESEN_EPOSTA, _eposta_gecerli),
)


def dosya_test_yolu_mu(dosya: str | None) -> bool:
    if not dosya:
        return False
    norm = f"/{dosya.replace(chr(92), '/')}/"
    return any(f"/{t}" in norm for t in TEST_YOLU_KIRINTILARI)


def satiri_tara(
    satir: str,
    *,
    dosya: str | None = None,
    commit: str | None = None,
    line: int | None = None,
) -> list[dict[str, Any]]:
    """TEK satırı tüm desenlerle tarar, MASKELENMİŞ bulgular döndürür.

    Ham satır yalnızca bu fonksiyona girer; bulgular `bulgu_olustur` üzerinden
    üretildiği için ham içerik dışarı çıkmaz. `eslesme` koordinatı snippet'in
    eşleşmenin ETRAFINDA kurulması için `bulgu_olustur`'a geçirilir; metnin
    kendisi asla dönmez.
    """
    if not satir:
        return []
    ham = satir[:SATIR_UST_SINIR]
    if "\x00" in ham:  # "metin" değildir
        return []
    test_yolu = dosya_test_yolu_mu(dosya)
    bulgular: list[dict[str, Any]] = []
    gorulen: set[str] = set()
    for kind, severity, desen, suzgec in TESPIT_DESENLERI:
        if kind in gorulen:
            continue  # satır başına tür başına tek bulgu
        for eslesme in desen.finditer(ham):
            if suzgec is not None and not suzgec(eslesme):
                continue
            bulgular.append(
                bulgu_olustur(
                    kind=kind,
                    severity=severity,
                    file=dosya,
                    line=line,
                    commit=commit,
                    ham_metin=ham,
                    eslesme=eslesme.span(),
                    test_yolu=test_yolu,
                    siradan_ev_yolu=kind == "kisisel-yol" and bool(_SIRADAN_EV_YOLU.match(eslesme.group(0))),
                )
            )
            gorulen.add(kind)
            break  # desen basina tek eslesme
    return bulgular


# --------------------------------------------------------------------------
# .env / görsel (dosya-özel türler)
# --------------------------------------------------------------------------

_ENV_ADI_DESENI = re.compile(r"^\.env(\..+)?$", re.IGNORECASE)
GORSEL_UZANTILARI = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"})
#: Görsel taramasının DIŞINDA kalan üretim/bağımlılık dizinleri (git izlese
#: bile bu dosyalar repo içeriği değildir).
GORSEL_HARIC_DIR = ("node_modules/", ".venv/", "vendor/", "dist/", "build/", "__snapshots__/")
#: Bu sayıdan SONRA dosya başına bulgu yerine TEK özet bulgu yazılır.
GORSEL_OZET_ESIGI = 50

GORSEL_ELLE_KONTROL_NOTU = "elle kontrol et (kişisel veri/yol/anahtar var mı)"


def env_dosyasi_mi(dosya: str) -> bool:
    """Git'in İZLEDİĞİ `.env` dosyası mı? (`.env.example` vb. HAYIR)."""
    ad = Path(dosya).name
    if not _ENV_ADI_DESENI.match(ad):
        return False
    kucuk = ad.lower()
    return not any(kucuk.endswith(ek) for ek in ENV_DOSYA_ADI_ISTISNA)


def env_bulgu_olustur(dosya: str) -> dict[str, Any]:
    """`.env` için YOL bulgusu. Dosya içeriği OKUNMAZ."""
    return bulgu_olustur(
        kind="env-izlenen", severity="yuksek", file=dosya, line=None, commit=None
    )


def gorsel_dosyalari(lsfiles: Iterable[str]) -> list[str]:
    """Git'in izlediği TÜM görseller (herhangi bir dizinde), üretim dizinleri hariç."""
    aday: set[str] = set()
    for d in lsfiles:
        if Path(d).suffix.lower() not in GORSEL_UZANTILARI:
            continue
        norm = f"/{d.replace(chr(92), '/')}/".lower()
        if any(f"/{dizin}" in norm for dizin in GORSEL_HARIC_DIR):
            continue
        aday.add(d)
    return sorted(aday)


def gorsel_bulgu_olustur(dosya: str) -> dict[str, Any]:
    """OCR YOK: yalnızca dosya varlığı + elle kontrol notu."""
    return bulgu_olustur(
        kind="gorsel-elle-kontrol",
        severity="bilgi",
        file=dosya,
        line=None,
        commit=None,
        ham_metin=GORSEL_ELLE_KONTROL_NOTU,
    )


def gorsel_ozet_bulgu_olustur(adet: int) -> dict[str, Any]:
    """Çok sayıda görselde liste boğulmasın diye TEK özet bulgu."""
    return bulgu_olustur(
        kind="gorsel-elle-kontrol",
        severity="bilgi",
        file=None,
        line=None,
        commit=None,
        ham_metin=f"{adet} görsel, elle kontrol et (kişisel veri/yol/anahtar var mı)",
    )


def gorsel_bulgulari(lsfiles: Iterable[str]) -> list[dict[str, Any]]:
    dosyalar = gorsel_dosyalari(lsfiles)
    if len(dosyalar) > GORSEL_OZET_ESIGI:
        return [gorsel_ozet_bulgu_olustur(len(dosyalar))]
    return [gorsel_bulgu_olustur(d) for d in dosyalar]


# --------------------------------------------------------------------------
# Repo düşük seviye
# --------------------------------------------------------------------------

#: İkili dosya: ilk 8 KiB içinde NUL.
BINAR_BASLAMA_NUL = 8192
#: 1 MiB'tan büyük dosya atlanır.
DOSYA_UST_SINIR = 1024 * 1024

_DIFF_BASLIK = "diff --git "
_DIFF_AYRAC = "rename to "
_DIFF_ESKI_ONEKI = "--- "
_DIFF_YENI_ONEKI = "+++ "
_DIFF_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
_DIFF_BINAR = re.compile(r"^(Binary files |GIT binary patch)")

#: git'in diff yol alanında kullandığı kaçışlar (C stili, `core.quotePath`).
_GIT_KACIS = {
    "a": "\a", "b": "\b", "f": "\f", "n": "\n", "r": "\r",
    "t": "\t", "v": "\v", "\\": "\\", '"': '"',
}
_GIT_SEKIZLI = "01234567"


def _yol_coz(alan: str) -> str:
    """`--- a/<yol>` alanındaki metni GERÇEK dosya yoluna çevirir.

    git, özel karakter içeren yolları tırnak içinde yazar:
    `--- "a/emoji \\360\\237\\230\\200 dosya.txt"`. `-c core.quotepath=false`
    ile ASCII olmayan karakterler düz gelir ama tırnak içinde kalan
    (`"`, `\\`, TAB) yollar her zaman çözülmelidir. Ayrıca `a/`/`b/` öneki
    çıkarılır.
    """
    alan = alan.rstrip("\t")  # git, tırnaksız yollardan sonra TAB yazar
    if len(alan) >= 2 and alan[0] == '"' and alan[-1] == '"':
        alan = _tirnaki_coz(alan[1:-1])
    for onek in ("a/", "b/"):
        if alan.startswith(onek):
            return alan[len(onek) :]
    return alan


def _tirnaki_coz(ic: str) -> str:
    """Tırnak içindeki git yol alanını bayt doğru çözer.

    Sekizli kaçışlar (`\\303\\274`) UTF-8 BAYT'larıdır; karakter karakter
    çözülürse Türkçe harfler bozulur.
    """
    bayt = bytearray()
    i = 0
    while i < len(ic):
        ch = ic[i]
        if ch != "\\":
            bayt += ch.encode("utf-8")
            i += 1
            continue
        i += 1
        if i >= len(ic):
            bayt += b"\\"
            break
        k = ic[i]
        if k in _GIT_KACIS:
            bayt += _GIT_KACIS[k].encode("utf-8")
            i += 1
        elif k in _GIT_SEKIZLI:
            j = i
            while j < min(i + 3, len(ic)) and ic[j] in _GIT_SEKIZLI:
                j += 1
            bayt.append(int(ic[i:j], 8) & 0xFF)
            i = j
        else:
            bayt += k.encode("utf-8")
            i += 1
    return bayt.decode("utf-8", "replace")


def _git(
    args: list[str],
    repo: Path,
    timeout: int,
    *,
    izinli: frozenset[str],
    tolere_hatalar: frozenset[int] = frozenset(),
    ek_config: dict[str, str] | None = None,
) -> bytes:
    """Salt-okunur git çağrısı.

    `tolere_hatalar`: normal kabul edilen sıfır-dışı dönüş kodları (ör. boş
    depoda `git log` 128 verir — bu bir hata değildir, sadece commit yoktur).

    `ek_config`: `GIT_CONFIG_COUNT` ile TEK KULLANIMLIK config geçersiz kılma.
    Komut satırı DEĞİŞMEZ (guard/izin listesi etkilenmez) ve hiçbir kalıcı
    ayar yazılmaz.
    """
    alt = args[0] if args else ""
    if not alt or alt not in ALLOWED_GIT_SUBCOMMANDS or alt not in izinli:
        raise GitError(f"izin verilmeyen git komutu: {alt}")
    env = git_env()
    if ek_config:
        env["GIT_CONFIG_COUNT"] = str(len(ek_config))
        for i, (anahtar, deger) in enumerate(ek_config.items()):
            env[f"GIT_CONFIG_KEY_{i}"] = anahtar
            env[f"GIT_CONFIG_VALUE_{i}"] = deger
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), *args], capture_output=True, timeout=timeout, env=env
        )
    except subprocess.TimeoutExpired as exc:
        raise GitError("git komutu zaman asimina ugradi") from exc
    except (OSError, subprocess.SubprocessError) as exc:
        raise GitError(type(exc).__name__) from exc
    if proc.returncode != 0 and proc.returncode not in tolere_hatalar:
        # stderr HAM olabilir; yalnızca hata sinyali kullanılır, içerik loglanmaz.
        raise GitError("git komutu basarisiz")
    return proc.stdout


def ls_files(repo: Path, timeout: int = 60) -> list[str]:
    """`git ls-files -z`: yalnızca İZLENEN dosyalar."""
    ham = _git(["ls-files", "-z"], repo, timeout, izinli=frozenset({LS_FILES_SUBCOMMAND}))
    return [p.decode("utf-8", "replace") for p in ham.split(b"\x00") if p]


def dosya_oku_salt(repo: Path, dosya: str) -> bytes | None:
    """Dosyayı SALT-OKUNUR modda okur; atlanması gerekenlerde `None`."""
    yol = repo / dosya
    try:
        if yol.is_symlink() or not yol.is_file():
            return None
        if yol.stat().st_size > DOSYA_UST_SINIR:
            return None
        with open(yol, "rb") as fh:  # yalnızca 'r' kipi; yazma modu yok
            veri = fh.read(DOSYA_UST_SINIR + 1)
    except OSError:
        return None
    if len(veri) > DOSYA_UST_SINIR or b"\x00" in veri[:BINAR_BASLAMA_NUL]:
        return None
    return veri


def tara_calisma_agaci(repo: Path, *, timeout: int = 60) -> list[dict[str, Any]]:
    """Yalnızca `git ls-files` ile İZLENEN dosyalar taranır."""
    lsfiles = ls_files(repo, timeout)
    bulgular: list[dict[str, Any]] = []
    env_dosyalari = {d for d in lsfiles if env_dosyasi_mi(d)}
    for d in sorted(env_dosyalari):
        bulgular.append(env_bulgu_olustur(d))
    bulgular.extend(gorsel_bulgulari(lsfiles))
    for dosya in lsfiles:
        if dosya in env_dosyalari:
            continue  # `.env` içeriği okunmaz; yol bulgusu yeter
        veri = dosya_oku_salt(repo, dosya)
        if veri is None:
            continue
        metin = veri.decode("utf-8", "replace")
        for no, satir in enumerate(metin.splitlines(), start=1):
            for b in satiri_tara(satir, dosya=dosya, line=no):
                bulgular.append(b)
    return bulgular


def _gecmis_govdesi(govde: str, commit: str) -> list[dict[str, Any]]:
    """`git log -p -U0` gövdesini dosya + satır numarasıyla tarar.

    Durum makinesi (dört durum):
      * `diff --git …`          → dosya bağlamını SIFIRLAR (commit'te birden
                                   çok dosya olabilir; İLK dosyaya bağlamak
                                   yanlış dosya atfı üretir).
      * `--- a/…` / `+++ b/…`   → eski/yeni yolu günceller. `+++ /dev/null`
                                   silme, `rename to` yeniden adlandırmadır.
      * `@@ -a,b +c,d @@`       → YENİ dosyadaki satır sayacı `c`'ye kurulur.
      * gövde satırı           → `+` eklenen satır (yeni numara verilir, sonra
                                   sayac artar), `-` silinen satır (yeni
                                   dosyada YOK: sayac artmaz), ` ` bağlam
                                   satırı (sayac artar).
    """
    bulgular: list[dict[str, Any]] = []
    eski_yol: str | None = None
    yeni_yol: str | None = None
    dosya: str | None = None
    satir: int | None = None
    hunk_ici = False

    for ham_satir in govde.splitlines():
        if ham_satir.startswith(_DIFF_BASLIK):
            eski_yol = yeni_yol = dosya = None
            satir = None
            hunk_ici = False
            continue
        if ham_satir.startswith(_DIFF_AYRAC):  # rename to <yeni yol>
            yeni_yol = _yol_coz(ham_satir[len(_DIFF_AYRAC) :])
            dosya = yeni_yol
            continue
        if not hunk_ici:
            # Hunk DIŞINDA: `---`/`+++` dosya başlıklarıdır, eklenen satır
            # değildir (hunk İÇİNDE aynı karakterler normal gövde olur).
            if ham_satir.startswith(_DIFF_ESKI_ONEKI):
                eski_yol = _yol_coz(ham_satir[len(_DIFF_ESKI_ONEKI) :])
                continue
            if ham_satir.startswith(_DIFF_YENI_ONEKI):
                yeni_yol = _yol_coz(ham_satir[len(_DIFF_YENI_ONEKI) :])
                # Silinen dosyada `+++ /dev/null` → atf ESKİ yola yapılır.
                dosya = eski_yol if yeni_yol == "/dev/null" else yeni_yol
                continue
            hunk = _DIFF_HUNK.match(ham_satir)
            if hunk:
                satir = int(hunk.group(3))  # YENİ dosyanın başlangıç satırı
                hunk_ici = True
            continue  # index/mode/similarity/Binary files: içerik değil
        if _DIFF_BINAR.match(ham_satir):
            continue
        if ham_satir.startswith("+"):  # eklenen satır
            no = satir
            satir = None if satir is None else satir + 1
            if dosya is None:
                continue  # dosya çözülemedi: yanlış dosyaya bağlamaktansa atla
            bulgular.extend(satiri_tara(ham_satir[1:], dosya=dosya, commit=commit, line=no))
        elif ham_satir.startswith("-"):  # silinen satır: yeni dosyada yok
            continue
        elif ham_satir.startswith(" "):  # bağlam satırı
            satir = None if satir is None else satir + 1
        # `\ No newline at end of file` ve diğerleri yok sayılır
    return bulgular


def tara_gecmis(repo: Path, *, commit_sayisi: int = 500, timeout: int = 120) -> list[dict[str, Any]]:
    r"""`git log -p -U0` çıktısındaki EKLENEN (`+`) satırları tarar.

    `core.quotepath=false` geçici olarak geçerli kılınır: Türkçe/emoji içeren
    yollar tırnaklı-sekizli biçimde gelmesin diye. Yine de tırnaklı biçim
    çözülür (içinde `"`/`\`/TAB olan yollar her zaman tırnaklıdır).
    """
    ham = _git(
        [
            "log", "-p", "-U0", "--no-color", "--no-ext-diff",
            "-n", str(max(0, commit_sayisi)),
            GECMIS_LOG_BICIM,
        ],
        repo, timeout, izinli=frozenset({"log"}),
        ek_config={"core.quotepath": "false"},
        # 128 = "hic commit yok" (bos depo): hata degil, bulgu da yok.
        tolere_hatalar=frozenset({128}),
    )
    metin = ham.decode("utf-8", "replace")
    parcalar = GECMIS_AYRAC_DESENI.split(metin)
    bulgular: list[dict[str, Any]] = []
    for i in range(1, len(parcalar) - 1, 2):
        bulgular.extend(_gecmis_govdesi(parcalar[i + 1], parcalar[i]))
    return bulgular


# --------------------------------------------------------------------------
# Yüksek seviye
# --------------------------------------------------------------------------

class RepoTarama(NamedTuple):
    repo: str
    bulgular: list[dict[str, Any]]
    uyarilar: list[str]


def tara_repo(repo: Path, *, commit_sayisi: int = 500, timeout: int = 60) -> RepoTarama:
    """Tek repo: çalışma ağacı + geçmiş. Hata olursa `GitError` fırlatır."""
    baslangic = time.monotonic()
    bulgular = tara_calisma_agaci(repo, timeout=timeout)
    bulgular.extend(tara_gecmis(repo, commit_sayisi=commit_sayisi, timeout=timeout))
    uyarilar: list[str] = []
    sure = time.monotonic() - baslangic
    if sure > REPO_SURE_UST_SINIR:
        uyarilar.append(f"kismi tarama: repo {sure:.0f} sn (ust sinir {REPO_SURE_UST_SINIR:.0f} sn)")
    return RepoTarama(repo=str(repo), bulgular=bulgular, uyarilar=uyarilar)


def tara_roots(
    roots: Iterable[Path], *, commit_sayisi: int = 500, depth: int = 3
) -> tuple[dict[str, list[dict[str, Any]]], list[tuple[Path, str]]]:
    """(repo -> bulgular, hatalar). Hatalı repo taramayı çökertmez."""
    sonuc: dict[str, list[dict[str, Any]]] = {}
    hatalar: list[tuple[Path, str]] = []
    for repo in find_repo_paths(roots, depth=depth):
        try:
            tarama = tara_repo(repo, commit_sayisi=commit_sayisi)
        except GitError as exc:
            hatalar.append((repo, str(exc)))
            continue
        except Exception as exc:  # beklenmeyen: taramayı çökertme
            hatalar.append((repo, type(exc).__name__))
            continue
        sonuc[tarama.repo] = tarama.bulgular
    return sonuc, hatalar