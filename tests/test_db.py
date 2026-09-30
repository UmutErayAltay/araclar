"""SQLite katmani: sema, UPSERT, silme, listeleme."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from atlas import db as db_mod
from conftest import make_repo


def satir(path: str, name: str, **kw) -> dict:
    taban = {
        "path": path,
        "name": name,
        "dirty": 0,
        "unpushed": 0,
        "branch": "main",
        "last_commit_at": "2024-01-02T03:04:05+00:00",
        "has_remote": 0,
    }
    taban.update(kw)
    return taban


def test_ust_dizin_olusturulur(tmp_path: Path):
    yol = tmp_path / "yeni" / "derin" / "atlas.db"
    conn = db_mod.connect(yol)
    conn.close()
    assert yol.exists()


def test_sema_tablolari_var(tmp_path: Path):
    conn = db_mod.connect(tmp_path / "a.db")
    try:
        adlar = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"repos", "findings", "readme_status", "todos"} <= adlar
    finally:
        conn.close()


def test_sema_sutunlari(tmp_path: Path):
    conn = db_mod.connect(tmp_path / "a.db")
    try:
        kolonlar = {r["name"] for r in conn.execute("PRAGMA table_info(repos)")}
        assert kolonlar == {
            "path", "name", "scanned_at", "dirty", "unpushed",
            "branch", "last_commit_at", "has_remote",
        }
    finally:
        conn.close()


def test_dalga_b_c_d_sutunlari_simdiden_hazir(tmp_path: Path):
    """B/C/D icin gereken sutunlar Dalga A'da da bos olsa da mevcut olmali."""
    conn = db_mod.connect(tmp_path / "a.db")
    try:
        assert {r["name"] for r in conn.execute("PRAGMA table_info(findings)")} == {
            "id", "repo", "kind", "severity", "file", "line", "commit", "snippet_redacted"
        }
        assert {r["name"] for r in conn.execute("PRAGMA table_info(readme_status)")} == {
            "repo", "readme_commit", "behavior_commits_after", "screenshot_age_days"
        }
        assert {r["name"] for r in conn.execute("PRAGMA table_info(todos)")} == {
            "id", "repo", "file", "line", "text"
        }
    finally:
        conn.close()


def test_upsert_ekler(tmp_path: Path):
    conn = db_mod.connect(tmp_path / "a.db")
    try:
        db_mod.upsert_repos(conn, [satir("/a/tek", "tek", dirty=3, unpushed=2, has_remote=1)])
        rows = db_mod.list_repos(conn)
        assert len(rows) == 1
        assert rows[0]["dirty"] == 3
        assert rows[0]["unpushed"] == 2
        assert rows[0]["has_remote"] == 1
    finally:
        conn.close()


def test_yeniden_tarama_cogaltmaz_gunceller(tmp_path: Path):
    conn = db_mod.connect(tmp_path / "a.db")
    try:
        db_mod.upsert_repos(conn, [satir("/a/tek", "tek", dirty=0)])
        db_mod.upsert_repos(conn, [satir("/a/tek", "tek", dirty=5, branch="dal")])
        rows = db_mod.list_repos(conn)
        assert len(rows) == 1
        assert rows[0]["dirty"] == 5
        assert rows[0]["branch"] == "dal"
    finally:
        conn.close()


def test_ayni_ad_farkli_yol_ayri_satir(tmp_path: Path):
    conn = db_mod.connect(tmp_path / "a.db")
    try:
        db_mod.upsert_repos(conn, [satir("/a/x/ortak", "ortak"), satir("/b/x/ortak", "ortak")])
        assert db_mod.count_repos(conn) == 2
    finally:
        conn.close()


