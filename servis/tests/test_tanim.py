"""Tanim dosyasi (TOML) okuma ve dogrulama testleri.

Gercek servisler (cor/kule/liman/postgres) CALISMAZ; yalniz tanim dosyalari
tmp_path altinda yazilir/okunur. Ag yok.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import REPO_ROOT, tanim_yaz

from servis.tanim import ServisHatasi, sec, tanim_yolu, yukle

ORNEK = REPO_ROOT / "servisler.toml.ornek"


def _tek(tmp_path: Path, **ayarlar) -> Path:
    """Tek servisten olusan gecerli bir tanim dosyasi."""
    varsayilan = {"port": 9001, "baslat": ["ornek"]}
    varsayilan.update(ayarlar)
    return tanim_yaz(tmp_path / "servisler.toml", {"tek": varsayilan})


# --------------------------------------------------------------------------
# okuma
# --------------------------------------------------------------------------


def test_ornek_dosya_dort_servis_verir():
    """Paketle gelen servisler.toml.ornek dogrulanabilir ve dort servis tanimlar."""
    servisler = yukle(ORNEK)
    assert sorted(servisler) == ["cor", "kule", "liman", "readbunny-postgres"]
    assert servisler["cor"].port == 8787
    assert servisler["cor"].durdur == ["cor", "stop"]


def test_ornek_yollari_yer_tutucu(tmp_path):
    """Ornekteki cwd'ler ~ ile yazilir ve acilir (ornek yollar mevcut olmak zorunda degil)."""
    cor = yukle(ORNEK)["cor"]
    assert cor.cwd is not None
    assert not str(cor.cwd).startswith("~"), "cwd '~' olarak kalmamali, acilmali"
    assert "projeler" in str(cor.cwd)


def test_alanlar_normalize_edilir(tmp_path):
    """Istege bagli alanlar varsayilanda kalir, cwd acilir, bekle_sn float olur."""
    tanim = _tek(tmp_path, cwd="~/projeler/ornek")
    servis = yukle(tanim)["tek"]
    assert servis.port == 9001
    assert servis.baslat == ["ornek"]
    assert servis.bekle_sn == 20.0, "bekle_sn varsayilani 20"
    assert servis.durdur is None
    assert servis.saglik_url is None
    assert str(servis.cwd).startswith(str(Path.home()))


def test_bekle_sn_ve_bekle_sn_sifir(tmp_path):
    """bekle_sn yazilabilir; 0 gecerli (bekleme yok)."""
    tanim = _tek(tmp_path, bekle_sn=0)
    assert yukle(tanim)["tek"].bekle_sn == 0.0


# --------------------------------------------------------------------------
# dogrulama hatalari (her bulgu turu icin pozitif + negatif)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("eksik", ["port", "baslat"])
def test_zorunlu_alanlar(tmp_path, eksik):
    """port/baslat zorunlu; eksikse hatada alan adi gecer."""
    ayarlar = {"port": 9001, "baslat": ["ornek"]}
    del ayarlar[eksik]
    tanim = tanim_yaz(tmp_path / "servisler.toml", {"tek": ayarlar})
    with pytest.raises(ServisHatasi) as exc:
        yukle(tanim)
    assert eksik in str(exc.value)


@pytest.mark.parametrize("port", [0, -1, 65536, "8787", 8787.5, True])
def test_port_gecersiz(tmp_path, port):
    """port 1-65535 arasi tam sayi olmali."""
    tanim = _tek(tmp_path, port=port)
    with pytest.raises(ServisHatasi, match="port"):
        yukle(tanim)


@pytest.mark.parametrize("argv", [[], "cor start", [1, 2], ["", "cor"]])
def test_baslat_gecersiz(tmp_path, argv):
    """baslat bos olmayan, yalniz metin ogelerinden olusan bir argv listesi olmali."""
    tanim = _tek(tmp_path, baslat=argv)
    with pytest.raises(ServisHatasi, match="baslat"):
        yukle(tanim)


def test_durdur_gereksiz_argv(tmp_path):
    """durdur verilirse ayni argv kuralina uyar."""
    tanim = _tek(tmp_path, durdur="cor stop")
    with pytest.raises(ServisHatasi, match="durdur"):
        yukle(tanim)


