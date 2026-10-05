"""servis komut satiri: durum / baslat / durdur.

Cikis kodlari: 0 istenen tum servisler hedef durumda, 1 en az biri hedefte
degil, 2 kullanim/tanim hatasi (`Hata: ...` stderr'e, traceback yok).
Guvenlik: durdurma yalniz kendi pid dosyamizdaki sureci yapar.
"""

from __future__ import annotations

import argparse
import json
import sys

from . import durum as durum_modul
from . import surec as surec_modul
from .tanim import ServisHatasi, sec, yukle

KULLANIM_HATASI = 2
HEDEF_DEGIL = 1

#: hedef duruma ulasilan sonuclar (baslat/durdur icin "tamam" sayilanlar)
BASLAT_OK = (surec_modul.CALISTI, surec_modul.ZATEN_CALISIYOR, surec_modul.KURU)
DURDUR_OK = (surec_modul.DURDU_SONUC, surec_modul.ZATEN_DURDU, surec_modul.KURU)


def _coz(args: argparse.Namespace):
    """Tanimi bir kez okur, secilen servisleri dondurur."""
    return sec(yukle(args.tanim), args.ad)


def _durum(args: argparse.Namespace) -> int:
    olcumler = [durum_modul.olc(s) for s in _coz(args)]
    if args.json:
        print(json.dumps(olcumler, ensure_ascii=False, indent=2))
    else:
        print(durum_modul.tablo(olcumler))
    return 0 if all(o["durum"] == durum_modul.CALISIYOR for o in olcumler) else HEDEF_DEGIL


def _baslat(args: argparse.Namespace) -> int:
    sonuclar = [surec_modul.baslat(s, kuru=args.kuru) for s in _coz(args)]
    if args.json:
        print(json.dumps(sonuclar, ensure_ascii=False, indent=2))
    else:
        if args.kuru:
            print("KURU CALISTIRMA: hicbir surec baslatilmadi.")
        for s in sonuclar:
            print(f"  {s['ad']}: {s['sonuc']}  {s['mesaj']}")
            if s["sonuc"] == surec_modul.BASARISIZ:
                for satir in surec_modul.log_son_satirlar(s["ad"]):
                    print(f"      | {satir}")
    return 0 if all(s["sonuc"] in BASLAT_OK for s in sonuclar) else HEDEF_DEGIL


def _durdur(args: argparse.Namespace) -> int:
    sonuclar = [surec_modul.durdur(s, zorla=args.zorla, kuru=args.kuru) for s in _coz(args)]
    if args.json:
        print(json.dumps(sonuclar, ensure_ascii=False, indent=2))
    else:
        if args.kuru:
            print("KURU CALISTIRMA: hicbir surec oldurulmedi.")
        for s in sonuclar:
            print(f"  {s['ad']}: {s['sonuc']}  {s['mesaj']}")
    return 0 if all(s["sonuc"] in DURDUR_OK for s in sonuclar) else HEDEF_DEGIL


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="servis",
        description="Yerel servis yiginini (cor, kule, liman, readbunny-postgres) "
                    "baslatir, durdurur ve durumunu gosterir. Kabuk calistirmaz.",
    )
    alt = p.add_subparsers(dest="komut", required=True)

    def ortak(q: argparse.ArgumentParser) -> None:
        q.add_argument("ad", nargs="*", help="servis adi (verilmezse tum tanimli servisler)")
        q.add_argument("--tanim", default=None, metavar="DOSYA.toml",
                       help="tanim dosyasi (varsayilan: SERVIS_TANIM veya ~/.servis/servisler.toml)")
        q.add_argument("--json", action="store_true", help="JSON olarak yaz")

    d = alt.add_parser("durum", help="her servisin durumunu goster")
    ortak(d)
    d.set_defaults(isle=_durum)

    b = alt.add_parser("baslat", help="servisleri baslat (calisanlar atlanir)")
    ortak(b)
    b.add_argument("--kuru", action="store_true", help="hicbir sey baslatma, ne yapilacagini yaz")
    b.set_defaults(isle=_baslat)

    s = alt.add_parser("durdur", help="servisleri durdur (yalniz kendi pid dosyamizdakiler)")
    ortak(s)
    s.add_argument("--zorla", action="store_true", help="SIGTERM'e yanit vermeyene SIGKILL")
    s.add_argument("--kuru", action="store_true", help="hicbir sey oldurme, ne yapilacagini yaz")
    s.set_defaults(isle=_durdur)
    return p


def main(argv: list[str] | None = None) -> int:
    for akim in (sys.stdout, sys.stderr):
        try:
            akim.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    args = _parser().parse_args(argv)
    try:
        return args.isle(args)
    except ServisHatasi as exc:
        print(f"Hata: {exc}", file=sys.stderr)
        return KULLANIM_HATASI
    except ValueError as exc:
        print(f"Hata: {exc}", file=sys.stderr)
        return KULLANIM_HATASI
    except OSError as exc:
        print(f"Hata: {exc}", file=sys.stderr)
        return KULLANIM_HATASI


if __name__ == "__main__":
    raise SystemExit(main())