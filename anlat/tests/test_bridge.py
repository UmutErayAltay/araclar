"""bridge/client.py testleri.

Gerçek ağ (NotebookLM) çağrısı YAPILMAZ; onun yerine Python stdlib'in
`http.server`'ı ile gerçek bir soket üzerinde çalışan sahte bir köprü sunucusu
kaldırılır. Böylece istek/cevap ayrımı, zaman aşımı ve hata yolu mock'lanmadan,
gerçek bir localhost bağlantısı üzerinden sınanır.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from bridge.client import (
    AUTH_HELP,
    CONNECT_HELP,
    DEFAULT_BASE_URL,
    BridgeError,
    NotebookLMBridge,
)

AUDIO_BYTES = b"ID3-fake-mp3-payload" * 32


class FakeBridgeHandler(BaseHTTPRequestHandler):
    """Sahte NotebookLM köprüsü: kaydettiği istekleri testlere açar."""

    protocol_version = "HTTP/1.1"

    def log_message(self, *args: Any) -> None:  # pytest çıktısını kirletmesin
        return

    # -- yardımcılar --------------------------------------------------- #

    @property
    def fake(self) -> "FakeBridgeServer":
        # socketserver, handler örneğine `server` niteliğini kendisi atar.
        return self.server  # type: ignore[no-any-return]

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("content-length") or 0)
        raw = self.rfile.read(length) if length else b""
        return json.loads(raw.decode("utf-8")) if raw else {}

    def _respond(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # -- yönlendirme --------------------------------------------------- #

    def do_GET(self) -> None:  # noqa: N802 - stdlib arayüzü
        parsed = urllib.parse.urlparse(self.path)
        query = dict(urllib.parse.parse_qsl(parsed.query))
        self.fake.requests.append({"method": "GET", "path": parsed.path, "query": query})
        route = self.fake.routes.get(("GET", parsed.path))

        if parsed.path == "/health" and self.fake.health_delay:
            time.sleep(self.fake.health_delay)
        if parsed.path == "/content/download" and self.fake.download_delay:
            time.sleep(self.fake.download_delay)

        if route is None:
            self._respond(404, {"success": False, "error": f"bilinmeyen uç: {parsed.path}"})
            return
        self._respond(200, route)

    def do_POST(self) -> None:  # noqa: N802 - stdlib arayüzü
        parsed = urllib.parse.urlparse(self.path)
        body = self._read_json()
        self.fake.requests.append(
            {"method": "POST", "path": parsed.path, "body": body}
        )
        if parsed.path == "/content/generate" and self.fake.generate_delay:
            time.sleep(self.fake.generate_delay)

        route = self.fake.routes.get(("POST", parsed.path))
        if route is None:
            self._respond(404, {"success": False, "error": f"bilinmeyen uç: {parsed.path}"})
            return
        self._respond(200, route)


class FakeBridgeServer(ThreadingHTTPServer):
    """Route tablosu ve istek günlüğü tutan sahte köprü sunucusu."""

    daemon_threads = True

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), FakeBridgeHandler)
        self.routes: dict[tuple[str, str], dict[str, Any]] = {}
        self.requests: list[dict[str, Any]] = []
        self.health_delay = 0.0
        self.generate_delay = 0.0
        self.download_delay = 0.0
        self._thread = threading.Thread(target=self.serve_forever, daemon=True)
        self._thread.start()

    @property
    def base_url(self) -> str:
        host, port = self.server_address[0], self.server_address[1]
        return f"http://{host}:{port}"

    def route(self, method: str, path: str, payload: dict[str, Any]) -> None:
        self.routes[(method, path)] = payload

    def close(self) -> None:
        self.shutdown()
        self.server_close()
        self._thread.join(timeout=5)


@pytest.fixture
def fake_bridge() -> "FakeBridgeServer":
    server = FakeBridgeServer()
    try:
        yield server
    finally:
        server.close()


def authenticated_health() -> dict[str, Any]:
    return {
        "success": True,
        "data": {
            "status": "ok",
            "authenticated": True,
            "active_sessions": 0,
            "max_sessions": 5,
        },
    }


def last_body(server: "FakeBridgeServer", path: str) -> dict[str, Any]:
    for entry in reversed(server.requests):
        if entry["path"] == path and entry["method"] == "POST":
            return entry["body"]
    raise AssertionError(f"{path} için POST isteği kaydedilmedi: {server.requests}")


# --------------------------------------------------------------------- #
# Bağlantı kurulamazsa
# --------------------------------------------------------------------- #


def test_connection_refused_gives_setup_instructions() -> None:
    """Kapalı bir porta bağlanınca kullanıcıya ne yapması gerektiği söylenmeli."""
    # Port 9 (discard) bu ortamda kapalı; bağlantı reddedilmesi beklenir.
    bridge = NotebookLMBridge(base_url="http://127.0.0.1:9", timeout=5.0)

    with pytest.raises(BridgeError) as excinfo:
        bridge.health()

    assert "npm run start:http" in str(excinfo.value)
    assert "npm run setup-auth" in str(excinfo.value)
    assert "127.0.0.1:9" not in CONNECT_HELP  # yardım metni sabit bir komut listesi
    assert "bağlanılamadı" in str(excinfo.value)


def test_default_base_url_is_localhost_3000() -> None:
    assert DEFAULT_BASE_URL == "http://127.0.0.1:3000"
    assert NotebookLMBridge().base_url == "http://127.0.0.1:3000"


# --------------------------------------------------------------------- #
# /health
# --------------------------------------------------------------------- #


def test_health_success_and_is_authenticated(fake_bridge: FakeBridgeServer) -> None:
    fake_bridge.route("GET", "/health", authenticated_health())
    bridge = NotebookLMBridge(base_url=fake_bridge.base_url, timeout=10.0)

    payload = bridge.health()

    assert payload["success"] is True
    assert payload["data"]["status"] == "ok"
    assert bridge.is_authenticated() is True
    assert [r["path"] for r in fake_bridge.requests] == ["/health", "/health"]


def test_health_failure_is_reported_not_swallowed(
    fake_bridge: FakeBridgeServer,
) -> None:
    """Sunucu ayakta ama `success: false` diyorsa bunu da bildirmeliyiz."""
    fake_bridge.route("GET", "/health", {"success": False, "error": "oturum yok"})
    bridge = NotebookLMBridge(base_url=fake_bridge.base_url, timeout=10.0)

    payload = bridge.health()

    assert payload["success"] is False
    assert payload["error"] == "oturum yok"
    assert bridge.is_authenticated() is False


def test_health_not_authenticated_says_setup_auth(fake_bridge: FakeBridgeServer) -> None:
    fake_bridge.route(
        "GET",
        "/health",
        {"success": True, "data": {"status": "ok", "authenticated": False}},
    )
    bridge = NotebookLMBridge(base_url=fake_bridge.base_url, timeout=10.0)

    assert bridge.is_authenticated() is False
    assert "setup-auth" in AUTH_HELP


def test_http_error_status_raises(fake_bridge: FakeBridgeServer) -> None:
    """404 gibi bir durum kodu BridgeError'a dönüşmeli."""
    bridge = NotebookLMBridge(base_url=fake_bridge.base_url, timeout=10.0)

    with pytest.raises(BridgeError, match="HTTP 404"):
        bridge.health()


