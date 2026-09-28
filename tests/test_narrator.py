"""narrator.py testleri: sahte LLMClient ile, gerçek ağ çağrısı yapmadan."""

from __future__ import annotations

from pathlib import Path

import pytest

from generator.narrator import (
    REQUIRED_SECTIONS,
    LLMClient,
    NarratorError,
    build_prompt,
    generate_narration,
)
from generator.scanner import scan_repository

GOOD_NARRATION = """# Ornek Proje Anlatisi

Bu proje, ornek bir uygulama icin gelistirilmistir.

## Özellikler ve Zaman Çizelgesi

Projenin ilk commit'i 2024-01-10 tarihinde atildi ve README ile basladi.
2024-02-05'te flask bagimliligi eklendi. 2024-03-12'de jest test altyapisi
kuruldu. 2024-04-20'de ilk ozellik olan selam verme fonksiyonu eklendi.

## Teknoloji Seçimleri ve Nedenleri

Flask secildi cunku hafif ve ogrenmesi kolay bir web framework'u. Jest ise
JavaScript tarafinda hizli bir test kosucusu oldugu icin tercih edildi.

## Önemli Tasarım Kararları

Bagimlilik dosyalarinin versiyonlari sabitlendi; bu, tekrar uretilebilir
kurulumlar icin kasitli bir tercih olarak belgelendi.
"""


class FakeLLMClient:
    """Test-only: cevabı sabit döndürür, ağa dokunmaz."""

    model = "fake-model"

    def __init__(self, response: str = GOOD_NARRATION) -> None:
        self.response = response
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.response


def test_protocol_is_satisfied_by_fake_and_real() -> None:
    from generator.narrator import CorLLMClient

    assert isinstance(FakeLLMClient(), LLMClient)
    assert isinstance(CorLLMClient(), LLMClient)


def test_prompt_contains_scan_evidence(sample_repo: Path) -> None:
    scan = scan_repository(sample_repo)
    prompt = build_prompt(scan)

    assert "ilk commit: README" in prompt
    assert "flask==3.0.0" in prompt
    assert "Ornek Proje" in prompt
    for section in REQUIRED_SECTIONS:
        assert section in prompt


def test_generate_narration_returns_markdown(sample_repo: Path) -> None:
    scan = scan_repository(sample_repo)
    client = FakeLLMClient()

    result = generate_narration(scan, client)

    assert result.markdown.startswith("# Ornek Proje Anlatisi")
    assert result.model == "fake-model"
    assert len(client.prompts) == 1
    for section in REQUIRED_SECTIONS:
        assert section in result.markdown


def test_empty_response_raises_instead_of_faking(sample_repo: Path) -> None:
    scan = scan_repository(sample_repo)

    with pytest.raises(NarratorError):
        generate_narration(scan, FakeLLMClient(response="   "))


def test_missing_section_raises(sample_repo: Path) -> None:
    scan = scan_repository(sample_repo)
    incomplete = "## Özellikler ve Zaman Çizelgesi\n\nYeterince uzun bir metin. " * 5

    with pytest.raises(NarratorError, match="zorunlu bölümleri"):
        generate_narration(scan, FakeLLMClient(response=incomplete))


def test_trivially_short_response_raises(sample_repo: Path) -> None:
    scan = scan_repository(sample_repo)
    short = "\n".join(REQUIRED_SECTIONS)

    with pytest.raises(NarratorError, match="kısa"):
        generate_narration(scan, FakeLLMClient(response=short))


def test_client_exception_is_wrapped(sample_repo: Path) -> None:
    scan = scan_repository(sample_repo)

    class ExplodingClient:
        def complete(self, prompt: str) -> str:
            raise ConnectionError("baglanti yok")

    with pytest.raises(NarratorError, match="başarısız"):
        generate_narration(scan, ExplodingClient())


def test_transient_5xx_is_retried_then_succeeds() -> None:
    """Sağlayıcının geçici 5xx'i bir kez tekrarlanıp sonra başarılı olmalı."""
    from generator.narrator import CorLLMClient

    client = CorLLMClient(retry_backoff=0.0)
    calls = {"n": 0}

    def fake_post(prompt: str) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            raise NarratorError("cor proxy HTTP 502 döndü: upstream bos")
        return "tamam"

    client._post_once = fake_post  # type: ignore[method-assign]
    assert client.complete("prompt") == "tamam"
    assert calls["n"] == 2


def test_connection_error_is_not_retried() -> None:
    """Bağlantı hatası kalıcıdır; yeniden denenmemeli."""
    from generator.narrator import CorLLMClient

    client = CorLLMClient(retry_backoff=0.0)
    calls = {"n": 0}

    def fake_post(prompt: str) -> str:
        calls["n"] += 1
        raise NarratorError("cor proxy'ye bağlanılamadı: refused")

    client._post_once = fake_post  # type: ignore[method-assign]
    with pytest.raises(NarratorError, match="bağlanılamadı"):
        client.complete("prompt")
    assert calls["n"] == 1


def test_persistent_5xx_gives_up_after_max_retries() -> None:
    from generator.narrator import CorLLMClient

    client = CorLLMClient(retry_backoff=0.0, max_retries=2)
    calls = {"n": 0}

    def fake_post(prompt: str) -> str:
        calls["n"] += 1
        raise NarratorError("cor proxy HTTP 502 döndü: upstream bos")

    client._post_once = fake_post  # type: ignore[method-assign]
    with pytest.raises(NarratorError, match="502"):
        client.complete("prompt")
    assert calls["n"] == 3  # ilk deneme + 2 tekrar
