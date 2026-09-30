"""NotebookLM köprü sunucusuna konuşan ince HTTP istemcisi.

Bu modül NotebookLM'i kendisi sürmez, tarayıcı otomasyonu yapmaz, Google'a
bağlanmaz. Yalnızca kullanıcının kendi makinesinde `npm run start:http` ile
ayakta tuttuğu sunucuya HTTP istekleri gönderir.

Tasarım notları:
  * Ekstra bağımlılık yok: `urllib.request` kullanılır (narrator.py'deki
    `CorLLMClient` ile aynı yaklaşım).
  * Sunucu her yanıtta `{"success": bool, ...}` döner. `success: false` hiçbir
    zaman yutulmaz: `BridgeError` yükselir. "Başardım ama hiçbir şey olmadı"
    durumu bu repodaki her modülün ortak kuralına ayrıdır.
  * Gerçek Google Audio Overview üretimi dakikalar sürebildiği için
    varsayılan zaman aşımı cömerttir (15 dakika).
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_BASE_URL = "http://127.0.0.1:3000"

# Not: gerçek Audio Overview üretimi dakikalar sürebildiği için en az 10 dakika.
DEFAULT_TIMEOUT = 900.0

# /content/generate içinde yalnızca bu tip desteklenir; diğer Studio türleri
# (presentation, report, infographic, data_table, video) kapsam dışıdır.
CONTENT_TYPE_AUDIO_OVERVIEW = "audio_overview"

# Bir sistem köküne yazmayı reddetmek için: bu yolların altına "çıktı dosyası"
# anlamında inmek makul değil.
_FORBIDDEN_OUTPUT_ROOTS = frozenset({"/", "/bin", "/boot", "/dev", "/etc", "/lib", "/proc", "/root", "/sbin", "/sys", "/usr", "/var"})

CONNECT_HELP = (
    "NotebookLM köprü sunucusuna bağlanılamadı — önce kendi makinende "
    "`npm install @roomi-fields/notebooklm-mcp && npm run start:http` "
    "çalıştırdığından ve `npm run setup-auth` ile giriş yaptığından emin ol."
)

AUTH_HELP = (
    "NotebookLM köprüsü çalışıyor ama Google girişi yapılmamış. Köprü sunucusunun "
    "bulunduğu terminalde `npm run setup-auth` komutunu çalıştırıp tarayıcıda "
    "elle giriş yap."
)


class BridgeError(RuntimeError):
    """Köprü sunucusuyla konuşulurken ya da sunucu bir adımı reddettiğinde yükselir."""


class NotAuthenticatedError(BridgeError):
    """Sunucu ayakta ama Google girişi yapılmamış."""


def _error_text(payload: Any) -> str:
    """Sunucunun döndüğü hata metnini insan okunur hale getirir."""
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, str) and error.strip():
            return error.strip()
        if error:
            return json.dumps(error, ensure_ascii=False)
    return "sunucu hata metni vermedi"


class NotebookLMBridge:
    """Kullanıcının makinesindeki NotebookLM HTTP sunucusuna ince istemci."""

    def __init__(
        self, base_url: str = DEFAULT_BASE_URL, timeout: float = DEFAULT_TIMEOUT
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    # ------------------------------------------------------------------ #
    # Taşıma katmanı
    # ------------------------------------------------------------------ #

    def _request(
        self, method: str, path: str, *, query: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Tek bir HTTP isteği atar ve çözülmüş JSON gövdesini döner.

        Bağlantı hataları ve HTTP/JSON hataları `BridgeError` olur; sunucunun
        `success: false` demesi bu katmanda hata DEĞİLDİR — çağıran karar verir.
        """
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{urllib.parse.urlencode(query)}"

        data: bytes | None = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")

        request = urllib.request.Request(
            url,
            data=data,
            headers={"content-type": "application/json", "accept": "application/json"},
            method=method,
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise BridgeError(
                f"NotebookLM köprüsü {method} {path} için HTTP {exc.code} döndü: {detail}"
            ) from exc
        except (urllib.error.URLError, ConnectionRefusedError, socket.timeout, OSError) as exc:
            raise BridgeError(f"{CONNECT_HELP} (Detay: {exc})") from exc

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise BridgeError(
                f"NotebookLM köprüsünden beklenmeyen yanıt biçimi ({method} {path}): "
                f"{raw[:500]}"
            ) from exc
        if not isinstance(parsed, dict):
            raise BridgeError(
                f"NotebookLM köprüsü beklenmeyen bir gövde döndü ({method} {path}): {raw[:500]}"
            )
        return parsed

    @staticmethod
    def _require_success(payload: dict[str, Any], action: str) -> dict[str, Any]:
        """`success: false` ise istisna fırlatır; `data` sözlüğünü döner."""
        if not payload.get("success"):
            raise BridgeError(f"{action} başarısız: {_error_text(payload)}")
        data = payload.get("data")
        return data if isinstance(data, dict) else {}

    # ------------------------------------------------------------------ #
    # Köprü uçları
    # ------------------------------------------------------------------ #

    def health(self) -> dict[str, Any]:
        """`GET /health`. Sunucu ayaktaysa `{"success": true, "data": {...}}`.

        `success: false` burada istisna fırlatmaz: "ayakta ama sağlıksız" ile
        "hiç bağlanamıyor" ayrımını `is_authenticated()`/CLI mesajı yapsın.
        """
        return self._request("GET", "/health")

    def is_authenticated(self) -> bool:
        """`/health` yanıtından Google giriş durumunu çıkarır."""
        payload = self.health()
        if not payload.get("success"):
            return False
        data = payload.get("data")
        return bool(isinstance(data, dict) and data.get("authenticated"))

    def create_notebook(self, name: str) -> str:
        """`POST /notebooks/create` → notebook URL'sini döner."""
        if not name or not name.strip():
            raise BridgeError("Notebook adı boş olamaz.")
        payload = self._request("POST", "/notebooks/create", body={"name": name})
        data = self._require_success(payload, "Notebook oluşturma")
        url = data.get("notebook_url")
        if not isinstance(url, str) or not url.strip():
            raise BridgeError(
                "Notebook oluşturuldu yanıtında notebook_url yok; devam edilemez."
            )
        return url.strip()

    def add_text_source(
        self, notebook_url: str, text: str, title: str, session_id: str | None = None
    ) -> None:
        """`POST /content/sources` ile anlatıyı notebook'a metin kaynağı olarak ekler."""
        if not text or not text.strip():
            raise BridgeError("Kaynak metni boş; notebook'a boş kaynak eklenemez.")
        body: dict[str, Any] = {
            "source_type": "text",
            "text": text,
            "title": title,
            "notebook_url": notebook_url,
        }
        if session_id:
            body["session_id"] = session_id
        payload = self._request("POST", "/content/sources", body=body)
        self._require_success(payload, "Kaynak ekleme")

    def generate_audio_overview(
        self,
        notebook_url: str,
        custom_instructions: str | None = None,
        language: str | None = None,
        session_id: str | None = None,
    ) -> None:
        """`POST /content/generate` ile Audio Overview üretir (yavaş olabilir)."""
        body: dict[str, Any] = {
            "content_type": CONTENT_TYPE_AUDIO_OVERVIEW,
            "notebook_url": notebook_url,
        }
        if custom_instructions:
            body["custom_instructions"] = custom_instructions
        if language:
            body["language"] = language
        if session_id:
            body["session_id"] = session_id
        payload = self._request("POST", "/content/generate", body=body)
        self._require_success(payload, "Audio Overview üretimi")

    def download_audio_overview(
        self, notebook_url: str, output_path: Path, session_id: str | None = None
    ) -> Path:
        """`GET /content/download` ile Audio Overview'u indirir, yolu döner."""
        target = self._prepare_output_path(output_path)
        query = {
            "content_type": CONTENT_TYPE_AUDIO_OVERVIEW,
            "output_path": str(target),
            "notebook_url": notebook_url,
        }
        if session_id:
            query["session_id"] = session_id
        payload = self._request("GET", "/content/download", query=query)
        data = self._require_success(payload, "Audio Overview indirme")

        # Sunucu "indirdim" dese de dosya yoksa başarı saymayız.
        if not target.is_file():
            reported = data.get("filePath") or data.get("file_path")
            reported_path = Path(reported) if isinstance(reported, str) and reported else None
            if reported_path is None or not reported_path.is_file():
                raise BridgeError(
                    f"Köprü indirmeyi başarılı bildirdi ama dosya diskte yok: {target}"
                )
            target = reported_path
        return target

    # ------------------------------------------------------------------ #
    # Çıktı yolu güvenliği (asgari sağduyu kontrolü)
    # ------------------------------------------------------------------ #

    @staticmethod
    def _prepare_output_path(output_path: Path) -> Path:
        """İndirme hedefini mutlak yola çevirir ve saçma bir kökü reddeder.

        Bu yol bizim kendi makinemizdeki bir çıktı dosyası; uzak sunucuya
        güvenilmeyen bir yazma hedefi olarak gönderilse bile sistemin kök
        dizinine yazmayı engellemek için basit bir kontrol yeter.
        """
        target = Path(output_path).expanduser().resolve()
        if str(target) in _FORBIDDEN_OUTPUT_ROOTS or target.parent == target:
            raise BridgeError(
                f"Geçersiz çıktı yolu: {target}. Kök dizinine yazılmayacak."
            )
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise BridgeError(
                f"Çıktı dizini oluşturulamadı: {target.parent} ({exc})"
            ) from exc
        return target
