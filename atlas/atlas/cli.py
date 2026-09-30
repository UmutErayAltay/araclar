"""atlas komut satiri arayuzu."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

from . import __version__, config, db, durum, leaks, readme_stale, scan, summary, todo

#: Yazilari terminal genisligine gore sutunlara dizer.
_MIN_WIDTH = 8

#: `unpushed` bilinmiyorsa (remote var ama yerelde uzak-takip ref'i yok).
BILINMIYOR_ISARETI = "?"
BILINMIYOR_ACIKLAMA = "uzak-takip bilgisi yok (git fetch gerekir); atlas fetch yapmaz."

#: `atlas sizinti --gecmis` varsayilani (son N commit).
VARSAYILAN_GECMIS = 500

#: `atlas web --port` varsayilani. Adres kodda sabittir (127.0.0.1).
VARSAYILAN_PORT = 8770

#: Onem sirasi (ozet ciktisinda ve filtrelerde).
ONEMLER = ("yuksek", "orta", "dusuk", "bilgi")

#: Tur basliklari (tablo ciktisinda Turkce).
TUR_BASLIK = {
    "api-anahtari": "API anahtari",
    "ozel-anahtar": "Ozel anahtar",
    "env-izlenen": ".env izlenen",
    "kisisel-yol": "Kisisel yol",
    "e-posta": "E-posta",
    "gorsel-elle-kontrol": "Gorsel (elle kontrol)",
}



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

    sizinti = sub.add_parser("sizinti", help="sizinti taramasi yap ve bulgulari yaz")
    sizinti.add_argument("--root", action="append", metavar="DIZIN", help="tarama koku (birden fazla olabilir)")
    sizinti.add_argument("--db", metavar="YOL", help="veritabani yolu (varsayilan: ~/.atlas/atlas.db)")
    sizinti.add_argument("--repo", metavar="AD", help="yalnizca bu repo taranir (adi veya yolu)")
    sizinti.add_argument(
        "--gecmis", type=int, default=VARSAYILAN_GECMIS, metavar="N",
        help=f"gecmis taramasi icin son N commit (varsayilan: {VARSAYILAN_GECMIS})",
    )

    bulgular = sub.add_parser("bulgular", help="kayitli bulgulari tablo olarak listele")
    bulgular.add_argument("--db", metavar="YOL", help="veritabani yolu (varsayilan: ~/.atlas/atlas.db)")
    bulgular.add_argument("--repo", metavar="AD", help="repo filtresi (tam eslesme)")
    bulgular.add_argument("--siddet", choices=ONEMLER, help="onem filtresi")
    bulgular.add_argument("--tur", metavar="T", help="tur filtresi (orn. api-anahtari)")

    borc = sub.add_parser("borc", help="TODO/FIXME borcunu tara ve raporla")
    borc.add_argument("--root", action="append", metavar="DIZIN", help="tarama koku (birden fazla olabilir)")
    borc.add_argument("--db", metavar="YOL", help="veritabani yolu (varsayilan: ~/.atlas/atlas.db)")
    borc.add_argument("--repo", metavar="AD", help="yalnizca bu repo taranir (adi veya yolu)")

    guncelle = sub.add_parser(
        "guncelle",
        help="tara + sizinti + borc + readme: dort tabloyu tek komutta doldurur",
    )
    guncelle.add_argument("--root", action="append", metavar="DIZIN", help="tarama koku (birden fazla olabilir)")
    guncelle.add_argument("--db", metavar="YOL", help="veritabani yolu (varsayilan: ~/.atlas/atlas.db)")
    guncelle.add_argument(
        "--gecmis", type=int, default=VARSAYILAN_GECMIS, metavar="N",
        help=f"sizinti gecmisi icin son N commit (varsayilan: {VARSAYILAN_GECMIS})",
    )

    readme = sub.add_parser(
        "readme",
        help="README bayatligini olcer (skora gore sirali tablo)",
    )
    readme.add_argument("--root", action="append", metavar="DIZIN", help="tarama koku (birden fazla olabilir)")
    readme.add_argument("--db", metavar="YOL", help="veritabani yolu (varsayilan: ~/.atlas/atlas.db)")
    readme.add_argument("--repo", metavar="AD", help="yalnizca bu repo taranir (adi veya yolu)")
    readme.add_argument("--json", action="store_true", help="makine tarafinin okunabilir cikti")

    ozet = sub.add_parser(
        "ozet",
        help="repo basina 'simdi ne yapmali' ozeti uret (varsayilan: ağa cikmaz)",
    )
    ozet.add_argument("--db", metavar="YOL", help="veritabani yolu (varsayilan: ~/.atlas/atlas.db)")
    ozet.add_argument("--repo", metavar="AD", help="yalnizca bu repo icin ozet (adi veya yolu)")
    ozet.add_argument(
        "--cor", action="store_true",
        help="ozeti yerel cor proxy'sine sor (VARSAYILAN DEGILDIR; dar veri kumesi gonderilir)",
    )
    ozet.add_argument(
        "--kuru", action="store_true",
        help="hicbir icerik gostermeden gidecek alan turlerini ve toplam karakteri yaz",
    )
    ozet.add_argument("--json", action="store_true", help="makine tarafinin okunabilir cikti")

    durum = sub.add_parser(
        "durum",
        help="salt-okunur durum ozeti (kule entegrasyonu; --json sozlesme bicimi)",
    )
    durum.add_argument("--db", metavar="YOL", help="veritabani yolu (varsayilan: ~/.atlas/atlas.db)")
    durum.add_argument(
        "--json", action="store_true",
        help="sozlesme JSON'unu bas (kule bu bicimi okur)",
    )

    web = sub.add_parser("web", help="salt-okunur web panelini baslat (yalnizca 127.0.0.1)")
    web.add_argument("--db", metavar="YOL", help="veritabani yolu (varsayilan: ~/.atlas/atlas.db)")
    web.add_argument("--port", type=int, default=VARSAYILAN_PORT, metavar="N", help="port (varsayılan: %d)" % VARSAYILAN_PORT)
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


def _cmd_sizinti(args: argparse.Namespace) -> int:
    """Tarar, DB'ye yazar, ozet basar. Bulgu olmasi HATA DEGILDIR (cikis kodu 0)."""
    db_path = Path(args.db) if args.db else config.default_db_path()
    commit_sayisi = max(0, int(args.gecmis))

    kokler = [Path(r) for r in args.root] if args.root else config.load_roots()
    if args.repo:
        repo = _tek_repo_coz(args.repo, kokler)
        if repo is None:
            print(f"Repo bulunamadi: {args.repo}", file=sys.stderr)
            return 1
        yalniz: Path | None = repo
    else:
        yalniz = None

    conn = db.connect(db_path)
    try:
        if yalniz is not None:
            try:
                tarama = leaks.tara_repo(yalniz, commit_sayisi=commit_sayisi)
                repo_bulgulari = {tarama.repo: tarama.bulgular}
                uyarilar = list(tarama.uyarilar)
                hatalar: list[tuple[Path, str]] = []
            except Exception as exc:
                repo_bulgulari, uyarilar = {}, []
                hatalar = [(yalniz, type(exc).__name__)]
        else:
            repo_bulgulari, hatalar = leaks.tara_roots(kokler, commit_sayisi=commit_sayisi)
            uyarilar = []

        toplam = 0
        for repo_yol in sorted(repo_bulgulari):
            # Yeniden taramada o repo'nun ESKI bulgulari silinir (ayni transaction).
            toplam += db.replace_findings(conn, repo_yol, repo_bulgulari[repo_yol])
        ozet = db.findings_ozet(conn)
    finally:
        conn.close()

    print(f"Taranan repo: {len(repo_bulgulari) + len(hatalar)}")
    print(f"Bulgu: {toplam}")
    if not ozet:
        print("Bulgu yok.")
    else:
        print()
        print(render_table(
            ["Repo", "Tur", "Onem", "Adet"],
            [
                [Path(r["repo"]).name or r["repo"], TUR_BASLIK.get(r["kind"], r["kind"]),
                 r["severity"], str(r["adet"])]
                for r in ozet
            ],
        ))
        print(f"\nToplam bulgu: {sum(r['adet'] for r in ozet)}")
    print(f"Veritabani: {db_path}")
    for uyari in uyarilar:
        print(f"  ! {uyari}", file=sys.stderr)
    for path, err in hatalar:
        print(f"  ! atlandi: {path}: {err}", file=sys.stderr)
    if hatalar:
        print(f"Hatali repo: {len(hatalar)}", file=sys.stderr)
    return 0  # bulgu bulmak hata degildir


