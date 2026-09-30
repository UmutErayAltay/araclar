"""GERÇEK cor entegrasyon testleri.

Bu modül varsayılan `pytest` koşusunda da ÇALIŞIR (API.md: "cor gerçekten
burada çalışıyor, atlamaya gerek yok"). cor çalışmıyorsa dürüstçe atlanır
(`pytest.skip`), sahte bir "başarılı" sonuç üretilmez.

Gerçekten ne yaptığını doğrulamak için:
    cor status
    python3 -m pytest -v tests/test_integration_cor.py
"""

from __future__ import annotations

import socket

import pytest
from conftest import FIXTURE_DIR

from danis.cli import main
from danis.dosya_metni import metni_cikar
from danis.hata_analiz import prompt_olustur, yaniti_ayikla
from danis.llm import DEFAULT_BASE_URL, CorLLMClient, LLMError

GERCEKCI_SENARYO = ("git psh origin main", 127)


def cor_reachable(base_url: str = DEFAULT_BASE_URL) -> bool:
    host, port = "127.0.0.1", int(base_url.rsplit(":", 1)[1])
    with socket.socket() as sock:
        sock.settimeout(1.0)
        return sock.connect_ex((host, port)) == 0


@pytest.fixture
def gercek_cor() -> CorLLMClient:
    if not cor_reachable():
        pytest.skip("cor proxy bu ortamda erişilebilir değil (`cor start` gerekli)")
    return CorLLMClient(timeout=120.0)


@pytest.mark.integration
def test_real_cor_answers_a_plain_question(gercek_cor: CorLLMClient) -> None:
    """En temel yol: proxy gerçekten metin döndürüyor mu?"""
    yanit = gercek_cor.complete("Tek kelimeyle cevap ver: Türkiye'nin başkenti neresi?")
    assert yanit.strip()
    assert "ankara" in yanit.lower()


@pytest.mark.integration
def test_real_cor_diagnoses_a_real_command(gercek_cor: CorLLMClient, capsys) -> None:
    """Uçtan uca gerçek senaryo: `danis hata "git psh origin main" 127`."""
    komut, cikis_kodu = GERCEKCI_SENARYO

    ham = gercek_cor.complete(prompt_olustur(komut, cikis_kodu))
    sonuc = yaniti_ayikla(ham)

    # LLM biçime uymadıysa ham metin `teshis`e düşer — yine de dolu olmalı.
    assert sonuc["teshis"].strip(), f"boş teşhis, ham yanıt: {ham!r}"

    # 'push' geçen bir yerde geçmeli: gerçek bir teşhis bekleniyor.
    assert "push" in sonuc["teshis"].lower() or "psh" in sonuc["teshis"].lower()

    # Düzeltme ya ayrıştırılmış ya da None olmalı — asla uydurulmamalı.
    if sonuc["duzeltme"] is not None:
        assert sonuc["duzeltme"].strip()


@pytest.mark.integration
def test_real_cli_hata_end_to_end(gercek_cor: CorLLMClient, capsys, monkeypatch) -> None:
    """CLI'nin tamamı gerçek cor'a karşı: çıkış kodu 0, teşhis basılıyor."""
    monkeypatch.setattr("danis.cli.CorLLMClient", lambda **kw: gercek_cor)
    komut, cikis_kodu = GERCEKCI_SENARYO

    assert main(["hata", komut, str(cikis_kodu)]) == 0

    cikti = capsys.readouterr().out
    assert "🔎 TEŞHİS: " in cikti
    assert cikti.split("TEŞHİS: ", 1)[1].strip()


@pytest.mark.integration
def test_real_cli_dosya_end_to_end(gercek_cor: CorLLMClient, capsys, monkeypatch) -> None:
    """Gerçek bir örnek dosya gerçek cor'a sorulur."""
    monkeypatch.setattr("danis.cli.CorLLMClient", lambda **kw: gercek_cor)
    yol = FIXTURE_DIR / "ornek.txt"

    # Önce metin çıkarma sözleşmesini doğrula (dosya gerçekten okunabiliyor mu).
    assert "Danis test dosyasi" in metni_cikar(yol)

    assert main(["dosya", str(yol), "Bu metin kaç satır? Tek kelimeyle cevap ver."]) == 0
    assert capsys.readouterr().out.strip()


@pytest.mark.integration
def test_real_cor_summarizes_real_pdf_text(gercek_cor: CorLLMClient) -> None:
    """PDF'ten çıkarılan metin gerçek cor'da anlamlı yanıt üretiyor mu?"""
    metin = metni_cikar(FIXTURE_DIR / "ornek.pdf")
    yanit = gercek_cor.complete(
        f"Aşağıdaki metnin ne anlama geldiğini tek cümleyle söyle:\n\n{metin}"
    )
    assert "pdf" in yanit.lower()


@pytest.mark.integration
def test_real_cor_unreachable_url_raises_llm_error() -> None:
    """Gerçek hata yolu da gerçek: kapalı bir port LLMError fırlatır."""
    with pytest.raises(LLMError):
        CorLLMClient(base_url="http://127.0.0.1:9", timeout=5.0).complete("selam")
