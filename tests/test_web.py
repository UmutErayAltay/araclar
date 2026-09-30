"""Dalga C web paneli: Flask test client ile rota, guvenlik ve veri testleri.

Kapsam: tum rotalar 200/404/405, JSON sekilleri, bos DB, guvenlik basliklari,
Host dogrulama (403 + reddedilen istek DB acmaz), `mode=ro`, suzgecler ve
sayfalama, XSS (asagida `test_web_xss.py`).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from conftest import db_doldur

def _taze(zaman_saat_geri=1):
    """`scanned_at` icin GORECELI zaman: test yarin da gecer.

    Sabit tarih kullanmak "zaman bombasi" yaratir: 24 saat uzeri gecince
    `veri_bayat` yanlislikla True olur ve "taze veri" testleri kirilir.
    """
    from datetime import datetime, timedelta, timezone

    return (datetime.now(timezone.utc) - timedelta(hours=zaman_saat_geri)).isoformat(
        timespec="seconds"
    )


from atlas import db as db_mod
from atlas.web import app_olustur

SAYFALAR = ["/", "/yarim-is", "/sizinti", "/borc", "/bayat-readme"]
APILER = ["/api/ozet", "/api/yarim-is", "/api/bulgular", "/api/borc", "/api/bayat-readme", "/saglik"]


@pytest.fixture
def dolu_db(tmp_path: Path) -> Path:
    """Kurgusal (uydurma) veriyle doldurulmuş DB — gerçek ad/yol YOK."""
    yol = tmp_path / "dolu.db"
    db_doldur(
        yol,
        repos=[
            {"path": "/kurgusal/ornek-api", "name": "ornek-api", "dirty": 3,
             "unpushed": 2, "branch": "main", "last_commit_at": "2026-09-29T10:00:00+00:00",
             "has_remote": 1, "scanned_at": _taze()},
            {"path": "/kurgusal/demo-arayuz", "name": "demo-arayuz", "dirty": 0,
             "unpushed": None, "branch": "feat/yeni", "last_commit_at": "2026-09-28T10:00:00+00:00",
             "has_remote": 1, "scanned_at": _taze()},
            {"path": "/kurgusal/temiz-repo", "name": "temiz-repo", "dirty": 0,
             "unpushed": 0, "branch": "main", "last_commit_at": "2026-09-27T10:00:00+00:00",
             "has_remote": 0, "scanned_at": _taze()},
        ],
        findings=[
            {"repo": "/kurgusal/ornek-api", "kind": "api-anahtari", "severity": "yuksek",
             "file": "app/sablon.py", "line": 12, "commit": None,
             "snippet_redacted": "…[maskeli:api-anahtari]…"},
            {"repo": "/kurgusal/ornek-api", "kind": "ozel-anahtar", "severity": "yuksek",
             "file": "certs/id.pem", "line": 1, "commit": "abc1234",
             "snippet_redacted": "-----BEGIN RSA PRIVATE KEY-----…"},
            {"repo": "/kurgusal/demo-arayuz", "kind": "e-posta", "severity": "dusuk",
             "file": "iletisim.md", "line": 4, "commit": None,
             "snippet_redacted": "iletisim: <e-posta>"},
            {"repo": "/kurgusal/demo-arayuz", "kind": "env-izlenen", "severity": "yuksek",
             "file": ".env", "line": None, "commit": None, "snippet_redacted": None},
            {"repo": "/kurgusal/temiz-repo", "kind": "gorsel-elle-kontrol", "severity": "bilgi",
             "file": "docs/ekran/a.png", "line": None, "commit": None,
             "snippet_redacted": "elle kontrol et"},
        ],
        todos=[
            {"repo": "/kurgusal/ornek-api", "file": "app/sablon.py", "line": 3,
             "text": "# TODO: burayi ayir"},
            {"repo": "/kurgusal/ornek-api", "file": "app/sablon.py", "line": 44,
             "text": "# FIXME: hata durumu eksik"},
            {"repo": "/kurgusal/demo-arayuz", "file": "src/panel.js", "line": 88,
             "text": "// HACK: gecici, sonra duzelt"},
            {"repo": "/kurgusal/temiz-repo", "file": "README.md", "line": 2,
             "text": "# XXX: belge eksik"},
        ],
    )
    return yol


@pytest.fixture
def dolu_client(dolu_db: Path):
    return app_olustur(dolu_db).test_client()


# --------------------------------------------------------------------------
# Rota yuzeyi
# --------------------------------------------------------------------------


@pytest.mark.parametrize("yol", SAYFALAR)
def test_sayfalar_200(dolu_client, yol: str):
    assert dolu_client.get(yol).status_code == 200


@pytest.mark.parametrize("yol", APILER)
def test_api_200(dolu_client, yol: str):
    assert dolu_client.get(yol).status_code == 200


@pytest.mark.parametrize("yol", SAYFALAR)
def test_bos_db_sayfalar_200_anlamli_bos_durum(web_client, yol: str):
    """Bos DB çökmez: her sayfa 200 ve BOS DURUM metni doner."""
    r = web_client.get(yol)
    assert r.status_code == 200
    assert "bos-durum" in r.data.decode("utf-8")


@pytest.mark.parametrize("yol", APILER)
def test_bos_db_api_200(web_client, yol: str):
    """Bos DB'de API de anlamli JSON doner (sayfalar kadar derin gostermez)."""
    r = web_client.get(yol)
    assert r.status_code == 200
    v = _json(r)  # gecerli JSON
    assert isinstance(v, dict)


