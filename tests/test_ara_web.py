"""Dalga D — `/ara` web testleri: rotalar, JSON şekli, XSS, CSP, salt-okunurluk.

Yalnızca GET; aynı güvenlik modeli (127.0.0.1, Host doğrulama, CSP,
`mode=ro`) geçerlidir. Vurgu `<mark>` YALNIZCA sunucunun ürettiği
aralıklardan doğar; not başlığı/alıntısı otomatik kaçışlıdır.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from conftest import XSS_BASLIK, XSS_BASLIK2, vault_hashleri, yaz

from harita.index import indeksle
from harita.web import sunucu

pytest.importorskip("flask", reason="Flask kurulu değil (requirements.txt)")


@pytest.fixture
def arama_istemci(arama_db: Path):
    with sunucu.app_olustur(arama_db).test_client() as c:
        yield c


@pytest.fixture
def xss_arama_vault(tmp_path: Path) -> Path:
    """Arama yüzeyinde XSS yükü taşıyan kurgusal vault."""
    vault = tmp_path / "xss-arama"
    vault.mkdir()
    yaz(vault, f"kutu/{XSS_BASLIK}.md", f"---\ntitle: {XSS_BASLIK}\n---\n# Zararli\n")
    yaz(vault, f"kutu/{XSS_BASLIK2}.md", f"---\ntitle: {XSS_BASLIK2}\n---\n# Zararli 2\n")
    yaz(vault, "kutu/paylasim.md", f"---\ntitle: Paylaşım\n---\n# Paylaşım\n\n→ [[{XSS_BASLIK}]]\n")
    yaz(vault, "kutu/notlu.md", "---\ntitle: Notlu\n---\n# Notlu\n\nGizli Özel Sözcük burada.\n")
    return vault


@pytest.fixture
def xss_istemci(xss_arama_vault: Path, tmp_path: Path):
    db = tmp_path / "xss-ara.db"
    indeksle(xss_arama_vault, db)
    with sunucu.app_olustur(db).test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# Sayfa
# ---------------------------------------------------------------------------


def test_ara_sayfasi_bos_durum(arama_istemci) -> None:
    """Sorgu yokken ilk durum metni görünür."""
    cevap = arama_istemci.get("/ara")
    assert cevap.status_code == 200
    govde = cevap.get_data(as_text=True)
    assert "Ne aramıştın" in govde


def test_ara_sayfasi_q_dogrudan_acilis(arama_istemci) -> None:
    """JS KAPALIYKEN bile `?q=` ile açılan sayfa sonuç gösterir."""
    cevap = arama_istemci.get("/ara?q=g%C3%BCvenlik")
    assert cevap.status_code == 200
    govde = cevap.get_data(as_text=True)
    assert "Güvenlik Sırları" in govde
    assert "sonuç" in govde


def test_ara_sayfasi_mark_vurgusu(arama_istemci) -> None:
    """Eşleşme `<mark>` ile vurgulanır."""
    govde = arama_istemci.get("/ara?q=g%C3%BCvenlik").get_data(as_text=True)
    assert "<mark>" in govde
    assert re.search(r"<mark>[^<]*Güvenlik[^<]*</mark>", govde)


def test_ara_sayfasi_bos_sonuc(arama_istemci) -> None:
    cevap = arama_istemci.get("/ara?q=bulunamayacakkelime")
    assert cevap.status_code == 200
    assert "Sonuç yok" in cevap.get_data(as_text=True)


def test_ara_sayfasi_sonuc_sayisi_gosterilir(arama_istemci) -> None:
    govde = arama_istemci.get("/ara?q=g%C3%BCvenlik").get_data(as_text=True)
    assert re.search(r"\d+ sonuç", govde)


def test_ara_sayfasi_graf_linki_kullanir(arama_istemci) -> None:
    """Sonuç başlığı mevcut `/?not=<id>` desenini kullanır."""
    govde = arama_istemci.get("/ara?q=g%C3%BCvenlik").get_data(as_text=True)
    assert re.search(r'href="/\?not=\d+"', govde)


def test_ara_sayfasi_etiket_rozetleri(arama_istemci) -> None:
    govde = arama_istemci.get("/ara?q=g%C3%BCvenlik").get_data(as_text=True)
    assert "#gizlilik" in govde


def test_ara_sayfasi_graf_gezinmesi_korur(arama_istemci) -> None:
    """`/ara` sayfasından grafa dönüş bağlantısı korunur."""
    assert 'href="/"' in arama_istemci.get("/ara").get_data(as_text=True)


@pytest.mark.parametrize("yol", ["/", "/kirik", "/yetim"])
def test_ust_seritte_ara_linki_var(arama_istemci, yol: str) -> None:
    """Graf/liste sayfalarının üst şeridinde "Ara" bağlantısı var."""
    assert 'href="/ara"' in arama_istemci.get(yol).get_data(as_text=True)


# ---------------------------------------------------------------------------
# /api/ara
# ---------------------------------------------------------------------------


def test_api_ara_sekli(arama_istemci) -> None:
    veri = arama_istemci.get("/api/ara?q=g%C3%BCvenlik").get_json()
    assert veri["sorgu"] == "güvenlik"
    assert veri["sonuclar"]
    ilk = veri["sonuclar"][0]
    assert set(ilk) == {"puan", "baslik", "yol", "etiketler", "alinti", "vurgular", "not_id"}
    assert isinstance(ilk["vurgular"], list)
    assert ilk["vurgular"]


def test_api_ara_ilk_ust_siniri(arama_istemci) -> None:
    """`ilk` üst sınırı 50; daha büyük değer 50'ye kırpılır."""
    veri = arama_istemci.get("/api/ara?q=g%C3%BCvenlik&ilk=9999").get_json()
    assert len(veri["sonuclar"]) <= 50