def test_non_json_response_raises(fake_bridge: FakeBridgeServer) -> None:
    """JSON olmayan gövde sessizce yutulmamalı."""

    class HtmlHandler(FakeBridgeHandler):
        def do_GET(self) -> None:  # noqa: N802
            body = b"<html>not json</html>"
            self.send_response(200)
            self.send_header("content-type", "text/html")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    fake_bridge.RequestHandlerClass = HtmlHandler  # type: ignore[attr-defined]
    bridge = NotebookLMBridge(base_url=fake_bridge.base_url, timeout=10.0)

    with pytest.raises(BridgeError, match="yanıt biçimi"):
        bridge.health()


# --------------------------------------------------------------------- #
# /notebooks/create
# --------------------------------------------------------------------- #


def test_create_notebook_returns_url(fake_bridge: FakeBridgeServer) -> None:
    fake_bridge.route(
        "POST",
        "/notebooks/create",
        {"success": True, "data": {"notebook_url": "https://notebooklm.google.com/abc123"}},
    )
    bridge = NotebookLMBridge(base_url=fake_bridge.base_url, timeout=10.0)

    url = bridge.create_notebook("Örnek Depo")

    assert url == "https://notebooklm.google.com/abc123"
    assert last_body(fake_bridge, "/notebooks/create") == {"name": "Örnek Depo"}


