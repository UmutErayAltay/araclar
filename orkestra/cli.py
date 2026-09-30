"""orkestra komut satırı arayüzü (Dalga A kuyruk, Dalga B gerçek çalıştırıcı)."""

from __future__ import annotations

import argparse
import signal
import sys
from pathlib import Path

from . import __version__, guard
from .models import Durum, OrkestraHata
from .queue import Queue
from .runner import ClaudeRunner

DURUM_LISTESI = [d.value for d in Durum]

ACIKLAMA = (
    "Ajan Orkestrasi — gorev kuyrugu. Dalga A: kuyruk + CLI. "
    "Dalga B: headless claude calistirici."
)

ALT_KOMUT_ACIKLAMA = {
    "ver": "Kuyruga yeni gorev ekler",
    "liste": "Gorevleri listeler",
    "iptal": "Gorevi iptal eder",
    "tekrar": "Hatali gorevi yeniden denemeye alir",
    "calistir-bir": "Siradaki bekleyen gorevi calistirir",
    "calistir": "Bekleyen gorevleri sirayla calistirir",
    "kurtar": "Yarim kalan calisiyor gorevleri kurtarir",
    "rapor": "Gorevin son kosusunu raporlar",
}

RAPOR_SON_SATIR = 40
VARSAYILAN_LIMIT = 1000


