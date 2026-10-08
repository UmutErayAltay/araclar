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

from . import rapor, tara as tara_modul
from .kesif import KesifHatasi, repo_listesi, repo_meta_listesi
from .onbellek import docker_boyutlari, onbellek_tara
from .sil import sil, sil_idler
from .turler import tur_adlari

KULLANIM_HATASI = 2


def _tara(args: argparse.Namespace) -> int:
    baslangic = time.time()
    repolar = repo_listesi(
        [Path(r) for r in args.root] or None,
        Path(args.atlas_db) if args.atlas_db else None,
        derinlik=args.derinlik,
        ev=args.ev,
    )
    print(f"{len(repolar)} repo bulundu, taraniyor...", file=sys.stderr)

    adaylar = tara_modul.tara(repolar)
    meta_listesi = repo_meta_listesi(repolar)
    onbellekler = onbellek_tara() if args.onbellek else []
    docker = docker_boyutlari() if args.onbellek else {"var": False, "imaj": 0, "konteyner": 0, "volume": 0, "build_cache": 0}

    # Repo meta -> dict
    repolar_dict = [
        {
            "yol": str(m.yol),
            "son_commit": m.son_commit,
            "kirli": m.kirli,
            "aday_boyut": sum(a.get("boyut", 0) for a in adaylar if a.get("repo") == str(m.yol)),
        }
        for m in meta_listesi
    ]

    veri = rapor.olustur(
        adaylar=adaylar,
        onbellekler=onbellekler,
        docker=docker,
        repolar=repolar_dict,
        simdi=time.time(),
        sure_sn=time.time() - baslangic,
    )
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
    """Web paneli baslatir (Dalga B icin placeholder)."""
    try:
        from .web import app  # type: ignore
    except ImportError as exc:
        if "No module named" in str(exc) and "web" in str(exc):
            print("Hata: Flask kurulu degil. Web paneli icin: pip install -e .[web]", file=sys.stderr)
            return KULLANIM_HATASI
        raise
    print(f"Web paneli baslatiliyor: http://127.0.0.1:{args.port}")
    app.run(host="127.0.0.1", port=args.port, debug=False)
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
    w.add_argument("--ac", action="store_true", help="tarayiciyi ac (henuz uygulanmadi)")
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