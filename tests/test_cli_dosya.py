"""`danis dosya` alt komutu testleri.

Gerçek örnek dosyalar (tests/fixtures) + sahte cor üzerinden GERÇEK soket.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import FIXTURE_DIR, FakeCorServer, messages_response
from danis.cli import main


def test_asks_default_summary_when_no_question(cli_cor: FakeCorServer, capsys) -> None:
    cli_cor.responses = [(200, messages_response("Dosya 3 cumleyle ozetlendi."))]

    assert main(["dosya", str(FIXTURE_DIR / "ornek.txt")]) == 0

    assert "Dosya 3 cumleyle ozetlendi." in capsys.readouterr().out
    icerik = cli_cor.requests[-1]["body"]["messages"][0]["content"]
    assert "3-5 cümleyle özetle" in icerik
    assert "Danis test dosyasi" in icerik


def test_custom_question_is_forwarded(cli_cor: FakeCorServer) -> None:
    assert main(["dosya", str(FIXTURE_DIR / "ornek.md"), "Bu belgede kaç madde var?"]) == 0

    icerik = cli_cor.requests[-1]["body"]["messages"][0]["content"]
    assert icerik.startswith("Bu belgede kaç madde var?")
    assert "# Danis Ornek Markdown" in icerik


def test_file_text_reaches_llm_for_each_supported_type(
    cli_cor: FakeCorServer,
) -> None:
    for ad, beklenen in [
        ("ornek.txt", "Danis test dosyasi"),
        ("ornek.md", "Danis Ornek Markdown"),
        ("ornek.pdf", "Danis ornek PDF dosyasi"),
        ("ornek.docx", "Danis ornek DOCX dosyasi"),
    ]:
        cli_cor.responses = [(200, messages_response("ok"))]
        assert main(["dosya", str(FIXTURE_DIR / ad)]) == 0
        assert beklenen in cli_cor.requests[-1]["body"]["messages"][0]["content"]


def test_missing_file_exits_nonzero(cli_cor: FakeCorServer, capsys, tmp_path: Path) -> None:
    assert main(["dosya", str(tmp_path / "yok.pdf")]) == 1
    assert "Dosya bulunamadı" in capsys.readouterr().err


def test_unsupported_type_exits_nonzero_with_ocr_hint(
    cli_cor: FakeCorServer, capsys, tmp_path: Path
) -> None:
    """API.md'nin istediği net Türkçe mesaj + OCR yönlendirmesi."""
    yol = tmp_path / "ekran.png"
    yol.write_bytes(b"\x89PNG\r\n\x1a\n")

    assert main(["dosya", str(yol)]) == 1

    hata = capsys.readouterr().err
    assert "desteklenmiyor: .png" in hata
    assert "OCR" in hata
    assert "kısayol" in hata


def test_empty_file_exits_nonzero(cli_cor: FakeCorServer, capsys, tmp_path: Path) -> None:
    yol = tmp_path / "bos.txt"
    yol.write_text("   \n", encoding="utf-8")

    assert main(["dosya", str(yol)]) == 1
    assert "boş" in capsys.readouterr().err


def test_file_errors_take_precedence_over_llm(cli_cor: FakeCorServer, tmp_path: Path) -> None:
    """Dosya okunamıyorsa LLM'ye hiç istek atılmaz."""
    assert main(["dosya", str(tmp_path / "yok.txt")]) == 1
    assert cli_cor.hits == 0


def test_llm_failure_after_reading_file_exits_nonzero(
    cli_cor: FakeCorServer, capsys
) -> None:
    cli_cor.responses = [(503, {"error": "yok"})]

    assert main(["dosya", str(FIXTURE_DIR / "ornek.txt")]) == 1
    assert "cor'a ulaşılamadı" in capsys.readouterr().err


def test_long_file_is_truncated_before_sending(cli_cor: FakeCorServer, tmp_path: Path) -> None:
    yol = tmp_path / "uzun.txt"
    yol.write_text("z" * 50_000, encoding="utf-8")

    assert main(["dosya", str(yol)]) == 0

    icerik = cli_cor.requests[-1]["body"]["messages"][0]["content"]
    assert "[... kırpıldı ...]" in icerik
    # Gövdedeki 'z' karakterleri tam olarak MAX_KARAKTER olmalı (soru metnindeki
    # 'özetle' kelimesindeki 'z' dahil değildir).
    govde = icerik.split("--- DOSYA İÇERİĞİ ---", 1)[1]
    assert len(govde.split("\n\n[... kırpıldı ...]")[0].strip()) == 12_000


def test_help_works(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["dosya", "--help"])
    assert exc.value.code == 0
    assert "dosya_yolu" in capsys.readouterr().out
