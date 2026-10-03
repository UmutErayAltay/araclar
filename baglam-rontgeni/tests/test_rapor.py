"""rapor: RONTGEN_DIR, gizlilik (metin sizmaz), atomik kaydet, tablo sirasi/ozeti.

RONTGEN_DIR gecici dizine yonlendirilir; kullanici dizini olusturulmaz/ezilmez.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path

import pytest
from conftest import dosya_agaci, kur, sahte_claude_dir

from baglam_rontgeni import kesif, rapor

GIZLI_METIN = "OZEL_GOVDE_METNINI_SIZDIRMA"


def _kalem(ad: str, acilis: int | None, *, cagrilinca: int | None = None, **ek) -> dict:
    return {
        "tur": ek.pop("tur", "skill"),
        "ad": ad,
        "kaynak": ek.pop("kaynak", f"/tmp/{ad}/SKILL.md"),
        "acilis_token": acilis,
        "cagrilinca_token": cagrilinca,
        "kapali": ek.pop("kapali", False),
        "olculemedi": ek.pop("olculemedi", False),
        **ek,
    }


def ornek_kalemler() -> list[dict]:
    """Uc kalem: buyuk skill, kucuk skill, olculemeyen MCP."""
    return [
        _kalem("kule:harita", 120, cagrilinca=800),
        _kalem("kule:kule-gelistirme", 30, cagrilinca=4000),
        _kalem("atlas", None, tur="mcp", olculemedi=True),
    ]


# --------------------------------------------------------------------------
# olustur
# --------------------------------------------------------------------------


def test_olustur_sema_anahtarlari():
    """olustur tam olarak surum/tarih/tahmin_notu/kalemler/toplam_acilis dondurur."""
    veri = rapor.olustur(ornek_kalemler(), simdi=time.time())
    assert set(veri) == {"surum", "tarih", "tahmin_notu", "kalemler", "toplam_acilis"}
    assert veri["surum"] == rapor.SURUM == 1


def test_olustur_tarih_iso_ve_timezone():
    """Rapor tarihi ISO-8601 ve timezone'lu (raporlar kararlilastirilabilir)."""
    veri = rapor.olustur(ornek_kalemler(), simdi=time.time())
    assert datetime.fromisoformat(veri["tarih"]).tzinfo is not None


def test_olustur_tahmin_notu_yazar():
    """Rapor her sayinin TAHMIN oldugunu basinda bildirir."""
    assert rapor.olustur([], simdi=time.time())["tahmin_notu"] == "karakter/4 tahmini"


def test_olustur_toplam_kapali_kalemleri_hesaba_katmaz():
    """Kapali skill toplam acilisa GIRMEZ (her oturum yuklenmiyor)."""
    kalemler = ornek_kalemler() + [_kalem("kule:eski", 500, kapali=True)]
    assert rapor.olustur(kalemler, simdi=time.time())["toplam_acilis"] == 150


def test_olustur_olculemeyen_toplami_bozmaz():
    """MCP gibi olculemeyen kalemler toplama 0 ekler (yok sayilir)."""
    veri = rapor.olustur(ornek_kalemler(), simdi=time.time())
    assert veri["toplam_acilis"] == 150


def test_olustur_bos_liste_calisir():
    """Kalem yoksa rapor yine gecerli sema (toplam 0)."""
    veri = rapor.olustur([], simdi=time.time())
    assert veri["kalemler"] == [] and veri["toplam_acilis"] == 0


def test_olustur_kalemleri_oldugu_gibi_korur():
    """olustur kalem kartlarini DEGISTIRMEZ (kapali isaretlari bozulmaz)."""
    kalemler = ornek_kalemler()
    rapor.olustur(kalemler, simdi=time.time())
    assert kalemler == ornek_kalemler()


# --------------------------------------------------------------------------
# kaydet / yukle
# --------------------------------------------------------------------------


def test_kaydet_rontgen_dir_env_ile_belirlenir(rapor_dizini):
    """Rapor RONTGEN_DIR/son.json'a yazilir; kullanici dizini olusturulmaz."""
    kaydedilen = rapor.kaydet(rapor.olustur(ornek_kalemler()))
    assert kaydedilen == rapor_dizini / "son.json"
    assert kaydedilen.is_file()