def test_bayat_readme_dalga_d_var(web_client):
    """`/bayat-readme` Dalga D ile eklendi: bos DB'de 200 + bos durum."""
    r = web_client.get("/bayat-readme")
    assert r.status_code == 200
    assert "bos-durum" in r.data.decode("utf-8")


def test_repo_sayfasi_200_ve_detay(dolu_client):
    import sqlite3 as s3

    conn = s3.connect(":memory:")
    del conn
    # rowid = `repos` tablosunun satir kimligi (AD DEGIL).
    db_yol = dolu_client.application.config["ATLAS_DB"]
    con = s3.connect(db_yol)
    con.row_factory = s3.Row
    repo_id = con.execute("SELECT rowid FROM repos WHERE name = 'ornek-api'").fetchone()["rowid"]
    con.close()
    r = dolu_client.get(f"/repo/{repo_id}")
    assert r.status_code == 200
    assert b"ornek-api" in r.data
    assert b"/kurgusal/ornek-api" in r.data
    assert b"TODO" in r.data


def test_repo_yoksa_404(dolu_client):
    assert dolu_client.get("/repo/9999").status_code == 404


def test_repo_id_sayisal_degil_404(dolu_client):
    """Rota yüzeyi sayısal id'dir; isim/yol kabul edilmez."""
    assert dolu_client.get("/repo/ornek-api").status_code == 404


@pytest.mark.parametrize("yol", SAYFALAR + APILER + ["/repo/1", "/saglik"])
def test_yalnizca_get_dolu_client(dolu_client, yol: str):
    """Tum rotalar salt-GET: diger metotlar 405."""
    for metot in ("post", "put", "delete", "patch"):
        r = getattr(dolu_client, metot)(yol)
        assert r.status_code == 405, f"{metot.upper()} {yol} -> {r.status_code}"


# --------------------------------------------------------------------------
# Guvenlik basliklari
# --------------------------------------------------------------------------

CSP_BEKLENEN = (
    "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)


@pytest.mark.parametrize("yol", SAYFALAR + APILER + ["/repo/1"])
def test_guvenlik_basliklari_tum_rotalarda(dolu_client, yol: str):
    r = dolu_client.get(yol)
    assert r.status_code == 200
    assert r.headers["Content-Security-Policy"] == CSP_BEKLENEN
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["Referrer-Policy"] == "no-referrer"
    assert r.headers["Cache-Control"] == "no-store"


def test_guvenlik_basliklari_404_ve_403_ve_405(dolu_client):
    for r in (
        dolu_client.get("/repo/9999"),
        dolu_client.get("/", headers={"Host": "kotu.example.com"}),
        dolu_client.post("/"),
    ):
        assert r.headers["Content-Security-Policy"] == CSP_BEKLENEN
        assert r.headers["X-Content-Type-Options"] == "nosniff"


def test_satir_ici_script_ve_stil_yok(dolu_client):
    """CSP `script-src 'self'`: HTML'de satir ici <script> ve style= OLMAMALI."""
    for yol in SAYFALAR:
        govde = dolu_client.get(yol).data.decode("utf-8")
        assert "<script>" not in govde
        assert "style=" not in govde
        assert "javascript:" not in govde


# --------------------------------------------------------------------------
# Host dogrulama (DNS rebinding)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "host",
    ["127.0.0.1", "127.0.0.1:8770", "localhost", "localhost:8770", "LOCALHOST:1"],
)
def test_izinli_host_200(dolu_client, host: str):
    assert dolu_client.get("/", headers={"Host": host}).status_code == 200