def _utf8_konfigure() -> None:
    """Windows cp1252 konsolunda Turkce karakter cokmesini onler."""
    for akis in (sys.stdout, sys.stderr):
        yeniden = getattr(akis, "reconfigure", None)
        if yeniden is not None:
            try:
                yeniden(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


DB_YARDIM = (
    "Veritabani dosyasi (varsayilan: ORKESTRA_DB veya ~/.orkestra/orkestra.db)"
)


def _calistir_bayraklari(ayrac: argparse.ArgumentParser) -> None:
    ayrac.add_argument("--model", default=None, metavar="M", help="claude modeli")
    ayrac.add_argument("--cwd", default=None, metavar="DIR", help="Calistirma calisma dizini")
    ayrac.add_argument(
        "--zaman-asimi", type=int, default=1800, metavar="SN",
        help="Saniye cinsinden zaman asimi (varsayilan 1800)",
    )
    ayrac.add_argument(
        "--cikti-dizini", default=None, metavar="DIR",
        help="Log dosyalarinin yazilacagi dizin (varsayilan ~/.orkestra/runs)",
    )


def _kur() -> argparse.ArgumentParser:
    ayrac = argparse.ArgumentParser(prog="orkestra", description=ACIKLAMA)
    ayrac.add_argument("--surum", action="version", version=f"orkestra {__version__}")
    ayrac.add_argument("--db", default=None, metavar="YOL", help=DB_YARDIM)
    alt = ayrac.add_subparsers(dest="komut", required=True, metavar="KOMUT")

    p_ver = alt.add_parser("ver", help=ALT_KOMUT_ACIKLAMA["ver"])
    p_ver.add_argument("--ajan", required=True, metavar="AD", help="Ajan adi, orn. bunny-coder")
    p_ver.add_argument("istem", metavar="ISTEM", help="Gorev metni")
    p_ver.add_argument("--db", dest="alt_db", default=None, metavar="YOL", help=DB_YARDIM)

    p_liste = alt.add_parser("liste", help=ALT_KOMUT_ACIKLAMA["liste"])
    p_liste.add_argument("--durum", choices=DURUM_LISTESI, default=None, help="Duruma gore filtre")
    p_liste.add_argument("--db", dest="alt_db", default=None, metavar="YOL", help=DB_YARDIM)

    p_iptal = alt.add_parser("iptal", help=ALT_KOMUT_ACIKLAMA["iptal"])
    p_iptal.add_argument("id", type=int, metavar="ID")
    p_iptal.add_argument("--db", dest="alt_db", default=None, metavar="YOL", help=DB_YARDIM)

    p_tekrar = alt.add_parser("tekrar", help=ALT_KOMUT_ACIKLAMA["tekrar"])
    p_tekrar.add_argument("id", type=int, metavar="ID")
    p_tekrar.add_argument("--db", dest="alt_db", default=None, metavar="YOL", help=DB_YARDIM)

    p_calistir_bir = alt.add_parser(
        "calistir-bir", help=ALT_KOMUT_ACIKLAMA["calistir-bir"]
    )
    _calistir_bayraklari(p_calistir_bir)
    p_calistir_bir.add_argument("--db", dest="alt_db", default=None, metavar="YOL", help=DB_YARDIM)

    p_calistir = alt.add_parser("calistir", help=ALT_KOMUT_ACIKLAMA["calistir"])
    _calistir_bayraklari(p_calistir)
    p_calistir.add_argument(
        "--limit", type=int, default=VARSAYILAN_LIMIT, metavar="N",
        help=f"En fazla calistirilacak gorev (varsayilan {VARSAYILAN_LIMIT})",
    )
    p_calistir.add_argument("--db", dest="alt_db", default=None, metavar="YOL", help=DB_YARDIM)

    p_kurtar = alt.add_parser("kurtar", help=ALT_KOMUT_ACIKLAMA["kurtar"])
    p_kurtar.add_argument("--db", dest="alt_db", default=None, metavar="YOL", help=DB_YARDIM)

    p_rapor = alt.add_parser("rapor", help=ALT_KOMUT_ACIKLAMA["rapor"])
    p_rapor.add_argument("id", type=int, metavar="ID")
    p_rapor.add_argument("--db", dest="alt_db", default=None, metavar="YOL", help=DB_YARDIM)
    return ayrac


def _ver(kuyruk: Queue, args) -> int:
    gorev = kuyruk.ekle(args.ajan, args.istem)
    print(f"Gorev #{gorev.id} eklendi: ajan={gorev.ajan} durum={gorev.durum.value}")
    return 0


def _liste(kuyruk: Queue, args) -> int:
    gorevler = kuyruk.liste(args.durum)
    if not gorevler:
        print("Kuyruk bos.")
        return 0
    print(f"{'ID':>4}  {'DURUM':<14}  {'AJAN':<16}  {'OLUSTURMA':<20}  ISTEM")
    for gorev in gorevler:
        print(
            f"{gorev.id:>4}  {gorev.durum.value:<14}  {gorev.ajan:<16}  "
            f"{gorev.olusturma:<20}  {gorev.onizleme}"
        )
    print(f"Toplam {len(gorevler)} gorev.")
    return 0


def _iptal(kuyruk: Queue, args) -> int:
    onceki = kuyruk.al(args.id).durum.value
    gorev = kuyruk.iptal(args.id)
    print(f"Gorev #{gorev.id} iptal edildi (onceki durum: {onceki}).")
    return 0


def _tekrar(kuyruk: Queue, args) -> int:
    gorev = kuyruk.tekrar(args.id)
    print(f"Gorev #{gorev.id} yeniden denemeye alindi: durum={gorev.durum.value}")
    return 0


def _runner(args) -> ClaudeRunner:
    return ClaudeRunner(
        model=args.model,
        cwd=args.cwd,
        zaman_asimi=args.zaman_asimi,
        cikti_dizini=getattr(args, "cikti_dizini", None),
    )


def _sonuc_yaz(gorev, kosu) -> None:
    """Sonucu özetler; log YOLUNU basar, log METNINI ekrana dökmez."""
    print(f"Gorev #{gorev.id} -> {gorev.durum.value}")
    print(f"  run id    : {kosu.id}")
    print(f"  cikis kodu: {kosu.cikis_kodu}")
    if kosu.hata:
        print(f"  hata      : {guard.maskele(kosu.hata)}")
    if kosu.cikti_yolu:
        print(f"  log       : {kosu.cikti_yolu}")


def _calistir_bir(kuyruk: Queue, args) -> int:
    sonuc = kuyruk.calistir_bir(_runner(args))
    if sonuc is None:
        print("bekleyen gorev yok")
        return 0
    gorev, kosu = sonuc
    _sonuc_yaz(gorev, kosu)
    return 0


def _calistir(kuyruk: Queue, args) -> int:
    """Bekleyen görevleri sırayla çalıştırır; Ctrl-C düzgün durur."""
    limit = args.limit if args.limit is not None else VARSAYILAN_LIMIT
    if limit <= 0:
        print("Hata: --limit pozitif olmali.", file=sys.stderr)
        return 2
    calisan = _runner(args)
    durduruldu = False

    def _durustur(_kod, _cerceve):
        nonlocal durduruldu
        durduruldu = True
        print("\nDurduruluyor... (calisan gorev kurtarilabilir)", file=sys.stderr)

    eski = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGINT, _durustur)
    sayi = 0
    try:
        while sayi < limit and not durduruldu:
            sonuc = kuyruk.calistir_bir(calisan)
            if sonuc is None:
                break
            gorev, kosu = sonuc
            sayi += 1
            _sonuc_yaz(gorev, kosu)
    finally:
        signal.signal(signal.SIGINT, eski)
    if sayi == 0:
        print("bekleyen gorev yok")
    else:
        print(f"Toplam {sayi} gorev calistirildi.")
    if durduruldu:
        # Çalışan görev `calisiyor` kalır; `orkestra kurtar` ile düzeltilir.
        print("Yarim kalan gorevler icin 'orkestra kurtar' calistirin.", file=sys.stderr)
        return 130
    return 0


