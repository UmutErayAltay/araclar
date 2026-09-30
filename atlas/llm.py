"""Yerel cor proxy'sine konuşan ince LLM istemcisi (Dalga D).

Tasarım notları:
  * `/home/user/harita/harita/llm.py` ile AYNI desen: ek bağımlılık yok
    (stdlib `urllib`), Anthropic uyumlu `POST /v1/messages`, retry SADECE
    HTTP 5xx'te, `LLMClient` Protocol'ü sayesinde test'lerde SAHTE istemci
    enjekte edilebilir (ağa hiç çıkmadan).
  * Boş metin, HTTP 200'e rağmen BAŞARISIZLIKTIR: sahte yanıt üretmeyip
    `LLMError` yükseltiriz — `summary.ozet_uret` bunu yakalar.
  * GÜVENLİK: yalnızca LOOPBACK adreslerine bağlanmayı kabul eder. cor
    yereldir; `http://ornek.com:8787` gibi bir adres verilirse hata verilir
    (depo içeriği dışarı gitmez).
  * Bu modül `harita`'dan İÇE AKTARILMAZ; desen kopyalanıp bu pakete
    uyarlanmıştır (bagimlilik yonu ters cevrilmis olurdu).

Bu istemci YALNIZCA `--cor` bayragiyla kullanilir. Varsayilan ozet
(`atlas ozet`) HIC BIR cagri yapmaz.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Protocol, runtime_checkable

#: cor adresi ve modeli ortam degiskeniyle degistirilebilir.
DEFAULT_BASE_URL = os.environ.get("COR_BASE_URL", "http://127.0.0.1:8787")
DEFAULT_MODEL = os.environ.get("COR_MODEL", "stealth/space-bunny-alpha")

MAX_TOKENS = 2000

#: Baglanilabilecek konak adlari. cor YERELDIR.
IZINLI_KONAKLAR = frozenset({"127.0.0.1", "localhost", "::1", "[::1]"})


class LLMError(RuntimeError):
    """LLM'e erisilemedi ya da beklenmeyen bir yanit bicimi geldi."""


@runtime_checkable
class LLMClient(Protocol):
    """Prompt alip metin donduren en kucuk arayuz."""

    def complete(self, prompt: str) -> str: ...


def konak_kontrol(base_url: str) -> str:
    """`base_url`nin konak adini dondurur; loopback DEGILSE `LLMError` verir."""
    parcalar = urllib.parse.urlsplit(base_url)
    if parcalar.scheme not in ("http", "https"):
        raise LLMError(f"cor adresi gecersiz sema: {base_url!r}")
    konak = parcalar.hostname
    if konak is None or konak.lower() not in IZINLI_KONAKLAR:
        raise LLMError(
            f"cor adresi loopback olmali, {konak!r} reddedildi. "
            "Bu arac yalnizca yerel cor proxy'sine baglanir."
        )
    return konak


class CorLLMClient:
    """Yerel cor proxy'sine Anthropic uyumlu HTTP ile baglanir.

    Neden subprocess degil: proxy zaten `/v1/messages` ucunu kimlik
    dogrulamasi sunuyor; test edilebilir, zaman asimlari ve hata mesajlari
    dogrudan kontrol edilir, alt surec yonetimi yok.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        timeout: float = 60.0,
        max_retries: int = 3,
        retry_backoff: float = 3.0,
    ) -> None:
        konak_kontrol(base_url)  # kurulusta reddet: ag yanlisa gitmesin
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
            raise LLMError(f"cor proxy HTTP {exc.code} dondu: {detail[:500]}") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise LLMError(
                f"cor proxy'ye ({self.base_url}) baglanilamadi: {exc}. "
                "Once `cor start` ile proxy'yi baslatmayi deneyin."
            ) from exc

        try:
            parsed = json.loads(body)
            text = parsed["content"][0]["text"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"cor proxy'den beklenmeyen yanit bicimi: {body[:500]}") from exc

        if not text or not text.strip():
            raise LLMError(
                "LLM bos yanit dondu (muhtemelen max_tokens kisa kaldi). "
                "Sahte yanit uretmek yerine hata firlatildi."
            )
        return text

    def complete(self, prompt: str) -> str:
        """Istegi gonderir; 5xx hatalarinda ustel geri cekilmeli tekrar dener."""
        last_error: LLMError | None = None
        for attempt in range(self.max_retries + 1):
            try:
                return self._post_once(prompt)
            except LLMError as exc:
                last_error = exc
                # Baglanti hatasi ve bozuk yanit kalicidir; yalniz 5xx gecicidir.
                if "HTTP 5" not in str(exc) or attempt == self.max_retries:
                    raise
                delay = self.retry_backoff * (2**attempt)
                print(
                    f"Gecici saglayici hatasi, {delay:.0f}s sonra tekrar denenecek "
                    f"({attempt + 1}/{self.max_retries}): {exc}",
                    file=sys.stderr,
                )
                time.sleep(delay)
        raise last_error if last_error else LLMError("Bilinmeyen hata")
