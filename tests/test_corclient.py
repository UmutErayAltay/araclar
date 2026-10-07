"""`corclient.py` davranış testleri — SOZLESME 5. bölüm kapsam listesi.

Her ağ etkileşimi gerçek bir yerel HTTP sunucusuna (`127.0.0.1`, boş port)
gider; sahte veri kullanılır, gerçek cor'a hiç gidilmez.
"""

from __future__ import annotations

import socket

import pytest

import corclient
from corclient import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    IZINLI_KONAKLAR,
    CorLLMClient,
    LLMClient,
    LLMError,
    konak_kontrol,
)
from conftest import FakeCorServer, messages_response


# --------------------------------------------------------------------- #
# Yapılandırma / sözleşme yüzeyi
# --------------------------------------------------------------------- #


def test_modul_surumu() -> None:
    assert corclient.__surum__ == "0.1.0"


def test_disa_acik_adlar_tam() -> None:
    """Sözleşmedeki adların hepsi `__all__`da ve gerçekten var."""
    beklenen = {
        "__surum__",
        "DEFAULT_BASE_URL",
        "DEFAULT_MODEL",
        "IZINLI_KONAKLAR",
        "LLMError",
        "LLMClient",
        "konak_kontrol",
        "CorLLMClient",
    }
    assert beklenen <= set(corclient.__all__)
    for ad in beklenen:
        assert hasattr(corclient, ad), ad


def test_modul_duzeyinde_import_edilen_adlar() -> None:
    """Tüketici testleri bu NAMES üzerinden yama yapar; kayıp olursa kırılır."""
    assert hasattr(corclient, "time")
    assert hasattr(corclient, "sys")
    assert hasattr(corclient, "json")
    assert hasattr(corclient, "os")
    assert hasattr(corclient, "urllib")
    assert hasattr(corclient.urllib, "request")
    assert hasattr(corclient.urllib, "error")


def test_varsayilanlar() -> None:
    client = CorLLMClient()
    assert client.base_url == "http://127.0.0.1:8787"
    assert client.model == "nvidia/nemotron-3-ultra-550b-a55b:free"
    assert client.timeout == 120.0
    assert client.max_retries == 3
    assert client.retry_backoff == 3.0
    assert client.max_tokens == 4000
    assert client.baslat_ipucu == "cor start"
    assert DEFAULT_BASE_URL == "http://127.0.0.1:8787"
    assert DEFAULT_MODEL == "nvidia/nemotron-3-ultra-550b-a55b:free"
    assert IZINLI_KONAKLAR == frozenset({"127.0.0.1", "localhost", "::1", "[::1]"})


def test_llm_error_status_alani() -> None:
    """`status` HTTP hatasında kod, diğer hatalarda `None`."""
    hata = LLMError("yok", status=503)
    assert hata.status == 503
    assert str(hata) == "yok"
    assert isinstance(hata, RuntimeError)
    assert LLMError("düz").status is None


def test_llm_client_protocol_isinstance() -> None:
    class Sahte:
        def complete(self, prompt: str) -> str:
            return prompt

    assert isinstance(CorLLMClient(), LLMClient)
    assert isinstance(Sahte(), LLMClient)
    assert not isinstance(object(), LLMClient)


# --------------------------------------------------------------------- #
# Başarılı çağrı: yol, başlık, gövde
# --------------------------------------------------------------------- #


def test_basarili_cagri_govde_ve_baslik(sahte_cor: FakeCorServer) -> None:
    """Gövde alanları, yol, başlık ve ek alan YOK."""
    sahte_cor.responses = [(200, messages_response("merhaba"))]
    client = CorLLMClient(
        base_url=sahte_cor.base_url,
        model="kurgusal/model",
        max_tokens=1234,
        timeout=10.0,
    )

    assert client.complete("selam") == "merhaba"

    istek = sahte_cor.requests[-1]
    assert istek["path"] == "/v1/messages"
    assert istek["method"] == "POST"
    assert istek["content_type"] == "application/json"
    assert istek["body"]["model"] == "kurgusal/model"
    assert istek["body"]["max_tokens"] == 1234
    assert istek["body"]["messages"] == [{"role": "user", "content": "selam"}]
    assert set(istek["body"]) == {"model", "max_tokens", "messages"}


