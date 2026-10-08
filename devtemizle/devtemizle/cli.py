"""devtemizle komut satiri: tara / goster / sil / web.

Cikis kodlari: 0 basari (silinemedi olmasi HATA DEGIL), 2 kullanim/kesif hatasi.
Guvenlik: silme varsayilan olarak kuru calistirmadir; ayrinti icin bkz. sil.py.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import is_akisi, rapor
from .kesif import KesifHatasi, repo_listesi
from .sil import sil, sil_idler
from .turler import tur_adlari

KULLANIM_HATASI = 2


def _tara(args: argparse.Namespace) -> int:
    def ilerleme(adim: str, i: int, n: int) -> None:
        if adim == "kesif":
            print(f"{n} repo bulundu, taraniyor...", file=sys.stderr)

    veri = is_akisi.tam_tarama(
        [Path(r) for r in args.root] or None,
        atlas_db=Path(args.atlas_db) if args.atlas_db else None,
        derinlik=args.derinlik,
        ev=args.ev,
        onbellek=args.onbellek,
        ilerleme=ilerleme,
    )
    yol = rapor._yol()  # tam_tarama raporu bu yola yazar (kaydet varsayilani)
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
        print(f"olusturma: {veri.get('olusturma')}")
        print(f"sure_sn: {veri.get('sure_sn', 0):.1f}")
        print(rapor.tablo(veri))
        # Onbellek ozet
        if veri.get("onbellekler"):
            print("\nOnbellekler:")
            for o in veri["onbellekler"]:
                if o.get("var"):
                    print(f"  {o['ad']:12} {rapor.boyut_yaz(o['boyut']):>8}  {o['risk']}  {o['aciklama']}")
        # Docker ozet
        if veri.get("docker", {}).get("var"):
            d = veri["docker"]
            print(f"\nDocker: imaj={rapor.boyut_yaz(d['imaj'])} konteyner={rapor.boyut_yaz(d['konteyner'])} "
                  f"volume={rapor.boyut_yaz(d['volume'])} build={rapor.boyut_yaz(d['build_cache'])}")
        # Repo ozet
        if veri.get("repolar"):
            print("\nRepolar:")
            for r in veri["repolar"]:
                kirli = " *" if r.get("kirli") else ""
                print(f"  {Path(r['yol']).name}{kirli}  aday_boyut={rapor.boyut_yaz(r.get('aday_boyut', 0))}")
    return 0


def _sil(args: argparse.Namespace) -> int:
    if args.yas < 0:
        raise ValueError(f"--yas negatif olamaz: {args.yas}")

    # ID listesiyle silme (yeni)
    if args.id:
        sonuc = sil_idler(
            idler=args.id,
            onbellek_adlar=args.onbellek_ad,
            uygula=args.uygula,
            dikkat_dahil=args.dikkat_dahil,
        )
        if args.json:
            print(json.dumps(sonuc, ensure_ascii=False, indent=2, default=str))
        else:
            print(rapor.sil_ozeti(sonuc, args.uygula))
            if sonuc.get("onbellek_sonuclari"):
                print("\nOnbellek sonuclari:")
                for o in sonuc["onbellek_sonuclari"]:
                    durum = "OK" if o.get("basarili") else f"HATA: {o.get('hata')}"
                    print(f"  {o['ad']:12} {durum}")
        return 0

    # Eski davranis: tara + filtre + sil (geriye uyumlu)
    repolar = repo_listesi(
        [Path(r) for r in args.root] or None,
        Path(args.atlas_db) if args.atlas_db else None,
        derinlik=args.derinlik,
        ev=args.ev,
    )
    print(f"{len(repolar)} repo bulundu, taraniyor...", file=sys.stderr)

    sonuc = sil(repolar, args.uygula, yas=args.yas, turler=args.tur or None)
    if args.json:
        print(json.dumps(sonuc, ensure_ascii=False, indent=2, default=str))
    else:
        print(rapor.sil_ozeti(sonuc, args.uygula))
    return 0


def _web(args: argparse.Namespace) -> int:
    """Yerel web panelini baslatir (Flask gerektirir: pip install -e .[web])."""
    try:
        from .web import calistir
    except ImportError as exc:
        if (exc.name or "").split(".")[0] in ("flask", "werkzeug", "jinja2"):
            print("Hata: Flask kurulu degil. Web paneli icin: pip install -e .[web]", file=sys.stderr)
            return KULLANIM_HATASI
        raise
    calistir(
        port=args.port,
        ac=args.ac,
        kokler=[Path(r) for r in args.root] or None,
        ev=args.ev,
    )
    return 0


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="devtemizle",
        description="Repolardaki derleme/dev artiklarini tarayip yasina gore temizler (varsayilan: kuru calistirma)",
    )
    alt = p.add_subparsers(dest="komut", required=True)

    # tara
    t = alt.add_parser("tara", help="repolari tara, raporu kaydet")
    t.add_argument("--root", action="append", default=[], metavar="YOL",
                   help="taranacak kok (birden fazla verilebilir; verilmezse atlas DB)")
    t.add_argument("--atlas-db", default=None, help="atlas veritabani (varsayilan: ATLAS_DB veya ~/.atlas/atlas.db)")
    t.add_argument("--derinlik", type=int, default=3, metavar="N",
                   help="kok altinda aranacak derinlik (varsayilan: 3, en cok: 8)")
    t.add_argument("--ev", action="store_true",
                   help="ev dizininden tarama (derinlik 5, bazi dizinler hariç tutulur)")
    t.add_argument("--onbellek", action="store_true",
                   help="genel onbellekleri de tara (pip, npm, cargo, docker raporu...)")
    t.add_argument("--json", action="store_true", help="JSON olarak yaz")
    t.set_defaults(isle=_tara)

    # goster
    g = alt.add_parser("goster", help="son raporu goster")
    g.add_argument("--json", action="store_true", help="JSON olarak yaz")
    g.set_defaults(isle=_goster)

    # sil
    s = alt.add_parser("sil", help="eski aday klasorleri sil (varsayilan: kuru calistirma)")
    s.add_argument("--root", action="append", default=[], metavar="YOL",
                   help="taranacak kok (birden fazla verilebilir; verilmezse atlas DB)")
    s.add_argument("--atlas-db", default=None, help="atlas veritabani (varsayilan: ATLAS_DB veya ~/.atlas/atlas.db)")
    s.add_argument("--derinlik", type=int, default=3, metavar="N",
                   help="kok altinda aranacak derinlik (varsayilan: 3, en cok: 8)")
    s.add_argument("--ev", action="store_true",
                   help="ev dizininden tarama (derinlik 5, bazi dizinler hariç tutulur)")
    s.add_argument("--uygula", action="store_true", help="gercekten sil (yoksa yalnizca rapor)")
    s.add_argument("--tur", action="append", default=[], choices=sorted(tur_adlari()),
                   help="sadece bu tur (birden fazla verilebilir; verilmezse hepsi)")
    s.add_argument("--yas", type=float, default=7.0,
                   help="bu yastan eski adaylar silinir (gun; 0 = yas filtresi yok, varsayilan: 7)")
    s.add_argument("--dikkat-dahil", action="store_true",
                   help="risk='dikkat' olan adaylari da sil (varsayilan: sadece guvenli)")
    s.add_argument("--onbellek", action="append", default=[], dest="onbellek_ad", metavar="AD",
                   help="onbellek temizle (pip, npm, yarn, pnpm, uv, cargo, gradle, playwright, huggingface)")
    s.add_argument("--id", action="append", default=[], metavar="ID",
                   help="rapor ID'siyle sil (baska filtreler yoksa sadece bu ID'ler)")
    s.add_argument("--json", action="store_true", help="JSON olarak yaz")
    s.set_defaults(isle=_sil)

    # web
    w = alt.add_parser("web", help="yerel web paneli baslat (Flask gerektirir)")
    w.add_argument("--port", type=int, default=8796, help="port (varsayilan: 8796)")
    w.add_argument("--ac", action="store_true", help="tarayiciyi ac")
    w.add_argument("--root", action="append", default=[], metavar="YOL",
                   help="panelin tarayacagi kok (birden fazla verilebilir; verilmezse atlas DB)")
    w.add_argument("--ev", action="store_true",
                   help="ev dizininden tarama (derinlik 5, bazi dizinler hariç tutulur)")
    w.set_defaults(isle=_web)

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