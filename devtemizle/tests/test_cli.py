"""CLI sozlesmesi: `python -m devtemizle` GERCEKTEN subprocess olarak calistirilir.

DEVTEMIZLE_DIR ve ATLAS_DB gecici dizine yonlendirilir: kullanicinin
raporu ya da gercek atlas DB'si okunmaz/yazilmaz. Silme testleri de YALNIZCA
tmp_path altindaki sahte repolarda calisir.
"""

from __future__ import annotations

import json
from pathlib import Path

from conftest import atlas_db_olustur, run_module_cli, sahte_aday, sahte_repo, tree_hash

KULLANIM_HATASI = 2


def _env(tmp_path: Path) -> dict[str, str]:
    """CLI alt surecine verilecek izole ortam (rapor + atlas DB gecici)."""
    return {
        "DEVTEMIZLE_DIR": str(tmp_path / "raporlar"),
        "ATLAS_DB": str(tmp_path / "yok-boyle-bir.db"),
    }


# --------------------------------------------------------------------------
# tara
# --------------------------------------------------------------------------


def test_tara_rapor_yazar_ve_cikis_0(tmp_path):
    """`tara --root` cikis 0 doner ve raporu DEVTEMIZLE_DIR/son.json'a yazar."""
    kok = tmp_path / "projeler"
    repo = sahte_repo(kok / "harita", {"package.json": "{}\n"})
    sahte_aday(repo, "node_modules", bayt=100)
    proc = run_module_cli("tara", "--root", str(kok), cwd=tmp_path, env_ek=_env(tmp_path))
    assert proc.returncode == 0, proc.stderr
    rapor = json.loads((tmp_path / "raporlar" / "son.json").read_text(encoding="utf-8"))
    assert rapor["surum"] == 1
    assert [a["tur"] for a in rapor["adaylar"]] == ["node_modules"], rapor
    assert rapor["adaylar"][0]["repo"] == str(repo)


def test_tara_rapor_dizini_env_ile_yonlendirilir(tmp_path):
    """Rapor DEVTEMIZLE_DIR'e yazilir; cikti yolu da orayi gosterir."""
    kok = tmp_path / "projeler"
    repo = sahte_repo(kok / "r")
    sahte_aday(repo, "node_modules")
    env = _env(tmp_path)
    proc = run_module_cli("tara", "--root", str(kok), cwd=tmp_path, env_ek=env)
    assert proc.returncode == 0, proc.stderr
    assert (tmp_path / "raporlar" / "son.json").is_file()
    assert env["DEVTEMIZLE_DIR"] in proc.stdout


def test_tara_json_gecerli_json(tmp_path):
    """`tara --json` raporu JSON olarak yazar (tablo degil)."""
    kok = tmp_path / "projeler"
    repo = sahte_repo(kok / "r")
    sahte_aday(repo, "node_modules", bayt=10)
    proc = run_module_cli(
        "tara", "--root", str(kok), "--json", cwd=tmp_path, env_ek=_env(tmp_path)
    )
    assert proc.returncode == 0, proc.stderr
    veri = json.loads(proc.stdout)
    assert veri["surum"] == 1
    assert [a["tur"] for a in veri["adaylar"]] == ["node_modules"]


def test_tara_olmayan_root_cikis_2(tmp_path):
    """Var olmayan --root yolu: kesif hatasi -> cikis kodu 2, Turkce 'bulunamadi'."""
    proc = run_module_cli(
        "tara", "--root", str(tmp_path / "yok"), cwd=tmp_path, env_ek=_env(tmp_path)
    )
    assert proc.returncode == KULLANIM_HATASI, proc.stdout
    assert "bulunamadi" in proc.stderr


