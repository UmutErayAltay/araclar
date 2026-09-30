"""SQLite veri katmani. Sema Dalga B/C/D icin simdiden tam kuruludur."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

SCHEMA = """
CREATE TABLE IF NOT EXISTS repos (
    path            TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    scanned_at      TEXT NOT NULL,
    dirty           INTEGER NOT NULL DEFAULT 0,
    unpushed        INTEGER NOT NULL DEFAULT 0,
    branch          TEXT,
    last_commit_at  TEXT,
    has_remote      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS findings (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    repo              TEXT NOT NULL,
    kind              TEXT NOT NULL,
    severity          TEXT,
    file              TEXT,
    line              INTEGER,
    "commit"          TEXT,          -- SQLite anahtar kelimesi, tirnak icinde
    snippet_redacted  TEXT
);

CREATE TABLE IF NOT EXISTS readme_status (
    repo                    TEXT PRIMARY KEY,
    readme_commit           TEXT,
    behavior_commits_after  INTEGER,
    screenshot_age_days     INTEGER
);

CREATE TABLE IF NOT EXISTS todos (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    repo  TEXT NOT NULL,
    file  TEXT,
    line  INTEGER,
    text  TEXT
);

CREATE INDEX IF NOT EXISTS idx_findings_repo ON findings(repo);
CREATE INDEX IF NOT EXISTS idx_todos_repo    ON todos(repo);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Ust dizini varsa olusturup baglantiyi acar."""
    path = Path(db_path).expanduser()
    if path.parent and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


REPO_COLUMNS = ("path", "name", "dirty", "unpushed", "branch", "last_commit_at", "has_remote")


def upsert_repos(conn: sqlite3.Connection, repos: Sequence[dict[str, Any]]) -> None:
    """Ayni path'i UPDATE eder, cogaltmaz (path PRIMARY KEY)."""
    if not repos:
        return
    now = utc_now()
    # Siralama, asagidaki INSERT sutun sirasiyla BIREBIR ayni olmali.
    rows = [
        (
            r["path"],
            r["name"],
            int(r.get("dirty") or 0),
            int(r.get("unpushed") or 0),
            r.get("branch"),
            r.get("last_commit_at"),
            1 if r.get("has_remote") else 0,
            r.get("scanned_at") or now,
        )
        for r in repos
    ]
    conn.executemany(
        f"INSERT INTO repos ({', '.join(REPO_COLUMNS)}, scanned_at) "
        f"VALUES ({', '.join('?' * (len(REPO_COLUMNS) + 1))}) "
        f"ON CONFLICT(path) DO UPDATE SET "
        f"name=excluded.name, dirty=excluded.dirty, unpushed=excluded.unpushed, "
        f"branch=excluded.branch, last_commit_at=excluded.last_commit_at, "
        f"has_remote=excluded.has_remote, scanned_at=excluded.scanned_at",
        rows,
    )
    conn.commit()


def delete_missing_repos(conn: sqlite3.Connection, existing_paths: Iterable[str]) -> int:
    """Taramada gorulmeyen repo satirlarini siler; silinen sayisini dondurur."""
    keep = set(existing_paths)
    all_paths = [row["path"] for row in conn.execute("SELECT path FROM repos")]
    gone = [p for p in all_paths if p not in keep]
    if gone:
        conn.executemany("DELETE FROM repos WHERE path = ?", [(p,) for p in gone])
        conn.commit()
    return len(gone)


def list_repos(conn: sqlite3.Connection, only_dirty: bool = False) -> list[sqlite3.Row]:
    """Repolari adina gore sirali listeler.

    `only_dirty` = `--sadece-yarim`: yalnizca BEKLEYEN is olan repolar.
    Remote'i olmayan repoda sozlesme geregi `unpushed` tum commit sayisidir;
    bu bir tanim sonucu, gercek bir "push bekliyor" durumu degildir, ancak
    filtrede sayilmaz.
    """
    sql = "SELECT * FROM repos"
    if only_dirty:
        sql += " WHERE dirty > 0 OR (unpushed > 0 AND has_remote = 1)"
    sql += " ORDER BY name COLLATE NOCASE, path"
    return list(conn.execute(sql))


def count_repos(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM repos").fetchone()[0])
