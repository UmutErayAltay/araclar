"""Dalga B — web testleri: rotalar, JSON şekilleri, güvenlik başlıkları,
salt-okunurluk, XSS kaçışı, CSP uyumu ve `harita web` alt komutu.
"""

from __future__ import annotations

import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import (
    KOK,
    XSS_BASLIK,
    XSS_BASLIK2,
    XSS_HEDEF,
    vault_hashleri,
    yetim_vault,
    yaz,
)

from harita.cli import main as cli_main
from harita.index import indeksle
from harita.web import sunucu

pytest.importorskip("flask", reason="Flask kurulu değil (requirements.txt)")


@pytest.fixture
def db(mini_vault: Path, tmp_path: Path) -> Path:
    yol = tmp_path / "web.db"
    indeksle(mini_vault, yol)
    return yol


def id_ara(istemci, yol: str) -> int:
    """Yoluna göre not id'si bulur (fixture id'leri sıraya göre değişir)."""
    veri = istemci.get("/api/graf").get_json()
    return next(d["id"] for d in veri["dugumler"] if d["yol"] == yol)


@pytest.fixture
def istemci(db: Path):
    uygulama = sunucu.app_olustur(db)
    with uygulama.test_client() as c:
        yield c


@pytest.fixture
def bos_istemci(tmp_path: Path):
    vault = tmp_path / "bos-vault"
    vault.mkdir()
    yol = tmp_path / "bos.db"
    indeksle(vault, yol)
    with sunucu.app_olustur(yol).test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# Rotalar ve temel şekiller
# ---------------------------------------------------------------------------

def test_ana_sayfa_200_ve_ozet(istemci) -> None:
    cevap = istemci.get("/")
    assert cevap.status_code == 200
    govde = cevap.get_data(as_text=True)
    assert "Zihin haritası" in govde
    # Üst özet şeridi sunucudan gelen sayılarla dolu.
    graf = istemci.get("/api/graf").get_json()
    assert f'id="sayac-not">{len(graf["dugumler"])}</b>' in govde
    kirik_sayisi = sum(
        len(istemci.get(f"/api/not/{d['id']}").get_json()["kirik"]) for d in graf["dugumler"]
    )
    assert f">{kirik_sayisi}</b> kırık link" in govde
    assert "id=\"sayac-link\"" in govde


def test_saglik_durum_ok(istemci) -> None:
    cevap = istemci.get("/saglik")
    assert cevap.status_code == 200
    assert cevap.get_json() == {"durum": "ok"}


def test_api_graf_sekli(istemci) -> None:
    veri = istemci.get("/api/graf").get_json()
    assert set(veri) == {"dugumler", "kenarlar"}
    assert veri["dugumler"] and veri["kenarlar"]
    for d in veri["dugumler"]:
        assert set(d) == {"id", "baslik", "yol", "klasor", "etiketler", "derece"}
        assert isinstance(d["id"], int)
        assert isinstance(d["etiketler"], list)
        assert isinstance(d["derece"], int) and d["derece"] >= 0
    for k in veri["kenarlar"]:
        assert set(k) == {"kaynak", "hedef"}


def test_api_graf_klasor_kok_etiketi(istemci) -> None:
    """Kökteki notların klasörü `"(kök)"`; alt klasördekiler en üst bileşen."""
    veri = istemci.get("/api/graf").get_json()
    klasorler = {d["yol"]: d["klasor"] for d in veri["dugumler"]}
    assert klasorler["ozet.md"] == "(kök)"
    assert klasorler["🧠 Bilgi/ızgara-notu.md"] == "🧠 Bilgi"
    assert klasorler["📁 Klasör/derin-not.md"] == "📁 Klasör"


def test_klasor_rengi_paleti_ve_diger_kurali(mini_vault: Path, tmp_path: Path) -> None:
    """8'den fazla klasör varsa kalanlar gri (`#999999`) ve lejantta "diğer"."""
    import collections

    vault = tmp_path / "cok-klasorlu"
    vault.mkdir()
    yaz(vault, "k0/a.md", "# A\n[[k1/b]]\n")
    yaz(vault, "k1/b.md", "# B\n[[k2/c]]\n")
    yaz(vault, "k2/c.md", "# C\n[[k3/d]]\n")
    yaz(vault, "k3/d.md", "# D\n[[k4/e]]\n")
    yaz(vault, "k4/e.md", "# E\n[[k5/f]]\n")
    yaz(vault, "k5/f.md", "# F\n[[k6/g]]\n")
    yaz(vault, "k6/g.md", "# G\n[[k7/h]]\n")
    yaz(vault, "k7/h.md", "# H\n[[k8/i]]\n")
    yaz(vault, "k8/i.md", "# I\n[[k9/j]]\n")
    yaz(vault, "k9/j.md", "# J\n[[k0/a]]\n")
    db = tmp_path / "cok.db"
    indeksle(vault, db)
    js = (KOK / "harita" / "web" / "static" / "graf.js").read_text(encoding="utf-8")

    veri = sunucu.app_olustur(db).test_client().get("/api/graf").get_json()
    klasorler = collections.Counter(d["klasor"] for d in veri["dugumler"])
    assert len(klasorler) == 10  # 10 farklı klasör > 8 palet rengi
    assert len(sunucu.OKABE_ITO) == 8
    assert "PALET.length" in js and "DIGER_RENK" in js
    assert "diğer (" in js
    assert klasorler  # lejant girdileri JS'te üretilir


