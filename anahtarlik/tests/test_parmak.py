"""Parmak izi: tuzlu, kararli, kisa degerde None."""

from __future__ import annotations

import secrets
from pathlib import Path

import pytest

from anahtarlik import parmak

DEGER = "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


def test_izi_kararli(anahtarlik_dir):
    """Ayni deger, ayni tuz -> ayni iz (iki cagri karsilastirilabilir)."""
    assert parmak.izi(DEGER) == parmak.izi(DEGER)


def test_izi_degisik_deger_degisir(anahtarlik_dir):
    assert parmak.izi(DEGER) != parmak.izi(DEGER + "x")


def test_izi_tuz_dosyasina_yazilir(anahtarlik_dir):
    """Tuz dosyaya yazilir ve oradan okunur (makine-yerel, kalici)."""
    parmak.izi(DEGER)
    tuz_dosya = anahtarlik_dir / "tuz"
    assert tuz_dosya.is_file()
    assert tuz_dosya.read_bytes() == parmak.tuz()


def test_izi_kisa_deger_none(anahtarlik_dir):
    """8 karakterden kisa deger: None (tuzlu kaba kuvvet riski)."""
    assert parmak.izi("kisa") is None
    assert parmak.izi("1234567") is None


def test_izi_bos_deger_none(anahtarlik_dir):
    assert parmak.izi("") is None


def test_izi_esik_deger_kabul(anahtarlik_dir):
    """Tam 8 karakter kabul edilir."""
    assert parmak.izi("12345678") is not None


def test_izi_uzunlugu_sabit(anahtarlik_dir):
    assert len(parmak.izi(DEGER)) == 8


def test_iki_kurulum_farkli_tuz_farkli_izi(tmp_path, monkeypatch):
    """Ayni deger, FARKLI tuz -> farkli iz (envanter tasinamaz, karsilastirilamaz)."""
    monkeypatch.setenv("ANAHTARLIK_DIR", str(tmp_path / "a"))
    ilk = parmak.izi(DEGER)
    monkeypatch.setenv("ANAHTARLIK_DIR", str(tmp_path / "b"))
    ikinci = parmak.izi(DEGER)
    assert ilk is not None and ikinci is not None
    assert ilk != ikinci


def test_tuz_yazilamazsa_calisir(tmp_path, monkeypatch):
    """Tuz yazilamazsa gecici tuz uretilir: tarama cokmez."""
    engel = tmp_path / "engel"
    engel.write_text("dosya", encoding="utf-8")
    monkeypatch.setenv("ANAHTARLIK_DIR", str(engel / "tuzlu"))
    assert parmak.izi(DEGER) is not None


def test_bos_tuz_dosyasi_yenilenir(tmp_path, monkeypatch):
    """Bozuk/bos tuz dosyasi sessizce yenilenir (eski izler gecersizlesir)."""
    dizin = tmp_path / "ev"
    dizin.mkdir()
    (dizin / "tuz").write_bytes(b"")
    monkeypatch.setenv("ANAHTARLIK_DIR", str(dizin))
    assert len(parmak.tuz()) == 32
    assert (dizin / "tuz").read_bytes() == parmak.tuz()


# --------------------------------------------------------------------------
# Tuzun kabul kosullari ve yarisma
# --------------------------------------------------------------------------


@pytest.mark.parametrize("bozuk", [b"", b"\x01", b"kisa"])
def test_kisa_bozuk_tuz_reddedilir(tmp_path, monkeypatch, bozuk):
    """Cok kisa tuz kabul edilmez: 8 hex (32 bit) iz, kisa tuzla kaba
    kuvvetle COZULEBILIR (1 baytlik tuz 256 denemede kirilir)."""
    dizin = tmp_path / "ev"
    dizin.mkdir()
    (dizin / "tuz").write_bytes(bozuk)
    monkeypatch.setenv("ANAHTARLIK_DIR", str(dizin))
    tuz = parmak.tuz()
    assert len(tuz) >= parmak.ASGARI_TUZ
    assert (dizin / "tuz").read_bytes() == tuz  # dosya da yenilendi


def test_yeterince_uzun_tuz_aynen_kabul_edilir(tmp_path, monkeypatch):
    """16 baytlik tuz KABUL edilir (gereksiz yere yenilenmez)."""
    dizin = tmp_path / "ev"
    dizin.mkdir()
    mevcut = bytes(range(parmak.ASGARI_TUZ))
    (dizin / "tuz").write_bytes(mevcut)
    monkeypatch.setenv("ANAHTARLIK_DIR", str(dizin))
    assert parmak.tuz() == mevcut


def test_tuz_yazma_yarismasi_tutarli(tmp_path, monkeypatch):
    """Iki surec ayni anda tuz uretirse izler TUTARLI kalmali.

    Yarisma GERCEK: surec tuzunu yazip okumadan once baska bir surec kendi
    tuzunu yazarsa ilki kendi tuzunu kullanir, ikinci disktekinden farkli
    bir tuz kullanir -> iz tabanlari tutarsizlasir. `O_EXCL` ile dosyayi
    YALNIZCA ilk kacan surec yazar; kaybeden `FileExistsError` alip diskteki
    tuzu okur.
    """
    dizin = tmp_path / "ev"
    monkeypatch.setenv("ANAHTARLIK_DIR", str(dizin))
    gercek = Path.read_bytes  # tuz dosyasinin ilk okumasini yakala
    sayac = {"n": 0}

    def yarisan_ok(self):
        if self.name == "tuz" and sayac["n"] == 0:
            sayac["n"] = 1
            # Rakip surec bu arada kendi tuzunu yazdi; ben de yazacaktim.
            self.write_bytes(secrets.token_bytes(parmak.TUZ_UZUNLUK))
        return gercek(self)

    monkeypatch.setattr(Path, "read_bytes", yarisan_ok)
    benim = parmak.tuz()
    # `undo()` ANAHTARLIK_DIR'i de geri alirdi: sadece yamayi geri al.
    monkeypatch.setattr(Path, "read_bytes", gercek)
    # Rakip yazmis gorunse de benim tuzum disktekiyle AYNI olmali.
    assert benim == (dizin / "tuz").read_bytes() == parmak.tuz()


def test_tuz_dosyasi_yarisinda_tek_kazanir(tmp_path, monkeypatch):
    """`O_EXCL`: dosyayi olusturan surec yazar, digerleri olusturamaz."""
    dizin = tmp_path / "ev"
    dizin.mkdir()
    monkeypatch.setenv("ANAHTARLIK_DIR", str(dizin))
    yol = dizin / "tuz"
    ilk = parmak._tuz_uret_ve_yaz(yol, yalniz_olustur=True)
    with pytest.raises(FileExistsError):
        parmak._tuz_uret_ve_yaz(yol, yalniz_olustur=True)  # ikinci kacan YAZAMAZ
    assert yol.read_bytes() == ilk == parmak.tuz()