@pytest.mark.parametrize(
    "host",
    [
        "evil.example.com",
        "127.0.0.1.evil.com",
        "localhost.evil.com",
        "192.168.1.10",
        "127.0.0.1.evil.com:8770",
        "user@localhost",  # kullanici bilgisi ile sahte host
        "",
    ],
)
def test_yasakli_host_403(dolu_client, host: str):
    r = dolu_client.get("/", headers={"Host": host})
    assert r.status_code == 403


def test_reddedilen_istek_db_acmaz(dolu_db: Path):
    """403 alan istek hicbir sorgu YAPMAZ (baglanti acilmaz)."""
    app = app_olustur(dolu_db)
    client = app.test_client()
    acilan = []
    gercek_ac = sqlite3.connect

    def gozlemci(*a, **kw):
        acilan.append(a)
        return gercek_ac(*a, **kw)

    import atlas.web.sunucu as sunucu

    sunucu.sqlite3.connect = gozlemci
    try:
        r = client.get("/api/ozet", headers={"Host": "kotu.example.com"})
    finally:
        sunucu.sqlite3.connect = gercek_ac
    assert r.status_code == 403
    assert acilan == [], f"reddedilen istek DB acmaliydi: {acilan}"


# --------------------------------------------------------------------------
# mode=ro
# --------------------------------------------------------------------------


def test_db_mode_ro(dolu_db: Path):
    """Panel DB'yi `mode=ro` ile acar: yazma denemesi hata verir."""
    from atlas.web.sunucu import db_ac

    conn = db_ac(dolu_db)
    try:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("INSERT INTO repos (path, name, scanned_at) VALUES ('x', 'x', 'x')")
    finally:
        conn.close()


def test_panel_yazma_yapmaz(dolu_db: Path, dolu_client):
    """Tum sayfalar gezildikten sonra DB baytlari AYNI kalmali."""
    once = dolu_db.read_bytes()
    for yol in SAYFALAR + APILER + ["/repo/1"]:
        dolu_client.get(yol)
    assert dolu_db.read_bytes() == once


def test_panel_tarama_tetiklemez(dolu_db: Path, dolu_client, monkeypatch):
    """Panel repolara dokunmaz: hicbir git/scan cagrisi yapilmaz."""
    import atlas.scan as scan_mod

    cagrilan = []
    monkeypatch.setattr(scan_mod, "find_repo_paths", lambda *a, **k: cagrilan.append(a))
    monkeypatch.setattr(scan_mod, "find_repos", lambda *a, **k: cagrilan.append(a))
    import atlas.leaks as leaks_mod

    monkeypatch.setattr(leaks_mod, "ls_files", lambda *a, **k: cagrilan.append(a))
    for yol in SAYFALAR + APILER:
        dolu_client.get(yol)
    assert cagrilan == [], f"panel tarama tetikledi: {cagrilan}"


def test_db_yazilamaz_dosya_olsaydi_da_okur(dolu_db: Path):
    """Salt-okunur mod: dosya yazma izni olmasa da acilabilir (goreli chmod)."""
    import os

    if os.geteuid() == 0:
        pytest.skip("root: chmod ile salt-okunur dosya uretilemiyor")
    yedek = dolu_db.stat().st_mode
    try:
        dolu_db.chmod(0o444)
        client = app_olustur(dolu_db).test_client()
        assert client.get("/").status_code == 200
    finally:
        dolu_db.chmod(yedek)


# --------------------------------------------------------------------------
# API sekilleri
# --------------------------------------------------------------------------


def _json(r):
    return json.loads(r.data.decode("utf-8"))


