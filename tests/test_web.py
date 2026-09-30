"""`orkestra.web` testleri (Dalga C): rota sözleşmesi + BAĞLAYICI güvenlik.

Kapsam: tüm rotaların 200/404/405'i, JSON şekilleri, boş DB, güvenlik
başlıkları, Host doğrulama (reddedilen istek DB açmaz), `mode=ro`, XSS,
log yolu kaçışı ve maskeleme.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from orkestra.queue import SEMA
from orkestra.web import sunucu
from orkestra.web.sunucu import app_olustur

# XSS yükleri: istem/ajan/hata/log içeriği güvenilmeyendir.
YUK_ONERROR = '<img src=x onerror="window.__xss=1">'
YUK_SCRIPT = "<script>window.__xss=1</script>"
YUK_SVG = '<svg/onload=window.__xss=1>'

# Sahte sır: kaynakta tam literal YOK, çalışma zamanında parçalardan kurulur
# (böylece sırrı kendisi bile sızdırmaz testler).
SAHTE_SIR_PARCA = "sk-" + "test" + "0123456789abcdefXYZ"
SAHTE_SIR = SAHTE_SIR_PARCA


@pytest.fixture()
def db(tmp_path):
    """Bereketli (yazılabilir) test DB'si — panel bunu mode=ro ile açacak."""
    yol = tmp_path / "panel.db"
    b = sqlite3.connect(yol)
    b.row_factory = sqlite3.Row
    b.executescript(SEMA)
    b.commit()
    b.close()
    return yol


@pytest.fixture()
def cikti_dizini(tmp_path):
    d = tmp_path / "runs"
    d.mkdir()
    return d


@pytest.fixture()
def uygulama(db, cikti_dizini):
    return app_olustur(db, cikti_dizini=cikti_dizini)


@pytest.fixture()
def istemci(uygulama):
    return uygulama.test_client()


def ekle(db, ajan="bunny-coder", istem="gorev", durum="bekliyor", **kosu):
    b = sqlite3.connect(db)
    b.row_factory = sqlite3.Row
    b.execute(
        "INSERT INTO tasks (ajan, istem, durum, olusturma) VALUES (?,?,?,?)",
        (ajan, istem, durum, "2026-09-30T06:00:00Z"),
    )
    gorev_id = b.execute("SELECT last_insert_rowid()").fetchone()[0]
    for anahtar, deger in kosu.items():
        if anahtar == "log":
            b.execute(
                "INSERT INTO runs (task_id, baslangic, bitis, cikis_kodu, cikti_yolu, hata) "
                "VALUES (?,?,?,?,?,?)",
                (
                    gorev_id,
                    "2026-09-30T06:00:01Z",
                    "2026-09-30T06:00:09Z",
                    deger.get("cikis_kodu", 0),
                    deger.get("yol"),
                    deger.get("hata"),
                ),
            )
    b.commit()
    b.close()
    return gorev_id


# -- rota sozlesmesi ---------------------------------------------------------

ROTALAR = ["/", "/kota", "/saglik", "/api/gorevler", "/api/kota"]


@pytest.mark.parametrize("rota", ROTALAR)
def test_rotalar_200(istemci, rota):
    cevap = istemci.get(rota)
    assert cevap.status_code == 200


def test_gorev_detay_200(istemci, db):
    gorev_id = ekle(db)
    assert istemci.get(f"/gorev/{gorev_id}").status_code == 200


def test_api_gorev_200(istemci, db):
    gorev_id = ekle(db)
    assert istemci.get(f"/api/gorev/{gorev_id}").status_code == 200


def test_gorev_detay_404(istemci):
    assert istemci.get("/gorev/9999").status_code == 404


def test_api_gorev_404(istemci):
    assert istemci.get("/api/gorev/9999").status_code == 404


def test_bilinmeyen_rota_404(istemci):
    assert istemci.get("/boyle-bir-sayfa-yok").status_code == 404


