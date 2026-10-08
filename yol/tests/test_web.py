"""Web paneli: Host/CSP/Origin/CSRF, maskeleme, uygula + yedek, cakisma 409, geri-al, dizin-var."""

from __future__ import annotations

import json
import re

import pytest

from yol.kaynak import DosyaKaynak, KaynakHatasi, SurecKaynak
from yol.web import uygulama_olustur
from yol.yedek import YedekHatasi, yedekler

GIZLI = "gizli-deger-7f3a9c-ASLA-GORUNMEMELI"
YENI_GIZLI = "yeni-gizli-deger-42"
HOST_URL = "http://127.0.0.1:8797"
ORIGIN = "http://127.0.0.1:8797"
CSRF_RE = re.compile(r'name="yol-csrf" content="([^"]+)"')


@pytest.fixture(autouse=True)
def _veri_dizini(yol_dir):
    """Yedek ve gunluk yalnizca tmp dizinine yazilsin."""
    return yol_dir


@pytest.fixture
def bin_dizini(tmp_path):
    kok = tmp_path / "bin"
    kok.mkdir()
    return kok


@pytest.fixture
def web_kaynak(tmp_path, bin_dizini) -> DosyaKaynak:
    sistem_dizini = tmp_path / "sistem"
    sistem_dizini.mkdir()
    yol = tmp_path / "ortam.json"
    veri = {
        "ayirici": ";",
        "windows": True,
        "sistem": {
            "Path": {"metin": f"{sistem_dizini};%SystemRoot%", "genisler": True},
            "SystemRoot": {"metin": "C:\\Windows", "genisler": False},
        },
        "kullanici": {
            "Path": {
                "metin": f"{bin_dizini};C:\\Yok\\dizin;{bin_dizini}",
                "genisler": True,
            },
            "API_TOKEN": {"metin": GIZLI, "genisler": False},
            "EDITOR": {"metin": "code", "genisler": False},
        },
    }
    yol.write_text(json.dumps(veri, ensure_ascii=False), encoding="utf-8")
    return DosyaKaynak(yol)


@pytest.fixture
def uygulama(web_kaynak):
    app = uygulama_olustur(web_kaynak, dizin_var=lambda yol: "Yok" not in yol,
                          dosya_var=lambda yol: False)
    app.config["TESTING"] = True
    return app


@pytest.fixture
def istemci(uygulama):
    return uygulama.test_client()


@pytest.fixture
def csrf(istemci) -> str:
    cevap = istemci.get("/", base_url=HOST_URL)
    eslesme = CSRF_RE.search(cevap.get_data(as_text=True))
    assert eslesme, "GET / sayfasinda CSRF meta etiketi yok"
    return eslesme.group(1)


def _post(istemci, yol, veri=None, *, csrf_jetonu=None, origin=ORIGIN, host=HOST_URL):
    basliklar = {}
    if origin is not None:
        basliklar["Origin"] = origin
    if csrf_jetonu is not None:
        basliklar["X-CSRF"] = csrf_jetonu
    return istemci.post(yol, json=veri, headers=basliklar, base_url=host)


def _post_yetkili(istemci, csrf, yol, veri=None):
    return _post(istemci, yol, veri, csrf_jetonu=csrf)


def _kullanici_path(kaynak: DosyaKaynak) -> dict:
    return kaynak.oku("kullanici")["Path"].sozluk()


def _kullanici_path_eski_yeni(kaynak: DosyaKaynak, yeni_metin: str) -> dict:
    eski = kaynak.oku("kullanici")["Path"]
    return {
        "kapsam": "kullanici",
        "ad": "Path",
        "eski": eski.sozluk(),
        "yeni": {"metin": yeni_metin, "genisler": eski.genisler},
    }


# ----------------------------------------------------------- Host, CSP, sayfa

@pytest.mark.parametrize("host", ["http://evil.example", "http://127.0.0.1.nip.io:8797", "http://10.0.0.5:8797"])
def test_host_yabanci_ise_403(istemci, host):
    assert istemci.get("/api/durum", base_url=host).status_code == 403
    assert istemci.get("/", base_url=host).status_code == 403


