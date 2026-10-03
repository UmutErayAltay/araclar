"""rapor: DEVTEMIZLE_DIR, atomik JSON kaydet/yukle, boyut bicimi, tablo ve sil ozeti.

DEVTEMIZLE_DIR gecici dizine yonlendirilir; kullanici dizini olusturulmaz/ezilmez.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
from conftest import GUN

from devtemizle import rapor


def _iso(gun_once: float, simdi: float) -> str:
    return datetime.fromtimestamp(simdi - gun_once * GUN, timezone.utc).isoformat(
        timespec="seconds"
    )


def ornek_adaylar(simdi: float | None = None) -> list[dict]:
    """Uc durumu da iceren aday listesi: normal, atlanan (baglanti), buyuk.

    Bicim tara() ciktisiyla birebir ayni (son_erisim ISO metin, atlandi str|None).
    """
    simdi = time.time() if simdi is None else simdi
    return [
        {
            "repo": "/tmp/harita",
            "yol": "/tmp/harita/node_modules",
            "tur": "node_modules",
            "boyut": 1536,
            "son_erisim": _iso(30.0, simdi),
            "yas_gun": 30.0,
            "atlandi": None,
        },
        {
            "repo": "/tmp/kule",
            "yol": "/tmp/kule/node_modules",
            "tur": "node_modules",
            "boyut": 0,
            "son_erisim": _iso(2.0, simdi),
            "yas_gun": 2.0,
            "atlandi": "baglanti",
        },
        {
            "repo": "/tmp/kule",
            "yol": "/tmp/kule/.venv",
            "tur": ".venv",
            "boyut": 5 * 1024 * 1024,
            "son_erisim": _iso(40.0, simdi),
            "yas_gun": 40.0,
            "atlandi": "pyvenv-yok",
        },
    ]


def ornek_sonuc(simdi: float | None = None) -> dict:
    """sil() ciktisi biciminde ornek sonuc (kayitlar {yol, neden} sozlugu)."""
    simdi = time.time() if simdi is None else simdi
    adaylar = ornek_adaylar(simdi)
    return {
        "silinecek": [adaylar[0], adaylar[2]],
        "silindi": [adaylar[0]],
        "silinemedi": [{"yol": "/tmp/kule/x", "neden": "kilitli: izin yok"}],
        "atlanan": [
            {"yol": adaylar[1]["yol"], "neden": "baglanti"},
            {"yol": adaylar[2]["yol"], "neden": "yeni"},
        ],
        "bosalan_bayt": 1536,
    }


# --------------------------------------------------------------------------
# olustur / kaydet / yukle
# --------------------------------------------------------------------------


def test_olustur_sema_anahtarlari():
    """olustur tam olarak surum/tarih/adaylar dondurur."""
    veri = rapor.olustur(ornek_adaylar(), simdi=time.time())
    assert set(veri) == {"surum", "tarih", "adaylar"}
    assert veri["surum"] == rapor.SURUM == 1
    assert len(veri["adaylar"]) == 3


def test_olustur_tarih_iso_ve_timezone():
    """Rapor tarihi ISO-8601 ve timezone'lu (raporlar kararlilastirilabilir)."""
    from datetime import datetime

    veri = rapor.olustur(ornek_adaylar(), simdi=time.time())
    assert datetime.fromisoformat(veri["tarih"]).tzinfo is not None


def test_olustur_adalari_oldugu_gibi_korur():
    """olustur aday kartlarini DEGISTIRMEZ (rapor kaynak verinin aynisini tasir)."""
    adaylar = ornek_adaylar()
    veri = rapor.olustur(adaylar, simdi=time.time())
    assert veri["adaylar"] == adaylar


def test_olustur_bos_aday_listesi():
    """Aday yoksa rapor yine gecerli sema (adaylar: [])."""
    veri = rapor.olustur([], simdi=time.time())
    assert veri["adaylar"] == []


def test_kaydet_yukle_round_trip(rapor_dizini):
    """kaydet -> yukle ayni veriyi dondurur (rapor kaybi yok)."""
    kaydedilen = rapor.kaydet(rapor.olustur(ornek_adaylar()))
    veri = rapor.yukle()
    assert veri is not None
    assert veri["surum"] == 1
    assert len(veri["adaylar"]) == 3
    assert veri["adaylar"][0]["tur"] == "node_modules"
    assert veri["adaylar"][1]["atlandi"] == "baglanti"
    assert kaydedilen == rapor_dizini / "son.json"


def test_kaydet_devtemizle_dir_env_ile_belirlenir(rapor_dizini):
    """Rapor DEVTEMIZLE_DIR/son.json'a yazilir; kullanici dizini olusturulmaz."""
    rapor.kaydet(rapor.olustur(ornek_adaylar()))
    assert (rapor_dizini / "son.json").is_file()