# yazma yuzeyi yok: panel yalnizca GET
@pytest.mark.parametrize("rota", ROTALAR)
@pytest.mark.parametrize("metot", ["post", "put", "delete", "patch"])
def test_yalnizca_get_405(istemci, rota, metot):
    cevap = getattr(istemci, metot)(rota)
    assert cevap.status_code == 405


@pytest.mark.parametrize("metot", ["post", "delete"])
def test_gorev_detay_yalnizca_get_405(istemci, db, metot):
    gorev_id = ekle(db)
    assert getattr(istemci, metot)(f"/gorev/{gorev_id}").status_code == 405


# -- guvenlik basliklari -----------------------------------------------------

BEKLENEN_CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; "
    "img-src 'self' data:; connect-src 'self'; base-uri 'none'; "
    "form-action 'none'; frame-ancestors 'none'"
)


@pytest.mark.parametrize("rota", ROTALAR + ["/saglik"])
def test_csp_basligi(istemci, rota):
    cevap = istemci.get(rota)
    assert cevap.headers["Content-Security-Policy"] == BEKLENEN_CSP


@pytest.mark.parametrize("rota", ROTALAR + ["/saglik"])
def test_diger_guvenlik_basliklari(istemci, rota):
    b = istemci.get(rota).headers
    assert b["X-Content-Type-Options"] == "nosniff"
    assert b["Referrer-Policy"] == "no-referrer"
    assert b["Cache-Control"] == "no-store"


def test_guvenlik_basliklari_404_ve_405_ve_halde(istemci):
    assert "Content-Security-Policy" in istemci.get("/yok").headers
    assert "Content-Security-Policy" in istemci.post("/").headers
    assert "Content-Security-Policy" in istemci.get(
        "/", headers={"Host": "kotu.example"}
    ).headers


def test_satir_ici_script_yok(istemci, db):
    gorev_id = ekle(db, istem=YUK_SCRIPT)
    govde = istemci.get(f"/gorev/{gorev_id}").get_data(as_text=True)
    # Sablon satır içi script/stil içermez; kullanıcı verisi ESCAPED.
    assert "<script>" not in govde
    assert "onerror=" not in govde


def test_satir_ici_style_yok(istemci):
    govde = istemci.get("/").get_data(as_text=True)
    assert "style=" not in govde


# -- Host dogrulama ---------------------------------------------------------


@pytest.mark.parametrize(
    "host", ["127.0.0.1", "127.0.0.1:8780", "localhost", "localhost:8780", "LOCALHOST:8780"]
)
def test_gecerli_host_kabul(istemci, host):
    assert istemci.get("/", headers={"Host": host}).status_code == 200


@pytest.mark.parametrize(
    "host",
    [
        "example.com",
        "evil.example.com",
        "127.0.0.1.evil.com",
        "localhost.evil.com",
        "0.0.0.0",
        "192.168.1.5:8780",
        "127.0.0.1@evil.com",
        "[::1]:8780",
        "",
    ],
)
def test_gecersiz_host_403(istemci, host):
    cevap = istemci.get("/", headers={"Host": host})
    assert cevap.status_code == 403


def test_host_reddi_403_metni_guvenli(istemci):
    cevap = istemci.get("/", headers={"Host": "evil.com"})
    assert "Host" in cevap.get_data(as_text=True)


def test_host_reddedilen_istek_db_acmaz(db, cikti_dizini, monkeypatch):
    """Reddedilen istek hiçbir sorgu YAPMAMALI (baglanti sayaci 0)."""
    acilan = []
    gercek = sunucu.db_ac

    def sayac(yol):
        acilan.append(yol)
        return gercek(yol)

    monkeypatch.setattr(sunucu, "db_ac", sayac)
    uygulama = app_olustur(db, cikti_dizini=cikti_dizini)
    istemci = uygulama.test_client()
    cevap = istemci.get("/", headers={"Host": "evil.com"})
    assert cevap.status_code == 403
    assert acilan == []


