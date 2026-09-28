"""İsteğe bağlı gerçek entegrasyon testi.

Varsayılan `pytest` koşusunda ATLANIR (pytest.ini: -m "not integration").
Çalıştırmak için:  pytest -m integration
"""

from __future__ import annotations

import json
import socket
import urllib.request
from pathlib import Path

import pytest

from generator.narrator import DEFAULT_BASE_URL, CorLLMClient, NarratorError
from generator.scanner import scan_repository


def cor_reachable(base_url: str = DEFAULT_BASE_URL) -> bool:
    host, port = "127.0.0.1", int(base_url.rsplit(":", 1)[1])
    with socket.socket() as sock:
        sock.settimeout(1.0)
        return sock.connect_ex((host, port)) == 0


@pytest.mark.integration
def test_real_cor_client_completes(sample_repo: Path) -> None:
    if not cor_reachable():
        pytest.skip("cor proxy bu ortamda erişilebilir değil")

    scan = scan_repository(sample_repo)
    result = CorLLMClient(timeout=180.0).complete(build_short_prompt(scan))

    assert result.strip(), "cor boş yanıt döndürdü"


def build_short_prompt(scan) -> str:
    return (
        f"Bu depoda {len(scan.commits)} commit var. "
        "Tek kelimeyle cevap ver: hazir."
    )


@pytest.mark.integration
def test_real_end_to_end_narration(sample_repo: Path) -> None:
    if not cor_reachable():
        pytest.skip("cor proxy bu ortamda erişilebilir değil")

    from generator.narrator import generate_narration

    scan = scan_repository(sample_repo)
    result = generate_narration(scan, CorLLMClient(timeout=300.0))

    assert len(result.markdown) > 200
    for section in ("Özellikler", "Teknoloji", "Tasarım"):
        assert section in result.markdown


@pytest.mark.integration
def test_connection_refused_raises_narrator_error(sample_repo: Path) -> None:
    """Yanlış port sessizce geçmemeli, net hata vermeli."""
    client = CorLLMClient(base_url="http://127.0.0.1:9", timeout=5.0)
    with pytest.raises(NarratorError):
        client.complete("merhaba")
