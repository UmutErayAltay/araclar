"""`danis/hata_analiz.py` testleri — saf metin dönüşümleri, ağ yok."""

from __future__ import annotations

from danis.hata_analiz import prompt_olustur, yaniti_ayikla


# --------------------------------------------------------------------- #
# prompt_olustur
# --------------------------------------------------------------------- #


def test_prompt_contains_command_and_exit_code() -> None:
    prompt = prompt_olustur("git psh origin main", 127)
    assert "git psh origin main" in prompt
    assert "127" in prompt


def test_prompt_asks_for_exact_plain_text_format() -> None:
    """JSON değil düz metin, iki başlık — ayrıştırma buna dayanıyor."""
    prompt = prompt_olustur("ls", 1)
    assert "TEŞHİS:" in prompt
    assert "DÜZELTME:" in prompt
    assert "JSON" not in prompt


def test_prompt_is_turkish_and_asks_for_short_answer() -> None:
    prompt = prompt_olustur("ls", 1)
    assert "Türkçe" in prompt
    assert "KISA" in prompt
    assert "1-3 cümle" in prompt


# --------------------------------------------------------------------- #
# yaniti_ayikla — mutlu yol
# --------------------------------------------------------------------- #


def test_parses_canonical_two_line_answer() -> None:
    ham = "TEŞHİS: 'psh' komutu yok. 'push' yazmalısın.\nDÜZELTME: git push origin main"
    assert yaniti_ayikla(ham) == {
        "teshis": "'psh' komutu yok. 'push' yazmalısın.",
        "duzeltme": "git push origin main",
    }


def test_yok_means_no_fix() -> None:
    ham = "TEŞHİS: Kimlik doğrulama başarısız.\nDÜZELTME: yok"
    assert yaniti_ayikla(ham)["duzeltme"] is None


def test_missing_duzeltme_line_gives_none() -> None:
    assert yaniti_ayikla("TEŞHİS: Bir şeyler ters gitmiş.")["duzeltme"] is None


def test_multiline_teshis_is_preserved() -> None:
    ham = "TEŞHİS: İlk satır.\nİkinci satır.\nDÜZELTME: ls -la"
    sonuc = yaniti_ayikla(ham)
    assert sonuc["teshis"] == "İlk satır.\nİkinci satır."
    assert sonuc["duzeltme"] == "ls -la"


def test_markdown_bold_headers_are_tolerated() -> None:
    ham = "**TEŞHİS:** Yanlış bayrak.\n**DÜZELTME:** `git log --oneline`"
    assert yaniti_ayikla(ham) == {
        "teshis": "Yanlış bayrak.",
        "duzeltme": "git log --oneline",
    }


def test_lowercase_headers_are_tolerated() -> None:
    """Küçük harfli başlıklar da kabul edilir.

    Küçültme Türkçe'ye duyarlı olmalı: 'İ' (U+0130) standart `lower()` ile
    'i' olmaz, 'Ş' de küçültmede korunur — bu yüzden başlık eşleşmesi elle
    normalize edilir.
    """
    ham = "teşhis: küçük harf başlık\ndüzeltme: whoami"
    assert yaniti_ayikla(ham) == {"teshis": "küçük harf başlık", "duzeltme": "whoami"}


def test_dotted_capital_i_is_matched_in_duplicate_of_header() -> None:
    """'DÜZELTME' kelimesindeki 'İ' (U+0130) normal `lower()` ile 'eşleşmez'."""
    ham = "teşhis: I harfi\nDÜZELTME: echo i"
    assert yaniti_ayikla(ham)["duzeltme"] == "echo i"


def test_leading_dash_in_fix_is_preserved() -> None:
    """Düzeltme bir komuttur: `--help` gibi bayraklar geçerli bir yanıttır."""
    ham = "TEŞHİS: Yanlış bayrak.\nDÜZELTME: git log --oneline"
    assert yaniti_ayikla(ham)["duzeltme"] == "git log --oneline"


def test_bullet_prefix_in_diagnosis_is_stripped() -> None:
    """Teşhis satırındaki madde işareti biçim kalıntısıdır."""
    ham = "TEŞHİS:\n- Birinci madde.\n- İkinci madde.\nDÜZELTME: yok"
    assert yaniti_ayikla(ham)["teshis"] == "Birinci madde.\nİkinci madde."


def test_code_fence_around_answer_is_tolerated() -> None:
    ham = "```\nTEŞHİS: Kod blok içinde.\nDÜZELTME: pwd\n```"
    assert yaniti_ayikla(ham) == {
        "teshis": "Kod blok içinde.",
        "duzeltme": "pwd",
    }


def test_try_this_hint_becomes_duzeltme() -> None:
    """LLM DÜZELTME başlığını atlayıp ipucu verirse komut yine yakalanır."""
    ham = 'TEŞHİS: Komut yok.\nŞunu deneyin: `git push`'
    assert yaniti_ayikla(ham)["duzeltme"] == "git push"


# --------------------------------------------------------------------- #
# yaniti_ayikla — format dışı yanıt (sessiz başarısızlık YOK)
# --------------------------------------------------------------------- #


def test_unformatted_answer_falls_back_to_raw_text() -> None:
    ham = "Sanırım push yazmak istediniz, çünkü psh diye bir komut yok."
    assert yaniti_ayikla(ham) == {"teshis": ham, "duzeltme": None}


def test_empty_answer_yields_empty_diagnosis_and_no_fix() -> None:
    """Uydurma DÜZELTME basılmaz; çağıran taraf ham metni görür."""
    assert yaniti_ayikla("") == {"teshis": "", "duzeltme": None}
    assert yaniti_ayikla("   \n  ") == {"teshis": "", "duzeltme": None}


def test_empty_duzeltme_value_is_none() -> None:
    ham = "TEŞHİS: Bir sorun var.\nDÜZELTME:"
    assert yaniti_ayikla(ham) == {"teshis": "Bir sorun var.", "duzeltme": None}


def test_duzeltme_with_none_variant_is_none() -> None:
    ham = "TEŞHİS: Bir sorun var.\nDÜZELTME: yok."
    assert yaniti_ayikla(ham)["duzeltme"] is None