def test_gecerli_host_db_acar(db, cikti_dizini, monkeypatch):
    acilan = []
    gercek = sunucu.db_ac
    monkeypatch.setattr(
        sunucu, "db_ac", lambda yol: (acilan.append(yol), gercek(yol))[1]
    )
    istemci = app_olustur(db, cikti_dizini=cikti_dizini).test_client()
    assert istemci.get("/", headers={"Host": "127.0.0.1:8780"}).status_code == 200
    assert len(acilan) == 1


# -- salt okunur ------------------------------------------------------------


def test_db_mode_ro(db, cikti_dizini):
    uygulama = app_olustur(db, cikti_dizini=cikti_dizini)
    istemci = uygulama.test_client()
    istemci.get("/api/gorevler")
    with uygulama.app_context():
        baglanti = sunucu.db_ac(db)
        try:
            baglanti.execute("INSERT INTO tasks (ajan, istem, durum, olusturma) VALUES ('a','b','bekliyor','x')")
        except sqlite3.OperationalError:
            return
        pytest.fail("salt-okunur DB yazmaya izin verdi")


def test_sunucu_yazma_yapmaz(istemci, db):
    """Sayfalari gezmek DB'yi degistirmemeli."""
    ekle(db)
    with open(db, "rb") as f:
        once = f.read()
    for rota in ROTALAR:
        istemci.get(rota)
    with open(db, "rb") as f:
        assert f.read() == once


# -- XSS --------------------------------------------------------------------

#: Yük autoescape SONRASI HTML'de güvenli görünmelidir: tırnak `&#34;`,
#: `<` `&lt;`, `>` `&gt;` olur. Ham yükün kendisi geçmemelidir.
def xss_etkisiz_mi(ham_yuk: str, govde: str) -> None:
    """Yük kaçışsız basılmamalı; kaçırılmış hâli güvenlidir."""
    assert ham_yuk not in govde, "yük kaçışsız basıldı"
    # Etiket açılışı hiçbir yerde gerçek olmamalı.
    assert "<script>" not in govde
    assert "onerror=\"" not in govde.replace("&#34;", "")
    assert "<svg/onload" not in govde


@pytest.mark.parametrize("yuk", [YUK_ONERROR, YUK_SCRIPT, YUK_SVG])
def test_xss_istem_kuyrukta_calismaz(istemci, db, yuk):
    ekle(db, istem=yuk)
    govde = istemci.get("/").get_data(as_text=True)
    xss_etkisiz_mi(yuk, govde)


@pytest.mark.parametrize("yuk", [YUK_ONERROR, YUK_SCRIPT, YUK_SVG])
def test_xss_istem_detayda_calismaz(istemci, db, yuk):
    gorev_id = ekle(db, istem=yuk)
    govde = istemci.get(f"/gorev/{gorev_id}").get_data(as_text=True)
    xss_etkisiz_mi(yuk, govde)


def test_xss_ajan_kuyrukta_calismaz(istemci, db):
    yuk = YUK_ONERROR
    ekle(db, ajan=yuk)
    govde = istemci.get("/").get_data(as_text=True)
    xss_etkisiz_mi(yuk, govde)


def test_xss_ajan_detayda_calismaz(istemci, db):
    yuk = YUK_SCRIPT
    gorev_id = ekle(db, ajan=yuk)
    govde = istemci.get(f"/gorev/{gorev_id}").get_data(as_text=True)
    xss_etkisiz_mi(yuk, govde)


def test_xss_hata_detayda_calismaz(istemci, db):
    yuk = YUK_ONERROR
    gorev_id = ekle(db, hata=yuk)
    govde = istemci.get(f"/gorev/{gorev_id}").get_data(as_text=True)
    xss_etkisiz_mi(yuk, govde)


def test_xss_log_icerigi_calismaz(istemci, db, cikti_dizini):
    log = cikti_dizini / "k.log"
    log.write_text(f"satir1\n{YUK_ONERROR}\n", encoding="utf-8")
    gorev_id = ekle(db, log={"yol": str(log)})
    govde = istemci.get(f"/gorev/{gorev_id}").get_data(as_text=True)
    xss_etkisiz_mi(YUK_ONERROR, govde)


