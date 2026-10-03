"""devtemizle komut satiri: tara / goster / sil.

Cikis kodlari: 0 basari (silinemedi olmasi HATA DEGIL), 2 kullanim/kesif hatasi.
Guvenlik: silme varsayilan olarak kuru calistirmadir; ayrinti icin bkz. sil.py.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import rapor, tara as tara_modul
from .kesif import KesifHatasi, repo_listesi
from .sil import sil
from .tara import ADAYLAR

KULLANIM_HATASI = 2


def _tara(args: argparse.Namespace) -> int:
    repolar = repo_listesi(
        [Path(r) for r in args.root] or None,
        Path(args.atlas_db) if args.atlas_db else None,
    )
    print(f"{len(repolar)} repo bulundu, taraniyor...", file=sys.stderr)

    adaylar = tara_modul.tara(repolar)
    veri = rapor.olustur(adaylar)
    yol = rapor.kaydet(veri)
    if args.json:
        print(json.dumps({**veri, "rapor": str(yol)}, ensure_ascii=False, indent=2))
    else:
        print(rapor.tablo(veri))
        print(f"\nrapor: {yol}")
    return 0


def _goster(args: argparse.Namespace) -> int:
    veri = rapor.yukle()
    if not veri:
        print(
            "Hata: rapor bulunamadi. Once `devtemizle tara` calistirin "
            f"(beklenen: {rapor._yol()}).",
            file=sys.stderr,
        )
        return KULLANIM_HATASI
    if args.json:
        print(json.dumps(veri, ensure_ascii=False, indent=2))
    else:
        print(f"tarih: {veri.get('tarih')}")
        print(rapor.tablo(veri))
    return 0


def _sil(args: argparse.Namespace) -> int:
    if args.yas < 0:
        raise ValueError(f"--yas negatif olamaz: {args.yas}")
    repolar = repo_listesi(
        [Path(r) for r in args.root] or None,
        Path(args.atlas_db) if args.atlas_db else None,
    )
    print(f"{len(repolar)} repo bulundu, taraniyor...", file=sys.stderr)

    sonuc = sil(repolar, args.uygula, yas=args.yas, turler=args.tur or None)
    if args.json:
        print(json.dumps(sonuc, ensure_ascii=False, indent=2, default=str))
    else:
        print(rapor.sil_ozeti(sonuc, args.uygula))
    return 0


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="devtemizle",
        description="Repolardaki node_modules/__pycache__/sanal ortam klasorlerini "
                    "yasina gore temizler (varsayilan: kuru calistirma)",
    )
    alt = p.add_subparsers(dest="komut", required=True)

    t = alt.add_parser("tara", help="repolari tara, raporu kaydet")
    t.add_argument("--root", action="append", default=[], metavar="YOL",
                   help="taranacak kok (birden fazla verilebilir; verilmezse atlas DB)")
    t.add_argument("--atlas-db", default=None, help="atlas veritabani (varsayilan: ATLAS_DB veya ~/.atlas/atlas.db)")
    t.add_argument("--json", action="store_true", help="JSON olarak yaz")
    t.set_defaults(isle=_tara)

    g = alt.add_parser("goster", help="son raporu goster")
    g.add_argument("--json", action="store_true", help="JSON olarak yaz")
    g.set_defaults(isle=_goster)

    s = alt.add_parser("sil", help="eski aday klasorleri sil (varsayilan: kuru calistirma)")
    s.add_argument("--root", action="append", default=[], metavar="YOL",
                   help="taranacak kok (birden fazla verilebilir; verilmezse atlas DB)")
    s.add_argument("--atlas-db", default=None, help="atlas veritabani (varsayilan: ATLAS_DB veya ~/.atlas/atlas.db)")
    s.add_argument("--uygula", action="store_true", help="gercekten sil (yoksa yalnizca rapor)")
    s.add_argument("--tur", action="append", default=[], choices=sorted(ADAYLAR),
                   help="sadece bu tur (birden fazla verilebilir; verilmezse hepsi)")
    s.add_argument("--yas", type=float, default=7.0,
                   help="bu yastan eski adaylar silinir (gun; 0 = yas filtresi yok, varsayilan: 7)")
    s.add_argument("--json", action="store_true", help="JSON olarak yaz")
    s.set_defaults(isle=_sil)
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
    except KesifHatasi as exc:
        print(f"Hata: {exc}", file=sys.stderr)
        return KULLANIM_HATASI
    except ValueError as exc:
        print(f"Hata: gecersiz deger ({exc})", file=sys.stderr)
        return KULLANIM_HATASI


if __name__ == "__main__":
    raise SystemExit(main())