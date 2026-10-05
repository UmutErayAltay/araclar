"""kesif: .git isaretli repo bulma, atlas DB okuma, KesifHatasi yollari.

Gercek git CALISTIRILMAZ: kesif yalnizca `.git` varligina bakar, tum dizin
agaci tmp_path altinda kurulur.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest
from conftest import sahte_repo

from olubag.kesif import KesifHatasi, repo_listesi


def test_kok_alti_tum_repolar_bulunur(tmp_path):
    """.git isaretli dizinler repo sayilir; kokun altindaki hepsi listelenir."""
    kok = tmp_path / "projeler"
    sahte_repo(kok / "a")
    sahte_repo(kok / "b")
    assert sorted(p.name for p in repo_listesi([kok])) == ["a", "b"]


def test_kokun_kendisi_repo_sayilir(tmp_path):
    """Verilen kok zaten .git isaretliyse kendisi repo sayilir."""
    repo = sahte_repo(tmp_path / "tek")
    assert repo_listesi([repo]) == [repo]


def test_git_dosya_olarak_işaretli(tmp_path):
    """.git bir DIZIN olmak zorunda degil: worktree/alt modulde dosyadir, yine bulunur."""
    kok = tmp_path / "projeler"
    wt = kok / "worktree-repo"
    wt.mkdir(parents=True)
    (wt / ".git").write_text("gitdir: ../../.git/modules/x\n", encoding="utf-8")
    assert repo_listesi([kok]) == [wt]


def test_node_modules_icine_girilmez(tmp_path):
    """node_modules icindeki .git isaretli dizin GORULMEZ (bagimlilik deposu)."""
    kok = tmp_path / "projeler"
    sahte_repo(kok / "node_modules" / "paket-repo")
    sahte_repo(kok / "gercek")
    assert repo_listesi([kok]) == [kok / "gercek"]


def test_derinlik_siniri(tmp_path):
    """Kesif yalnizca 3 derinlige kadar iner; cok derin repo gorulmez."""
    kok = tmp_path / "projeler"
    sahte_repo(kok / "a" / "b" / "c")
    assert (kok / "a" / "b" / "c") in repo_listesi([kok])
    sahte_repo(kok / "x" / "y" / "z" / "w")
    assert kok / "x" / "y" / "z" / "w" not in repo_listesi([kok])


def test_bos_kok_kesif_hatasi(tmp_path):
    """Bos kok: KesifHatasi."""
    kok = tmp_path / "bos"
    kok.mkdir()
    with pytest.raises(KesifHatasi, match="taranacak repo bulunamadi"):
        repo_listesi([kok])


def test_olmayan_kok_kesif_hatasi(tmp_path):
    """Var olmayan yol: KesifHatasi 'bulunamadi'."""
    with pytest.raises(KesifHatasi, match="bulunamadi"):
        repo_listesi([tmp_path / "yok"])


def test_ayni_repo_tekrarlanmaz(tmp_path):
    """Ayni repo birden fazla kok altinda sayilmissa bir kez doner."""
    kok = tmp_path / "projeler"
    a = sahte_repo(kok / "a" / "repo")
    b = sahte_repo(kok / "b")
    assert repo_listesi([kok, a, b]).count(a) == 1


# --------------------------------------------------------------------------
# atlas DB
# --------------------------------------------------------------------------


def test_atlas_db_yoksa_kesif_hatasi(tmp_path):
    """DB yoksa KesifHatasi; mesaj --kok/atlas tara'ya yonlendirir."""
    with pytest.raises(KesifHatasi) as hata:
        repo_listesi(None, atlas_db=tmp_path / "yok.db")
    assert "--kok" in str(hata.value) and "atlas tara" in str(hata.value)


def test_atlas_db_ile_repo_listesi(tmp_path, monkeypatch):
    """ATLAS_DB ortam degiskeni repo listesini verir."""
    db = tmp_path / "a.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE repos (path TEXT PRIMARY KEY, name TEXT)")
    conn.executemany("INSERT INTO repos (path, name) VALUES (?, ?)", [(str(sahte_repo(tmp_path / n)), n) for n in ("r1", "r2")])
    conn.commit()
    conn.close()
    monkeypatch.setenv("ATLAS_DB", str(db))
    assert sorted(p.name for p in repo_listesi(None)) == ["r1", "r2"]


def test_atlas_db_sifirla_yazmaz(tmp_path):
    """DB salt-okunur acilir: kesif sonrasi DB dosyasi BIRE BIR degismez."""
    db = tmp_path / "a.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE repos (path TEXT PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO repos (path, name) VALUES (?, ?)", (str(sahte_repo(tmp_path / "r")), "r"))
    conn.commit()
    conn.close()
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    repo_listesi(None, atlas_db=db)
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before, "atlas DB'ye yazildi"


def test_atlas_db_okunamazsa_kesif_hatasi(tmp_path):
    """DB var ama gecersiz: kesif patlamaz, KesifHatasi verir."""
    db = tmp_path / "bozuk.db"
    sqlite3.connect(str(db)).close()  # tablo yok
    with pytest.raises(KesifHatasi) as hata:
        repo_listesi(None, atlas_db=db)
    assert "atlas tara" in str(hata.value)