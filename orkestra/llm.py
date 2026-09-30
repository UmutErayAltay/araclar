"""Yerel cor proxy'sine konuşan ince LLM istemcisi (Dalga D planlayıcı).

Tasarım notları:
  * `harita/harita/llm.py` ile AYNI desen, buraya **kopyalanıp uyarlanmıştır**
    (İÇE AKTARILMAZ): ek bağımlılık yok (stdlib `urllib`), Anthropic uyumlu
    `POST /v1/messages`, retry **yalnız HTTP 5xx**'te, `LLMClient` Protocol'ü
    sayesinde test'lerde sahte istemci enjekte edilebilir.
  * Boş metin HTTP 200'e rağmen BAŞARISIZLIKTIR: sahte yanıt üretilmez,
    `LLMError` yükseltilir — planlayıcı KISMİ SONUÇ ÜRETMEZ.
  * GÜVENLİK: yalnızca LOOPBACK adreslerine bağlanmayı kabul eder. cor
    yereldir; dış adres verilirse kuruluşta reddedilir (kullanıcının verisi
    başka makineye gitmez).
  * `harita`'dan yalnızca OKUNUR referans alındı; bu modül oraya YAZMAZ.
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

DEFAULT_BASE_URL = os.environ.get("COR_BASE_URL", "http://127.0.0.1:8787")
# Varsayılan model. GÖZLEM: `stealth/space-bunny-alpha` planlama isteminde
# `max_tokens` tamamını DÜŞÜNME tokena harcayıp `stop_reason=max_tokens` ve
# BOŞ metin döndürdü (4000 ve 16000 denendi). `nvidia/nemotron-3-ultra-550b:free`
# aynı istemde geçerli JSON döndürdü. `COR_MODEL` ile değiştirilebilir.
DEFAULT_MODEL = os.environ.get(
    "COR_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free"
)

MAX_TOKENS = 4000

# Yalnızca loopback: planlayıcı hedef metnini başka yere göndermemeli.
IZINLI_KONAKLAR = frozenset({"127.0.0.1", "localhost", "::1", "[::1]"})


class LLMError(RuntimeError):
    """LLM'e erişilemedi ya da beklenmeyen bir yanıt biçimi geldi."""


@runtime_checkable
class LLMClient(Protocol):
    """Prompt alıp metin döndüren en küçük arayüz."""

    def complete(self, prompt: str) -> str: ...


def konak_kontrol(base_url: str) -> str:
    """`base_url`nin konak adını döner; loopback DEĞİLSE `LLMError` verir."""
    parcalar = urllib.parse.urlsplit(base_url)
    if parcalar.scheme not in ("http", "https"):
        raise LLMError(f"cor adresi geçersiz şema: {base_url!r}")
    konak = parcalar.hostname
    if konak is None or konak.lower() not in IZINLI_KONAKLAR:
        raise LLMError(
            f"cor adresi loopback olmalı, {konak!r} reddedildi. "
            "Bu araç yalnızca yerel cor proxy'sine bağlanır."
        )
    return konak


class CorLLMClient:
    """Yerel cor proxy'sine Anthropic uyumlu HTTP ile bağlanır.

    Neden subprocess değil: proxy zaten `/v1/messages` ucunu kimlik
    doğrulamasız sunuyor; test edilebilir, alt süreç yönetimi yok.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        timeout: float = 120.0,
        max_retries: int = 3,
        retry_backoff: float = 3.0,
    ) -> None:
        konak_kontrol(base_url)  # kuruluşta reddet: ağ yanlışa gitmesin
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
        istek = urllib.request.Request(
            f"{self.base_url}/v1/messages",
            data=payload,
            headers={"content-type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(istek, timeout=self.timeout) as yanit:
                govde = yanit.read().decode("utf-8")
        except urllib.error.HTTPError as hata:
            ayrinti = hata.read().decode("utf-8", errors="replace")
            raise LLMError(f"cor proxy HTTP {hata.code} döndü: {ayrinti[:500]}") from hata
        except (urllib.error.URLError, OSError) as hata:
            raise LLMError(
                f"cor proxy'ye ({self.base_url}) bağlanılamadı: {hata}. "
                "Önce `cor start` ile proxy'yi başlatmayı deneyin."
            ) from hata

        try:
            ayristirilmis = json.loads(govde)
            metin = ayristirilmis["content"][0]["text"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as hata:
            raise LLMError(f"cor proxy'den beklenmeyen yanıt biçimi: {govde[:500]}") from hata

        if not metin or not metin.strip():
            raise LLMError(
                "LLM boş yanıt döndürdü (muhtemelen max_tokens kısa kaldı). "
                "Sahte yanıt üretmek yerine hata fırlatıldı."
            )
        return metin

    def complete(self, prompt: str) -> str:
        """İsteği gönderir; **yalnız 5xx**'te üstel geri çekilmeli tekrar dener."""
        son_hata: LLMError | None = None
        for deneme in range(self.max_retries + 1):
            try:
                return self._post_once(prompt)
            except LLMError as hata:
                son_hata = hata
                # Bağlantı hatası ve bozuk yanıt kalıcıdır; yalnız 5xx geçicidir.
                if "HTTP 5" not in str(hata) or deneme == self.max_retries:
                    raise
                bekleme = self.retry_backoff * (2**deneme)
                print(
                    f"Geçici sağlayıcı hatası, {bekleme:.0f}s sonra tekrar denenecek "
                    f"({deneme + 1}/{self.max_retries}): {hata}",
                    file=sys.stderr,
                )
                time.sleep(bekleme)
        raise son_hata if son_hata else LLMError("Bilinmeyen hata")
