import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "ne-izlesem.db"

VALID_KINDS = {"film", "dizi", "anime", "kitap"}
VALID_STATUSES = {"planlanan", "izleniyor", "tamamlandi", "birakildi"}


def get_connection(db_path=DEFAULT_DB_PATH):
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def init_db(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            kind TEXT NOT NULL,
            status TEXT NOT NULL,
            rating INTEGER,
            note TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.commit()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


def list_items(conn, kind=None, status=None, q=None):
    query = "SELECT * FROM items WHERE 1=1"
    params: list = []
    if kind is not None:
        query += " AND kind = ?"
        params.append(kind)
    if status is not None:
        query += " AND status = ?"
        params.append(status)
    if q:
        query += " AND title LIKE ? ESCAPE '\\'"
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        params.append(f"%{escaped}%")
    query += " ORDER BY updated_at DESC"
    rows = conn.execute(query, params).fetchall()
    return [_row_to_dict(r) for r in rows]


def create_item(conn, title, kind, status="planlanan", rating=None, note=None):
    now = _now()
    cur = conn.execute(
        "INSERT INTO items (title, kind, status, rating, note, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (title, kind, status, rating, note, now, now),
    )
    conn.commit()
    return get_item(conn, cur.lastrowid)


def get_item(conn, item_id):
    row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    return _row_to_dict(row) if row else None


def update_item(conn, item_id, **fields):
    if not fields:
        return get_item(conn, item_id)
    fields = dict(fields)
    fields["updated_at"] = _now()
    set_clause = ", ".join(f"{key} = ?" for key in fields)
    params = list(fields.values()) + [item_id]
    cur = conn.execute(f"UPDATE items SET {set_clause} WHERE id = ?", params)
    conn.commit()
    if cur.rowcount == 0:
        return None
    return get_item(conn, item_id)


def delete_item(conn, item_id) -> bool:
    cur = conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
    conn.commit()
    return cur.rowcount > 0