def test_klasor_etiketi_kok_durumu(istemci) -> None:
    veri = istemci.get("/api/graf").get_json()
    kok = [d for d in veri["dugumler"] if "/" not in d["yol"]]
    assert kok
    assert all(d["klasor"] == "(kök)" for d in kok)


def test_api_graf_yalnizca_cozulmus_linkler(istemci) -> None:
    """Kırık linkler kenara dönüşmez; kırık olan id yoktur."""
    veri = istemci.get("/api/graf").get_json()
    var = {d["id"] for d in veri["dugumler"]}
    for k in veri["kenarlar"]:
        assert k["kaynak"] in var and k["hedef"] in var
    kirik_hedefler = {"bilinmeyen-not", "gömülü-görsel"}
    assert kirik_hedefler, "fixture kırık link içermeli"
    assert veri["kenarlar"], "en az bir çözülmüş link olmalı"


def test_api_graf_derece_konsistansi(istemci) -> None:
    """Derece = gelen + giden ÇÖZÜLMÜŞ link sayısı (kırık linkler sayılmaz).

    Çoklu (aynı çifte tekrarlanan) linkler graf kenarı olarak TEK sayılır;
    derece ise panel bağlantılarıyla eşleşmelidir.
    """
    veri = istemci.get("/api/graf").get_json()
    for d in veri["dugumler"]:
        detay = istemci.get(f"/api/not/{d['id']}").get_json()
        assert d["derece"] == len(detay["giden"]) + len(detay["gelen"])
        # Graf kenarı ile panel bağlantıları aynı kümede olmalı.
        uclular = {k["hedef"] for k in veri["kenarlar"] if k["kaynak"] == d["id"]}
        uclular |= {k["kaynak"] for k in veri["kenarlar"] if k["hedef"] == d["id"]}
        assert uclular == {x["id"] for x in detay["giden"] + detay["gelen"]}


def test_api_graf_tekrarli_link_tek_kenar(mini_vault: Path, tmp_path: Path) -> None:
    """Aynı çifteki çoklu linkler grafte TEK kenardır."""
    yaz(mini_vault, "coklu.md", "[[ozet]] [[ozet]] [[ozet]]\n")
    db = tmp_path / "coklu.db"
    indeksle(mini_vault, db)
    veri = sunucu.app_olustur(db).test_client().get("/api/graf").get_json()
    ozet_id = next(d["id"] for d in veri["dugumler"] if d["yol"] == "ozet.md")
    coklu_id = next(d["id"] for d in veri["dugumler"] if d["yol"] == "coklu.md")
    ciftler = [
        (k["kaynak"], k["hedef"]) for k in veri["kenarlar"] if {k["kaynak"], k["hedef"]} == {coklu_id, ozet_id}
    ]
    assert len(ciftler) == 1


def test_api_not_sekli(istemci) -> None:
    veri = istemci.get("/api/not/1").get_json()
    assert set(veri) == {
        "id", "baslik", "yol", "klasor", "etiketler", "ozet", "ozet_kesildi",
        "giden", "gelen", "kirik",
    }
    assert veri["id"] == 1
    for bag in veri["giden"] + veri["gelen"]:
        assert set(bag) == {"id", "baslik"}


def test_api_not_olmayan_id_404(istemci) -> None:
    cevap = istemci.get("/api/not/999999")
    assert cevap.status_code == 404
    assert cevap.get_json() == {"hata": "not bulunamadı", "id": 999999}


def test_api_not_ozet_gozde_ve_kirik(istemci) -> None:
    """Özet gövdeden gelir; kırık linkler ayrı listede."""
    ızgara = id_ara(istemci, "🧠 Bilgi/ızgara-notu.md")
    veri = istemci.get(f"/api/not/{ızgara}").get_json()
    assert "bilinmeyen-not" in veri["kirik"]
    assert "gömülü-görsel" in veri["kirik"]
    # Kırık linkler kenara/panele gider; çözülenler `giden` listesinde.
    kirik_metinler = set(veri["kirik"])
    assert kirik_metinler == {"bilinmeyen-not", "gömülü-görsel"}
    # Bu not yalnızca kırık link veriyor; çözülen giden linki yoktur.
    assert veri["giden"] == []
    assert kirik_metinler.isdisjoint({g["baslik"] for g in veri["giden"]})


