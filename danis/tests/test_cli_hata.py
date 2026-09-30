"""`danis hata` alt komutu testleri.

LLM isteği stdlib `http.server` ile kaldırılan sahte cor'a GERÇEK soketten
gider (conftest.cli_cor); `main()` doğrudan çağrılır ve stdout/stderr/çıkış
kodu `capsys` ile sınanır.
"""

from __future__ import annotations

import pytest
from conftest import FakeCorServer, messages_response

from danis.cli import main


def test_prints_diagnosis_and_fix(cli_cor: FakeCorServer, capsys) -> None:
    cli_cor.responses = [
        (
            200,
            messages_response(
                "TEŞHİS: 'psh' diye bir komut yok, 'push' demek istedin.\n"
                "DÜZELTME: git push origin main"
            ),
        )
    ]

    assert main(["hata", "git psh origin main", "127"]) == 0

    cikti = capsys.readouterr().out
    assert "🔎 TEŞHİS: " in cikti
    assert "'psh' diye bir komut yok" in cikti
    assert "✅ DÜZELTME: git push origin main" in cikti


def test_fix_line_omitted_when_absent(cli_cor: FakeCorServer, capsys) -> None:
    """DÜZELTME yoksa o satır HİÇ basılmaz (API.md)."""
    cli_cor.responses = [(200, messages_response("TEŞHİS: Kimlik doğrulama başarısız.\nDÜZELTME: yok"))]

    assert main(["hata", "git push", "128"]) == 0

    cikti = capsys.readouterr().out
    assert "🔎 TEŞHİS: Kimlik doğrulama başarısız." in cikti
    assert "DÜZELTME" not in cikti


def test_prompt_sent_to_llm_contains_command_and_code(cli_cor: FakeCorServer) -> None:
    assert main(["hata", "docker ps", "125"]) == 0

    govde = cli_cor.requests[-1]["body"]
    icerik = govde["messages"][0]["content"]
    assert "docker ps" in icerik
    assert "125" in icerik


def test_unformatted_llm_answer_still_printed(cli_cor: FakeCorServer, capsys) -> None:
    """Format dışı yanıtta ham metin kullanıcıya gösterilir, uydurulmaz."""
    ham = "Galiba docker daemon calismiyor."
    cli_cor.responses = [(200, messages_response(ham))]

    assert main(["hata", "docker ps", "1"]) == 0

    cikti = capsys.readouterr().out
    assert ham in cikti
    assert "DÜZELTME" not in cikti


def test_llm_unreachable_exits_nonzero(cli_cor: FakeCorServer, capsys) -> None:
    cli_cor.responses = [(500, {"error": "cor cok kotu"})]

    assert main(["hata", "ls", "1"]) == 1

    assert "cor'a ulaşılamadı" in capsys.readouterr().err


def test_empty_llm_answer_exits_nonzero(cli_cor: FakeCorServer, capsys) -> None:
    """Boş yanıt: sahte teşhis basılmaz, hata verilir."""
    cli_cor.responses = [(200, messages_response("   "))]

    assert main(["hata", "ls", "1"]) == 1
    assert "cor'a ulaşılamadı" in capsys.readouterr().err


def test_negative_exit_code_accepted(cli_cor: FakeCorServer) -> None:
    assert main(["hata", "ls", "-1"]) == 0
    assert "-1" in cli_cor.requests[-1]["body"]["messages"][0]["content"]


def test_non_integer_exit_code_is_rejected() -> None:
    """argparse kendi hata mesajıyla durur ve SystemExit(2) fırlatır."""
    with pytest.raises(SystemExit) as exc:
        main(["hata", "ls", "abc"])
    assert exc.value.code == 2


def test_help_works(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    assert "hata" in capsys.readouterr().out


def test_subcommand_help_works(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["hata", "--help"])
    assert exc.value.code == 0
    assert "cikis_kodu" in capsys.readouterr().out
