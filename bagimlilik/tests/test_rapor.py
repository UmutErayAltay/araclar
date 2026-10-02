"""rapor: JSON kaydet/yukle round-trip, atomik yazim, tablo ciktisi.

BAGIMLILIK_DIR gecici dizine yonlendirilir; kullanici ~/.bagimlilik'i ezilmez.
"""

from __future__ import annotations

import json
import os

import pytest
from conftest import fixture_yukle

from bagimlilik import rapor
from bagimlilik.denetim import Acik, Denetim, RepoSonuc, parse_npm_audit, parse_pip_audit


def ornek_sonuclar() -> list[RepoSonuc]:
    """Uc durumu da iceren sonuc listesi: acikli pip, acikli npm, kilit-yok."""
    pip_sayilar, pip_aciklar = parse_pip_audit(fixture_yukle("pip_audit_acikli"))
    npm_sayilar, npm_aciklar = parse_npm_audit(fixture_yukle("npm_audit_acikli"))
    return [
        RepoSonuc(
            yol="/tmp/harita",
            ad="harita",
            denetimler=[
                Denetim("pip", "requirements.txt", "acik", sayilar=pip_sayilar,
                        toplam=len(pip_aciklar), aciklar=pip_aciklar),
                Denetim("npm", "package.json", "denetlenemedi", neden="kilit-yok",
                        ayrinti="package-lock.json yok"),
            ],
            desteklenmeyen=["go.mod"],
        ),
        RepoSonuc(
            yol="/tmp/kule",
            ad="kule",
            denetimler=[
                Denetim("npm", "package.json", "acik", sayilar=npm_sayilar, toplam=69,
                        aciklar=npm_aciklar),
            ],
        ),
    ]


# --------------------------------------------------------------------------
# kaydet / yukle
# --------------------------------------------------------------------------


def test_kaydet_yukle_round_trip(rapor_dizini):
    """kaydet -> yukle ayni veriyi dondurur (rapor kaybi yok)."""
    kaydetilen = rapor.kaydet(ornek_sonuclar())
    veri = rapor.yukle()
    assert veri is not None
    assert veri["surum"] == rapor.SURUM == 1
    assert [r["ad"] for r in veri["repolar"]] == ["harita", "kule"]
    ilk = veri["repolar"][0]
    assert ilk["denetimler"][0]["toplam"] == 9
    assert len(ilk["denetimler"][0]["aciklar"]) == 9
    assert ilk["desteklenmeyen"] == ["go.mod"]
    assert ilk["denetimler"][1]["neden"] == "kilit-yok"
    assert kaydetilen == rapor_dizini / "son.json"


def test_sema_anahtarlari(rapor_dizini):
    """Rapor semasi tam olarak: surum(1) / tarih(iso) / repolar."""
    rapor.kaydet(ornek_sonuclar())
    veri = json.loads((rapor_dizini / "son.json").read_text(encoding="utf-8"))
    assert set(veri) == {"surum", "tarih", "repolar"}
    assert veri["surum"] == 1
    from datetime import datetime

    assert datetime.fromisoformat(veri["tarih"]).tzinfo is not None, "tarih timezone'lu olmali"


def test_bos_liste_de_kaydedilir(rapor_dizini):
    """Sonuc yoksa da rapor semasi gecerli (repolar: [])."""
    rapor.kaydet([])
    assert rapor.yukle()["repolar"] == []


def test_yukle_yoksa_none(rapor_dizini):
    """Rapor dosyasi yoksa yukle None doner (hata firlatmaz)."""
    assert rapor.yukle() is None


def test_yukle_bozuk_json_none(rapor_dizini):
    """Bozuk rapor dosyasi yukle'de None: CLI 'rapor bulunamadi' der, cokmez."""
    rapor_dizini.mkdir(parents=True, exist_ok=True)
    (rapor_dizini / "son.json").write_text("{bozuk", encoding="utf-8")
    assert rapor.yukle() is None


def test_ust_dizin_yoksa_olusur(rapor_dizini):
    """BAGIMLILIK_DIR henuz yoksa kaydet kendisi olusturur."""
    assert not rapor_dizini.exists()
    rapor.kaydet(ornek_sonuclar())
    assert (rapor_dizini / "son.json").is_file()