def test_api_ozet_sekli(dolu_client):
    v = _json(dolu_client.get("/api/ozet"))
    assert v["repo_sayisi"] == 3
    assert v["kirli_repo"] == 1
    assert v["push_bekleyen"] == 1
    assert v["push_bilinmeyen"] == 1
    assert v["toplam_todo"] == 4
    assert v["toplam_bulgu"] == 5
    assert v["bulgu_sayaclari"]["yuksek"] == 3
    assert v["bulgu_sayaclari"]["dusuk"] == 1
    assert v["bulgu_sayaclari"]["bilgi"] == 1
    assert "son_tarama" in v and "veri_bayat" in v


def test_api_yarim_is_uc_bolum(dolu_client):
    v = _json(dolu_client.get("/api/yarim-is"))
    assert set(v) == {"kirli", "push_bekleyen", "push_bilinmeyen"}
    assert [x["name"] for x in v["kirli"]] == ["ornek-api"]
    assert [x["name"] for x in v["push_bekleyen"]] == ["ornek-api"]
    assert [x["unpushed"] for x in v["push_bekleyen"]] == [2]
    assert [x["name"] for x in v["push_bilinmeyen"]] == ["demo-arayuz"]
    # Her kayıt tıklanabilir sayısal id taşır (ad DEĞİL).
    assert all(isinstance(x["id"], int) for k in v for x in v[k])


def test_api_bulgular_sayfalama_ve_suzgec(dolu_client):
    v = _json(dolu_client.get("/api/bulgular"))
    assert v["toplam"] == 5
    assert v["sayfa"] == 1
    assert v["sayfa_boyutu"] == 100
    assert v["toplam_sayfa"] == 1
    assert len(v["kayitlar"]) == 5
    # Önem sırası: yüksek -> bilgi
    onemler = [k["onem"] for k in v["kayitlar"]]
    assert onemler == ["yuksek", "yuksek", "yuksek", "dusuk", "bilgi"]

    v = _json(dolu_client.get("/api/bulgular?siddet=yuksek"))
    assert v["toplam"] == 3
    assert all(k["onem"] == "yuksek" for k in v["kayitlar"])

    v = _json(dolu_client.get("/api/bulgular?tur=api-anahtari"))
    assert v["toplam"] == 1
    assert v["kayitlar"][0]["tur"] == "api-anahtari"

    v = _json(dolu_client.get("/api/bulgular?repo=/kurgusal/demo-arayuz"))
    assert v["toplam"] == 2


def test_api_bulgular_konum_alanlari(dolu_client):
    v = _json(dolu_client.get("/api/bulgular"))
    bulgu = next(k for k in v["kayitlar"] if k["commit"])
    assert bulgu["yer"] == "geçmişte"
    bulgu2 = next(k for k in v["kayitlar"] if not k["commit"])
    assert bulgu2["yer"] == "çalışma ağacında"


def test_api_borc_sekli(dolu_client):
    v = _json(dolu_client.get("/api/borc"))
    assert v["toplam"] == 4
    assert v["en_cok"] == 2
    yo = [(x["repo"], x["adet"], round(x["oran"])) for x in v["ozet"]]
    assert yo[0] == ("ornek-api", 2, 100)  # en yoğun = %100
    assert yo[1][1] == 1
    assert all(0 <= x["oran"] <= 100 for x in v["ozet"])
    assert len(v["kayitlar"]) == 4


def test_api_bos_db_zayif_sekiller(web_client):
    for yol in APILER:
        r = web_client.get(yol)
        assert r.status_code == 200
        _json(r)


# --------------------------------------------------------------------------
# Sayfa ici davranis
# --------------------------------------------------------------------------


def test_sizinti_sayfasi_suzgec_formu(dolu_client):
    govde = dolu_client.get("/sizinti").data.decode("utf-8")
    assert 'name="siddet"' in govde
    assert 'name="tur"' in govde
    assert 'name="repo"' in govde
    assert "<select" in govde and "<button" in govde


def _masaustu_tablo(govde: str) -> str:
    """Masaüstü tablo bloğu (mobil kart listesi aynı kayıtları TEKRAR basar)."""
    assert 'class="tablo-sarayici"' in govde, "masaüstü tablo bekleniyordu"
    return govde.split('class="tablo-sarayici"', 1)[1].split('class="kart-liste"', 1)[0]