def test_kaydet_ust_dizin_yoksa_olusur(rapor_dizini):
    """RONTGEN_DIR henuz yoksa kaydet kendisi olusturur."""
    assert not rapor_dizini.exists()
    rapor.kaydet(rapor.olustur(ornek_kalemler()))
    assert (rapor_dizini / "son.json").is_file()


def test_kaydet_yukle_round_trip(rapor_dizini):
    """kaydet -> yukle ayni veriyi dondurur (rapor kaybi yok)."""
    rapor.kaydet(rapor.olustur(ornek_kalemler()))
    veri = rapor.yukle()
    assert veri is not None
    assert veri["surum"] == 1
    assert len(veri["kalemler"]) == 3
    assert veri["kalemler"][0]["ad"] == "kule:harita"


def test_yazim_atomik_ara_dosya_birakmaz(rapor_dizini):
    """kaydet sonrasi dizinde SADECE son.json var: gecici .tmp dosyasi kalmaz."""
    rapor.kaydet(rapor.olustur(ornek_kalemler()))
    assert dosya_agaci(rapor_dizini) == ["son.json"]


def test_ikinci_yazim_eskiyi_degistirir_ara_dosya_yok(rapor_dizini):
    """Ust uste kaydet: dosya sayisi sabit kalir, gecici sizinti olmaz."""
    rapor.kaydet(rapor.olustur(ornek_kalemler()))
    rapor.kaydet(rapor.olustur(ornek_kalemler()[:1]))
    assert dosya_agaci(rapor_dizini) == ["son.json"]
    assert len(rapor.yukle()["kalemler"]) == 1


def test_kaydet_hata_olursa_eski_rapor_bozulmaz(rapor_dizini, monkeypatch):
    """os.replace patlarsa gecici dosya SILINIR ve eski rapor BOZULMAZ (yarim JSON gorunmez)."""
    rapor_dizini.mkdir(parents=True, exist_ok=True)
    (rapor_dizini / "son.json").write_text('{"surum": 1, "onceki": true}', encoding="utf-8")

    def patla(*_a, **_k):
        raise OSError("disk doldu")

    monkeypatch.setattr(rapor.os, "replace", patla)
    with pytest.raises(OSError):
        rapor.kaydet(rapor.olustur(ornek_kalemler()))

    assert dosya_agaci(rapor_dizini) == ["son.json"]
    assert json.loads((rapor_dizini / "son.json").read_text(encoding="utf-8"))["onceki"] is True


def test_kaydet_json_okunabilir_yazar(rapor_dizini):
    """son.json gecerli JSON'dur (rapor `goster` tarafindan tekrar okunur)."""
    rapor.kaydet(rapor.olustur(ornek_kalemler()))
    veri = json.loads((rapor_dizini / "son.json").read_text(encoding="utf-8"))
    assert veri["kalemler"][0]["tur"] == "skill"


def test_yukle_dosya_yoksa_none(rapor_dizini):
    """Rapor dosyasi yoksa yukle None doner (hata firlatmaz)."""
    assert rapor.yukle() is None


def test_yukle_bozuk_json_none(rapor_dizini):
    """Bozuk rapor dosyasi yukle'de None: CLI 'rapor bulunamadi' der, cokmez."""
    rapor_dizini.mkdir(parents=True, exist_ok=True)
    (rapor_dizini / "son.json").write_text("{bozuk", encoding="utf-8")
    assert rapor.yukle() is None


# --------------------------------------------------------------------------
# gizlilik: kalemden metin tasINMAZ, tablo metni gostermez
# --------------------------------------------------------------------------


def test_gercek_skill_kalemi_rapora_metin_tasimaz(rapor_dizini, tmp_path):
    """Uctan uca gizlilik: kesif urettigi kalem, kaydedilen rapora skill METNI tasimaz.

    Govde ve description metni kesifte zaten SAYIYA cevrilir; rapor dosyasi
    yalniz ad + sayi + yol tasir. Tablo da ayni veriden beslenir.
    """
    icerik = f"---\nname: harita\ndescription: {GIZLI_METIN}\n---\n\n{GIZLI_METIN}\n"
    claude = sahte_claude_dir(tmp_path / "claude", skilller={"x": icerik})
    veri = rapor.olustur(kesif.skill_kalemleri(kur(), claude), simdi=time.time())
    yol = rapor.kaydet(veri)
    assert GIZLI_METIN not in yol.read_text(encoding="utf-8"), "skill metni rapora sizdi"
    assert "harita" in yol.read_text(encoding="utf-8")
    assert GIZLI_METIN not in rapor.tablo(veri)