@pytest.mark.parametrize("host", ["http://127.0.0.1:8797", "http://localhost:8797", "http://localhost"])
def test_host_loopback_kabul(istemci, host):
    assert istemci.get("/api/durum", base_url=host).status_code == 200


def test_csp_basliklari(istemci):
    cevap = istemci.get("/", base_url=HOST_URL)
    csp = cevap.headers["Content-Security-Policy"]
    assert "default-src 'none'" in csp
    assert "script-src 'self'" in csp
    assert "style-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert cevap.headers["X-Content-Type-Options"] == "nosniff"


@pytest.mark.parametrize("deger, beklenen", [
    ("http://127.0.0.1:5173", "frame-ancestors http://127.0.0.1:5173"),
    ("http://localhost:8080", "frame-ancestors http://localhost:8080"),
    ("https://evil.example", "frame-ancestors 'none'"),
    ("http://127.0.0.1:5173/yol", "frame-ancestors 'none'"),
    ("http://*", "frame-ancestors 'none'"),
    ("http://127.0.0.1:abc", "frame-ancestors 'none'"),
])
def test_kule_frame_origin_dogrulama(istemci, monkeypatch, deger, beklenen):
    monkeypatch.setenv("KULE_FRAME_ORIGIN", deger)
    csp = istemci.get("/", base_url=HOST_URL).headers["Content-Security-Policy"]
    assert beklenen in csp
    if beklenen == "frame-ancestors 'none'":
        assert deger not in csp


def test_sayfa_csrf_meta_ve_satir_ici_kod_yok(istemci):
    html = istemci.get("/", base_url=HOST_URL).get_data(as_text=True)
    eslesme = CSRF_RE.search(html)
    assert eslesme and len(eslesme.group(1)) >= 40
    # Satir ici script (src'siz) ve satir ici stil yok.
    assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html)
    assert "<style" not in html
    assert ' style="' not in html
    assert " onclick=" not in html
    assert "innerHTML" not in html
    assert 'role="tablist"' in html
    assert "PATH" in html and "Komutlar" in html and "Değişkenler" in html and "Yedekler" in html


# ----------------------------------------------------------- POST: Origin ve CSRF

def test_post_csrf_yok_403(istemci):
    cevap = _post(istemci, "/api/onizle", {"degisiklikler": []})
    assert cevap.status_code == 403


def test_post_yanlis_csrf_403(istemci, csrf):
    cevap = _post(istemci, "/api/onizle", {"degisiklikler": []}, csrf_jetonu="yanlis")
    assert cevap.status_code == 403


def test_post_yanlis_origin_403(istemci, csrf):
    cevap = _post(istemci, "/api/onizle", {"degisiklikler": []}, csrf_jetonu=csrf,
                  origin="http://evil.example")
    assert cevap.status_code == 403


def test_post_origin_yok_403(istemci, csrf):
    cevap = _post(istemci, "/api/onizle", {"degisiklikler": []}, csrf_jetonu=csrf, origin=None)
    assert cevap.status_code == 403


def test_post_kule_origin_kabul(istemci, csrf, monkeypatch):
    monkeypatch.setenv("KULE_FRAME_ORIGIN", "http://127.0.0.1:5173")
    yanit = _post(istemci, "/api/onizle", {"degisiklikler": []}, csrf_jetonu=csrf,
                  origin="http://127.0.0.1:5173")
    # Origin gecer; eksik govde 400 doner (403 degil).
    assert yanit.status_code == 400


def test_post_dogru_jeton_ve_origin_gecer(istemci, csrf, bin_dizini):
    yanit = _post_yetkili(istemci, csrf, "/api/dizin-var", {"yol": str(bin_dizini)})
    assert yanit.status_code == 200
    assert yanit.get_json() is True


def test_uygula_yalniz_post(istemci):
    assert istemci.get("/api/uygula", base_url=HOST_URL).status_code == 405


# ----------------------------------------------------------- durum sekli