def test_create_notebook_success_false_raises(fake_bridge: FakeBridgeServer) -> None:
    fake_bridge.route(
        "POST", "/notebooks/create", {"success": False, "error": "login gerekli"}
    )
    bridge = NotebookLMBridge(base_url=fake_bridge.base_url, timeout=10.0)

    with pytest.raises(BridgeError, match="Notebook oluşturma başarısız: login gerekli"):
        bridge.create_notebook("Örnek Depo")


def test_create_notebook_without_url_raises(fake_bridge: FakeBridgeServer) -> None:
    """success:true olsa bile url yoksa ilerlememeliyiz."""
    fake_bridge.route("POST", "/notebooks/create", {"success": True, "data": {"id": "1"}})
    bridge = NotebookLMBridge(base_url=fake_bridge.base_url, timeout=10.0)

    with pytest.raises(BridgeError, match="notebook_url yok"):
        bridge.create_notebook("Örnek Depo")


def test_create_notebook_rejects_blank_name(fake_bridge: FakeBridgeServer) -> None:
    bridge = NotebookLMBridge(base_url=fake_bridge.base_url, timeout=10.0)

    with pytest.raises(BridgeError, match="adı boş"):
        bridge.create_notebook("   ")


# --------------------------------------------------------------------- #
# /content/sources
# --------------------------------------------------------------------- #


def test_add_text_source_sends_expected_body(fake_bridge: FakeBridgeServer) -> None:
    fake_bridge.route("POST", "/content/sources", {"success": True, "data": {"id": "s1"}})
    bridge = NotebookLMBridge(base_url=fake_bridge.base_url, timeout=10.0)

    bridge.add_text_source("https://nb/1", "## Anlatı\niçerik", "Örnek Depo Anlatısı")

    body = last_body(fake_bridge, "/content/sources")
    assert body["source_type"] == "text"
    assert body["text"] == "## Anlatı\niçerik"
    assert body["title"] == "Örnek Depo Anlatısı"
    assert body["notebook_url"] == "https://nb/1"
    assert "session_id" not in body


def test_add_text_source_failure_raises(fake_bridge: FakeBridgeServer) -> None:
    fake_bridge.route(
        "POST", "/content/sources", {"success": False, "error": "notebook bulunamadı"}
    )
    bridge = NotebookLMBridge(base_url=fake_bridge.base_url, timeout=10.0)

    with pytest.raises(BridgeError, match="Kaynak ekleme başarısız: notebook bulunamadı"):
        bridge.add_text_source("https://nb/1", "metin", "başlık")


def test_add_text_source_rejects_empty_text(fake_bridge: FakeBridgeServer) -> None:
    bridge = NotebookLMBridge(base_url=fake_bridge.base_url, timeout=10.0)

    with pytest.raises(BridgeError, match="boş"):
        bridge.add_text_source("https://nb/1", "  \n ", "başlık")


# --------------------------------------------------------------------- #
# /content/generate
# --------------------------------------------------------------------- #


def test_generate_audio_overview_body(fake_bridge: FakeBridgeServer) -> None:
    fake_bridge.route("POST", "/content/generate", {"success": True, "data": {"id": "c1"}})
    bridge = NotebookLMBridge(base_url=fake_bridge.base_url, timeout=10.0)

    bridge.generate_audio_overview(
        "https://nb/1", custom_instructions="teknoloji seçimlerine vurgu yap", language="tr"
    )

    body = last_body(fake_bridge, "/content/generate")
    assert body["content_type"] == "audio_overview"
    assert body["notebook_url"] == "https://nb/1"
    assert body["language"] == "tr"
    assert body["custom_instructions"] == "teknoloji seçimlerine vurgu yap"


