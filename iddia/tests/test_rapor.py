"""rapor: tablo bicimi, ozet satiri, JSON govdesi.

Bu modul YAZMAZ; testler de yazma denemez (salt-okunur).
"""

from __future__ import annotations

from pathlib import Path

from iddia.rapor import json_uret, tablo


def _bulgu(tur="test-sayisi", iddia="1000 test", gercek="10 test", readme="README.md:3"):
    return {"repo": "/projeler/harita", "readme": readme, "tur": tur,
            "iddia": iddia, "gercek": gercek}


def test_bos_liste_mesaj_verir():
    """Bulgu yokken acik bir mesaj yazilir (bos tablo basilmaz)."""
    assert "bulgu yok" in tablo([])


def test_tablo_baslik_ve_satirlar():
    """Tablo basligi + her bulgu icin bir satir icerir."""
    cikti = tablo([_bulgu()])
    satirlar = cikti.splitlines()
    assert satirlar[0].split() == ["repo", "readme", "tur", "iddia", "gercek"]
    assert "harita" in satirlar[1]  # repo adi kisaltilir
    assert "1000 test" in satirlar[1]
    assert "10 test" in satirlar[1]


def test_ozet_satiri_turleri_sayar():
    """Ozet satiri tur basina adet sayar."""
    bulgular = [_bulgu(), _bulgu(tur="dosya-yolu", iddia="a.py"), _bulgu(tur="dosya-yolu", iddia="b.py")]
    ozet = tablo(bulgular).splitlines()[-1]
    assert "3 bulgu" in ozet
    assert "2 dosya-yolu" in ozet
    assert "1 test-sayisi" in ozet


def test_json_uret_govdesi():
    """JSON govdesi surum/sayim/bulgular icerir."""
    veri = json_uret([_bulgu()], [Path("/projeler/harita")])
    assert veri["surum"] == 1
    assert veri["bulgu_sayisi"] == 1
    assert veri["repo_sayisi"] == 1
    assert veri["tur_sayimi"] == {"test-sayisi": 1}
    assert veri["bulgular"][0]["tur"] == "test-sayisi"


def test_json_uret_bos():
    """Bos bulgu listesi de gecerli bir govde uretir."""
    veri = json_uret([], [Path("/a"), Path("/b")])
    assert veri["bulgu_sayisi"] == 0
    assert veri["repo_sayisi"] == 2
    assert veri["tur_sayimi"] == {}


def test_uzun_metin_satiri_bozmaz():
    """Cok uzun iddia metni satiri tabloyu bozmaz (sutun genisligi hesaplanir)."""
    cikti = tablo([_bulgu(iddia="x" * 300)])
    assert len(cikti.splitlines()) == 3  # baslik + 1 bulgu + ozet