def test_durum_sekli(istemci):
    veri = istemci.get("/api/durum", base_url=HOST_URL).get_json()
    assert set(veri) >= {"platform", "path", "komutlar", "ozet", "yedek"}
    assert veri["platform"]["kaynak"] == "dosya"
    assert veri["platform"]["windows"] is True
    kapsamlar = {k["ad"]: k["yazilabilir"] for k in veri["platform"]["kapsamlar"]}
    assert kapsamlar == {"sistem": True, "kullanici": True}
    assert veri["path"]["kayitlar"]["kullanici"]["ad"] == "Path"
    bulgular = [b for g in veri["path"]["girdiler"] for b in g["bulgular"]]
    assert "yok" in bulgular and "tekrar" in bulgular
    assert set(veri["ozet"]) >= {"girdi", "sorunlu", "golgelenen", "uzun"}
    assert "oneri" in veri["path"] and "kullanici" in veri["path"]["oneri"]
    assert veri["yedek"] == {"son": None, "sayi": 0}


def test_durum_komut_listesi(istemci):
    veri = istemci.get("/api/durum", base_url=HOST_URL).get_json()
    adlar = [k["ad"] for k in veri["komutlar"]]
    assert "python" in adlar and "git" in adlar
    assert all(k["kazanan"] is None for k in veri["komutlar"])


# ----------------------------------------------------------- maskeleme

def test_gizli_deger_get_yanitlarinda_gorunmez(istemci, web_kaynak):
    for yol in ["/", "/api/durum", "/api/degiskenler", "/api/degiskenler?kapsam=kullanici",
                "/api/yedekler", "/api/degiskenler?goster=1"]:
        cevap = istemci.get(yol, base_url=HOST_URL)
        assert GIZLI not in cevap.get_data(as_text=True), yol


def test_degiskenler_maskeli_satir(istemci):
    liste = istemci.get("/api/degiskenler", base_url=HOST_URL).get_json()["degiskenler"]
    gizli = next(d for d in liste if d["ad"] == "API_TOKEN" and d["kapsam"] == "kullanici")
    assert gizli["gizli"] is True
    assert gizli["deger"] == "•" * 8
    assert gizli["uzunluk"] is None
    acik = next(d for d in liste if d["ad"] == "EDITOR")
    assert acik["gizli"] is False and acik["deger"] == "code"


def test_goster_yalniz_tek_ad_icin(istemci):
    cevap = istemci.get("/api/degiskenler?goster=1", base_url=HOST_URL)
    assert cevap.status_code == 400
    assert GIZLI not in cevap.get_data(as_text=True)

    cevap = istemci.get("/api/degiskenler?goster=1&ad=API_TOKEN&kapsam=kullanici", base_url=HOST_URL)
    assert cevap.status_code == 200
    kayitlar = cevap.get_json()["degiskenler"]
    assert len(kayitlar) == 1 and kayitlar[0]["deger"] == GIZLI

    assert istemci.get("/api/degiskenler?goster=1&ad=YOK", base_url=HOST_URL).status_code == 404


def test_onizle_gizli_degeri_maskeler(istemci, csrf):
    yanit = _post_yetkili(istemci, csrf, "/api/onizle", {"degisiklikler": [
        {"kapsam": "kullanici", "ad": "API_TOKEN",
         "eski": {"metin": GIZLI, "genisler": False},
         "yeni": {"metin": YENI_GIZLI, "genisler": False}},
    ]})
    assert yanit.status_code == 200
    govde = yanit.get_data(as_text=True)
    assert GIZLI not in govde and YENI_GIZLI not in govde
    satir = yanit.get_json()["fark"][0]
    assert satir["gizli"] is True and satir["eylem"] == "degistir"


def test_yedek_fark_gizli_degeri_maskeler(istemci, csrf, web_kaynak):
    eski = web_kaynak.oku("kullanici")["API_TOKEN"]
    _post_yetkili(istemci, csrf, "/api/uygula", {"degisiklikler": [
        {"kapsam": "kullanici", "ad": "API_TOKEN", "eski": eski.sozluk(),
         "yeni": {"metin": YENI_GIZLI, "genisler": False}},
    ]})
    yedek = yedekler()[0]["id"]
    cevap = istemci.get(f"/api/yedek/{yedek}/fark", base_url=HOST_URL)
    assert cevap.status_code == 200
    govde = cevap.get_data(as_text=True)
    assert GIZLI not in govde and YENI_GIZLI not in govde
    assert cevap.get_json()["fark"][0]["gizli"] is True