def test_generate_audio_overview_omits_optional_fields(
    fake_bridge: FakeBridgeServer,
) -> None:
    """Sunucu dil istemiyorsa alanlar hiç gönderilmemeli (undefined -> null değil)."""
    fake_bridge.route("POST", "/content/generate", {"success": True, "data": {}})
    bridge = NotebookLMBridge(base_url=fake_bridge.base_url, timeout=10.0)

    bridge.generate_audio_overview("https://nb/1")

    body = last_body(fake_bridge, "/content/generate")
    assert set(body) == {"content_type", "notebook_url"}


def test_generate_audio_overview_times_out(fake_bridge: FakeBridgeServer) -> None:
    """Kısa timeout + geç cevap: istisna fırlatmalı, takılıp kalmamalı."""
    fake_bridge.route("POST", "/content/generate", {"success": True, "data": {}})
    fake_bridge.generate_delay = 2.0
    bridge = NotebookLMBridge(base_url=fake_bridge.base_url, timeout=0.3)

    started = time.monotonic()
    with pytest.raises(BridgeError) as excinfo:
        bridge.generate_audio_overview("https://nb/1")
    elapsed = time.monotonic() - started

    assert "bağlanılamadı" in str(excinfo.value)
    assert elapsed < 1.9  # gerçekten 2 saniyelik gecikmeyi bekleyip sonra bitmedi


def test_generate_audio_overview_failure_raises(fake_bridge: FakeBridgeServer) -> None:
    fake_bridge.route(
        "POST", "/content/generate", {"success": False, "error": "quota doldu"}
    )
    bridge = NotebookLMBridge(base_url=fake_bridge.base_url, timeout=10.0)

    with pytest.raises(BridgeError, match="Audio Overview üretimi başarısız: quota doldu"):
        bridge.generate_audio_overview("https://nb/1")


# --------------------------------------------------------------------- #
# /content/download
# --------------------------------------------------------------------- #


def test_download_writes_file_to_disk(fake_bridge: FakeBridgeServer, tmp_path: Path) -> None:
    def download_route(_payload: dict[str, Any]) -> dict[str, Any]:
        return {"success": True, "data": {"filePath": "", "size": len(AUDIO_BYTES)}}

    output = tmp_path / "ses" / "anlat.mp3"

    class WritingHandler(FakeBridgeHandler):
        """Sahte sunucu output_path'e gerçekten dosya yazar (dizin de kendisi açar)."""

        def do_GET(self) -> None:  # noqa: N802
            parsed = urllib.parse.urlparse(self.path)
            query = dict(urllib.parse.parse_qsl(parsed.query))
            self.fake.requests.append({"method": "GET", "path": parsed.path, "query": query})
            if parsed.path != "/content/download":
                super().do_GET()
                return
            destination = Path(query["output_path"])
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(AUDIO_BYTES)
            payload = download_route(query)
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    fake_bridge.RequestHandlerClass = WritingHandler  # type: ignore[attr-defined]
    bridge = NotebookLMBridge(base_url=fake_bridge.base_url, timeout=10.0)

    result = bridge.download_audio_overview("https://nb/1", output)

    assert result == output
    assert output.is_file()
    assert output.read_bytes() == AUDIO_BYTES
    query = fake_bridge.requests[-1]["query"]
    assert query["content_type"] == "audio_overview"
    assert query["notebook_url"] == "https://nb/1"
    assert query["output_path"] == str(output)


def test_download_failure_raises(fake_bridge: FakeBridgeServer, tmp_path: Path) -> None:
    fake_bridge.route(
        "GET", "/content/download", {"success": False, "error": "içerik henüz hazır değil"}
    )
    bridge = NotebookLMBridge(base_url=fake_bridge.base_url, timeout=10.0)

    with pytest.raises(BridgeError, match="içerik henüz hazır değil"):
        bridge.download_audio_overview("https://nb/1", tmp_path / "anlat.mp3")


def test_download_success_but_no_file_raises(
    fake_bridge: FakeBridgeServer, tmp_path: Path
) -> None:
    """Sunucu 'başardım' dese bile diskte dosya yoksa başarı sayılmaz."""
    fake_bridge.route("GET", "/content/download", {"success": True, "data": {"filePath": ""}})
    bridge = NotebookLMBridge(base_url=fake_bridge.base_url, timeout=10.0)

    with pytest.raises(BridgeError, match="dosya diskte yok"):
        bridge.download_audio_overview("https://nb/1", tmp_path / "anlat.mp3")


