"""cli.py: cikis kodlari, kuru calistirma, uygula, ekle/kaldir, geri-al, web baglantisi."""

from __future__ import annotations

import json
import sys

import pytest

from yol import cli
from yol.yedek import yedekler


@pytest.fixture(autouse=True)
def _yedek_dizini(yol_dir):
    return yol_dir


@pytest.fixture
def bin_dizinleri(tmp_path):
    bin1, bin2, bin3 = tmp_path / "bin1", tmp_path / "bin2", tmp_path / "bin3"
    for d in (bin1, bin2, bin3):
        d.mkdir()
    (bin1 / "python").write_text("", encoding="utf-8")
    (bin2 / "python").write_text("", encoding="utf-8")
    return bin1, bin2, bin3


def _calistir(capsys, *args: str) -> tuple[int, str, str]:
    kod = cli.main(list(args))
    cikti = capsys.readouterr()
    return kod, cikti.out, cikti.err


def _yol(spec: str) -> str:
    return spec[len("dosya:"):]


def _kullanici_path(spec: str) -> str:
    return json.loads(open(_yol(spec), encoding="utf-8").read())["kullanici"]["PATH"]["metin"]


def test_denetle_temiz_kurulum_sifir(capsys, tmp_path, posix_kaynak, bin_dizinleri):
    bin1, bin2, _ = bin_dizinleri
    kaynak = posix_kaynak(sistem=str(bin2), kullanici=str(bin1))
    kod, out, _ = _calistir(capsys, "--kaynak", kaynak, "denetle")
    assert kod == 0
    assert "ozet:" in out
    assert "sorunlu 0" in out


def test_denetle_sorunlu_kurulum_bir(capsys, tmp_path, posix_kaynak, bin_dizinleri):
    bin1, bin2, _ = bin_dizinleri
    kullanici = f"{bin1}:{bin2}:{tmp_path / 'yok'}::{bin1}/"
    kaynak = posix_kaynak(sistem=str(bin2), kullanici=kullanici)
    kod, out, _ = _calistir(capsys, "--kaynak", kaynak, "denetle")
    assert kod == 1
    assert "sistemde-var" in out
    assert "yok" in out
    assert "tekrar" in out
    assert "bos" in out


def test_denetle_json(capsys, bin_dizinleri, posix_kaynak):
    bin1, bin2, _ = bin_dizinleri
    kaynak = posix_kaynak(sistem=str(bin2), kullanici=str(bin1))
    kod, out, _ = _calistir(capsys, "--kaynak", kaynak, "denetle", "--json")
    veri = json.loads(out)
    assert kod == 0
    assert veri["ozet"]["sorunlu"] == 0
    assert {"girdiler", "komutlar", "oneri", "path_adlari"} <= veri.keys()


def test_nerede_sistem_once_kazanan(capsys, bin_dizinleri, posix_kaynak):
    bin1, bin2, _ = bin_dizinleri
    kaynak = posix_kaynak(sistem=str(bin2), kullanici=str(bin1))
    kod, out, _ = _calistir(capsys, "--kaynak", kaynak, "nerede", "python")
    assert kod == 0
    assert f"python: {bin2 / 'python'}" in out
    assert f"golgede: {bin1 / 'python'}" in out


def test_nerede_bulunamayan_komut_bir(capsys, bin_dizinleri, posix_kaynak):
    bin1, bin2, _ = bin_dizinleri
    kaynak = posix_kaynak(sistem=str(bin2), kullanici=str(bin1))
    kod, out, _ = _calistir(capsys, "--kaynak", kaynak, "nerede", "yokkomut")
    assert kod == 1
    assert "bulunamadi" in out


def test_temizle_kuru_calistirma_dosyayi_degistirmez(capsys, tmp_path, posix_kaynak, bin_dizinleri,
                                                      yol_dir):
    bin1, bin2, _ = bin_dizinleri
    kaynak = posix_kaynak(sistem=str(bin2), kullanici=f"{bin1}:{tmp_path / 'yok'}:{bin1}/")
    onceki = open(_yol(kaynak), "rb").read()
    kod, out, _ = _calistir(capsys, "--kaynak", kaynak, "temizle")
    assert kod == 0
    assert "kuru calistirma" in out
    assert open(_yol(kaynak), "rb").read() == onceki
    assert yedekler() == []


def test_temizle_uygula_yedek_alir(capsys, tmp_path, posix_kaynak, bin_dizinleri):
    bin1, bin2, _ = bin_dizinleri
    kaynak = posix_kaynak(sistem=str(bin2), kullanici=f"{bin1}:{tmp_path / 'yok'}:{bin1}/")
    kod, out, _ = _calistir(capsys, "--kaynak", kaynak, "temizle", "--uygula")
    assert kod == 0
    assert _kullanici_path(kaynak) == str(bin1)
    assert len(yedekler()) == 1
    assert "yedek:" in out