def test_sizinti_suzgec_uygulanir(dolu_client):
    """`?siddet=yuksek` yalnizca yüksek rozetli kayitlari gosterir."""
    govde = dolu_client.get("/sizinti?siddet=yuksek").data.decode("utf-8")
    tablo = _masaustu_tablo(govde)
    assert tablo.count('class="rozet yuksek"') == 3  # yalniz yuksek bulgular
    assert 'class="rozet dusuk"' not in tablo
    assert 'class="rozet bilgi"' not in tablo
    assert "3 bulgu" in govde
    # Filtre formunda secim korunur.
    assert '<option value="yuksek" selected>' in govde


def test_sizinti_temiz_suzgec_tum_kayitlar(dolu_client):
    govde = dolu_client.get("/sizinti").data.decode("utf-8")
    tablo = _masaustu_tablo(govde)
    assert tablo.count('class="rozet yuksek"') == 3
    assert tablo.count('class="rozet dusuk"') == 1
    assert tablo.count('class="rozet bilgi"') == 1
    assert "5 bulgu" in govde


def test_ozet_sayfasi_kartlari(dolu_client):
    govde = dolu_client.get("/").data.decode("utf-8")
    for beklenen in ["Repo", "Kirli repo", "Push bekleyen", "bilinmeyen", "Toplam todo"]:
        assert beklenen in govde


def test_yarim_is_aciklama_fetch_uyarisi(dolu_client):
    govde = dolu_client.get("/yarim-is").data.decode("utf-8")
    assert "fetch yapmaz" in govde


def test_borc_sayfasi_yogunluk_cubugu(dolu_client):
    govde = dolu_client.get("/borc").data.decode("utf-8")
    assert "data-genislik" in govde
    assert "cubuk" in govde


def test_bayatlık_uyarisi_eski_veride(dolu_db: Path, tmp_path: Path):
    """24 saatten eski tarama zamanı uyarıyı gösterir."""
    eski = tmp_path / "eski.db"
    db_doldur(
        eski,
        repos=[{"path": "/kurgusal/r", "name": "r", "dirty": 0, "unpushed": 0,
                "branch": "main", "has_remote": 0, "scanned_at": "2020-01-01T00:00:00+00:00"}],
    )
    c = app_olustur(eski).test_client()
    v = _json(c.get("/api/ozet"))
    assert v["veri_bayat"] is True
    assert "atlas guncelle" in c.get("/").data.decode("utf-8")


def test_taze_veride_uyari_yok(dolu_client):
    v = _json(dolu_client.get("/api/ozet"))
    assert v["veri_bayat"] is False
    assert "uyari-bar" not in dolu_client.get("/").data.decode("utf-8")


# --------------------------------------------------------------------------
# Navigasyon
# --------------------------------------------------------------------------


@pytest.mark.parametrize("yol", SAYFALAR)
def test_navigasyon_her_sayfada_tam(dolu_client, yol: str):
    govde = dolu_client.get(yol).data.decode("utf-8")
    for hedef, etiket in [
        ("/", "Özet"), ("/yarim-is", "Yarım iş"), ("/sizinti", "Sızıntı"), ("/borc", "Borç"),
        ("/bayat-readme", "Bayat README"),
    ]:
        assert f'href="{hedef}"' in govde
        assert etiket in govde


def test_navigasyon_aktif_sayfayi_isaretler(dolu_client):
    for yol, beklenen in [("/", "Özet"), ("/sizinti", "Sızıntı"), ("/borc", "Borç")]:
        govde = dolu_client.get(yol).data.decode("utf-8")
        assert f'aria-current="page"' in govde


def test_static_dosyalar_servis_edilir(dolu_client):
    for dosya in ("stil.css", "panel.js"):
        r = dolu_client.get(f"/static/{dosya}")
        assert r.status_code == 200
        assert r.headers["X-Content-Type-Options"] == "nosniff"


# --------------------------------------------------------------------------
# Dalga D: /bayat-readme, README satırı ve özet (panel SALT OKUNUR)
# --------------------------------------------------------------------------

#: Kurgusal readme_status satırları (skora göre karışık sırada verilir; sayfa
#: skora AZALAN sıralamalıdır).
KURGUSAL_READMELER = [
    {"repo": "/kurgusal/ornek-api", "skor": 9, "seviye": "bayat",
     "behavior_commits_after": 9, "screenshot_age_days": 45, "readme_yolu": "README.md"},
    {"repo": "/kurgusal/demo-arayuz", "skor": 4, "seviye": "eskiyor",
     "behavior_commits_after": 4, "screenshot_age_days": None, "readme_yolu": "README.rst"},
    {"repo": "/kurgusal/temiz-repo", "skor": 1, "seviye": "taze",
     "behavior_commits_after": 1, "screenshot_age_days": None, "readme_yolu": "README.md"},
]


