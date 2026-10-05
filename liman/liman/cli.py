"""liman komut satiri: tablo / --json / bos / kim / izle / web.

Çıkış kodları: 0 başarı, 1 "bulunamadı" (boş port / port boşta), 2 kullanım hatası.
Hatalar `Hata: ...` ile stderr'a yazılır; traceback ASLA basilmaz.
"""

from __future__ import annotations

import argparse
import json
import sys
import time

from . import __version__, bos as bos_modulu, tarama

#: Sutunlari hizalar; en kisa baslik genisligi.
_MIN_GENISLIK = 4

#: `liman web --port` varsayilani. Adres kodda sabittir (127.0.0.1).
VARSAYILAN_WEB_PORT = 8795

#: `liman izle` varsayilan araligi (saniye).
VARSAYILAN_IZLEME_SN = 2

#: ANSI: ekrani temizle + imleci basa al.
ANSI_TEMIZLE = "\033[2J\033[H"

#: Disa acik satirlarin tablo basindaki isareti (renkten bagimsiz ayirt etme).
DISA_ACIK_ISARETI = "!"

#: Bos hucre yerine gosterilen isaret.
BOS_ISARET = "-"


def _genislik(metin: str) -> int:
    """Gorunur genislik (birlesik karakter varsa 0)."""
    import unicodedata

    return sum(0 if unicodedata.combining(c) else 1 for c in metin)


def _siga(sutun: list[str], genislikler: list[int]) -> str:
    parcalar = [_siga_bir(sutun[i] if i < len(sutun) else "", genislikler[i]) for i in range(len(genislikler))]
    return "  ".join(parcalar).rstrip()


def _siga_bir(metin: str, genislik: int) -> str:
    """Tek hucreyi hizalar; tasarsa "…" ile keser."""
    if _genislik(metin) <= genislik:
        return metin + " " * (genislik - _genislik(metin))
    kes = metin[: genislik - 1] + "…"
    return kes + " " * (genislik - _genislik(kes))


def tablo_ciz(satirlar: list[dict]) -> str:
    """Dolu port tablosu (hizali, sabit genislikli)."""
    basliklar = ["PORT", "PROTO", "KAPSAM", "SÜREÇ", "PID", "BAĞLI", "ETİKET"]
    govde: list[list[str]] = []
    for s in satirlar:
        kapsam_metin = "dışa açık" if s["kapsam"] == "disa_acik" else "yerel"
        govde.append(
            [
                f"{DISA_ACIK_ISARETI} {s['port']}" if s["kapsam"] == "disa_acik" else str(s["port"]),
                s["proto"],
                kapsam_metin,
                s["surec"] or BOS_ISARET,
                str(s["pid"]) if s["pid"] is not None else BOS_ISARET,
                str(s["bagli"]),
                s["etiket"] or BOS_ISARET,
            ]
        )

    genislikler = [max(_MIN_GENISLIK, _genislik(h)) for h in basliklar]
    for satir in govde:
        for i in range(len(genislikler)):
            genislikler[i] = max(genislikler[i], _genislik(satir[i]))

    ayrac = "  ".join("-" * g for g in genislikler)
    return "\n".join([_siga(basliklar, genislikler), ayrac, *(_siga(s, genislikler) for s in govde)])


def _ozet_satiri(satirlar: list[dict]) -> str:
    ozet = tarama.ozet(satirlar)
    return f"{ozet['toplam']} dinleyen, {ozet['disa_acik']} dışa açık"


def _tablo_yaz(satirlar: list[dict]) -> None:
    """Dolu port tablosunu ve ozet satirini (veya bos durum metnini) yazar."""
    if not satirlar:
        print("Dinleyen port yok.")
        return
    print(tablo_ciz(satirlar))
    print(f"\n{_ozet_satiri(satirlar)}")


