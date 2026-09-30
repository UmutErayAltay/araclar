"""`harita` komut satırı arayüzü (Dalga A + Dalga B).

Alt komutlar: indeksle, kirik, yetim, etiketler, web.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

from . import __version__, index as indeks_modulu

BOSLUK = " "


def _akisi_ayarla() -> None:
    """Windows cp1252 konsolunda Türkçe karakterlerin çökmesini engeller."""
    for akis in (sys.stdout, sys.stderr):
        reconfigure = getattr(akis, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def _db_yolu(args: argparse.Namespace) -> Path:
    """Verilen `--db`, yoksa $HARITA_DB / ~/.harita/harita.db."""
    db = getattr(args, "db", None)
    return Path(db).expanduser() if db else indeks_modulu.varsayilan_db()


def _db_ac(db_yolu: str | None) -> sqlite3.Connection:
    yol = Path(db_yolu).expanduser() if db_yolu else indeks_modulu.varsayilan_db()
    if not yol.exists():
        raise SystemExit(f"İndeks bulunamadı: {yol}\nÖnce `harita indeksle VAULT` çalıştır.")
    baglanti = indeks_modulu.baglan(yol)
    indeks_modulu.sema_olustur(baglanti)
    return baglanti


def komut_indeksle(args: argparse.Namespace) -> int:
    vault = Path(args.vault)
    if not vault.is_dir():
        print(f"Hata: vault bulunamadı: {vault}", file=sys.stderr)
        return 2
    db_yolu = _db_yolu(args)
    ozet = indeks_modulu.indeksle(vault, db_yolu)
    print(f"İndeks: {db_yolu}")
    print(ozet.ozet_metni())
    return 0


def komut_kirik(args: argparse.Namespace) -> int:
    baglanti = _db_ac(_db_yolu(args))
    try:
        kirik = indeks_modulu.kirik_linkler(baglanti)
    finally:
        baglanti.close()
    if not kirik:
        print("Kırık link yok.")
        return 0
    print(f"Kırık link: {len(kirik)}")
    for yol, baslik, hedef in kirik[: args.ilk] if args.ilk else kirik:
        print(f"  {yol}{BOSLUK}({baslik}) → [[{hedef}]]")
    if args.ilk and len(kirik) > args.ilk:
        print(f"  ... ve {len(kirik) - args.ilk} tane daha")
    return 0


def komut_yetim(args: argparse.Namespace) -> int:
    baglanti = _db_ac(_db_yolu(args))
    try:
        bolum = indeks_modulu.yetim_ayir(baglanti)
        hepsi = indeks_modulu.yetim_notlar(baglanti)
    finally:
        baglanti.close()

    # Varsayılan: yalnız GERÇEK yetimler. `--tumu` Dalga A davranışını verir
    # (daily/ günlükleri ve kök dosyaları da listeler).
    if args.tumu:
        kayitlar = list(hepsi)
        baslik_satiri = f"Yetim not: {len(kayitlar)}"
    else:
        kayitlar = [(yol, baslik) for _, yol, baslik in bolum.gercek]
        baslik_satiri = f"Yetim not: {len(kayitlar)}"
        if len(bolum.yok_sayilabilir):
            baslik_satiri += f" (yok sayılabilir: {len(bolum.yok_sayilabilir)}, `--tumu` ile gör)"

    if not kayitlar:
        print("Yetim not yok.")
        return 0
    print(baslik_satiri)
    for yol, baslik_ad in kayitlar[: args.ilk] if args.ilk else kayitlar:
        print(f"  {yol}{BOSLUK}({baslik_ad})")
    if args.ilk and len(kayitlar) > args.ilk:
        print(f"  ... ve {len(kayitlar) - args.ilk} tane daha")
    return 0


def komut_etiketler(args: argparse.Namespace) -> int:
    baglanti = _db_ac(_db_yolu(args))
    try:
        etiketler = indeks_modulu.etiket_sikligi(baglanti, args.ilk)
    finally:
        baglanti.close()
    if not etiketler:
        print("Etiket yok.")
        return 0
    en_genis = max((str(adet) for _, adet in etiketler), key=len)
    for etiket, adet in etiketler:
        print(f"  {adet:>{len(en_genis)}}  #{etiket}")
    return 0


def komut_web(args: argparse.Namespace) -> int:
    """Grafi sunar. Sunucu ADRESİ KODDA SABİTTİR: yalnız 127.0.0.1.

    `VAULT` verilirse önce indekslenir (salt okunur); sonra DB `mode=ro` ile
    açılır. `--host` seçeneği BİLEREK YOKTUR: dışarıya açmak için kod
    değiştirmek gerekir.
    """
    from .web import sunucu  # Flask yalnızca bu komutta yüklenir

    db_yolu = _db_yolu(args)
    if args.vault:
        vault = Path(args.vault)
        if not vault.is_dir():
            print(f"Hata: vault bulunamadı: {vault}", file=sys.stderr)
            return 2
        ozet = indeks_modulu.indeksle(vault, db_yolu)
        print(f"İndeks: {db_yolu}")
        print(ozet.ozet_metni())
    elif not db_yolu.exists():
        print(
            f"Hata: indeks bulunamadı: {db_yolu}\n"
            "Önce `harita indeksle VAULT` ya da `harita web VAULT` çalıştır.",
            file=sys.stderr,
        )
        return 2

    print(f"harita web → http://127.0.0.1:{args.port}  (yalnızca yerel; Ctrl+C ile dur)")
    try:
        sunucu.calistir(db_yolu, args.port)
    except KeyboardInterrupt:  # pragma: no cover
        print("\nDurduruldu.")
    return 0


def arg_parser() -> argparse.ArgumentParser:
    # `--db` hem `harita --db X kirik` hem `harita kirik --db X` biçiminde çalışsın.
    # SUPPRESS: alt komut `--db` verilmediğinde, `default=None` üstteki değeri
    # ezip `harita --db X kirik` biçimini bozardı.
    ortak = argparse.ArgumentParser(add_help=False)
    ortak.add_argument(
        "--db",
        default=argparse.SUPPRESS,
        help="SQLite indeks dosyası (varsayılan: $HARITA_DB veya ~/.harita/harita.db)",
    )

    parser = argparse.ArgumentParser(
        prog="harita",
        parents=[ortak],
        description="Vault zihin haritası: not grafiğini indeksler ve sağlığını raporlar.",
    )
    parser.add_argument("--versiyon", action="version", version=f"harita {__version__}")
    alt = parser.add_subparsers(dest="komut", required=True)

    p = alt.add_parser("indeksle", parents=[ortak], help="Vault'u indeksle")
    p.add_argument("vault", help="Vault kökü")
    p.set_defaults(fonksiyon=komut_indeksle)

    p = alt.add_parser("kirik", parents=[ortak], help="Çözülemeyen linkleri listele")
    p.add_argument("--ilk", type=int, default=None, help="Yalnızca ilk N kaydı göster")
    p.set_defaults(fonksiyon=komut_kirik)

    p = alt.add_parser("yetim", parents=[ortak], help="Ne link alan ne link veren notları listele")
    p.add_argument("--ilk", type=int, default=None, help="Yalnızca ilk N kaydı göster")
    p.add_argument(
        "--tumu",
        action="store_true",
        help="`daily/` günlükleri ve kökteki tek-bileşenli dosyalar (yok sayılabilirler) dahil listele",
    )
    p.set_defaults(fonksiyon=komut_yetim)

    p = alt.add_parser("etiketler", parents=[ortak], help="Etiketleri sıklığa göre listele")
    p.add_argument("--ilk", type=int, default=None, help="Yalnızca ilk N etiketi göster")
    p.set_defaults(fonksiyon=komut_etiketler)

    p = alt.add_parser("web", parents=[ortak], help="Grafiği 127.0.0.1 üzerinde sun")
    p.add_argument("vault", nargs="?", help="Verilirse önce salt-okunur indeksler")
    p.add_argument("--port", type=int, default=8765, help="Dinlenecek port (varsayılan: 8765)")
    p.set_defaults(fonksiyon=komut_web)

    return parser


def main(argv: list[str] | None = None) -> int:
    _akisi_ayarla()
    args = arg_parser().parse_args(argv)
    return int(args.fonksiyon(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
