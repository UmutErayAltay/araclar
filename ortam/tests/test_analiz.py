"""analiz: kod <-> belge karsilastirmasi ve dort bulgu turu.

Her bulgu turu icin pozitif ve negatif test.
"""

from __future__ import annotations

import shutil

import pytest
from conftest import GIZLI_DEGER, git_ekle_ve_kaydet, git_kur, sahte_repo, turler

from ortam import analiz

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="bu makinede git yok")


def _tur(veri: dict, tur: str) -> list[dict]:
    return [b for b in veri["bulgular"] if b["tur"] == tur]


# --------------------------------------------------------------------------
# belgelenmemis
# --------------------------------------------------------------------------


def test_belgelenmemis_kodda_var_belgede_yok(tmp_path):
    """Kodda kullanilan ama hicbir yerde adı gecmeyen degisken: bulgu."""
    repo = sahte_repo(tmp_path / "r", {"a.py": 'X = os.environ["GIZLI_AD"]\n'})
    veri = analiz.analiz([repo])
    assert turler(veri) == {"belgelenmemis"}
    bulgu = _tur(veri, "belgelenmemis")[0]
    assert bulgu["ad"] == "GIZLI_AD"
    assert bulgu["dosya"] == "a.py" and bulgu["satir"] == 1


def test_belgelenmemis_negatif_env_exampleda(tmp_path):
    """`.env.example`'da tanimli degisken belgelenmistir: bulgu YOK."""
    repo = sahte_repo(
        tmp_path / "r",
        {".env.example": "TANIMLI=\n", "a.py": 'X = os.environ["TANIMLI"]\n'},
    )
    assert _tur(analiz.analiz([repo]), "belgelenmemis") == []


def test_belgelenmemis_negatif_readmede(tmp_path):
    """README'de adi gecen degisken belgelenmistir: bulgu YOK."""
    repo = sahte_repo(
        tmp_path / "r",
        {"README.md": "`READMEDE_VAR` ayarlanmalidir.\n",
         "a.py": 'X = os.environ["READMEDE_VAR"]\n'},
    )
    assert _tur(analiz.analiz([repo]), "belgelenmemis") == []


def test_belgelenmemis_negatif_compose_da(tmp_path):
    """docker-compose'ta gecen degisken de belgelenmistir: bulgu YOK."""
    repo = sahte_repo(
        tmp_path / "r",
        {
            "docker-compose.yml": "services:\n  app:\n    environment:\n      COMPOSE_ADI: x\n",
            "a.py": 'X = os.environ["COMPOSE_ADI"]\n',
        },
    )
    assert _tur(analiz.analiz([repo]), "belgelenmemis") == []


def test_belgelenmemis_negatif_genel_degisken(tmp_path):
    """PATH/HOME/CI gibi genel degiskenler hicbir yerde gecmese de bulgu YOK."""
    repo = sahte_repo(
        tmp_path / "r", {"a.py": 'a = os.environ["PATH"]\nb = os.getenv("CI")\n'}
    )
    assert _tur(analiz.analiz([repo]), "belgelenmemis") == []


# --------------------------------------------------------------------------
# kullanilmayan
# --------------------------------------------------------------------------


def test_kullanilmayan_env_exampleda_kodda_yok(tmp_path):
    """`.env.example`'da tanimli ama kodda hic gecikmeyen degisken: bulgu."""
    repo = sahte_repo(tmp_path / "r", {".env.example": "KULLANILMAZ=\n"})
    veri = analiz.analiz([repo])
    assert turler(veri) == {"kullanilmayan"}
    assert _tur(veri, "kullanilmayan")[0]["ad"] == "KULLANILMAZ"


def test_kullanilmayan_negatif_kodda_kullaniliyor(tmp_path):
    """Kodda kullanilan degisken `kullanilmayan` DEGILDIR."""
    repo = sahte_repo(
        tmp_path / "r", {".env.example": "KULLANILIR=\n", "a.py": 'x = os.getenv("KULLANILIR")\n'}
    )
    assert _tur(analiz.analiz([repo]), "kullanilmayan") == []


def test_kullanilmayan_negatif_readme_tek_basina(tmp_path):
    """Yalniz README'de gecen bir AD `kullanilmayan` sayilmaz (tanimsiz degisken)."""
    repo = sahte_repo(tmp_path / "r", {"README.md": "`SADECE_README` yazildi.\n"})
    assert _tur(analiz.analiz([repo]), "kullanilmayan") == []


# --------------------------------------------------------------------------
# env_gitignorede_degil
# --------------------------------------------------------------------------


def test_env_gitignorede_degil(tmp_path):
    """Yerel `.env` var ama `.gitignore` kapsamiyor: bulgu."""
    repo = sahte_repo(tmp_path / "r", {".env": f"A={GIZLI_DEGER}\n", ".gitignore": "*.log\n"})
    bulgular = _tur(analiz.analiz([repo]), "env_gitignorede_degil")
    assert len(bulgular) == 1
    assert bulgular[0]["dosya"] == ".env"


