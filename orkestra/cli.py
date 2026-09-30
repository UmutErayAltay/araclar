"""orkestra komut satırı arayüzü (Dalga A kuyruk, Dalga B gerçek çalıştırıcı)."""

from __future__ import annotations

import argparse
import os
import signal
import sys
from pathlib import Path

from . import __version__, guard, quota
from .models import Durum, OrkestraHata
from .queue import Queue
from .runner import ClaudeRunner

DURUM_LISTESI = [d.value for d in Durum]

ACIKLAMA = (
    "Ajan Orkestrasi — gorev kuyrugu. Dalga A: kuyruk + CLI. "
    "Dalga B: headless claude calistirici. Dalga C: web paneli + kota."
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
    "web": "Salt-okunur web panelini 127.0.0.1 uzerinde baslatir",
    "kota": "Model basina gunluk kota durumunu gosterir",
    "kota-guncelle": "cor proxy.log dosyasini okuyup kotayi gunceller",
}

RAPOR_SON_SATIR = 40
VARSAYILAN_LIMIT = 1000
VARSAYILAN_PORT = 8780

DEFAULT_KOTA_TOML_ACIKLAMA = (
    "Limit dosyasi (varsayilan ~/.orkestra/kota.toml)"
)
DEFAULT_COR_LOG_ACIKLAMA = (
    "cor proxy.log yolu (varsayilan COR_LOG veya /root/.claude-openrouter/proxy.log)"
)


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

    p_web = alt.add_parser("web", help=ALT_KOMUT_ACIKLAMA["web"])
    p_web.add_argument("--port", type=int, default=VARSAYILAN_PORT, metavar="N",
                       help=f"Port (varsayilan {VARSAYILAN_PORT})")
    p_web.add_argument("--cikti-dizini", default=None, metavar="DIR",
                       help="Log dizini siniri (varsayilan ~/.orkestra/runs)")
    p_web.add_argument("--cor-log", default=None, metavar="YOL",
                       help=DEFAULT_COR_LOG_ACIKLAMA + " (COR_LOG olarak aktarilir)")
    p_web.add_argument("--kota-toml", default=None, metavar="YOL",
                       help="Limit dosyasi (varsayilan ~/.orkestra/kota.toml)")
    p_web.add_argument("--db", dest="alt_db", default=None, metavar="YOL", help=DB_YARDIM)

    p_kota = alt.add_parser("kota", help=ALT_KOMUT_ACIKLAMA["kota"])
    p_kota.add_argument("--json", action="store_true", help="JSON olarak bas")
    p_kota.add_argument("--kota-toml", default=None, metavar="YOL", help=DEFAULT_KOTA_TOML_ACIKLAMA)
    p_kota.add_argument("--db", dest="alt_db", default=None, metavar="YOL", help=DB_YARDIM)

    p_kota_guncelle = alt.add_parser(
        "kota-guncelle", help=ALT_KOMUT_ACIKLAMA["kota-guncelle"]
    )
    p_kota_guncelle.add_argument("--cor-log", default=None, metavar="YOL",
                                 help=DEFAULT_COR_LOG_ACIKLAMA)
    p_kota_guncelle.add_argument("--kota-toml", default=None, metavar="YOL", help=DEFAULT_KOTA_TOML_ACIKLAMA)
    p_kota_guncelle.add_argument("--db", dest="alt_db", default=None, metavar="YOL", help=DB_YARDIM)
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


# -- Dalga C: web + kota ---------------------------------------------------


def _web(args) -> int:  # pragma: no cover — gerçek sunucu e2e'de çalıştırılır
    """Paneli BAŞLATIR. Adres kodda sabittir (127.0.0.1); `--host` yoktur."""
    from .web import calistir

    print(f"Panel: http://127.0.0.1:{args.port}  (yalnizca yerel, salt okunur)")
    if args.cor_log:
        # Panel kota verisini DB'den okur; log yalnız `kota-guncelle` girdisidir.
        # Bayrak verilmişse ortam değişkenine yazılır, böylece panelde görünen
        # kota aynı kaynaktan türetilir (sessizce yok sayılmaz).
        os.environ["COR_LOG"] = args.cor_log
    calistir(
        args.db or varsayilan_db_yolu(),
        port=args.port,
        cikti_dizini=args.cikti_dizini,
        kota_toml=args.kota_toml,
    )
    return 0


def _kota_guncelle(kuyruk: Queue, args) -> int:
    """`proxy.log`'u artımlı okur ve `quota_snapshots`'a yazar."""
    sonuc = quota.guncelle(kuyruk.baglanti_al(), args.cor_log)
    if sonuc.yeni_satir == 0 and sonuc.taninmayan == 0:
        print(f"Kota guncellendi: yeni istek yok ({sonuc.kaynak}).")
    else:
        print(
            f"Kota guncellendi: {sonuc.yeni_satir} yeni istek, "
            f"{sonuc.taninmayan} taninmayan satir ({sonuc.kaynak})."
        )
    for gun_anahtari in sorted(sonuc.gunler):
        sayac = sonuc.gunler[gun_anahtari]
        print(f"  {gun_anahtari}: {sayac.istek} istek")
    return 0


def _kota(kuyruk: Queue, args) -> int:
    limitler = quota.limitleri_yukle(args.kota_toml)
    gorunum = quota.kota_gorunumu(kuyruk.baglanti_al(), limitler)
    if args.json:
        import json as _json

        veri = {
            "gun": gorunum.gun,
            "limit_kaynagi": gorunum.limit_kaynagi,
            "toplam_istek": gorunum.toplam_istek,
            "uyari_sayisi": gorunum.uyari_sayisi,
            "modeller": [
                {
                    "model": m.model,
                    "istek": m.istek,
                    "limit": m.limit,
                    "durum": m.durum,
                    "yuzde": m.yuzde,
                }
                for m in gorunum.modeller
            ],
        }
        print(_json.dumps(veri, ensure_ascii=False, indent=2))
        return 0
    if not gorunum.veri_var:
        print("Kota verisi yok. Once 'orkestra kota-guncelle' calistirin.")
        return 0
    if not gorunum.modeller:
        print("Kota verisi yok.")
        return 0
    print(f"Kota ({gorunum.gun} UTC, limit kaynagi: {gorunum.limit_kaynagi})")
    for m in gorunum.modeller:
        limit = "-" if m.limit is None else str(m.limit)
        yuzde_m = "-" if m.yuzde is None else f"{m.yuzde:.0f}%"
        print(
            f"  {m.model:<40}  {m.istek:>4} istek  limit={limit:<5} "
            f"{yuzde_m:>5}  {m.durum_etiket}"
        )
    print(f"Toplam {gorunum.toplam_istek} istek; {gorunum.uyari_sayisi} model uyarida.")
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

    if args.komut == "web":
        # Panel kendi SALT-OKUNUR baglantisini acar; yazma yapan Queue
        # BAGLAMI burada acilmaz (baglanti hic kurulmaz).
        try:
            return _web(args)
        except OrkestraHata as hata:
            print(f"Hata: {hata}", file=sys.stderr)
            return 1

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
            if args.komut == "kota":
                return _kota(kuyruk, args)
            if args.komut == "kota-guncelle":
                return _kota_guncelle(kuyruk, args)
    except OrkestraHata as hata:
        print(f"Hata: {hata}", file=sys.stderr)
        return 1
    ayrac.error(f"bilinmeyen komut: {args.komut}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())