def test_xss_api_json_guvenli(istemci, db):
    gorev_id = ekle(db, istem=YUK_SCRIPT, ajan=YUK_ONERROR)
    veri = istemci.get(f"/api/gorev/{gorev_id}").get_json()
    assert "<script>" in veri["istem"]  # JSON'da metin olarak kalir
    # HTML'e gomuldugunu varsay: panel bunu textContent ile basar.

# -- maskeleme --------------------------------------------------------------


def test_sir_istemde_maskeli(istemci, db):
    # `ver` komutu gizli kalibi reddeder; DB'ye ELLE yazilmis sira test edilir.
    gorev_id = ekle(db, istem=f"anahtar {SAHTE_SIR} gecerli")
    govde = istemci.get(f"/gorev/{gorev_id}").get_data(as_text=True)
    assert SAHTE_SIR not in govde
    assert "[maskeli]" in govde


def test_sir_logda_maskeli(istemci, db, cikti_dizini):
    log = cikti_dizini / "s.log"
    log.write_text(f"token {SAHTE_SIR}\n", encoding="utf-8")
    gorev_id = ekle(db, log={"yol": str(log)})
    govde = istemci.get(f"/gorev/{gorev_id}").get_data(as_text=True)
    assert SAHTE_SIR not in govde
    assert "[maskeli]" in govde


def test_sir_hatada_maskeli(istemci, db):
    gorev_id = ekle(db, hata=f"hata: {SAHTE_SIR}")
    govde = istemci.get(f"/gorev/{gorev_id}").get_data(as_text=True)
    assert SAHTE_SIR not in govde


def test_sir_json_api_maskeli(istemci, db):
    gorev_id = ekle(db, istem=f"x {SAHTE_SIR} y")
    veri = istemci.get(f"/api/gorev/{gorev_id}").get_json()
    assert SAHTE_SIR not in json.dumps(veri, ensure_ascii=False)
    assert SAHTE_SIR not in istemci.get("/api/gorevler").get_data(as_text=True)


def test_sir_kota_log_yolunda_maskeli(istemci, db, cikti_dizini):
    log = cikti_dizini / "y.log"
    log.write_text("x\n", encoding="utf-8")
    gorev_id = ekle(db, log={"yol": str(log)})
    veri = istemci.get(f"/api/gorev/{gorev_id}").get_json()
    assert SAHTE_SIR not in json.dumps(veri, ensure_ascii=False)


def test_sahte_sir_kaynakta_tam_literal_yok():
    """Guvenlik testi: sır kaynak dosyada tam yazılmaz."""
    import pathlib

    kaynak = pathlib.Path(sunucu.__file__).read_text(encoding="utf-8")
    assert SAHTE_SIR not in kaynak


# -- log yolu kacisi --------------------------------------------------------


def test_log_dizin_ici_okunur(istemci, db, cikti_dizini):
    log = cikti_dizini / "i.log"
    log.write_text("gizli satirlar burada\n", encoding="utf-8")
    gorev_id = ekle(db, log={"yol": str(log)})
    govde = istemci.get(f"/gorev/{gorev_id}").get_data(as_text=True)
    assert "gizli satirlar burada" in govde


def test_log_nokta_nokta_kacisi_reddedilir(istemci, db, cikti_dizini):
    disarida = cikti_dizini.parent / "disarida.log"
    disarida.write_text("DI SARI\n", encoding="utf-8")
    gorev_id = ekle(db, log={"yol": f"{cikti_dizini}/../disarida.log"})
    govde = istemci.get(f"/gorev/{gorev_id}").get_data(as_text=True)
    assert "DI SARI" not in govde
    assert "Log okunamadı" in govde


