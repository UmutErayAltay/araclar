"""baglam-rontgeni komut satiri: tara / goster / kapat / ac.

Cikis kodlari: 0 basari, 2 AyarHatasi / gecersiz hedef / rapor yok.
Guvenlik: kapat/ac varsayilan olarak kuru calistirmadir; ayrinti icin bkz. ayar.py.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import kesif, rapor
from .ayar import AyarHatasi, claude_dizin, degisiklik_plani, oku, temiz, uygulanan_ayar, yaz

KULLANIM_HATASI = 2

KURU_CALISTIRMA_NOTU = "kuru calistirma: hicbir sey yazilmadi"


def _skill_uyarisi(hedef: str, ayar: dict) -> str:
    """`kapat X` icin X bilinen bir skill mi? Degilse uyari satiri (reddetMEZ).

    Bilinen: kesfedilen skill adlari (rapor kalemleri) ya da mevcut
    skillOverrides anahtarlari (kapali skill'ler kesifte gorunmez).
    """
    if ":" not in hedef or "@" in hedef:
        return ""  # duz ad (kullanici skill'i) ya da plugin: hepsi olabilir
    bilinen = {k.get("ad") for k in kesif.skill_kalemleri(ayar, claude_dizin())}
    bilinen |= set(ayar.get("skillOverrides") or {})
    return "" if hedef in bilinen else f"uyari: {temiz(hedef)} bilinen skill degil"


def _yazdir(args: argparse.Namespace, veri: dict) -> None:
    if args.json:
        print(json.dumps(veri, ensure_ascii=False, indent=2))
    else:
        print(rapor.tablo(veri, args.ilk))


def _tara(args: argparse.Namespace) -> int:
    ayar = oku()
    proje = Path(args.proje).expanduser() if args.proje else None
    veri = rapor.olustur(kesif.kalemler(ayar, proje=proje))
    yol = rapor.kaydet(veri)
    if args.json:
        print(json.dumps({**veri, "rapor": str(yol)}, ensure_ascii=False, indent=2))
    else:
        print(rapor.tablo(veri, rapor.VARSAYILAN_ILK))
        print(f"\nrapor: {temiz(yol)}")
    return 0


def _goster(args: argparse.Namespace) -> int:
    veri = rapor.yukle()
    if not veri:
        print(
            "Hata: rapor bulunamadi. Once `rontgen tara` calistirin "
            f"(beklenen: {rapor._yol()}).",
            file=sys.stderr,
        )
        return KULLANIM_HATASI
    if args.json:
        print(json.dumps(veri, ensure_ascii=False, indent=2))
    else:
        print(f"tarih: {veri.get('tarih')}")
        print(rapor.tablo(veri, args.ilk))
    return 0


def _degistir(args: argparse.Namespace, acik: bool) -> int:
    ayar = oku()
    plan = degisiklik_plani(ayar, args.hedef, acik)
    uyari = _skill_uyarisi(args.hedef, ayar)
    if not plan:
        durum = "zaten acik" if acik else "zaten kapali"
        print(f"{temiz(args.hedef)}: {durum}, degisiklik yok")
        if uyari:
            print(uyari)
        return 0

    print(f"hedef: {temiz(args.hedef)}")
    if uyari:
        print(uyari)
    for satir in plan:
        print(f"  {satir}")

    if not args.uygula:
        print(KURU_CALISTIRMA_NOTU + "; uygulamak icin --uygula ekleyin")
        return 0

    # bekle=ayar: yazma aninda ayar arada degistiyse USTUNE YAZILMAZ.
    yol = yaz(
        claude_dizin() / "settings.json",
        uygulanan_ayar(ayar, args.hedef, acik),
        True,
        bekle=ayar,
    )
    print(f"uygulandi: {temiz(yol)} (yedek: {yol.name}.rontgen-bak-*)")
    return 0


def _kapat(args: argparse.Namespace) -> int:
    return _degistir(args, acik=False)


def _ac(args: argparse.Namespace) -> int:
    return _degistir(args, acik=True)


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="rontgen",
        description="Claude Code baglamini (skill/CLAUDE.md/MCP) tarayip acilis "
                    "token maliyetini cikartir (varsayilan: kuru calistirma)",
    )
    alt = p.add_subparsers(dest="komut", required=True)

    t = alt.add_parser("tara", help="baglami tara, raporu kaydet")
    t.add_argument("--proje", default=None, metavar="YOL",
                   help="proje dizini (CLAUDE.md/CLAUDE.local.md/.mcp.json icin)")
    t.add_argument("--json", action="store_true", help="JSON olarak yaz")
    t.set_defaults(isle=_tara)

    g = alt.add_parser("goster", help="son raporu goster")
    g.add_argument("--json", action="store_true", help="JSON olarak yaz")
    g.add_argument("--ilk", type=int, default=rapor.VARSAYILAN_ILK,
                   metavar="N", help=f"kac satir gosterilir (varsayilan: {rapor.VARSAYILAN_ILK})")
    g.set_defaults(isle=_goster)

    for ad, islev, yardim in (
        ("kapat", _kapat, "skill veya plugin'i kapat"),
        ("ac", _ac, "skill veya plugin'i ac"),
    ):
        a = alt.add_parser(ad, help=yardim)
        a.add_argument("hedef", help="`plugin:skill` (skill) veya `ad@pazar` (plugin)")
        a.add_argument("--uygula", action="store_true",
                       help="gercekten settings.json'u yaz (yoksa yalniz diff)")
        a.set_defaults(isle=islev)
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
    except AyarHatasi as exc:
        print(f"Hata: {exc}", file=sys.stderr)
        return KULLANIM_HATASI
    except kesif.KesifHatasi as exc:
        print(f"Hata: {exc}", file=sys.stderr)
        return KULLANIM_HATASI
    except ValueError as exc:
        print(f"Hata: {exc}", file=sys.stderr)
        return KULLANIM_HATASI
    except OSError as exc:
        # Salt-okunur ayar/rapor dizini, kilitli dosya: iz degil, cikis 2.
        print(f"Hata: {exc}", file=sys.stderr)
        return KULLANIM_HATASI


if __name__ == "__main__":
    raise SystemExit(main())