# ----------------------------------------------------------- uygula, cakisma, yedek

def test_uygula_yazar_ve_yedek_alir(istemci, csrf, web_kaynak, yol_dir):
    eski_path = web_kaynak.oku("kullanici")["Path"].metin
    yeni_metin = eski_path.split(";")[0]  # tekrar ve yok girdilerini kaldir
    degisiklik = _kullanici_path_eski_yeni(web_kaynak, yeni_metin)

    yanit = _post_yetkili(istemci, csrf, "/api/uygula", {"degisiklikler": [degisiklik]})
    assert yanit.status_code == 200, yanit.get_data(as_text=True)
    veri = yanit.get_json()
    assert veri["uygulanan"] == 1 and veri["yedek"]

    yeni = web_kaynak.oku("kullanici")["Path"]
    assert yeni.metin == yeni_metin
    assert yeni.genisler is True  # REG_EXPAND_SZ tipi korunur

    kimlikler = [y["id"] for y in yedekler()]
    assert veri["yedek"] in kimlikler

    gunluk = yol_dir / "gunluk.jsonl"
    assert gunluk.exists()
    assert eski_path not in gunluk.read_text(encoding="utf-8")


def test_uygula_eski_uyusmazsa_409_ve_yazmaz(istemci, csrf, web_kaynak):
    onceki = web_kaynak.oku("kullanici")["Path"].metin
    degisiklik = _kullanici_path_eski_yeni(web_kaynak, "C:\\Baska")
    degisiklik["eski"] = {"metin": "bayat-deger", "genisler": True}

    yanit = _post_yetkili(istemci, csrf, "/api/uygula", {"degisiklikler": [degisiklik]})
    assert yanit.status_code == 409
    assert "Path" in yanit.get_json()["hata"]
    assert web_kaynak.oku("kullanici")["Path"].metin == onceki
    assert yedekler() == []  # yazma yok, yedek de alinmadi


def test_uygula_gecersiz_govde_400(istemci, csrf):
    assert _post_yetkili(istemci, csrf, "/api/uygula", {"degisiklikler": []}).status_code == 400
    assert _post_yetkili(istemci, csrf, "/api/uygula", {}).status_code == 400
    kotu = {"kapsam": "kullanici", "ad": "A=B", "eski": None, "yeni": {"metin": "x", "genisler": False}}
    assert _post_yetkili(istemci, csrf, "/api/uygula", {"degisiklikler": [kotu]}).status_code == 400


def test_yazilamayan_kapsam_403():
    app = uygulama_olustur(SurecKaynak())
    app.config["TESTING"] = True
    istemci = app.test_client()
    csrf = CSRF_RE.search(istemci.get("/", base_url=HOST_URL).get_data(as_text=True)).group(1)
    degisiklik = {"kapsam": "surec", "ad": "X", "eski": None, "yeni": {"metin": "1", "genisler": False}}
    yanit = _post_yetkili(istemci, csrf, "/api/uygula", {"degisiklikler": [degisiklik]})
    assert yanit.status_code == 403
    assert yedekler() == []


def test_geri_al_roundtrip(istemci, csrf, web_kaynak):
    orijinal = web_kaynak.oku("kullanici")["Path"]
    eski_path = orijinal.sozluk()
    degisiklik = _kullanici_path_eski_yeni(web_kaynak, "C:\\Yeni\\yol")
    veri = _post_yetkili(istemci, csrf, "/api/uygula", {"degisiklikler": [degisiklik]}).get_json()
    yedek_id = veri["yedek"]
    assert web_kaynak.oku("kullanici")["Path"].metin == "C:\\Yeni\\yol"

    fark = istemci.get(f"/api/yedek/{yedek_id}/fark", base_url=HOST_URL).get_json()["fark"]
    path_satiri = next(s for s in fark if s["ad"] == "Path")
    assert path_satiri["path"] is True and path_satiri["cikan"] == ["C:\\Yeni\\yol"]

    geri = _post_yetkili(istemci, csrf, f"/api/geri-al/{yedek_id}")
    assert geri.status_code == 200
    assert geri.get_json()["uygulanan"] >= 1
    assert web_kaynak.oku("kullanici")["Path"].sozluk() == eski_path


