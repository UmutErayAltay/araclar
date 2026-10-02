"""CLI sozlesmesi: `python -m bagimlilik` GERCEKTEN subprocess olarak calistirilir.

BAGIMLILIK_DIR ve ATLAS_DB gecici dizine yonlendirilir: kullanicinin
raporu ya da gercek atlas DB'si okunmaz/yazilmaz.
Gercek pip-audit / npm audit kurulu olmadigi icin denetimler 'arac-yok'
doner — bu bir HATA degildir ve cikis kodunu bozmaz.
"""

from __future__ import annotations

import json
from pathlib import Path

from conftest import atlas_db_olustur, run_module_cli, sahte_repo

KULLANIM_HATASI = 2


def _env(tmp_path: Path) -> dict[str, str]:
    return {
        "BAGIMLILIK_DIR": str(tmp_path / "raporlar"),
        "ATLAS_DB": str(tmp_path / "yok-boyle-bir.db"),
    }


# --------------------------------------------------------------------------
# goster
# --------------------------------------------------------------------------


def test_goster_rapor_yokken_cikis_2_ve_turkce_ipucu(tmp_path):
    """Rapor yoksa `goster` cikis kodu 2 doner, stderr Turkce ve `tara` oner."""
    proc = run_module_cli("goster", cwd=tmp_path, env_ek=_env(tmp_path))
    assert proc.returncode == KULLANIM_HATASI, proc.stdout
    assert "rapor bulunamadi" in proc.stderr
    assert "bagimlilik tara" in proc.stderr
    assert proc.stdout.strip() == ""


def test_goster_bozuk_rapor_cikis_2(tmp_path):
    """Bozuk rapor dosyasi da 'bulunamadi' sayilir (cokmez, cikis 2)."""
    dizin = tmp_path / "raporlar"
    dizin.mkdir()
    (dizin / "son.json").write_text("{bozuk", encoding="utf-8")
    proc = run_module_cli("goster", cwd=tmp_path, env_ek=_env(tmp_path))
    assert proc.returncode == KULLANIM_HATASI
    assert "rapor bulunamadi" in proc.stderr


def test_goster_json_gecerli_json(tmp_path):
    """`goster --json` kaydedilmis raporu OLDUGU GIBI JSON olarak yazar."""
    dizin = tmp_path / "raporlar"
    dizin.mkdir()
    veri = {"surum": 1, "tarih": "2026-10-03T00:00:00+00:00", "repolar": [
        {"yol": "/x", "ad": "x", "denetimler": [
            {"ekosistem": "pip", "kaynak": "requirements.txt", "durum": "acik", "neden": None,
             "sayilar": {"kritik": 0, "yuksek": 0, "orta": 0, "dusuk": 0, "bilinmiyor": 1},
             "toplam": 1,
             "aciklar": [{"paket": "flask", "surum": "0.12", "id": "CVE-2019-1010083",
                          "duzeltme": "1.0", "siddet": "bilinmiyor"}],
             "ayrinti": None}],
         "desteklenmeyen": []}]}
    (dizin / "son.json").write_text(json.dumps(veri, ensure_ascii=False), encoding="utf-8")
    proc = run_module_cli("goster", "--json", cwd=tmp_path, env_ek=_env(tmp_path))
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout) == veri


def test_goster_tablo_modu_denetimleri_geri_alir(tmp_path):
    """`goster` (json'siz) raporu tabloya cevirir: Denetim/Acik geri alinir, hata yok."""
    dizin = tmp_path / "raporlar"
    dizin.mkdir()
    veri = {"surum": 1, "tarih": "2026-10-03T00:00:00+00:00", "repolar": [
        {"yol": "/x", "ad": "harita", "denetimler": [
            {"ekosistem": "npm", "kaynak": "package.json", "durum": "denetlenemedi",
             "neden": "kilit-yok", "sayilar": {"kritik": 0, "yuksek": 0, "orta": 0, "dusuk": 0,
                                               "bilinmiyor": 0},
             "toplam": 0, "aciklar": [], "ayrinti": "package-lock.json yok"}],
         "desteklenmeyen": ["go.mod"]}]}
    (dizin / "son.json").write_text(json.dumps(veri, ensure_ascii=False), encoding="utf-8")
    proc = run_module_cli("goster", cwd=tmp_path, env_ek=_env(tmp_path))
    assert proc.returncode == 0, proc.stderr
    assert "tarih: 2026-10-03T00:00:00+00:00" in proc.stdout
    assert "harita" in proc.stdout and "denetlenemedi(kilit-yok)" in proc.stdout
    assert "1 repo -> 0 temiz, 0 acikli, 1 denetlenemedi, 0 manifestsiz" in proc.stdout