def test_api_not_gelen_linkler(istemci) -> None:
    """Gelen linkler, bu nota link veren notları listeler."""
    ozet = id_ara(istemci, "ozet.md")
    veri = istemci.get(f"/api/not/{ozet}").get_json()
    # ozet.md `[[ızgara]]` (takma ad) çözülür, `[[gömülü-görsel]]` çözülmez.
    assert "gömülü-görsel" in veri["kirik"]
    assert [g["baslik"] for g in veri["giden"]] == ["Izgara Ağı Hakkında"]
    # ozet.md'ye link veren yok.
    assert veri["gelen"] == []


def test_api_not_ozet_karakter_siniri(istemci) -> None:
    """Özet ~600 karakterle sınırlıdır."""
    import harita.index as indeks_modulu

    assert indeks_modulu.OZET_KARAKTER == 600
    derin = id_ara(istemci, "ozet.md")
    veri = istemci.get(f"/api/not/{derin}").get_json()
    assert len(veri["ozet"]) <= indeks_modulu.OZET_KARAKTER


def test_api_not_ozet_gizli_satiri_icermez(xss_vault: Path, tmp_path: Path) -> None:
    """Özet `chunks`'tan okunur; süzülmüş satırlar sızmaz."""
    vault = xss_vault
    yaz(vault, "kutu/sirli.md", "---\ntitle: Sırlı\n---\nBu satır sızdırabilir: sk-abcdefghijklmnopqrstuvwxyz123456\nBu satır güvenli.\n")
    db = tmp_path / "sir.db"
    indeksle(vault, db)
    with sunucu.app_olustur(db).test_client() as c:
        sirli = next(d["id"] for d in c.get("/api/graf").get_json()["dugumler"] if d["yol"] == "kutu/sirli.md")
        veri = c.get(f"/api/not/{sirli}").get_json()
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in veri["ozet"]
    assert "Bu satır güvenli." in veri["ozet"]


def test_api_not_yol_degistirici_yok(istemci) -> None:
    """Yol alan rotalar yok; yalnızca sayısal id kabul edilir."""
    for yol in ("/api/not/abc", "/api/not/../../etc/passwd", "/api/not/1.0", "/api/not/-1"):
        assert istemci.get(yol).status_code == 404
    assert istemci.get("/api/not/1%20OR%201=1").status_code in (404, 400, 405)


def test_api_graf_turkce_karakterler_kacissiz(istemci) -> None:
    """Türkçe karakterler JSON'da kaçışsız (okunabilir) gelir."""
    ham = istemci.get("/api/graf").get_data(as_text=True)
    assert "Izgara" in ham or "ızgara" in ham
    assert "🧠 Bilgi" in ham


# ---------------------------------------------------------------------------
# /kirik ve /yetim
# ---------------------------------------------------------------------------

def test_kirik_sayfasi_listeler_ve_baglanti_verir(istemci) -> None:
    cevap = istemci.get("/kirik")
    assert cevap.status_code == 200
    govde = cevap.get_data(as_text=True)
    assert "[[bilinmeyen-not]]" in govde
    # Her satır, grafta o kaynak notu açan bir bağlantı içerir.
    assert "/?not=" in govde


def test_yetim_iki_bolum(yetim_vault_fixture: Path, tmp_path: Path) -> None:
    db = tmp_path / "yetim.db"
    indeksle(yetim_vault_fixture, db)
    istemci = sunucu.app_olustur(db).test_client()
    govde = istemci.get("/yetim").get_data(as_text=True)
    assert "Gerçek yetim" in govde
    assert "Yok sayılabilir" in govde
    # Alt klasördeki, hiç bağlantısı olmayan notlar GERÇEK yetim…
    assert "Köşe Not" in govde
    assert "Plan" in govde
    # …link alan kök notu gerçek yetim DEĞİLDİR (link almak yeter).
    assert "Serbest Not" not in govde
    # …daily/ günlüğü ve kök dosyaları yok sayılabilir bölümde.
    assert "Günlük" in govde
    assert "README" in govde


def test_yetim_bolum_ayrimi(yetim_vault_fixture: Path, tmp_path: Path) -> None:
    """İki bölümün içeriği ayrı ayrı doğrulanır (metin yerleşimi değil, veri)."""
    from harita.index import baglan, yetim_ayir

    db = tmp_path / "yetim2.db"
    indeksle(yetim_vault_fixture, db)
    b = baglan(db)
    try:
        bolum = yetim_ayir(b)
    finally:
        b.close()
    gercek = {yol for _, yol, _ in bolum.gercek}
    yok = {yol for _, yol, _ in bolum.yok_sayilabilir}
    assert gercek == {"proje/plan.md", "kose/not.md"}
    assert yok == {"CLAUDE.md", "README.md", "daily/2026-01-01.md"}
    # Ayrım kümeleri ayrık ve toplamı eski tanımla aynı.
    assert gercek.isdisjoint(yok)


