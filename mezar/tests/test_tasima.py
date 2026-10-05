"""Denetim 2: `tasima_tamlik` -- tasinan kod gercekten tasinmis mi?"""

from __future__ import annotations

from mezar import tasima

from conftest import hedef_kopyala, mezar_tasi_repo, yaz

DOSYALAR = {
    "README.md": "# proje\n",
    "pyproject.toml": "[project]\n",
    "src/kod.py": "print(1)\n",
    "docs/rehber.md": "rehber\n",
}


def test_hepsi_tasinmis_tam(tmp_path):
    """Pozitif: tum kaynak dosyalar hedefte ayni goreli yolla var."""
    repo = mezar_tasi_repo(tmp_path, "anlat", DOSYALAR)
    hedef = hedef_kopyala(tmp_path / "araclar", "anlat", DOSYALAR)
    sonuc = tasima.denetle(repo, hedef)
    assert sonuc["durum"] == "tam"
    assert sonuc["kaynak"] == len(DOSYALAR)
    assert sonuc["eksik_sayisi"] == 0


def test_bir_dosya_eksik(tmp_path):
    """Negatif: hedefte olmayan dosya 'eksik' sayilir."""
    repo = mezar_tasi_repo(tmp_path, "anlat", DOSYALAR)
    eksik_kalan = {k: v for k, v in DOSYALAR.items() if k != "src/kod.py"}
    hedef = hedef_kopyala(tmp_path / "araclar", "anlat", eksik_kalan)
    sonuc = tasima.denetle(repo, hedef)
    assert sonuc["durum"] == "eksik-var"
    assert sonuc["eksik_sayisi"] == 1
    assert sonuc["eksik_gosterilen"] == ["src/kod.py"]


def test_yol_degisse_de_eslesir(tmp_path):
    """Hedefte yol degismis olsa da ayni dosya adi eslesir (2. asam)."""
    repo = mezar_tasi_repo(tmp_path, "anlat", DOSYALAR)
    hedef_dosyalar = dict(DOSYALAR)
    # src/kod.py -> lib/kod.py: yol degisti, ad ayni.
    hedef_dosyalar["lib/kod.py"] = hedef_dosyalar.pop("src/kod.py")
    hedef = hedef_kopyala(tmp_path / "araclar", "anlat", hedef_dosyalar)
    sonuc = tasima.denetle(repo, hedef)
    assert sonuc["durum"] == "tam", sonuc["eksik_gosterilen"]


def test_yoksa_yilana_gore_sayilir(tmp_path):
    """Iki kaynak dosya, tek hedef dosya: biri eslesir, DIGERI eksik kalir."""
    kaynak = ["a/mod.py", "b/mod.py"]
    # Tek hedef dosya ikisini birden karsilayamaz.
    assert tasima._eksikleri(kaynak, ["mod.py"]) == ["b/mod.py"]
    # Iki hedef varsa ikisi de eslesir (coklu kopya sayimi korunur).
    assert tasima._eksikleri(kaynak, ["x/mod.py", "y/mod.py"]) == []
    # Ad hic yoksa ikisi de eksik.
    assert tasima._eksikleri(kaynak, ["other.py"]) == ["a/mod.py", "b/mod.py"]


def test_yoksayilanlar_eksik_sayilmaz(tmp_path):
    """`.gitignore`, `__pycache__`, `*.pyc`, `.egg-info` karsilastirmaya girmez."""
    kaynak = {
        ".gitignore": "*.pyc\n",
        "src/kod.py": "x\n",
        "src/__pycache__/kod.pyc": "x\n",
        "src/proj.egg-info/PKG-INFO": "x\n",
        ".pytest_cache/CACHEDIR.TAG": "x\n",
    }
    repo = mezar_tasi_repo(tmp_path, "anlat", kaynak)
    hedef = hedef_kopyala(tmp_path / "araclar", "anlat", {"src/kod.py": "x\n"})
    sonuc = tasima.denetle(repo, hedef)
    assert sonuc["durum"] == "tam", sonuc["eksik_gosterilen"]
    assert sonuc["kaynak"] == 1


def test_head1_yoksa_denetim_atlanir(tmp_path):
    """Tek commit'li repo: HEAD~1 yok -> 'atlandi', sahte pozitif URETILMEZ."""
    repo = tmp_path / "bos"
    repo.mkdir()
    yaz(repo / "README.md", "# tek commit\n")
    from conftest import git

    git(repo, "init", "-q")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "tek")
    hedef = hedef_kopyala(tmp_path / "araclar", "bos", {"README.md": "# tek\n"})
    sonuc = tasima.denetle(repo, hedef)
    assert sonuc["durum"] == "atlandi"
    assert "denetlenemedi" in sonuc["not"]


def test_hedef_dizini_yoksa_hepsi_eksik(tmp_path):
    """Hedef dizin hicbise karsi kurulmadiysa tum kaynak dosyalar eksiktir."""
    repo = mezar_tasi_repo(tmp_path, "anlat", DOSYALAR)
    sonuc = tasima.denetle(repo, tmp_path / "araclar" / "olmayan")
    assert sonuc["durum"] == "eksik-var"
    assert sonuc["eksik_sayisi"] == len(DOSYALAR)


def test_eksik_liste_25_ile_kisitlanir(tmp_path):
    """En cok 25 eksik listelenir; toplam sayi her zaman yazilir."""
    cok = {f"dosya{i:03d}.txt": "x\n" for i in range(40)}
    repo = mezar_tasi_repo(tmp_path, "anlat", cok)
    sonuc = tasima.denetle(repo, tmp_path / "araclar" / "anlat")
    assert sonuc["eksik_sayisi"] == 40
    assert len(sonuc["eksik_gosterilen"]) == 25