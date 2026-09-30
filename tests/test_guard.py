"""Giriş doğrulama: reddedilen her desen, kabul edilen temiz metin, maskeleme."""

import pytest

from orkestra.guard import (
    ISTEM_EN_FAZLA,
    ajan_gecerli,
    gizli_desen_ara,
    girdi_kontrol,
    istem_kontrol,
    maskele,
)
from orkestra.models import GecersizGirdi
from orkestra.queue import Queue

SIRLAR = {
    "api anahtari": "sk-abcdefghijklmnopqrstuvwxyz012345",
    "aws erisim anahtari": "AKIAIOSFODNN7EXAMPLE",
    "ozel anahtar": "-----BEGIN RSA PRIVATE KEY-----",
    "env dosyasi": "/home/kullanici/proje/.env dosyasina bak",
    "sifre/anahtar atamasi": "api_key = abcdefgh12345",
}

TEMIZ = {
    "kisa is": "kendi notlarina bak ve ozet yaz",
    "yol": "/home/kullanici/proje/kod.py dosyasini ac",
    "api_key kelimesi": "api_key kelimesinin gecerli adresini bul",
    "token kelimesi": "token bilgisiyle ilgili degil, sadece bir sozcuk",
    "environment kelimesi": "environment variables konusunu anlat",
    "sk kisa": "sk-1234 yeterince uzun degil",
    "env kelimesi": "environment icinde calisiyor",
    "turkce": "Türkçe karakterler: ı İ ş ğ ç ö ü",
}


# -- ajan adi ------------------------------------------------------------


@pytest.mark.parametrize("ajan", ["bunny-coder", "a", "x1", "nemotron", "a-b-c-9"])
def test_gecerli_ajan_adlari(ajan):
    assert ajan_gecerli(ajan)


@pytest.mark.parametrize(
    "ajan",
    ["", "-abc", "Abc", "abc_def", "abc.def", "abc def", "ünny", "abc/1", "a" * 40 + "!"],
)
def test_gecersiz_ajan_adlari(ajan):
    assert not ajan_gecerli(ajan)
    with pytest.raises(GecersizGirdi):
        girdi_kontrol(ajan, "temiz is")


def test_gecersiz_ajan_hatasi_istemi_yansitmaz():
    with pytest.raises(GecersizGirdi) as bilgi:
        girdi_kontrol("GECERSIZ AJAN", "gizli: sk-abcdefghijklmnopqrstuvwxyz012345")
    assert "sk-abcdefghijklmnop" not in str(bilgi.value)


# -- istem sinirlari ----------------------------------------------------


@pytest.mark.parametrize("istem", ["", "   ", "\n\t "])
def test_bos_istem_reddi(istem):
    with pytest.raises(GecersizGirdi):
        istem_kontrol(istem)


def test_cok_uzun_istem_reddi():
    with pytest.raises(GecersizGirdi):
        istem_kontrol("a" * (ISTEM_EN_FAZLA + 1))


def test_sinirdaki_istem_kabul():
    istem_kontrol("a" * ISTEM_EN_FAZLA)


def test_almost_cok_uzun_istem_kabul():
    istem_kontrol("a" * (ISTEM_EN_FAZLA - 1))


# -- gizli desenler -----------------------------------------------------


@pytest.mark.parametrize("ad,istem", sorted(SIRLAR.items()))
def test_gizli_desen_reddi(ad, istem):
    assert gizli_desen_ara(istem), f"{ad} yakalanmadi"
    with pytest.raises(GecersizGirdi):
        istem_kontrol(istem)


@pytest.mark.parametrize("ad,istem", sorted(TEMIZ.items()))
def test_temiz_metin_kabul(ad, istem):
    assert gizli_desen_ara(istem) == []
    istem_kontrol(istem)


def test_env_dosya_adi_cesitleri():
    for istem in [".env", ".env.local", "cat .env ", "yol/.env\n", "a/.env.txt"]:
        with pytest.raises(GecersizGirdi):
            istem_kontrol(istem)


def test_env_kelimesi_yanlis_pozitif_uretmemesi():
    istem_kontrol("environment.yml dosyasini oku")
    istem_kontrol("envexample.txt adli dosya")


def test_anahtar_atamasi_cesitleri():
    for istem in [
        "token=abcdefgh1234",
        "secret : abcdefgh1234",
        "PASSWORD=qwertyuiop",
        "api-key: 1234567890",
        "my_api_key=9876543210",
    ]:
        with pytest.raises(GecersizGirdi):
            istem_kontrol(istem)


def test_kisa_atama_kabul():
    istem_kontrol("token=abc")
    istem_kontrol("api_key: x")
    istem_kontrol("isimlendirmede api_key kelimesi gecerli")


# -- maskeleme ----------------------------------------------------------


@pytest.mark.parametrize("ad,sir", sorted(SIRLAR.items()))
def test_maskele_gizli_kalibi_kaldirir(ad, sir):
    assert sir not in maskele(sir)


def test_maskele_temiz_metni_bozmasin():
    for istem in TEMIZ.values():
        assert maskele(istem) == istem


def test_hata_mesaji_sirri_icermez():
    s = SIRLAR["api anahtari"]
    with pytest.raises(GecersizGirdi) as bilgi:
        istem_kontrol(f"bu istege bak: {s}")
    mesaj = str(bilgi.value)
    assert s not in mesaj
    assert "sk-abcdefghijklmnop" not in mesaj


def test_maskelenmis_hata_mesaji_hazir():
    s = SIRLAR["api anahtari"]
    assert maskele(s) == "[maskeli]"
    assert maskele(f"anahtar: {s} son") == "anahtar: [maskeli] son"


# -- kuyruk seviyesi ----------------------------------------------------


def test_kuyruk_ekle_gizli_istemi_reddeder(kuyruk):
    with pytest.raises(GecersizGirdi):
        kuyruk.ekle("bunny-coder", SIRLAR["aws erisim anahtari"])
    assert kuyruk.liste() == []


def test_kuyruk_ekle_gecersiz_ajani_reddeder(kuyruk):
    with pytest.raises(GecersizGirdi):
        kuyruk.ekle("Bunny Coder!", "temiz is")
    assert kuyruk.liste() == []


def test_kuyruk_ekle_turkce_istemi_kabul(kuyruk):
    gorev = kuyruk.ekle("bunny-coder", "Şu ızgara ğğğ öüç test et")
    assert "ızgara" in kuyruk.al(gorev.id).istem