def test_tablo_hucreleri_sadece_sayi_yazar():
    """Tablo sutunlari sabit; `acilis`/`cagrilinca` hucreleri SAYI, digerleri `-`.

    `acilis_token` sayi oldugu icin hucreye ham metin degil SAYI yazilir.
    """
    veri = rapor.olustur([_kalem("harita", 42, cagrilinca=8000)], simdi=time.time())
    satir = rapor.tablo(veri).splitlines()[1]
    assert satir.split() == ["harita", "skill", "42", "8000"], satir


def test_tablo_govde_metni_tasimaz():
    """Tablo govde metni TASIMAZ: yalniz ad, tur, sayilar ve durum gorunur."""
    veri = rapor.olustur([_kalem("harita", 42, cagrilinca=8000)], simdi=time.time())
    metin = rapor.tablo(veri)
    assert "8000" in metin and "harita" in metin
    assert len(metin.splitlines()) == 3, metin  # baslik + kalem + ozet


def test_kalem_yalniz_alan_tasiyor():
    """Kalem semasi sabit: tur/ad/kaynak/acilis/cagrilinca/kapali/olculemedi."""
    assert set(rapor.olustur(ornek_kalemler(), simdi=0)["kalemler"][0]) == {
        "tur",
        "ad",
        "kaynak",
        "acilis_token",
        "cagrilinca_token",
        "kapali",
        "olculemedi",
    }


# --------------------------------------------------------------------------
# gizlilik: ev dizini yolu `~` ile kisaltilir
# --------------------------------------------------------------------------


def test_kaynak_ev_dizini_tilde_kisaltilir(ev_isole):
    """Rapor `kaynak` alani ev dizini altindaysa `~` ile kisaltilir.

    Rapor paylasildiginda tam mutlak yol KULLANICI ADINI sizdirirdi.
    """
    yol = ev_isole / ".claude" / "skills" / "harita" / "SKILL.md"
    veri = rapor.olustur([_kalem("harita", 10, kaynak=str(yol))], simdi=time.time())
    assert veri["kalemler"][0]["kaynak"] == "~/.claude/skills/harita/SKILL.md"


def test_kaynak_kisaltma_ev_disi_yolda_calismaz(ev_isole):
    """Ev disindaki yol (ornegin gecici dizin) DEGISTIRILMEZ: yarim yol bozulmaz."""
    digeri = str(Path(os.environ.get("TEMP") or "C:/gecici") / "x" / "SKILL.md")
    veri = rapor.olustur([_kalem("harita", 10, kaynak=digeri)], simdi=time.time())
    assert veri["kalemler"][0]["kaynak"] == digeri


def test_kaynak_kisaltma_girdi_kalemleri_bozmaz(ev_isole):
    """olustur girdi kalem kartlarini DEGISTIRMEZ (sadece rapordaki kopyayi kisaltir)."""
    yol = ev_isole / ".claude" / "SKILL.md"
    kart = _kalem("harita", 10, kaynak=str(yol))
    rapor.olustur([kart], simdi=time.time())
    assert kart["kaynak"] == str(yol), "girdi kartı yerinde degisti"


def test_tablo_ad_kontrol_karakteri_temizlenir():
    """Ad sutunundaki ESC/DEL temizlenir: terminal satiri bozmaz."""
    veri = rapor.olustur([_kalem("har\x1b[2Jita\x7f", 10)], simdi=time.time())
    satir = rapor.tablo(veri).splitlines()[1]
    assert "\x1b" not in satir and "\x7f" not in satir, repr(satir)
    assert satir.startswith("har?[2Jita?"), repr(satir)


# --------------------------------------------------------------------------
# tablo
# --------------------------------------------------------------------------


def test_tablo_buyukten_kucuge_siralanir():
    """Satirlar acilis tokenina gore AZALAN sirada; en buyuk ilk satirda.

    Girdi KUCUKTEN BUYUGE verilir: siralama tablo icinde yapilir, girdi sirasi
    korunmaz (aksi halde bu test hicbir seyi yakalamaz).
    """
    karisik = [_kalem("kucuk", 10), _kalem("orta", 50), _kalem("buyuk", 900)]
    veri = rapor.olustur(karisik, simdi=time.time())
    sirali = [ln.split()[0] for ln in rapor.tablo(veri).splitlines()[1:-1]]
    assert sirali == ["buyuk", "orta", "kucuk"], sirali