def test_env_gitignorede_degil_negatif_gitignore_kapsiyor(tmp_path):
    """`.gitignore` `.env` kapsiyorsa bulgu YOK."""
    repo = sahte_repo(tmp_path / "r", {".env": f"A={GIZLI_DEGER}\n", ".gitignore": ".env\n"})
    assert _tur(analiz.analiz([repo]), "env_gitignorede_degil") == []


def test_env_gitignorede_degil_negatif_env_yok(tmp_path):
    """Yerel `.env` yoksa bulgu YOK (ornek dosya tek basina yeter)."""
    repo = sahte_repo(tmp_path / "r", {".env.example": "A=\n"})
    assert _tur(analiz.analiz([repo]), "env_gitignorede_degil") == []


def test_env_gitignorede_degil_negatif_ornek_env_yeter(tmp_path):
    """Yalniz `.env.example` varsa bulgu YOK: sablon sizinti degildir."""
    repo = sahte_repo(tmp_path / "r", {".env.example": "A=\n", ".gitignore": "node_modules\n"})
    assert _tur(analiz.analiz([repo]), "env_gitignorede_degil") == []


# --------------------------------------------------------------------------
# env_izleniyor
# --------------------------------------------------------------------------


@needs_git
def test_env_izleniyor(tmp_path):
    """Commit'lenmis gercek `.env` izleniyor: bulgu."""
    repo = git_kur(tmp_path / "r")
    (repo / ".env").write_text(f"A={GIZLI_DEGER}\n", encoding="utf-8")
    git_ekle_ve_kaydet(repo, ".env")
    bulgular = _tur(analiz.analiz([repo]), "env_izleniyor")
    assert len(bulgular) == 1 and bulgular[0]["dosya"] == ".env"


@needs_git
def test_env_izleniyor_negatif_ornek_commitli(tmp_path):
    """Commit'lenmis `.env.example` izlenen-ENV sayilmaz."""
    repo = git_kur(tmp_path / "r")
    (repo / ".env.example").write_text("A=\n", encoding="utf-8")
    git_ekle_ve_kaydet(repo, ".env.example")
    assert _tur(analiz.analiz([repo]), "env_izleniyor") == []


@needs_git
def test_env_izleniyor_negatif_izlenmemis_env(tmp_path):
    """`.gitignore`'da olup commit'lenmemis `.env` izlenmiyordur: bulgu YOK."""
    repo = git_kur(tmp_path / "r")
    (repo / ".gitignore").write_text(".env\n", encoding="utf-8")
    (repo / ".env").write_text(f"A={GIZLI_DEGER}\n", encoding="utf-8")
    git_ekle_ve_kaydet(repo, ".gitignore")
    assert _tur(analiz.analiz([repo]), "env_izleniyor") == []


# --------------------------------------------------------------------------
# Genel sozlesme
# --------------------------------------------------------------------------


def test_bos_repo_bulgu_yok(tmp_path):
    """Bos repo: bulgu yok, toplam 0."""
    assert analiz.analiz([sahte_repo(tmp_path / "r")])["toplam"] == 0


def test_dort_tur_ayni_repoda(tmp_path):
    """Dort tur ayni repoda birlikte uretilebilir."""
    repo = git_kur(tmp_path / "r")
    (repo / ".env").write_text(f"A={GIZLI_DEGER}\n", encoding="utf-8")
    (repo / ".gitignore").write_text("*.log\n", encoding="utf-8")
    (repo / ".env.example").write_text("KULLANILMAZ=\n", encoding="utf-8")
    (repo / "a.py").write_text('x = os.environ["BELGEYEN_MI"]\n', encoding="utf-8")
    git_ekle_ve_kaydet(repo, ".env")
    veri = analiz.analiz([repo])
    assert turler(veri) == {"env_izleniyor", "env_gitignorede_degil", "belgelenmemis", "kullanilmayan"}


def test_deger_hicbir_bulguya_girmez(tmp_path):
    """`.env` icindeki deger, raporun HICBIR yerinde gecmez."""
    repo = sahte_repo(tmp_path / "r", {".env": f"AD={GIZLI_DEGER}\n", ".gitignore": "*.log\n"})
    assert GIZLI_DEGER not in repr(analiz.analiz([repo]))


def test_bulgular_kararli_sirali(tmp_path):
    """Ayni turde bulgular AD'a gore sirali doner (cikti kararli olsun)."""
    repo = sahte_repo(tmp_path / "r", {".env.example": "ZZZ=\nAAA=\nMMM=\n"})
    veri = analiz.analiz([repo])
    assert [b["ad"] for b in _tur(veri, "kullanilmayan")] == ["AAA", "MMM", "ZZZ"]
