"""maske komut satiri: tara / uygula.

Cikis kodlari: 0 bulgu yok, 1 bulgu var, 2 kullanim/kesif hatasi (`Hata: ...`
stderr'e, traceback YOK). Guvenlik: ham deger ne cikisa ne hataya girer.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import maskele, rapor as rapor_mod, tara
from .kesif import KesifHatasi, repo_listesi

BULGU_VAR = 1
KULLANIM_HATASI = 2


def _tara(args: argparse.Namespace) -> int:
    repolar = repo_listesi(args.kok)
    print(f"{len(repolar)} repo bulundu, taraniyor...", file=sys.stderr)
    veri = tara.tara(repolar)
    if args.json:
        print(json.dumps(rapor_mod.json_ve(veri, kuru=True), ensure_ascii=False, indent=2))
    else:
        print(rapor_mod.tablo(veri, kuru=True))
    return BULGU_VAR if veri["bulgar"] else 0


def _uygula(args: argparse.Namespace) -> int:
    repolar = repo_listesi(args.kok)
    print(f"{len(repolar)} repo bulundu, taraniyor...", file=sys.stderr)
    veri = maskele.uygula(repolar, args.uygula)
    if args.json:
        print(json.dumps(rapor_mod.json_ve(veri, kuru=not args.uygula), ensure_ascii=False, indent=2))
    else:
        if not args.uygula:
            print("KURU CALISTIRMA: hicbir dosya yazilmadi. Maskelemek icin --uygula ekleyin.")
        print(rapor_mod.tablo(veri, kuru=not args.uygula))
    return BULGU_VAR if veri["bulgar"] else 0


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="maske",
        description="Dosyalardaki gizli anahtarlari (API key/token/parola/ozel anahtar) "
                    "bulur ve yerinde maskeler; varsayilan KURU CALISTIRMA.",
    )
    alt = p.add_subparsers(dest="komut", required=True)

    t = alt.add_parser("tara", help="gizli anahtarlari bul ve RAPORLA (dosyaya yazmaz)")
    t.add_argument("--kok", action="append", default=[], metavar="DIZIN",
                   help="taranacak kok dizin (birden fazla verilebilir)")
    t.add_argument("--json", action="store_true", help="JSON olarak yaz")
    t.set_defaults(isle=_tara)

    u = alt.add_parser("uygula", help="bulgulari maskele (varsayilan: kuru calistirma)")
    u.add_argument("--kok", action="append", default=[], metavar="DIZIN",
                   help="taranacak kok dizin (birden fazla verilebilir)")
    u.add_argument("--uygula", action="store_true", help="gercekten yaz (yoksa yalnizca rapor)")
    u.add_argument("--json", action="store_true", help="JSON olarak yaz")
    u.set_defaults(isle=_uygula)
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
        print(f"Hata: {exc}", file=sys.stderr)
        return KULLANIM_HATASI
    except OSError as exc:
        # Salt-okunur dosya, kilitli dosya: iz (traceback) degil, cikis 2.
        print(f"Hata: {exc}", file=sys.stderr)
        return KULLANIM_HATASI


if __name__ == "__main__":
    raise SystemExit(main())