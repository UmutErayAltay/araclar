"""`danis/dosya_metni.py` testleri — gerçek örnek dosyalar, mock yok.

tests/fixtures/ altındaki dosyalar gerçek: .txt/.md düz metin, .pdf elle
üretilmiş geçerli bir PDF, .docx python-docx ile üretilmiş gerçek bir zip.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import FIXTURE_DIR
from danis.dosya_metni import (
    MAX_KARAKTER,
    NUL_TARAMA_BOYUTU,
    BosDosyaError,
    DosyaBulunamadiError,
    DosyaTuruDesteklenmiyorError,
    IkiliDosyaError,
    metni_cikar,
)


# --------------------------------------------------------------------- #
# Düz metin
# --------------------------------------------------------------------- #


def test_reads_txt() -> None:
    metin = metni_cikar(FIXTURE_DIR / "ornek.txt")
    assert "Danis test dosyasi" in metin
    assert "Ikinci satir" in metin


def test_reads_markdown_preserving_syntax() -> None:
    metin = metni_cikar(FIXTURE_DIR / "ornek.md")
    assert "# Danis Ornek Markdown" in metin
    assert "**kalin**" in metin


def test_reads_py_and_json_and_csv(tmp_path: Path) -> None:
    """API.md metin uzantıları: doğrudan okunur."""
    for ad, icerik in [
        ("a.py", "print('x')"),
        ("a.json", '{"k": 1}'),
        ("a.csv", "k,v\n1,2"),
    ]:
        yol = tmp_path / ad
        yol.write_text(icerik, encoding="utf-8")
        assert metni_cikar(yol) == icerik


def test_unknown_text_extension_is_read_directly(tmp_path: Path) -> None:
    """API.md: "bilinmeyen metin uzantıları → doğrudan oku"."""
    yol = tmp_path / "notlar.xyz"
    yol.write_text("ozet notlar", encoding="utf-8")
    assert metni_cikar(yol) == "ozet notlar"


def test_extension_match_is_case_insensitive(tmp_path: Path) -> None:
    yol = tmp_path / "RAHATSIZ.TXT"
    yol.write_text("buyuk harfli uzanti", encoding="utf-8")
    assert metni_cikar(yol) == "buyuk harfli uzanti"


def test_undecodable_bytes_are_replaced_not_fatal(tmp_path: Path) -> None:
    """`errors="replace"`: bozuk bayt ölümcül hata değil.

    NUL içermeyen bozuk baytlar hâlâ düzeltilerek geçer; NUL baytı ise aşağıdaki
    ikili kontrolüne takılır.
    """
    yol = tmp_path / "bozuk.txt"
    yol.write_bytes(b"onceki \xff\xfe sonrasi")
    metin = metni_cikar(yol)
    assert "onceki" in metin and "sonrasi" in metin


# --------------------------------------------------------------------- #
# NUL baytı / ikili dosya güvenlik ağı
# --------------------------------------------------------------------- #


def test_binary_fixture_file_raises_ikili_dosya() -> None:
    """tests/fixtures/ikili.dat: gerçek ikili bayt, bilinmeyen uzantı.

    Uzantı listesinde olmayan gerçek bir ikili dosya, `errors="replace"` ile
    sessizce bozuk karakter yığınına çevrilip cor'a gönderilmemeli.
    """
    with pytest.raises(IkiliDosyaError) as exc:
        metni_cikar(FIXTURE_DIR / "ikili.dat")
    assert "NUL bayt" in str(exc.value)
    assert "ikili.dat" in str(exc.value)


def test_nul_byte_in_known_text_extension_also_raises(tmp_path: Path) -> None:
    """Kontrol bilinen metin uzantılarına da uygulanır (tutarlılık)."""
    yol = tmp_path / "sahte.txt"
    yol.write_bytes(b"metin gibi gorunuyor\x00\x00ama ikili")
    with pytest.raises(IkiliDosyaError):
        metni_cikar(yol)


def test_nul_after_scan_window_is_not_fatal(tmp_path: Path) -> None:
    """Tarama yalnızca ilk 8192 bayta bakar: sınırın ötesi kasıtlı olarak kör."""
    yol = tmp_path / "gec_nul.txt"
    yol.write_bytes(b"a" * (NUL_TARAMA_BOYUTU + 100) + b"\x00" + b"b" * 10)
    metin = metni_cikar(yol)
    assert metin.startswith("a" * 10) and metin.endswith("b" * 10)


def test_utf8_multibyte_characters_are_not_mistaken_for_binary(tmp_path: Path) -> None:
    """Türkçe karakterlerde NUL olmayan çok baytlı diziler yanlışlıkla reddedilmez."""
    yol = tmp_path / "turkce.txt"
    icerik = "ğüşiöç ĞÜŞİÖÇ — çalıştı ✓ 漢字"
    yol.write_text(icerik, encoding="utf-8")
    assert metni_cikar(yol) == icerik


# --------------------------------------------------------------------- #
# PDF / DOCX
# --------------------------------------------------------------------- #


def test_reads_pdf_text() -> None:
    metin = metni_cikar(FIXTURE_DIR / "ornek.pdf")
    assert "Danis ornek PDF dosyasi" in metin


def test_reads_docx_paragraphs() -> None:
    metin = metni_cikar(FIXTURE_DIR / "ornek.docx")
    assert "Danis ornek DOCX dosyasi" in metin
    assert "Uctuncu paragraf" in metin


def test_pdf_without_text_raises_bos_dosya() -> None:
    with pytest.raises(BosDosyaError):
        metni_cikar(FIXTURE_DIR / "bos.pdf")


def test_docx_without_text_raises_bos_dosya() -> None:
    with pytest.raises(BosDosyaError):
        metni_cikar(FIXTURE_DIR / "bos.docx")


# --------------------------------------------------------------------- #
# Hata yolları
# --------------------------------------------------------------------- #


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(DosyaBulunamadiError):
        metni_cikar(tmp_path / "yok.txt")


def test_directory_is_not_a_file(tmp_path: Path) -> None:
    with pytest.raises(DosyaBulunamadiError):
        metni_cikar(tmp_path)


def test_image_extension_is_rejected(tmp_path: Path) -> None:
    yol = tmp_path / "ekran.png"
    yol.write_bytes(b"\x89PNG\r\n\x1a\n")
    with pytest.raises(DosyaTuruDesteklenmiyorError, match="png"):
        metni_cikar(yol)


def test_empty_file_raises_bos_dosya(tmp_path: Path) -> None:
    yol = tmp_path / "bos.txt"
    yol.write_text("", encoding="utf-8")
    with pytest.raises(BosDosyaError):
        metni_cikar(yol)


def test_whitespace_only_file_raises_bos_dosya(tmp_path: Path) -> None:
    yol = tmp_path / "bosluk.txt"
    yol.write_text("   \n\t\n  ", encoding="utf-8")
    with pytest.raises(BosDosyaError):
        metni_cikar(yol)


# --------------------------------------------------------------------- #
# Kırpma
# --------------------------------------------------------------------- #


def test_short_text_is_not_truncated(tmp_path: Path) -> None:
    yol = tmp_path / "kisa.txt"
    yol.write_text("x" * 100, encoding="utf-8")
    metin = metni_cikar(yol)
    assert metin == "x" * 100
    assert "kırpıldı" not in metin


def test_long_text_is_truncated_with_note(tmp_path: Path) -> None:
    yol = tmp_path / "uzun.txt"
    yol.write_text("y" * (MAX_KARAKTER + 500), encoding="utf-8")
    metin = metni_cikar(yol)
    assert metin.startswith("y" * 100)
    assert "[... kırpıldı ...]" in metin
    assert len(metin) < MAX_KARAKTER + 500


def test_truncation_bounds_prompt_size(tmp_path: Path) -> None:
    """Kırpma LLM prompt'unu sınırlı tutar — belgelenen üst sınır."""
    yol = tmp_path / "cok_uzun.txt"
    yol.write_text("z" * 200_000, encoding="utf-8")
    assert len(metni_cikar(yol)) == MAX_KARAKTER + len("\n\n[... kırpıldı ...]")