def test_log_mutlak_yol_disi_reddedilir(istemci, db, cikti_dizini, tmp_path):
    disarida = tmp_path / "mutlak.log"
    disarida.write_text("MUTLAK\n", encoding="utf-8")
    gorev_id = ekle(db, log={"yol": str(disarida)})
    assert "MUTLAK" not in istemci.get(f"/gorev/{gorev_id}").get_data(as_text=True)


def test_log_sembolik_link_disi_reddedilir(istemci, db, cikti_dizini, tmp_path):
    disarida = tmp_path / "hedef.log"
    disarida.write_text("SEMBOLIK HEDEF\n", encoding="utf-8")
    link = cikti_dizini / "bag.log"
    link.symlink_to(disarida)
    gorev_id = ekle(db, log={"yol": str(link)})
    assert "SEMBOLIK HEDEF" not in istemci.get(f"/gorev/{gorev_id}").get_data(as_text=True)


def test_log_sembolik_link_ici_okunur(istemci, db, cikti_dizini):
    hedef = cikti_dizini / "gercek.log"
    hedef.write_text("IC HEDEF\n", encoding="utf-8")
    link = cikti_dizini / "bag2.log"
    link.symlink_to(hedef)
    gorev_id = ekle(db, log={"yol": str(link)})
    assert "IC HEDEF" in istemci.get(f"/gorev/{gorev_id}").get_data(as_text=True)


def test_log_yoksa_okunamaz(istemci, db, cikti_dizini):
    gorev_id = ekle(db, log={"yol": str(cikti_dizini / "yok.log")})
    assert "Log okunamadı" in istemci.get(f"/gorev/{gorev_id}").get_data(as_text=True)


def test_log_yolu_bos(istemci, db):
    gorev_id = ekle(db, log={"yol": None})
    assert "Log okunamadı" in istemci.get(f"/gorev/{gorev_id}").get_data(as_text=True)


def test_kosu_yoksa_log_yok(istemci, db):
    gorev_id = ekle(db)
    assert "Log okunamadı" in istemci.get(f"/gorev/{gorev_id}").get_data(as_text=True)


def test_guvenli_log_yolu_dogrudan(tmp_path):
    kok = tmp_path / "runs"
    kok.mkdir()
    ic = kok / "a.log"
    ic.write_text("x", encoding="utf-8")
    assert sunucu.guvenli_log_yolu(str(ic), kok) == ic.resolve()
    assert sunucu.guvenli_log_yolu(str(kok.parent / "b.log"), kok) is None
    assert sunucu.guvenli_log_yolu(None, kok) is None


def test_log_son_200_satir(istemci, db, cikti_dizini):
    log = cikti_dizini / "cok.log"
    log.write_text("\n".join(f"satir{i}" for i in range(500)) + "\n", encoding="utf-8")
    gorev_id = ekle(db, log={"yol": str(log)})
    govde = istemci.get(f"/gorev/{gorev_id}").get_data(as_text=True)
    assert "satir499" in govde
    assert "satir0<" not in govde  # ilk satirlar kirpildi


# -- JSON sekilleri ---------------------------------------------------------


def test_api_gorevler_sekli(istemci, db):
    gorev_id = ekle(db)
    veri = istemci.get("/api/gorevler").get_json()
    assert set(veri) == {"gorevler"}
    kayit = veri["gorevler"][0]
    assert kayit["id"] == gorev_id
    assert set(kayit) == {"id", "ajan", "istem", "durum", "durum_etiket", "olusturma"}


def test_api_gorev_sekli(istemci, db):
    gorev_id = ekle(db, log={"yol": None, "cikis_kodu": 0})
    veri = istemci.get(f"/api/gorev/{gorev_id}").get_json()
    assert set(veri) == {"id", "ajan", "istem", "durum", "durum_etiket", "olusturma", "kosular", "log"}
    assert set(veri["kosular"][0]) == {"id", "baslangic", "bitis", "cikis_kodu", "log_yolu", "kanit", "hata"}
    assert set(veri["log"]) == {"ok", "metin", "satir", "yol"}