def test_kaydet_ust_dizin_yoksa_olusur(rapor_dizini):
    """DEVTEMIZLE_DIR henuz yoksa kaydet kendisi olusturur."""
    assert not rapor_dizini.exists()
    rapor.kaydet(rapor.olustur(ornek_adaylar()))
    assert (rapor_dizini / "son.json").is_file()


def test_yukle_dosya_yoksa_none(rapor_dizini):
    """Rapor dosyasi yoksa yukle None doner (hata firlatmaz)."""
    assert rapor.yukle() is None


def test_yukle_bozuk_json_none(rapor_dizini):
    """Bozuk rapor dosyasi yukle'de None: CLI 'rapor bulunamadi' der, cokmez."""
    rapor_dizini.mkdir(parents=True, exist_ok=True)
    (rapor_dizini / "son.json").write_text("{bozuk", encoding="utf-8")
    assert rapor.yukle() is None


def test_yazim_atomik_ara_dosya_birakmaz(rapor_dizini):
    """kaydet sonrasi dizinde SADECE son.json var: gecici .tmp dosyasi kalmaz."""
    rapor.kaydet(rapor.olustur(ornek_adaylar()))
    assert sorted(p.name for p in rapor_dizini.iterdir()) == ["son.json"]


def test_ikinci_yazim_eskiyi_degistirir_ara_dosya_yok(rapor_dizini):
    """Ust uste kaydet: dosya sayisi sabit kalir, gecici sizinti olmaz."""
    rapor.kaydet(rapor.olustur(ornek_adaylar()))
    rapor.kaydet(rapor.olustur(ornek_adaylar()[:1]))
    assert sorted(p.name for p in rapor_dizini.iterdir()) == ["son.json"]
    assert len(rapor.yukle()["adaylar"]) == 1


def test_kaydet_yarim_rapor_birakmaz(rapor_dizini, monkeypatch):
    """Yazma basarisiz olursa gecici dosya SILINIR ve eski rapor BOZULMAZ.

    Bu, atomikligi ozetleyen asil test: kaydet -> eski rapor okunabilir kalir,
    dizinde .tmp sizintisi olmaz. Dogrudan (atomik olmayan) yazimda yarim
    JSON kalirdi.
    """
    rapor_dizini.mkdir(parents=True, exist_ok=True)
    (rapor_dizini / "son.json").write_text('{"surum": 1, "onceki": true}', encoding="utf-8")
    def patla(*_a, **_k):
        raise OSError("disk doldu")

    monkeypatch.setattr(rapor.os, "replace", patla)
    with pytest.raises(OSError):
        rapor.kaydet(rapor.olustur(ornek_adaylar()))
    assert sorted(p.name for p in rapor_dizini.iterdir()) == ["son.json"]
    assert json.loads((rapor_dizini / "son.json").read_text(encoding="utf-8"))["onceki"] is True


def test_kaydet_json_okunabilir_yazar(rapor_dizini):
    """son.json gecerli JSON'dur (rapor insan/CLI tarafindan tekrar okunur)."""
    rapor.kaydet(rapor.olustur(ornek_adaylar()))
    veri = json.loads((rapor_dizini / "son.json").read_text(encoding="utf-8"))
    assert veri["adaylar"][0]["yol"] == "/tmp/harita/node_modules"


# --------------------------------------------------------------------------
# boyut_yaz
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bayt, beklenen",
    [
        (0, "0 B"),
        (1, "1 B"),
        (512, "512 B"),
        (1023, "1023 B"),
        (1024, "1.0 KB"),
        (1536, "1.5 KB"),
        (1024 * 1024, "1.0 MB"),
        (5 * 1024 * 1024, "5.0 MB"),
        (int(1.5 * 1024**3), "1.5 GB"),
        (3 * 1024**3, "3.0 GB"),
    ],
)
def test_boyut_yaz_birimleri(bayt, beklenen):
    """B/KB/MB/GB: 1024 tabani, tek ondalik (0 B tam sayi)."""
    assert rapor.boyut_yaz(bayt) == beklenen


def test_boyut_yaz_tek_ondalik():
    """KB/MB/GB degerleri tek ondalikli yazilir (sutun hizasi icin)."""
    assert rapor.boyut_yaz(1234567) == "1.2 MB"
    assert rapor.boyut_yaz(int(2.34 * 1024**3)) == "2.3 GB"


# --------------------------------------------------------------------------
# tablo
# --------------------------------------------------------------------------


def test_tablo_ozet_satiri_ada_y_sayisi_ve_atlandi():
    """Ozet satiri 'N aday' ve 'atlandi' sayisini verir."""
    metin = rapor.tablo(rapor.olustur(ornek_adaylar(), simdi=time.time()))
    assert "3 aday" in metin, metin
    assert "atlandi" in metin, metin