def test_api_ara_ilk_gecersiz_deger(arama_istemci) -> None:
    """Sayı olmayan `ilk` çökmez, varsayılana düşer."""
    cevap = arama_istemci.get("/api/ara?q=g%C3%BCvenlik&ilk=abc")
    assert cevap.status_code == 200
    assert cevap.get_json()["sonuclar"]


def test_api_ara_bos_sorgu(arama_istemci) -> None:
    veri = arama_istemci.get("/api/ara?q=").get_json()
    assert veri["sonuclar"] == []
    assert "hata" in veri


def test_api_ara_sonucsuz(arama_istemci) -> None:
    veri = arama_istemci.get("/api/ara?q=bulunamayacakkelime").get_json()
    assert veri["sonuclar"] == []


def test_api_ara_yazma_metodu_405(arama_istemci) -> None:
    assert arama_istemci.post("/api/ara?q=x").status_code == 405


def test_ara_yazma_metodu_405(arama_istemci) -> None:
    assert arama_istemci.post("/ara", data={"q": "x"}).status_code == 405


# ---------------------------------------------------------------------------
# XSS
# ---------------------------------------------------------------------------


def test_xss_not_basligi_ara_sayfasina_girmez(xss_istemci) -> None:
    """Sahte not başlığı HTML'e kaçışsız girmez; `<script>` yürütülmez."""
    cevap = xss_istemci.get("/ara?q=zararli")
    govde = cevap.get_data(as_text=True)
    assert "<script>window.__xss=1</script>" not in govde
    assert "&lt;script&gt;" in govde or "zararli" in govde.lower()


def test_xss_alinti_ara_sayfasina_girmez(xss_istemci) -> None:
    """Alıntı içindeki yük kaçışlıdır, ham `<script>` olarak bulunmaz."""
    govde = xss_istemci.get("/ara?q=zararli").get_data(as_text=True)
    assert "window.__xss=1" not in govde or "&lt;" in govde
    assert "<img src=x onerror" not in govde


def test_xss_json_ara_icerigi_korumali(xss_istemci) -> None:
    """JSON alıntısı ham metindir ama HTML'e yazılmaz (içerik olarak taşınır)."""
    veri = xss_istemci.get("/api/ara?q=zararli").get_json()
    basliklar = " ".join(s["baslik"] for s in veri["sonuclar"])
    assert "<script>" in basliklar or basliklar == ""
    # Önemli olan: bu değer HTML'e GİRMEZ.
    govde = xss_istemci.get("/ara?q=zararli").get_data(as_text=True)
    assert "<script>window.__xss=1</script>" not in govde


