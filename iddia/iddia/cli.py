"""iddia komut satiri: `iddia tara --kok DIZIN...`.

Cikis kodlari:
- 0 : tarama bitti, BULGU YOK.
- 1 : tarama bitti, en az bir bulgu var.
- 2 : kullanim/kesif hatasi (yol yok, repo yok).

Guvenlik: arac SALT OKUNURDUR; hicbir komut dosya yazmaz ve `--uygula`
bayragi YOKTUR. Bulgu metinleri README'den ve sayimlardan gelir; gizli
degerlerin ham hali bu aracin konusu degildir.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import denetle as denetle_modul
from . import rapor
from .kesif import KesifHatasi, repo_listesi

KULLANIM_HATASI = 2
BULGU_VAR = 1


def _tara(args: argparse.Namespace) -> int:
    repolar = repo_listesi([Path(r) for r in args.kok])
    bulgular = denetle_modul.denetle(repolar)
    if args.json:
        print(json.dumps(rapor.json_uret(bulgular, repolar), ensure_ascii=False, indent=2))
    else:
        print(f"{len(repolar)} repo tarandi; salt-okunur.")
        print(rapor.tablo(bulgular))
    return BULGU_VAR if bulgular else 0


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="iddia",
        description="Repo README'lerindeki somut iddialari (test sayisi, dosya yolu, "
                    "CLI bayragi, komut sayisi) kodun gercegiyle karsilastirir. SALT OKUNUR.",
    )
    alt = p.add_subparsers(dest="komut", required=True)

    t = alt.add_parser("tara", help="verilen koklerin altindaki repolarda README iddialarini denetle")
    t.add_argument("--kok", action="append", default=[], metavar="DIZIN", required=True,
                   help="taranacak kok dizin (birden fazla verilebilir)")
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
    except OSError as exc:
        # Salt-okunur tarama: kilitli/bozuk dosya -> iz (traceback) degil, cikis 2.
        print(f"Hata: {exc}", file=sys.stderr)
        return KULLANIM_HATASI


if __name__ == "__main__":
    raise SystemExit(main())