# --------------------------------------------------------------------------
# Atomiklik
# --------------------------------------------------------------------------


def test_yazim_atomik_ara_dosya_birakmaz(rapor_dizini):
    """kaydet sonrasi dizinde SADECE son.json var: gecici .tmp dosyasi kalmaz."""
    rapor.kaydet(ornek_sonuclar())
    assert sorted(p.name for p in rapor_dizini.iterdir()) == ["son.json"]


def test_ikinci_yazim_eskiyi_degistirir_ara_dosya_yok(rapor_dizini):
    """Ust uste kaydet: dosya sayisi sabit kalir, gecici sizinti olmaz."""
    rapor.kaydet(ornek_sonuclar())
    rapor.kaydet([RepoSonuc(yol="/x", ad="x")])
    assert sorted(p.name for p in rapor_dizini.iterdir()) == ["son.json"]
    assert [r["ad"] for r in rapor.yukle()["repolar"]] == ["x"]


def test_hata_durumunda_ara_dosya_silinir(rapor_dizini, monkeypatch):
    """os.replace patlarsa gecici dosya SILINIR (yarim rapor birakmaz)."""
    rapor_dizini.mkdir(parents=True, exist_ok=True)

    def patla(*_a, **_k):
        raise OSError("disk dolu")

    monkeypatch.setattr(os, "replace", patla)
    with pytest.raises(OSError):
        rapor.kaydet(ornek_sonuclar())
    assert list(rapor_dizini.iterdir()) == []


def test_explicit_yol_dizini_ezmez(rapor_dizini, tmp_path):
    """kaydet(yol=...) BAGIMLILIK_DIR'u yok sayar ve o yola yazar."""
    ozel = tmp_path / "ozel" / "rapor.json"
    rapor.kaydet(ornek_sonuclar(), ozel)
    assert ozel.is_file() and not rapor_dizini.exists()
    assert rapor.yukle(ozel)["repolar"][0]["ad"] == "harita"


# --------------------------------------------------------------------------
# Tablo ciktisi
# --------------------------------------------------------------------------


def test_tablo_acikli_satirda_ilk_uc_acik():
    """'acik' denetiminde aciklar listenin TUMU raporda durur, tablo en fazla 3 gosterir.

    Fixture'da tek denetim icin 9 acik vardir; tabloda 3 satir cikar.
    """
    sayilar, aciklar = parse_pip_audit(fixture_yukle("pip_audit_acikli"))
    metin = rapor.tablo([RepoSonuc(yol="/x", ad="x", denetimler=[
        Denetim("pip", "requirements.txt", "acik", sayilar=sayilar, toplam=9, aciklar=aciklar)])])
    liste = [ln for ln in metin.splitlines() if ln.startswith("    - ")]
    assert len(liste) == 3, "9 aciktan tam 3 gosterilmeli"
    assert liste[0] == "    - flask 0.12 [bilinmiyor] CVE-2019-1010083 -> 1.0"
    assert liste[1] == "    - flask 0.12 [bilinmiyor] CVE-2018-1000656 -> 0.12.3"
    assert liste[2] == "    - requests 2.19.0 [bilinmiyor] CVE-2018-18074 -> 2.20.0"


def test_tablo_her_acikli_denetim_icin_uc_satir():
    """Birden fazla acikli denetim oldugunda her biri kendi ilk 3 acikini gosterir."""
    metin = rapor.tablo(ornek_sonuclar())
    assert len([ln for ln in metin.splitlines() if ln.startswith("    - ")]) == 6  # 2 x 3
    assert any("GHSA-fv7c-fp4j-7gwp -> mevcut" in ln for ln in metin.splitlines())


def test_tablo_duzeltmesi_olmayanda_metin():
    """Duzeltme sürümü olmayan acik 'duzeltme yok' ile biter (sessiz bos yol yok)."""
    metin = rapor.tablo([RepoSonuc(yol="/x", ad="x", denetimler=[
        Denetim("npm", "package.json", "acik", toplam=1, sayilar={},
                aciklar=[Acik("x", "", "GHSA-1", None, "yuksek")])])])
    assert "-> duzeltme yok" in metin


