"""Giriş doğrulama (bağlayıcı güvenlik kuralı).

Ajanlara verilen görev metni `.env`/anahtar içeremez; reddedilen istem hata
mesajına ASLA aynen yansımaz.
"""

from __future__ import annotations

import re

from .models import GecersizGirdi

ISTEM_EN_FAZLA = 20_000
AJAN_DESENI = re.compile(r"^[a-z0-9][a-z0-9-]*$")

GIZLI_DESENLERI: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    ("api anahtari", "sk- ile baslayan anahtar", re.compile(r"sk-[A-Za-z0-9_-]{20,}")),
    ("aws erisim anahtari", "AKIA... anahtari", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("ozel anahtar", "BEGIN PRIVATE KEY blogu", re.compile(r"-----BEGIN .*PRIVATE KEY-----")),
    ("env dosyasi", ".env dosya adi", re.compile(r"(^|[\s/\\])\.env(\.|\s|$)", re.MULTILINE)),
    (
        "sifre/anahtar atamasi",
        "api_key/token/secret/password = ... atamasi",
        re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[=:]\s*\S{8,}"),
    ),
    (
        "anahtar degeri",
        "anahtar/token adinin ardindan 8+ karakterlik deger",
        re.compile(
            r"(?i)\b(api[_-]?key|token|secret|password|bearer)\b[\"']?\s*[:=]\s*"
            r"[\"']?[A-Za-z0-9/+._~_-]{8,}"
        ),
    ),
)

MASKE = "[maskeli]"


def maskele(metin: str) -> str:
    """Metindeki gizli kalıpları maskeler (kısmi sırı bile sızdırmaz)."""
    sonuc = metin
    for _ad, _aciklama, desen in GIZLI_DESENLERI:
        sonuc = desen.sub(MASKE, sonuc)
    return sonuc


def ajan_gecerli(ajan: str) -> bool:
    return bool(isinstance(ajan, str) and AJAN_DESENI.match(ajan))


def istem_uyari(istem: str) -> list[str]:
    """Temizlenmesi gereken kalıpların açıklamaları; temiz metinde boş liste."""
    if not isinstance(istem, str):
        return ["istem metin degil"]
    return gizli_desen_ara(istem)


def gizli_desen_ara(metin: str) -> list[str]:
    """`guard` içinde de kullanılabilen kolay eşleştirici (bulunan desen adları)."""
    return [aciklama for ad, aciklama, desen in GIZLI_DESENLERI if desen.search(metin)]


def istem_kontrol(istem: str) -> None:
    if not isinstance(istem, str) or not istem.strip():
        raise GecersizGirdi("istem bos olamaz")
    if len(istem) > ISTEM_EN_FAZLA:
        raise GecersizGirdi(
            f"istem cok uzun ({len(istem)} karakter, en fazla {ISTEM_EN_FAZLA})"
        )
    uyarilar = gizli_desen_ara(istem)
    if uyarilar:
        # Reddedilen istem ASLA aynen yansitilmaz.
        raise GecersizGirdi(
            "istemde gizli bilgi kalibi reddedildi: " + ", ".join(uyarilar)
        )


def girdi_kontrol(ajan: str, istem: str) -> None:
    if not ajan_gecerli(ajan):
        raise GecersizGirdi("gecersiz ajan adi")
    istem_kontrol(istem)


def cikti_goster(metin: str | None) -> str:
    """Kullanıcıya gösterilecek metni maskeler (CLI çıktısı için)."""
    return "" if metin is None else maskele(metin)