def test_ekle_kaldir_ve_tekrar_reddi(capsys, bin_dizinleri, posix_kaynak):
    bin1, bin2, bin3 = bin_dizinleri
    kaynak = posix_kaynak(sistem=None, kullanici=str(bin1))

    # kuru calistirma degistirmez
    kod, out, _ = _calistir(capsys, "--kaynak", kaynak, "ekle", str(bin2))
    assert kod == 0 and "kuru calistirma" in out
    assert _kullanici_path(kaynak) == str(bin1)

    kod, _, _ = _calistir(capsys, "--kaynak", kaynak, "ekle", str(bin2), "--uygula")
    assert kod == 0
    assert _kullanici_path(kaynak) == f"{bin1}:{bin2}"

    kod, _, err = _calistir(capsys, "--kaynak", kaynak, "ekle", str(bin2) + "/", "--uygula")
    assert kod == 1 and "zaten var" in err

    kod, _, _ = _calistir(capsys, "--kaynak", kaynak, "ekle", str(bin3), "--basa", "--uygula")
    assert kod == 0
    assert _kullanici_path(kaynak) == f"{bin3}:{bin1}:{bin2}"

    kod, _, err = _calistir(capsys, "--kaynak", kaynak, "ekle", str(bin3 / "yok"), "--uygula")
    assert kod == 1 and "dizin yok" in err

    kod, _, _ = _calistir(capsys, "--kaynak", kaynak, "kaldir", str(bin1), "--uygula")
    assert kod == 0
    assert _kullanici_path(kaynak) == f"{bin3}:{bin2}"

    kod, _, err = _calistir(capsys, "--kaynak", kaynak, "kaldir", str(bin1), "--uygula")
    assert kod == 1 and "bulunamadi" in err


def test_cozumlenemeyen_degisken_sorunlu_sayilmaz(capsys, posix_kaynak):
    # Regresyon: acilamayan degisken "yok" diye sorunlu sayiliyordu (denetle cikis kodu 1).
    kaynak = posix_kaynak(sistem=None, kullanici="/${COZULMEYEN_X}/bin")
    kod, out, _ = _calistir(capsys, "--kaynak", kaynak, "denetle")
    assert kod == 0
    assert "cozumlenemedi (notr)" in out


def test_yedekler_ve_geri_al_roundtrip(capsys, bin_dizinleri, posix_kaynak):
    bin1, bin2, _ = bin_dizinleri
    kaynak = posix_kaynak(sistem=None, kullanici=str(bin1))
    _calistir(capsys, "--kaynak", kaynak, "ekle", str(bin2), "--uygula")
    kimlik = yedekler()[0]["id"]

    kod, out, _ = _calistir(capsys, "yedekler")
    assert kod == 0 and kimlik in out

    kod, out, _ = _calistir(capsys, "--kaynak", kaynak, "geri-al", kimlik)
    assert kod == 0 and "kuru calistirma" in out
    assert _kullanici_path(kaynak) == f"{bin1}:{bin2}"

    kod, _, _ = _calistir(capsys, "--kaynak", kaynak, "geri-al", kimlik, "--uygula")
    assert kod == 0
    assert _kullanici_path(kaynak) == str(bin1)


def test_geri_al_gecersiz_kimlik_bir(capsys, posix_kaynak, bin_dizinleri):
    bin1, _, _ = bin_dizinleri
    kaynak = posix_kaynak(sistem=None, kullanici=str(bin1))
    kod, _, err = _calistir(capsys, "--kaynak", kaynak, "geri-al", "../x")
    assert kod == 1
    assert "gecersiz yedek kimligi" in err
    assert "Traceback" not in err


def test_web_flask_yoksa_ikiye_cikar(capsys, monkeypatch):
    monkeypatch.setitem(sys.modules, "yol.web", None)
    kod, _, err = _calistir(capsys, "web")
    assert kod == 2
    assert "pip install -e .[web]" in err


def test_kullanim_hatalari(capsys):
    assert cli.main(["bilinmeyen"]) == 2
    assert cli.main([]) == 2


def test_bilinmeyen_kaynak_hata_mesaji(capsys):
    kod, _, err = _calistir(capsys, "--kaynak", "bogus", "denetle")
    assert kod == 1
    assert "bilinmeyen YOL_KAYNAK" in err
    assert "Traceback" not in err


def test_salt_okunur_kaynakta_ekle_reddedilir(capsys, tmp_path, monkeypatch):
    kod, _, err = _calistir(capsys, "--kaynak", "surec", "ekle", str(tmp_path), "--uygula")
    assert kod == 1
    assert "kullanici" in err
