"""Tarama: calisma agacindaki dosyalarda gizli anahtar SPAN'larini bulur.

Tespit desenleri ve parmak izi `anahtarlik` paketinden ICE AKTARILIR
(`anahtarlik.desen`, `anahtarlik.parmak`) -- mantik KOPYALANMAZ. `desen.satir_tara`
yalniz turun ADINI dondurur; maskelemede span gerektigi icin `desen.TUR_SARASI`
ayni sirayla (daha ozel desen once) taranir ve `finditer` ile bas/son konumlari
alinir. Bu, maske'ye ait ince bir kabuktur: anahtarlik klasorune DOKUNULMAZ.

HAMLIK KURALI: bulgu kaydi ({repo, dosya, satir, tur, ad, izi}) bir sir TASIYAMAZ.
Eslestirilen deger kayda girmez, parmak izine ozetlenip hemen birakilir; degeri
maskelemek gereken `maskele.py` dosyayi YENIDEN okuyup ayni span'i kendisi
turetiyor (rapor yolu fiziksel olarak deger tasiyamaz).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Iterator

from anahtarlik import desen, parmak

from . import tuz as tuz_mod
from .kesif import ATLANAN

#: Bu boyuttan buyuk dosyalar okunmaz (uretimde yazilan dev dosyalar).
AZAMI_DOSYA = 1024 * 1024  # 1 MB

#: Ornek/uygulama dosyalari HEDEF DISIDIR: `*.example`, `test_*`, `tests/`.
#: Bunlarin icindeki "sir" genelde sahte bir ornek degerdir; maskelemek
#: ornegi bozar ve gercek bir bulgu degildir.
_ORNEK_EKI = (".example", ".sample", ".template")
#: Dosya adinin basindaki test oneki: `test_x.py`, `test_x.js` ...
_TEST_ONEKI = ("test_",)
#: Dizin adi: `tests/`, `test/` (her seviyede).
_TEST_DIZIN = frozenset({"tests", "test"})

#: Acikca sahte isaretli deger: AWS dokuman ornegindeki `AKIA...EXAMPLE` gibi.
#: Saglayici desenleri yer tutucu filtresi kullanmaz; bu satirlar elenir.
_SAHTE_ISARET = re.compile(r"(?i)EXAMPLE|xxx+|changeme|dummy|redacted")


def dosya_kapsam_disi(dosya: Path, repo: Path) -> str | None:
    """Dosya tarama hedefi DEGILSE nedenini dondurur, hedefse `None`.

    Uc kural birlikte: ornek dosya ekleri, `test_` oneki, `tests/` dizini.
    """
    try:
        parcalar = dosya.relative_to(repo).parts
    except ValueError:
        parcalar = dosya.parts
    ad = parcalar[-1].lower()
    if any(ad.endswith(ek) for ek in _ORNEK_EKI):
        return "ornek-dosya"
    if any(ad.startswith(onek) for onek in _TEST_ONEKI):
        return "test-dosyasi"
    if any(parca.lower() in _TEST_DIZIN for parca in parcalar[:-1]):
        return "tests-dizini"
    return None


def _sahte_mi(metin: str) -> bool:
    """Eslesme `EXAMPLE`/`xxxx`/`changeme` gibi acikca sahte isaretli mi?"""
    return bool(_SAHTE_ISARET.search(metin))


#: Eslesmenin SOLUNDA aranan etiket: `token = "sk-..."` -> `token`.
#: Etiket DEGERIN ONCESI gelir; eslesmenin kendisi (saglayici desenlerinde
#: degerin kendisi) ASLA ad olarak kullanilmaz.
_ETIKET_DESENI = re.compile(r"([A-Za-z][A-Za-z0-9_-]{0,39})[\"']?\s*[:=]\s*[\"']?\s*$")


def _ad_cikar(oncesi: str, tur: str) -> str:
    """Rotasyon listesi icin anahtarin ADI (deger ASLA).

    `API_KEY=...` gibi satirlarda etiket eslesmenin SOLUNDAN alinir. Saglayici
    desenlerinde (aws, jwt, sk- ...) etiket yoktur: turun adi kullanilir.

    Iki savunma: (1) kaynak yalnizca eslesme ONCESI bolgedir, deger hicbir
    zaman ad olamaz; (2) etiket kendisi bir sira benziyorsa (`AKIA...=...`)
    reddedilir -- boyle bir etiket zaten sirdir, gosterilmez.
    """
    eslesme = _ETIKET_DESENI.search(oncesi)
    if eslesme:
        ad = eslesme.group(1)
        if desen.satir_tara(ad) is None:  # etiket kendisi sira benzemiyor
            return ad
    return tur


def _satir_sonu_bul(ham: str, bas: int) -> str | None:
    """`bas` konumundaki satirin sonlanma bicimi (`\\r\\n`, `\\n`, `\\r` veya bos)."""
    kalan = ham[bas:]
    if kalan.startswith("\r\n"):
        return "\r\n"
    if kalan[:1] in ("\n", "\r"):
        return kalan[:1]
    return ""


def _cakisir(bas: int, bitis: int, kabul: list[tuple[int, int]]) -> bool:
    """Yeni span, kabul edilmis bir spanla BINIYOR mu? (cift maskeleme olmaz)"""
    return any(bas < kabul_bit and kabul_bas < bitis for kabul_bas, kabul_bit in kabul)


def eslesmeler(satir_ham: str) -> list[tuple[int, int, str, str]]:
    """TEK satirda gizli anahtar span'larini dondurur: (bas, bitis, tur, ad).

    `anahtarlik.desen.TUR_SARASI` sirasiyla turler; daha ozel desen ONCE
    denendigi icin cakisan spanlarda ozel olan sahibi olur (`token = "sk-..."`
    satirinda `sk-anahtari` kazanir, `anahtar-deger` elenir).

    Cakisma denetimi TEK bir imlec degil, KABUL EDILEN SPAN LISTESI uzerinden
    yapilir: desenler ozellige gore, eslesmeleri ise metindeki konuma gore
    sirali gelir. Tek imlec, soldaki bir eslesmeyi sagdaki bir eslesmeyle
    yanlisligina silerdi.

    Ham satir buraya girer ve DEGER olarak GERI DONMEZ: donen tur ust sadece
    konum ve etikettir.
    """
    if not satir_ham or "\x00" in satir_ham:
        return []
    ham = satir_ham[: desen.SATIR_UST_SINIR]
    bulunan: list[tuple[int, int, str, str]] = []
    kabul: list[tuple[int, int]] = []
    for tur, kalip, suzgec in desen.TUR_SARASI:
        for eslesme in kalip.finditer(ham):
            bas, bitis = eslesme.start(), eslesme.end()
            if _cakisir(bas, bitis, kabul):
                continue  # daha ozel bir desen bu araligi zaten sahiplendi
            if suzgec is not None and not suzgec(eslesme):
                continue
            if _sahte_mi(eslesme.group(0)):
                continue
            kabul.append((bas, bitis))
            bulunan.append((bas, bitis, tur, _ad_cikar(ham[:bas], tur)))
    bulunan.sort(key=lambda b: b[0])  # maskelemede konum sirasiyla islenir
    return bulunan


def _okunabilir_satirlar(icerik: bytes) -> list[str] | None:
    """BOM'suz metni satirlara boler; son satir sonu OLMADAN saklanir (ayni yerine doner).

    `newline=""` mantigi burada elle kurulur: satir sonu HICBIR ZAMAN yeniden
    uretilmez, `satir_sonu` alani aynen saklanir. Boylece CRLF dosya bayt bayt
    korunur.
    """
    if b"\x00" in icerik:
        return None  # ikili dosya
    try:
        metin = icerik.decode("utf-8")
    except UnicodeDecodeError:
        return None  # metin degil
    return metin.splitlines(keepends=True)


def _govde_satir(satir: str) -> tuple[str, str]:
    """Satiri (govde, satir_sonu) olarak ayirir; satir sonu AYNEN doner."""
    ham = satir
    for son in ("\r\n", "\n", "\r"):
        if ham.endswith(son):
            return ham[: -len(son)], son
    return ham, ""


def dosya_tara(repo: Path, dosya: Path, atlanan: list[str]) -> list[dict]:
    """Tek dosyada bulgulari dondurur (rapor kaydi; deger YOK)."""
    try:
        boyut = dosya.stat().st_size
    except OSError as exc:
        atlanan.append(f"{dosya}: okunamadi ({exc.strerror or exc})")
        return []
    if boyut > AZAMI_DOSYA:
        atlanan.append(f"{dosya}: 1 MB'den buyuk ({boyut} bayt), atlandi")
        return []
    try:
        icerik = dosya.read_bytes()
    except OSError as exc:
        atlanan.append(f"{dosya}: okunamadi ({exc.strerror or exc})")
        return []
    satirlar = _okunabilir_satirlar(icerik)
    if satirlar is None:
        return []  # ikili: sessizce gec (her dosya rapora girmez)

    goreli = _goreli(dosya, repo)
    bulgular: list[dict] = []
    for numara, satir in enumerate(satirlar, start=1):
        govde, _son = _govde_satir(satir)
        for bas, bitis, tur, ad in eslesmeler(govde):
            bulgular.append(
                {
                    "repo": str(repo),
                    "dosya": goreli,
                    "satir": numara,
                    "tur": tur,
                    "ad": ad,
                    # --- ham deger yasam alani: yalniz burada, ozetlenip birakiliyor ---
                    # Her turun EN KISA eslesmesi 15 karakterden uzundur (bkz.
                    # `test_en_kisa_span_iz_alir`), `parmak.izi` ise 8'den kisa
                    # degerde None doner: burada iz HER ZAMAN uretilir.
                    "izi": parmak.izi(govde[bas:bitis]),
                    # --------------------------------------------------------------------
                }
            )
    return bulgular


def _goreli(dosya: Path, repo: Path) -> str:
    try:
        return dosya.relative_to(repo).as_posix()
    except ValueError:
        return dosya.as_posix()  # repo disi: goreli hesaplanamaz


def _dosyalar(repo: Path) -> Iterator[Path]:
    """Repodaki calisma agaci dosyalari (baglanti izlenmez, derinlik sinirli)."""
    for mevcut, dizinler, dosyalar in os.walk(
        repo, topdown=True, followlinks=False, onerror=lambda _e: None
    ):
        kok = Path(mevcut)
        # `.git` ve dev klasorler ATLANAN kumesinde: hicbirine girilmez.
        dizinler[:] = sorted(d for d in dizinler if d not in ATLANAN)
        for ad in dosyalar:
            yol = kok / ad
            if yol.is_symlink():
                continue  # bagli dosyaya yazmayiz
            yield yol


def tara(repolar: list[Path]) -> dict:
    """Verilen repolari tarar; rapor govdesi doner (dosya sistemi DEGISTIRILMEZ).

    Govde: {"bulgar": [{repo, dosya, satir, tur, ad, izi}], "atlanan": [...],
            "dosya": taranan dosya sayisi}
    """
    tuz_mod.hazirla()  # tuzu kullanici veri dizinine yonlendir (repo ici ASLA)
    atlanan: list[str] = []
    bulgar: list[dict] = []
    sayilan = 0
    for repo in map(Path, repolar):
        for dosya in _dosyalar(repo):
            if dosya_kapsam_disi(dosya, repo):
                continue
            sayilan += 1
            bulgar.extend(dosya_tara(repo, dosya, atlanan))
    return {
        "bulgar": sorted(bulgar, key=lambda b: (b["repo"], b["dosya"], b["satir"])),
        "atlanan": atlanan,
        "dosya": sayilan,
    }