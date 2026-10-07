"""mezar komut satiri: denetle.

Cikis kodlari: 0 hepsi repo KAPATILABILIR, 1 en az biri DIKKAT,
2 kullanim/kesif hatasi (`Hata: ...` stderr'e, traceback YOK).

Guvenlik (baglayici): arac SALT OKUNUR. `--uygala` YOKTUR ve OLMAMALIDIR:
silme, arsivleme, push, fetch ya da ag erisimi hicbir yerde bulunmaz.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import gecmis, karar as karar_mod, rapor as rapor_mod
from .kesif import KesifHatasi

BULGU_VAR = 1
KULLANIM_HATASI = 2


def _denetle(args: argparse.Namespace) -> int:
    if args.satir_limiti <= 0:
        raise ValueError(f"--satir-limiti pozitif olmali: {args.satir_limiti}")
    if args.sure_limiti <= 0:
        raise ValueError(f"--sure-limiti pozitif olmali: {args.sure_limiti}")
    kok = Path(args.kok)
    arac_repo = Path(args.arac_repo)
    veri = karar_mod.denetle(
        kok,
        arac_repo,
        args.repo,
        satir_limiti=args.satir_limiti,
        sure_limiti=args.sure_limiti,
    )
    if args.json:
        print(json.dumps(veri, ensure_ascii=False, indent=2))
    else:
        print(rapor_mod.metin(veri))
    o = veri["ozet"]
    return 0 if o["dikkat"] == 0 else BULGU_VAR


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mezar",
        description="Bosaltilmis ('mezar tasi') repolari silmeden/arşivlemeden ONCE "
                    "denetler. TAMAMEN SALT OKUNUR: silmez, arşivlemez, ag erişimi yoktur.",
    )
    alt = p.add_subparsers(dest="komut", required=True)

    d = alt.add_parser("denetle", help="repolari denetle (KAPATILABILIR / DIKKAT)")
    d.add_argument("--kok", required=True, metavar="DIZIN",
                   help="repo kok dizini (--repo adlari bunun ALTINDA aranir)")
    d.add_argument("--arac-repo", required=True, metavar="DIZIN",
                   help="araclar monoreposu (tasinan kodun yeni yeri: <arac-repo>/<ad>/)")
    d.add_argument("--repo", action="append", default=[], metavar="ad", required=True,
                   help="denetlenecek repo adi = <kok>/<ad> (birden fazla verilebilir)")
    d.add_argument("--satir-limiti", type=int, default=gecmis.SATIR_LIMITI,
                   help=f"gecmis taramasi icin azami satir (varsayilan: {gecmis.SATIR_LIMITI})")
    d.add_argument("--sure-limiti", type=float, default=gecmis.SURE_LIMITI,
                   help=f"gecmis taramasi icin azami sure, sn (varsayilan: {gecmis.SURE_LIMITI:.0f})")
    d.add_argument("--json", action="store_true", help="JSON olarak yaz")
    d.set_defaults(isle=_denetle)
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