# --------------------------------------------------------------------------
# tara
# --------------------------------------------------------------------------


def test_tara_temiz_sonuc_cikis_0(tmp_path):
    """Acik bulunmayan tarama cikis kodu 0 doner: 'acik bulmak hata degil' sozlesmesi.

    DENETLENMEYEN repo (hicbir bagimlilik bildirimi yok) ozette 'denetlenemedi'
    sayilir: ozet kurali yalnizca 'acik' varsa acikli, 'temiz' varsa temiz
    sayar, aksi halde 'denetlenemedi' der. Denetlenmesi gereken bir sey
    olmadigi icin bu bir inceleme bulgusudur (bkz. rapor.tablo).
    """
    kok = tmp_path / "projeler"
    sahte_repo(kok / "r")
    proc = run_module_cli("tara", "--root", str(kok), cwd=tmp_path, env_ek=_env(tmp_path))
    assert proc.returncode == 0, proc.stderr
    assert "1 repo -> 0 temiz, 0 acikli, 0 denetlenemedi, 1 manifestsiz" in proc.stdout


def test_tara_hic_repo_bulunamazsa_cikis_2(tmp_path):
    """Tamamen bos kok (hic repo, hic proje izi) denetlenecek sey yoktur: kesif hatasi, cikis 2."""
    kok = tmp_path / "bos"
    kok.mkdir()
    proc = run_module_cli("tara", "--root", str(kok), cwd=tmp_path, env_ek=_env(tmp_path))
    assert proc.returncode == KULLANIM_HATASI, proc.stdout
    assert "denetlenecek repo bulunamadi" in proc.stderr


def test_tara_gercek_repo_cikis_0_ve_rapor_yazilir(tmp_path):
    """`tara` gercek bir bulus tara: cikis kodu 0, rapor yazilir, repo adlari raporda."""
    kok = tmp_path / "projeler"
    sahte_repo(kok / "harita", {"go.mod": "module x\n"})
    proc = run_module_cli("tara", "--root", str(kok), cwd=tmp_path, env_ek=_env(tmp_path))
    assert proc.returncode == 0, proc.stderr
    rapor = json.loads((tmp_path / "raporlar" / "son.json").read_text(encoding="utf-8"))
    assert rapor["surum"] == 1 and rapor["repolar"][0]["ad"] == "harita"
    assert rapor["repolar"][0]["desteklenmeyen"] == ["go.mod"]
    assert "1 repo bulundu" in proc.stderr


def test_tara_arac_yok_durumu_hata_sayilmaz(tmp_path, monkeypatch, capsys):
    """pip-audit kurulu degilse 'arac-yok' rapora girer ama CIKIS KODU 0 kalir.

    Arac eksikligi denetim sonucudur, komut hatasi degil. Ortamda pip-audit kurulu
    olsa da sonuc ayni olsun diye find_spec surec ici sahtelenir.
    """
    from bagimlilik import cli, denetim

    gercek = denetim.importlib.util.find_spec
    monkeypatch.setattr(
        denetim.importlib.util, "find_spec",
        lambda ad, *a, **k: None if ad == "pip_audit" else gercek(ad, *a, **k),
    )
    monkeypatch.setenv("BAGIMLILIK_DIR", str(tmp_path / "raporlar"))
    kok = tmp_path / "projeler"
    sahte_repo(kok / "r", {"requirements.txt": "flask==0.12\n"})
    assert cli.main(["tara", "--root", str(kok), "--json"]) == 0
    d = json.loads(capsys.readouterr().out)["repolar"][0]["denetimler"][0]
    assert d["neden"] == "arac-yok" and d["durum"] == "denetlenemedi"