def test_api_kota_sekli(istemci):
    veri = istemci.get("/api/kota").get_json()
    assert set(veri) == {"gun", "limit_kaynagi", "toplam_istek", "uyari_sayisi", "veri_var", "modeller"}
    for m in veri["modeller"]:
        assert set(m) == {"model", "etiket", "istek", "limit", "durum", "yuzde", "seri"}


def test_saglik_sekli(istemci):
    assert istemci.get("/saglik").get_json() == {"durum": "ok"}


def test_api_turkce_kacis_yok(istemci, db):
    ekle(db, istem="Türkçe ğüşıöç test")
    ham = istemci.get("/api/gorevler").get_data(as_text=True)
    assert "\\u" not in ham
    assert "Türkçe" in ham


# -- filtre ve siralama -----------------------------------------------------


def test_durum_filtresi(istemci, db):
    ekle(db, durum="bekliyor")
    ekle(db, durum="bitti")
    veri = istemci.get("/api/gorevler?durum=bitti").get_json()
    assert len(veri["gorevler"]) == 1
    assert veri["gorevler"][0]["durum"] == "bitti"


def test_gecersiz_durum_filtresi_yoksayilir(istemci, db):
    ekle(db, durum="bekliyor")
    veri = istemci.get("/api/gorevler?durum=%27+OR+1%3D1--").get_json()
    assert len(veri["gorevler"]) == 1


def test_sql_enjeksiyonu_durum_param(istemci, db):
    ekle(db)
    cevap = istemci.get("/api/gorevler?durum=x%27%20OR%20%271%27%3D%271")
    assert cevap.status_code == 200
    assert len(cevap.get_json()["gorevler"]) == 1  # tum gorevler, hata degil


def test_sql_enjeksiyonu_id(istemci):
    assert istemci.get("/api/gorev/1%20OR%201%3D1").status_code == 404


def test_en_yeni_ustte(istemci, db):
    ilk = ekle(db, istem="ilk")
    son = ekle(db, istem="son")
    veri = istemci.get("/api/gorevler").get_json()["gorevler"]
    assert [k["id"] for k in veri] == [son, ilk]


def test_istem_onizleme_100_karakter(istemci, db):
    uzun = "x" * 500
    gorev_id = ekle(db, istem=uzun)
    kayit = istemci.get("/api/gorevler").get_json()["gorevler"][0]
    assert len(kayit["istem"]) == sunucu.ISTEM_ONIZLEME
    # Detayda tam istem var.
    detay = istemci.get(f"/api/gorev/{gorev_id}").get_json()
    assert len(detay["istem"]) == 500


def test_istem_onizleme_satir_birlestirir():
    assert sunucu.istem_onizleme("  bir\n  iki   uc ") == "bir iki uc"


# -- bos DB -----------------------------------------------------------------


def test_bos_db_kuyruk(istemci):
    govde = istemci.get("/").get_data(as_text=True)
    assert "Kuyruk boş" in govde
    assert "goreli" not in govde  # tablo basligi cizilmemeli


def test_bos_db_gorev_listesi_api(istemci):
    assert istemci.get("/api/gorevler").get_json() == {"gorevler": []}


def test_bos_db_kota(istemci):
    # Hiç snapshot yok: "0 istek" DEĞİL, "okunmadı" gösterilir.
    govde = istemci.get("/kota").get_data(as_text=True)
    assert "Kota verisi yok" in govde
    assert "kota-guncelle" in govde


def test_bos_db_kota_veri_var_false(istemci):
    assert istemci.get("/api/kota").get_json()["veri_var"] is False


def test_kota_gercek_sifir_istek_gosterilir(istemci, db):
    """Snapshot VAR ama istek 0 ise 'kota verisi yok' DENİMELİ ( dürüst durum )."""
    b = sqlite3.connect(db)
    b.execute(
        "INSERT INTO quota_snapshots (model, gun, istek, maliyet) VALUES (?,?,?,0)",
        ("a/b:free", "2020-01-01", 0),
    )
    b.commit()
    b.close()
    govde = istemci.get("/kota").get_data(as_text=True)
    assert "Kota verisi yok" not in govde
    assert istemci.get("/api/kota").get_json()["veri_var"] is True


