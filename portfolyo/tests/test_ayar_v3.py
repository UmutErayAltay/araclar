"""ayar: dil/dil_baglantisi, deneyim/egitim/yetenekler; sahip iletişim + ledler; repo.one_cikan.

Yeni alanların hepsi opsiyonel: alan yoksa eski davranış ve varsayılanlar geçerli.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from portfolyo.ayar import AyarHatasi, Deneyim, Egitim, Led, YetenekGrubu, ayar_oku

SAHIP = {"ad": "Test", "unvan": "Dev", "github": "testuser", "hakkinda": "Merhaba."}
REPO = {"ad": "demo", "herkese_acik": True}


def _oku(tmp_path: Path, **ek):
    veri = {"sahip": SAHIP, "repolar": [REPO], **ek}
    yol = tmp_path / "p.json"
    yol.write_text(json.dumps(veri, ensure_ascii=False), encoding="utf-8")
    return ayar_oku(yol)


# --- alanlar yokken eski davranış ---------------------------------------------------------

def test_yeni_alanlar_yokken_varsayilanlar(tmp_path):
    a = _oku(tmp_path)
    assert a.dil == "tr" and a.dil_baglantisi == ""
    assert a.deneyim == () and a.egitim == () and a.yetenekler == ()
    assert a.repolar[0].one_cikan is False
    s = a.sahip
    assert (s.eposta, s.linkedin, s.konum, s.cv_tr, s.cv_en, s.ledler) == ("", "", "", "", "", ())


def test_bilinmeyen_alan_hala_reddedilir(tmp_path):
    with pytest.raises(AyarHatasi, match="tanınmayan kök alan"):
        _oku(tmp_path, deneyim_x=1)
    with pytest.raises(AyarHatasi, match=r"sahip\.telefon: tanınmayan alan"):
        _oku(tmp_path, sahip={**SAHIP, "telefon": "0"})


# --- dil / dil_baglantisi -----------------------------------------------------------------

def test_dil_gecerli(tmp_path):
    assert _oku(tmp_path, dil="en").dil == "en"
    assert _oku(tmp_path, dil="tr").dil == "tr"


@pytest.mark.parametrize("dil", ["fr", "TR", "", 3, None, True])
def test_dil_gecersiz(tmp_path, dil):
    with pytest.raises(AyarHatasi, match="dil"):
        _oku(tmp_path, dil=dil)


@pytest.mark.parametrize("yol", ["/en/", "/", "/en", "/a/b_c-1/"])
def test_dil_baglantisi_gecerli(tmp_path, yol):
    assert _oku(tmp_path, dil_baglantisi=yol).dil_baglantisi == yol


@pytest.mark.parametrize(
    "yol",
    [
        "en/", "../en/", "/a/../b", "/..", "//evil.io", "/a//b", "https://x.io/en",
        "/en?x=1", "/en#a", "/en\x00", "/" + "a" * 100, 5, None, ["x"],
    ],
)
def test_dil_baglantisi_gecersiz(tmp_path, yol):
    with pytest.raises(AyarHatasi, match="dil_baglantisi"):
        _oku(tmp_path, dil_baglantisi=yol)


# --- deneyim ------------------------------------------------------------------------------

def test_deneyim_gecerli(tmp_path):
    a = _oku(tmp_path, deneyim=[
        {"rol": "Geliştirici", "kurum": "Acme", "tarih": "2020-2024", "aciklama": "X yaptı."},
        {"rol": "Stajyer", "kurum": "Beta"},  # tarih/aciklama opsiyonel
    ])
    assert a.deneyim == (
        Deneyim(rol="Geliştirici", kurum="Acme", tarih="2020-2024", aciklama="X yaptı."),
        Deneyim(rol="Stajyer", kurum="Beta", tarih="", aciklama=""),
    )


@pytest.mark.parametrize(
    "deneyim",
    [
        "x", {"rol": "a"},                                            # liste bekleniyor
        [{"kurum": "A"}], [{"rol": "A"}],                             # rol/kurum zorunlu
        [{"rol": "", "kurum": "A"}], [{"rol": "A", "kurum": ""}],
        [{"rol": "A", "kurum": "B", "rol2": 1}],                      # tanınmayan alan
        [{"rol": "A\x00", "kurum": "B"}], [{"rol": "A", "kurum": "B\x00c"}],
        [{"rol": "x" * 81, "kurum": "B"}], [{"rol": "A", "kurum": "y" * 81}],
        [{"rol": "A", "kurum": "B", "tarih": "t" * 81}], [{"rol": "A", "kurum": "B", "aciklama": "a" * 601}],
        [{"rol": 5, "kurum": "B"}], [{"rol": "A", "kurum": 5}], ["metin"],
        [{"rol": f"r{i}", "kurum": "B"} for i in range(9)],           # en fazla 8
    ],
)
def test_deneyim_gecersiz(tmp_path, deneyim):
    with pytest.raises(AyarHatasi, match="deneyim"):
        _oku(tmp_path, deneyim=deneyim)


# --- egitim -------------------------------------------------------------------------------

def test_egitim_gecerli(tmp_path):
    a = _oku(tmp_path, egitim=[
        {"derece": "Lisans", "okul": "İTÜ", "tarih": "2019", "ek": "Bilgisayar"},
        {"derece": "Lise", "okul": "Anadolu"},
    ])
    assert a.egitim == (
        Egitim(derece="Lisans", okul="İTÜ", tarih="2019", ek="Bilgisayar"),
        Egitim(derece="Lise", okul="Anadolu", tarih="", ek=""),
    )


@pytest.mark.parametrize(
    "egitim",
    [
        "x", {"derece": "a"}, [{"okul": "A"}], [{"derece": "A"}],
        [{"derece": "", "okul": "A"}], [{"derece": "A", "okul": ""}],
        [{"derece": "A", "okul": "B", "ekstra": 1}],
        [{"derece": "x" * 101, "okul": "B"}], [{"derece": "A", "okul": "y" * 101}],
        [{"derece": "A", "okul": "B", "tarih": "t" * 81}], [{"derece": "A", "okul": "B", "ek": "e" * 81}],
        [{"derece": "A\x00", "okul": "B"}], [{"derece": 5, "okul": "B"}],
        [{"derece": f"d{i}", "okul": "B"} for i in range(5)],          # en fazla 4
    ],
)
def test_egitim_gecersiz(tmp_path, egitim):
    with pytest.raises(AyarHatasi, match="egitim"):
        _oku(tmp_path, egitim=egitim)


# --- yetenekler ---------------------------------------------------------------------------

def test_yetenekler_gecerli(tmp_path):
    a = _oku(tmp_path, yetenekler=[
        {"grup": "Diller", "ogeler": ["Python", "TypeScript"]},
        {"grup": "Araçlar", "ogeler": ["Git"]},
    ])
    assert a.yetenekler == (
        YetenekGrubu(grup="Diller", ogeler=("Python", "TypeScript")),
        YetenekGrubu(grup="Araçlar", ogeler=("Git",)),
    )
    assert _oku(tmp_path, yetenekler=[{"grup": "Diller", "ogeler": ["a" * 40]}]).yetenekler[0].ogeler == ("a" * 40,)


@pytest.mark.parametrize(
    "yetenekler",
    [
        "x", {"grup": "a"}, [{}], [{"ogeler": ["a"]}],
        [{"grup": ""}], [{"grup": "x" * 41}],
        [{"grup": "A", "baslik": 1}],                                  # tanınmayan alan
        [{"grup": "A"}],                                              # ogeler 1-12 olmalı
        [{"grup": "A", "ogeler": []}], [{"grup": "A", "ogeler": "Python"}],
        [{"grup": "A", "ogeler": ["x" * 41]}], [{"grup": "A", "ogeler": [""]}],
        [{"grup": "A", "ogeler": ["ok", 5]}], [{"grup": "A", "ogeler": ["ok\x00"]}],
        [{"grup": "A\x00", "ogeler": ["ok"]}],
        [{"grup": f"g{i}", "ogeler": ["a"]} for i in range(9)],        # en fazla 8 grup
        [{"grup": "A", "ogeler": [f"o{i}" for i in range(13)]}],      # en fazla 12 öğe
    ],
)
def test_yetenekler_gecersiz(tmp_path, yetenekler):
    with pytest.raises(AyarHatasi, match="yetenekler"):
        _oku(tmp_path, yetenekler=yetenekler)


# --- sahip: eposta / linkedin / konum / cv -------------------------------------------------

def test_sahip_iletisim_gecerli(tmp_path):
    a = _oku(tmp_path, sahip={**SAHIP, "eposta": "umut+site@example.co.uk",
                              "linkedin": "https://www.linkedin.com/in/umut",
                              "konum": "Istanbul, Turkiye",
                              "cv_tr": "/cv/umut-cv.pdf", "cv_en": "/cv/resume.pdf"})
    s = a.sahip
    assert s.eposta == "umut+site@example.co.uk"
    assert s.linkedin == "https://www.linkedin.com/in/umut"
    assert s.konum == "Istanbul, Turkiye"
    assert (s.cv_tr, s.cv_en) == ("/cv/umut-cv.pdf", "/cv/resume.pdf")


@pytest.mark.parametrize(
    "eposta",
    ["umut", "umut@", "@example.com", "umut example.com", "a@b@c.com", "umut@x",
     "a" * 96 + "@e.com", 5, None, "a@b\n.com"],
)
def test_eposta_gecersiz(tmp_path, eposta):
    with pytest.raises(AyarHatasi, match="eposta"):
        _oku(tmp_path, sahip={**SAHIP, "eposta": eposta})


def test_eposta_100_karakter_siniri(tmp_path):
    tam = "a" * 93 + "@ex.com"  # 100 karakter
    assert len(tam) == 100
    assert _oku(tmp_path, sahip={**SAHIP, "eposta": tam}).sahip.eposta == tam
    with pytest.raises(AyarHatasi, match=r"eposta: en fazla 100 karakter"):
        _oku(tmp_path, sahip={**SAHIP, "eposta": "a" * 94 + "@ex.com"})


@pytest.mark.parametrize(
    "linkedin",
    [
        "javascript:alert(1)", "http://www.linkedin.com/in/x", "https://linkedin.com.evil.io/in/x",
        "https://notlinkedin.com/in/x", "//www.linkedin.com/in/x",
        "https://www.linkedin.com/\"onload=", 5, None, 1,
    ],
)
def test_linkedin_gecersiz(tmp_path, linkedin):
    with pytest.raises(AyarHatasi, match="linkedin"):
        _oku(tmp_path, sahip={**SAHIP, "linkedin": linkedin})


def test_linkedin_yalniz_linkedin_hostu(tmp_path):
    for adres in ("https://linkedin.com/in/umut", "https://www.linkedin.com",
                  "https://www.linkedin.com/company/x?trk=y"):
        assert _oku(tmp_path, sahip={**SAHIP, "linkedin": adres}).sahip.linkedin == adres


@pytest.mark.parametrize("konum", ["x" * 61, "İs\x00tanbul", 5, ["x"]])
def test_konum_gecersiz(tmp_path, konum):
    with pytest.raises(AyarHatasi, match="konum"):
        _oku(tmp_path, sahip={**SAHIP, "konum": konum})


@pytest.mark.parametrize(
    "cv",
    [
        "cv/umut.pdf", "../cv.pdf", "/cv/../gizli.pdf", "//x.io/cv.pdf", "/cv/umut.pdf.html",
        "/cv/umut.pdf\"onload=1", "/cv/umut p.pdf", "/cv/" + "a" * 120 + ".pdf", 5, None,
    ],
)
def test_cv_yolu_gecersiz(tmp_path, cv):
    for alan in ("cv_tr", "cv_en"):
        with pytest.raises(AyarHatasi, match=alan):
            _oku(tmp_path, sahip={**SAHIP, alan: cv})


def test_cv_yolu_bos_ve_kosul_gecerli(tmp_path):
    a = _oku(tmp_path, sahip={**SAHIP, "cv_tr": "", "cv_en": "/a/b.pdf"})
    assert a.sahip.cv_tr == "" and a.sahip.cv_en == "/a/b.pdf"


# --- sahip: ledler ------------------------------------------------------------------------

def test_ledler_gecerli(tmp_path):
    a = _oku(tmp_path, sahip={**SAHIP, "ledler": [
        {"metin": "İletişim", "tur": "eylem"},
        {"metin": "CV"},                       # tur varsayılan "acik"
        {"metin": "Kapat", "tur": "kapali"},
    ]})
    assert a.sahip.ledler == (
        Led(metin="İletişim", tur="eylem"),
        Led(metin="CV", tur="acik"),
        Led(metin="Kapat", tur="kapali"),
    )
    assert _oku(tmp_path, sahip={**SAHIP, "ledler": []}).sahip.ledler == ()
    # 4 led sınırı dahilinde
    assert len(_oku(tmp_path, sahip={**SAHIP, "ledler": [{"metin": "x"}] * 4}).sahip.ledler) == 4


@pytest.mark.parametrize(
    "ledler",
    [
        "x", {"metin": "a"}, ["Metin"], [{"tur": "acik"}], [{}],
        [{"metin": ""}], [{"metin": "x" * 31}], [{"metin": "a\x00"}], [{"metin": 5}],
        [{"metin": "a", "tur": "yesil"}], [{"metin": "a", "tur": 5}], [{"metin": "a", "tur": None}],
        [{"metin": "a", "renk": "kirmizi"}],
        [{"metin": "x"}] * 5,                      # en fazla 4
    ],
)
def test_ledler_gecersiz(tmp_path, ledler):
    with pytest.raises(AyarHatasi, match="ledler"):
        _oku(tmp_path, sahip={**SAHIP, "ledler": ledler})


# --- repo.one_cikan -----------------------------------------------------------------------

def test_one_cikan_gecerli_ve_taninmaz_siralamayi_bozmaz(tmp_path):
    a = _oku(tmp_path, repolar=[{**REPO, "one_cikan": True}, {**REPO, "ad": "b"}])
    assert a.repolar[0].one_cikan is True and a.repolar[1].one_cikan is False


@pytest.mark.parametrize("deger", ["true", "evet", 1, 0, None, []])
def test_one_cikan_boolean_olmali(tmp_path, deger):
    with pytest.raises(AyarHatasi, match=r"one_cikan: boolean bekleniyor"):
        _oku(tmp_path, repolar=[{**REPO, "one_cikan": deger}])


def test_one_cikan_herkese_acik_kuralini_degistirmez(tmp_path):
    with pytest.raises(AyarHatasi, match="herkese_acik: tam olarak true"):
        _oku(tmp_path, repolar=[{**REPO, "herkese_acik": False, "one_cikan": True}])


# --- repo.led -----------------------------------------------------------------------------

def test_repo_led_gecerli(tmp_path):
    a = _oku(tmp_path, repolar=[{**REPO, "led": {"metin": "İncele", "tur": "eylem"}},
                                {**REPO, "ad": "b", "led": {"metin": "Kapat", "tur": "kapali"}},
                                {**REPO, "ad": "c", "led": {"metin": "Aç"}}])  # tur varsayılan "acik"
    assert a.repolar[0].led == Led(metin="İncele", tur="eylem")
    assert a.repolar[1].led == Led(metin="Kapat", tur="kapali")
    assert a.repolar[2].led == Led(metin="Aç", tur="acik")


def test_repo_led_yok_veya_null(tmp_path):
    assert _oku(tmp_path).repolar[0].led is None
    assert _oku(tmp_path, repolar=[{**REPO, "led": None}]).repolar[0].led is None


@pytest.mark.parametrize(
    "led",
    [
        "Metin", ["Metin"], 5, True,                                    # nesne bekleniyor
        {"tur": "acik"}, {},                                            # metin zorunlu
        {"metin": ""}, {"metin": "x" * 31}, {"metin": "a\x00"}, {"metin": 5},
        {"metin": "Aç", "tur": "yesil"}, {"metin": "Aç", "tur": 5}, {"metin": "Aç", "tur": None},
        {"metin": "Aç", "renk": "kirmizi"},                              # tanınmayan alan
    ],
)
def test_repo_led_gecersiz(tmp_path, led):
    with pytest.raises(AyarHatasi, match=r"led"):
        _oku(tmp_path, repolar=[{**REPO, "led": led}])


def test_repo_led_herkese_acik_kuralini_degistirmez(tmp_path):
    a = _oku(tmp_path, repolar=[{**REPO, "herkese_acik": True, "led": {"metin": "Aç"}}])
    assert a.repolar[0].led == Led(metin="Aç", tur="acik")
    with pytest.raises(AyarHatasi, match="herkese_acik: tam olarak true"):
        _oku(tmp_path, repolar=[{**REPO, "herkese_acik": False, "led": {"metin": "Aç"}}])