def test_tara_bos_kok_cikis_2(tmp_path):
    """Hic repo bulunamazsa kesif hatasi: cikis 2, 'temizlenecek repo bulunamadi'."""
    kok = tmp_path / "bos"
    kok.mkdir()
    proc = run_module_cli("tara", "--root", str(kok), cwd=tmp_path, env_ek=_env(tmp_path))
    assert proc.returncode == KULLANIM_HATASI
    assert "temizlenecek repo bulunamadi" in proc.stderr


def test_tara_atlas_db_ile_calisir(tmp_path):
    """ATLAS_DB ortam degiskeni repo listesini verir: kesif hatasi olmaz, tarama calisir."""
    repo = sahte_repo(tmp_path / "r")
    sahte_aday(repo, "node_modules")
    db = atlas_db_olustur(tmp_path / "a.db", [repo])
    proc = run_module_cli(
        "tara", cwd=tmp_path, env_ek={**_env(tmp_path), "ATLAS_DB": str(db)}
    )
    assert proc.returncode == 0, proc.stderr
    assert "r" in proc.stdout


def test_tara_atlas_db_yoksa_cikis_2(tmp_path):
    """--root yoksa ATLAS_DB'ye gider; DB de yoksa kesif hatasi, cikis 2."""
    proc = run_module_cli("tara", cwd=tmp_path, env_ek=_env(tmp_path))
    assert proc.returncode == KULLANIM_HATASI
    assert "--root" in proc.stderr and "atlas tara" in proc.stderr


def test_tara_rapor_guncellenir(tmp_path):
    """Ikinci tara raporun USTUNE yazar (tek dosya, surekli guncel, .tmp sizintisi yok)."""
    kok = tmp_path / "projeler"
    repo = sahte_repo(kok / "r")
    sahte_aday(repo, "node_modules")
    for _ in range(2):
        proc = run_module_cli("tara", "--root", str(kok), cwd=tmp_path, env_ek=_env(tmp_path))
        assert proc.returncode == 0, proc.stderr
    assert sorted(p.name for p in (tmp_path / "raporlar").iterdir()) == ["son.json"]


# --------------------------------------------------------------------------
# goster
# --------------------------------------------------------------------------


def test_goster_rapor_yokken_cikis_2(tmp_path):
    """Rapor yoksa `goster` cikis kodu 2 doner, stderr Turkce ve `tara` oner."""
    proc = run_module_cli("goster", cwd=tmp_path, env_ek=_env(tmp_path))
    assert proc.returncode == KULLANIM_HATASI, proc.stdout
    assert "rapor bulunamadi" in proc.stderr
    assert "devtemizle tara" in proc.stderr
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
    kok = tmp_path / "projeler"
    repo = sahte_repo(kok / "r")
    sahte_aday(repo, "node_modules", bayt=10)
    assert (
        run_module_cli("tara", "--root", str(kok), cwd=tmp_path, env_ek=_env(tmp_path)).returncode
        == 0
    )
    proc = run_module_cli("goster", "--json", cwd=tmp_path, env_ek=_env(tmp_path))
    assert proc.returncode == 0, proc.stderr
    veri = json.loads(proc.stdout)
    assert veri["surum"] == 1
    assert [a["tur"] for a in veri["adaylar"]] == ["node_modules"]


def test_goster_tablo_modu_adalari_gosterir(tmp_path):
    """`goster` (json'siz) raporu tabloya cevirir: aday turleri ve ozet gorunur."""
    kok = tmp_path / "projeler"
    repo = sahte_repo(kok / "r")
    sahte_aday(repo, "node_modules", bayt=1536)
    assert (
        run_module_cli("tara", "--root", str(kok), cwd=tmp_path, env_ek=_env(tmp_path)).returncode
        == 0
    )
    proc = run_module_cli("goster", cwd=tmp_path, env_ek=_env(tmp_path))
    assert proc.returncode == 0, proc.stderr
    assert "node_modules" in proc.stdout
    assert "1 aday" in proc.stdout
    assert "1.5 KB" in proc.stdout


# --------------------------------------------------------------------------
# sil
# --------------------------------------------------------------------------