def test_bos_db_filtreli_kuyruk(istemci):
    assert "Bu filtrede görev yok" in istemci.get("/?durum=hata").get_data(as_text=True)


# -- kota sayfasi -----------------------------------------------------------


def test_kota_sayfasi_model_renkleri(istemci, db):
    b = sqlite3.connect(db)
    b.execute(
        "INSERT INTO quota_snapshots (model, gun, istek, maliyet) VALUES (?,?,?,0)",
        ("nvidia/nemotron-3-ultra-550b-a55b:free", "2020-01-01", 5),
    )
    b.commit()
    b.close()
    govde = istemci.get("/kota").get_data(as_text=True)
    assert "nemotron" in govde


def test_kota_graf_svg(istemci, db):
    b = sqlite3.connect(db)
    for gun in ("2026-09-28", "2026-09-29", "2026-09-30"):
        b.execute(
            "INSERT INTO quota_snapshots (model, gun, istek, maliyet) VALUES (?,?,?,0)",
            ("a/b:free", gun, 7),
        )
    b.commit()
    b.close()
    govde = istemci.get("/kota").get_data(as_text=True)
    assert "<svg" in govde and "</svg>" in govde


def test_kota_cdn_yok(istemci):
    govde = istemci.get("/kota").get_data(as_text=True)
    assert "http://" not in govde
    assert "https://" not in govde


# -- grafik geometrisi ------------------------------------------------------


def test_graf_taban_genislik_sabit():
    seri = [{"gun": "2026-09-30", "istek": i} for i in range(14)]
    graf = sunucu.grafigi_hazirla(seri, None)
    assert graf["genislik"] == sunucu.GRAF_TABAN
    assert graf["yukseklik"] == sunucu.GRAF_YUKSEK


def test_graf_14_cubuk():
    seri = [{"gun": f"2026-09-{i:02d}", "istek": i} for i in range(1, 15)]
    assert len(sunucu.grafigi_hazirla(seri, None)["cubuklar"]) == 14


def test_graf_bos_veri():
    seri = [{"gun": "2026-09-30", "istek": 0}] * 14
    graf = sunucu.grafigi_hazirla(seri, None)
    assert graf["bos"] is True


def test_graf_etiketler_ayrik():
    seri = [{"gun": "2026-09-30", "istek": 1} for _ in range(14)]
    graf = sunucu.grafigi_hazirla(seri, None)
    xler = [e["x"] for e in graf["etiketler"]]
    assert xler == sorted(xler)
    # Etiketler birbirine cok yakin olmamali (>=28 px aralik).
    farklar = [b - a for a, b in zip(xler, xler[1:])]
    assert all(f >= 28 for f in farklar)


def test_graf_limit_cizgisi_yok_limit():
    seri = [{"gun": "2026-09-30", "istek": 3} for _ in range(14)]
    assert sunucu.grafigi_hazirla(seri, None)["limit"] is None


def test_graf_limit_cizgisi_var():
    seri = [{"gun": "2026-09-30", "istek": 3} for _ in range(14)]
    graf = sunucu.grafigi_hazirla(seri, 50)
    assert graf["limit"] is not None
    assert graf["tavan"] >= 50


def test_graf_limit_etiketi_kutu_ici():
    """`limit N` etiketi SVG genişliğini AŞMAMALI (taşarsa kırpılır)."""
    seri = [{"gun": "2026-09-30", "istek": 3} for _ in range(14)]
    graf = sunucu.grafigi_hazirla(seri, 50)
    # 11 px sans-serif'te "limit 50" ~42 px geniş; sağda 52 px + 8 px pay var.
    assert graf["limit"]["tx"] + 42 <= graf["genislik"], graf


