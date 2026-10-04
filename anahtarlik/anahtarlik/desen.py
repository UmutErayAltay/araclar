"""Satir duzeyinde gizli anahtar TESPITI.

Desenler `atlas.atlas.leaks` dosyasindan KOPYALANMISTIR (import edilmez:
anahtarlik'in atlas'a bagimliligi olmamalidir, "iki tuketici" kurali).

BAYAT KURALI: HAM SIR HICBIR YERE CIKMAZ. Bu modulun tek cikti noktasi
`onizleme(tur)` fonksiyonudur ve o da yalnizca `[maskeli:<tur>]` uretir.
Ham satir buraya GIRER, tasinabilir bir metin olarak CIKMAZ.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any, Callable

__all__ = ["satir_tara", "onizleme", "TUR_SIRASI", "YER_TUTUCU_DESENI", "temiz_yol"]


#: `anahtar = <deger>` deseninde deger yer tutucu ise bulgu DEGILDIR.
#: `process.env.X` / `os.environ[...]` gibi KOD referanslari da yer tutucudur:
#: bunlar sir DEGILDIR, degisken okunur. Atlas'tan birebir kopyalandi.
YER_TUTUCU_DESENI = re.compile(
    r"x{3,}|<[^>]*>|\$\{[^}]*\}|\$[A-Z_][A-Z0-9_]*|your[_-]|"
    r"example|placeholder|changeme|dummy|sample|redacted|"
    r"todo|none|null|insert|replace|test|demo|asdf|foo|bar|"
    r"abc123|123456|passwd|password|"
    r"process\.env|os\.environ|getenv|ENV\[|env\[|os\.get",
    re.IGNORECASE,
)

#: Ham satir BASTAN kesilmez: kesmek, satirin sonundaki sirleri gizlerdi.
#: Bu deger yalnizca TEORIK bir guvenlik tavani (diff ciktisi denetimsiz buyuyebilir).
SATIR_UST_SINIR = 200_000


# --------------------------------------------------------------------------
# Tespit desenleri (atlas'tan kopyalandi)
# --------------------------------------------------------------------------

_DESEN_SK = re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{20,}")
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
#: `api_key = <deger>`: deger tirnak icinde ya da tirnaksiz; deger sonrasi
#: imle satirlayici gelmemeli. `apiKey = resolveKey(config)` bir fonksiyon
#: CAGRISI degil gecici bir degerdir: bu yuzden `(?![A-Za-z0-9_$])` ve
#: `(?!\s*\()` eklenir.
_DESEN_ANAHTAR_DEGER = re.compile(
    r"(?i)\b(api[_-]?key|secret|token|password|passwd)\b[\"']?\s*[:=]\s*"
    r"[\"']?[A-Za-z0-9/+_.~-]{16,}[\"']?(?![A-Za-z0-9_$])(?!\s*\()"
)
#: ETIKETLI DEGER: etiket ile `:=` arasinda en cok 40 karakter olabilir.
_DESEN_ETIKETLI_DEGER = re.compile(
    r"(?i)\b(api[ _-]?key|apikey|credential|secret|token|passwd|password)\b"
    r"[^\n:=]{0,40}[:=]\s*[\"']?(?P<deger>[A-Za-z0-9_\-/+.=~]{24,})"
    r"[\"']?(?![A-Za-z0-9_$])(?!\s*\()"
)
_DESEN_OZEL_ANAHTAR = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY")


# --------------------------------------------------------------------------
# Suzgecler
# --------------------------------------------------------------------------


def _rakam_var(eslesme: re.Match) -> bool:
    """`sk-` eslesmesinde en az BIR rakam olmali.

    Kebab-case kelimeleri (`flask-`, `task-`, `risk-`) eler.
    """
    return any(k.isdigit() for k in eslesme.group(0))


def _rakamli(eslesme: re.Match) -> bool:
    """Etiketli degerin KENDISI en az bir rakam icermeli (`deger` grubu)."""
    deger = eslesme.groupdict().get("deger")
    if deger is None:
        deger = eslesme.group(0)
    return any(k.isdigit() for k in deger)


def _yer_tutucu_değil(eslesme: re.Match) -> bool:
    return not YER_TUTUCU_DESENI.search(eslesme.group(0))


def _anahtar_deger_gibi(eslesme: re.Match) -> bool:
    """`anahtar = deger` eslesmesi gercek bir anahtara BENZIYOR mu?

    Sozluk/gunluk metinlerinde `Token: <sozcuk>` siklikla gecer. Gercek bir
    sir ya rakam icerir ya buyuk harf karisimidir ya da tirnakli/tireli bir
    bicimdedir; duz kucuk harfli sozcuk dizisi sirdir.
    """
    g = eslesme.group(0)
    deger = g.split("=", 1)[-1].split(":", 1)[-1].strip("\"' ")
    if any(k.isdigit() for k in deger):
        return True
    if any(k.isupper() for k in deger):
        return True
    return bool(re.search(r"[\"']", deger)) or ("-" in deger) or ("_" in deger)


#: (tur, desen, suzgec). `suzgec` `None` ise ek kosul yoktur.
#: SIRA ONEMLIDIR: daha ozel desen once denenir, satir basina ilk tur doner.
TUR_SARASI: tuple[tuple[str, re.Pattern, Callable | None], ...] = (
    ("ozel-anahtar", _DESEN_OZEL_ANAHTAR, None),
    ("sk-anahtari", _DESEN_SK, _rakam_var),
    ("sb-secret", _DESEN_SB_SECRET, None),
    ("aws-anahtari", _DESEN_AWS, None),
    ("github-token", _DESEN_GH, None),
    ("slack-token", _DESEN_SLACK, None),
    ("stripe-anahtari", _DESEN_STRIPE, None),
    ("google-anahtari", _DESEN_GOOGLE, None),
    ("jwt", _DESEN_JWT, None),
    # `sb_publishable_` tasarim geregi herkese aciktir: yine de kayda gider.
    ("sb-publishable", _DESEN_SB_PUBLISHABLE, None),
    (
        "anahtar-deger",
        _DESEN_ANAHTAR_DEGER,
        lambda m: _yer_tutucu_değil(m) and _anahtar_deger_gibi(m),
    ),
    (
        "etiketli-deger",
        _DESEN_ETIKETLI_DEGER,
        lambda m: _yer_tutucu_değil(m) and _rakamli(m),
    ),
)


def onizleme(tur: str) -> str:
    """Bulgu onizlemesi: HAM METIN YOK, yalnizca tur isareti."""
    return f"[maskeli:{tur}]"


def satir_tara(satir: str) -> str | None:
    """TEK satiri tarar; eslesen desen TURU adini dondurur, yoksa `None`.

    Yer tutucu degerler (`xxxx`, `<...>`, `changeme`, `example`), kod
    referanslari (`process.env.X`, `os.environ[...]`) ve kabuk degiskenleri
    (`${VAR}`) bulgu DEGILDIR.

    Ham satir buraya girer ve geri DONMEZ: sonuc yalnizca bir tur adidir.
    """
    if not satir:
        return None
    ham = satir[:SATIR_UST_SINIR]
    if "\x00" in ham:  # "metin" degildir
        return None
    for tur, desen, suzgec in TUR_SARASI:
        for eslesme in desen.finditer(ham):
            if suzgec is not None and not suzgec(eslesme):
                continue
            return tur
    return None


def tur_listesi() -> list[str]:
    """Bilgi amacli: taninan tur adlari."""
    return [tur for tur, _d, _s in TUR_SARASI]


#: `env-dosyasi` bu modulun DEGIL, hook.py'in turudur (dosya yolu bulgusu).
ENV_DOSYASI_TURU = "env-dosyasi"

#: Ornek/şablon dosyalar: `.env.example` gibi adlar Git'in IZLEDIGI `.env`
#: DEGILDIR (atlas'tan kopyalandi).
_ENV_ADI_DESENI = re.compile(r"^\.env(\..+)?$", re.IGNORECASE)
ENV_ADI_ISTISNA = (".example", ".sample", ".template", ".dist", ".defaults")


def env_dosyasi_mi(dosya: str) -> bool:
    """Git'in IZLEDIGI `.env` dosyasi mi? (`.env.example` vb. HAYIR)."""
    ad = PurePosixPath(dosya.replace("\\", "/")).name
    if not _ENV_ADI_DESENI.match(ad):
        return False
    kucuk = ad.lower()
    return not any(kucuk.endswith(ek) for ek in ENV_ADI_ISTISNA)


#: Terminale yazilacak metinden cikarilan KONTROL karakterLERI: ANSI kacis,
#: bell, satir sonu gibi. Bunlar dosya adi olsa bile ekranda komut/cikti
#: taklit edebilir (ORN: `x\x1b[2J` ekrani siler).
_KONTROL = re.compile(r"[\x00-\x1f\x7f]")


def temiz_yol(metin: str) -> str:
    """Dosya adini terminale güvenli yazmak icin: kontrol karakterleri `?`.

    Anahtar degeri degil, dosya yolu; ama o yol da kullanici kontrolunde ve
    ekrana dogrudan yazildigi icin ANSI enjeksiyonu yuzey olmamali.
    Git yollari C-quote ile kaçirdigi icin bu genelde savunma derinligidir.
    """
    return _KONTROL.sub("?", metin)


def bulgu(dosya: str, satir: int, tur: str) -> dict[str, Any]:
    """Tek bulgu sozlugu: dosya, satir, tur ve MASKELENMIS onizleme."""
    return {
        "dosya": temiz_yol(dosya),
        "satir": satir,
        "tur": tur,
        "onizleme": onizleme(tur),
    }