def test_tablo_ozet_satiri_atlandi_sayisini_yazar():
    """Ozet satiri atlanan aday SAYISINI verir (3 aday, 2 atlandi)."""
    metin = rapor.tablo(rapor.olustur(ornek_adaylar(), simdi=time.time()))
    ozet = [ln for ln in metin.splitlines() if ln.startswith("ozet:")][0]
    assert ozet.endswith("2 atlandi"), ozet


def test_tablo_bos_girdi_calisir():
    """Aday yokken tablo yine calisir (IndexError yok), ozet '0 aday' der."""
    metin = rapor.tablo(rapor.olustur([], simdi=time.time()))
    assert "0 aday" in metin, metin


def test_tablo_her_aday_icin_satir_yazar():
    """Her aday icin bir satir olur (3 aday -> baslik + 3 satir + ozet).

    Tablonun ilk sutunu aday KLASOR adidir (node_modules/.venv), repo adi degil:
    ayni tur birden fazla repoda olsa da satirlar ayirt edilebilir kalsin diye
    daraltilmis ad gosterilir.
    """
    adaylar = ornek_adaylar()
    metin = rapor.tablo(rapor.olustur(adaylar, simdi=time.time()))
    satirlar = metin.splitlines()
    assert len(satirlar) == 5, satirlar  # baslik + 3 aday + ozet
    assert satirlar[0].split() == ["repo", "tur", "boyut", "yas(gun)", "durum"]
    for aday in adaylar:
        assert Path(aday["yol"]).name in metin, aday


def test_tablo_boyut_bicimi_kullanir():
    """Tablo ham bayt yerine boyut_yaz bicimini gosterir (insan okunur)."""
    metin = rapor.tablo(rapor.olustur(ornek_adaylar(), simdi=time.time()))
    assert "1.5 KB" in metin, metin
    assert "5.0 MB" in metin, metin


def test_tablo_atlandi_nedeni_gorunur():
    """Atlanan adayin nedeni satirda gorunur (kullanici ne olmadigini anlar)."""
    metin = rapor.tablo(rapor.olustur(ornek_adaylar(), simdi=time.time()))
    assert "baglanti" in metin and "pyvenv-yok" in metin, metin


def test_tablo_yas_gun_gorunur():
    """Yas gun sutunu raporda gorunur (silme karari yasa bagli)."""
    metin = rapor.tablo(rapor.olustur(ornek_adaylar(), simdi=time.time()))
    assert "yas" in metin.lower() or "gün" in metin.lower(), metin
    assert "30" in metin, metin


# --------------------------------------------------------------------------
# sil_ozeti
# --------------------------------------------------------------------------


def test_sil_ozeti_kuru_calistirma_uyari_verir():
    """Kuru calistirma ozeti 'KURU CALISTIRMA' der ve --uygula isaretini gosterir.

    Bu satir kullaniciya diskte HICBIR seyin silinmedigini ve nasil
    silinecegini bildirir; sessizce silmis gibi gorunmemelidir.
    """
    metin = rapor.sil_ozeti(ornek_sonuc(), False)
    assert "KURU CALISTIRMA" in metin, metin
    assert "--uygula" in metin, metin


def test_sil_ozeti_uygula_silindi_diyor():
    """Gercek silmede ozet 'silindi' sayisini bildirir (kuru calistirma uyarisi YOK)."""
    metin = rapor.sil_ozeti(ornek_sonuc(), True)
    assert "silindi" in metin, metin
    assert "KURU CALISTIRMA" not in metin, metin


def test_sil_ozeti_bosalan_bayt_bicimi_kullanir():
    """Bosalan bayt boyut_yaz ile yazilir (0 ise '0 B')."""
    metin = rapor.sil_ozeti(ornek_sonuc(), True)
    assert "1.5 KB" in metin, metin
    assert rapor.boyut_yaz(0) in rapor.sil_ozeti(
        {**ornek_sonuc(), "bosalan_bayt": 0}, True
    ), "sifir bayt yazimi eksik"

def test_tablo_repo_sutunu_repo_adini_gosterir():
    """Regresyon: 'repo' sutunu klasor adini degil repo adini yazar."""
    from devtemizle import rapor

    r = rapor.olustur([{"repo": "/tmp/harita", "yol": "/tmp/harita/node_modules",
                        "tur": "node_modules", "boyut": 10, "son_erisim": "2026-01-01T00:00:00+00:00",
                        "yas_gun": 9.0, "atlandi": None}], 0)
    satir = rapor.tablo(r).splitlines()[1].split()
    assert satir[0] == "harita"