def test_geri_al_gecersiz_kimlik_404(istemci, csrf):
    assert _post_yetkili(istemci, csrf, "/api/geri-al/bozuk-kimlik").status_code == 404
    assert istemci.get("/api/yedek/bozuk-kimlik/fark", base_url=HOST_URL).status_code == 404


def test_yedekler_listesi(istemci, csrf, web_kaynak):
    assert istemci.get("/api/yedekler", base_url=HOST_URL).get_json() == {"yedekler": []}
    _post_yetkili(istemci, csrf, "/api/uygula", {"degisiklikler": [
        _kullanici_path_eski_yeni(web_kaynak, "C:\\Bir")]})
    liste = istemci.get("/api/yedekler", base_url=HOST_URL).get_json()["yedekler"]
    assert len(liste) == 1 and liste[0]["kapsamlar"]["kullanici"] >= 1


# ----------------------------------------------------------- dizin-var

def test_dizin_var_yalnizca_bool(tmp_path, web_kaynak):
    app = uygulama_olustur(web_kaynak)
    app.config["TESTING"] = True
    istemci = app.test_client()
    csrf = CSRF_RE.search(istemci.get("/", base_url=HOST_URL).get_data(as_text=True)).group(1)

    var_dizin = tmp_path / "gercek-dizin-adi"
    var_dizin.mkdir()
    yanit = _post_yetkili(istemci, csrf, "/api/dizin-var", {"yol": str(var_dizin)})
    assert yanit.status_code == 200
    assert yanit.get_data(as_text=True).strip() == "true"
    assert str(var_dizin) not in yanit.get_data(as_text=True)

    yok = _post_yetkili(istemci, csrf, "/api/dizin-var", {"yol": str(tmp_path / "yok")})
    assert yok.get_data(as_text=True).strip() == "false"

    dosya = tmp_path / "dosya.txt"
    dosya.write_text("x", encoding="utf-8")
    assert _post_yetkili(istemci, csrf, "/api/dizin-var", {"yol": str(dosya)}).get_data(as_text=True).strip() == "false"

    assert _post_yetkili(istemci, csrf, "/api/dizin-var", {"yol": ""}).get_data(as_text=True).strip() == "false"
    assert _post_yetkili(istemci, csrf, "/api/dizin-var", {}).status_code == 400


# ----------------------------------------------------- regresyonlar (degerlendirme bulgulari)

class _YayinsizDosya(DosyaKaynak):
    def yayinla(self):
        raise KaynakHatasi("sahte yayin hatasi")


def test_genisler_metin_olamaz_400(istemci, csrf, web_kaynak):
    # Regresyon: "false" metni genisler=True sayiliyordu.
    eski = web_kaynak.oku("kullanici")["Path"].sozluk()
    kayit = {"kapsam": "kullanici", "ad": "Path", "eski": eski,
             "yeni": {"metin": "C:\\X", "genisler": "true"}}
    assert _post_yetkili(istemci, csrf, "/api/onizle", {"degisiklikler": [kayit]}).status_code == 400
    assert _post_yetkili(istemci, csrf, "/api/uygula", {"degisiklikler": [kayit]}).status_code == 400


def test_onizle_buyuk_kucuk_harf_yeni_ad_409(istemci, csrf, web_kaynak):
    # Regresyon: "PATH" yeni ad, Windows'ta mevcut "Path" ile ayni degisken.
    kayit = {"kapsam": "kullanici", "ad": "PATH", "eski": None,
             "yeni": {"metin": "C:\\X", "genisler": False}}
    yanit = _post_yetkili(istemci, csrf, "/api/onizle", {"degisiklikler": [kayit]})
    assert yanit.status_code == 409
    assert "PATH" not in web_kaynak.oku("kullanici")