def _tek_repo_coz(anahtar: str, kokler: list[Path]) -> Path | None:
    """`--repo` ile verilen adı (veya yolu) çözümler; bulunamazsa `None`."""
    yol = Path(anahtar).expanduser()
    if scan.is_repo(yol):
        return yol.resolve()
    for aday in scan.find_repo_paths(kokler):
        if aday.name == anahtar or str(aday) == anahtar:
            return aday
    return None


def _cmd_bulgular(args: argparse.Namespace) -> int:
    db_path = Path(args.db) if args.db else config.default_db_path()
    if not db_path.exists():
        print(f"Veritabani yok: {db_path}", file=sys.stderr)
        print("Once 'atlas sizinti' calistir.", file=sys.stderr)
        return 1
    conn = db.connect(db_path)
    try:
        rows = db.list_findings(conn, repo=args.repo, tur=args.tur, onem=args.siddet)
    finally:
        conn.close()

    if not rows:
        print("Bulgu yok.")
        return 0

    basliklar = ["Repo", "Onem", "Tur", "Dosya", "Commit", "Snippet"]
    tablo = [
        [
            Path(r["repo"]).name or r["repo"],
            r["severity"] or "-",
            TUR_BASLIK.get(r["kind"], r["kind"] or "-"),
            leaks.bulgu_satiri(r),
            r["commit"] or "-",
            r["snippet_redacted"] or "-",
        ]
        for r in rows
    ]
    print(render_table(basliklar, tablo))
    print(f"\nToplam: {len(rows)}")
    return 0


