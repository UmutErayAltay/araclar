"""cli: cikis kodlari, tablo, JSON, hata yollari ve "deger ciktida gecmez" sozlesmesi."""

from __future__ import annotations

import json

from conftest import GIZLI_AWS, GIZLI_SK, repo_kur, run_module_cli, tree_hash


def _repo(tmp_path):
    return repo_kur(
        tmp_path / "r", {"a.py": f'KEY="{GIZLI_SK}"\n', "b.py": "print('temiz')\n"}
    )


def test_tara_bulgu_yok_cikis_0(tmp_path):
    repo = repo_kur(tmp_path / "r", {"a.py": "print('temiz')\n"})
    c = run_module_cli("tara", "--kok", str(repo))
    assert c.returncode == 0
    assert "bulgu yok" in c.stdout


def test_tara_bulgu_var_cikis_1(tmp_path):
    c = run_module_cli("tara", "--kok", str(_repo(tmp_path)))
    assert c.returncode == 1
    assert "a.py:1" in c.stdout
    assert "sk-anahtari" in c.stdout


def test_uygula_kuru_calistirma_dokunmaz(tmp_path):
    repo = _repo(tmp_path)
    once = tree_hash(repo)
    c = run_module_cli("uygula", "--kok", str(repo))
    assert c.returncode == 1
    assert "KURU CALISTIRMA" in c.stdout
    assert tree_hash(repo) == once


def test_uygula_bayrak_maskeler(tmp_path):
    repo = _repo(tmp_path)
    c = run_module_cli("uygula", "--kok", str(repo), "--uygula")
    assert c.returncode == 1
    icerik = (repo / "a.py").read_text(encoding="utf-8")
    assert GIZLI_SK not in icerik
    assert "***MASKELENDI:sk-anahtari***" in icerik


def test_uygula_idempotent_cikis_0(tmp_path):
    repo = _repo(tmp_path)
    run_module_cli("uygula", "--kok", str(repo), "--uygula")
    c = run_module_cli("uygula", "--kok", str(repo), "--uygula")
    assert c.returncode == 0
    assert "bulgu yok" in c.stdout


def test_kok_verilmezse_hata_2():
    c = run_module_cli("tara")
    assert c.returncode == 2
    assert c.stdout == ""
    assert "Hata:" in c.stderr
    assert "Traceback" not in c.stderr


def test_yol_bulunamaz_hata_2(tmp_path):
    c = run_module_cli("tara", "--kok", str(tmp_path / "yok"))
    assert c.returncode == 2
    assert "Hata:" in c.stderr and "Traceback" not in c.stderr


def test_json_bulgular_ve_rotasyon(tmp_path):
    c = run_module_cli("tara", "--kok", str(_repo(tmp_path)), "--json")
    assert c.returncode == 1
    veri = json.loads(c.stdout)
    assert veri["bulgar"][0]["tur"] == "sk-anahtari"
    assert veri["rotasyon"][0]["ad"] == "KEY"
    assert "döndürün" in veri["uyari"]


def test_json_ensure_ascii_false(tmp_path):
    """Turkce karakterler \\uXXXX olarak KACIRILMAZ."""
    c = run_module_cli("tara", "--kok", str(_repo(tmp_path)), "--json")
    assert "döndürün" in c.stdout
    assert "\\u00f6" not in c.stdout


def test_rotasyon_uyarisi_her_zaman_var(tmp_path):
    c = run_module_cli("tara", "--kok", str(_repo(tmp_path)))
    assert "Maskeleme git geçmişini temizlemez; anahtarı sağlayıcıda döndürün." in c.stdout


def test_deger_ciktida_gecmez_stdout_stderr(tmp_path):
    """SOZLESME: sahte secret degeri ne stdout ne stderr'da gecmez."""
    repo = repo_kur(tmp_path / "r", {"a.py": f'K="{GIZLI_SK}"\nAWS={GIZLI_AWS}\n'})
    for ek in ([], ["--json"]):
        for komut in (["tara"], ["uygula"], ["uygula", "--uygula"]):
            c = run_module_cli(komut[0], "--kok", str(repo), *komut[1:], *ek)
            assert GIZLI_SK not in c.stdout + c.stderr
            assert GIZLI_AWS not in c.stdout + c.stderr


def test_hata_yolunda_deger_gecmez(tmp_path):
    """Hata ciktisinda da deger olmaz (dosya adi bile tutmaz)."""
    repo = repo_kur(tmp_path / "r", {f"{GIZLI_SK}.txt": "x\n"})
    c = run_module_cli("tara", "--kok", str(repo))
    assert GIZLI_SK not in c.stdout + c.stderr


def test_birden_fazla_kok_ve_tekrar(tmp_path):
    """`--kok` tekrarlanabilir; ayni kok iki kez verilse bulgu iki kez sayilmaz."""
    repo = _repo(tmp_path)
    c = run_module_cli("tara", "--kok", str(repo), "--kok", str(repo))
    assert c.returncode == 1
    assert len(json.loads(run_module_cli("tara", "--kok", str(repo), "--json").stdout)["bulgar"]) == 1


def test_komsu_kok_derinlikteki_repo(tmp_path):
    """Kok altinda derinlik 3'e kadar ic ice repo bulunur."""
    repo_kur(tmp_path / "a" / "b" / "c", {"a.py": f'KEY="{GIZLI_SK}"\n'})
    c = run_module_cli("tara", "--kok", str(tmp_path / "a"), "--json")
    assert c.returncode == 1
    assert len(json.loads(c.stdout)["bulgar"]) == 1