@pytest.fixture
def dalga_d_client(tmp_path: Path):
    """Dalga D verisi dolu panel (readme_status + summaries)."""
    yol = tmp_path / "d.db"
    db_doldur(
        yol,
        repos=[
            {"path": "/kurgusal/ornek-api", "name": "ornek-api", "dirty": 2,
             "unpushed": 1, "branch": "main", "last_commit_at": "2026-09-29T09:12:00+00:00",
             "has_remote": 1, "scanned_at": _taze()},
            {"path": "/kurgusal/demo-arayuz", "name": "demo-arayuz", "dirty": 0,
             "unpushed": None, "branch": "main", "last_commit_at": "2026-09-28T09:00:00+00:00",
             "has_remote": 1, "scanned_at": _taze()},
            {"path": "/kurgusal/temiz-repo", "name": "temiz-repo", "dirty": 0,
             "unpushed": 0, "branch": "main", "last_commit_at": "2026-09-27T09:00:00+00:00",
             "has_remote": 0, "scanned_at": _taze()},
        ],
        readmes=KURGUSAL_READMELER,
        summaries=[
            {"repo": "/kurgusal/ornek-api", "kaynak": "yerel",
             "metin": "- 2 commit'lenmemiş değişiklik var → commit'le\n"
                      "- 1 push edilmemiş commit → push'la"},
            {"repo": "/kurgusal/demo-arayuz", "kaynak": "cor", "model": "sahte/model",
             "metin": "- Önce sızıntı bulgusunu ele al"},
        ],
    )
    return app_olustur(yol).test_client()


def test_bayat_readme_api_skora_gore_sirali(dalga_d_client):
    v = _json(dalga_d_client.get("/api/bayat-readme"))
    skorlar = [k["skor"] for k in v["kayitlar"]]
    assert skorlar == sorted(skorlar, reverse=True), skorlar
    assert v["toplam"] == 3
    assert v["sayaclar"] == {"bayat": 1, "eskiyor": 1, "taze": 1, "yok": 0}
    assert v["bayat_readme"] == 2, "bayat + eskiyor sayilir"


def test_ozet_api_geriye_uyumlu(dalga_d_client):
    """`/api/ozet` ESKI anahtarlarini korur, yeni anahtarlar EKLENIR."""
    v = _json(dalga_d_client.get("/api/ozet"))
    for eski in ("repo_sayisi", "kirli_repo", "push_bekleyen", "push_bilinmeyen",
                 "bulgu_sayaclari", "toplam_bulgu", "toplam_todo", "son_tarama",
                 "veri_bayat"):
        assert eski in v, f"geriye uyumluluk bozuldu: {eski}"
    assert v["bayat_readme"] == 2
    assert v["readme_sayaclari"]["bayat"] == 1
    assert v["readme_toplam"] == 3


def test_bayat_readme_sayfasi_rozet_metinli(dalga_d_client):
    """Seviye rozeti hem renk hem METIN tasir (yalnizca renk DEGIL)."""
    govde = dalga_d_client.get("/bayat-readme").data.decode("utf-8")
    for seviye in ("bayat", "eskiyor", "taze"):
        assert f">{seviye}<" in govde, f"rozet metni yok: {seviye}"
    assert 'class="rozet bayat"' in govde
    assert 'class="rozet eskiyor"' in govde


def test_bayat_readme_bos_durum(web_client):
    """`readme_status` bosken anlamli bos durum (panel taramayi TETIKLEMEZ)."""
    r = web_client.get("/bayat-readme")
    assert r.status_code == 200
    assert "Henüz README taraması yapılmamış" in r.data.decode("utf-8")


def test_ozet_karti_bos_durumda_sifir(dolu_client):
    v = _json(dolu_client.get("/api/ozet"))
    assert v["bayat_readme"] == 0
    assert v["readme_toplam"] == 0