def test_tablo_denetlenemedi_satirinda_neden_gorunur(rapor_dizini):
    """'denetlenemedi' satiri nedeni parantez icinde gosterir."""
    metin = rapor.tablo(ornek_sonuclar())
    assert "denetlenemedi(kilit-yok)" in metin


def test_tablo_ozet_satiri_sayilari(rapor_dizini):
    """Ozet satiri: repo/adet sayilarini Turkce etiketlerle verir."""
    metin = rapor.tablo(ornek_sonuclar())
    ozet = [ln for ln in metin.splitlines() if ln.startswith("ozet:")][0]
    assert "2 repo -> 0 temiz, 2 acikli, 0 denetlenemedi" in ozet
    assert "K/Y/O/D = kritik/yuksek/orta/dusuk" in ozet


def test_tablo_ozet_denetlenemedi_sayimi(rapor_dizini):
    """Hepsi denetlenemedi olan repo ozette 'denetlenemedi' sayilir, 'temiz' DEGIL."""
    sonuclar = [RepoSonuc(yol="/x", ad="x", denetimler=[Denetim("npm", "package.json", "denetlenemedi", neden="arac-yok")])]
    ozet = [ln for ln in rapor.tablo(sonuclar).splitlines() if ln.startswith("ozet:")][0]
    assert "1 repo -> 0 temiz, 0 acikli, 1 denetlenemedi" in ozet


def test_tablo_pip_siddeti_sorulur():
    """pip-audit siddet vermez: acikli pip satirinda K/Y/O/D '?' isareti, toplam gercek sayi."""
    sayilar, aciklar = parse_pip_audit(fixture_yukle("pip_audit_acikli"))
    metin = rapor.tablo([RepoSonuc(yol="/x", ad="x", denetimler=[
        Denetim("pip", "requirements.txt", "acik", sayilar=sayilar, toplam=9, aciklar=aciklar)])])
    satir = [ln for ln in metin.splitlines() if ln.startswith("x ")][0]
    alanlar = satir.split()
    assert alanlar[3:7] == ["?", "?", "?", "?"], satir
    assert alanlar[7] == "9", satir


def test_tablo_npm_siddetleri_gosterilir():
    """npm siddeti var: K/Y/O/D sayilarla dolar, '?' cikmaz."""
    sayilar, aciklar = parse_npm_audit(fixture_yukle("npm_audit_acikli"))
    metin = rapor.tablo([RepoSonuc(yol="/x", ad="x", denetimler=[
        Denetim("npm", "package.json", "acik", sayilar=sayilar, toplam=69, aciklar=aciklar)])])
    satir = [ln for ln in metin.splitlines() if ln.startswith("x ")][0]
    alanlar = satir.split()
    assert alanlar[3:7] == ["3", "35", "17", "14"], satir
    assert alanlar[7] == "69", satir


def test_tablo_bos_girdi_calisir():
    """Sonuc yokken tablo yine baslik + ozet satiri uretir (IndexError yok)."""
    metin = rapor.tablo([])
    assert metin.splitlines()[0].split() == ["repo", "kaynak", "durum", "K", "Y", "O", "D", "toplam"]
    assert "0 repo -> 0 temiz, 0 acikli, 0 denetlenemedi" in metin


def test_tablo_kolonlari_hizali():
    """Baslik ve veri satirlari ayni kolon genisliklerini paylasir (kolon kaymasi yok).

    Her veri satiri iki boslukla ayrilmis tam 8 alan icerir ve alan baslangic
    sutunlari baslikla birebir ayni indekslerdedir.
    """
    import re

    metin = rapor.tablo(ornek_sonuclar())
    satirlar = [ln for ln in metin.splitlines() if not ln.startswith("    - ") and not ln.startswith("ozet:")]
    konumlar = [[m.start() for m in re.finditer(r"\S+", ln)] for ln in satirlar]
    assert all(len(k) == 8 for k in konumlar), [ln.split() for ln in satirlar]
    assert konumlar[0] == konumlar[1] == konumlar[2] == konumlar[3]
    assert satirlar[0].split() == ["repo", "kaynak", "durum", "K", "Y", "O", "D", "toplam"]
