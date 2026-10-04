"""Parmak izi: degeri gostermeden tanimayan ozet.

Tuz makine-yereldir (`ANAHTARLIK_DIR/tuz`, varsayilan `~/.anahtarlik/tuz`).
Tuz olmadikca iki kurulum ayni deger icin AYNI izi verir; tuz olan ikisi farkli
izi verir. Bu, "envanteri bir baska yere gonderdim" durumunda karsi tarafin
dogrudan karsilastirma yapmasini engeller.

KISA DEGER (<8 karakter) ve BOS deger icin `izi` None doner: kisa bir deger
tuzla bile kaba kuvvetle bulunur (8 karakterlik alfabe dar). `envanter.py` bunu
`kisa` etiketiyle envanterde gosterir.
"""

from __future__ import annotations

import hashlib
import os
import secrets
from pathlib import Path

#: Tuz dosyasinin adi (ANAHTARLIK_DIR altinda).
TUZ_ADI = "tuz"

#: Izin verilen en kisa deger (kaba kuvvet altinda guvenli sayilmaz).
ASGARI_UZUNLUK = 8

#: Parmak izi uzunlugu (hex karakter).
IZI_UZUNLUK = 8

#: Tuzun kabul edilen en kisa uzunlugu. `IZI_UZUNLUK` hex karakteri (32 bit)
#: icin tuzlu kaba kuvveti kirilmaz olmak icin tuz en az 16 bayt olmali.
#: 1 baytlik tuz kabul edilirse 256 denemede cozulur (test: `parmak`).
ASGARI_TUZ = 16

#: Uretilen tuzun bayt uzunlugu.
TUZ_UZUNLUK = 32


def dizin() -> Path:
    """ANAHTARLIK_DIR varsa o, yoksa ~/.anahtarlik (goreli yol mutlaklastirilir)."""
    yol = Path(os.environ.get("ANAHTARLIK_DIR") or (Path.home() / ".anahtarlik")).expanduser()
    return yol.resolve() if not yol.is_absolute() else yol


def _tuz_uret_ve_yaz(yol: Path, yalniz_olustur: bool) -> bytes:
    """Tuzu uretip dosyaya yazar; **dosyada ne varsa onu dondurur**.

    `yalniz_olustur=True` -> `O_CREAT|O_EXCL`: dosya varsa `FileExistsError`,
    yani ilk KACAN surec yazar ve yaris penceresi kapanir.
    `yalniz_olustur=False` -> `O_TRUNC`: BOZUK/kisa bir tuz dosyasini ONARMAK
    icin (bu yol yalnizca dosya zaten gecersizse calisir).
    """
    bayraklar = os.O_WRONLY | os.O_CREAT | (os.O_EXCL if yalniz_olustur else os.O_TRUNC)
    fd = os.open(yol, bayraklar, 0o600)
    try:
        with os.fdopen(fd, "wb") as akim:
            akim.write(secrets.token_bytes(TUZ_UZUNLUK))
    except BaseException:
        if yalniz_olustur:  # yarim dosya kalmasin (O_TRUNC'da eski dosya zaten gitti)
            Path(yol).unlink(missing_ok=True)
        raise
    return yol.read_bytes()


def tuz() -> bytes:
    """Makine-yerel tuzu okur; yoksa uretip dosyaya yazar (0o600, atomik).

    Yarisma onlemi: dosya ONCE `O_EXCL` ile OLUSTURULUR. Iki es zamanli surec
    (orn. biri push hook'u, biri `tara`) ayni anda tuz uretmeye kalkarsa
    YALNIZCA BIRi kazanir; kaybeden diskteki tuzu okur. Boylece herkes ayni
    tuzdan (ayni parmak izinden) konusur.

    Dosya ZATEN varsa ama bozuk/kisa ise onarilir; bu yol cok nadirdir (dosya
    yalnizca bozulunca gecersizdir) ve onarim da ayni dosyayi paylasan herkesi
    ayni tuza baglar.

    Okuma/yazma hatasinda gecici bir tuz uretilir: tarama calismaya devam eder,
    ama parmak izleri bu calisma icin tutarsiz olabilir (dogrusu da budur).
    """
    yol = dizin() / TUZ_ADI
    bozuk = False
    try:
        mevcut = yol.read_bytes()
        if len(mevcut) >= ASGARI_TUZ:
            return mevcut
        bozuk = True  # var ama gecersiz: onarilacak
    except OSError:
        pass  # yok ya da okunamadi: yenisi uretilir

    try:
        yol.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return secrets.token_bytes(TUZ_UZUNLUK)  # yazilamadi: gecici tuz

    try:
        # Dosya yoksa yaris KAZANAN olabilirdi (iki surec iki tuz yazar):
        # `O_EXCL` ile yalnizca ilk kacan yazar. Dosya BOZUKSA onarmak sart.
        return _tuz_uret_ve_yaz(yol, yalniz_olustur=not bozuk)
    except FileExistsError:
        pass  # kaybettik: kazananin tuzunu kullan
    except OSError:
        return secrets.token_bytes(TUZ_UZUNLUK)  # yazilamadi: gecici tuz

    try:
        diskteki = yol.read_bytes()
        if len(diskteki) >= ASGARI_TUZ:
            return diskteki
    except OSError:
        pass
    return secrets.token_bytes(TUZ_UZUNLUK)


def izi(deger: str) -> str | None:
    """`deger` icin tuzlu sha256 ozeti (ilk 8 hex karakter).

    Bos veya 8 karakterden kisa deger icin None doner (tuzlu kaba kuvvet riski).
    """
    if not deger or len(deger) < ASGARI_UZUNLUK:
        return None
    # surrogateescape: .env utf-8 DEGILSE de baytlar aynen geri gider, iz kararli kalir.
    ozet = hashlib.sha256(tuz() + deger.encode("utf-8", "surrogateescape")).hexdigest()
    return ozet[:IZI_UZUNLUK]