def _borc_tara(args: argparse.Namespace) -> tuple[dict[str, list[dict]], list[tuple[Path, str]], list[str]]:
    """`--repo` filtresi varsa yalniz o repo, yoksa koklerin tumu taranir.

    Doner: (repo -> todos, hatalar, uyarilar).
    """
    kokler = [Path(r) for r in args.root] if args.root else config.load_roots()
    uyarilar: list[str] = []
    hatalar: list[tuple[Path, str]] = []
    if getattr(args, "repo", None):
        repo = _tek_repo_coz(args.repo, kokler)
        if repo is None:
            return {}, [(Path(args.repo), "repo bulunamadi")], uyarilar
        try:
            tarama = todo.tara_repo(repo)
            return {tarama.repo: tarama.todos}, hatalar, list(tarama.uyarilar)
        except Exception as exc:
            return {}, [(repo, type(exc).__name__)], uyarilar
    repo_todolar, hatalar = todo.tara_roots(kokler)
    return repo_todolar, hatalar, uyarilar


def _cmd_borc(args: argparse.Namespace) -> int:
    """TODO/FIXME borcunu tarar, DB'ye yazar, repo basina sayi basar."""
    db_path = Path(args.db) if args.db else config.default_db_path()
    repo_todolar, hatalar, uyarilar = _borc_tara(args)

    conn = db.connect(db_path)
    try:
        toplam = 0
        for repo_yol in sorted(repo_todolar):
            # Yeniden taramada o repo'nun ESKI todo'lari silinir (ayni transaction).
            toplam += db.replace_todos(conn, repo_yol, repo_todolar[repo_yol])
        ozet = db.todos_ozet(conn)
    finally:
        conn.close()

    print(f"Taranan repo: {len(repo_todolar) + len(hatalar)}")
    print(f"Todo: {toplam}")
    if not ozet:
        print("TODO/FIXME borcu yok.")
    else:
        print()
        print(render_table(
            ["Repo", "Todo"],
            [[Path(r["repo"]).name or r["repo"], str(r["adet"])] for r in ozet],
        ))
        print(f"\nToplam todo: {sum(r['adet'] for r in ozet)}")
    print(f"Veritabani: {db_path}")
    for uyari in uyarilar:
        print(f"  ! {uyari}", file=sys.stderr)
    for path, err in hatalar:
        print(f"  ! atlandi: {path}: {err}", file=sys.stderr)
    if hatalar:
        print(f"Hatali repo: {len(hatalar)}", file=sys.stderr)
    return 0


