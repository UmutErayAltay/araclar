"""Yerel cor proxy'sine konuşan ince LLM istemcisi (haftalik özet üretimi).

Commit verisi dışarı gitmesin diye loopback dışı adresler reddedilir. Gerçek istemci
`_corclient.py`'dedir: `tools/sync.py` ile senkronlanır, ELLE DÜZENLENMEZ.
"""

from __future__ import annotations

import os

from . import _corclient
from ._corclient import LLMClient, LLMError, konak_kontrol  # noqa: F401

DEFAULT_BASE_URL = os.environ.get("COR_BASE_URL", "http://127.0.0.1:8787")
DEFAULT_MODEL = os.environ.get("COR_MODEL", "stealth/space-bunny-alpha")

MAX_TOKENS = 2000

IZINLI_KONAKLAR = frozenset({"127.0.0.1", "localhost", "::1", "[::1]"})


class CorLLMClient(_corclient.CorLLMClient):
    """Yerel cor proxy'sine Anthropic uyumlu HTTP ile bağlanır (bkz. `_corclient`)."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        timeout: float = 60.0,
        max_retries: int = 3,
        retry_backoff: float = 3.0,
    ) -> None:
        super().__init__(
            base_url,
            model,
            timeout,
            max_retries,
            retry_backoff,
            max_tokens=MAX_TOKENS,
            izinli_konaklar=IZINLI_KONAKLAR,
            baslat_ipucu="cor start",
        )
