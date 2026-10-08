"""kaynak.py: DosyaKaynak (gidis-donus, atomik yazma, hata yolu), SurecKaynak, kaynak_sec."""

from __future__ import annotations

import pytest

from yol.kaynak import (
    KULLANICI,
    SISTEM,
    SUREC,
    Deger,
    DosyaKaynak,
    KaynakHatasi,
    SurecKaynak,
    kaynak_sec,
)


def test_dosya_gidis_donus_ve_atomik(tmp_path):
    yol = tmp_path / "k.json"
    kaynak = DosyaKaynak(yol)
    assert kaynak.oku(KULLANICI) == {}
    kaynak.yaz(KULLANICI, "Path", Deger("a;b", True))
    kaynak.yaz(KULLANICI, "EDITOR", Deger("code"))
    yeni = DosyaKaynak(yol)
    assert yeni.oku(KULLANICI) == {"Path": Deger("a;b", True), "EDITOR": Deger("code", False)}
    yeni.sil(KULLANICI, "EDITOR")
    assert "EDITOR" not in DosyaKaynak(yol).oku(KULLANICI)
    yeni.sil(KULLANICI, "YOK")  # olmayan silinince hata yok
    assert list(tmp_path.glob("*.tmp")) == []


def test_dosya_genisler_tipi_saklanir(tmp_path):
    yol = tmp_path / "k.json"
    DosyaKaynak(yol).yaz(SISTEM, "Path", Deger("%SystemRoot%", True))
    assert DosyaKaynak(yol).oku(SISTEM)["Path"].genisler is True


def test_dosya_bozuk_json_hata(tmp_path):
    yol = tmp_path / "k.json"
    yol.write_text("{bozuk", encoding="utf-8")
    with pytest.raises(KaynakHatasi):
        DosyaKaynak(yol).oku(KULLANICI)


def test_dosya_yazma_hatasi_kaynak_hatasi(tmp_path):
    engel = tmp_path / "dosya.txt"
    engel.write_text("x", encoding="utf-8")
    with pytest.raises(KaynakHatasi):
        DosyaKaynak(engel / "k.json").yaz(KULLANICI, "Path", Deger("a"))


def test_dosya_bilinmeyen_kapsam(tmp_path):
    kaynak = DosyaKaynak(tmp_path / "k.json")
    with pytest.raises(KaynakHatasi):
        kaynak.oku("bilinmeyen")


def test_dosya_yazilabilirlik(tmp_path):
    kaynak = DosyaKaynak(tmp_path / "k.json")
    assert kaynak.yazilabilir(KULLANICI) and kaynak.yazilabilir(SISTEM)
    assert not kaynak.yazilabilir(SUREC)


def test_surec_salt_okunur(monkeypatch):
    monkeypatch.setenv("YOL_TEST_DEGER", "x")
    kaynak = SurecKaynak()
    assert kaynak.oku(SUREC)["YOL_TEST_DEGER"] == Deger("x")
    assert kaynak.yazilabilir(SUREC) is False
    with pytest.raises(KaynakHatasi):
        kaynak.yaz(SUREC, "A", Deger("b"))
    with pytest.raises(KaynakHatasi):
        kaynak.sil(SUREC, "A")
    assert kaynak.yayinla() is None


def test_kaynak_sec(tmp_path, monkeypatch):
    yol = tmp_path / "k.json"
    assert isinstance(kaynak_sec(f"dosya:{yol}"), DosyaKaynak)
    assert isinstance(kaynak_sec("surec"), SurecKaynak)
    assert isinstance(kaynak_sec(None), SurecKaynak)  # Linux varsayilani
    monkeypatch.setenv("YOL_KAYNAK", f"dosya:{yol}")
    assert isinstance(kaynak_sec(None), DosyaKaynak)
    with pytest.raises(KaynakHatasi):
        kaynak_sec("bogus")
