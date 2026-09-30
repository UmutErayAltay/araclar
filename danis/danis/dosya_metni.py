"""Yerel dosyanın (txt/md/pdf/docx) metnini çıkarır.

Neden ayrı modül: hem `danis dosya` CLI'sı hem de testler aynı yönlendirme
mantığını kullansın; PDF/DOCX bağımlılıkları yalnızca burada import edilir,
metin dosyaları stdlib ile açılır.
"""

from __future__ import annotations

from pathlib import Path

MAX_KARAKTER = 12000
KIRPMA_NOTU = "\n\n[... kırpıldı ...]"

# NUL bayt taraması yalnızca bu kadar bayta bakar: pratikte ikili dosyalar
# baştan itibaren NUL içerir, 8 KiB maliyetli bir güvenlik ağı için fazlasıyla
# yeterlidir (dosyanın tamamını diske çıkarmadan karar vermek).
NUL_TARAMA_BOYUTU = 8192

# API.md: "bilinmeyen metin uzantıları → doğrudan oku" AMA "desteklenmeyen
# uzantı (ör. resim) → hata". İkisini birleştiren çözüm: metin olmayan türler
# KESİN olarak listelenip reddedilir, geri kalan her şey metin varsayılır.
# Liste dışı kalanlar (`.blend`, `.dat`, ...) için liste bir ikili garantisi
# DEĞİLDİR: içerik bazlı NUL taraması ikinci güvenlik ağıdır.
_METIN_UZANTILARI = frozenset({".txt", ".md", ".py", ".json", ".csv"})
_METIN_DEGIL_UZANTILARI = frozenset(
    {
        ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff",
        ".ico", ".svgz", ".heic",
        ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
        ".exe", ".dll", ".so", ".dylib", ".bin", ".o", ".a", ".class", ".pyc",
        ".mp3", ".mp4", ".mkv", ".avi", ".wav", ".flac", ".ogg", ".mov",
        ".ttf", ".otf", ".woff", ".woff2", ".eot",
        ".db", ".sqlite", ".sqlite3", ".iso", ".dmg", ".pkl", ".pickle", ".npy",
    }
)


class DosyaHatasi(Exception):
    """Metin çıkarma sırasındaki hataların tabanı."""


class DosyaBulunamadiError(DosyaHatasi):
    """Verilen yol bir dosya değil."""


class DosyaTuruDesteklenmiyorError(DosyaHatasi):
    """Uzantı için metin çıkarma yolu yok (ör. .png)."""


class BosDosyaError(DosyaHatasi):
    """Dosya okundu ama içinde anlamlı metin yok."""


class IkiliDosyaError(DosyaHatasi):
    """Metin sanılan ama içerik ikili (NUL bayt içeren) çıktı."""


def metni_cikar(dosya_yolu: Path) -> str:
    """Uzantıya göre yönlendirir, `MAX_KARAKTER` karaktere kırpır."""
    yol = Path(dosya_yolu)
    if not yol.is_file():
        raise DosyaBulunamadiError(f"Dosya bulunamadı: {yol}")

    uzanti = yol.suffix.lower()
    if uzanti == ".pdf":
        metin = _pdf_metni(yol)
    elif uzanti == ".docx":
        metin = _docx_metni(yol)
    elif uzanti in _METIN_DEGIL_UZANTILARI:
        raise DosyaTuruDesteklenmiyorError(f"desteklenmiyor: {uzanti}")
    else:
        # .txt/.md/.py/.json/.csv ve listelenmemiş metin uzantıları: doğrudan oku.
        metin = _duz_metni(yol)

    metin = _kirp(metin)
    if not metin.strip():
        raise BosDosyaError(f"metin bulunamadı (boş): {yol}")
    return metin


def _kirp(metin: str) -> str:
    if len(metin) <= MAX_KARAKTER:
        return metin
    return metin[:MAX_KARAKTER] + KIRPMA_NOTU


def _duz_metni(yol: Path) -> str:
    ham = yol.read_bytes()
    if b"\x00" in ham[:NUL_TARAMA_BOYUTU]:
        raise IkiliDosyaError(
            f"İkili/okunamayan bir dosya gibi görünüyor (NUL bayt içeriyor): {yol}"
        )
    # UTF-8, okunamayan baytlar `errors="replace"` ile değiştirilir.
    return ham.decode("utf-8", errors="replace")


def _pdf_metni(yol: Path) -> str:
    from pypdf import PdfReader

    okuyucu = PdfReader(str(yol))
    return "\n\n".join(sayfa.extract_text() or "" for sayfa in okuyucu.pages)


def _docx_metni(yol: Path) -> str:
    import docx

    belge = docx.Document(str(yol))
    return "\n".join(paragraf.text for paragraf in belge.paragraphs)