def test_yetim_bos_durum_metinleri(tmp_path: Path) -> None:
    vault = tmp_path / "bagli-vault"
    vault.mkdir()
    yaz(vault, "a.md", "# A\n[[b]]\n")
    yaz(vault, "b.md", "# B\n[[a]]\n")
    db = tmp_path / "bagli.db"
    indeksle(vault, db)
    govde = sunucu.app_olustur(db).test_client().get("/yetim").get_data(as_text=True)
    assert "Gerçek yetim yok" in govde


# ---------------------------------------------------------------------------
# Boş veritabanı
# ---------------------------------------------------------------------------

def test_bos_db_ana_sayfa(bos_istemci) -> None:
    cevap = bos_istemci.get("/")
    assert cevap.status_code == 200
    assert "İndekte not yok" in cevap.get_data(as_text=True)


def test_bos_db_api_graf_bos(bos_istemci) -> None:
    veri = bos_istemci.get("/api/graf").get_json()
    assert veri == {"dugumler": [], "kenarlar": []}


def test_bos_db_kirik_ve_yetim_bos_durum(bos_istemci) -> None:
    assert "Kırık link yok" in bos_istemci.get("/kirik").get_data(as_text=True)
    assert "Gerçek yetim yok" in bos_istemci.get("/yetim").get_data(as_text=True)


def test_bos_db_saglik_calisir(bos_istemci) -> None:
    assert bos_istemci.get("/saglik").status_code == 200


# ---------------------------------------------------------------------------
# Sadece GET: diğer metotlar 405
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("yol", ["/", "/api/graf", "/api/not/1", "/kirik", "/yetim", "/saglik"])
@pytest.mark.parametrize("metot", ["post", "put", "delete", "patch"])
def test_yazma_metotlari_405(istemci, yol: str, metot: str) -> None:
    cevap = getattr(istemci, metot)(yol)
    assert cevap.status_code == 405
    assert "Allow" in cevap.headers


def test_yok_rota_404(istemci) -> None:
    assert istemci.get("/olmayan-sayfa").status_code == 404


# ---------------------------------------------------------------------------
# Güvenlik başlıkları
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("yol", ["/", "/api/graf", "/api/not/1", "/kirik", "/yetim", "/saglik"])
def test_guvenlik_basliklari(istemci, yol: str) -> None:
    basliklar = istemci.get(yol).headers
    assert basliklar["Content-Security-Policy"] == (
        "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    )
    assert basliklar["X-Content-Type-Options"] == "nosniff"
    assert basliklar["Referrer-Policy"] == "no-referrer"
    assert basliklar["Cache-Control"] == "no-store"


def test_guvenlik_basliklari_405_ve_404_ve_403(istemci) -> None:
    for cevap in (
        istemci.post("/"),
        istemci.get("/olmayan"),
        istemci.get("/", headers={"Host": "kotu.example"}),
    ):
        assert cevap.headers["X-Content-Type-Options"] == "nosniff"
        assert "frame-ancestors 'none'" in cevap.headers["Content-Security-Policy"]


def test_statik_dosyalar_yine_guvenli(istemci) -> None:
    for ad in ("/static/graf.js", "/static/stil.css"):
        cevap = istemci.get(ad)
        assert cevap.status_code == 200
        assert cevap.headers["X-Content-Type-Options"] == "nosniff"
        assert "default-src 'none'" in cevap.headers["Content-Security-Policy"]


# ---------------------------------------------------------------------------
# DNS rebinding koruması
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "host",
    ["127.0.0.1", "127.0.0.1:8765", "localhost", "localhost:9999", "LOCALHOST:8765"],
)
def test_loopback_host_kabul(istemci, host: str) -> None:
    assert istemci.get("/", headers={"Host": host}).status_code == 200


@pytest.mark.parametrize(
    "host",
    [
        "kotu.example",
        "evil.com",
        "localhost.evil.com",
        "127.0.0.1.evil.com",
        "0.0.0.0",
        "192.168.1.10:8765",
        "[::1]:8765",
        "",
    ],
)
def test_loopback_disi_host_403(istemci, host: str) -> None:
    assert istemci.get("/", headers={"Host": host}).status_code == 403


def test_host_kontrolu_yoksa_403(istemci) -> None:
    """Host başlığı tamamen yoksa da reddedilir (yok sayılan değer: boş)."""
    cevap = istemci.get("/", headers={"Host": ""})
    assert cevap.status_code == 403


def test_host_kontrolu_kirik_indexe_dokunmaz(db: Path) -> None:
    """Reddedilen istek indeksi hiç açmaz."""
    uygulama = sunucu.app_olustur(db)
    with uygulama.test_client() as c:
        assert c.get("/api/graf", headers={"Host": "kotu.example"}).status_code == 403


# ---------------------------------------------------------------------------
# Salt-okunurluk
# ---------------------------------------------------------------------------

