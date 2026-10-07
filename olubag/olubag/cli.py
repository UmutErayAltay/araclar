"""olubag komut satiri: tara.

Cikis kodlari: 0 bulgu yok, 1 bulgu var, 2 kullanim/kesif hatasi.
Guvenlik: SALT OKUNUR — hicbir dosya yazilmaz, yazma bayragi YOKTUR.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import rapor, tara as tara_modul
from .kesif import KesifHatasi, repo_listesi

KULLANIM_HATASI = 2
BULGU_VAR = 1


def _tara(args: argparse.Namespace) -> int:
    repolar = repo_listesi(
        [Path(r) for r in args.kok] or None,
        Path(args.atlas_db) if args.atlas_db else None,
    )
    veri = tara_modul.tara(repolar)
    if args.json:
        print(json.dumps(veri, ensure_ascii=False, indent=2))
    else:
        print(rapor.tablo(veri))
    # Bulgu varsa cikis 1 (CI'ya baglanabilir); belirsiz bulgu sayilir.
    return BULGU_VAR if veri["ozet"]["kullanilmayan"] or veri["ozet"]["belirsiz"] else 0


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="olubag",
        description="Bildirilip hic kullanilmayan bagimliliklari (Python/JS) tarayan "
                    "SALT-OKUNUR CLI",
    )
    alt = p.add_subparsers(dest="komut", required=True)

    t = alt.add_parser("tara", help="repolari tara ve kullanilmayan bagimliliklari goster")
    t.add_argument("--kok", action="append", default=[], metavar="DIZIN",
                   help="taranacak kok dizin (birden fazla verilebilir; verilmezse atlas DB)")
    t.add_argument("--atlas-db", default=None,
                   help="atlas veritabani (varsayilan: ATLAS_DB veya ~/.atlas/atlas.db)")
    t.add_argument("--json", action="store_true", help="JSON olarak yaz")
    t.set_defaults(isle=_tara)
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