def test_graf_tavan_okunur():
    assert sunucu._guzel_tavan(0) == 1
    assert sunucu._guzel_tavan(1) == 1
    assert sunucu._guzel_tavan(7) == 10
    assert sunucu._guzel_tavan(1200) == 2000


def test_graf_cubuklar_viewbox_ici():
    seri = [{"gun": "2026-09-30", "istek": i * 100} for i in range(14)]
    graf = sunucu.grafigi_hazirla(seri, 50)
    for c in graf["cubuklar"]:
        assert 0 <= c["x"]
        assert c["x"] + c["genislik"] <= graf["genislik"] + 0.5
        assert 0 <= c["y"] <= graf["yukseklik"]


def test_graf_sifir_sutun_isaretli():
    seri = [{"gun": "2026-09-30", "istek": 0}] * 13 + [{"gun": "2026-09-30", "istek": 5}]
    graf = sunucu.grafigi_hazirla(seri, None)
    assert sum(1 for c in graf["cubuklar"] if c["bos"]) == 13
    assert graf["bos"] is False


# -- statik dosyalar --------------------------------------------------------


def test_statik_dosyalar_dagitilir(istemci):
    assert istemci.get("/static/stil.css").status_code == 200
    assert istemci.get("/static/panel.js").status_code == 200


def test_js_innerHTML_kullanmaz(istemci):
    """`innerHTML` YORUMDA geçse bile KODDA olmamalı.

    Blok yorumların tamamı (gövde + kapanış) silinir; satır yorumları da düşer.
    """
    kaynak = istemci.get("/static/panel.js").get_data(as_text=True)
    blok_ici = False
    kod_satirlari = []
    for satir in kaynak.splitlines():
        temiz = satir.strip()
        if blok_ici:
            if "*/" in temiz:
                blok_ici = False
            continue
        if temiz.startswith("/*"):
            if "*/" not in temiz:
                blok_ici = True
            continue
        if temiz.startswith("//"):
            continue
        kod_satirlari.append(satir)
    kod = "\n".join(kod_satirlari)
    assert "innerHTML" not in kod
    assert "outerHTML" not in kod
    assert "document.write" not in kod
    assert "eval(" not in kod


def test_stil_beyaz_varsayilan_yok():
    from pathlib import Path

    kaynak = (Path(sunucu.__file__).parent / "static" / "stil.css").read_text(encoding="utf-8")
    # Koyu tema: beyaz varsayilan kontrol kaliplari tanimli degil.
    assert "background: #fff" not in kaynak
    assert "background: white" not in kaynak
    assert "background: #ffffff" not in kaynak


def test_stil_dark_zemin_ve_palet():
    from pathlib import Path

    kaynak = (Path(sunucu.__file__).parent / "static" / "stil.css").read_text(encoding="utf-8")
    assert "#0f1115" in kaynak   # zemin
    assert "#e6e6e6" in kaynak   # metin
    assert "#9aa3b2" in kaynak   # ikincil
    for renk in ("#E69F00", "#56B4E9", "#009E73", "#F0E442", "#0072B2", "#D55E00", "#CC79A7", "#999999"):
        assert renk.lower() in kaynak.lower(), renk


def test_stil_mobil_kart_gorunumu():
    from pathlib import Path

    kaynak = (Path(sunucu.__file__).parent / "static" / "stil.css").read_text(encoding="utf-8")
    assert "@media" in kaynak
    assert ".kart-liste" in kaynak


def test_rozet_yalnizca_renge_dayanmaz(istemci, db):
    """Durum rozeti metin de icermeli (renk korluğu)."""
    ekle(db, durum="onay-bekliyor")
    govde = istemci.get("/").get_data(as_text=True)
    assert "onay bekliyor" in govde  # ASCII değil, ETIKET metni


def test_sunucu_host_sabit(db, cikti_dizini):
    """`--host` secenegi YOK; adres kodda sabit."""
    import inspect

    kaynak = inspect.getsource(sunucu.calistir)
    assert 'host="127.0.0.1"' in kaynak
    assert "0.0.0.0" not in kaynak
