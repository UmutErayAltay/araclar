"""Denetim 4 -- `gecmis_secret`: repoda gizli anahtar izi var mi?

`git log -p --all` ciktisi AKIS olarak okunur (satir satir): butun patch bellege
ALINMAZ. Limitler: 200000 satir ya da 20 saniye; biri asilirsa tarama kesilir ve
"KISMI TARAMA" uyarisi dusulur.

Guvenlik (baglayici): HAM DEGER HICBIR YERE CIKMAZ. Rapor satiri yalniz su
alanlari tasir: commit kisaltilmis hash'i, dosya yolu, tur ve tuzlu parmak izi.
Span, tanimlanan yasam alaninda ozetlenip HEMEN BIRAKILIR; ne rapora girer,
ne istisna mesajina, ne de test ciktisina.

Tespit desenleri `anahtarlik.desen`'den ICE AKTARILIR (bkz. `mezar/__init__.py`).
Ornek/test dosyalari atlanir: `test_` oneki, `tests/` dizini, `.example` ve
`EXAMPLE` isaretliler -- bunlar gosterim icindir, sizmis sayilmaz.
"""

from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path
from typing import Iterator

from anahtarlik import desen, parmak

#: Tarama ust sinirlari. Asilirsa tarama KISMIDIR ve karar DIKKAT'a duser:
#: "tarama bitmedi" demek "sir yok" demek DEGILDIR.
SATIR_LIMITI = 200_000
SURE_LIMITI = 20.0

#: Ornek/uygulama dosyalari: bunlar gosterim icindir, sizmis sayilmaz.
_ORNEK_EKI = (".example", ".sample", ".template")
_TEST_ONEKI = "test_"

#: `git log -p` basligi: `commit <40-hex>` (veya kisaltilmis hash).
_COMIT_BASI = re.compile(r"^commit ([0-9a-f]{7,40})\b")

#: Satir sonu ve ORIJINALIN SOLUNDA gosterilen dosya yolu: `+++ b/<yol>`.
_DOSYA_BASI = re.compile(r"^\+\+\+ (?:b/)?(.+?)(?:\t.*)?$")


def ornek_dosya_mi(dosya: str) -> bool:
    """Ornek/test dosyasi mi? (kisa devre: `git log` cok dosya verir)."""
    kucuk = dosya.lower()
    parcalar = kucuk.split("/")
    if "tests" in parcalar[:-1]:
        return True
    ad = parcalar[-1]
    if ad.startswith(_TEST_ONEKI):
        return True
    if any(kucuk.endswith(ek) for ek in _ORNEK_EKI):
        return True
    return "example" in ad or "ornek" in ad


def _satirlar(repo: Path) -> Iterator[str]:
    """`git log -p --all` satirlarini AKIS olarak uretir.

    `text=False` ile bayt alinir ve UTF-8'e COZULMEZ: cozulemeyen bir bayt
    (ikili dosya, bozuk bayt) istisna firlatmasin. Metin `errors="replace"`
    ile modul icinde cozulur; ham bayt hicbir yere tasinmaz.
    """
    proc = subprocess.Popen(
        ["git", "-C", str(repo), "log", "-p", "--all"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    try:
        assert proc.stdout is not None
        for satir_bayt in proc.stdout:  # satir satir: BUYUK DIFF BELLEGE GIRMEZ
            yield satir_bayt.decode("utf-8", "replace")
    finally:
        if proc.stdout is not None:
            proc.stdout.close()
        proc.wait()


def _iz(deger: str) -> str:
    """Tuzlu parmak izi. Kisa degerde `kisa` etiketi uretilir.

    `desen.TUR_SARASI` desenleri 15+ karakter eslestirir, bu yuzden iz burada
    her zaman uretilir; yine de `parmak.izi` None donerse `kisa` yazilir ve
    DEGER HICBIR YERDE gorunmez.
    """
    return parmak.izi(deger) or "kisa"


def tara(repo: Path, *, satir_limiti: int = SATIR_LIMITI, sure_limiti: float = SURE_LIMITI) -> dict:
    """Gecmisi tarar; bulgulari ve tarama durumunu doner.

    Donen sozluk: {"bulundu": [...], "kismi": bool, "taranan_satir": int,
    "sure": float, "not": str | None}. Her bulgu: {"commit", "dosya", "tur", "izi"}.
    """
    bulundu: list[dict] = []
    gorulen: set[tuple[str, str, str]] = set()
    commit = ""
    dosya = ""
    sayac = 0
    baslangic = time.monotonic()
    kesildi = None

    for satir in _satirlar(repo):
        sayac += 1
        if sayac > satir_limiti:
            kesildi = f"satir siniri ({satir_limiti}) asildi"
            break
        if sayac % 512 == 0 and time.monotonic() - baslangic > sure_limiti:
            kesildi = f"sure siniri ({sure_limiti:.0f} sn) asildi"
            break

        satir = satir.rstrip("\n")
        eslesme = _COMIT_BASI.match(satir)
        if eslesme:
            commit = eslesme.group(1)[:8]
            continue
        eslesme = _DOSYA_BASI.match(satir)
        if eslesme and eslesme.group(1) != "/dev/null":
            dosya = desen.temiz_yol(eslesme.group(1).strip())
            continue
        # diff'in SADECE eklenen satirlari (`+`, `+++` haric) taranir: silinen
        # kod icinde gizli anahtar YOKTUR, olmus sayilamaz.
        if not satir.startswith("+") or satir.startswith("+++"):
            continue
        if dosya and ornek_dosya_mi(dosya):
            continue

        govde = satir[1:]
        tur = desen.satir_tara(govde)
        if tur is None:
            continue
        # --- ham degerin yasam alani: yalniz burada, ozetlenip birakiliyor ---
        izi = _iz(_eslesen_span(govde, tur))
        # -----------------------------------------------------------------------
        anahtar = (commit, dosya, tur)
        if anahtar in gorulen:  # ayni dosya+tur commit basina bir kez sayilir
            continue
        gorulen.add(anahtar)
        bulundu.append({"commit": commit, "dosya": dosya, "tur": tur, "izi": izi})

    sure = time.monotonic() - baslangic
    return {
        "bulundu": bulundu,
        "kismi": kesildi is not None,
        "taranan_satir": min(sayac, satir_limiti),
        "sure": sure,
        "not": f"kismi tarama: {kesildi} (tarama tamamlanmadi)" if kesildi else None,
    }


def _eslesen_span(govde: str, tur: str) -> str:
    """Bulgu turunun ilk eslesmesini dondurur -- parmak izi bu metinden uretilir.

    Donen metin ASLA ciktida gorunmez; `gecmis.bulundu` yalniz `izi` tasir.
    """
    for ad, kalip, suzgec in desen.TUR_SARASI:
        if ad != tur:
            continue
        for eslesme in kalip.finditer(govde[: desen.SATIR_UST_SINIR]):
            if suzgec is None or suzgec(eslesme):
                return eslesme.group(0)
        return govde
    return govde