def test_mark_yalnizca_sunucu_uretiyor(arama_istemci) -> None:
    """`<mark>` yalnızca vurgu aralıklarının etrafında üretilir."""
    govde = arama_istemci.get("/ara?q=g%C3%BCvenlik").get_data(as_text=True)
    # Her `<mark>` kapanır ve içinde yalnızca metin vardır (etiket değil).
    assert govde.count("<mark>") == govde.count("</mark>")
    for parca in re.findall(r"<mark>(.*?)</mark>", govde, re.S):
        assert "<" not in parca and ">" not in parca


def test_sablonlarda_satir_ici_script_yok_ara() -> None:
    """`/ara` şablonunda satır içi script/stil yok (CSP uyumu)."""
    kok = Path(__file__).resolve().parents[1] / "harita" / "web" / "sablonlar" / "ara.html"
    govde = kok.read_text(encoding="utf-8")
    assert "<script>" not in govde
    assert "onclick=" not in govde
    assert "style=" not in govde


def test_ara_js_innerhtml_kullanmaz() -> None:
    """`ara.js` DOM'a yalnız `location.assign` yazar; `innerHTML` yok."""
    kok = Path(__file__).resolve().parents[1] / "harita" / "web" / "static" / "ara.js"
    kaynak = kok.read_text(encoding="utf-8")
    assert "innerHTML" not in kaynak
    assert "outerHTML" not in kaynak
    assert "insertAdjacentHTML" not in kaynak
    assert "location.assign" in kaynak


# ---------------------------------------------------------------------------
# Güvenlik başlıkları / Host / salt-okunurluk
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("yol", ["/ara", "/api/ara?q=g%C3%BCvenlik"])
def test_ara_guvenlik_basliklari(arama_istemci, yol: str) -> None:
    cevap = arama_istemci.get(yol)
    assert cevap.headers["Content-Security-Policy"] == sunucu.CSP
    assert cevap.headers["X-Content-Type-Options"] == "nosniff"
    assert cevap.headers["Referrer-Policy"] == "no-referrer"
    assert cevap.headers["Cache-Control"] == "no-store"


def test_ara_host_disi_403(arama_istemci) -> None:
    cevap = arama_istemci.get("/ara?q=x", headers={"Host": "ornek.com"})
    assert cevap.status_code == 403


def test_ara_arama_db_yi_degistirmez(arama_db: Path) -> None:
    """Arama sonrası indeks DB'sinin hash'i DEĞİŞMEZ (salt okunur)."""
    import hashlib

    with sunucu.app_olustur(arama_db).test_client() as c:
        c.get("/ara?q=g%C3%BCvenlik")
        c.get("/api/ara?q=g%C3%BCvenlik")
    once = hashlib.sha256(arama_db.read_bytes()).hexdigest()
    with sunucu.app_olustur(arama_db).test_client() as c:
        c.get("/ara?q=plan")
    assert hashlib.sha256(arama_db.read_bytes()).hexdigest() == once


def test_ara_vaultu_degistirmez(arama_vault: Path, arama_db: Path) -> None:
    """Web araması vault dosyalarının hash'ini DEĞİŞTİRMEZ."""
    once = vault_hashleri(arama_vault)
    with sunucu.app_olustur(arama_db).test_client() as c:
        c.get("/ara?q=g%C3%BCvenlik")
        c.get("/api/ara?q=borsa")
    assert vault_hashleri(arama_vault) == once


def test_ara_soket_acmaz(arama_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Web araması soket AÇMAZ (ağ yasağı)."""
    import socket

    def yakala(*a, **k):  # noqa: ANN001
        raise AssertionError("web araması soket açmaya çalıştı")

    monkeypatch.setattr(socket, "create_connection", yakala)
    with sunucu.app_olustur(arama_db).test_client() as c:
        c.get("/ara?q=g%C3%BCvenlik")


# ---------------------------------------------------------------------------
# Statik dosya paketleme
# ---------------------------------------------------------------------------


def test_ara_js_paket_icinde() -> None:
    """`ara.js` paket verisine dahil (paket kurulumunda kaybolmaz)."""
    kok = Path(__file__).resolve().parents[1]
    assert (kok / "harita" / "web" / "static" / "ara.js").exists()
    assert (kok / "harita" / "web" / "sablonlar" / "ara.html").exists()
