"""orkestra komut satırı arayüzü (Dalga A)."""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .models import Durum, OrkestraHata
from .queue import Queue

DURUM_LISTESI = [d.value for d in Durum]

ACIKLAMA = (
    "Ajan Orkestrasi — gorev kuyrugu. Dalga A: kuyruk + CLI. "
    "Gercek calistirici B dalgasinda gelir."
)

ALT_KOMUT_ACIKLAMA = {
    "ver": "Kuyruga yeni gorev ekler",
    "liste": "Gorevleri listeler",
    "iptal": "Gorevi iptal eder",
    "tekrar": "Hatali gorevi yeniden denemeye alir",
    "calistir-bir": "Siradaki bekleyen gorevi calistirir (B dalgasinda)",
}


def _utf8_konfigure() -> None:
    """Windows cp1252 konsolunda Turkce karakter cokmesini onler."""
    for akis in (sys.stdout, sys.stderr):
        yeniden = getattr(akis, "reconfigure", None)
        if yeniden is not None:
            try:
                yeniden(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


DB_YARDIM = (
    "Veritabani dosyasi (varsayilan: ORKESTRA_DB veya ~/.orkestra/orkestra.db)"
)


def _kur() -> argparse.ArgumentParser:
    ayrac = argparse.ArgumentParser(prog="orkestra", description=ACIKLAMA)
    ayrac.add_argument("--surum", action="version", version=f"orkestra {__version__}")
    ayrac.add_argument("--db", default=None, metavar="YOL", help=DB_YARDIM)
    alt = ayrac.add_subparsers(dest="komut", required=True, metavar="KOMUT")

    p_ver = alt.add_parser("ver", help=ALT_KOMUT_ACIKLAMA["ver"])
    p_ver.add_argument("--ajan", required=True, metavar="AD", help="Ajan adi, orn. bunny-coder")
    p_ver.add_argument("istem", metavar="ISTEM", help="Gorev metni")
    p_ver.add_argument("--db", dest="alt_db", default=None, metavar="YOL", help=DB_YARDIM)

    p_liste = alt.add_parser("liste", help=ALT_KOMUT_ACIKLAMA["liste"])
    p_liste.add_argument("--durum", choices=DURUM_LISTESI, default=None, help="Duruma gore filtre")
    p_liste.add_argument("--db", dest="alt_db", default=None, metavar="YOL", help=DB_YARDIM)

    p_iptal = alt.add_parser("iptal", help=ALT_KOMUT_ACIKLAMA["iptal"])
    p_iptal.add_argument("id", type=int, metavar="ID")
    p_iptal.add_argument("--db", dest="alt_db", default=None, metavar="YOL", help=DB_YARDIM)

    p_tekrar = alt.add_parser("tekrar", help=ALT_KOMUT_ACIKLAMA["tekrar"])
    p_tekrar.add_argument("id", type=int, metavar="ID")
    p_tekrar.add_argument("--db", dest="alt_db", default=None, metavar="YOL", help=DB_YARDIM)

    alt.add_parser("calistir-bir", help=ALT_KOMUT_ACIKLAMA["calistir-bir"])
    return ayrac


def _ver(kuyruk: Queue, args) -> int:
    gorev = kuyruk.ekle(args.ajan, args.istem)
    print(f"Gorev #{gorev.id} eklendi: ajan={gorev.ajan} durum={gorev.durum.value}")
    return 0


def _liste(kuyruk: Queue, args) -> int:
    gorevler = kuyruk.liste(args.durum)
    if not gorevler:
        print("Kuyruk bos.")
        return 0
    print(f"{'ID':>4}  {'DURUM':<14}  {'AJAN':<16}  {'OLUSTURMA':<20}  ISTEM")
    for gorev in gorevler:
        print(
            f"{gorev.id:>4}  {gorev.durum.value:<14}  {gorev.ajan:<16}  "
            f"{gorev.olusturma:<20}  {gorev.onizleme}"
        )
    print(f"Toplam {len(gorevler)} gorev.")
    return 0


def _iptal(kuyruk: Queue, args) -> int:
    onceki = kuyruk.al(args.id).durum.value
    gorev = kuyruk.iptal(args.id)
    print(f"Gorev #{gorev.id} iptal edildi (onceki durum: {onceki}).")
    return 0


def _tekrar(kuyruk: Queue, args) -> int:
    gorev = kuyruk.tekrar(args.id)
    print(f"Gorev #{gorev.id} yeniden denemeye alindi: durum={gorev.durum.value}")
    return 0


def main(argv: list[str] | None = None) -> int:
    _utf8_konfigure()
    ayrac = _kur()
    args = ayrac.parse_args(argv)
    # `--db` komuttan önce veya sonra verilebilir; alt komut bayrağı üstü ezer.
    if getattr(args, "alt_db", None) is not None:
        args.db = args.alt_db

    if args.komut == "calistir-bir":
        print("calistir-bir icin gercek calistirici B dalgasinda gelecek.")
        return 2

    try:
        with Queue(args.db) as kuyruk:
            if args.komut == "ver":
                return _ver(kuyruk, args)
            if args.komut == "liste":
                return _liste(kuyruk, args)
            if args.komut == "iptal":
                return _iptal(kuyruk, args)
            if args.komut == "tekrar":
                return _tekrar(kuyruk, args)
    except OrkestraHata as hata:
        print(f"Hata: {hata}", file=sys.stderr)
        return 1
    ayrac.error(f"bilinmeyen komut: {args.komut}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())