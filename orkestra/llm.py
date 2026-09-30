"""Yerel cor proxy'sine konusan ince LLM istemcisi (Dalga D planlayici). GOZLEM: `stealth/space-bunny-alpha` planlama isteminde `max_tokens` tamamini DUSUNME tokena harcayip BOS metin dondurdu; `nvidia/nemotron-3-ultra-550b:free` ayni istemde gecerli JSON dondurdu. `COR_MODEL` ile degistirilebilir.

Gerçek istemci `_corclient.py`'dedir: `corclient` reposundan `tools/sync.py` ile
senkronlanır ve ELLE DÜZENLENMEZ (sapma `tests/test_corclient_senkron.py` ile
yakalanır). Bu modül yalnızca bu repoya özgü varsayılanları (model, token, zaman
aşımı, konak denetimi) taşır ve eski kamuya açık adları korur.
"""

from __future__ import annotations

# Testler bu adlar üzerinden yama yapar (`llm.urllib.request.urlopen`, `llm.time.sleep`).
import json  # noqa: F401
import os
import sys  # noqa: F401
import time  # noqa: F401
import urllib.error  # noqa: F401
import urllib.parse  # noqa: F401
import urllib.request  # noqa: F401
from typing import Protocol, runtime_checkable  # noqa: F401

from . import _corclient
from ._corclient import LLMClient, LLMError, konak_kontrol  # noqa: F401

DEFAULT_BASE_URL = os.environ.get("COR_BASE_URL", "http://127.0.0.1:8787")
DEFAULT_MODEL = os.environ.get(
    "COR_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free"
)

MAX_TOKENS = 4000

IZINLI_KONAKLAR = frozenset({"127.0.0.1", "localhost", "::1", "[::1]"})


class CorLLMClient(_corclient.CorLLMClient):
    """Yerel cor proxy'sine Anthropic uyumlu HTTP ile bağlanır (bkz. `_corclient`)."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        timeout: float = 120.0,
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
            baslat_ipucu='cor start',
        )
