"""Gizli gorunen ortam degiskenlerini tespit eder ve degerlerini maskeler."""

from __future__ import annotations

import re

DESENLER = ("KEY", "TOKEN", "SECRET", "PASSWORD", "PASSWD", "PASS", "PWD",
            "CREDENTIAL", "AUTH", "PRIVATE",
            "URL", "DSN", "CONNECTION", "COOKIE", "SIGNATURE", "SESSION", "BEARER")
SONEKLER = ("_PAT",)

_PWD_ISTISNA = {"PWD", "OLDPWD"}
_MASKE = "•" * 8  # sabit uzunluk: deger uzunlugu da sizmaz
# Kullanici:parola@ bicimli URL kimligi (ornek: https://kullanici:parola@sunucu/yol)
_URL_KIMLIK = re.compile(r"://[^/\s:@]+:[^@\s]+@")


def kimlik_iceriyor(metin: str) -> bool:
    """Deger, URL icinde kullanici:parola bilgisi tasiyor mu?"""
    return _URL_KIMLIK.search(metin) is not None


def gizli_mi(ad: str, metin: str | None = None) -> bool:
    """Ad gizli bir desen iceriyorsa ya da (verilirse) deger URL kimligi tasiyorsa True.

    PWD ve OLDPWD her iki denetimden de muaftir.
    """
    ust = ad.upper()
    if ust in _PWD_ISTISNA:
        return False
    if any(desen in ust for desen in DESENLER) or ust.endswith(SONEKLER):
        return True
    return metin is not None and kimlik_iceriyor(metin)


def maskele(metin: str) -> str:
    """Degeri gosterilmeyecek bicimde maskeler. Bos deger bos kalir."""
    return "" if metin == "" else _MASKE