def test_onizle_url_kimligi_maskelenir(istemci, csrf):
    kayit = {"kapsam": "kullanici", "ad": "CACHE_DIR", "eski": None,
             "yeni": {"metin": "https://umut:cok-gizli-parola@sunucu/x", "genisler": False}}
    yanit = _post_yetkili(istemci, csrf, "/api/onizle", {"degisiklikler": [kayit]})
    assert yanit.status_code == 200
    assert "cok-gizli-parola" not in yanit.get_data(as_text=True)
    assert yanit.get_json()["fark"][0]["gizli"] is True


def test_uygula_yayin_hatasi_yayinlandi_false(tmp_path, yol_dir):
    yol = tmp_path / "ortam.json"
    veri = {"ayirici": ";", "windows": True, "sistem": {},
            "kullanici": {"EDITOR": {"metin": "code", "genisler": False}}}
    yol.write_text(json.dumps(veri, ensure_ascii=False), encoding="utf-8")
    app = uygulama_olustur(_YayinsizDosya(yol), dizin_var=lambda p: True, dosya_var=lambda p: False)
    app.config["TESTING"] = True
    istemci = app.test_client()
    csrf_metin = istemci.get("/", base_url=HOST_URL).get_data(as_text=True)
    csrf_jetonu = CSRF_RE.search(csrf_metin).group(1)
    kayit = {"kapsam": "kullanici", "ad": "EDITOR", "eski": {"metin": "code", "genisler": False},
             "yeni": {"metin": "vim", "genisler": False}}
    with pytest.warns(UserWarning):
        yanit = _post_yetkili(istemci, csrf_jetonu, "/api/uygula", {"degisiklikler": [kayit]})
    assert yanit.status_code == 200
    veri_yanit = yanit.get_json()
    assert veri_yanit["yayinlandi"] is False
    assert veri_yanit["uygulanan"] == 1


def test_uygula_gunluk_hatasi_basarili_yanit_verir(istemci, csrf, web_kaynak, monkeypatch):
    # Regresyon: yazmadan sonraki gunluk hatasi 500 "hicbir sey yazilmadi" donuyordu.
    from yol import degisiklik as _dg

    def bozuk_gunluk(_kayit):
        raise YedekHatasi("sahte gunluk hatasi")

    monkeypatch.setattr(_dg, "gunluk_ekle", bozuk_gunluk)
    yeni_metin = web_kaynak.oku("kullanici")["Path"].metin.split(";")[0]
    kayit = _kullanici_path_eski_yeni(web_kaynak, yeni_metin)
    with pytest.warns(UserWarning):
        yanit = _post_yetkili(istemci, csrf, "/api/uygula", {"degisiklikler": [kayit]})
    assert yanit.status_code == 200
    assert yanit.get_json()["yayinlandi"] is True
    assert web_kaynak.oku("kullanici")["Path"].metin == yeni_metin


def test_istek_govdesi_ust_siniri(istemci, csrf, uygulama):
    assert uygulama.config["MAX_CONTENT_LENGTH"] == 1_000_000
    govde = b"{" + b" " * 1_100_000 + b"}"
    yanit = istemci.post("/api/onizle", data=govde, content_type="application/json",
                         headers={"Origin": ORIGIN, "X-CSRF": csrf}, base_url=HOST_URL)
    assert yanit.status_code == 413


def test_panel_js_notr_rozet_ve_yayin_notu():
    # Istemci kodu tarayicida calistirilmadigi icin metin denetimi: notr rozetler, yayin notu,
    # buyuk/kucuk harfe duyarsiz ad denetimi.
    from pathlib import Path
    js = (Path(__file__).resolve().parent.parent / "yol" / "web" / "static" / "panel.js").read_text(encoding="utf-8")
    assert "cozumlenemedi" in js and "kontrol-edilemedi" in js
    assert "yayinlandi" in js and "açık programlara duyurulamadı" in js
    assert "d.ad === ad" not in js
