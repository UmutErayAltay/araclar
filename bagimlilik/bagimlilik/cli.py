"""bagimlilik komut satiri: tara / goster.

Cikis kodlari: 0 basari (acik bulmak HATA DEGIL), 2 kullanim/kesif hatasi.
Guvenlik: repolara hicbir sey yazilmaz; ayrinti icin bkz. denetim.py.
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path

from . import rapor
from .denetim import denetle_repo
from .kesif import KesifHatasi, repo_listesi

KULLANIM_HATASI = 2


def _tara(args: argparse.Namespace) -> int:
    repolar = repo_listesi(
        [Path(r) for r in args.root] or None,
        Path(args.atlas_db) if args.atlas_db else None,
    )
    if not repolar:
        print("Hata: denetlenecek repo bulunamadi.", file=sys.stderr)
        return KULLANIM_HATASI

    print(f"{len(repolar)} repo bulundu, denetleniyor...", file=sys.stderr)
    with ThreadPoolExecutor(max_workers=max(1, args.paralel)) as havuz:
        isler = {havuz.submit(denetle_repo, repo, zaman_asimi=args.zaman_asimi): i
                 for i, repo in enumerate(repolar)}
        # Ilerleme bitis sirasiyla yazilir; rapor tarama sirasiyla korunur.
        sira_bitti = sorted((isler[g], g.result()) for g in as_completed(isler))
    sonuclar = [sonuc for _sira, sonuc in sira_bitti]
    for sira, sonuc in sira_bitti:
        print(f"[{sira + 1}/{len(repolar)}] {sonuc.ad}", file=sys.stderr)

    yol = rapor.kaydet(sonuclar)
    if args.json:
        print(json.dumps({"surum": rapor.SURUM, "rapor": str(yol),
                          "repolar": [asdict(s) for s in sonuclar]}, ensure_ascii=False, indent=2))
    else:
        print(rapor.tablo(sonuclar))
        print(f"\nrapor: {yol}")
    return 0


def _goster(args: argparse.Namespace) -> int:
    veri = rapor.yukle()
    if not veri:
        print(
            "Hata: rapor bulunamadi. Once `bagimlilik tara` calistirin "
            f"(beklenen: {rapor._yol()}).",
            file=sys.stderr,
        )
        return KULLANIM_HATASI
    if args.json:
        print(json.dumps(veri, ensure_ascii=False, indent=2))
    else:
        from .denetim import Acik, Denetim, RepoSonuc

        # asdict cevirdigi icin ic ice donusum SIFIR YAZILIR: Denetim ve aciklar da geri alinir.
        sonuclar = [
            RepoSonuc(
                yol=r["yol"],
                ad=r["ad"],
                denetimler=[
                    Denetim(**{**d, "aciklar": [Acik(**a) for a in d.get("aciklar", [])]})
                    for d in r.get("denetimler", [])
                ],
                desteklenmeyen=r.get("desteklenmeyen", []),
            )
            for r in veri.get("repolar", [])
        ]
        print(f"tarih: {veri.get('tarih')}")
        print(rapor.tablo(sonuclar))
    return 0


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="bagimlilik",
        description="Tum repolarda pip-audit ve npm audit calistirip tek rapor cikarir "
                    "(repolara yazmaz)",
    )
    alt = p.add_subparsers(dest="komut", required=True)

    t = alt.add_parser("tara", help="repolari tara, raporu kaydet")
    t.add_argument("--root", action="append", default=[], metavar="YOL",
                   help="taranacak kok (birden fazla verilebilir; verilmezse atlas DB)")
    t.add_argument("--atlas-db", default=None, help="atlas veritabani (varsayilan: ATLAS_DB veya ~/.atlas/atlas.db)")
    t.add_argument("--paralel", type=int, default=4, help="paralel repo sayisi (varsayilan: 4)")
    t.add_argument("--zaman-asimi", type=int, default=120, help="repo basina saniye (varsayilan: 120)")
    t.add_argument("--json", action="store_true", help="JSON olarak yaz")
    t.set_defaults(isle=_tara)

    g = alt.add_parser("goster", help="son raporu goster")
    g.add_argument("--json", action="store_true", help="JSON olarak yaz")
    g.set_defaults(isle=_goster)
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
