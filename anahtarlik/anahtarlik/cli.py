"""anahtarlik komut satiri: tara / goster / not / eski / hook-kur / hook-tara / fark.

Cikis kodlari: 0 basari, 2 kullanim / kesif / envanter-dosya hatasi (OSError dahil).
Guvenlik: ham deger ne cikisa ne hataya girer; ekranda yalniz AD + parmak izi.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from . import envanter, github, hook, kesif

KULLANIM_HATASI = 2


def _tara(args: argparse.Namespace) -> int:
    kokler = [Path(r).expanduser() for r in (args.root or [])]
    repolar = kesif.repo_listesi(kokler or None, Path(args.atlas_db) if args.atlas_db else None)
    veri = envanter.tara(repolar)
    yol = envanter.kaydet(veri)
    ozet = f"envanter: {yol}"
    if args.json:
        print(json.dumps({**veri, "envanter": str(yol)}, ensure_ascii=False, indent=2))
    else:
        print(envanter.tablo(veri))
        print(f"\n{ozet}")
    return 0


def _goster(args: argparse.Namespace) -> int:
    veri = envanter.yukle()
    if not veri:
        print(
            "Hata: envanter bulunamadi. Once `anahtarlik tara` calistirin "
            f"(beklenen: {envanter._yol()}).",
            file=sys.stderr,
        )
        return KULLANIM_HATASI
    if args.json:
        print(json.dumps(veri, ensure_ascii=False, indent=2))
    else:
        print(envanter.tablo(veri))
    return 0


def _not(args: argparse.Namespace) -> int:
    try:
        date.fromisoformat(args.tarih)
    except ValueError:
        print(
            f"Hata: --tarih YYYY-MM-DD biciminde olmali (verilen: {args.tarih}).",
            file=sys.stderr,
        )
        return KULLANIM_HATASI
    envanter.not_ekle(args.ad, args.tarih, args.aciklama)
    print(f"not kaydedildi: {args.ad} ({args.tarih}) -- 90 gun sonra `eski` listesinde")
    return 0


def _eski(args: argparse.Namespace) -> int:
    veri = envanter.yukle()
    if not veri:
        print(
            "Hata: envanter bulunamadi. Once `anahtarlik tara` calistirin "
            f"(beklenen: {envanter._yol()}).",
            file=sys.stderr,
        )
        return KULLANIM_HATASI
    kalan = envanter.eski_olanlar(veri, envanter.notlari_yukle(), args.gun)
    if args.json:
        print(json.dumps({"gun": args.gun, "eski": kalan}, ensure_ascii=False, indent=2))
        return 0
    if not kalan:
        print(f"rotasyon notu olmayan ya da {args.gun} gunden eski anahtar yok")
        return 0
    print(f"{args.gun} gunu gecen ya da notsuz ({len(kalan)} anahtar):")
    for kart in kalan:
        not_ = kart.get("not") or {}
        not_roku = f"  [not {not_.get('tarih')}]" if not_.get("tarih") else ""
        print(f"  {kart['ad']}  {kart.get('izi') or 'kisa'}  {kart.get('repo')}{not_roku}")
    return 0


def _hook_kur(args: argparse.Namespace) -> int:
    repo = Path(args.repo).expanduser()
    s = hook.kur(repo, uygula=args.uygula, ortak=args.ortak)
    if args.json:
        print(json.dumps(s, ensure_ascii=False, indent=2))
    elif s["durum"] == "ortak-hooks-dizini":
        print(f"core.hooksPath repo disini gosteriyor: {s['hooks_dizini']}\n"
              "Bu dizindeki hook TUM repolarda calisir; yine de kurmak icin --ortak ekleyin.")
    elif s["durum"] == "eski-surum":
        # Guvenlik acigi olan onceki surum: kullanici aksiyonu gerekir.
        print(f"eski-surum: {s['yol']}\n"
              "Bu hook modulun guvenli yuklemiyi kullanmiyor (-P yok). "
              "Yenilemek icin --uygala ekleyin.", file=sys.stderr)
    else:
        ek = "  (kuru calistirma; yazmak icin --uygula)" if s["durum"] == "yok" else ""
        print(f"{s['durum']}: {s['yol']}{ek}")
    return 0 if s["durum"] in ("yok", "yazildi", "guncel") else KULLANIM_HATASI


def _hook_tara(args: argparse.Namespace) -> int:
    return hook.hook_tara_main(sys.stdin, Path.cwd())


def _fark(args: argparse.Namespace) -> int:
    repo = Path(args.repo).expanduser()
    yerel = {k["ad"] for r in envanter.tara([repo])["repolar"] for k in r["anahtarlar"]}
    s = github.fark(repo, github.workflow_secretlari(repo), yerel_adlar=yerel)
    if args.json:
        print(json.dumps(s, ensure_ascii=False, indent=2))
        return 0
    if s["durum"] != "tamam":
        print(f"durum: {s['durum']}", file=sys.stderr)
        return KULLANIM_HATASI
    basliklar = {
        "workflow_var_gh_yok": "workflow kullaniyor, GitHub'da TANIMSIZ (CI kirilir)",
        "gh_var_workflow_kullanmiyor": "GitHub'da tanimli, workflow kullanmiyor",
        "yerel_var_gh_yok": "yerel .env'de var, GitHub'da yok",
        "gh_var_yerel_yok": "GitHub'da var, yerel .env'de yok",
    }
    for anahtar, baslik in basliklar.items():
        print(f"{baslik}: {', '.join(s[anahtar]) or '-'}")
    return 0


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="anahtarlik",
        description="Repolardaki gizli anahtarlari (API key/token/parola) tarar; "
                    "HAM DEGERI ASLA GOSTERMEZ, yalniz ad + parmak izi.",
    )
    alt = p.add_subparsers(dest="komut", required=True)

    t = alt.add_parser("tara", help="repolari tara, envanteri kaydet")
    t.add_argument("--root", action="append", default=[], metavar="R",
                   help="taranacak kok (coklu verilebilir; verilmezse atlas DB)")
    t.add_argument("--atlas-db", default=None, metavar="P", help="atlas.db yolu")
    t.add_argument("--json", action="store_true", help="JSON olarak yaz")
    t.set_defaults(isle=_tara)

    g = alt.add_parser("goster", help="son envanteri goster")
    g.add_argument("--json", action="store_true", help="JSON olarak yaz")
    g.set_defaults(isle=_goster)

    n = alt.add_parser("not", help="anahtara rotasyon/iptal notu ekle")
    n.add_argument("ad", help="anahtar adi (orn. GITHUB_TOKEN)")
    n.add_argument("--tarih", required=True, metavar="YYYY-MM-DD", help="rotasyon tarihi")
    n.add_argument("--aciklama", default=None, metavar="S", help="serbest metin not")
    n.set_defaults(isle=_not)

    e = alt.add_parser("eski", help="rotasyon notu olmayan / gunu gecmis anahtarlar")
    e.add_argument("--gun", type=int, default=90, metavar="N",
                   help="eski sayilacak gun (varsayilan: 90)")
    e.add_argument("--json", action="store_true", help="JSON olarak yaz")
    e.set_defaults(isle=_eski)

    hk = alt.add_parser("hook-kur", help="pre-push sizinti hook'unu kur (varsayilan kuru calistirma)")
    hk.add_argument("--repo", default=".", help="git deposu (varsayilan: bulunulan dizin)")
    hk.add_argument("--uygula", action="store_true", help="gercekten yaz")
    hk.add_argument("--ortak", action="store_true",
                    help="core.hooksPath repo disindaysa (tum repolar) yine de kur")
    hk.add_argument("--json", action="store_true", help="JSON olarak yaz")
    hk.set_defaults(isle=_hook_kur)

    ht = alt.add_parser("hook-tara", help="(git pre-push hook'u cagirir) stdin'deki push'u tara")
    ht.set_defaults(isle=_hook_tara)

    f = alt.add_parser("fark", help="yerel .env + workflow secret ADLARI ile GitHub Secrets farki")
    f.add_argument("--repo", default=".", help="git deposu (varsayilan: bulunulan dizin)")
    f.add_argument("--json", action="store_true", help="JSON olarak yaz")
    f.set_defaults(isle=_fark)
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
    except envanter.EnvanterHatasi as exc:
        print(f"Hata: {exc}", file=sys.stderr)
        return KULLANIM_HATASI
    except ValueError as exc:
        print(f"Hata: {exc}", file=sys.stderr)
        return KULLANIM_HATASI
    except OSError as exc:
        # Salt-okunur envanter dizini, kilitli dosya: iz (traceback) degil, cikis 2.
        print(f"Hata: {exc}", file=sys.stderr)
        return KULLANIM_HATASI


if __name__ == "__main__":
    raise SystemExit(main())