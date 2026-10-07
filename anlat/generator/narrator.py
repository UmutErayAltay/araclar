"""Ham RepoScan verisini Türkçe teknik anlatıya (Markdown) dönüştürür.

LLM'e erişim `LLMClient` protokolü üzerinden soyutlanmıştır; testler sahte bir
implementasyon kullanır, gerçek implementasyon yerel cor proxy'sine HTTP ile
bağlanır (ortak istemci: `generator/_corclient.py`, kaynak repo kökündeki
`corclient.py`). LLM çağrısı başarısız olursa sahte/boş bir anlatı üretmek yerine
`NarratorError` yükselir.
"""

from __future__ import annotations

# Testler bu adlar üzerinden yama yapabilir (`narrator.urllib.request.urlopen`, `narrator.time.sleep`).
import json  # noqa: F401
import sys  # noqa: F401
import time  # noqa: F401
import urllib.error  # noqa: F401
import urllib.request  # noqa: F401
from dataclasses import dataclass
from typing import Protocol, runtime_checkable  # noqa: F401

from generator import _corclient
from generator._corclient import LLMClient  # noqa: F401
from generator.scanner import RepoScan

DEFAULT_BASE_URL = "http://127.0.0.1:8787"
DEFAULT_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"

MAX_TOKENS = 8000

#: Bağlanılabilecek konak adları. cor YERELDİR; depo geçmişi/dokümanları başka bir makineye gitmesin
#: diye loopback dışı adresler kuruluşta reddedilir.
IZINLI_KONAKLAR = frozenset({"127.0.0.1", "localhost", "::1", "[::1]"})

REQUIRED_SECTIONS = (
    "## Özellikler ve Zaman Çizelgesi",
    "## Teknoloji Seçimleri ve Nedenleri",
    "## Önemli Tasarım Kararları",
)

MIN_NARRATION_CHARS = 200


class NarratorError(_corclient.LLMError):
    """Anlatı üretilemediğinde yükselir.

    `corclient.LLMError`'un alt sınıfıdır: ortak istemcinin yeniden deneme mantığı
    (yalnız 5xx) bu hatayı da tanır, `except NarratorError` ise eskisi gibi çalışır.
    """


class CorLLMClient(_corclient.CorLLMClient):
    """Yerel cor proxy'sine Anthropic uyumlu HTTP ile bağlanır (bkz. `_corclient`).

    Neden HTTP ve `cor claude -p` subprocess'i değil: proxy zaten Anthropic uyumlu
    `/v1/messages` ucunu (kimlik doğrulama gerekmeden) sunuyor; subprocess'e göre
    test edilebilir, zaman aşımları ve hata mesajları doğrudan kontrol edilebilir.
    Ortak istemcinin her hatası (kurulumdaki konak denetimi dahil) `NarratorError`'a çevrilir.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        timeout: float = 300.0,
        max_retries: int = 3,
        retry_backoff: float = 3.0,
    ) -> None:
        try:
            super().__init__(
                base_url,
                model,
                timeout,
                max_retries,
                retry_backoff,
                max_tokens=MAX_TOKENS,
                izinli_konaklar=IZINLI_KONAKLAR,
                baslat_ipucu="cor claude",
            )
        except NarratorError:
            raise
        except _corclient.LLMError as hata:  # loopback dışı / geçersiz adres
            raise NarratorError(str(hata), status=hata.status) from hata

    def _post_once(self, prompt: str) -> str:
        try:
            return super()._post_once(prompt)
        except NarratorError:
            raise
        except _corclient.LLMError as hata:
            raise NarratorError(str(hata), status=hata.status) from hata


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