def _cmd_guncelle(args: argparse.Namespace) -> int:
    """`tara` + `sizinti` + `borc` + `readme` + yerel `ozet`.

    Mevcut komutlarin davranisi DEGISTIRILMEZ; `guncelle` yalnizca onlari
    sirayla cagirir. Yeni adim `readme` ve YEREL `ozet` ile tamamlanir;
    `ozet` AGSIZ calisir (--cor YOKTUR, cor'a HICBIR istek gitmez).
    """
    kokler = [Path(r) for r in args.root] if args.root else config.load_roots()
    kok_metni = [str(k) for k in kokler]
    db_yol = str(Path(args.db) if args.db else config.default_db_path())
    cikis = 0

    print("== 1/5: repo taramasi ==")
    cikis |= _cmd_tara(_alt(args, komut="tara", root=kok_metni, db=db_yol, derinlik=config.DEFAULT_DEPTH))
    print()
    print("== 2/5: sizinti taramasi ==")
    cikis |= _cmd_sizinti(_alt(args, komut="sizinti", root=kok_metni, db=db_yol, gecmis=args.gecmis, repo=None))
    print()
    print("== 3/5: TODO/FIXME borcu ==")
    cikis |= _cmd_borc(_alt(args, komut="borc", root=kok_metni, db=db_yol, repo=None))
    print()
    print("== 4/5: README bayatligi ==")
    cikis |= _cmd_readme(_alt(args, komut="readme", root=kok_metni, db=db_yol, repo=None, json=False))
    print()
    print("== 5/5: yerel 'simdi ne yapmali' ozeti (agsiz) ==")
    cikis |= _cmd_ozet(_alt(args, komut="ozet", db=db_yol, repo=None, cor=False, kuru=False, json=False))
    return cikis


# --------------------------------------------------------------------------
# Dalga D: README bayatligi
# --------------------------------------------------------------------------

#: `atlas readme` tablosunda gorsel yasi yerine gosterilen metin.
GORSEL_YOK_ISARETI = "-"


def _readme_satiri_olustur(durum: readme_stale.ReadmeDurumu) -> list[str]:
    """Tek repo'nun tablo satiri (yazar, seviye, skor, davranis, gorsel yasi)."""
    seviye = durum.seviye or "bilinmiyor"
    if durum.neden:
        seviye = f"{seviye} ({durum.neden})"
    yas = (
        GORSEL_YOK_ISARETI
        if durum.screenshot_age_days is None
        else str(durum.screenshot_age_days)
    )
    return [
        Path(durum.repo).name or durum.repo,
        seviye,
        str(durum.skor),
        str(durum.davranis_commit),
        yas,
    ]


def _readme_tara(
    args: argparse.Namespace,
) -> tuple[list[readme_stale.ReadmeDurumu], list[tuple[Path, str]]]:
    """`--repo` filtresi varsa yalniz o repo, yoksa koklerin tumu.

    Doner: (durumlar, hatalar).
    """
    kokler = [Path(r) for r in args.root] if args.root else config.load_roots()
    if getattr(args, "repo", None):
        repo = _tek_repo_coz(args.repo, kokler)
        if repo is None:
            return [], [(Path(args.repo), "repo bulunamadi")]
        return [readme_stale.tara_repo(repo)], []
    sonuc, hatalar = readme_stale.tara_roots(kokler)
    return list(sonuc.values()), hatalar


