"""Telegram modülü testleri (gerçek ağa çıkmaz, urlopen monkeypatch)."""

from __future__ import annotations

import json
import logging
import os
from unittest.mock import patch

import pytest

from tekrar.telegram import (
    TOKEN_ENV,
    CHAT_ENV,
    MAX_MESAJ,
    kacis,
    kart_mesaji,
    gonder,
)


class TestKacis:
    """kacis fonksiyonu testleri."""

    def test_tum_ozel_karakterler(self) -> None:
        """Telegram MarkdownV2 özel karakterlerinin tümü kaçışlanır."""
        metin = "_*[]()~`>#+-=|{}.!\\"
        beklenen = r"\_\*\[\]\(\)\~\`\>\#\+\-\=\|\{\}\.\!\\"
        assert kacis(metin) == beklenen

    def test_ters_egik_cizgi(self) -> None:
        """Ters eğik çizgi kaçışlanır."""
        assert kacis("\\") == r"\\"

    def test_yeni_satir_korunur(self) -> None:
        """Yeni satır karakterleri korunur."""
        assert kacis("satir1\nsatir2") == "satir1\nsatir2"

    def test_bos_metin(self) -> None:
        """Boş metin boş döner."""
        assert kacis("") == ""

    def test_normal_metin_degismez(self) -> None:
        """Özel karakter içermeyen metin aynen kalır."""
        assert kacis("Merhaba Dunya") == "Merhaba Dunya"


class TestKartMesaji:
    """kart_mesaji fonksiyonu testleri."""

    def test_spoiler_bicimi_ve_numaralama(self) -> None:
        """Spoiler biçimi (||...||) ve numaralama (1\\. ) doğrudur."""
        ciftler = [("Soru 1?", "Cevap 1"), ("Soru 2?", "Cevap 2")]
        mesaj = kart_mesaji(ciftler)
        assert "*Bugünün tekrar kartları*" in mesaj
        assert "1\\. Soru 1?" in mesaj
        assert "||Cevap 1||" in mesaj
        assert "2\\. Soru 2?" in mesaj
        assert "||Cevap 2||" in mesaj

    def test_bos_liste(self) -> None:
        """Boş liste boş string döndürür."""
        assert kart_mesaji([]) == ""

    def test_maks_uzunluk_siniri(self) -> None:
        """Mesaj MAX_MESAJ'ı aşmaz; sığmayan kartlar çıkarılır."""
        uzun_soru = "S" * 2000
        uzun_cevap = "C" * 2000
        ciftler = [(uzun_soru, uzun_cevap), ("Kısa?", "Kısa")]
        mesaj = kart_mesaji(ciftler)
        assert len(mesaj) <= MAX_MESAJ
        # En az bir kart sığmalı
        assert "1\\." in mesaj

    def test_yarim_kacis_dizisi_olmaz(self) -> None:
        """Mesajın sonunda yarım kaçış dizisi (tek başına \\) kalmaz."""
        # Kaçış karakteri içeren cevap, sınırda kesilirse yarım kaçış kalmamalı
        cevap = "x" * 4000 + "\\"  # Son karakter kaçış
        ciftler = [("Soru?", cevap)]
        mesaj = kart_mesaji(ciftler)
        assert len(mesaj) <= MAX_MESAJ
        # Son karakter \ olmamalı (kaçışlı ... olmalı)
        assert not mesaj.rstrip().endswith("\\")

    def test_tek_kart_sigmazsa_cevap_kisaltilir(self) -> None:
        """Tek kart bile sığmazsa cevap kısaltılır ve … eklenir."""
        # Başlık + numara + spoiler etiketleri = ~50 karakter
        # Kalan 4046 karaktere sığacak kadar uzun cevap
        cevap = "C" * 5000
        ciftler = [("Soru?", cevap)]
        mesaj = kart_mesaji(ciftler)
        assert len(mesaj) <= MAX_MESAJ
        assert mesaj.endswith("…||")
        assert not mesaj.rstrip("|").endswith("\\")

    def test_ozel_karakterler_kacislanir(self) -> None:
        """Soru ve cevaptaki özel karakterler kaçışlanır."""
        ciftler = [("Soru *kalın*?", "Cevap _italik_")]
        mesaj = kart_mesaji(ciftler)
        assert "Soru \\*kalın\\*" in mesaj
        assert "Cevap \\_italik\\_" in mesaj


