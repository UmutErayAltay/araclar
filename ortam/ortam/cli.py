"""ortam komut satiri: tara.

Cikis kodlari: 0 bulgu yok, 1 bulgu var, 2 kullanim/kesif hatasi.
Guvenlik: arac SALT OKUNURDUR; hicbir komut dosya yazmaz/silmez/duzenlemez.
Degisken DEGERLERI hicbir ciktiya girmez; yalniz ad + dosya:satir raporlanir.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import analiz, kesif, tablo as tablo_modul

KULLANIM_HATASI = 2
BULGU_VAR = 1


def _tara(args: argparse.Namespace) -> int:
    repolar = kesif.repo_listesi([Path(r).expanduser() for r in args.kok])
    print(f"{len(repolar)} repo bulundu, taraniyor...", file=sys.stderr)

    veri = analiz.analiz(repolar)
    if args.json:
        print(json.dumps(veri, ensure_ascii=False, indent=2))
    else:
        print(tablo_modul.tablo(veri))
    return BULGU_VAR if veri["toplam"] else 0


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ortam",
        description="Ortam degiskeni denetleyicisi: kod kullanimlarini .env.example, "
                    "README ve docker-compose ile karsilastirir. SALT OKUNUR.",
    )
    alt = p.add_subparsers(dest="komut", required=True)

    t = alt.add_parser("tara", help="repolari tara, bulgulari raporla")
    t.add_argument("--kok", action="append", metavar="DIZIN", required=True,
                   help="taranacak kok dizin (coklu verilebilir)")
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
    except kesif.KesifHatasi as exc:
        print(f"Hata: {exc}", file=sys.stderr)
        return KULLANIM_HATASI
    except OSError as exc:
        print(f"Hata: {exc}", file=sys.stderr)
        return KULLANIM_HATASI


if __name__ == "__main__":
    raise SystemExit(main())