def test_basarili_cagri_metin_dondurur(sahte_cor: FakeCorServer) -> None:
    sahte_cor.responses = [(200, messages_response("merhaba dunya"))]
    client = CorLLMClient(base_url=sahte_cor.base_url, timeout=10.0)
    assert client.complete("selam") == "merhaba dunya"


def test_sondaki_slah_atilir(sahte_cor: FakeCorServer) -> None:
    """`base_url` sondaki `/` atılır; çift eğik çizgi oluşmaz."""
    sahte_cor.responses = [(200, messages_response("tamam"))]
    client = CorLLMClient(base_url=sahte_cor.base_url + "/", timeout=10.0)
    assert client.base_url == sahte_cor.base_url
    assert client.complete("x") == "tamam"
    assert sahte_cor.requests[-1]["path"] == "/v1/messages"


# --------------------------------------------------------------------- #
# Retry: YALNIZ 5xx
# --------------------------------------------------------------------- #


def test_4xx_yeniden_denemez(sahte_cor: FakeCorServer) -> None:
    """4xx kalıcıdır: erişim sayısı 1."""
    sahte_cor.responses = [(400, {"hata": "kotu istek"})]
    client = CorLLMClient(base_url=sahte_cor.base_url, timeout=10.0, max_retries=3)

    with pytest.raises(LLMError) as hata:
        client.complete("selam")
    assert "HTTP 400" in str(hata.value)
    assert hata.value.status == 400
    assert sahte_cor.hits == 1


def test_429_yeniden_denemez(sahte_cor: FakeCorServer) -> None:
    sahte_cor.responses = [(429, {"hata": "cok hizli"})]
    client = CorLLMClient(
        base_url=sahte_cor.base_url, timeout=10.0, max_retries=3, retry_backoff=0.0
    )
    with pytest.raises(LLMError, match="HTTP 429"):
        client.complete("selam")
    assert sahte_cor.hits == 1


def test_5xx_max_retries_kadar_denir_ve_yukselir(sahte_cor: FakeCorServer) -> None:
    sahte_cor.responses = [(503, {"hata": "gecici"})]
    client = CorLLMClient(
        base_url=sahte_cor.base_url, timeout=10.0, max_retries=2, retry_backoff=0.0
    )

    with pytest.raises(LLMError) as hata:
        client.complete("selam")
    assert "HTTP 503" in str(hata.value)
    assert hata.value.status == 503
    assert sahte_cor.hits == 3  # ilk deneme + 2 tekrar


def test_5xx_sonra_basari(sahte_cor: FakeCorServer) -> None:
    sahte_cor.responses = [
        (500, {"hata": "gecici"}),
        (503, {"hata": "gecici"}),
        (200, messages_response("sonunda")),
    ]
    client = CorLLMClient(base_url=sahte_cor.base_url, timeout=10.0, retry_backoff=0.0)
    assert client.complete("x") == "sonunda"
    assert sahte_cor.hits == 3