def test_delete_missing_repos(tmp_path: Path):
    conn = db_mod.connect(tmp_path / "a.db")
    try:
        db_mod.upsert_repos(conn, [satir("/a/1", "bir"), satir("/a/2", "iki"), satir("/a/3", "uc")])
        silinen = db_mod.delete_missing_repos(conn, ["/a/1", "/a/3"])
        assert silinen == 1
        kalanlar = [r["path"] for r in db_mod.list_repos(conn)]
        assert kalanlar == ["/a/1", "/a/3"]
    finally:
        conn.close()


def test_delete_missing_repos_hepsini_korur(tmp_path: Path):
    conn = db_mod.connect(tmp_path / "a.db")
    try:
        db_mod.upsert_repos(conn, [satir("/a/1", "bir")])
        assert db_mod.delete_missing_repos(conn, ["/a/1"]) == 0
        assert db_mod.count_repos(conn) == 1
    finally:
        conn.close()


def test_upsert_bos_liste_guvenli(tmp_path: Path):
    conn = db_mod.connect(tmp_path / "a.db")
    try:
        db_mod.upsert_repos(conn, [])
        assert db_mod.count_repos(conn) == 0
    finally:
        conn.close()


def test_liste_sadece_yarim(tmp_path: Path):
    conn = db_mod.connect(tmp_path / "a.db")
    try:
        db_mod.upsert_repos(
            conn,
            [
                satir("/a/temiz", "temiz"),
                satir("/a/dirty", "dirty", dirty=1),
                satir("/a/unpushed", "unpushed", unpushed=2, has_remote=1),
            ],
        )
        adlar = sorted(r["name"] for r in db_mod.list_repos(conn, only_dirty=True))
        assert adlar == ["dirty", "unpushed"]
    finally:
        conn.close()


def test_sadece_yarim_remote_suz_tum_commitleri_saymaz(tmp_path: Path):
    """Sozlesme geregi remote'suz repoda unpushed = tum commit sayisi,
    ama bu 'push bekliyor' demek degildir; filtreye girmemeli."""
    conn = db_mod.connect(tmp_path / "a.db")
    try:
        db_mod.upsert_repos(conn, [satir("/a/yerel", "yerel", unpushed=7, has_remote=0)])
        assert db_mod.list_repos(conn, only_dirty=True) == []
        assert len(db_mod.list_repos(conn)) == 1
    finally:
        conn.close()


def test_liste_ada_gore_sirali(tmp_path: Path):
    conn = db_mod.connect(tmp_path / "a.db")
    try:
        db_mod.upsert_repos(conn, [satir("/a/z", "zeta"), satir("/a/a", "alfa"), satir("/a/m", "Mavi")])
        adlar = [r["name"] for r in db_mod.list_repos(conn)]
        assert adlar == ["alfa", "Mavi", "zeta"]  # buyuk/kucuk harf duyarsiz
    finally:
        conn.close()


def test_last_commit_at_null_saklanir(tmp_path: Path):
    conn = db_mod.connect(tmp_path / "a.db")
    try:
        db_mod.upsert_repos(conn, [satir("/a/bos", "bos", last_commit_at=None)])
        assert db_mod.list_repos(conn)[0]["last_commit_at"] is None
    finally:
        conn.close()


def test_db_dosyasi_sonradan_acilabilir(tmp_path: Path):
    yol = tmp_path / "a.db"
    conn = db_mod.connect(yol)
    db_mod.upsert_repos(conn, [satir("/a/1", "bir")])
    conn.close()
    conn2 = sqlite3.connect(str(yol))
    try:
        assert conn2.execute("SELECT COUNT(*) FROM repos").fetchone()[0] == 1
    finally:
        conn2.close()


def test_gercek_repo_tarama_ve_kayit(db_file: Path, tmp_path: Path):
    from atlas.scan import collect_repo

    repo = make_repo(tmp_path / "gercek")
    conn = db_mod.connect(db_file)
    try:
        db_mod.upsert_repos(conn, [collect_repo(repo)])
        rows = db_mod.list_repos(conn)
        assert len(rows) == 1
        assert rows[0]["path"] == str(repo)
        assert rows[0]["scanned_at"]
    finally:
        conn.close()