def test_sil_kuru_calistirma_diski_degistirmez(tmp_path):
    """`sil --root R` (--uygula yok): cikis 0, 'KURU CALISTIRMA' uyarisi, disk AYNEN durur."""
    kok = tmp_path / "projeler"
    repo = sahte_repo(kok / "r", {"index.js": "kaynak\n"})
    sahte_aday(repo, "node_modules", bayt=100)
    sahte_aday(repo, "__pycache__", bayt=50)
    once = tree_hash(repo)
    proc = run_module_cli("sil", "--root", str(kok), cwd=tmp_path, env_ek=_env(tmp_path))
    assert proc.returncode == 0, proc.stderr
    assert "KURU CALISTIRMA" in proc.stdout
    assert tree_hash(repo) == once, "kuru calistirma diski degistirdi"
    assert (repo / "node_modules").is_dir() and (repo / "index.js").is_file()


def test_sil_uygula_gercekten_siler(tmp_path):
    """`sil --root R --uygula --yas 0`: cikis 0, node_modules GERCEKTEN gider."""
    kok = tmp_path / "projeler"
    repo = sahte_repo(kok / "r", {"index.js": "kaynak\n"})
    sahte_aday(repo, "node_modules", bayt=100)
    proc = run_module_cli(
        "sil", "--root", str(kok), "--uygula", "--yas", "0", cwd=tmp_path, env_ek=_env(tmp_path)
    )
    assert proc.returncode == 0, proc.stderr
    assert not (repo / "node_modules").exists(), "node_modules silinmedi"
    assert (repo / "index.js").is_file() and (repo / ".git").is_dir(), "kaynak/.git etkilendi"


def test_sil_uygula_ozet_silindi_diyor(tmp_path):
    """`sil --uygula` ciktisinda 'silindi' sayaci gorunur (kuru calistirma ciktisi DEGIL)."""
    kok = tmp_path / "projeler"
    repo = sahte_repo(kok / "r")
    sahte_aday(repo, "node_modules", bayt=100)
    proc = run_module_cli(
        "sil", "--root", str(kok), "--uygula", "--yas", "0", cwd=tmp_path, env_ek=_env(tmp_path)
    )
    assert proc.returncode == 0, proc.stderr
    assert "silindi" in proc.stdout
    assert "KURU CALISTIRMA" not in proc.stdout


def test_sil_tur_filtresi_yalniz_isteneni_siler(tmp_path):
    """`sil --uygula --tur node_modules`: yalniz node_modules gider, __pycache__ KALIR."""
    kok = tmp_path / "projeler"
    repo = sahte_repo(kok / "r")
    sahte_aday(repo, "node_modules", bayt=100)
    sahte_aday(repo, "__pycache__", bayt=50)
    proc = run_module_cli(
        "sil", "--root", str(kok), "--uygula", "--yas", "0", "--tur", "node_modules",
        cwd=tmp_path, env_ek=_env(tmp_path),
    )
    assert proc.returncode == 0, proc.stderr
    assert not (repo / "node_modules").exists()
    assert (repo / "__pycache__").is_dir(), "istenmeyen tur silindi"


def test_sil_tur_birden_fazla_gecerli(tmp_path):
    """`--tur` tekrar edilebilir: birden fazla tur verilebilir."""
    kok = tmp_path / "projeler"
    repo = sahte_repo(kok / "r")
    sahte_aday(repo, "node_modules", bayt=10)
    sahte_aday(repo, "__pycache__", bayt=10)
    proc = run_module_cli(
        "sil", "--root", str(kok), "--uygula", "--yas", "0",
        "--tur", "node_modules", "--tur", "__pycache__",
        cwd=tmp_path, env_ek=_env(tmp_path),
    )
    assert proc.returncode == 0, proc.stderr
    assert not (repo / "node_modules").exists()
    assert not (repo / "__pycache__").exists()