def test_db_salt_okunur_acilir(db: Path) -> None:
    """Web'in açtığı bağlantıya yazma denemesi hata verir."""
    b = sunucu.indeks_modulu.baglan_salt_okunur(db)
    try:
        assert b.execute("SELECT COUNT(*) FROM notes").fetchone()[0] > 0
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            b.execute("INSERT INTO notes (yol, baslik, mtime, karakter) VALUES ('x', 'y', 0, 0)")
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            b.execute("DELETE FROM notes")
    finally:
        b.close()


def test_web_istekleri_indeksi_degistirmez(db: Path) -> None:
    """Tüm GET rotaları DB dosyasının SHA256'sını değiştirmez."""
    once = db.read_bytes()
    with sunucu.app_olustur(db).test_client() as c:
        for yol in ("/", "/api/graf", "/api/not/1", "/api/not/999", "/kirik", "/yetim", "/saglik"):
            c.get(yol)
    assert db.read_bytes() == once


def test_web_akisi_vaultu_degistirmez(mini_vault: Path, tmp_path: Path) -> None:
    """`harita web` indeksleme + sunma akışı vault'a dokunmaz."""
    once = vault_hashleri(mini_vault)
    db = tmp_path / "ro-web.db"
    indeksle(mini_vault, db)
    with sunucu.app_olustur(db).test_client() as c:
        for yol in ("/", "/api/graf", "/kirik", "/yetim"):
            c.get(yol)
    assert vault_hashleri(mini_vault) == once
    assert set(once) == set(vault_hashleri(mini_vault))


def test_web_modulunde_vault_yazma_yolu_yok() -> None:
    """Web paketinde vault'a yazan hiçbir çağrı yok."""
    for dosya in (KOK / "harita" / "web").rglob("*.py"):
        kaynak = dosya.read_text(encoding="utf-8")
        assert ".write_text" not in kaynak, dosya.name
        assert ".write_bytes" not in kaynak, dosya.name
        assert "os.remove" not in kaynak, dosya.name
        assert "shutil" not in kaynak, dosya.name


# ---------------------------------------------------------------------------
# XSS
#
# NOT BAŞLIKLARI KULLANICI İÇERİĞİDİR. İki katmanlı savunma:
#   1. HTML rotalarında Jinja autoescape → özel karakterler `&lt;` olur.
#   2. JS DOM'a yalnızca `textContent`/`setAttribute` yazar (içerik testiyle
#      kanıtlanır; tarayıcıdaki `window.__xss` testi `test_web_e2e.py`'de).
#
# NOT: JSON gövdesi metni olduğu gibi taşır — kaçış JSON'un işi değildir,
# hatta kaçışsız taşımak DOĞRU davranıştır (`</script>` kaçırdırmak veri
# bozar). HTML'e gömme sorumluluğu autoescape'tedir.
# ---------------------------------------------------------------------------

KIRLI_AD = "kutu/" + XSS_BASLIK + ".md"


def _sayfalar(vault: Path, db_adi: str) -> tuple[str, str, str]:
    """(tüm HTML sayfaları, /kirik, /yetim) — XSS yüzeylerini toplar."""
    db = Path(db_adi)
    indeksle(vault, db)
    with sunucu.app_olustur(db).test_client() as c:
        kirik = c.get("/kirik").get_data(as_text=True)
        yetim = c.get("/yetim").get_data(as_text=True)
        ana = c.get("/").get_data(as_text=True)
    return "\n".join((ana, kirik, yetim)), kirik, yetim


def test_xss_ham_etiket_hicbir_sayfada_yok(xss_vault: Path, tmp_path: Path) -> None:
    """Başlık yükleri `<`/`>` KAÇIŞLI basılır: hiçbir yerde gerçek etiket olmaz."""
    hepsi, _, _ = _sayfalar(xss_vault, tmp_path / "xss-a.db")
    for ham in ("<script>", "<img", "<b>hic-boyle-not"):
        assert ham not in hepsi, ham


def test_xss_kirik_link_metni_autoescape_ile_kacisli(xss_vault: Path, tmp_path: Path) -> None:
    """Gövdedeki düz `[[XSS_HEDEF]]` gerçek kırık linktir ve kaçışlı basılır."""
    _, kirik, _ = _sayfalar(xss_vault, tmp_path / "xss-b.db")
    assert "[[&lt;b&gt;hic-boyle-not&lt;/b&gt;]]" in kirik
    assert "<b>hic-boyle-not" not in kirik


def test_xss_not_basligi_html_e_girmez(xss_vault: Path, tmp_path: Path) -> None:
    """Kirli başlıklar link aldıkları için yetim değildir → HTML'e hiç girmez."""
    hepsi, _, _ = _sayfalar(xss_vault, tmp_path / "xss-c.db")
    assert XSS_BASLIK not in hepsi
    assert XSS_BASLIK2 not in hepsi
    assert "<img" not in hepsi
    assert "onerror=window.__xss2" not in hepsi, "payload hiçbir yerde ham değil"


