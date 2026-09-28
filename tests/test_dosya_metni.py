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
    BosDosyaError,
    DosyaBulunamadiError,
    DosyaTuruDesteklenmiyorError,
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
    """`errors="replace"`: bozuk bayt ölümcül hata değil."""
    yol = tmp_path / "bozuk.txt"
    yol.write_bytes(b"onceki \xff\xfe sonrasi")
    metin = metni_cikar(yol)
    assert "onceki" in metin and "sonrasi" in metin


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