def test_cwd_metin_olmali(tmp_path):
    """cwd bos metin veya sayi olamaz."""
    for bozuk in ("", 5):
        tanim = _tek(tmp_path, cwd=bozuk)
        with pytest.raises(ServisHatasi, match="cwd"):
            yukle(tanim)


def test_bekle_sn_negatif_olmaz(tmp_path):
    """bekle_sn negatif olamaz."""
    for bozuk in (-1, "20", True):
        tanim = _tek(tmp_path, bekle_sn=bozuk)
        with pytest.raises(ServisHatasi, match="bekle_sn"):
            yukle(tanim)


def test_servis_tablosu_tablo_olmali(tmp_path):
    """[servis.<ad>] bir tablo olmali."""
    tanim = _tek(tmp_path)
    tanim.write_text('[servis.tek]\nport = 9001\n', encoding="utf-8")
    with pytest.raises(ServisHatasi):
        yukle(tanim)


def test_saglik_url_yerel_adrese_gider(tmp_path):
    """saglik_url yalniz http(s)://127.0.0.1|localhost olabilir -- dis aga cikamaz."""
    tanim = _tek(tmp_path, saglik_url="http://127.0.0.1:9001/health")
    assert yukle(tanim)["tek"].saglik_url == "http://127.0.0.1:9001/health"


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/health",
        "https://10.0.0.5/health",
        "ftp://127.0.0.1/health",
        "127.0.0.1:9001",
        "",
        5,
    ],
)
def test_saglik_url_gecersiz(tmp_path, url):
    """Diger adresler reddedilir (yerel yigin araci dis aga cikmaz)."""
    tanim = _tek(tmp_path, saglik_url=url)
    with pytest.raises(ServisHatasi, match="saglik_url"):
        yukle(tanim)


@pytest.mark.parametrize("ad", ["", "..", "../kacis", "a/b", "a\\b"])
def test_servis_adi_yol_olamaz(tmp_path, ad):
    """Ad, dosya yoluna donusmemeli (pid/log dosyasi kacisina karsi).

    Baslik TOML literal tirnakla yazilir: `\\b` kacisi backspace'e donusmesin.
    """
    tanim = tmp_path / "servisler.toml"
    tanim.write_text(f"[servis.'{ad}']\nport = 9001\nbaslat = [\"x\"]\n", encoding="utf-8")
    with pytest.raises(ServisHatasi, match="gecersiz servis adi"):
        yukle(tanim)


# --------------------------------------------------------------------------
# dosya hatalari
# --------------------------------------------------------------------------


def test_bozuk_toml_hata(tmp_path):
    """Bozuk TOML ServisHatasi olur (CLI bunu 'Hata: ...' ile, cikis 2 yapar)."""
    tanim = tanim_yaz(tmp_path / "servisler.toml", None, govde="[servis.tek\nport = = 1\n")
    with pytest.raises(ServisHatasi, match="bozuk TOML"):
        yukle(tanim)


def test_bozuk_toml_hatasi_toml_denetleyicisinden_gelir(tmp_path):
    """Bozuk TOML icin ham tomllib.TOMLDecodeError mesaji korunur."""
    import tomllib

    tanim = tanim_yaz(tmp_path / "servisler.toml", None, govde="port = = 1\n")
    with pytest.raises(tomllib.TOMLDecodeError):
        tomllib.loads(tanim.read_text(encoding="utf-8"))
    with pytest.raises(ServisHatasi):
        yukle(tanim)


def test_servis_tablosu_yok(tmp_path):
    """[servis] tablosu olmayan dosya reddedilir."""
    tanim = tanim_yaz(tmp_path / "servisler.toml", None, govde='[baska]\nx = 1\n')
    with pytest.raises(ServisHatasi, match=r"\[servis\]"):
        yukle(tanim)


def test_hic_servis_yok(tmp_path):
    """[servis] bos olabilir ama o zaman tanim yok sayilir."""
    tanim = tanim_yaz(tmp_path / "servisler.toml", None, govde="[servis]\n")
    with pytest.raises(ServisHatasi, match="hic servis yok"):
        yukle(tanim)