def test_xss_json_icerik_korumasi(xss_vault: Path, tmp_path: Path) -> None:
    """JSON yükleri DEĞER olarak birebir korur (kaçış yok, veri kaybı yok)."""
    db = tmp_path / "xss-json.db"
    indeksle(xss_vault, db)
    with sunucu.app_olustur(db).test_client() as c:
        veri = c.get("/api/graf").get_json()
        detay = next(
            c.get(f"/api/not/{d['id']}").get_json() for d in veri["dugumler"] if d["yol"] == KIRLI_AD
        )
    assert KIRLI_AD in [d["yol"] for d in veri["dugumler"]]
    assert detay["baslik"] == XSS_BASLIK
    assert detay["id"] in {d["id"] for d in veri["dugumler"]}


def test_api_not_ozet_gozden_gelir(xss_vault: Path, tmp_path: Path) -> None:
    """Özet notun gövdesinden gelir (chunks), ham dosya yeniden okunmaz."""
    db = tmp_path / "xss-ozet.db"
    indeksle(xss_vault, db)
    with sunucu.app_olustur(db).test_client() as c:
        veri = next(
            c.get(f"/api/not/{d['id']}").get_json()
            for d in c.get("/api/graf").get_json()["dugumler"]
            if d["yol"] == KIRLI_AD
        )
    assert "Zararli" in veri["ozet"]


def test_js_yalnizca_text_content_kullanir() -> None:
    """Graf JS'i DOM'a HTML hiç yazmaz; metin yolları `textContent`."""
    js = (KOK / "harita" / "web" / "static" / "graf.js").read_text(encoding="utf-8")
    for yasak in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
        assert yasak not in js, yasak
    # Kullanıcı metni giden yollar: textContent (DOM) ve setAttribute (SVG).
    assert ".textContent = " in js
    assert "etiket.textContent = d.baslik" in js


def test_sablon_autoescape_acik(xss_vault: Path, tmp_path: Path) -> None:
    """Autoescape kapalı olsaydı ham `<script>` çıkardı; burada `&lt;` çıkar."""
    db = tmp_path / "ae.db"
    indeksle(xss_vault, db)
    uygulama = sunucu.app_olustur(db)
    assert uygulama.jinja_env.autoescape
    with uygulama.test_client() as c:
        kirik = c.get("/kirik").get_data(as_text=True)
    assert "&lt;b&gt;hic-boyle-not&lt;/b&gt;" in kirik
    assert "<b>hic-boyle-not" not in kirik


# ---------------------------------------------------------------------------
# CSP uyumu: şablonlarda satır içi script/stil YOK
# ---------------------------------------------------------------------------

def test_sablonlarda_satir_ici_script_yok() -> None:
    desen = re.compile(r"<script\b(?![^>]*\bsrc=)[^>]*>", re.IGNORECASE)
    for sablon in (KOK / "harita" / "web" / "sablonlar").glob("*.html"):
        icerik = sablon.read_text(encoding="utf-8")
        bulunan = desen.search(icerik)
        assert bulunan is None, f"{sablon.name}: {bulunan.group(0) if bulunan else ''}"


def test_sablonlarda_satir_ici_stil_yok() -> None:
    desen = re.compile(r"\sstyle\s*=", re.IGNORECASE)
    for sablon in (KOK / "harita" / "web" / "sablonlar").glob("*.html"):
        icerik = sablon.read_text(encoding="utf-8")
        assert not desen.search(icerik), sablon.name


def test_sablonlarda_event_handler_yok() -> None:
    desen = re.compile(r"\son[a-z]+\s*=\s*[\"']", re.IGNORECASE)
    for sablon in (KOK / "harita" / "web" / "sablonlar").glob("*.html"):
        icerik = sablon.read_text(encoding="utf-8")
        assert not desen.search(icerik), sablon.name


def test_html_gercek_sayfada_satir_ici_script_stil_yok(istemci) -> None:
    """Sunucudan gelen HTML'de de satır içi script/stil bulunmaz."""
    govde = istemci.get("/").get_data(as_text=True)
    assert not re.search(r"<script\b(?![^>]*\bsrc=)", govde, re.IGNORECASE)
    assert not re.search(r"\sstyle\s*=", govde, re.IGNORECASE)
    # JS ve CSS yalnızca statik dosyadan yüklenir.
    assert "/static/graf.js" in govde
    assert "/static/stil.css" in govde


def test_kirik_ve_yetim_sayfalarinda_da_satir_ici_yok(istemci) -> None:
    for yol in ("/kirik", "/yetim"):
        govde = istemci.get(yol).get_data(as_text=True)
        assert not re.search(r"\sstyle\s*=", govde, re.IGNORECASE)
        assert not re.search(r"\son[a-z]+\s*=\s*[\"']", govde, re.IGNORECASE)


# ---------------------------------------------------------------------------
# CLI: `harita web`
# ---------------------------------------------------------------------------