def _port_coz(metin: str) -> int:
    """Port argumanini cozer; gecersizse Turkce `ValueError`."""
    try:
        port = int(metin)
    except ValueError:
        raise ValueError(f"geçersiz port: {metin} (sayı olmalı)") from None
    if not 1 <= port <= 65535:
        raise ValueError(f"geçersiz port: {metin} (1-65535 aralığında olmalı)")
    return port


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="liman",
        description="Liman: dolu ve boştaki portları gösteren salt-okunur araç.",
    )
    parser.add_argument("--version", action="version", version=f"liman {__version__}")
    parser.add_argument("--json", action="store_true", help="makine tarafının okunabilir çıktı")
    sub = parser.add_subparsers(dest="komut", metavar="KOMUT")

    bos_parser = sub.add_parser("bos", help="boş portları bul")
    bos_parser.add_argument("--aralik", default="8000-8999", metavar="A-B", help="port aralığı (varsayılan: 8000-8999)")
    bos_parser.add_argument("--adet", type=int, default=bos_modulu.VARSAYILAN_ADET, metavar="N", help="kaç boş port isteniyor (varsayılan: %d)" % bos_modulu.VARSAYILAN_ADET)

    kim_parser = sub.add_parser("kim", help="bir portu kullananı göster")
    kim_parser.add_argument("port", metavar="PORT", help="port numarası (1-65535)")

    izle_parser = sub.add_parser("izle", help="tabloyu periyodik olarak tazele")
    izle_parser.add_argument("--aralik-sn", type=float, default=VARSAYILAN_IZLEME_SN, metavar="N", help="tazeleme aralığı, saniye (en az 1; varsayılan: %d)" % VARSAYILAN_IZLEME_SN)

    web_parser = sub.add_parser("web", help="salt-okunur web panelini başlat (yalnızca 127.0.0.1)")
    web_parser.add_argument("--port", type=int, default=VARSAYILAN_WEB_PORT, metavar="N", help="port (varsayılan: %d)" % VARSAYILAN_WEB_PORT)
    return parser


def _cmd_bos(args: argparse.Namespace) -> int:
    aralik = bos_modulu.aralik_coz(args.aralik)
    if args.adet < 1:
        raise ValueError(f"geçersiz adet: {args.adet} (en az 1 olmalı)")
    portlar = bos_modulu.bos_portlar(aralik=aralik, adet=args.adet)
    if not portlar:
        print("Boş port bulunamadı.")
        return 1
    for port in portlar:
        print(port)
    return 0


def _cmd_kim(args: argparse.Namespace) -> int:
    port = _port_coz(args.port)
    satirlar = [s for s in tarama.dinleyenler() if s["port"] == port]
    if not satirlar:
        print(f"Port {port} boşta.")
        return 1
    print(tablo_ciz(satirlar))
    return 0


def _cmd_izle(args: argparse.Namespace) -> int:
    """Ekrani temizleyip tabloyu tazeler. Ctrl+C temiz cikar (traceback yok)."""
    if args.aralik_sn < 1:
        raise ValueError(f"geçersiz aralık: {args.aralik_sn} (en az 1 saniye)")
    try:
        while True:
            satirlar = tarama.dinleyenler()
            print(ANSI_TEMIZLE, end="")
            _tablo_yaz(satirlar)
            sys.stdout.flush()
            time.sleep(args.aralik_sn)
    except KeyboardInterrupt:
        # Ekranda yarim tablo kalmasin; son satiri once yaz.
        print("\nİzleme durduruldu.")
        return 0


def _cmd_web(args: argparse.Namespace) -> int:  # pragma: no cover — gerçek süreç
    from .web import sunucu

    port = _port_coz(str(args.port))
    print(f"Panel: http://127.0.0.1:{port}/  (salt-okunur; yalnızca 127.0.0.1)")
    sunucu.calistir(port)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.komut is None:
            if args.json:
                satirlar = tarama.dinleyenler()
                print(json.dumps({"dinleyenler": satirlar, "ozet": tarama.ozet(satirlar)}, ensure_ascii=False, indent=2))
            else:
                _tablo_yaz(tarama.dinleyenler())
            return 0
        if args.komut == "bos":
            return _cmd_bos(args)
        if args.komut == "kim":
            return _cmd_kim(args)
        if args.komut == "izle":
            return _cmd_izle(args)
        if args.komut == "web":
            return _cmd_web(args)
    except ValueError as exc:
        print(f"Hata: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:  # pragma: no cover
        print("İptal edildi.", file=sys.stderr)
        return 130
    except OSError as exc:
        print(f"Hata: {exc}", file=sys.stderr)
        return 2
    parser.error("bilinmeyen komut")  # pragma: no cover
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