def test_statussuz_http5xx_mesaji_retry_edilir(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tüketici testlerinin `_post_once` yolu: `status` YOK, mesajda `HTTP 5`.

    Bu korunmalıdır; aksi halde tüketici repoların testleri kırılır.
    """
    client = CorLLMClient(retry_backoff=0.0, max_retries=2)
    sayac = {"n": 0}

    def sahte_post(prompt: str) -> str:
        sayac["n"] += 1
        if sayac["n"] == 1:
            raise LLMError("cor proxy HTTP 502 döndü: upstream bos")
        return "tamam"

    monkeypatch.setattr(client, "_post_once", sahte_post)
    assert client.complete("p") == "tamam"
    assert sayac["n"] == 2


def test_statussuz_http5xx_max_retries_sonrasi_yukselir(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = CorLLMClient(retry_backoff=0.0, max_retries=2)
    sayac = {"n": 0}

    def sahte_post(prompt: str) -> str:
        sayac["n"] += 1
        raise LLMError("cor proxy HTTP 502 döndü: upstream bos")

    monkeypatch.setattr(client, "_post_once", sahte_post)
    with pytest.raises(LLMError, match="502"):
        client.complete("p")
    assert sayac["n"] == 3


def test_statussuz_4xx_mesaji_retry_edilmez(monkeypatch: pytest.MonkeyPatch) -> None:
    """`status` yok ama mesaj 4xx: kalıcı, tekrar DENENMEZ."""
    client = CorLLMClient(retry_backoff=0.0, max_retries=3)
    sayac = {"n": 0}

    def sahte_post(prompt: str) -> str:
        sayac["n"] += 1
        raise LLMError("cor proxy HTTP 400 döndü: kotu")

    monkeypatch.setattr(client, "_post_once", sahte_post)
    with pytest.raises(LLMError):
        client.complete("p")
    assert sayac["n"] == 1


def test_baglanti_hatasi_retry_edilmez(monkeypatch: pytest.MonkeyPatch) -> None:
    client = CorLLMClient(retry_backoff=0.0, max_retries=3)
    sayac = {"n": 0}

    def sahte_post(prompt: str) -> str:
        sayac["n"] += 1
        raise LLMError("cor proxy'ye bağlanılamadı: refused")

    monkeypatch.setattr(client, "_post_once", sahte_post)
    with pytest.raises(LLMError, match="bağlanılamadı"):
        client.complete("p")
    assert sayac["n"] == 1


def test_status_alani_5xx_olmadan_es_karari_yapmaz() -> None:
    """`status` varsa O kod belirler: 599 geçici, 600 kalıcı sayılır."""
    assert corclient._gecici_mi(LLMError("x", status=599)) is True
    assert corclient._gecici_mi(LLMError("x", status=500)) is True
    assert corclient._gecici_mi(LLMError("HTTP 5 gizli", status=404)) is False
    assert corclient._gecici_mi(LLMError("bağlanılamadı")) is False


def test_bekleme_ustel_gider(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    """`retry_backoff * 2**deneme` beklenir, stderr'e satır basılır."""
    beklemeler: list[float] = []
    monkeypatch.setattr(corclient.time, "sleep", beklemeler.append)

    client = CorLLMClient(retry_backoff=0.5, max_retries=2)
    sayac = {"n": 0}

    def sahte_post(prompt: str) -> str:
        sayac["n"] += 1
        raise LLMError("cor proxy HTTP 502 döndü: gecici")

    monkeypatch.setattr(client, "_post_once", sahte_post)
    with pytest.raises(LLMError):
        client.complete("p")

    assert beklemeler == [0.5, 1.0]
    cikti = capsys.readouterr().err
    assert cikti.count("Geçici sağlayıcı hatası") == 2
    assert "1/2" in cikti and "2/2" in cikti
    assert cikti == cikti  # stderr


def test_max_retries_sifirsa_tek_deneme(monkeypatch: pytest.MonkeyPatch) -> None:
    client = CorLLMClient(retry_backoff=0.0, max_retries=0)
    sayac = {"n": 0}

    def sahte_post(prompt: str) -> str:
        sayac["n"] += 1
        raise LLMError("cor proxy HTTP 500 döndü: gecici")

    monkeypatch.setattr(client, "_post_once", sahte_post)
    with pytest.raises(LLMError):
        client.complete("p")
    assert sayac["n"] == 1


# --------------------------------------------------------------------- #
# Yanıt biçimi / boş yanıt
# --------------------------------------------------------------------- #


def test_bos_yant_hata_verir(sahte_cor: FakeCorServer) -> None:
    """HTTP 200 olsa bile boş metin BAŞARISIZLIKTIR; sahte yanıt üretilmez."""
    sahte_cor.responses = [(200, messages_response("   "))]
    client = CorLLMClient(base_url=sahte_cor.base_url, timeout=10.0)
    with pytest.raises(LLMError, match="boş yanıt"):
        client.complete("x")


def test_bos_dize_hata_verir(sahte_cor: FakeCorServer) -> None:
    sahte_cor.responses = [(200, messages_response(""))]
    client = CorLLMClient(base_url=sahte_cor.base_url, timeout=10.0)
    with pytest.raises(LLMError):
        client.complete("x")


def test_bozuk_json_hata_verir(sahte_cor: FakeCorServer) -> None:
    sahte_cor.responses = [(200, b"bu json degil")]
    client = CorLLMClient(base_url=sahte_cor.base_url, timeout=10.0)
    with pytest.raises(LLMError, match="yanıt biçimi"):
        client.complete("x")


def test_eksik_content_hata_verir(sahte_cor: FakeCorServer) -> None:
    sahte_cor.responses = [(200, {"beklenmeyen": "bicim"})]
    client = CorLLMClient(base_url=sahte_cor.base_url, timeout=10.0)
    with pytest.raises(LLMError, match="yanıt biçimi"):
        client.complete("x")


def test_bos_content_dizi_hata_verir(sahte_cor: FakeCorServer) -> None:
    sahte_cor.responses = [(200, {"content": []})]
    client = CorLLMClient(base_url=sahte_cor.base_url, timeout=10.0)
    with pytest.raises(LLMError):
        client.complete("x")


def test_yanit_bicimi_hatasi_retry_edilmez(sahte_cor: FakeCorServer) -> None:
    sahte_cor.responses = [(200, {"beklenmeyen": "bicim"})]
    client = CorLLMClient(
        base_url=sahte_cor.base_url, timeout=10.0, max_retries=3, retry_backoff=0.0
    )
    with pytest.raises(LLMError):
        client.complete("x")
    assert sahte_cor.hits == 1


# --------------------------------------------------------------------- #
# Bağlantı hatası / başlat ipucu
# --------------------------------------------------------------------- #


def test_kapali_port_mesaji_ve_baslat_ipucu() -> None:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        bos_port = s.getsockname()[1]
    client = CorLLMClient(base_url=f"http://127.0.0.1:{bos_port}", timeout=1.0)
    with pytest.raises(LLMError) as hata:
        client.complete("x")
    assert "bağlanılamadı" in str(hata.value)
    assert "cor start" in str(hata.value)
    assert hata.value.status is None


def test_ozel_baslat_ipucu_kullanilir() -> None:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        bos_port = s.getsockname()[1]
    client = CorLLMClient(
        base_url=f"http://127.0.0.1:{bos_port}", timeout=1.0, baslat_ipucu="cor claude"
    )
    with pytest.raises(LLMError) as hata:
        client.complete("x")
    assert "cor claude" in str(hata.value)


def test_http_hata_govdesi_ilk_500_karaktere_kisirilir(
    sahte_cor: FakeCorServer,
) -> None:
    sahte_cor.responses = [(500, {"hata": "x" * 2000})]
    client = CorLLMClient(
        base_url=sahte_cor.base_url, timeout=10.0, max_retries=0, retry_backoff=0.0
    )
    with pytest.raises(LLMError) as hata:
        client.complete("p")
    ayrinti = str(hata.value).split("döndü: ", 1)[1]
    assert len(ayrinti) == 500


# --------------------------------------------------------------------- #
# Konak denetimi
# --------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "adres",
    ["http://ornek.invalid:8787", "http://10.0.0.5:8787", "http://192.168.1.4:8787"],
)
def test_loopback_disi_reddedilir(adres: str) -> None:
    with pytest.raises(LLMError) as hata:
        CorLLMClient(base_url=adres)
    assert "loopback" in str(hata.value)