def _cmd_readme(args: argparse.Namespace) -> int:
    """README bayatligini tarar, DB'ye yazar, skora azalan tablo basar.

    Repolara HICBIR SEY yazmaz (yalniz `git log`/`ls-files` okunur).
    """
    db_path = Path(args.db) if args.db else config.default_db_path()
    durumlar, hatalar = _readme_tara(args)

    conn = db.connect(db_path)
    try:
        if durumlar:
            db.replace_readme_status(conn, durumlar)
    finally:
        conn.close()

    sirali = readme_stale.sirala(durumlar)
    if getattr(args, "json", False):
        import json as _json

        print(_json.dumps([d._asdict() for d in sirali], ensure_ascii=False, indent=2))
    else:
        print(f"Taranan repo: {len(durumlar) + len(hatalar)}")
        if not sirali:
            print("README taranacak repo yok.")
        else:
            print()
            print(render_table(
                ["Repo", "Seviye", "Skor", "Davranis commit", "Gorsel yasi (gun)"],
                [_readme_satiri_olustur(d) for d in sirali],
            ))
            sayaclar = {s: 0 for s in readme_stale.SEVIYELER}
            for d in sirali:
                if d.seviye in sayaclar:
                    sayaclar[d.seviye] += 1
            dagilim = " · ".join(f"{s}: {sayaclar[s]}" for s in readme_stale.SEVIYELER)
            print(f"\nToplam: {len(sirali)}")
            print(f"Seviye dagilimi: {dagilim}")
            print(
                f"Eskikler: skor {readme_stale.TAZE_UST_SINIR} alti 'taze', "
                f"{readme_stale.ESKIYOR_UST_SINIR}+ 'bayat'."
            )
        print(f"Veritabani: {db_path}")
    for path, err in hatalar:
        print(f"  ! atlandi: {path}: {err}", file=sys.stderr)
    if hatalar:
        print(f"Hatali repo: {len(hatalar)}", file=sys.stderr)
    return 0


# --------------------------------------------------------------------------
# Dalga D: repo basina ozet
# --------------------------------------------------------------------------

#: `--cor` basarisiz olursa cikis kodu (0 DEGILDIR: basari gibi GORUNMEZ).
COR_HATASI_CIKIS = 3

KAYNAK_ETIKETI = {"yerel": "yerel kural", "cor": "cor"}


def _ozet_satirlari(conn) -> list[tuple[Any, list, int, Any]]:
    """(repo satiri, bulgular, todo adedi, readme satiri) listesi."""
    out = []
    for r in db.list_repos(conn):
        bulgular = conn.execute(
            "SELECT kind, severity FROM findings WHERE repo = ?", (r["path"],)
        ).fetchall()
        todo = int(conn.execute(
            "SELECT COUNT(*) FROM todos WHERE repo = ?", (r["path"],)
        ).fetchone()[0])
        readme = db.readme_status_for(conn, r["path"])
        out.append((r, bulgular, todo, readme))
    return out


