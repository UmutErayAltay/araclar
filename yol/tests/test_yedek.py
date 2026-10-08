"""yedek.py: atomik yazma, budama, benzersiz kimlik, kimlik dogrulama, gunluk."""

from __future__ import annotations

import datetime as dt
import json

import pytest

from yol import yedek
from yol.kaynak import Deger
from yol.yedek import ID_RE, YEDEK_SAYISI, YedekHatasi, gunluk_ekle, yedek_al, yedek_oku, yedekler

ESKI_PATH = Deger("C:\\Users\\umut\\bin;C:\\Tools", True)


def test_yedek_al_dosya_yazar(yol_dir, dosya_kaynak):
    kimlik = yedek_al(dosya_kaynak, ["kullanici", "sistem"])
    assert ID_RE.fullmatch(kimlik)
    veri = json.loads((yol_dir / "yedek" / f"{kimlik}.json").read_text(encoding="utf-8"))
    assert veri["id"] == kimlik
    assert veri["kaynak"] == "dosya"
    assert veri["kapsamlar"]["kullanici"]["Path"] == {"metin": "C:\\Users\\umut\\bin;C:\\Tools", "genisler": True}
    assert veri["kapsamlar"]["sistem"]["Path"]["genisler"] is True
    assert list((yol_dir / "yedek").glob("*.tmp")) == []


def test_atomik_yazma_hatada_dosya_olusmaz(yol_dir, dosya_kaynak, monkeypatch):
    def patlar(*args, **kwargs):
        raise OSError("disk dolu")

    monkeypatch.setattr(yedek.os, "replace", patlar)
    with pytest.raises(YedekHatasi):
        yedek_al(dosya_kaynak, ["kullanici"])
    assert list((yol_dir / "yedek").glob("*.json")) == []
    assert list((yol_dir / "yedek").glob("*.tmp")) == []


def test_budama_en_fazla_otuz(yol_dir, dosya_kaynak):
    kimlikler = [yedek_al(dosya_kaynak, ["kullanici"]) for _ in range(YEDEK_SAYISI + 5)]
    kalan = sorted(p.stem for p in (yol_dir / "yedek").glob("*.json"))
    assert len(kalan) == YEDEK_SAYISI
    assert kalan == sorted(kimlikler)[-YEDEK_SAYISI:]
    listesi = [y["id"] for y in yedekler()]
    assert len(listesi) == YEDEK_SAYISI
    assert listesi == sorted(listesi, reverse=True)


def test_ayni_mikrosaniyede_benzersiz_kimlik(yol_dir, dosya_kaynak, monkeypatch):
    sabit = dt.datetime(2026, 10, 8, 15, 30, 0, 123456, tzinfo=dt.timezone.utc)
    monkeypatch.setattr(yedek, "_simdi", lambda: sabit)
    ilk = yedek_al(dosya_kaynak, ["kullanici"])
    ikinci = yedek_al(dosya_kaynak, ["kullanici"])
    assert ilk != ikinci
    assert ilk == "20261008T153000123456Z"
    assert ikinci == "20261008T153000123457Z"
    assert (yol_dir / "yedek" / f"{ilk}.json").exists()
    assert (yol_dir / "yedek" / f"{ikinci}.json").exists()


@pytest.mark.parametrize("kimlik", ["../x", "..\\x", "20261008T153000123456Z/../../x", "", "abc",
                                    "20261008T153000123456Z\n"])
def test_gecersiz_kimlik_reddedilir(yol_dir, kimlik):
    with pytest.raises(YedekHatasi):
        yedek_oku(kimlik)


def test_yedek_oku_deger_nesneleri(yol_dir, dosya_kaynak):
    kimlik = yedek_al(dosya_kaynak, ["kullanici"])
    goruntu = yedek_oku(kimlik)
    assert goruntu["kapsamlar"]["kullanici"]["Path"] == ESKI_PATH
    assert goruntu["kapsamlar"]["kullanici"]["EDITOR"] == Deger("code", False)


def test_yedek_yok_ise_hata(yol_dir):
    with pytest.raises(YedekHatasi):
        yedek_oku("20260101T000000000000Z")


def test_okunamayan_yedek_listelemede_atlanir(yol_dir, dosya_kaynak):
    klasor = yol_dir / "yedek"
    klasor.mkdir(parents=True)
    (klasor / "20260101T000000000000Z.json").write_text("{bozuk", encoding="utf-8")
    kimlik = yedek_al(dosya_kaynak, ["kullanici"])
    ids = [y["id"] for y in yedekler()]
    assert ids == [kimlik]


def test_yedekler_kapsam_sayilari(yol_dir, dosya_kaynak):
    yedek_al(dosya_kaynak, ["kullanici", "sistem"])
    assert yedekler()[0]["kapsamlar"] == {"kullanici": 2, "sistem": 1}


def test_gunluk_zaman_ekler(yol_dir):
    gunluk_ekle({"eylem": "ekle", "ad": "Path"})
    satirlar = (yol_dir / "gunluk.jsonl").read_text(encoding="utf-8").splitlines()
    kayit = json.loads(satirlar[-1])
    assert kayit["eylem"] == "ekle"
    assert "zaman" in kayit