@pytest.mark.parametrize(
    "adres", ["http://127.0.0.1:8787", "http://localhost:8787", "http://[::1]:8787"]
)
def test_loopback_kabul(adres: str) -> None:
    assert konak_kontrol(adres)
    assert CorLLMClient(base_url=adres).base_url.startswith("http://")


def test_gecersiz_sema_reddedilir() -> None:
    with pytest.raises(LLMError, match="şema"):
        konak_kontrol("ftp://127.0.0.1:8787")
    with pytest.raises(LLMError):
        CorLLMClient(base_url="ftp://127.0.0.1:8787")


def test_konak_yoksa_reddedilir() -> None:
    with pytest.raises(LLMError):
        konak_kontrol("http:///v1")


def test_izinli_konaklar_none_dis_konagi_kabul_eder(sahte_cor: FakeCorServer) -> None:
    """`None` = denetim YAPILMAZ (danis / ne-izlesem'in bugünkü davranışı)."""
    client = CorLLMClient(
        base_url="http://ornek.invalid:8787",
        timeout=1.0,
        retry_backoff=0.0,
        max_retries=0,
        izinli_konaklar=None,
    )
    assert client.base_url == "http://ornek.invalid:8787"
    # Gerçekten denetim yok: kurucu hata vermedi, bağlantı denemesi yapıldı.
    with pytest.raises(LLMError, match="bağlanılamadı"):
        client.complete("x")


