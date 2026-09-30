"""Yerel cor proxy'sine konuşan LLM istemcisinin TEK kaynağı.

Bu modül, daha önce `atlas`, `harita`, `orkestra`, `danis` ve `ne-izlesem`
paketlerinde birer kopyası yaşayan istemcinin kaynağıdır. Tüketici repolar bu
dosyayı `tools/sync.py` ile kendi paketlerine `_corclient.py` adıyla kopyalar
ve `llm.py` ince kabuğunu korur. Kopya ELLE düzenlenmez; sapma (drift)
senkron başlığındaki sha256 ile yakalanır.

Davranış kopyalarla BİREBİR aynıdır; bu bir davranış DEĞİŞTİREN değil,
yalnızca TEK KAYNAĞA indiren refactor'dır:

  * Yalnızca stdlib (`urllib`); ek kurulum adımı ve ek bağımlılık YOK.
  * Anthropic uyumlu `POST /v1/messages`, gövde
    `{"model", "max_tokens", "messages":[{"role":"user","content":...}]}`.
  * Retry YALNIZCA HTTP 5xx'te; bağlantı hatası ve bozuk yanıt kalıcıdır.
  * Boş metin HTTP 200'e rağmen BAŞARISIZLIKTIR: sahte yanıt üretilmez.
  * Konak denetimi `konak_kontrol` içindedir ve kurucu tarafından YALNIZCA
    `izinli_konaklar` bir küme verilmişse çalıştırılır.

Modül düzeyinde `import time`, `urllib.request`, `urllib.error`, `json`, `sys`
ve `os` ile içe aktarılır; tüketici testleri bu NAMES üzerinden yama yapar
(`llm.urllib.request.urlopen`, `time.sleep`), bu yüzden `from x import y`
bağlaması kullanılmaz.
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

__surum__ = "0.1.0"

__all__ = [
    "__surum__",
    "DEFAULT_BASE_URL",
    "DEFAULT_MODEL",
    "IZINLI_KONAKLAR",
    "LLMError",
    "LLMClient",
    "konak_kontrol",
    "CorLLMClient",
]

#: cor adresi ortam değişkeniyle değiştirilebilir.
DEFAULT_BASE_URL = os.environ.get("COR_BASE_URL", "http://127.0.0.1:8787")

#: Varsayılan model. Tüketici repolar kendi varsayılanlarını kurucuya geçirir.
DEFAULT_MODEL = os.environ.get("COR_MODEL", "stealth/space-bunny-alpha")

#: Bağlanılabilecek konak adları. cor YERELDİR: dışarıya çıkmak bu modülün işi
#: değildir, bu yüzden loopback dışı adresler reddedilir.
IZINLI_KONAKLAR = frozenset({"127.0.0.1", "localhost", "::1", "[::1]"})


class LLMError(RuntimeError):
    """LLM'e erişilemedi ya da beklenmeyen bir yanıt biçimi geldi."""

    def __init__(self, mesaj: str, status: int | None = None) -> None:
        super().__init__(mesaj)
        #: HTTP hatasıysa durum kodu; bağlantı/şema hatasıysa `None`.
        self.status = status


@runtime_checkable
class LLMClient(Protocol):
    """Prompt alıp metin döndüren en küçük arayüz."""

    def complete(self, prompt: str) -> str: ...


def konak_kontrol(base_url: str, izinli: frozenset[str] = IZINLI_KONAKLAR) -> str:
    """`base_url`nin konak adını döner; şema geçersizse ya da konak `izinli`
    kümesinde değilse `LLMError` verir."""
    parcalar = urllib.parse.urlsplit(base_url)
    if parcalar.scheme not in ("http", "https"):
        raise LLMError(f"cor adresi geçersiz şema: {base_url!r}")
    konak = parcalar.hostname
    if konak is None or konak.lower() not in {k.lower() for k in izinli}:
        raise LLMError(
            f"cor adresi loopback olmalı, {konak!r} reddedildi. "
            "Bu araç yalnızca yerel cor proxy'sine bağlanır."
        )
    return konak


def _gecici_mi(hata: LLMError) -> bool:
    """Hata geçici mi? Yalnızca 5xx geçicidir.

    `status` biliniyorsa KOD karar verir. `status is None` ise (tüketici
    testlerinin `_post_once`'ı `status`suz `LLMError("cor proxy HTTP 502 ...")`
    ile değiştirdiği yol) mesajdaki `HTTP 5` ipucu kullanılır.
    """
    kod = hata.status
    if kod is not None:
        return 500 <= kod <= 599
    return "HTTP 5" in str(hata)


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
        *,
        max_tokens: int = 4000,
        izinli_konaklar: frozenset[str] | None = IZINLI_KONAKLAR,
        baslat_ipucu: str = "cor start",
    ) -> None:
        if izinli_konaklar is not None:
            # kuruluşta reddet: ağ yanlışa gitmesin
            konak_kontrol(base_url, izinli_konaklar)
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        self.max_tokens = max_tokens
        self.izinli_konaklar = izinli_konaklar
        self.baslat_ipucu = baslat_ipucu

    def _post_once(self, prompt: str) -> str:
        payload = json.dumps(
            {
                "model": self.model,
                "max_tokens": self.max_tokens,
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
            raise LLMError(
                f"cor proxy HTTP {hata.code} döndü: {ayrinti[:500]}", status=hata.code
            ) from hata
        except (urllib.error.URLError, OSError) as hata:
            raise LLMError(
                f"cor proxy'ye ({self.base_url}) bağlanılamadı: {hata}. "
                f"Önce `{self.baslat_ipucu}` ile proxy'yi başlatmayı deneyin."
            ) from hata

        try:
            ayristirilmis = json.loads(govde)
            metin = ayristirilmis["content"][0]["text"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as hata:
            raise LLMError(
                f"cor proxy'den beklenmeyen yanıt biçimi: {govde[:500]}"
            ) from hata

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
                if not _gecici_mi(hata) or deneme == self.max_retries:
                    raise
                bekleme = self.retry_backoff * (2**deneme)
                print(
                    f"Geçici sağlayıcı hatası, {bekleme:.0f}s sonra tekrar denenecek "
                    f"({deneme + 1}/{self.max_retries}): {hata}",
                    file=sys.stderr,
                )
                time.sleep(bekleme)
        raise son_hata if son_hata else LLMError("Bilinmeyen hata")
