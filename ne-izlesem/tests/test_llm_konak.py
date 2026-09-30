"""`app.llm`: loopback dışı cor adresi REDDEDİLİR (kullanıcı verisi başka makineye gitmesin).

Önceden bu araçta konak denetimi yoktu; atlas/harita/orkestra ile aynı sıkılığa getirildi.
"""

from __future__ import annotations

import pytest

from app.llm import CorLLMClient, LLMError, konak_kontrol


@pytest.mark.parametrize(
    "adres",
    ["http://ornek.com:8787", "http://192.168.1.10:8787", "http://0.0.0.0:8787", "https://api.ornek.com"],
)
def test_loopback_disi_adres_reddedilir(adres: str) -> None:
    with pytest.raises(LLMError, match="loopback"):
        CorLLMClient(base_url=adres)


def test_gecersiz_sema_reddedilir() -> None:
    with pytest.raises(LLMError):
        CorLLMClient(base_url="ftp://127.0.0.1:8787")


@pytest.mark.parametrize(
    "adres", ["http://127.0.0.1:8787", "http://localhost:8787", "http://[::1]:8787", "http://LOCALHOST:8787"]
)
def test_loopback_adresler_kabul(adres: str) -> None:
    assert CorLLMClient(base_url=adres).base_url == adres
    assert konak_kontrol(adres)
