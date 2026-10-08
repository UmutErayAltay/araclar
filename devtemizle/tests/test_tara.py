"""tara: temizlenebilir aday bulma, boyut/yas hesabi, atlandi nedenleri.

Gercek disk yazimi tmp_path altindadir; silme YAPILMAZ (tara salt-okunur).
Aday yaslari: simdi= parametresi verilerek yaS KONTROL altindadir, aksi halde
dosya sistemi zamanina birakilir.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path

import pytest
from conftest import eskit, sahte_aday, sahte_repo

from devtemizle import tara as tara_mod
from devtemizle.tara import tara

GUN = 86400.0


# --------------------------------------------------------------------------
# Aday listesi
# --------------------------------------------------------------------------


def test_bes_turun_de_aday_bulunur(tmp_path):
    """Sozlesmedeki bes turun tamami aday olarak raporlanir."""
    repo = sahte_repo(tmp_path / "r")
    for tur in ("node_modules", "__pycache__", ".pytest_cache", ".venv", "venv"):
        sahte_aday(repo, tur, pyvenv_cfg=True)
    adaylar = tara([repo])
    assert sorted(a["tur"] for a in adaylar) == sorted(
        ["node_modules", "__pycache__", ".pytest_cache", ".venv", "venv"]
    )


def test_aday_karti_alanlari(tmp_path):
    """Aday karti sozlesmedeki yedi alani tasir ve yol gercek diskte var."""
    repo = sahte_repo(tmp_path / "r")
    yol = sahte_aday(repo, "node_modules")
    aday = tara([repo])[0]
    assert set(aday) == {"repo", "yol", "tur", "boyut", "son_erisim", "yas_gun", "atlandi"}
    assert aday["repo"] == str(repo)
    assert Path(aday["yol"]) == yol and Path(aday["yol"]).is_dir()
    assert aday["tur"] == "node_modules"


def test_temiz_repo_hic_aday_yok(tmp_path):
    """Aday turu icermeyen repoda aday donmez (bos liste, hata DEGIL)."""
    repo = sahte_repo(tmp_path / "r", {"package.json": "{}\n", "index.js": "x\n"})
    assert tara([repo]) == []


def test_bir_repoda_birden_fazla_aday(tmp_path):
    """Ayni repodaki her tur ayri aday olur; adaylar tekrarlanmaz."""
    repo = sahte_repo(tmp_path / "r")
    sahte_aday(repo, "node_modules")
    (repo / "sub").mkdir()
    sahte_aday(repo / "sub", "__pycache__")
    adaylar = tara([repo])
    assert len(adaylar) == 2
    assert sorted(a["tur"] for a in adaylar) == ["__pycache__", "node_modules"]


def test_node_modules_icine_girilmez(tmp_path):
    """Ic ice aday tek tek raporlanmaz: node_modules'in icindeki node_modules gormez.

    Ust aday silinince altindakiler de gidecegi icin ikinci bir kayit yaniltir.
    """
    repo = sahte_repo(tmp_path / "r")
    ust = sahte_aday(repo, "node_modules")
    (ust / "paket" / "node_modules").mkdir(parents=True)
    (ust / "paket" / "node_modules" / "paket.js").write_bytes(b"x" * 9)
    adaylar = tara([repo])
    assert [a["yol"] for a in adaylar] == [str(ust)]


def test_birden_fazla_repo_taranir(tmp_path):
    """repolar listesi sirayla taranir, adaylar tum repolardan gelir."""
    kok = tmp_path / "projeler"
    a = sahte_repo(kok / "a")
    b = sahte_repo(kok / "b")
    sahte_aday(a, "node_modules")
    sahte_aday(b, "__pycache__")
    adaylar = tara([a, b])
    assert sorted(a_["repo"] for a_ in adaylar) == sorted([str(a), str(b)])


# --------------------------------------------------------------------------
# boyut
# --------------------------------------------------------------------------


def test_boyut_dosya_boyutlari_toplami(tmp_path):
    """boyut = aday icindeki tum dosyalarin (dosya) boyutu toplami."""
    repo = sahte_repo(tmp_path / "r")
    yol = sahte_aday(repo, "node_modules", bayt=100)
    (yol / "a.js").write_bytes(b"x" * 20)
    (yol / "alt").mkdir()
    (yol / "alt" / "b.js").write_bytes(b"x" * 30)
    assert tara([repo])[0]["boyut"] == 150


def test_boyut_bos_aday_sifir(tmp_path):
    """Icinde dosya olmayan aday: boyut 0 (silinecek bos alan)."""
    repo = sahte_repo(tmp_path / "r")
    (repo / "__pycache__").mkdir()
    assert tara([repo])[0]["boyut"] == 0


# --------------------------------------------------------------------------
# yas
# --------------------------------------------------------------------------


def test_yas_gun_simdi_erisim_farki(tmp_path):
    """yas_gun = (simdi - son_erisim) / 86400."""
    repo = sahte_repo(tmp_path / "r")
    sahte_aday(repo, "node_modules")
    simdi = time.time()
    eskit(repo / "node_modules", 10.0, simdi)
    aday = tara([repo], simdi=simdi)[0]
    assert abs(aday["yas_gun"] - 10.0) < 0.01, aday["yas_gun"]


def test_son_erisim_iso_tarih(tmp_path):
    """son_erisim raporlanabilir bir ISO-8601 zaman damgasidir (rapor JSON'unda metin)."""
    repo = sahte_repo(tmp_path / "r")
    sahte_aday(repo, "node_modules")
    simdi = time.time()
    eskit(repo / "node_modules", 10.0, simdi)
    aday = tara([repo], simdi=simdi)[0]
    an = datetime.fromisoformat(aday["son_erisim"])
    assert an.tzinfo is not None, "son erisim timezone'lu olmali"
    assert abs(an.timestamp() - (simdi - 10.0 * GUN)) < 2.0


def test_taze_aday_yas_sifira_yakin(tmp_path):
    """Yeni kurulmus aday yasi ~0 gundur (simdi verilmeden de calisir)."""
    repo = sahte_repo(tmp_path / "r")
    sahte_aday(repo, "node_modules")
    assert tara([repo])[0]["yas_gun"] < 1.0


# --------------------------------------------------------------------------
# atlandi nedenleri
# --------------------------------------------------------------------------


def test_baglanti_tespiti_reparse_point_da_gecerli(tmp_path, monkeypatch):
    """Windows junction (reparse point) de baglanti sayilir: symlink izni gerekmez.

    os.lstat bos donerse tara onu normal dizin sanir; o durumda `baglanti`
    yerine aday boyutu 0 ile raporlanir. Test, kaynagin REPARSE_POINT'e
    baktigini dogrular.
    """
    from devtemizle import tara as tara_modulu

    repo = sahte_repo(tmp_path / "r")
    sahte_aday(repo, "node_modules", bayt=10)
    monkeypatch.setattr(tara_modulu, "_baglanti", lambda yol: True)
    aday = tara([repo])[0]
    assert aday["atlandi"] == "baglanti", aday
    assert aday["boyut"] == 0


def test_baglanti_adayi_atlandi_ve_boyut_sifir(tmp_path, symlink_kur):
    """node_modules baglantiysa (symlink) atlandi='baglanti', boyut 0: hedef silinmez."""
    repo = sahte_repo(tmp_path / "r")
    hedef = tmp_path / "hedef-depo"
    sahte_repo(hedef, {"paket.js": "x"})
    symlink_kur(hedef, "node_modules", ust=repo)
    aday = tara([repo])[0]
    assert aday["tur"] == "node_modules"
    assert aday["atlandi"] == "baglanti", aday
    assert aday["boyut"] == 0


def test_pyvenv_cfg_olmayan_venv_atlandi(tmp_path):
    """.venv/venv icinde pyvenv.cfg yoksa atlandi='pyvenv-yok' (sirf venv adli klasor degil)."""
    repo = sahte_repo(tmp_path / "r")
    sahte_aday(repo, ".venv")
    sahte_aday(repo, "venv")
    assert sorted(a["atlandi"] for a in tara([repo])) == ["pyvenv-yok", "pyvenv-yok"]


def test_pyvenv_cfg_olan_venv_adaydir(tmp_path):
    """pyvenv.cfg varsa .venv/venv normal adaydir (atlandi bos)."""
    repo = sahte_repo(tmp_path / "r")
    sahte_aday(repo, ".venv", pyvenv_cfg=True)
    sahte_aday(repo, "venv", pyvenv_cfg=True)
    adaylar = tara([repo])
    assert len(adaylar) == 2
    assert not any(a["atlandi"] for a in adaylar), adaylar


def test_normal_adayin_atlandisi_yok(tmp_path):
    """node_modules/__pycache__ gibi adaylarin atlandi alani bos (None) gelir."""
    repo = sahte_repo(tmp_path / "r")
    sahte_aday(repo, "node_modules")
    sahte_aday(repo, "__pycache__")
    for aday in tara([repo]):
        assert not aday["atlandi"], aday


def test_tara_atlandiyi_ayiklamaz(tmp_path, symlink_kur):
    """tara ATLANAN adayi da listeler: kullanici neyin neden silinmedigini gorur."""
    repo = sahte_repo(tmp_path / "r")
    hedef = sahte_repo(tmp_path / "hedef")
    symlink_kur(hedef, "node_modules", ust=repo)
    sahte_aday(repo, "__pycache__")
    adaylar = tara([repo])
    assert {a["tur"]: a["atlandi"] for a in adaylar} == {
        "node_modules": "baglanti",
        "__pycache__": None,
    }

# --------------------------------------------------------------------------
# Regresyon: kardes kanit, izlenen dosya, yas (iz + commit, negatif yok), sert baglanti
# --------------------------------------------------------------------------


def _aday(repo, tur):
    return next(a for a in tara([repo]) if a["tur"] == tur)


def test_kanit_repo_koku_degil_kardes_dosyadir(tmp_path):
    """package.json kokte var ama coverage src/ altinda: kardesi yok -> kanit-yok."""
    repo = sahte_repo(tmp_path / "r", {"package.json": "{}"})
    (repo / "src" / "coverage").mkdir(parents=True)
    (repo / "src" / "coverage" / "mod.js").write_text("kaynak", encoding="utf-8")
    assert _aday(repo, "coverage")["atlandi"] == "kanit-yok"


def test_cargo_kanit_alt_dizinde_bulunmaz(tmp_path):
    """Cargo.toml kokte; tools/target kardesi Cargo.toml'siz -> kanit-yok."""
    repo = sahte_repo(tmp_path / "r", {"Cargo.toml": "[package]\n"})
    (repo / "tools" / "target").mkdir(parents=True)
    (repo / "tools" / "target" / "x.rs").write_text("", encoding="utf-8")
    assert _aday(repo, "target")["atlandi"] == "kanit-yok"


def test_pyproject_kokte_docs_dist_kanit_sayilmaz(tmp_path):
    """pyproject.toml kokte; docs/dist'in kardesi yok -> kanit-yok."""
    repo = sahte_repo(tmp_path / "r", {"pyproject.toml": "[project]\n"})
    (repo / "docs" / "dist").mkdir(parents=True)
    (repo / "docs" / "dist" / "a.txt").write_text("", encoding="utf-8")
    assert _aday(repo, "dist")["atlandi"] == "kanit-yok"


def test_htmlcov_kardes_kanitsiz_atlanir(tmp_path):
    """htmlcov kanitsiz aday degildir; kardes pyproject.toml ile aday olur."""
    repo = sahte_repo(tmp_path / "r")
    sahte_aday(repo, "htmlcov")
    assert _aday(repo, "htmlcov")["atlandi"] == "kanit-yok"
    (repo / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    assert _aday(repo, "htmlcov")["atlandi"] is None


def test_git_izlenen_dosya_iceren_aday_atlanir(tmp_path, monkeypatch):
    """git ls-files izlenen dosya dondururse aday atlanir (silme yok)."""
    repo = sahte_repo(tmp_path / "r", {"package.json": "{}"})
    sahte_aday(repo, "node_modules")
    cagrilar = []

    def sahte_calistir(args, **_kw):
        cagrilar.append(list(args))
        if "ls-files" in args:
            return subprocess.CompletedProcess(args, 0, stdout="node_modules/paket.js\n", stderr="")
        return subprocess.CompletedProcess(args, 128, stdout="", stderr="")

    monkeypatch.setattr(tara_mod.shutil, "which", lambda _ad: "/usr/bin/git")
    monkeypatch.setattr(tara_mod.subprocess, "run", sahte_calistir)
    assert _aday(repo, "node_modules")["atlandi"] == "izlenen-dosya"
    assert any("ls-files" in c for c in cagrilar)


def test_git_yoksa_izlenen_kontrolu_atlanmaz(tmp_path, monkeypatch):
    """git PATH'te yoksa izlenen-dosya denetimi yapilmaz; aday atlanmaz."""
    repo = sahte_repo(tmp_path / "r")
    sahte_aday(repo, "node_modules")
    monkeypatch.setattr(tara_mod.shutil, "which", lambda _ad: None)

    def git_cagrilmamali(*_a, **_k):
        raise AssertionError("git yokken calistirilmamali")

    monkeypatch.setattr(tara_mod.subprocess, "run", git_cagrilmamali)
    assert _aday(repo, "node_modules")["atlandi"] is None


def test_yas_ust_duzey_iz_en_yeni_zamani_alir(tmp_path):
    """Adayin dizini eski ama pyvenv/.yarn-integrity gibi taze bir iz varsa yas taze sayilir."""
    simdi = time.time()
    repo = sahte_repo(tmp_path / "r")
    yol = sahte_aday(repo, "node_modules")
    (yol / ".yarn-integrity").write_text("x", encoding="utf-8")
    eskit(yol, 30, simdi)
    assert tara([repo], simdi=simdi)[0]["yas_gun"] < 1.0


def test_repo_son_commit_yas_hesabina_girer(tmp_path, monkeypatch):
    """Reponun son commit zamani (2 gun once) aday dizini 30 gun eski olsa da yasi belirler."""
    simdi = time.time()
    repo = sahte_repo(tmp_path / "r")
    yol = sahte_aday(repo, "node_modules")
    eskit(yol, 30, simdi)
    monkeypatch.setattr(tara_mod, "_son_commit_zamani", lambda _repo: simdi - 2 * 86400, raising=False)
    assert abs(tara([repo], simdi=simdi)[0]["yas_gun"] - 2.0) < 0.01


def test_negatif_yas_sifira_kenetlenir(tmp_path):
    """simdi, son erisimden once ise yas negatif degil 0'dir."""
    repo = sahte_repo(tmp_path / "r")
    sahte_aday(repo, "node_modules")
    assert tara([repo], simdi=time.time() - 10 * 86400)[0]["yas_gun"] == 0.0


def test_sert_baglanti_boyutu_bir_kez_sayilir(tmp_path):
    """Ayni inode'a iki ad (sert baglanti) boyuta iki kez girmez."""
    repo = sahte_repo(tmp_path / "r")
    yol = sahte_aday(repo, "node_modules", bayt=100)
    try:
        os.link(yol / "paket.js", yol / "ayni.js")
    except (OSError, NotImplementedError):
        pytest.skip("sert baglanti olusturulamadi")
    assert _aday(repo, "node_modules")["boyut"] == 100