def test_sil_negatif_yas_cikis_2(tmp_path):
    """`--yas -1`: gecersiz deger, argparse hata verir, cikis kodu 2, hicbir sey silinmez."""
    kok = tmp_path / "projeler"
    repo = sahte_repo(kok / "r")
    sahte_aday(repo, "node_modules", bayt=10)
    once = tree_hash(repo)
    proc = run_module_cli(
        "sil", "--root", str(kok), "--uygula", "--yas", "-1", cwd=tmp_path, env_ek=_env(tmp_path)
    )
    assert proc.returncode == KULLANIM_HATASI, proc.stdout
    assert tree_hash(repo) == once, "gecersiz --yas yine de bir sey sildi"


def test_sil_olmayan_root_cikis_2(tmp_path):
    """Var olmayan --root yolu: kesif hatasi -> cikis 2."""
    proc = run_module_cli(
        "sil", "--root", str(tmp_path / "yok"), cwd=tmp_path, env_ek=_env(tmp_path)
    )
    assert proc.returncode == KULLANIM_HATASI
    assert "bulunamadi" in proc.stderr


def test_sil_bos_kok_cikis_2(tmp_path):
    """Hic repo yoksa kesif hatasi: cikis 2, 'temizlenecek repo bulunamadi'."""
    kok = tmp_path / "bos"
    kok.mkdir()
    proc = run_module_cli("sil", "--root", str(kok), cwd=tmp_path, env_ek=_env(tmp_path))
    assert proc.returncode == KULLANIM_HATASI
    assert "temizlenecek repo bulunamadi" in proc.stderr


def test_sil_rapor_yazmaz(tmp_path):
    """`sil` rapor YAZMAZ: rapor yalniz `tara` ciktisidir; `sil` diske dokundugu icin bayat kalir.

    Kullanici diskte ne oldugunu `tara` ile yeniden olcer; `sil` ozetini
    stdout'ta verir.
    """
    kok = tmp_path / "projeler"
    repo = sahte_repo(kok / "r")
    sahte_aday(repo, "node_modules", bayt=100)
    proc = run_module_cli(
        "sil", "--root", str(kok), "--uygula", "--yas", "0", cwd=tmp_path, env_ek=_env(tmp_path)
    )
    assert proc.returncode == 0, proc.stderr
    assert not (tmp_path / "raporlar" / "son.json").exists(), "sil rapor yazdi"


# --------------------------------------------------------------------------
# Genel sozlesme
# --------------------------------------------------------------------------


def test_alt_komut_zorunlu(tmp_path):
    """Alt komut verilmezse argparse hata verir ve cikis kodu 2 doner."""
    proc = run_module_cli(cwd=tmp_path, env_ek=_env(tmp_path))
    assert proc.returncode == KULLANIM_HATASI
    assert "usage" in proc.stderr.lower()


def test_yardim_sifir_cikar(tmp_path):
    """--help cikis kodu 0 verir ve komutlari listeler."""
    proc = run_module_cli("--help", cwd=tmp_path, env_ek=_env(tmp_path))
    assert proc.returncode == 0
    for komut in ("tara", "goster", "sil"):
        assert komut in proc.stdout, komut


def test_bilinmeyen_alt_komut_cikis_2(tmp_path):
    """Bilinmeyen alt komut: argparse hata, cikis 2."""
    proc = run_module_cli("uydur", cwd=tmp_path, env_ek=_env(tmp_path))
    assert proc.returncode == KULLANIM_HATASI

def test_sil_id_rapor_yoksa_cikis_1(tmp_path):
    """sil --id: rapor yoksa Turkce 'rapor yok' hatasi, cikis kodu 1 (sessiz 'silindi 0' degil)."""
    proc = run_module_cli(
        "sil", "--id", "abcdef12", "--uygula", cwd=tmp_path,
        env_ek={"DEVTEMIZLE_DIR": str(tmp_path / "yok")},
    )
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "rapor yok" in proc.stderr
    assert "devtemizle tara" in proc.stderr