def test_web_komutu_host_secenegi_yok() -> None:
    """`--host` BİLEREK yoktur: sunucu yalnız 127.0.0.1'e bağlanır."""
    from harita.cli import arg_parser

    with pytest.raises(SystemExit):
        arg_parser().parse_args(["web", "--host", "0.0.0.0"])


def test_web_komutu_port_varsayilani_ve_yolu() -> None:
    from harita.cli import arg_parser

    args = arg_parser().parse_args(["web", "/tmp/vault", "--port", "8899"])
    assert args.vault == "/tmp/vault"
    assert args.port == 8899
    assert arg_parser().parse_args(["web"]).port == 8765


def test_web_komutu_vault_verilmezse_indeks_hatasi(tmp_path: Path, capsys) -> None:
    """VAULT yoksa ve DB yoksa anlamlı hata verir (sunucu başlamaz)."""
    kod = cli_main(["web", "--db", str(tmp_path / "yok.db")])
    assert kod == 2
    assert "indeks bulunamadı" in capsys.readouterr().err.lower()


def test_web_komutu_olmayan_vault_hata(tmp_path: Path, capsys) -> None:
    kod = cli_main(["web", str(tmp_path / "olmayan"), "--db", str(tmp_path / "x.db")])
    assert kod == 2
    assert "vault bulunamadı" in capsys.readouterr().err


def test_web_komutu_yetim_tumu_bayragi(tmp_path: Path, capsys) -> None:
    """`harita yetim` varsayılan gerçek yetimleri, `--tumu` hepsini listeler."""
    vault = tmp_path / "yetim-cli"
    vault.mkdir()
    yaz(vault, "bagli.md", "# Bağlı\n[[serbest]]\n")
    yaz(vault, "serbest.md", "# Serbest\n")
    yaz(vault, "kose/not.md", "# Köşe\n")
    yaz(vault, "daily/2026-02-02.md", "# Günlük\n")
    db = tmp_path / "yetim-cli.db"
    assert cli_main(["indeksle", str(vault), "--db", str(db)]) == 0
    capsys.readouterr()

    assert cli_main(["yetim", "--db", str(db)]) == 0
    varsayilan = capsys.readouterr().out
    assert "kose/not.md" in varsayilan
    assert "serbest.md" not in varsayilan  # link ALAN not gerçek yetim değil
    assert "2026-02-02.md" not in varsayilan
    assert "yok sayılabilir" in varsayilan

    assert cli_main(["yetim", "--tumu", "--db", str(db)]) == 0
    tumu = capsys.readouterr().out
    assert "serbest.md" not in tumu  # --tumu DA yalnız link vermeyenleri listeler
    assert "kose/not.md" in tumu
    assert "2026-02-02.md" in tumu


def test_web_sunucusu_yalnizca_loopback_dinler() -> None:
    """Kaynak kodda adres sabit: `0.0.0.0`/dışarı adres yok."""
    kaynak = (KOK / "harita" / "web" / "sunucu.py").read_text(encoding="utf-8")
    assert 'host="127.0.0.1"' in kaynak
    for kotu in ('host="0.0.0.0"', 'host="::"', "0.0.0.0"):
        assert kotu not in kaynak


def test_web_sunucusu_gercek_surec_loopback_dinler(mini_vault: Path, tmp_path: Path) -> None:
    """Gerçek `harita web` süreci 127.0.0.1'e bağlanır, 0.0.0.0'a DEĞİL."""
    import socket
    import time
    import urllib.error
    import urllib.request

    db = tmp_path / "surec.db"
    indeksle(mini_vault, db)
    port = _bos_port()
    surec = subprocess.Popen(
        [sys.executable, "-m", "harita", "web", "--db", str(db), "--port", str(port)],
        cwd=str(KOK),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, "PYTHONPATH": str(KOK), "PYTHONIOENCODING": "utf-8"},
    )
    try:
        taban = f"http://127.0.0.1:{port}"
        _bekle(taban, surec)
        with urllib.request.urlopen(f"{taban}/saglik", timeout=5) as cevap:
            assert cevap.status == 200
        # Aynı port 0.0.0.0 üzerinden dışarıdan da erişilemez: adres zaten
        # loopback'e bağlı, bu yüzden yerel olmayan arayüzden bağlantı reddedilir.
        # `_dis_adresler()` bir LİSTE döner (yinelenenler olabilir, ör. CI çalıştırıcıları);
        # her dış adres ayrı ayrı denenir. (Eskiden liste URL'e gömülüyordu: dış arayüzü
        # olmayan konteynerde liste hep boştu, bu dal hiç koşmamış ve hata CI'da çıktı.)
        # TCP seviyesinde denenir: HTTP ile denemek Flask'ın `Host` başlığı denetimini (403)
        # "reddedildi" sanıp sunucu 0.0.0.0'a bağlı olsa bile geçerdi.
        for dis_adres in dict.fromkeys(_dis_adresler()):
            with pytest.raises(OSError):
                socket.create_connection((dis_adres, port), timeout=3).close()
    finally:
        surec.terminate()
        try:
            surec.wait(timeout=10)
        except subprocess.TimeoutExpired:  # pragma: no cover
            surec.kill()
            surec.wait(timeout=5)


