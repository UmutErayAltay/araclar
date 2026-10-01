"""Sızıntı tarayıcısı: gizli anahtar, PII, yerel yol, özel ağ ve dış kaynak tespiti.

Tüm desenler sabittir; çalışma zamanında yapılandırma yoktur. Çıktı: Bulgu listesi,
her bulgu türü ve maskelenmiş örneğiyle. Aynı (tur, ornek) çifti tekilleştirilir.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from collections.abc import Collection


@dataclass(frozen=True, order=True)
class Bulgu:
    """Tek bir sızıntı bulgusu.

    Attributes:
        tur: Bulgunun kategorisi (ör. "api-anahtari", "eposta", "jwt").
        ornek: Maske uygulanmış örnek değer (ilk 4 karakter + "…").
    """
    tur: str
    ornek: str


# Derlenmiş regex desenleri: (tur, regex, ignore_case).
# Büyük/küçük harf duyarsızlık DERLEME anında verilir (`finditer`'in ikinci
# argümanı bayrak değil başlangıç konumudur); aşağıda `_DESENLER` bunu uygular.
_HAM_DESENLER = [
    ("api-anahtari", re.compile(r"sk-[A-Za-z0-9_-]{20,}"), False),
    ("jwt", re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\."), False),
    ("aws", re.compile(r"AKIA[0-9A-Z]{16}"), False),
    ("github-token", re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"), False),
    ("telegram-token", re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{30,}"), False),
    ("ozel-anahtar", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY"), False),
    ("yerel-yol", re.compile(
        r"/home/[A-Za-z]"
        r"|/Users/[A-Za-z]"
        r"|[A-Za-z]:\\Users\\"
        r"|/root/",
    ), False),
    ("eposta", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), True),
    ("ozel-ag", re.compile(
        r"\b(10\.\d+\.\d+\.\d+"
        r"|192\.168\.\d+\.\d+"
        r"|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+)\b"
        r"|(localhost|127\.0\.0\.1):\d+",
    ), False),
    ("dis-kaynak", re.compile(
        r"<script"
        r"|<link\s"
        r"|<iframe"
        r"|@import"
        r"|url\(\s*['\"]?https?:"
        r"|src\s*=\s*['\"]?https?:",
    ), True),
]

_DESENLER = [
    (tur, re.compile(desen.pattern, re.IGNORECASE if ic else 0), ic)
    for tur, desen, ic in _HAM_DESENLER
]


def _maskele(deger: str) -> str:
    """Değeri maskeleyerek ilk 4 karakter + '…' döndürür."""
    if len(deger) <= 4:
        return deger + "…"
    return deger[:4] + "…"


def tara(metin: str, izinli_eposta: Collection[str] = ()) -> list[Bulgu]:
    """Metni tarayıp sızıntı bulgularını döndürür.

    Args:
        metin: Taranacak metin.
        izinli_eposta: Büyük/küçük harf duyarsız olarak göz ardı edilecek e-postalar.

    Returns:
        Metindeki konum sırasına göre sıralanmış, tekilleştirilmiş Bulgu listesi.
    """
    if not metin:
        return []

    izinli_kucuk = {e.lower() for e in izinli_eposta}
    bulunan: list[tuple[int, Bulgu]] = []  # (konum, Bulgu)
    gorulen: set[tuple[str, str]] = set()  # (tur, ornek)

    for tur, pattern, _ in _DESENLER:
        for match in pattern.finditer(metin):
            ornek_ham = match.group(0)
            ornek_maskeli = _maskele(ornek_ham)

            # E-posta için izinli kontrol
            if tur == "eposta" and ornek_ham.lower() in izinli_kucuk:
                continue

            anahtar = (tur, ornek_maskeli)
            if anahtar in gorulen:
                continue

            gorulen.add(anahtar)
            bulunan.append((match.start(), Bulgu(tur=tur, ornek=ornek_maskeli)))

    # Konuma göre sırala
    bulunan.sort(key=lambda x: x[0])
    return [bulgu for _, bulgu in bulunan]