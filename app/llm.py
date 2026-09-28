"""Yerel cor proxy'sine konuşan ince LLM istemcisi.

Tasarım notları:
  * `anlat` projesindeki `generator/narrator.py::CorLLMClient` ile AYNI desen:
    ek bağımlılık yok (stdlib `urllib`), Anthropic uyumlu `POST /v1/messages`,
    retry SADECE HTTP 5xx'te, `LLMClient` Protocol'ü sayesinde test'lerde
    sahte istemci enjekte edilebilir.
  * Boş metin, HTTP 200'e rağmen başarısızlıktır: sahte yanıt üretmeyip
    `LLMError` yükseltiriz — öneri motoru bunu `RecommendationError`'a çevirir.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Protocol, runtime_checkable

DEFAULT_BASE_URL = os.environ.get("COR_BASE_URL", "http://127.0.0.1:8787")
DEFAULT_MODEL = os.environ.get("COR_MODEL", "stealth/space-bunny-alpha")

MAX_TOKENS = 2000


class LLMError(RuntimeError):
    """LLM'e erişilemedi ya da beklenmeyen bir yanıt biçimi geldi."""


@runtime_checkable
class LLMClient(Protocol):
    """Prompt alıp metin döndüren en küçük arayüz."""

    def complete(self, prompt: str) -> str: ...


class CorLLMClient:
    """Yerel cor proxy'sine Anthropic uyumlu HTTP ile bağlanır.

    Neden subprocess değil: proxy zaten `/v1/messages` ucunu kimlik doğrulama
    olmadan sunuyor; test edilebilir, zaman aşımları ve hata mesajları
    doğrudan kontrol edilir, alt süreç yönetimi yok.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        timeout: float = 60.0,
        max_retries: int = 3,
        retry_backoff: float = 3.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff

    def _post_once(self, prompt: str) -> str:
        payload = json.dumps(
            {
                "model": self.model,
                "max_tokens": MAX_TOKENS,
                "messages": [{"role": "user", "content": prompt}],
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/v1/messages",
            data=payload,
            headers={"content-type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise LLMError(f"cor proxy HTTP {exc.code} döndü: {detail[:500]}") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise LLMError(
                f"cor proxy'ye ({self.base_url}) bağlanılamadı: {exc}. "
                "Önce `cor claude` ile proxy'yi başlatmayı deneyin."
            ) from exc

        try:
            parsed = json.loads(body)
            text = parsed["content"][0]["text"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise LLMError(
                f"cor proxy'den beklenmeyen yanıt biçimi: {body[:500]}"
            ) from exc

        if not text or not text.strip():
            raise LLMError(
                "LLM boş yanıt döndürdü (muhtemelen max_tokens kısa kaldı). "
                "Sahte yanıt üretmek yerine hata fırlatıldı."
            )
        return text

    def complete(self, prompt: str) -> str:
        """İsteği gönderir; sağlayıcının geçici 5xx hatalarında sınırlı sayıda tekrar dener."""
        last_error: LLMError | None = None
        for attempt in range(self.max_retries + 1):
            try:
                return self._post_once(prompt)
            except LLMError as exc:
                last_error = exc
                # Bağlantı hatası ve bozuk yanıt kalıcıdır; yalnızca HTTP 5xx geçicidir.
                if "HTTP 5" not in str(exc) or attempt == self.max_retries:
                    raise
                delay = self.retry_backoff * (2**attempt)
                print(
                    f"Geçici sağlayıcı hatası, {delay:.0f}s sonra tekrar denenecek "
                    f"({attempt + 1}/{self.max_retries}): {exc}",
                    file=sys.stderr,
                )
                time.sleep(delay)
        raise last_error if last_error else LLMError("Bilinmeyen hata")
