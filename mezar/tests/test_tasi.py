"""Denetim 1: `mezar_tasi` -- calisma agacinda ne kaldi?"""

from __future__ import annotations

from mezar import tasi

from conftest import yaz


def test_bosaltilmis_repo_mezar_tasi(tmp_path):
    """Pozitif: yalniz README.md kalan repo 'mezar-tasi' sayilir."""
    repo = tmp_path / "r"
    yaz(repo / "README.md", "# arsiv\n")
    sonuc = tasi.denetle(repo)
    assert sonuc["durum"] == "mezar-tasi"
    assert sonuc["not"] is None
    assert sonuc["kalan"] == []


def test_bosaltma_yoksa_bosaltilmis_gorunmuyor(tmp_path):
    """Negatif: README.md disinda dosya varsa 'boşaltılmış görünmüyor' notu düşer."""
    repo = tmp_path / "r"
    yaz(repo / "README.md", "# arsiv\n")
    yaz(repo / "src" / "kod.py", "print(1)\n")
    yaz(repo / "pyproject.toml", "[project]\n")
    sonuc = tasi.denetle(repo)
    assert sonuc["durum"] == "bosaltilmis-gorunmuyor"
    assert sonuc["kalan"] == ["pyproject.toml", "src/kod.py"]
    assert "bosaltilmis gorunmuyor" in sonuc["not"]
    assert "2 dosya var" in sonuc["not"]


def test_git_dizini_ve_kaplar_sayilmaz(tmp_path):
    """`.git`, `.github`, `__pycache__` sayilmaz; gizli klasorler icerik degildir."""
    repo = tmp_path / "r"
    yaz(repo / "README.md", "# arsiv\n")
    yaz(repo / ".git" / "HEAD", "ref: refs/heads/main\n")
    yaz(repo / ".github" / "is.yml", "on: push\n")
    yaz(repo / "__pycache__" / "kod.cpython-311.pyc", "x\n")
    sonuc = tasi.denetle(repo)
    assert sonuc["durum"] == "mezar-tasi", sonuc["not"]


def test_gizli_dosyalar_kalan_dosyalar_da_gorunur(tmp_path):
    """`.git` gizlidir ama `.env` gibi bir dosya KALAN dosyadır."""
    repo = tmp_path / "r"
    yaz(repo / "README.md", "# arsiv\n")
    yaz(repo / ".env", "TOKEN=x\n")
    sonuc = tasi.denetle(repo)
    assert sonuc["kalan"] == [".env"]


def test_cok_fazla_dosyada_not_kisaltir(tmp_path):
    """30 dosyada not ilk 10'u gosterir, toplami dogru yazar."""
    repo = tmp_path / "r"
    yaz(repo / "README.md", "# arsiv\n")
    for i in range(30):
        yaz(repo / f"dosya{i:02d}.txt", "x\n")
    sonuc = tasi.denetle(repo)
    assert len(sonuc["kalan"]) == 30
    assert "+20 tane daha" in sonuc["not"]