def test_olmayan_tanim_dosyasi(tmp_path):
    """Yoksa 'servisler.toml.ornek'i kopyalayin" yonlendirmesi verilir."""
    with pytest.raises(ServisHatasi) as exc:
        yukle(tmp_path / "yok.toml")
    assert "servisler.toml.ornek" in str(exc.value)


def test_tanim_dizini_olamaz(tmp_path):
    """Dizin verilirse okunamaz sayilir."""
    dizin = tmp_path / "bir-dizin"
    dizin.mkdir()
    with pytest.raises(ServisHatasi, match="dizin"):
        yukle(dizin)


# --------------------------------------------------------------------------
# tanim yolu onceligi
# --------------------------------------------------------------------------


def test_tanim_yolu_verilen_arguman_once(tmp_path, monkeypatch):
    """--tanim, SERVIS_TANIM ve varsayilanin hepsini yener."""
    monkeypatch.setenv("SERVIS_TANIM", str(tmp_path / "env.toml"))
    verilen = tmp_path / "verilen.toml"
    assert tanim_yolu(str(verilen)) == verilen


def test_tanim_yolu_env(tmp_path, monkeypatch):
    """Verilmezse SERVIS_TANIM kullanilir."""
    env = tmp_path / "env.toml"
    monkeypatch.setenv("SERVIS_TANIM", str(env))
    assert tanim_yolu() == env


def test_tanim_yolu_ev_altinda(tmp_path, monkeypatch):
    """Ne verilmez ne env varsa ~/.servis/servisler.toml."""
    monkeypatch.delenv("SERVIS_TANIM", raising=False)
    ev = tmp_path / "ev"
    ev.mkdir()
    monkeypatch.setenv("HOME", str(ev))
    monkeypatch.setenv("USERPROFILE", str(ev))
    assert tanim_yolu() == ev / ".servis" / "servisler.toml"


def test_servis_tanim_ortam_degiskeni_ile_yuklenir(tmp_path, monkeypatch):
    """SERVIS_TANIM gercekten yukleme yolunu degistirir."""
    tanim = _tek(tmp_path)
    monkeypatch.setenv("SERVIS_TANIM", str(tanim))
    assert yukle()["tek"].port == 9001


# --------------------------------------------------------------------------
# ad secimi
# --------------------------------------------------------------------------


def test_ad_verilmezse_tumu_alfabetik(tmp_path):
    """Ad verilmezse tum tanimli servisler alfabetik sirada gelir."""
    tanim = tanim_yaz(
        tmp_path / "servisler.toml",
        {
            "zeta": {"port": 9003, "baslat": ["x"]},
            "alfa": {"port": 9001, "baslat": ["x"]},
            "mid": {"port": 9002, "baslat": ["x"]},
        },
    )
    assert [s.ad for s in sec(yukle(tanim), [])] == ["alfa", "mid", "zeta"]


def test_ad_verilirse_sadece_o(tmp_path):
    """Verilen adlar sirasi korunur, tanim disindakilere hata verilir."""
    tanim = tanim_yaz(
        tmp_path / "servisler.toml",
        {
            "alfa": {"port": 9001, "baslat": ["x"]},
            "mid": {"port": 9002, "baslat": ["x"]},
        },
    )
    assert [s.ad for s in sec(yukle(tanim), ["mid"])] == ["mid"]


def test_tanimsiz_ad_hata(tmp_path):
    """Olmayan servis adi hatadir; tanimli adlar hatada listelenir."""
    tanim = _tek(tmp_path)
    with pytest.raises(ServisHatasi) as exc:
        sec(yukle(tanim), ["tek", "yok"])
    assert "yok" in str(exc.value)
    assert "tek" in str(exc.value)


def test_ayni_ad_tekrarlanmaz(tmp_path):
    """Ayni ad birden fazla verilirse tekrar edilmez."""
    tanim = _tek(tmp_path)
    assert [s.ad for s in sec(yukle(tanim), ["tek", "tek"])] == ["tek"]