def _cmd_ozet(args: argparse.Namespace) -> int:
    """Repo basina ozet uretir ve DB'ye yazar.

    VARSAYILAN: kural tabanli YEREL ozet — AGA CIKMAZ. `--cor` yalnizca acikca
    istenirse LLM'e gider; basarisiz olursa stderr'a acik uyari, YEREL ozet
    yazilir ve cikis kodu `COR_HATASI_CIKIS` (3) olur (basari gibi GORUNMEZ).
    """
    import json as _json

    db_path = Path(args.db) if args.db else config.default_db_path()
    if not db_path.exists():
        print(f"Veritabani yok: {db_path}", file=sys.stderr)
        print("Once 'atlas guncelle' calistir.", file=sys.stderr)
        return 1

    conn = db.connect(db_path)
    try:
        satirlar = _ozet_satirlari(conn)
        if args.repo:
            coz = _tek_repo_coz(args.repo, config.load_roots())
            if coz is None:
                print(f"Repo bulunamadi: {args.repo}", file=sys.stderr)
                return 1
            hedef = str(coz)
            satirlar = [s for s in satirlar if s[0]["path"] == hedef] or [
                ({"path": hedef, "name": Path(hedef).name, "dirty": 0, "unpushed": None,
                  "branch": None, "last_commit_at": None}, [], 0, None)
            ]

        llm = None
        cor_uyari = None
        if args.cor:
            from .llm import CorLLMClient, LLMError

            try:
                llm = CorLLMClient()
            except LLMError as exc:
                cor_uyari = str(exc)
                llm = None

        uretilen: list[dict] = []
        cor_hata_sayisi = 0
        for repo_row, bulgular, todo_adet, readme_row in satirlar:
            girdi = summary.girdi_olustur(
                repo_row, bulgular=bulgular, todo_adet=todo_adet, readme_row=readme_row
            )
            ad = leaks.maske(repo_row["name"] or Path(repo_row["path"]).name)
            if args.kuru:
                # HICBIR ICERIK gosterilmez: yalniz turler + karakter toplami.
                turler, toplam = summary.kuru_rapor(girdi)
                uretilen.append({
                    "repo": ad, "alan_turleri": turler, "toplam_karakter": toplam,
                    "kaynak": "cor" if args.cor else "yerel",
                })
                continue

            metin, kaynak, model = summary.ozet_uret(girdi, llm=llm, cor=bool(args.cor))
            if args.cor and kaynak != "cor":
                cor_hata_sayisi += 1
            db.replace_summary(
                conn, repo_row["path"], uretim=db.utc_now(), kaynak=kaynak, model=model,
                girdi_hash=summary.girdi_hash(girdi), metin=metin,
            )
            uretilen.append({
                "repo": ad, "kaynak": kaynak, "model": model, "metin": metin,
            })
    finally:
        conn.close()

    if args.json:
        print(_json.dumps(uretilen, ensure_ascii=False, indent=2))
    else:
        print(f"Repo: {len(uretilen)}")
        if args.kuru:
            print("(kuru kip: icerik GOSTERILMEZ; yalniz alan turleri ve karakter sayisi)")
            for kayit in uretilen:
                print(f"  {kayit['repo']}: {kayit['alan_turleri']} "
                      f"= {kayit['toplam_karakter']} karakter")
            print(f"\nToplam gidecek karakter: {sum(k['toplam_karakter'] for k in uretilen)}")
        elif not uretilen:
            print("Ozet uretilecek repo yok.")
        else:
            for kayit in uretilen:
                kaynak = KAYNAK_ETIKETI.get(kayit["kaynak"], kayit["kaynak"])
                if kayit["kaynak"] == "cor" and kayit["model"]:
                    kaynak = f"{kaynak}: {leaks.maske(kayit['model'])}"
                print()
                print(f"  {kayit['repo']}  [{kaynak}]")
                for satir in kayit["metin"].splitlines():
                    print(f"    {satir}")
        if not args.kuru:
            print(f"\nVeritabani: {db_path}")

    if cor_uyari:
        print(f"  ! cor: {cor_uyari}", file=sys.stderr)
    if cor_hata_sayisi:
        print(
            f"  ! cor ozeti {cor_hata_sayisi} repoda basarisiz; yerel kural ozeti yazildi.",
            file=sys.stderr,
        )
    if (cor_uyari or cor_hata_sayisi) and not args.kuru:
        return COR_HATASI_CIKIS
    return 0


# --------------------------------------------------------------------------
# `atlas durum` — kule entegrasyonu (sozlesme v1)
# --------------------------------------------------------------------------


def _cmd_durum(args: argparse.Namespace) -> int:
    """Salt-okunur durum ozeti. Varsayilan cikti sozlesme JSON'idir.

    DB `mode=ro` ile ACILIR: yazmaz, sema kurmaz, tarama TETIKLEMEZ, aga
    cikmaz, cor/LLM cagirmaz. `--json` verilmezse tek satirlik insan ozeti
    basilir (sozlesmenin izin verdigi sekil).
    """
    import json as _json

    db_path = Path(args.db) if args.db else config.default_db_path()
    # DB yoksa: sabit hata kodu. Istisna metni/yol HICBIR YERDE basilmaz.
    if not db_path.is_file():
        return _durum_hata(_json, args, durum.HATA_DB_YOK)
    try:
        conn = durum.db_ac(db_path)
    except sqlite3.Error:
        return _durum_hata(_json, args, durum.HATA_OKUNAMADI)
    try:
        # Bozuk/okunamayan dosyada SQLite'in `OperationalError` metaji dosya
        # YOLU tasiyabilir; bu yuzden mesaj ATILIR, sabit kod dondurulur.
        govde = durum.durum_sozlesmesi(durum.ozet_verisi(conn))
    except sqlite3.Error:
        return _durum_hata(_json, args, durum.HATA_OKUNAMADI)
    finally:
        conn.close()

    if args.json:
        print(_json.dumps(govde, ensure_ascii=True, sort_keys=False))
    else:
        print(_durum_tek_satir(govde))
    return 0