def test_izinli_konek_none_gcsmeyi_de_kabul_eder() -> None:
    client = CorLLMClient(base_url="ftp://ornek.invalid", izinli_konaklar=None)
    assert client.base_url == "ftp://ornek.invalid"


def test_ozel_kume_ile_0_0_0_0_kabul(sahte_cor: FakeCorServer) -> None:
    """`0.0.0.0` harita'nın kumesindedir; yalnız küme VERİLİRSE kabul edilir."""
    assert "0.0.0.0" not in IZINLI_KONAKLAR
    with pytest.raises(LLMError):
        CorLLMClient(base_url="http://0.0.0.0:8787")

    kume = IZINLI_KONAKLAR | {"0.0.0.0"}
    assert konak_kontrol("http://0.0.0.0:8787", kume) == "0.0.0.0"
    assert CorLLMClient(base_url="http://0.0.0.0:8787", izinli_konaklar=kume)


def test_ozel_kume_disi_konagi_reddeder() -> None:
    with pytest.raises(LLMError):
        CorLLMClient(base_url="http://127.0.0.1:8787", izinli_konaklar=frozenset({"::1"}))


def test_bekleme_gercekten_ustel(monkeypatch: pytest.MonkeyPatch) -> None:
    """4 tekrarda bekleme 2**n büyür (lineer büyüme 1.5/2.0 verirdi)."""
    beklemeler: list[float] = []
    monkeypatch.setattr(corclient.time, "sleep", beklemeler.append)
    client = CorLLMClient(retry_backoff=0.5, max_retries=4)

    def sahte_post(prompt: str) -> str:
        raise LLMError("cor proxy HTTP 503 döndü: gecici", status=503)

    monkeypatch.setattr(client, "_post_once", sahte_post)
    with pytest.raises(LLMError):
        client.complete("p")
    assert beklemeler == [0.5, 1.0, 2.0, 4.0]


@pytest.mark.parametrize("adres", ["http://LOCALHOST:8787", "http://Localhost:8787"])
def test_konak_buyuk_kucuk_harf_duyarsiz(adres: str) -> None:
    """Konak adı büyük/küçük harften bağımsız eşleşir (RFC: konak adları duyarsız)."""
    assert konak_kontrol(adres).lower() == "localhost"
    CorLLMClient(base_url=adres)  # kuruluşta reddedilmemeli
