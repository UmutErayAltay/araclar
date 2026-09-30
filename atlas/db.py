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
    unpushed        INTEGER,          -- NULL = bilinmiyor (bkz. scan._unpushed_count)
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

#: `repos.unpushed` sutunu NULL kabul edecek sekilde cevrildi (A.1).
#: 0 = eski sema (NOT NULL), 1 = gecerli sema.
SCHEMA_VERSION = 1

#: 0'a cekilirsen `unpushed` yerine `COALESCE(unpushed, 0)` yazilir; boylece
#: A.1 oncesinden kalma DB'ler de anlamli gorunur, ama yeni semayi zorlamaz.
UNKNOWN_AS_ZERO_SQL = "COALESCE(unpushed, 0)"


def _repos_unpushed_notnull(conn: sqlite3.Connection) -> bool:
    """`repos.unpushed` NOT NULL mi? (Tablo yoksa False: zaten goc yok.)

    `PRAGMA table_info` sutunlari: (cid, name, type, notnull, dflt_value, pk).
    Konumsal erisim kullanilir; boylece satir tipi (tuple / sqlite3.Row) onemsiz.
    """
    return any(
        row[3] for row in conn.execute("PRAGMA table_info(repos)") if row[1] == "unpushed"
    )


def _migrate(conn: sqlite3.Connection) -> None:
    """Semayi ilerletir. Mevcut DB'ler veri kaybetmeden guncellenir."""
    surum = int(conn.execute("PRAGMA user_version").fetchone()[0])
    if surum >= SCHEMA_VERSION:
        return

    if _repos_unpushed_notnull(conn):
        # Eski sema: `unpushed NOT NULL`. Guvenli goc sirasi:
        #   gecici isim ver -> yeni semali tabloyu kur -> veriyi tasi -> eskisini sil.
        # Boylece hicbir an icin veri yoktur ve yeni tablo NOT NULL'suz olur.
        conn.execute("ALTER TABLE repos RENAME TO repos_eski")
        conn.executescript(
            SCHEMA.replace("CREATE TABLE IF NOT EXISTS repos", "CREATE TABLE repos")
        )
        conn.execute(
            "INSERT INTO repos "
            "(path, name, scanned_at, dirty, unpushed, branch, last_commit_at, has_remote) "
            "SELECT path, name, scanned_at, dirty, "
            f"{UNKNOWN_AS_ZERO_SQL}, branch, last_commit_at, has_remote FROM repos_eski"
        )
        conn.execute("DROP TABLE repos_eski")

    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()


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
    _migrate(conn)
    conn.commit()
    return conn


REPO_COLUMNS = ("path", "name", "dirty", "unpushed", "branch", "last_commit_at", "has_remote")


