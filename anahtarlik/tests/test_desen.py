"""desen: satir duzeyinde tur tespiti.

YAPAY anahtar `SENTINEL` ile isaretlidir: ham hali hicbir ciktida gecmemelidir.
"""

from __future__ import annotations

import pytest

from anahtarlik import desen

#: `_DESEN_SK` ile eslesen yapay anahtar (rakam icerir, 20+ karakter).
ANAHTAR = "sk-SENTINEL8fHq2Lp9Zx4Wq7Nb3"
#: `_DESEN_ETIKETLI_DEGER` ile eslesen yapay deger.
ETIKETLI = "API_KEY=SENTINEL8fHq2Lp9Zx4"


def test_bos_satir_bulgu_degil():
    assert desen.satir_tara("") is None


def test_gunluk_kod_bulgu_degil():
    assert desen.satir_tara("print('merhaba')  # buraya bir sey yazilir") is None


def test_yapay_sk_anahtari_yakalanir():
    tur = desen.satir_tara(f'token = "{ANAHTAR}"')
    assert tur == "sk-anahtari"


def test_etiketli_yapay_deger_yakalanir():
    assert desen.satir_tara(ETIKETLI) is not None


@pytest.mark.parametrize(
    "satir",
    [
        "API_KEY=<senin-anahtarin>",
        "API_KEY=xxxxxxxxxxxxxxxxxxxxxxxx",
        "api_key=${GITHAYIR}",
        "token = process.env.API_KEY",
        "secret = os.environ['SOMETHING']",
        "API_KEY=changeme1234567890",
        "API_KEY=your-api-key-here-0123",
        "password = <buraya-yaz>",
    ],
)
def test_yer_tutucu_ve_kod_referansi_bulgu_degil(satir):
    """Yer tutucu, kabuk degiskeni ve KOD referansi sir DEGILDIR."""
    assert desen.satir_tara(satir) is None


def test_sk_kebab_case_elenir():
    """`sk-` sonrasi rakam yoksa elenir: `flask-sqlalchemy-...` sir degildir."""
    assert desen.satir_tara("sk-sqlalchemy-migrate-extension") is None


def test_ozel_anahtar_basligi():
    assert desen.satir_tara("-----BEGIN RSA PRIVATE KEY-----") == "ozel-anahtar"


@pytest.mark.parametrize(
    "satir,tur",
    [
        ("AKIAIOSFODNN7EXAMPLE", "aws-anahtari"),
        ("ghp_" + "a" * 36, "github-token"),
        ("xoxb-123456789012-abcdefghij", "slack-token"),
        ("sk_live_" + "a" * 24, "stripe-anahtari"),
        ("sb_secret_" + "a" * 30, "sb-secret"),
        (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N",
            "jwt",
        ),
    ],
)
def test_saglayici_tipleri(satir, tur):
    assert desen.satir_tara(satir) == tur


def test_nul_lu_satir_taranmaz():
    assert desen.satir_tara("a\x00b") is None


def test_onizleme_maskeli_tur():
    """Onizleme yalnizca tur isaretidir, ham metin YOK."""
    onizleme = desen.onizleme("sk-anahtari")
    assert onizleme == "[maskeli:sk-anahtari]"
    assert ANAHTAR not in onizleme


def test_tur_listesi_isimlendirilmis():
    turler = desen.tur_listesi()
    assert "sk-anahtari" in turler and "ozel-anahtar" in turler
    assert len(turler) == len(set(turler))  # tur adlari tekil


def test_bulgu_sozlugu_alani_dort():
    b = desen.bulgu("app.py", 12, "sk-anahtari")
    assert set(b) == {"dosya", "satir", "tur", "onizleme"}
    assert b["onizleme"] == "[maskeli:sk-anahtari]"


@pytest.mark.parametrize("ad", [".env", ".env.local", ".ENV", ".env.production"])
def test_env_dosyasi_mi_gec_dosyalar(ad):
    assert desen.env_dosyasi_mi(f"klasor/{ad}") is True


@pytest.mark.parametrize(
    "ad", [".env.example", ".env.sample", ".env.template", "env.py", ".environment"]
)
def test_env_dosyasi_mi_ornek_dosyalar(ad):
    assert desen.env_dosyasi_mi(ad) is False


def test_ham_anahtar_ciktida_yok():
    """SENTINEL yapay anahtari hicbir yerde ham gecmez."""
    tur = desen.satir_tara(ETIKETLI)
    assert tur is not None
    assert ANAHTAR not in tur
    assert "SENTINEL" not in tur