class TestGonder:
    """gonder fonksiyonu testleri."""

    def test_basari(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Başarılı yanıt (200 + ok:true) => True."""
        def mock_urlopen(req, timeout=None):
            class MockResponse:
                status = 200
                def read(self):
                    return b'{"ok": true}'
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    pass
            return MockResponse()

        with patch("tekrar.telegram.urllib.request.urlopen", mock_urlopen):
            sonuc = gonder("test", token="123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef", chat_id="123456789")
            assert sonuc is True

    def test_basari_gonderilen_istek(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Gönderilen isteğin URL, JSON gövde, parse_mode doğrulanır."""
        captured = {}

        def mock_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            captured["method"] = req.get_method()
            captured["headers"] = {k.lower(): v for k, v in req.header_items()}
            captured["data"] = json.loads(req.data.decode("utf-8")) if req.data else None

            class MockResponse:
                status = 200
                def read(self):
                    return b'{"ok": true}'
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    pass
            return MockResponse()

        with patch("tekrar.telegram.urllib.request.urlopen", mock_urlopen):
            gonder("merhaba", token="123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef", chat_id="123456789")

        assert captured["url"] == "https://api.telegram.org/bot123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef/sendMessage"
        assert captured["method"] == "POST"
        assert captured["headers"]["content-type"] == "application/json"
        assert captured["data"]["chat_id"] == "123456789"
        assert captured["data"]["text"] == "merhaba"
        assert captured["data"]["parse_mode"] == "MarkdownV2"
        assert captured["data"]["disable_web_page_preview"] is True

    def test_token_bicim_hatasi_urlopen_cagrilmaz(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Geçersiz token formatında urlopen HİÇ çağrılmaz."""
        cagirildi = {"count": 0}

        def mock_urlopen(*args, **kwargs):
            cagirildi["count"] += 1
            raise AssertionError("urlopen çağrılmamalıydı")

        with patch("tekrar.telegram.urllib.request.urlopen", mock_urlopen):
            sonuc = gonder("test", token="gecersiz", chat_id="123456789")
            assert sonuc is False
            assert cagirildi["count"] == 0

    def test_chat_id_bicim_hatasi_urlopen_cagrilmaz(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Geçersiz chat_id formatında urlopen HİÇ çağrılmaz."""
        cagirildi = {"count": 0}

        def mock_urlopen(*args, **kwargs):
            cagirildi["count"] += 1
            raise AssertionError("urlopen çağrılmamalıydı")

        with patch("tekrar.telegram.urllib.request.urlopen", mock_urlopen):
            sonuc = gonder("test", token="123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef", chat_id="gecersiz")
            assert sonuc is False
            assert cagirildi["count"] == 0

    def test_ortamdan_okuma(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Token ve chat_id ortam değişkeninden alınır."""
        monkeypatch.setenv(TOKEN_ENV, "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef")
        monkeypatch.setenv(CHAT_ENV, "123456789")

        def mock_urlopen(req, timeout=None):
            class MockResponse:
                status = 200
                def read(self):
                    return b'{"ok": true}'
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    pass
            return MockResponse()

        with patch("tekrar.telegram.urllib.request.urlopen", mock_urlopen):
            sonuc = gonder("test")
            assert sonuc is True

        monkeypatch.delenv(TOKEN_ENV, raising=False)
        monkeypatch.delenv(CHAT_ENV, raising=False)

    def test_http_error_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """HTTPError => False."""
        import urllib.error

        def mock_urlopen(*args, **kwargs):
            raise urllib.error.HTTPError("url", 400, "Bad Request", {}, None)

        with patch("tekrar.telegram.urllib.request.urlopen", mock_urlopen):
            sonuc = gonder("test", token="123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef", chat_id="123456789")
            assert sonuc is False

    def test_urlerror_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """URLError => False."""
        import urllib.error

        def mock_urlopen(*args, **kwargs):
            raise urllib.error.URLError("ağ hatası")

        with patch("tekrar.telegram.urllib.request.urlopen", mock_urlopen):
            sonuc = gonder("test", token="123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef", chat_id="123456789")
            assert sonuc is False

    def test_timeout_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """TimeoutError => False."""

        def mock_urlopen(*args, **kwargs):
            raise TimeoutError("zaman aşımı")

        with patch("tekrar.telegram.urllib.request.urlopen", mock_urlopen):
            sonuc = gonder("test", token="123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef", chat_id="123456789")
            assert sonuc is False

    def test_bozuk_json_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Bozuk JSON => False."""

        def mock_urlopen(req, timeout=None):
            class MockResponse:
                status = 200
                def read(self):
                    return b'bozuk json {'
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    pass
            return MockResponse()

        with patch("tekrar.telegram.urllib.request.urlopen", mock_urlopen):
            sonuc = gonder("test", token="123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef", chat_id="123456789")
            assert sonuc is False

    def test_ok_false_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """{"ok": false} => False."""

        def mock_urlopen(req, timeout=None):
            class MockResponse:
                status = 200
                def read(self):
                    return b'{"ok": false, "error_code": 400}'
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    pass
            return MockResponse()

        with patch("tekrar.telegram.urllib.request.urlopen", mock_urlopen):
            sonuc = gonder("test", token="123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef", chat_id="123456789")
            assert sonuc is False

    def test_hata_durumunda_token_sizmaz(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
        """Hata durumunda stdout/stderr'e token sızmaz."""
        import urllib.error

        def mock_urlopen(*args, **kwargs):
            raise urllib.error.URLError("ağ hatası")

        with patch("tekrar.telegram.urllib.request.urlopen", mock_urlopen):
            gonder("test", token="123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef", chat_id="123456789")

        captured = capsys.readouterr()
        assert "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef" not in captured.out
        assert "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef" not in captured.err

    def test_logda_token_yok(self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
        """Loglarda token görünmez (sabit mesaj)."""
        import urllib.error

        def mock_urlopen(*args, **kwargs):
            raise urllib.error.URLError("ağ hatası")

        with patch("tekrar.telegram.urllib.request.urlopen", mock_urlopen), caplog.at_level(logging.WARNING):
            gonder("test", token="123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef", chat_id="123456789")

        for record in caplog.records:
            assert "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef" not in record.getMessage()
            assert "token" not in record.getMessage().lower() or "geçersiz" in record.getMessage().lower()


import logging