def _bos_port() -> int:
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _dis_adresler() -> list[str]:
    """Makineye ait loopback DIŞI IPv4 adresleri (yoksa boş liste)."""
    import socket

    adresler = []
    try:
        for bilgi in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = bilgi[4][0]
            if not ip.startswith("127."):
                adresler.append(ip)
    except OSError:  # pragma: no cover
        return []
    return adresler


def _bekle(taban: str, surec: subprocess.Popen, zaman_asimi: float = 25.0) -> None:
    import time
    import urllib.error
    import urllib.request

    son = time.time() + zaman_asimi
    while time.time() < son:
        if surec.poll() is not None:
            hata = surec.stderr.read().decode("utf-8", "replace") if surec.stderr else ""
            raise AssertionError(f"sunucu erken kapandı: {hata}")
        try:
            with urllib.request.urlopen(f"{taban}/saglik", timeout=2):
                return
        except (urllib.error.URLError, OSError):
            time.sleep(0.2)
    raise AssertionError("sunucu zamanında ayağa kalkmadı")


# ---------------------------------------------------------------------------
# Statik varlıklar ve paket içeriği
# ---------------------------------------------------------------------------

def test_statik_dosyalar_paket_icinde() -> None:
    kok = KOK / "harita" / "web"
    assert (kok / "static" / "graf.js").exists()
    assert (kok / "static" / "stil.css").exists()
    for ad in ("graf.html", "kirik.html", "yetim.html"):
        assert (kok / "sablonlar" / ad).exists()


def test_graf_js_yok_sayilabilir_klasor_ve_diger_yok() -> None:
    """Lejantta "diğer" kuralı JS'te tanımlı."""
    js = (KOK / "harita" / "web" / "static" / "graf.js").read_text(encoding="utf-8")
    assert "diğer (" in js
    assert "#999999" in js


def test_requirements_flask_ve_playwright() -> None:
    req = (KOK / "requirements.txt").read_text(encoding="utf-8")
    assert "flask>=3.0" in req
    dev = (KOK / "requirements-dev.txt").read_text(encoding="utf-8")
    assert "playwright" in dev
    assert "requirements.txt" in dev, "dev bağımlılıkları üretim dosyasını içe aktarmalı"

# ---------------------------------------------------------------------------
# Ekran görüntüleri: gerçek veri sızmaz
# ---------------------------------------------------------------------------


def test_ekran_goruntusu_scripti_kurgusal_vault_uretir() -> None:
    """`scripts/ekran_goruntusu.py` içindeki tüm notlar kurgusal kurgu üretir."""
    kaynak = (KOK / "scripts" / "ekran_goruntusu.py").read_text(encoding="utf-8")
    # Gerçek vault yolu, e-posta ve anahtar kalıpları betikte geçmemeli.
    for yasak in ("/home/user", "Mt3", "Users\\", "@gmail", "sk-"):
        assert yasak not in kaynak, yasak
    # Tüm içerik tek bir kurgusal sözlükte toplanır.
    assert "KURGUSAL_NOTLAR" in kaynak


def test_ekran_goruntusu_cikti_dizini_dort_png() -> None:
    """README'de gösterilen dört PNG gerçekten üretilmiş ve repoda var."""
    klasor = KOK / "docs" / "ekran"
    for ad in ("graf-masaustu.png", "graf-panel-acik.png", "graf-mobil.png", "kirik-liste.png"):
        yol = klasor / ad
        assert yol.exists(), ad
        assert yol.stat().st_size > 5000, f"{ad} boş görünüyor"
    readme = (KOK / "README.md").read_text(encoding="utf-8")
    for ad in ("graf-masaustu.png", "graf-panel-acik.png", "graf-mobil.png", "kirik-liste.png"):
        assert f"docs/ekran/{ad}" in readme, f"README'de {ad} yok"


def test_readme_gercek_vault_verisi_icermiyor() -> None:
    """README ve testler gerçek vault yolu/e-posta/başlığı taşımaz."""
    # Yasak dizeler parçalardan kurulur; bu testin kendi kaynağı onları içermez.
    parcalar = (
        ("umut", "6"),
        ("Mt3", "Ui5"),
        ("/home/", "user/Mt3"),
        ("@gm", "ail.com"),
    )
    yasaklar = ["".join(p) for p in parcalar]
    for dosya in sorted((KOK / "tests").rglob("*.py")) + [
        KOK / "README.md",
        KOK / "scripts" / "ekran_goruntusu.py",
    ]:
        icerik = Path(dosya).read_text(encoding="utf-8")
        bas = icerik.find("    for dosya in sorted")
        if bas != -1:
            icerik = icerik[bas:]
        for yasak in yasaklar:
            assert yasak not in icerik, f"{dosya.name}: {yasak}"
