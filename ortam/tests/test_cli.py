"""CLI sozlesmesi: `python -m ortam` GERCEKTEN subprocess olarak calistirilir.

Arac SALT OKUNURDUR: `tree_hash` ile komutun dosya sistemini degistirmedigi
her test icin kanitlanir. GIZLI_DEGER hicbir cikti/es hatada gormemelidir.
"""

from __future__ import annotations

import json

from conftest import GIZLI_DEGER, run_module_cli, sahte_repo, tree_hash

KULLANIM_HATASI = 2
BULGU_VAR = 1


def test_tara_bulgu_yok_cikis_0(tmp_path):
    """Bulgu yoksa cikis 0; 'ozet: 0 bulgu' yazilir."""
    kok = tmp_path / "p"
    sahte_repo(kok / "r", {".env.example": "KULLANILIR=\n", "a.py": 'x = os.getenv("KULLANILIR")\n'})
    proc = run_module_cli("tara", "--kok", str(kok), cwd=tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "0 bulgu" in proc.stdout


def test_tara_bulgu_var_cikis_1(tmp_path):
    """Bulgu varsa cikis 1 (dunnya degistirilmez)."""
    kok = tmp_path / "p"
    sahte_repo(kok / "r", {"a.py": 'x = os.environ["BELGEYEN_MI"]\n'})
    proc = run_module_cli("tara", "--kok", str(kok), cwd=tmp_path)
    assert proc.returncode == BULGU_VAR, proc.stdout + proc.stderr
    assert "belgelenmemis" in proc.stdout


def test_tara_tablosu(tmp_path):
    """Tablo modu: tur, repo, ad ve dosya:satir gorunur."""
    kok = tmp_path / "p"
    sahte_repo(kok / "r", {"a.py": 'x = os.environ["ADIM"]\n'})
    proc = run_module_cli("tara", "--kok", str(kok), cwd=tmp_path)
    assert "tur" in proc.stdout and "repo" in proc.stdout
    assert "ADIM" in proc.stdout and "a.py:1" in proc.stdout


def test_tara_json_gecerli_json(tmp_path):
    """`--json` tablo degil JSON yazar; ensure_ascii=False (Turkce karakterler korunur)."""
    kok = tmp_path / "p"
    sahte_repo(kok / "r", {"a.py": 'x = os.environ["ADIM"]\n'})
    proc = run_module_cli("tara", "--kok", str(kok), "--json", cwd=tmp_path)
    assert proc.returncode == BULGU_VAR
    veri = json.loads(proc.stdout)
    assert veri["surum"] == 1 and veri["toplam"] == 1
    assert veri["bulgular"][0]["ad"] == "ADIM"


def test_tara_json_yildiz_isareti_aynen_kalir(tmp_path):
    """--json ciktisinda Turkce karakterler kacirilmaz (ensure_ascii=False).

    Turkce karakter iceren bir `.env` dosya adi `env_gitignorede_degil` bulusunun
    `detay` listesine gecer; JSON'da `\\uXXXX` olarak degil, oldugu gibi durur.
    """
    kok = tmp_path / "p"
    sahte_repo(kok / "r", {".env.çevre": "A=1\n", ".gitignore": "*.log\n"})
    proc = run_module_cli("tara", "--kok", str(kok), "--json", cwd=tmp_path)
    veri = json.loads(proc.stdout)
    detay = next(b for b in veri["bulgular"] if b["tur"] == "env_gitignorede_degil")["detay"]
    assert ".env.çevre" in detay, detay
    assert "\\u00e7" not in proc.stdout


def test_tara_diski_degistirmez(tmp_path):
    """SALT OKUNUR: tarama hicbir dosyayi degistirmez (`.env` de oldugu gibi kalir)."""
    kok = tmp_path / "p"
    repo = sahte_repo(
        kok / "r",
        {".env": f"A={GIZLI_DEGER}\n", ".gitignore": "*.log\n", "a.py": 'x = os.getenv("A")\n'},
    )
    once = tree_hash(repo)
    proc = run_module_cli("tara", "--kok", str(kok), cwd=tmp_path)
    assert proc.returncode == BULGU_VAR
    assert tree_hash(repo) == once, "tarama diski degistirdi"


def test_tara_deger_hicbir_ciktiya_girmez(tmp_path):
    """`.env` icindeki deger ne stdout'a ne stderr'a ne JSON'a gecer."""
    kok = tmp_path / "p"
    sahte_repo(kok / "r", {".env": f"A={GIZLI_DEGER}\n", ".gitignore": "*.log\n"})
    for bayraklar in ([], ["--json"]):
        proc = run_module_cli("tara", "--kok", str(kok), *bayraklar, cwd=tmp_path)
        assert GIZLI_DEGER not in proc.stdout
        assert GIZLI_DEGER not in proc.stderr


def test_tara_birden_fazla_kok(tmp_path):
    """`--kok` tekrarlanabilir: birden fazla kok verilebilir."""
    k1 = tmp_path / "p1"
    k2 = tmp_path / "p2"
    sahte_repo(k1 / "r1", {"a.py": 'x = os.environ["BIR"]\n'})
    sahte_repo(k2 / "r2", {"a.py": 'x = os.environ["IKI"]\n'})
    proc = run_module_cli("tara", "--kok", str(k1), "--kok", str(k2), cwd=tmp_path)
    assert proc.returncode == BULGU_VAR
    assert "2 repo bulundu" in proc.stderr


def test_tara_olmayan_kok_cikis_2(tmp_path):
    """Var olmayan --kok: kesif hatasi -> cikis 2, Turkce 'bulunamadi', iz yok."""
    proc = run_module_cli("tara", "--kok", str(tmp_path / "yok"), cwd=tmp_path)
    assert proc.returncode == KULLANIM_HATASI
    assert "bulunamadi" in proc.stderr
    assert "Traceback" not in proc.stderr


def test_tara_bos_kok_cikis_2(tmp_path):
    """Repo bulunamazsa cikis 2, 'denetlenecek repo bulunamadi'."""
    kok = tmp_path / "bos"
    kok.mkdir()
    proc = run_module_cli("tara", "--kok", str(kok), cwd=tmp_path)
    assert proc.returncode == KULLANIM_HATASI
    assert "denetlenecek repo bulunamadi" in proc.stderr


def test_kok_verilmezse_cikis_2(tmp_path):
    """--kok zorunludur: verilmezse argparse hata verir, cikis 2."""
    proc = run_module_cli("tara", cwd=tmp_path)
    assert proc.returncode == KULLANIM_HATASI


def test_yardim_sifir_cikar(tmp_path):
    """--help cikis kodu 0 verir ve komutu listeler."""
    proc = run_module_cli("--help", cwd=tmp_path)
    assert proc.returncode == 0
    assert "tara" in proc.stdout