def test_download_falls_back_to_reported_path(
    fake_bridge: FakeBridgeServer, tmp_path: Path
) -> None:
    """Sunucu başka bir yola yazdıysa oradaki dosya bulunmalı."""
    actual = tmp_path / "sunucu-secili.mp3"
    actual.write_bytes(AUDIO_BYTES)
    fake_bridge.route(
        "GET", "/content/download", {"success": True, "data": {"filePath": str(actual)}}
    )
    bridge = NotebookLMBridge(base_url=fake_bridge.base_url, timeout=10.0)

    result = bridge.download_audio_overview("https://nb/1", tmp_path / "istenen.mp3")

    assert result == actual
    assert actual.is_file()


def test_download_rejects_system_root(fake_bridge: FakeBridgeServer) -> None:
    """'/' gibi absürt bir kök yazma hedefi kabul edilmemeli."""
    bridge = NotebookLMBridge(base_url=fake_bridge.base_url, timeout=10.0)

    with pytest.raises(BridgeError, match="Geçersiz çıktı yolu"):
        bridge.download_audio_overview("https://nb/1", Path("/"))


def test_download_creates_missing_parent_directory(tmp_path: Path) -> None:
    target = tmp_path / "yeni" / "dizin" / "anlat.mp3"

    prepared = NotebookLMBridge._prepare_output_path(target)

    assert prepared == target
    assert prepared.parent.is_dir()


def test_default_timeout_is_generous() -> None:
    """Gerçek Audio Overview dakikalar sürdüğü için varsayılan en az 10 dakika olmalı."""
    assert NotebookLMBridge().timeout >= 600.0


# --------------------------------------------------------------------- #
# CLI bağlantısı
# --------------------------------------------------------------------- #


def test_cli_sesli_defaults_bridge_to_port_3000() -> None:
    """`sesli` varsayılan olarak 3000'e bağlanmalı.

    Regresyon: cli.py'de `--bridge-url` boş bırakılıp `generator.narrator`'ın
    DEFAULT_BASE_URL (cor proxy, 8787) değeri kullanılırsa köprü istemcisi yanlış
    servise bağlanır.
    """
    from cli import build_parser

    args = build_parser().parse_args(["sesli", "."])

    assert args.bridge_url == "http://127.0.0.1:3000"
    assert NotebookLMBridge(base_url=args.bridge_url).base_url == "http://127.0.0.1:3000"


def test_cli_sesli_stops_when_bridge_is_down(
    sample_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Köprü kapalıyken `sesli` daha ilk adımda durmalı, yarım iş yapmamalı."""
    from cli import main

    code = main(["sesli", str(sample_repo), "--bridge-url", "http://127.0.0.1:9", "--timeout", "5"])

    err = capsys.readouterr().err
    assert code == 1
    assert "bağlanılamadı" in err
    assert "npm run start:http" in err
    # Depoyu tarayıp yarım çıktı bırakmamalı.
    assert not (sample_repo / "ANLATI.md").exists()


def test_cli_sesli_reports_missing_login_distinctly(
    fake_bridge: FakeBridgeServer, sample_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Sunucu ayakta ama giriş yokken 'sunucu çalışmıyor' demek yanlış olurdu."""
    from cli import main

    fake_bridge.route(
        "GET", "/health", {"success": True, "data": {"status": "ok", "authenticated": False}}
    )

    code = main(["sesli", str(sample_repo), "--bridge-url", fake_bridge.base_url])

    err = capsys.readouterr().err
    assert code == 1
    assert "girişi yapılmamış" in err
    assert "npm run setup-auth" in err
    assert not (sample_repo / "ANLATI.md").exists()


def test_sesli_uzak_base_url_hata_mesaji_ve_kod_1(
    fake_bridge: FakeBridgeServer, sample_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from cli import main

    fake_bridge.route("GET", "/health", {"success": True, "data": {"status": "ok", "authenticated": True}})

    kod = main(["sesli", str(sample_repo), "--bridge-url", fake_bridge.base_url, "--base-url", "http://ornek.com:8787"])

    err = capsys.readouterr().err
    assert kod == 1
    assert "Hata:" in err and "loopback" in err
    assert not (sample_repo / "ANLATI.md").exists()
