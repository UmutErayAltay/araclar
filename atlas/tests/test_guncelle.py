"""Dalga C / `atlas guncelle`: `tara` + `sizinti` + `borc` — TEK komut.

Kanıtlanan davranışlar:
  * Tek komut ÜÇ tabloyu doldurur (gerçek subprocess, sahte istemci yok).
  * Mevcut komutların davranışı DEĞİŞMEZ (`tara`/`sizinti`/`borc` ayrı ayrı
    hâlâ aynı çıktıyı verir).
  * Salt-okunurluk: `guncelle` öncesi/sonrası fixture repo ağacı bayt bayt aynı.
  * Ham sır DB'de/çıktıda yok.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from conftest import commit_file, make_repo, run_module_cli, sahte_sir, tree_hash


@pytest.fixture
def uc_tablolu_kok(tmp_path: Path) -> Path:
    """Üç tablonun da dolacağı gerçek repolar."""
    kok = tmp_path / "koklar"
    temiz = make_repo(kok / "temiz-repo")
    commit_file(temiz, "notlar.md", "# TODO: dokumantasyon eksik\n", "not ekle")

    sizintili = make_repo(kok / "anahtarli-repo")
    commit_file(sizintili, "ayar.py", f'API_KEY = "{sahte_sir()}"\n', "ayar ekle")

    (kok / "temiz-repo" / "README.md").write_text("# degistirildi\n", encoding="utf-8")
    return kok


def _sayar(db: Path) -> dict[str, int]:
    con = sqlite3.connect(db)
    try:
        return {
            "repos": con.execute("SELECT COUNT(*) FROM repos").fetchone()[0],
            "findings": con.execute("SELECT COUNT(*) FROM findings").fetchone()[0],
            "todos": con.execute("SELECT COUNT(*) FROM todos").fetchone()[0],
        }
    finally:
        con.close()


def test_guncelle_uc_tablu_doldurur(uc_tablolu_kok: Path, db_file: Path):
    proc = run_module_cli("guncelle", "--root", str(uc_tablolu_kok), "--db", str(db_file))
    assert proc.returncode == 0, proc.stderr
    sayi = _sayar(db_file)
    assert sayi["repos"] == 2
    assert sayi["findings"] >= 1
    assert sayi["todos"] == 1


def test_guncelle_bes_asamayi_basar(uc_tablolu_kok: Path, db_file: Path):
    proc = run_module_cli("guncelle", "--root", str(uc_tablolu_kok), "--db", str(db_file))
    assert "1/5: repo taramasi" in proc.stdout
    assert "2/5: sizinti taramasi" in proc.stdout
    assert "3/5: TODO/FIXME borcu" in proc.stdout
    assert "4/5: README bayatligi" in proc.stdout
    assert "5/5: yerel 'simdi ne yapmali' ozeti (agsiz)" in proc.stdout


def test_guncelle_salt_okunur(uc_tablolu_kok: Path, db_file: Path):
    """Tarama fixture repolarını bayt bayt DEĞİŞTİRMEZ."""
    once = {r: tree_hash(r) for r in sorted(uc_tablolu_kok.iterdir())}
    proc = run_module_cli("guncelle", "--root", str(uc_tablolu_kok), "--db", str(db_file))
    assert proc.returncode == 0, proc.stderr
    for repo, beklenen in once.items():
        assert beklenen == tree_hash(repo), f"{repo.name} guncelle ile degisti"


def test_guncelle_sonrasi_repo_degistirilmez(uc_tablolu_kok: Path, db_file: Path):
    """İKİNCİ `guncelle` de aynı sonucu üretir (idempotent, tekrarlanabilir)."""
    run_module_cli("guncelle", "--root", str(uc_tablolu_kok), "--db", str(db_file))
    ilk = _sayar(db_file)
    hash_ilk = tree_hash(uc_tablolu_kok / "temiz-repo")
    proc = run_module_cli("guncelle", "--root", str(uc_tablolu_kok), "--db", str(db_file))
    assert proc.returncode == 0, proc.stderr
    assert _sayar(db_file) == ilk, "ikinci calistirma farkli sonuc verdi"
    assert tree_hash(uc_tablolu_kok / "temiz-repo") == hash_ilk


def test_guncelle_ham_sir_yazmaz(uc_tablolu_kok: Path, db_file: Path):
    proc = run_module_cli("guncelle", "--root", str(uc_tablolu_kok), "--db", str(db_file))
    assert proc.returncode == 0, proc.stderr
    sir = sahte_sir()
    ham = db_file.read_bytes() + proc.stdout.encode() + proc.stderr.encode()
    assert sir.encode() not in ham
    assert sir[:6].encode() not in ham


def test_guncelle_gecmis_secenegi(uc_tablolu_kok: Path, db_file: Path):
    """`--gecmis` sizinti adimina gecer."""
    proc = run_module_cli(
        "guncelle", "--root", str(uc_tablolu_kok), "--db", str(db_file), "--gecmis", "5"
    )
    assert proc.returncode == 0, proc.stderr


def test_ayri_komutlar_davranis_degismez(uc_tablolu_kok: Path, db_file: Path):
    """`guncelle` mevcut komutların YERINE geçmez: ayrı çalışma aynı tabloyu verir."""
    # 1) ayrı ayrı
    for args in (
        ("tara", "--root", str(uc_tablolu_kok)),
        ("sizinti", "--root", str(uc_tablolu_kok)),
        ("borc", "--root", str(uc_tablolu_kok)),
    ):
        proc = run_module_cli(*args, "--db", str(db_file))
        assert proc.returncode == 0, proc.stderr
    ayri = _sayar(db_file)

    # 2) guncelle (ayni DB, sifirdan)
    db2 = db_file.with_name("ikinci.db")
    proc = run_module_cli("guncelle", "--root", str(uc_tablolu_kok), "--db", str(db2))
    assert proc.returncode == 0, proc.stderr
    assert _sayar(db2) == ayri, "guncelle farkli tablo doldurdu"


def test_tara_liste_henuz_calismadi(db_file: Path):
    """`liste` DB yoksa uyari verir (davranis degismedi)."""
    proc = run_module_cli("liste", "--db", str(db_file))
    assert proc.returncode == 1
    assert "Once 'atlas tara'" in proc.stderr


def test_borc_komutu_liste_gerektirmez(uc_tablolu_kok: Path, db_file: Path):
    """`borc` yalniz kendi tablosunu doldurur; `tara` gerekmez."""
    proc = run_module_cli("borc", "--root", str(uc_tablolu_kok), "--db", str(db_file))
    assert proc.returncode == 0, proc.stderr
    assert _sayar(db_file)["todos"] == 1


def test_guncelle_bos_kok(tmp_path: Path, db_file: Path):
    bos = tmp_path / "bos-kok"
    bos.mkdir()
    proc = run_module_cli("guncelle", "--root", str(bos), "--db", str(db_file))
    assert proc.returncode == 0, proc.stderr
    assert _sayar(db_file) == {"repos": 0, "findings": 0, "todos": 0}