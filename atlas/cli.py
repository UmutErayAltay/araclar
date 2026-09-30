"""atlas komut satiri arayuzu."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

from . import __version__, config, db, scan

#: Yazilari terminal genisligine gore sutunlara dizer.
_MIN_WIDTH = 8

#: `unpushed` bilinmiyorsa (remote var ama yerelde uzak-takip ref'i yok).
BILINMIYOR_ISARETI = "?"
BILINMIYOR_ACIKLAMA = "uzak-takip bilgisi yok (git fetch gerekir); atlas fetch yapmaz."


def _display_width(text: str) -> int:
    try:
        import unicodedata

        return sum(2 if unicodedata.combining(c) else 1 for c in text)
    except Exception:  # pragma: no cover
        return len(text)


def _fit(text: str, width: int) -> str:
    if width <= 0:
        return ""
    if len(text) <= width:
        return text.ljust(width)
    if width <= 1:
        return "…"[:width]
    return text[: width - 1] + "…"


def render_table(headers: list[str], rows: list[list[str]]) -> str:
    """Baslikli sabit genislikli tablo (T Turkce karakterler icin duzeltilmis)."""
    cols = len(headers)
    widths = [_display_width(h) for h in headers]
    for row in rows:
        for i in range(cols):
            widths[i] = max(widths[i], _display_width(row[i]) if i < len(row) else 0)
    widths = [max(w, _MIN_WIDTH) for w in widths]

    def line(cells: list[str]) -> str:
        return "  ".join(_fit(cells[i] if i < len(cells) else "", widths[i]) for i in range(cols)).rstrip()

    sep = "  ".join("-" * w for w in widths)
    return "\n".join([line(headers), sep, *(line(r) for r in rows)])


def _short_date(value: str | None) -> str:
    """'2026-09-30T04:18:00+00:00' -> '2026-09-30 04:18'"""
    if not value:
        return "-"
    return value.replace("T", " ")[:16]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="atlas",
        description="Repo Saglik Atlasi: yerel git repolarini tarar, durumlarini SQLite'a yazar.",
    )
    parser.add_argument("--version", action="version", version=f"atlas {__version__}")
    sub = parser.add_subparsers(dest="komut", required=True, metavar="KOMUT")

    tara = sub.add_parser("tara", help="repolari tara ve veritabanina yaz")
    tara.add_argument("--root", action="append", metavar="DIZIN", help="tarama koku (birden fazla olabilir)")
    tara.add_argument("--db", metavar="YOL", help="veritabani yolu (varsayilan: ~/.atlas/atlas.db)")
    tara.add_argument("--derinlik", type=int, default=config.DEFAULT_DEPTH, metavar="N", help="tarama derinligi (varsayilan: 3)")

    liste = sub.add_parser("liste", help="repolari tablo olarak listele")
    liste.add_argument("--db", metavar="YOL", help="veritabani yolu (varsayilan: ~/.atlas/atlas.db)")
    liste.add_argument(
        "--sadece-yarim",
        action="store_true",
        help="yalnizca commit'lenmemis degisikligi olan ya da push bekleyen repolar",
    )
    return parser


def _cmd_tara(args: argparse.Namespace) -> int:
    roots = [Path(r) for r in args.root] if args.root else config.load_roots()
    db_path = Path(args.db) if args.db else config.default_db_path()
    depth = max(0, args.derinlik)

    conn = db.connect(db_path)
    try:
        found, removed, errors = scan.scan_and_sync(conn, roots, depth=depth)
    finally:
        conn.close()

    print(f"Taranan repo: {found}")
    print(f"Silinen repo satiri: {removed}")
    print(f"Veritabani: {db_path}")
    for path, err in errors:
        print(f"  ! atlandi: {path}: {err}", file=sys.stderr)
    if errors:
        print(f"Uyarili repo: {len(errors)}", file=sys.stderr)
    return 0


def _cmd_liste(args: argparse.Namespace) -> int:
    db_path = Path(args.db) if args.db else config.default_db_path()
    if not db_path.exists():
        print(f"Veritabani yok: {db_path}", file=sys.stderr)
        print("Once 'atlas tara' calistir.", file=sys.stderr)
        return 1
    conn = db.connect(db_path)
    try:
        rows = db.list_repos(conn, only_dirty=args.sadece_yarim)
    finally:
        conn.close()

    if not rows:
        print("Kayitli repo yok." if not args.sadece_yarim else "Yarim is olan repo yok.")
        return 0

    headers = ["Ad", "Dal", "Dirty", "Unpushed", "Son Commit", "Yol"]
    table_rows = [
        [
            r["name"] or "-",
            r["branch"] or "-",
            str(r["dirty"]),
            BILINMIYOR_ISARETI if r["unpushed"] is None else str(r["unpushed"]),
            _short_date(r["last_commit_at"]),
            r["path"],
        ]
        for r in rows
    ]
    print(render_table(headers, table_rows))
    if any(r["unpushed"] is None for r in rows):
        print(f"\n{BILINMIYOR_ISARETI} = {BILINMIYOR_ACIKLAMA}")
    print(f"\nToplam: {len(rows)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.komut == "tara":
            return _cmd_tara(args)
        if args.komut == "liste":
            return _cmd_liste(args)
    except BrokenPipeError:  # pragma: no cover
        return 0
    except KeyboardInterrupt:  # pragma: no cover
        print("Iptal edildi.", file=sys.stderr)
        return 130
    except sqlite3.Error as exc:
        print(f"Veritabani hatasi: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Hata: {exc}", file=sys.stderr)
        return 1
    parser.error("bilinmeyen komut")
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
