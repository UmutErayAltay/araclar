"""Ham RepoScan verisini Türkçe teknik anlatıya (Markdown) dönüştürür.

LLM'e erişim `LLMClient` protokolü üzerinden soyutlanmıştır; testler sahte bir
implementasyon kullanır, gerçek implementasyon yerel cor proxy'sine HTTP ile
bağlanır. LLM çağrısı başarısız olursa sahte/boş bir anlatı üretmek yerine
`NarratorError` yükselir.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from generator.scanner import RepoScan

DEFAULT_BASE_URL = "http://127.0.0.1:8787"
DEFAULT_MODEL = "stealth/space-bunny-alpha"

REQUIRED_SECTIONS = (
    "## Özellikler ve Zaman Çizelgesi",
    "## Teknoloji Seçimleri ve Nedenleri",
    "## Önemli Tasarım Kararları",
)

MIN_NARRATION_CHARS = 200


class NarratorError(RuntimeError):
    """Anlatı üretilemediğinde yükselir."""


@runtime_checkable
class LLMClient(Protocol):
    """Prompt alıp metin döndüren en küçük arayüz."""

    def complete(self, prompt: str) -> str: ...


class CorLLMClient:
    """Yerel cor proxy'sine Anthropic uyumlu HTTP ile bağlanır.

    Neden HTTP ve `cor claude -p` subprocess'i değil: proxy zaten
    Anthropic uyumlu `/v1/messages` ucunu (kimlik doğrulama gerekmeden) sunuyor;
    subprocess'e göre test edilebilir, zaman aşımları ve hata mesajları
    doğrudan kontrol edilebilir, ayrıca alt süreç yönetimi yok.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        timeout: float = 300.0,
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
                "max_tokens": 8000,
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
            raise NarratorError(
                f"cor proxy HTTP {exc.code} döndü: {detail[:500]}"
            ) from exc
        except (urllib.error.URLError, OSError) as exc:
            raise NarratorError(
                f"cor proxy'ye ({self.base_url}) bağlanılamadı: {exc}. "
                "Önce `cor claude` ile proxy'yi başlatmayı deneyin."
            ) from exc

        try:
            parsed = json.loads(body)
            text = parsed["content"][0]["text"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise NarratorError(
                f"cor proxy'den beklenmeyen yanıt biçimi: {body[:500]}"
            ) from exc

        # Boş metin, HTTP 200'e rağmen başarısızlıktır: sahte anlatı üretmeyelim.
        if not text or not text.strip():
            raise NarratorError(
                "LLM boş yanıt döndü (muhtemelen max_tokens kısa kaldı). "
                "Sahte anlatı üretmek yerine hata fırlatıldı."
            )
        return text

    def complete(self, prompt: str) -> str:
        """İsteği gönderir; sağlayıcının geçici hatalarında sınırlı sayıda tekrar dener."""
        last_error: NarratorError | None = None
        for attempt in range(self.max_retries + 1):
            try:
                return self._post_once(prompt)
            except NarratorError as exc:
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
        raise last_error if last_error else NarratorError("Bilinmeyen hata")


@dataclass
class NarrationResult:
    markdown: str
    model: str


def build_prompt(scan: RepoScan) -> str:
    """RepoScan'i LLM'e verilecek Türkçe istem metnine çevirir."""
    lines: list[str] = []
    lines.append(f"Depo adı: {scan.repo_name}")
    if scan.oldest_commit and scan.newest_commit:
        lines.append(
            f"Commit aralığı: {scan.oldest_commit.date} — {scan.newest_commit.date} "
            f"({len(scan.commits)} commit)"
        )
    lines.append("")

    lines.append("=== COMMITLER (eskiden yeniye) ===")
    for commit in scan.commits:
        lines.append(f"- {commit.date} {commit.short_hash} {commit.subject}")
    lines.append("")

    if scan.dependency_files:
        for dep in scan.dependency_files:
            note = " (kırpıldı)" if dep.truncated else ""
            lines.append(f"=== BAĞIMLILIK DOSYASI: {dep.path}{note} ===")
            lines.append(dep.history)
            lines.append("")

    for document in scan.documents:
        note = " (kırpıldı)" if document.truncated else ""
        lines.append(f"=== DOKÜMAN: {document.path}{note} ===")
        lines.append(document.content)
        lines.append("")

    lines.append("=== TALİMAT ===")
    lines.append(
        "Aşağıdaki git sinyallerine dayanarak bu projenin YAZILI teknik "
        "anlatımını Markdown olarak üret. Sadece veriden çıkarılabilenleri yaz; "
        "kanıtı olmayan iddialarda neyi varsaydığını açıkça belirt. Commit "
        "mesajları ve bağımlılık değişikliklerinin sırasından ne zaman ne "
        "eklendiğini çıkar."
    )
    lines.append("")
    lines.append("Anlatı tam olarak şu üç bölümü içermeli:")
    for section in REQUIRED_SECTIONS:
        lines.append(f"{section}")
    lines.append("")
    lines.append(
        "Türkçe yaz, her bölümü en az bir paragrafla doldur, Markdown başlık "
        "seviyelerini koru ve bölüm başlıklarını yukarıdaki metinle birebir aynı yaz. "
        "En üste depo adını içeren tek bir '# ' başlığı koy."
    )
    return "\n".join(lines)


def generate_narration(
    scan: RepoScan, client: LLMClient, required_sections: tuple[str, ...] = REQUIRED_SECTIONS
) -> NarrationResult:
    """Anlatıyı üretir; bölümler eksikse veya içerik yetersizse hata fıkseder."""
    try:
        markdown = client.complete(build_prompt(scan))
    except NarratorError:
        raise
    except Exception as exc:  # sahte istemci vb. beklenmeyen hatalar
        raise NarratorError(f"LLM çağrısı başarısız oldu: {exc}") from exc

    if not markdown or not markdown.strip():
        raise NarratorError("LLM boş anlatı döndürdü.")

    missing = [section for section in required_sections if section not in markdown]
    if missing:
        raise NarratorError(
            "Anlatı zorunlu bölümleri içermiyor: " + ", ".join(missing)
        )
    if len(markdown.strip()) < MIN_NARRATION_CHARS:
        raise NarratorError(
            f"Anlatı şüpheli biçimde kısa ({len(markdown.strip())} karakter); "
            "muhtemelen üretim tamamlanmadan kesildi."
        )

    model = getattr(client, "model", type(client).__name__)
    return NarrationResult(markdown=markdown.strip(), model=str(model))
