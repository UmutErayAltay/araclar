"""Gizli gorunen ortam degiskenlerini tespit eder ve degerlerini maskeler."""

from __future__ import annotations

DESENLER = ("KEY", "TOKEN", "SECRET", "PASSWORD", "PASSWD", "PASS", "PWD",
            "CREDENTIAL", "AUTH", "PRIVATE")

_PWD_ISTISNA = {"PWD", "OLDPWD"}
_MASKE = "•" * 8  # sabit uzunluk: deger uzunlugu da sizmaz


def gizli_mi(ad: str) -> bool:
    """Ad, gizli olabilecek bir desen iceriyorsa True (buyuk harf alt dizge eslesmesi)."""
    ust = ad.upper()
    if ust in _PWD_ISTISNA:
        return False
    return any(desen in ust for desen in DESENLER)


def maskele(metin: str) -> str:
    """Degeri gosterilmeyecek bicimde maskeler. Bos deger bos kalir."""
    return "" if metin == "" else _MASKE
