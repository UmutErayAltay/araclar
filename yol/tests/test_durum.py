"""durum.py: REG_EXPAND_SZ acma (ortam_olustur), PATH bulgulari ve deger maskeleme."""

from __future__ import annotations

import json

import pytest

from yol import durum
from yol.kaynak import DosyaKaynak


def _windows_kaynak(tmp_path, sistem: dict, kullanici: dict) -> DosyaKaynak:
    yol = tmp_path / "ortam.json"
    veri = {"ayirici": ";", "windows": True, "sistem": sistem, "kullanici": kullanici}
    yol.write_text(json.dumps(veri, ensure_ascii=False), encoding="utf-8")
    return DosyaKaynak(yol)


PROGRAM_FILES = {"ProgramFiles": {"metin": "C:\\Program Files", "genisler": False}}
JAVA_HOME = {"metin": "%ProgramFiles%\\Java\\jdk", "genisler": True}


@pytest.fixture(autouse=True)
def _surec_ortami_temiz(monkeypatch):
    monkeypatch.delenv("ProgramFiles", raising=False)


def test_ortam_kayit_degeri_ic_ice_acilir(tmp_path):
    kaynak = _windows_kaynak(tmp_path, PROGRAM_FILES, {"JAVA_HOME": JAVA_HOME})
    assert durum.ortam_olustur(kaynak)["JAVA_HOME"] == "C:\\Program Files\\Java\\jdk"


def test_ortam_acmada_surec_ortami_tercih_edilir(tmp_path, monkeypatch):
    monkeypatch.setenv("ProgramFiles", "D:\\PF")
    kaynak = _windows_kaynak(tmp_path, {}, {"JAVA_HOME": JAVA_HOME})
    assert durum.ortam_olustur(kaynak)["JAVA_HOME"] == "D:\\PF\\Java\\jdk"


def test_ortam_reg_sz_degeri_acilmaz(tmp_path):
    ham = {"metin": "%ProgramFiles%\\x", "genisler": False}
    kaynak = _windows_kaynak(tmp_path, PROGRAM_FILES, {"ORNEK": ham})
    assert durum.ortam_olustur(kaynak)["ORNEK"] == "%ProgramFiles%\\x"


def test_java_home_ornegi_path_girdisi_yok_olmaz(tmp_path):
    # Regresyon (veri kaybi): %JAVA_HOME%\bin calisan bir girdi, "yok" diye temizlenmemeli.
    kaynak = _windows_kaynak(tmp_path, PROGRAM_FILES, {
        "JAVA_HOME": JAVA_HOME,
        "Path": {"metin": "%JAVA_HOME%\\bin", "genisler": True},
    })
    bin_dizini = "c:\\program files\\java\\jdk\\bin"
    rapor = durum.path_durumu(kaynak, dizin_var=lambda yol: yol.casefold() == bin_dizini,
                              dosya_var=lambda yol: False)
    assert rapor["girdiler"][0]["genis"] == "C:\\Program Files\\Java\\jdk\\bin"
    assert rapor["girdiler"][0]["bulgular"] == []
    assert rapor["oneri"] == {}


def test_degiskenler_url_kimligi_iceren_degeri_maskeler(tmp_path):
    kaynak = _windows_kaynak(tmp_path, {}, {
        "CACHE_DIR": {"metin": "https://umut:cok-gizli-parola@sunucu/yol", "genisler": False},
        "PWD": {"metin": "https://umut:pwd-deger@sunucu/yol", "genisler": False},
    })
    satirlar = {s["ad"]: s for s in durum.degiskenler(kaynak)}
    assert satirlar["CACHE_DIR"]["gizli"] is True
    assert "cok-gizli-parola" not in json.dumps(satirlar["CACHE_DIR"], ensure_ascii=False)
    # PWD / OLDPWD muaftir: deger kimlik tasisa bile maskelenmez
    assert satirlar["PWD"]["gizli"] is False
    assert satirlar["PWD"]["deger"] == "https://umut:pwd-deger@sunucu/yol"
