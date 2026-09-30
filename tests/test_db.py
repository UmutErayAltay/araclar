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
        # `readme_status` artık Dalga D sütunlarını da İÇERİR (skor, seviye,
        # gorsel yaşı vb.); eski sütunlar yerinde KALIR (geriye uyum).
        assert {r["name"] for r in conn.execute("PRAGMA table_info(readme_status)")} == {
            "repo", "readme_commit", "behavior_commits_after", "screenshot_age_days",
            "readme_yolu", "readme_commit_tarihi", "skor", "seviye",
            "eksik_gorsel", "neden", "tarandi",
        }
        assert {r["name"] for r in conn.execute("PRAGMA table_info(todos)")} == {
            "id", "repo", "file", "line", "text"
        }
        assert "summaries" in {
            r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
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


def test_sadece_yarim_null_unpushedi_disarida_birakir(tmp_path: Path):
    """`unpushed` NULL (bilinmiyor) olan repo filtreye GIRMEZ.

    Gerekce: `dirty > 0 OR (NULL > 0 AND ...)` -> NULL, WHERE yalnizca TRUE kabul
    eder. Yani "bilinmiyor" asla "yarim is" sayilmaz.
    """
    conn = db_mod.connect(tmp_path / "a.db")
    try:
        db_mod.upsert_repos(
            conn,
            [
                satir("/a/bilinmeyen", "bilinmeyen", unpushed=None, has_remote=1),
                satir("/a/bilinmeyen-dirty", "bilinmeyen-dirty", dirty=2, unpushed=None, has_remote=1),
                satir("/a/temiz", "temiz"),
                satir("/a/push-bekleyen", "push-bekleyen", unpushed=2, has_remote=1),
            ],
        )
        adlar = sorted(r["name"] for r in db_mod.list_repos(conn, only_dirty=True))
        # NULL olan temiz repo cikmiyor; NULL olan kirli repo dirty>0 sayesinde cikiyor.
        assert adlar == ["bilinmeyen-dirty", "push-bekleyen"]
        assert len(db_mod.list_repos(conn)) == 4
    finally:
        conn.close()


def test_unpushed_null_saklanir_sifir_yazilmaz(tmp_path: Path):
    """None DB'ye NULL olarak gider; 0'a CEVRILMEZ."""
    conn = db_mod.connect(tmp_path / "a.db")
    try:
        db_mod.upsert_repos(conn, [satir("/a/x", "x", unpushed=None, has_remote=1)])
        tek = db_mod.list_repos(conn)[0]
        assert tek["unpushed"] is None
        assert tek["has_remote"] == 1
    finally:
        conn.close()


def test_eski_sema_not_null_gocu_calisir_veri_kaybolmaz(tmp_path: Path):
    """A.1 oncesi elle kurulmus DB (unpushed NOT NULL) acilirsa gocer ve veri korunur."""
    yol = tmp_path / "eski.db"
    eski_sema = """
    CREATE TABLE repos (
        path            TEXT PRIMARY KEY,
        name            TEXT NOT NULL,
        scanned_at      TEXT NOT NULL,
        dirty           INTEGER NOT NULL DEFAULT 0,
        unpushed        INTEGER NOT NULL DEFAULT 0,
        branch          TEXT,
        last_commit_at  TEXT,
        has_remote      INTEGER NOT NULL DEFAULT 0
    );
    """
    conn = sqlite3.connect(str(yol))
    try:
        conn.executescript(eski_sema)
        conn.executemany(
            "INSERT INTO repos (path, name, scanned_at, dirty, unpushed, branch, "
            "last_commit_at, has_remote) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("/a/bir", "bir", "2024-01-02T03:04:05+00:00", 0, 3, "main",
                 "2024-01-02T03:04:05+00:00", 1),
                ("/a/iki", "iki", "2024-01-02T03:04:05+00:00", 2, 0, "dal",
                 "2024-01-02T03:04:05+00:00", 0),
            ],
        )
        conn.commit()
        assert db_mod._repos_unpushed_notnull(conn)
    finally:
        conn.close()

    conn = db_mod.connect(yol)  # goc burada calisir
    try:
        assert not db_mod._repos_unpushed_notnull(conn)  # NOT NULL gitti
        assert int(conn.execute("PRAGMA user_version").fetchone()[0]) == db_mod.SCHEMA_VERSION
        satirlar = {r["name"]: dict(r) for r in db_mod.list_repos(conn)}
        assert set(satirlar) == {"bir", "iki"}  # veri KAYBOLMADI
        assert satirlar["bir"]["unpushed"] == 3  # degerler korundu
        assert satirlar["bir"]["has_remote"] == 1
        assert satirlar["bir"]["branch"] == "main"
        assert satirlar["bir"]["scanned_at"] == "2024-01-02T03:04:05+00:00"
        assert satirlar["iki"]["dirty"] == 2
        assert satirlar["iki"]["branch"] == "dal"
        # goc sonrasi yeni NULL satiri yazilabilmeli ve filtreye girmemeli
        db_mod.upsert_repos(conn, [satir("/a/uc", "uc", unpushed=None, has_remote=1)])
        uc = next(r for r in db_mod.list_repos(conn) if r["name"] == "uc")
        assert uc["unpushed"] is None  # NULL yazildi, 0 degil
        adlar = sorted(r["name"] for r in db_mod.list_repos(conn, only_dirty=True))
        # "bir" unpushed=3+remote; "iki" dirty=2; "uc" NULL -> DIŞARIDA kalır
        assert adlar == ["bir", "iki"]
    finally:
        conn.close()


def test_goc_idempotent_iki_acilis_bozulmaz(tmp_path: Path):
    """Ayni DB'yi iki kez acmak gocu tekrar tetiklemez, veri ayni kalir."""
    yol = tmp_path / "iki-kere.db"
    conn = db_mod.connect(yol)
    db_mod.upsert_repos(conn, [satir("/a/tek", "tek", unpushed=4, has_remote=1)])
    conn.close()
    conn = db_mod.connect(yol)
    try:
        assert db_mod.list_repos(conn)[0]["unpushed"] == 4
    finally:
        conn.close()
    conn = db_mod.connect(yol)
    try:
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
