"""filo komut satiri: `calistir`.

Cikis kodlari: 0 hepsi ok, 1 biri bile hata/zaman-asimi, 2 kullanim/kesif hatasi.
Guvenlik: alt surec `--dangerously-skip-permissions`/`bypassPermissions` ile
KURULAMAZ (bkz. calistir.argv_olustur); varsayilan araclar salt okunurdur ve
`--kuru` hicbir alt surec baslatmaz.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import rapor as rapor_modul
from .calistir import (
    AZAMI_PARALEL,
    VARSAYILAN_COR,
    VARSAYILAN_MODEL,
    CalistirmaHatasi,
    arac_listesi,
    argv_olustur,
    calistir,
    paralel_denetle,
)
from .kesif import KesifHatasi, repo_listesi

KULLANIM_HATASI = 2
BULGU_KODU = 1
AZAMI_PARALEL_DANIS = 8


def _gorev_metni(yol: Path) -> str:
    """Gorev dosyasini UTF-8 okur; BOS olmamali (bos istem anlamsizdir)."""
    try:
        metin = yol.read_text(encoding="utf-8")
    except OSError as exc:
        raise KesifHatasi(f"gorev dosyasi okunamadi: {yol} ({exc})") from exc
    except UnicodeDecodeError as exc:
        raise KesifHatasi(f"gorev dosyasi UTF-8 degil: {yol} ({exc})") from exc
    if not metin.strip():
        raise KesifHatasi(f"gorev dosyasi bos: {yol}")
    return metin


def _rapor_hedefleri(repolar: list[Path], cikti: Path) -> dict[str, Path]:
    """Her repo icin `<cikti>/<repo_adi>.md`; VAR OLAN DOSYA UZERINE YAZILMAZ.

    Ayni adi iki repo paylasirsa hata verilir (raporlar birbirine karisir).
    """
    hedefler: dict[str, Path] = {}
    isimler: dict[str, str] = {}
    for repo in repolar:
        ad = repo.name
        if ad in isimler:
            raise KesifHatasi(
                f"iki repo ayni ada sahip ({isimler[ad]} ve {repo}); rapor adi "
                f"'{ad}.md' cakisir. Ayri --cikti dizini verin."
            )
        isimler[ad] = str(repo)
        hedefler[str(repo)] = cikti / f"{ad}.md"
    cakisan = [h for h in hedefler.values() if h.exists()]
    if cakisan:
        raise KesifHatasi(
            "cikti dosyalari zaten var, uzerine yazilmadi: "
            + ", ".join(str(h) for h in sorted(cakisan))
            + ". Farkli bir --cikti dizini verin."
        )
    return hedefler


def _kuru_goster(argv: list[str], repolar: list[Path], hedefler: dict[str, Path], cor: str) -> None:
    """KURU CALISTIRMA: hicbir alt surec baslatmadan hangi repoda ne calisacak."""
    print("KURU CALISTIRMA: hicbir alt surec baslatilmadi.", file=sys.stderr)
    for repo in repolar:
        print(f"repo : {repo}")
        print(f"  cwd: {repo}")
        print(f"  rapor: {hedefler[str(repo)]}")
        print("  argv: " + " ".join(argv))


def _calistir(args: argparse.Namespace) -> int:
    gorev = _gorev_metni(Path(args.gorev).expanduser())
    paralel_denetle(args.paralel)  # --kuru da gecersiz degeri sessizce gecmez
    repolar = repo_listesi(
        [Path(r) for r in (args.repo or [])], [Path(k) for k in (args.kok or [])]
    )
    cor = args.cor or VARSAYILAN_COR
    model = args.model or VARSAYILAN_MODEL
    araclar = arac_listesi(args.duzenle)
    cikti = Path(args.cikti).expanduser() if args.cikti else rapor_modul.varsayilan_cikti()
    hedefler = _rapor_hedefleri(repolar, cikti)
    argv = argv_olustur(cor, model, araclar)

    if args.kuru:
        _kuru_goster(argv, repolar, hedefler, cor)
        return 0

    print(f"{len(repolar)} repo, paralellik {args.paralel}, araclar: {araclar}", file=sys.stderr)
    cikti.mkdir(parents=True, exist_ok=True)
    sonuclar = calistir(
        repolar, gorev, hedefler,
        cor=cor, model=model, araclar=araclar,
        paralel=args.paralel, zaman_asimi=args.zaman_asimi,
    )
    veri = rapor_modul.govde(sonuclar, cikti=cikti)
    ozet_yolu = rapor_modul.kaydet(veri, cikti)

    if args.json:
        print(json.dumps({**veri, "ozet_dosyasi": str(ozet_yolu)}, ensure_ascii=False, indent=2))
    else:
        print(rapor_modul.tablo(sonuclar))
        print(f"\nozet: {veri['ozet']}")
        print(f"\ncikti: {cikti}\nozet dosyasi: {ozet_yolu}")
    return BULGU_KODU if veri["ozet"]["hata"] or veri["ozet"]["zaman-asimi"] else 0


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="filo",
        description="Bir gorev metnini N repoya PARALEL dagitir; her repoda yerel "
                    "`cor claude` alt sureci calistirir, raporlari tek klasorde toplar. "
                    "Varsayilan araclar SALT OKUNURdur (Read,Glob,Grep).",
    )
    alt = p.add_subparsers(dest="komut", required=True)

    c = alt.add_parser("calistir", help="gorevi repolara dagit ve calistir")
    c.add_argument("--gorev", required=True, metavar="GOREV.TXT", help="dagitilacak gorev metni dosyasi")
    c.add_argument("--repo", action="append", default=[], metavar="DIZIN",
                   help="calistirilacak repo (coklu verilebilir)")
    c.add_argument("--kok", action="append", default=[], metavar="DIZIN",
                   help="altindaki repolari kesfet (coklu verilebilir; derinlik 1-2)")
    c.add_argument("--paralel", type=int, default=4, metavar="N",
                   help=f"paralel alt surec sayisi (1..{AZAMI_PARALEL}; varsayilan: 4)")
    c.add_argument("--cikti", default=None, metavar="DIZIN",
                   help="rapor dizini (varsayilan: ./filo-ciktilari/<zaman-damgasi>)")
    c.add_argument("--model", default=None, metavar="M",
                   help=f"model (varsayilan: $COR_MODEL ya da {VARSAYILAN_MODEL})")
    c.add_argument("--duzenle", action="store_true",
                   help="yazma/arac calistirma yetkisi ver (Read,Write,Edit,Bash,Glob,Grep); "
                        "verilmezse SALT OKUNUR")
    c.add_argument("--zaman-asimi", type=float, default=900.0, metavar="SN",
                   help="repo basina zaman asimi, saniye (varsayilan: 900)")
    c.add_argument("--cor", default=None, metavar="AD",
                   help=f"cor komutu (varsayilan: {VARSAYILAN_COR})")
    c.add_argument("--kuru", action="store_true",
                   help="hicbir alt surec baslatmadan plani goster")
    c.add_argument("--json", action="store_true", help="JSON olarak yaz")
    c.set_defaults(isle=_calistir)
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
    except CalistirmaHatasi as exc:
        print(f"Hata: {exc}", file=sys.stderr)
        return KULLANIM_HATASI
    except FileExistsError as exc:
        print(f"Hata: {exc}", file=sys.stderr)
        return KULLANIM_HATASI
    except OSError as exc:
        # Kilitli dosya / yazilamayan cikti: iz (traceback) degil, cikis 2.
        print(f"Hata: {exc}", file=sys.stderr)
        return KULLANIM_HATASI
    except ValueError as exc:
        print(f"Hata: {exc}", file=sys.stderr)
        return KULLANIM_HATASI


if __name__ == "__main__":
    raise SystemExit(main())