def _kurtar(kuyruk: Queue, args) -> int:
    kurtarilan = kuyruk.kurtar()
    if not kurtarilan:
        print("Kurtarilacak yarim kalan gorev yok.")
        return 0
    for gorev in kurtarilan:
        print(f"Gorev #{gorev.id} kurtarildi: {gorev.durum.value}")
    print(f"Toplam {len(kurtarilan)} gorev kurtarildi.")
    return 0


def _sure_metni(kosu) -> str:
    if not kosu.baslangic or not kosu.bitis:
        return "bilinmiyor"
    try:
        from datetime import datetime

        bas = datetime.fromisoformat(kosu.baslangic.replace("Z", "+00:00"))
        bit = datetime.fromisoformat(kosu.bitis.replace("Z", "+00:00"))
        return f"{(bit - bas).total_seconds():.1f} sn"
    except (TypeError, ValueError):
        return "bilinmiyor"


def _rapor(kuyruk: Queue, args) -> int:
    gorev = kuyruk.al(args.id)
    kosular = kuyruk.kosular(gorev.id)
    print(f"Gorev #{gorev.id}  ajan={gorev.ajan}  durum={gorev.durum.value}")
    if not kosular:
        print("Bu gorev hic calistirilmamis.")
        return 0
    kosu = kosular[-1]
    print(f"  run id    : {kosu.id}")
    print(f"  baslangic : {kosu.baslangic}")
    print(f"  bitis     : {kosu.bitis}")
    print(f"  sure      : {_sure_metni(kosu)}")
    print(f"  cikis kodu: {kosu.cikis_kodu}")
    if kosu.hata:
        print(f"  hata      : {guard.maskele(kosu.hata)}")
    log = kosu.cikti_yolu
    if not log:
        print("  log       : (yok)")
        return 0
    print(f"  log       : {log}")
    print(f"--- log son {RAPOR_SON_SATIR} satiri ---")
    try:
        metin = Path(log).read_text(encoding="utf-8", errors="replace")
    except OSError as hata:
        print(f"  (log okunamadi: {type(hata).__name__})")
        return 0
    satirlar = metin.splitlines()
    for satir in satirlar[-RAPOR_SON_SATIR:]:
        print(guard.maskele(satir))
    if len(satirlar) > RAPOR_SON_SATIR:
        print(f"--- ({len(satirlar) - RAPOR_SON_SATIR} satir onceki kisaltildi) ---")
    return 0


def main(argv: list[str] | None = None) -> int:
    _utf8_konfigure()
    ayrac = _kur()
    args = ayrac.parse_args(argv)
    # `--db` komuttan önce veya sonra verilebilir; alt komut bayrağı üstü ezer.
    if getattr(args, "alt_db", None) is not None:
        args.db = args.alt_db

    try:
        with Queue(args.db) as kuyruk:
            if args.komut == "ver":
                return _ver(kuyruk, args)
            if args.komut == "liste":
                return _liste(kuyruk, args)
            if args.komut == "iptal":
                return _iptal(kuyruk, args)
            if args.komut == "tekrar":
                return _tekrar(kuyruk, args)
            if args.komut == "calistir-bir":
                return _calistir_bir(kuyruk, args)
            if args.komut == "calistir":
                return _calistir(kuyruk, args)
            if args.komut == "kurtar":
                return _kurtar(kuyruk, args)
            if args.komut == "rapor":
                return _rapor(kuyruk, args)
    except OrkestraHata as hata:
        print(f"Hata: {hata}", file=sys.stderr)
        return 1
    ayrac.error(f"bilinmeyen komut: {args.komut}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())