def test_tablo_karisik_girdi_ayni_sirayi_verir():
    """`ornek_kalemler` zaten azalan sirada; tablo ayni sirayi korur."""
    veri = rapor.olustur(ornek_kalemler(), simdi=time.time())
    satirlar = rapor.tablo(veri).splitlines()
    assert satirlar[1].split()[0] == "kule:harita"
    assert satirlar[2].split()[0] == "kule:kule-gelistirme"


def test_tablo_basliklar_ve_sutunlar():
    """Basliklar ad/tur/acilis/cagrilinca/durum; her kalem icin bir satir olur."""
    metin = rapor.tablo(rapor.olustur(ornek_kalemler(), simdi=time.time()))
    satirlar = metin.splitlines()
    assert satirlar[0].split() == ["ad", "tur", "acilis", "cagrilinca", "durum"]
    assert len(satirlar) == 5, satirlar  # baslik + 3 kalem + ozet


def test_tablo_ilk_n_ile_kesilir():
    """`ilk` kadar satir gosterilir, kalan sayisi ozette belirtilir."""
    kalemler = [_kalem(f"s{i}", 100 - i) for i in range(5)]
    metin = rapor.tablo(rapor.olustur(kalemler, simdi=time.time()), ilk=2)
    assert "ve 3 kalem daha" in metin, metin
    assert "s3" not in metin and "s4" not in metin


def test_tablo_ozet_tahmin_ibaresi():
    """Ozet satiri toplamin TAHMIN oldugunu yazar (kesin olcum iddiasi yok)."""
    metin = rapor.tablo(rapor.olustur(ornek_kalemler(), simdi=time.time()))
    assert "TAHMIN" in metin, metin
    assert "toplam acilis ~150 token" in metin, metin


def test_tablo_ozet_olculemeyen_sayisi():
    """Ozet, tokeni OLCELEMEYEN kalemlerin sayisini yazar (MCP vb.)."""
    metin = rapor.tablo(rapor.olustur(ornek_kalemler(), simdi=time.time()))
    assert "1 olculemeyen kalem" in metin, metin
    assert "olculemeyen" in metin.splitlines()[-1]


def test_tablo_ozet_kapali_sayisi():
    """Ozet, KAPALI kalemlerin sayisini yazar (bastan tasarruf edilen yer)."""
    kalemler = ornek_kalemler() + [_kalem("kule:eski", 500, kapali=True)]
    assert "1 kapali" in rapor.tablo(rapor.olustur(kalemler, simdi=time.time()))


def test_tablo_olculemeyen_kalemde_sayi_yazmaz():
    """Olculemeyen kalem `acilis` sutununda '-' gosterir (uydurma sayi yazmaz)."""
    metin = rapor.tablo(rapor.olustur(ornek_kalemler(), simdi=time.time()))
    assert "atlas" in metin
    satir = [ln for ln in metin.splitlines() if ln.startswith("atlas")][0]
    assert satir.split() == ["atlas", "mcp", "-", "-", "olculemedi"], satir


def test_tablo_kapali_kalem_durum_sutununda_isaretli():
    """Kapali skill satiri 'kapali' isaretini tasir (kullanici neyin kapandigini gorur)."""
    kalemler = ornek_kalemler() + [_kalem("kule:eski", 500, kapali=True)]
    satir = [
        ln
        for ln in rapor.tablo(rapor.olustur(kalemler, simdi=time.time())).splitlines()
        if ln.startswith("kule:eski")
    ][0]
    assert satir.split()[-1] == "kapali", satir


def test_tablo_bos_girdi_calisir():
    """Kalem yokken tablo yine calisir (IndexError yok), ozet '0' der."""
    metin = rapor.tablo(rapor.olustur([], simdi=time.time()))
    assert "toplam acilis ~0 token" in metin, metin
    assert metin.splitlines()[0].split() == ["ad", "tur", "acilis", "cagrilinca", "durum"]


def test_tablo_sifir_ilk_ile_kac_satir():
    """`ilk=0`: hic kalem gosterilmez, sadece baslik + ozet (negatif ilk de cokmez)."""
    metin = rapor.tablo(rapor.olustur(ornek_kalemler(), simdi=time.time()), ilk=0)
    assert "ve 3 kalem daha" in metin
    assert "kule:harita" not in metin