def upsert_repos(conn: sqlite3.Connection, repos: Sequence[dict[str, Any]]) -> None:
    """Ayni path'i UPDATE eder, cogaltmaz (path PRIMARY KEY).

    `unpushed=None` "bilinmiyor" demektir ve NULL olarak yazilir; 0'a CEVRILMEZ.
    """
    if not repos:
        return
    now = utc_now()
    # Siralama, asagidaki INSERT sutun sirasiyla BIREBIR ayni olmali.
    rows = [
        (
            r["path"],
            r["name"],
            int(r.get("dirty") or 0),
            None if r.get("unpushed") is None else int(r["unpushed"]),
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

    `unpushed` NULL (bilinmiyor) olan repo: `unpushed > 0` ifadesi NULL verir ve
    `OR` ile birlesince tum ifade NULL olur; WHERE yalnizca TRUE kabul ettigi icin
    bu satir dogal olarak filtreye GIRMEZ. SQL semantigiyle guvence altindadir.
    """
    sql = "SELECT * FROM repos"
    if only_dirty:
        sql += f" WHERE dirty > 0 OR ({UNKNOWN_AS_ZERO_SQL} > 0 AND has_remote = 1)"
    sql += " ORDER BY name COLLATE NOCASE, path"
    return list(conn.execute(sql))


def count_repos(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM repos").fetchone()[0])


#: `commit` SQLite anahtar kelimesidir; INSERT listesinde tirnaklanmalidir.
FINDING_COLUMNS = ("repo", "kind", "severity", "file", "line", '"commit"', "snippet_redacted")

#: `onbulgu_sutun` = satiri ONCEDEN sil, sonra yaz (ayni transaction).
#: Boylece bir repo yeniden taraninca ESKI bulgular kalici olarak gider.
ONBULGU_SIL_SQL = "DELETE FROM findings WHERE repo = ?"


def replace_findings(
    conn: sqlite3.Connection, repo: str, bulgular: Sequence[dict[str, Any]]
) -> int:
    """Bir repo'nun bulgularini ATIP yeniler; doner: yazilan satir sayisi.

    Silme + yazma TEK transaction'dadir: yarim kalan bir bulgu durumu olusmaz.
    `snippet_redacted` alanina ham sır yazılamaz (bkz. `leaks.bulgu_olustur`).
    """
    with conn:  # BEGIN ... COMMIT
        conn.execute(ONBULGU_SIL_SQL, (repo,))
        if bulgular:
            conn.executemany(
                f"INSERT INTO findings ({', '.join(FINDING_COLUMNS)}) "
                f"VALUES ({', '.join('?' * len(FINDING_COLUMNS))})",
                [
                    (
                        repo,
                        b["kind"],
                        b.get("severity"),
                        b.get("file"),
                        b.get("line"),
                        b.get("commit"),
                        b.get("snippet_redacted"),
                    )
                    for b in bulgular
                ],
            )
    return len(bulgular)


def list_findings(
    conn: sqlite3.Connection,
    *,
    repo: str | None = None,
    tur: str | None = None,
    onem: str | None = None,
) -> list[sqlite3.Row]:
    """Bulgu tablosunu filtreli sıralı döndürür (önem sırası: en yüksek önce)."""
    sql = "SELECT * FROM findings"
    kosul: list[str] = []
    degerler: list[Any] = []
    for sutun, deger in (("repo", repo), ("kind", tur), ("severity", onem)):
        if deger is not None:
            kosul.append(f"{sutun} = ?")
            degerler.append(deger)
    if kosul:
        sql += " WHERE " + " AND ".join(kosul)
    # CASE ile onem sirasi: yuksek > orta > dusuk > bilgi.
    sql += (
        " ORDER BY CASE severity WHEN 'yuksek' THEN 0 WHEN 'orta' THEN 1"
        " WHEN 'dusuk' THEN 2 ELSE 3 END, repo, file, line, id"
    )
    return list(conn.execute(sql, degerler))


def count_findings(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM findings").fetchone()[0])


def findings_ozet(conn: sqlite3.Connection, repo: str | None = None) -> list[sqlite3.Row]:
    """(repo, tur, onem) -> adet ozeti; CLI `sizinti` ciktisini besler."""
    sql = "SELECT repo, kind, severity, COUNT(*) AS adet FROM findings"
    if repo is not None:
        sql += " WHERE repo = ?"
    sql += (
        " GROUP BY repo, kind, severity"
        " ORDER BY CASE severity WHEN 'yuksek' THEN 0 WHEN 'orta' THEN 1"
        " WHEN 'dusuk' THEN 2 ELSE 3 END, repo, kind"
    )
    return list(conn.execute(sql, () if repo is None else (repo,)))


# --------------------------------------------------------------------------
# TODOs (Dalga C)
# --------------------------------------------------------------------------

TODO_COLUMNS = ("repo", "file", "line", "text")

#: Yeniden taramada o repo'nun eski todo'lari ONCEDEN silinir (ayni transaction).
ONTODO_SIL_SQL = "DELETE FROM todos WHERE repo = ?"


def replace_todos(
    conn: sqlite3.Connection, repo: str, todos: Sequence[dict[str, Any]]
) -> int:
    """Bir repo'nun todo'larini ATIP yeniler; doner: yazilan satir sayisi.

    Silme + yazma TEK transaction'dadir. `text` alanina ham sır yazılamaz:
    metin `todo.satiri_tara` icinde `leaks.maske`'den gecmistir.
    """
    with conn:  # BEGIN ... COMMIT
        conn.execute(ONTODO_SIL_SQL, (repo,))
        if todos:
            conn.executemany(
                f"INSERT INTO todos ({', '.join(TODO_COLUMNS)}) "
                f"VALUES ({', '.join('?' * len(TODO_COLUMNS))})",
                [(t["repo"], t.get("file"), t.get("line"), t.get("text")) for t in todos],
            )
    return len(todos)


def list_todos(
    conn: sqlite3.Connection, *, repo: str | None = None
) -> list[sqlite3.Row]:
    """Todo kayitlari (repo adi, dosya, satir sirali)."""
    sql = "SELECT * FROM todos"
    parametre: tuple = ()
    if repo is not None:
        sql += " WHERE repo = ?"
        parametre = (repo,)
    sql += " ORDER BY repo, file, line, id"
    return list(conn.execute(sql, parametre))


def count_todos(conn: sqlite3.Connection, repo: str | None = None) -> int:
    sql = "SELECT COUNT(*) FROM todos"
    parametre: tuple = ()
    if repo is not None:
        sql += " WHERE repo = ?"
        parametre = (repo,)
    return int(conn.execute(sql, parametre).fetchone()[0])


def todos_ozet(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """(repo, adet) -> todo yogunlugu; en yogundan azaga, ada gore."""
    return list(
        conn.execute(
            "SELECT repo, COUNT(*) AS adet FROM todos GROUP BY repo "
            "ORDER BY adet DESC, repo COLLATE NOCASE"
        )
    )

