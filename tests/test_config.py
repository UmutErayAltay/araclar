"""Yapilandirma: ~/.atlas/config.toml ve ATLAS_DB ortam degiskeni."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from atlas import config


@pytest.fixture
def ev(monkeypatch, tmp_path: Path) -> Path:
    """HOME ve Path.home() yerine gecici bir ev dizini.

    `~` genisletmesi HOME ortam degiskenini okudugu icin ikisi de ayarlanir.
    """
    ev_dizini = tmp_path / "ev"
    ev_dizini.mkdir()
    monkeypatch.delenv("ATLAS_DB", raising=False)
    monkeypatch.setenv("HOME", str(ev_dizini))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: ev_dizini))
    return ev_dizini


def yaz_config(ev_dizini: Path, icerik: str) -> Path:
    d = ev_dizini / config.CONFIG_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    yol = d / config.CONFIG_FILENAME
    yol.write_text(icerik, encoding="utf-8")
    return yol


def test_config_yoksa_ev_koku(ev: Path):
    assert config.load_roots() == [ev]


def test_roots_okunur(ev: Path, tmp_path: Path):
    yaz_config(ev, 'roots = ["/srv/repo", "/opt/isbasi"]\n')
    assert config.load_roots() == [Path("/srv/repo"), Path("/opt/isbasi")]


def test_roots_yorumlu_toml(ev: Path):
    yaz_config(ev, '# yorum\nroots = ["/srv/repo"]\nderinlik = 5\n')
    assert config.load_roots() == [Path("/srv/repo")]


def test_tek_kok_da_liste_mi(ev: Path):
    yaz_config(ev, 'roots = ["/srv/repo"]\n')
    assert config.load_roots() == [Path("/srv/repo")]


def test_bozuk_toml_evt_donusur(ev: Path):
    yaz_config(ev, "roots = [bu gecersiz\n")
    assert config.load_roots() == [ev]


def test_roots_anahtarı_yoksa_evt_donusur(ev: Path):
    yaz_config(ev, 'derinlik = 4\n')
    assert config.load_roots() == [ev]


def test_roots_bos_liste_evt_donusur(ev: Path):
    yaz_config(ev, "roots = []\n")
    assert config.load_roots() == [ev]


def test_roots_liste_degil_evt_donusur(ev: Path):
    yaz_config(ev, 'roots = "/srv/repo"\n')
    assert config.load_roots() == [ev]


def test_roots_oge_degil_dizeler_atilir(ev: Path):
    yaz_config(ev, 'roots = ["/srv/repo", 5, true, "/opt/x"]\n')
    assert config.load_roots() == [Path("/srv/repo"), Path("/opt/x")]


def test_ilk_gecerli_kok_kullanilir(ev: Path):
    yaz_config(ev, 'roots = ["", "/srv/repo"]\n')
    assert config.load_roots() == [Path("/srv/repo")]


def test_config_dosyasi_dizinse_evt_donusur(ev: Path):
    d = ev / config.CONFIG_DIRNAME
    d.mkdir()
    (d / config.CONFIG_FILENAME).mkdir()  # config.toml bir dizin
    assert config.load_roots() == [ev]


def test_config_dosyasi_okunamazsa_evt_donusur(ev: Path):
    """chmod 000 config.toml taramayi cokertmemeli.

    Root icin de gecerli: okunabiliyorsa config degerleri doner, okunamıyorsa
    eve duser. Kritik olan `load_roots()`'in cokmemesi.
    """
    yaz_config(ev, 'roots = ["/srv/repo"]\n')
    yol = ev / config.CONFIG_DIRNAME / config.CONFIG_FILENAME
    os.chmod(yol, 0o000)
    try:
        sonuc = config.load_roots()
        assert isinstance(sonuc, list) and sonuc
        if os.access(yol, os.R_OK):  # root: DAC_OVERRIDE ile yine okur
            assert sonuc == [Path("/srv/repo")]
        else:
            assert sonuc == [ev]
    finally:
        os.chmod(yol, 0o600)


def test_config_yarim_yazilmis_toml(ev: Path):
    yaz_config(ev, 'roots = ["/srv/repo"\n')  # kapanis parantezi yok
    assert config.load_roots() == [ev]


def test_config_tilde_dongusu_cokmez(ev: Path, monkeypatch):
    """HOME sembolik link dongusune donerse load_roots cokmemeli."""
    yaz_config(ev, 'roots = ["~/projeler"]\n')
    dongu = ev / "dongu"
    dongu.symlink_to(dongu)  # kendine isaret eden bag
    monkeypatch.setenv("HOME", str(dongu))
    sonuc = config.load_roots()
    assert isinstance(sonuc, list) and sonuc


def test_tilde_genisletilir(ev: Path):
    yaz_config(ev, 'roots = ["~/projeler"]\n')
    assert config.load_roots() == [ev / "projeler"]


def test_db_varsayilan_yolu(ev: Path):
    assert config.default_db_path() == ev / ".atlas" / "atlas.db"


def test_db_ortam_degiskeni_gecerli(ev: Path, monkeypatch, tmp_path: Path):
    hedef = tmp_path / "ozel.db"
    monkeypatch.setenv(config.DB_ENV_VAR, str(hedef))
    assert config.default_db_path() == hedef


def test_db_ortam_degiskeni_tilde_genisletir(ev: Path, monkeypatch):
    monkeypatch.setenv(config.DB_ENV_VAR, "~/ozel.db")
    assert config.default_db_path() == ev / "ozel.db"


def test_db_ortam_degiskeni_bos_sayilir(ev: Path, monkeypatch):
    monkeypatch.setenv(config.DB_ENV_VAR, "")
    assert config.default_db_path() == ev / ".atlas" / "atlas.db"


def test_atlas_dizini_yolu(ev: Path):
    assert config.atlas_dir() == ev / ".atlas"
    assert config.config_path() == ev / ".atlas" / "config.toml"


def test_cli_root_verilmezse_config_kullanilir(ev: Path, monkeypatch, tmp_path: Path):
    """`--root` verilmezse config.toml'daki kokler taranir (HOME uzerinden)."""
    from conftest import make_repo, rows_for, run_module_cli

    proje = Path(ev) / "projeler" / "ornek"
    make_repo(proje)
    yaz_config(ev, 'roots = ["~/projeler"]\n')
    db = tmp_path / "y.db"
    proc = run_module_cli("tara", "--db", str(db))
    assert proc.returncode == 0, proc.stderr
    assert str(proje) in rows_for(db)