def test_tara_atlas_db_kesif_hatasi_cikis_2(tmp_path):
    """atlas DB yoksa kesif hatasi: cikis kodu 2, Turkce mesaj, hicbir repo taranmaz."""
    proc = run_module_cli("tara", cwd=tmp_path, env_ek=_env(tmp_path))
    assert proc.returncode == KULLANIM_HATASI
    assert "atlas veritabani bulunamadi" in proc.stderr
    assert "--root" in proc.stderr and "atlas tara" in proc.stderr


def test_tara_atlas_db_ile_calisir(tmp_path):
    """ATLAS_DB ortam degiskeni repo listesini verir: kesif hatasi olmaz, tarama calisir."""
    kok = tmp_path / "projeler"
    repo = sahte_repo(kok / "r", {"go.mod": "module x\n"})
    db = atlas_db_olustur(tmp_path / "a.db", [repo])
    proc = run_module_cli("tara", cwd=tmp_path, env_ek={**_env(tmp_path), "ATLAS_DB": str(db)})
    assert proc.returncode == 0, proc.stderr
    assert "r" in proc.stdout


def test_tara_olmayan_root_cikis_2(tmp_path):
    """Var olmayan --root yolu: KesifHatasi -> cikis kodu 2."""
    proc = run_module_cli("tara", "--root", str(tmp_path / "yok"), cwd=tmp_path, env_ek=_env(tmp_path))
    assert proc.returncode == KULLANIM_HATASI
    assert "bulunamadi" in proc.stderr


def test_tara_rapor_dizini_env_ile_yonlendirilir(tmp_path):
    """Rapor BAGIMLILIK_DIR'e yazilir; kullanici ~/.bagimlilik'i olusturulmaz."""
    kok = tmp_path / "projeler"
    sahte_repo(kok / "r")
    env = _env(tmp_path)
    proc = run_module_cli("tara", "--root", str(kok), cwd=tmp_path, env_ek=env)
    assert proc.returncode == 0, proc.stderr
    assert (tmp_path / "raporlar" / "son.json").is_file()
    assert env["BAGIMLILIK_DIR"] in proc.stdout


def test_tara_json_ciktisi_gecerli_json(tmp_path):
    """`tara --json` raporu + denetimleri JSON olarak yazar (tablo degil)."""
    kok = tmp_path / "projeler"
    sahte_repo(kok / "r", {"requirements.txt": "flask==0.12\n"})
    proc = run_module_cli("tara", "--root", str(kok), "--json", cwd=tmp_path, env_ek=_env(tmp_path))
    assert proc.returncode == 0, proc.stderr
    veri = json.loads(proc.stdout)
    assert veri["surum"] == 1 and veri["rapor"].endswith("son.json")
    assert veri["repolar"][0]["denetimler"][0]["ekosistem"] == "pip"


def test_tara_rapor_guncellenir(tmp_path):
    """Ikinci tara raporun USTUNE yazar (tek dosya, surekli guncel)."""
    kok = tmp_path / "projeler"
    sahte_repo(kok / "r")
    for _ in range(2):
        assert run_module_cli("tara", "--root", str(kok), cwd=tmp_path, env_ek=_env(tmp_path)).returncode == 0
    assert sorted(p.name for p in (tmp_path / "raporlar").iterdir()) == ["son.json"]


# --------------------------------------------------------------------------
# Genel sozlesme
# --------------------------------------------------------------------------


def test_alt_komut_zorunlu(tmp_path):
    """Alt komut verilmezse argparse hata verir ve cikis kodu 2 doner."""
    proc = run_module_cli(cwd=tmp_path, env_ek=_env(tmp_path))
    assert proc.returncode == KULLANIM_HATASI
    assert "usage" in proc.stderr.lower()


def test_yardim_sifir_cikar(tmp_path):
    """--help cikis kodu 0 verir ve iki komutu listeler."""
    proc = run_module_cli("--help", cwd=tmp_path, env_ek=_env(tmp_path))
    assert proc.returncode == 0
    assert "tara" in proc.stdout and "goster" in proc.stdout