def _durum_hata(_json, args, kod: str) -> int:
    """Hata govdesini basar ve cikis kodu 1 doner (`--json` de verilse)."""
    govde = durum.hata_sozlesmesi(kod)
    if getattr(args, "json", False):
        print(_json.dumps(govde, ensure_ascii=True))
    else:
        print(f"atlas durumu okunamadi: {kod}")
    return 1


def _durum_tek_satir(govde: dict) -> str:
    """Insan-okur tek satir. Yalniz SAYI ve sabit etiket icerir."""
    return (
        f"repo {govde['repo_sayisi']} · kirli {govde['kirli_repo']} · "
        f"push bekleyen {govde['push_bekleyen']} · bilinmeyen {govde['push_bilinmeyen']} · "
        f"bayat README {govde['bayat_readme']} · bulgu {govde['bulgu_toplam']} · "
        f"todo {govde['todo_toplam']} · "
        f"{'veri bayat' if govde['veri_bayat'] else 'veri taze'}"
    )


def _alt(args: argparse.Namespace, **degistir) -> argparse.Namespace:
    """Mevcut bir komutun Namespace'ini turetilir (`guncelle` bunu kullanir)."""
    yeni = argparse.Namespace(**vars(args))
    for anahtar, deger in degistir.items():
        setattr(yeni, anahtar, deger)
    return yeni


def _cmd_web(args: argparse.Namespace) -> int:  # pragma: no cover — gercek surec e2e'de
    """Salt-okunur paneli baslatir. Adres kodda sabittir: `127.0.0.1`."""
    from . import web as web_modulu

    db_path = Path(args.db) if args.db else config.default_db_path()
    if not db_path.exists():
        print(f"Veritabani yok: {db_path}", file=sys.stderr)
        print("Once 'atlas guncelle' calistir.", file=sys.stderr)
        return 1
    port = int(args.port)
    if not 1 <= port <= 65535:
        print(f"Gecersiz port: {port}", file=sys.stderr)
        return 1
    print(f"Panel: http://127.0.0.1:{port}/  (salt-okunur; yalnizca 127.0.0.1)")
    print(f"Veritabani: {db_path} (mode=ro)")
    web_modulu.calistir(db_path, port)
    return 0


def _stdout_stderr_utf8() -> None:
    """Türkçe karakterler (ı, ğ, ş…) her ortamda doğru çıksın.

    Container'da locale POSIX olduğu için Python aksi halde ASCII'ye düşer ve
    `UnicodeEncodeError` fırlatırdı. Bu, Dalga A'dan beri korunan bir davranıştır.
    """
    for akis in (sys.stdout, sys.stderr):
        try:
            akis.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError, OSError):  # pragma: no cover
            pass


def main(argv: list[str] | None = None) -> int:
    _stdout_stderr_utf8()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.komut == "tara":
            return _cmd_tara(args)
        if args.komut == "liste":
            return _cmd_liste(args)
        if args.komut == "sizinti":
            return _cmd_sizinti(args)
        if args.komut == "bulgular":
            return _cmd_bulgular(args)
        if args.komut == "borc":
            return _cmd_borc(args)
        if args.komut == "guncelle":
            return _cmd_guncelle(args)
        if args.komut == "readme":
            return _cmd_readme(args)
        if args.komut == "ozet":
            return _cmd_ozet(args)
        if args.komut == "durum":
            return _cmd_durum(args)
        if args.komut == "web":
            return _cmd_web(args)
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