def test_repo_sayfasinda_readme_satiri(dalga_d_client):
    import sqlite3 as s3

    con = s3.connect(dalga_d_client.application.config["ATLAS_DB"])
    con.row_factory = s3.Row
    repo_id = con.execute("SELECT rowid FROM repos WHERE name='ornek-api'").fetchone()["rowid"]
    con.close()
    govde = dalga_d_client.get(f"/repo/{repo_id}").data.decode("utf-8")
    assert "README" in govde
    assert "bayat" in govde, "README seviyesi gorunmeli"
    assert "9" in govde, "skor gorunmeli"
    assert "45" in govde, "gorsel yasi gorunmeli"


def test_repo_sayfasinda_ozet_gosterilir(dalga_d_client):
    import sqlite3 as s3

    con = s3.connect(dalga_d_client.application.config["ATLAS_DB"])
    con.row_factory = s3.Row
    repo_id = con.execute("SELECT rowid FROM repos WHERE name='ornek-api'").fetchone()["rowid"]
    con.close()
    govde = dalga_d_client.get(f"/repo/{repo_id}").data.decode("utf-8")
    assert "Şimdi ne yapmalı" in govde
    # Jinja autoescape `'` işaretini `&#39;` yapar; bu yüzden kesirli değil
    # parçalarla ararız (özet metni doğru basılmış mı?).
    assert "commit" in govde and "le" in govde
    assert "değişiklik var" in govde
    assert "yerel kural" in govde, "kaynak yazilmali"


def test_repo_sayfasinda_ozet_maddesinde_cift_isaret_yok(dalga_d_client):
    """Ozet satiri '- ' ile baslar; liste imi zaten var, metinde ikinci '-' gorunmemeli."""
    import re
    import sqlite3 as s3

    con = s3.connect(dalga_d_client.application.config["ATLAS_DB"])
    repo_id = con.execute("SELECT rowid FROM repos WHERE name='ornek-api'").fetchone()[0]
    con.close()
    govde = dalga_d_client.get(f"/repo/{repo_id}").data.decode("utf-8")
    ogeler = re.findall(r"<li>\s*(.*?)\s*</li>", govde, re.S)
    ozet = [o for o in ogeler if "değişiklik var" in o]
    assert ozet, "ozet maddesi bulunamadi"
    assert all(not o.lstrip().startswith(("-", "•", "*")) for o in ozet)


def test_repo_sayfasinda_ozet_kaynagi_cor_model(dalga_d_client):
    import sqlite3 as s3

    con = s3.connect(dalga_d_client.application.config["ATLAS_DB"])
    con.row_factory = s3.Row
    repo_id = con.execute("SELECT rowid FROM repos WHERE name='demo-arayuz'").fetchone()["rowid"]
    con.close()
    govde = dalga_d_client.get(f"/repo/{repo_id}").data.decode("utf-8")
    assert "cor: sahte/model" in govde, "cor kaynagi + model yazilmali"


def test_repo_sayfasinda_ozet_yoksa_mesaj(dolu_client):
    """Özet yoksa: 'henüz üretilmedi' + nasıl üretileceği YAZILIR."""
    import sqlite3 as s3

    con = s3.connect(dolu_client.application.config["ATLAS_DB"])
    con.row_factory = s3.Row
    repo_id = con.execute("SELECT rowid FROM repos WHERE name='ornek-api'").fetchone()["rowid"]
    con.close()
    govde = dolu_client.get(f"/repo/{repo_id}").data.decode("utf-8")
    assert "Henüz özet üretilmedi" in govde
    assert "atlas ozet" in govde


def test_web_tarama_tetiklemez(dalga_d_client):
    """Panel salt-okunur: istekler `readme_status`/`summaries` SAYISINI DEĞİŞTİRMEZ."""
    import sqlite3 as s3

    yol = dalga_d_client.application.config["ATLAS_DB"]
    con = s3.connect(yol)
    once = con.execute("SELECT COUNT(*) FROM readme_status").fetchone()[0]
    once_s = con.execute("SELECT COUNT(*) FROM summaries").fetchone()[0]
    con.close()
    for yol_url in ("/", "/bayat-readme", "/api/bayat-readme", "/api/ozet"):
        dalga_d_client.get(yol_url)
    con = s3.connect(yol)
    try:
        assert con.execute("SELECT COUNT(*) FROM readme_status").fetchone()[0] == once
        assert con.execute("SELECT COUNT(*) FROM summaries").fetchone()[0] == once_s
    finally:
        con.close()
