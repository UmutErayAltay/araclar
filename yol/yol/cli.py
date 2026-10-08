"""`yol` komutu: PATH ve ortam degiskeni denetimi, duzenleme, yedek ve geri alma.

Cikis kodlari: 0 basarili, 1 bulgu var / reddedildi / hata, 2 kullanim hatasi.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Sequence

from . import durum
from .analiz import anahtar, genislet, komut_ara, parcala, store_taklidi
from .degisiklik import (
    CakismaHatasi,
    Degisiklik,
    UygulamaHatasi,
    YetkiHatasi,
    eylem_adi,
    geri_al_plani,
    path_farki,
    uygula_ayrintili,
)
from .kaynak import KULLANICI, Deger, Kaynak, KaynakHatasi, kaynak_sec
from .yedek import YedekHatasi, yedekler

WEB_HATA_MESAJI = "web paneli icin: pip install -e .[web]"
_PYTHON_ADLARI = ("python", "python3", "py")
# Girdi bulgu etiketleri (ASCII; notr olanlar sorunlu sayilmaz)
_BULGU_ETIKETI = {
    "cozumlenemedi": "cozumlenemedi (notr)",
    "kontrol-edilemedi": "kontrol edilemedi (notr)",
}
_YAYIN_NOTU = ("uyari: degisiklik yazildi ama acik programlara duyurulamadi; "
               "yeni acilan terminallerde gecerli olur")


class _Reddedildi(RuntimeError):
    """Islem kurala aykiri (dizin yok, girdi zaten var, bulunamadi)."""


def _yazdir(metin: str = "") -> None:
    print(metin)


def _tablo(basliklar: list[str], satirlar: list[list]) -> None:
    hucreler = [[str(h) for h in basliklar]] + [[str(c) for c in satir] for satir in satirlar]
    genislikler = [max(len(satir[i]) for satir in hucreler) for i in range(len(basliklar))]
    for satir in hucreler:
        _yazdir("  ".join(c.ljust(g) for c, g in zip(satir, genislikler)).rstrip())


def _kaynak(args: argparse.Namespace) -> Kaynak:
    return kaynak_sec(args.kaynak)


def _kullanici_path(kaynak: Kaynak) -> tuple[str | None, Deger | None]:
    if KULLANICI not in kaynak.kapsamlar():
        raise YetkiHatasi("bu kaynakta kullanici kapsami yok (salt okunur)")
    return durum.path_kaydi(kaynak.oku(KULLANICI))


def _fark_yazdir(degisiklikler: list[Degisiklik], ayirici: str) -> None:
    """Degerler gosterilmez; yalniz PATH girdi listeleri ve degisken adlari yazilir."""
    for d in degisiklikler:
        if d.ad.casefold() == "path":
            fark = path_farki(
                d.eski.metin if d.eski is not None else "",
                d.yeni.metin if d.yeni is not None else "",
                ayirici,
            )
            _yazdir(f"{d.kapsam}/{d.ad} (PATH):")
            for girdi in fark["eklenen"]:
                _yazdir(f"  + {girdi}")
            for girdi in fark["cikan"]:
                _yazdir(f"  - {girdi}")
        else:
            etiket = {"ekle": "eklenecek", "degistir": "degisecek", "sil": "silinecek"}[eylem_adi(d)]
            _yazdir(f"{d.kapsam}/{d.ad}: {etiket} (deger gosterilmez)")


def _uygula_ya_da_goster(degisiklikler: list[Degisiklik], kaynak: Kaynak, uygula_mi: bool) -> int:
    _fark_yazdir(degisiklikler, kaynak.ayirici)
    if not uygula_mi:
        _yazdir("kuru calistirma: hicbir sey degismedi (uygulamak icin --uygula)")
        return 0
    sonuc = uygula_ayrintili(kaynak, degisiklikler)
    _yazdir(f"uygulandi. yedek: {sonuc.yedek_id}")
    if not sonuc.yayinlandi:
        print(_YAYIN_NOTU, file=sys.stderr)
    return 0


def _denetle(args: argparse.Namespace) -> int:
    kaynak = _kaynak(args)
    rapor = durum.path_durumu(kaynak)
    if args.json:
        _yazdir(json.dumps(rapor, ensure_ascii=False, indent=2))
    else:
        _tablo(
            ["kapsam", "#", "girdi", "bulgu"],
            [[g["kapsam"], g["sira"] + 1, g["ham"] if g["ham"].strip() else "(bos)",
              ", ".join(_BULGU_ETIKETI.get(b, b) for b in g["bulgular"]) or "-"]
             for g in rapor["girdiler"]],
        )
        _yazdir()
        _tablo(
            ["komut", "kazanan", "golgede", "bulgu"],
            [[k["ad"], k["kazanan"] or "(bulunamadi)", len(k["golgede"]), k["bulgu"] or "-"]
             for k in rapor["komutlar"]],
        )
        _yazdir()
        o = rapor["ozet"]
        kapsam_ozeti = ", ".join(f"{k} {n}" for k, n in o["girdi"].items()) or "yok"
        _yazdir(
            f"ozet: girdi {sum(o['girdi'].values())} ({kapsam_ozeti}), sorunlu {o['sorunlu']}, "
            f"golgelenen komut {o['golgelenen']}, uzun PATH {'evet' if o['uzun'] else 'hayir'}"
        )
    return 1 if rapor["ozet"]["sorunlu"] else 0


def _nerede(args: argparse.Namespace) -> int:
    kaynak = _kaynak(args)
    baglam = durum.yol_baglami(kaynak)
    eksik = False
    for ad in args.komutlar:
        bulunanlar = komut_ara(ad, baglam["dizinler"], kaynak.windows, baglam["pathext"], os.path.isfile)
        if not bulunanlar:
            _yazdir(f"{ad}: bulunamadi")
            eksik = True
            continue
        _yazdir(f"{ad}: {bulunanlar[0]}")
        if ad.casefold() in _PYTHON_ADLARI and store_taklidi(bulunanlar[0]):
            _yazdir("  uyari: Microsoft Store kisayolu gercek Python'u golgeliyor; "
                    "Ayarlar > Uygulama yurutme diger adlari'ndan kapatin")
        for yol in bulunanlar[1:]:
            _yazdir(f"  golgede: {yol}")
    return 1 if eksik else 0


def _temizle(args: argparse.Namespace) -> int:
    kaynak = _kaynak(args)
    rapor = durum.path_durumu(kaynak)
    yeni_metin = rapor["oneri"].get(KULLANICI)
    if yeni_metin is None:
        _yazdir("temizlenecek girdi yok")
        return 0
    ad, eski = _kullanici_path(kaynak)
    if ad is None or eski is None:
        _yazdir("temizlenecek girdi yok")
        return 0
    d = Degisiklik(KULLANICI, ad, eski, Deger(yeni_metin, eski.genisler))
    return _uygula_ya_da_goster([d], kaynak, args.uygula)


def _ekle(args: argparse.Namespace) -> int:
    kaynak = _kaynak(args)
    ortam = durum.ortam_olustur(kaynak)
    windows = kaynak.windows
    cozumlu = genislet(args.dizin, ortam, windows)
    if not os.path.isdir(cozumlu):
        raise _Reddedildi(f"dizin yok: {args.dizin}")
    ad, eski = _kullanici_path(kaynak)
    mevcut = eski.metin if eski is not None else ""
    hedef = anahtar(cozumlu, windows)
    for girdi in parcala(mevcut, kaynak.ayirici):
        if girdi.strip() and anahtar(genislet(girdi, ortam, windows), windows) == hedef:
            raise _Reddedildi(f"girdi zaten var: {args.dizin}")

    yeni_parcalar = parcala(mevcut, kaynak.ayirici)
    yeni_parcalar = [args.dizin] + yeni_parcalar if args.basa else yeni_parcalar + [args.dizin]
    yeni_metin = kaynak.ayirici.join(yeni_parcalar)
    if windows and "%" in yeni_metin:
        genisler = True
    else:
        genisler = eski.genisler if eski is not None else False
    ad_son = ad or ("Path" if windows else "PATH")
    d = Degisiklik(KULLANICI, ad_son, eski, Deger(yeni_metin, genisler))
    return _uygula_ya_da_goster([d], kaynak, args.uygula)


def _kaldir(args: argparse.Namespace) -> int:
    kaynak = _kaynak(args)
    ortam = durum.ortam_olustur(kaynak)
    windows = kaynak.windows
    ad, eski = _kullanici_path(kaynak)
    if ad is None or eski is None:
        raise _Reddedildi("kullanici PATH'i yok")
    hedef = anahtar(genislet(args.dizin, ortam, windows), windows)
    kalan: list[str] = []
    silinen = 0
    for girdi in parcala(eski.metin, kaynak.ayirici):
        if girdi.strip() and anahtar(genislet(girdi, ortam, windows), windows) == hedef:
            silinen += 1
        else:
            kalan.append(girdi)
    if silinen == 0:
        raise _Reddedildi(f"girdi bulunamadi: {args.dizin}")
    d = Degisiklik(KULLANICI, ad, eski, Deger(kaynak.ayirici.join(kalan), eski.genisler))
    return _uygula_ya_da_goster([d], kaynak, args.uygula)


def _yedekler(_args: argparse.Namespace) -> int:
    liste = yedekler()
    if not liste:
        _yazdir("yedek yok")
        return 0
    _tablo(
        ["id", "zaman", "etkilenen kapsam"],
        [[y["id"], y["zaman"], ", ".join(f"{k}:{n}" for k, n in y["kapsamlar"].items())] for y in liste],
    )
    return 0


def _geri_al(args: argparse.Namespace) -> int:
    kaynak = _kaynak(args)
    plan = geri_al_plani(kaynak, args.id)
    if not plan:
        _yazdir("geri alinacak fark yok")
        return 0
    _yazdir(f"geri alma plani (yedek {args.id}):")
    if not args.uygula:
        _fark_yazdir(plan, kaynak.ayirici)
        _yazdir("kuru calistirma: hicbir sey degismedi (uygulamak icin --uygula)")
        return 0
    sonuc = uygula_ayrintili(kaynak, plan)
    _yazdir(f"geri alindi. yeni yedek: {sonuc.yedek_id}")
    if not sonuc.yayinlandi:
        print(_YAYIN_NOTU, file=sys.stderr)
    return 0


def _web(args: argparse.Namespace) -> int:
    try:
        from .web import calistir
    except ImportError:
        print(WEB_HATA_MESAJI, file=sys.stderr)
        return 2
    kaynak = _kaynak(args)
    return int(calistir(kaynak, port=args.port, ac=args.ac))


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="yol", description="PATH ve ortam degiskeni duzenleyici")
    p.add_argument("--kaynak", help="dosya:<yol> | surec | windows (varsayilan: YOL_KAYNAK ya da platform)")
    alt = p.add_subparsers(dest="alt", metavar="KOMUT")

    d = alt.add_parser("denetle", help="PATH bulgulari ve komut tablosu")
    d.add_argument("--json", action="store_true", help="ciktiyi JSON olarak ver")

    n = alt.add_parser("nerede", help="komutun kazananini ve golgedekileri goster")
    n.add_argument("komutlar", nargs="+")

    t = alt.add_parser("temizle", help="kullanici PATH'i icin temizlik onerisi")
    t.add_argument("--uygula", action="store_true")

    e = alt.add_parser("ekle", help="kullanici PATH'ine dizin ekle")
    e.add_argument("dizin")
    e.add_argument("--basa", action="store_true", help="basa ekle")
    e.add_argument("--uygula", action="store_true")

    k = alt.add_parser("kaldir", help="kullanici PATH'inden dizin kaldir")
    k.add_argument("dizin")
    k.add_argument("--uygula", action="store_true")

    alt.add_parser("yedekler", help="yedek listesi")

    g = alt.add_parser("geri-al", help="bir yedege geri don")
    g.add_argument("id")
    g.add_argument("--uygula", action="store_true")

    w = alt.add_parser("web", help="web panelini baslat")
    w.add_argument("--port", type=int, default=8797)
    w.add_argument("--ac", action="store_true", help="tarayiciyi ac")
    return p


_KOMUTLAR: dict[str, Callable[[argparse.Namespace], int]] = {
    "denetle": _denetle,
    "nerede": _nerede,
    "temizle": _temizle,
    "ekle": _ekle,
    "kaldir": _kaldir,
    "yedekler": _yedekler,
    "geri-al": _geri_al,
    "web": _web,
}


def main(argv: Sequence[str] | None = None) -> int:
    for akim in (sys.stdout, sys.stderr):
        if hasattr(akim, "reconfigure"):
            akim.reconfigure(encoding="utf-8")
    parser = _parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        kod = exc.code
        return kod if isinstance(kod, int) else (0 if kod is None else 2)
    if args.alt is None:
        parser.print_help(sys.stderr)
        return 2
    try:
        return _KOMUTLAR[args.alt](args)
    except (KaynakHatasi, CakismaHatasi, YetkiHatasi, YedekHatasi, UygulamaHatasi, _Reddedildi) as exc:
        print(f"yol: {exc}", file=sys.stderr)
        return 1
