"""orkestra komut satırı arayüzü (Dalga A kuyruk, Dalga B gerçek çalıştırıcı)."""

from __future__ import annotations

import argparse
import os
import signal
import sys
from pathlib import Path

from . import __version__, guard, planner, quota, report
from . import durum as durum_mod
from .models import Durum, OrkestraHata
from .queue import Queue, varsayilan_db_yolu
from .runner import ClaudeRunner

DURUM_LISTESI = [d.value for d in Durum]

ACIKLAMA = (
    "Ajan Orkestrasi — gorev kuyrugu. Dalga A: kuyruk + CLI. "
    "Dalga B: headless claude calistirici. Dalga C: web paneli + kota. "
    "Dalga D: kanit degerlendirme + planlayici."
)

# Kanıt uyarısı taşıyan sonuçlar: `liste`/web'de görünür, `calistir*` stderr'e yazar.
KANIT_UYARI_DURUMLARI = (report.KANITSIZ, report.BASARISIZ, report.REDDEDILDI)
KATI_CIKIS_KODU = 4

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
    "dogrula": "Ajan raporunu gozlemlenen kanitlara karsi dogrular",
    "planla": "Hedefi cor uzerinden is dalgalarina boler",
    "plan-goster": "Kayitli plani gosterir",
    "plan-kuyruga": "Secilen planin tek dalgasini kuyruga ekler (CALISTIRMAZ)",
    "durum": "Kule entegrasyonu icin durum ozeti (--json)",
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
    p_ver.add_argument("--rapor-dosyasi", default=None, metavar="YOL",
                       help="Ajanin yazacagi rapor dosyasi (calisma dizinine goreli)")
    p_ver.add_argument("--db", dest="alt_db", default=None, metavar="YOL", help=DB_YARDIM)

    p_liste = alt.add_parser("liste", help=ALT_KOMUT_ACIKLAMA["liste"])
    p_liste.add_argument("--durum", choices=DURUM_LISTESI, default=None, help="Duruma gore filtre")
    p_liste.add_argument("--kanitsiz", action="store_true",
                         help="Yalniz kaniti yetersiz gorevleri goster")
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
    p_calistir_bir.add_argument("--kati", action="store_true",
                                help="Kanitsiz/basarisiz/red durumlarinda cikis kodu 4")
    p_calistir_bir.add_argument("--db", dest="alt_db", default=None, metavar="YOL", help=DB_YARDIM)

    p_calistir = alt.add_parser("calistir", help=ALT_KOMUT_ACIKLAMA["calistir"])
    _calistir_bayraklari(p_calistir)
    p_calistir.add_argument(
        "--limit", type=int, default=VARSAYILAN_LIMIT, metavar="N",
        help=f"En fazla calistirilacak gorev (varsayilan {VARSAYILAN_LIMIT})",
    )
    p_calistir.add_argument("--kati", action="store_true",
                            help="Kanitsiz/basarisiz/red durumlarinda cikis kodu 4")
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

    # -- Dalga D: kanit dogrulama + planlayici ----------------------------
    p_dogrula = alt.add_parser("dogrula", help=ALT_KOMUT_ACIKLAMA["dogrula"])
    p_dogrula.add_argument("id", type=int, nargs="?", metavar="ID",
                           help="Kayitli kosunun logunu yeniden degerlendirir")
    p_dogrula.add_argument("--dosya", default=None, metavar="RAPOR.md",
                           help="Bagimsiz dosya degerlendirmesi (DB gerekmez)")
    p_dogrula.add_argument("--dizin", default=None, metavar="DIR",
                           help="Calisma dizini (gorel yollar buraya gore cozulur)")
    p_dogrula.add_argument("--rapor-dosyasi", default=None, metavar="YOL",
                           help="Ajanin yazdigi rapor dosyasi (calisma dizinine goreli)")
    p_dogrula.add_argument("--yaz", action="store_true",
                           help="Sonucu DB'ye yaz (yalniz kayitli kosunda)")
    p_dogrula.add_argument("--kati", action="store_true",
                           help="Uyari durumlarinda cikis kodu 4 don")
    p_dogrula.add_argument("--json", action="store_true", help="JSON olarak bas")
    p_dogrula.add_argument("--db", dest="alt_db", default=None, metavar="YOL", help=DB_YARDIM)

    p_planla = alt.add_parser("planla", help=ALT_KOMUT_ACIKLAMA["planla"])
    p_planla.add_argument("hedef", metavar="HEDEF", help="Proje hedefi")
    p_planla.add_argument("--baglam", default=None, metavar="DOSYA",
                          help="cor'a gonderilecek baglam dosyasi (en fazla 4000 karakter)")
    p_planla.add_argument("--kuru", action="store_true",
                          help="Aga cikmaz; promptun karakter sayisini yazar")
    p_planla.add_argument("--json", action="store_true", help="JSON olarak bas")
    p_planla.add_argument("--db", dest="alt_db", default=None, metavar="YOL", help=DB_YARDIM)

    p_plan_goster = alt.add_parser("plan-goster", help=ALT_KOMUT_ACIKLAMA["plan-goster"])
    p_plan_goster.add_argument("id", type=int, metavar="ID")
    p_plan_goster.add_argument("--json", action="store_true", help="JSON olarak bas")
    p_plan_goster.add_argument("--db", dest="alt_db", default=None, metavar="YOL", help=DB_YARDIM)

    p_plan_kuyruga = alt.add_parser(
        "plan-kuyruga", help=ALT_KOMUT_ACIKLAMA["plan-kuyruga"]
    )
    p_plan_kuyruga.add_argument("id", type=int, metavar="ID")
    p_plan_kuyruga.add_argument("--dalga", required=True, metavar="A",
                                help="Kuyruga eklenecek DALGA adi (yalniz bu)")
    p_plan_kuyruga.add_argument("--cwd", default=None, metavar="DIR",
                                help="Gorevlerin calisma dizini (goruntuleme icin)")
    p_plan_kuyruga.add_argument("--tekrar", action="store_true",
                                help="Ayni dalgayi ikinci kez eklemeye izin ver")
    p_plan_kuyruga.add_argument("--db", dest="alt_db", default=None, metavar="YOL", help=DB_YARDIM)

    # -- Kule entegrasyonu: salt-okunur durum ozeti ------------------------
    p_durum = alt.add_parser("durum", help=ALT_KOMUT_ACIKLAMA["durum"])
    p_durum.add_argument("--json", action="store_true",
                         help="Tek JSON nesnesi bas (kule bunu okur)")
    p_durum.add_argument("--kota-toml", default=None, metavar="YOL",
                         help=DEFAULT_KOTA_TOML_ACIKLAMA)
    p_durum.add_argument("--db", dest="alt_db", default=None, metavar="YOL", help=DB_YARDIM)
    return ayrac


def _ver(kuyruk: Queue, args) -> int:
    gorev = kuyruk.ekle(
        args.ajan, args.istem, getattr(args, "rapor_dosyasi", None)
    )
    print(f"Gorev #{gorev.id} eklendi: ajan={gorev.ajan} durum={gorev.durum.value}")
    if gorev.rapor_dosyasi:
        print(f"  rapor dosyasi: {gorev.rapor_dosyasi} (kosu sonunda ayristirilacak)")
    return 0


def _liste(kuyruk: Queue, args) -> int:
    """Görevleri listeler; `--kanitsiz` yalnız uyarı taşıyanları gösterir."""
    gorevler = kuyruk.liste(args.durum)
    if getattr(args, "kanitsiz", False):
        gorulen = []
        for gorev in gorevler:
            kosular = kuyruk.kosular(gorev.id)
            son = kosular[-1] if kosular else None
            if son and son.kanit_durumu in KANIT_UYARI_DURUMLARI:
                gorulen.append((gorev, son.kanit_durumu))
        if not gorulen:
            print("Kaniti yetersiz (kanitsiz/basarisiz/red suphesi) gorev yok.")
            return 0
        print(f"{'ID':>4}  {'DURUM':<14}  {'KANIT':<20}  {'AJAN':<16}  ISTEM")
        for gorev, kanit in gorulen:
            etiket = report.SONUC_ETIKETLERI.get(kanit, kanit)
            satir = f"{gorev.id:>4}  {gorev.durum.value:<14}  {kanit} ({etiket})"
            print(f"{satir:<60}{gorev.ajan:<16}  {gorev.onizleme}")
        print(f"Toplam {len(gorulen)} gorevde kanit uyarisi var.")
        return 0
    if not gorevler:
        print("Kuyruk bos.")
        return 0
    print(f"{'ID':>4}  {'DURUM':<14}  {'KANIT':<20}  {'AJAN':<16}  {'OLUSTURMA':<20}  ISTEM")
    for gorev in gorevler:
        kosular = kuyruk.kosular(gorev.id)
        son = kosular[-1] if kosular else None
        kanit = son.kanit_durumu if son and son.kanit_durumu else "-"
        print(
            f"{gorev.id:>4}  {gorev.durum.value:<14}  {kanit:<20}  {gorev.ajan:<16}  "
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


def _sonuc_yaz(gorev, kosu) -> bool:
    """Sonucu özetler; log YOLUNU basar, log METNINI ekrana dökmez.

    Kanıt uyarısı taşıyorsa stderr'e AÇIK uyarı yazar ve `True` döner.
    """
    print(f"Gorev #{gorev.id} -> {gorev.durum.value}")
    print(f"  run id    : {kosu.id}")
    print(f"  cikis kodu: {kosu.cikis_kodu}")
    if kosu.hata:
        print(f"  hata      : {guard.maskele(kosu.hata)}")
    if kosu.cikti_yolu:
        print(f"  log       : {kosu.cikti_yolu}")
    if kosu.kanit_durumu:
        etiket = report.SONUC_ETIKETLERI.get(kosu.kanit_durumu, kosu.kanit_durumu)
        print(f"  kanit     : {kosu.kanit_durumu} ({etiket})")
    if kosu.kanit_durumu in KANIT_UYARI_DURUMLARI:
        ozet = (kosu.kanit_ozeti or {}).get("ozet", "")
        print(
            f"  [UYARI] gorev #{gorev.id} kaniti yetersiz: {kosu.kanit_durumu}. {ozet}\n"
            f"          Raporu 'orkestra dogrula {gorev.id}' ile incele.",
            file=sys.stderr,
        )
        return True
    return False


def _calistir_bir(kuyruk: Queue, args) -> int:
    sonuc = kuyruk.calistir_bir(_runner(args))
    if sonuc is None:
        print("bekleyen gorev yok")
        return 0
    gorev, kosu = sonuc
    uyari = _sonuc_yaz(gorev, kosu)
    return KATI_CIKIS_KODU if (uyari and args_kati_mi(args)) else 0


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
    uyarili = 0
    try:
        while sayi < limit and not durduruldu:
            sonuc = kuyruk.calistir_bir(calisan)
            if sonuc is None:
                break
            gorev, kosu = sonuc
            sayi += 1
            if _sonuc_yaz(gorev, kosu):
                uyarili += 1
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
    if uyarili:
        print(
            f"{uyarili} gorevde kanit sorunu var (kanitsiz/basarisiz/red suphesi). "
            "Ayrinti: 'orkestra dogrula <id>'.",
            file=sys.stderr,
        )
    return KATI_CIKIS_KODU if (uyarili and args_kati_mi(args)) else 0


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


def _kanit_bolumu_yaz(kosu) -> None:
    """Koşunun kanıt özetini yazar: GÖZLEMLENEN kanıt ve BEYAN ayrı listelenir.

    `kanit_ozeti` DB'de MASKELİ JSON olarak durur; burada olduğu gibi basılır.
    """
    if not kosu.kanit_durumu or not kosu.kanit_ozeti:
        print("  kanit     : (degerlendirilmedi)")
        return
    ozet = kosu.kanit_ozeti
    etiket = report.SONUC_ETIKETLERI.get(kosu.kanit_durumu, kosu.kanit_durumu)
    print(f"  kanit     : {kosu.kanit_durumu} ({etiket})")
    print("  --- gozlemlenen kanit (orkestra'nin kendi baktigi) ---")
    gorseller = ozet.get("gorseller", [])
    if not gorseller:
        print("    (gorsel kaniti yok)")
    for g in gorseller:
        isaret = "GECTI" if g.get("gecerli") else "KALDI"
        print(f"    [{isaret}] {g.get('yol')}: {g.get('gerekce')}")
    if ozet.get("git_degisti") is not None:
        print(f"    git agaci/HEAD: {'DEGISTI' if ozet['git_degisti'] else 'DEGISMEDI'}")
    else:
        print("    git agaci/HEAD: bilinmiyor")
    print("  --- beyan (yalnizca metinde yazan, kanit SAYILMAZ) ---")
    testler = ozet.get("testler", [])
    if not testler:
        print("    (test beyani yok)")
    for t in testler:
        sayilar = f"{t.get('passed') or 0} passed"
        if t.get("failed"):
            sayilar += f", {t['failed']} failed"
        print(f"    - {t.get('tur')}: {sayilar}")
    iddialar = ozet.get("iddialar", [])
    if iddialar:
        for i in iddialar[:5]:
            print(f"    - iddia: {i}")
    gerekceler = ozet.get("gerekceler", [])
    if gerekceler:
        print("  --- gerekceler ---")
        for g in gerekceler:
            print(f"    - {g.get('kural')}: {g.get('kanit')}")


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
    # Kanıt bölümü: gözlemlenen kanıt ile beyan AYRI gösterilir.
    _kanit_bolumu_yaz(kosu)
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


# -- Dalga D: kanit degerlendirme ---------------------------------------


def _degerlendirme_yaz(d, *, as_json: bool) -> None:
    """Degerlendirmeyi insana okunur biçimde yazar (gözlemlenen / beyan AYRI)."""
    if as_json:
        import json as _json

        print(_json.dumps(d.json(), ensure_ascii=False, indent=2))
        return
    etiket = report.SONUC_ETIKETLERI.get(d.sonuc, d.sonuc)
    print(f"Sonuc      : {d.sonuc} ({etiket})")
    print(f"Gozlemlenen: {d.gecerli_gorsel_sayisi} gorsel")
    for g in d.gorseller:
        isaret = "GECTI" if g.gecerli else "KALDI"
        print(f"  [{isaret}] {g.yol}: {g.gerekce}")
    print(f"Beyan      : {len(d.testler)} test, {len(d.iddialar)} iddia")
    for t in d.testler[:10]:
        sayilar = f"{t.passed or 0} passed"
        if t.failed:
            sayilar += f", {t.failed} failed"
        if t.error:
            sayilar += f", {t.error} error"
        print(f"  [beyan] {t.tur}: {sayilar}")
    if d.git_degisti is not None:
        print(f"Git        : {'DEGISTI' if d.git_degisti else 'DEGISMEDI'}")
    else:
        print("Git        : bilinmiyor (calisma dizini git deposu degil)")
    if d.uyarilar:
        print("Uyarilar   :")
        for u in d.uyarilar:
            print(f"  - {u}")
    print("Gerekceler :")
    for g in d.gerekceler:
        print(f"  - {g.kural}: {g.kanit}")


def _kosu_logu_oku(kosu) -> str:
    """Koşunun log dosyasını okur (yol DB'den gelir, dosya yoksa boş dize)."""
    if not kosu.cikti_yolu:
        return ""
    try:
        return Path(kosu.cikti_yolu).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _dogrula(kuyruk: Queue, args) -> int:
    """Kayıtlı koşuyu veya bağımsız dosyayı yeniden değerlendirir (ağsız, salt okunur)."""
    if args.dosya:
        # Bağımsız dosya değerlendirmesi: DB GEREKMEZ.
        dizin = args.dizin or str(Path(args.dosya).expanduser().resolve().parent)
        try:
            metin = Path(args.dosya).expanduser().read_text(encoding="utf-8", errors="replace")
        except OSError as hata:
            print(f"Hata: rapor okunamadi: {type(hata).__name__}", file=sys.stderr)
            return 1
        d = report.degerlendir(
            metin, calisma_dizini=dizin, rapor_dosyasi=args.rapor_dosyasi
        )
        _degerlendirme_yaz(d, as_json=args.json)
        return KATI_CIKIS_KODU if (args_kati_mi(args) and d.uyari_mi) else 0

    if args.id is None:
        print("Hata: ID verin ya da --dosya kullanin.", file=sys.stderr)
        return 2
    try:
        gorev = kuyruk.al(args.id)
    except OrkestraHata as hata:
        print(f"Hata: {hata}", file=sys.stderr)
        return 1
    kosular = kuyruk.kosular(gorev.id)
    if not kosular:
        print(f"Bu gorev hic calistirilmamis (gorev #{gorev.id}).")
        return 0
    kosu = kosular[-1]
    print(f"Gorev #{gorev.id}  run #{kosu.id}")
    d = report.degerlendir(
        _kosu_logu_oku(kosu),
        calisma_dizini=args.dizin or Path.cwd(),
        rapor_dosyasi=args.rapor_dosyasi,
    )
    _degerlendirme_yaz(d, as_json=args.json)
    if args.yaz:
        kuyruk.run_kanit_yaz(kosu.id, d.sonuc, d.json())
        print(f"\nDB'ye yazildi: run #{kosu.id} kanit_durumu={d.sonuc}")
    return KATI_CIKIS_KODU if (args_kati_mi(args) and d.uyari_mi) else 0


def args_kati_mi(args) -> bool:
    """`--kati` bayrağı (yalnız `dogrula`/`calistir*` anlamlı)."""
    return bool(getattr(args, "kati", False))


# -- Dalga D: planlayici --------------------------------------------------


def _planla(kuyruk: Queue, args) -> int:
    from .llm import DEFAULT_BASE_URL, DEFAULT_MODEL, CorLLMClient, LLMError

    hedef = args.hedef.strip()
    baglam = planner.baglam_oku(args.baglam) if args.baglam else ""
    if args.kuru:
        # AĞA ÇIKMAZ: istemci hiç oluşturulmaz.
        prompt = planner.prompt_olustur(hedef, baglam)
        print(f"Kuru mod: aga cikilmadi.")
        print(f"  hedef karakter : {len(hedef)}")
        print(f"  baglam karakter: {len(baglam)}")
        print(f"  prompt karakter: {len(prompt)}")
        return 0
    try:
        plan = planner.planla(hedef, istemci=CorLLMClient(), baglam=baglam)
    except planner.PlanHatasi as hata:
        # Geçersiz çıktıda KISMİ SONUÇ YOK: net hata, çıkış kodu 3.
        print(f"Plan reddedildi: {hata}", file=sys.stderr)
        return 3
    except LLMError as hata:
        # LLM'e erişilemedi / boş yanıt. İZİN RETTİ DEĞİLDİR, plan reddi de
        # değil: ağ/erişim hatası → çıkış kodu 1, KISMİ PLAN YOK.
        print(f"LLM hatasi: {hata}", file=sys.stderr)
        return 1
    except OrkestraHata as hata:
        print(f"Hata: {hata}", file=sys.stderr)
        return 1
    plan_id = kuyruk.plan_kaydet(plan.json(), hedef)
    if args.json:
        import json as _json

        print(_json.dumps({"id": plan_id, **plan.json()}, ensure_ascii=False, indent=2))
        return 0
    print(f"Plan #{plan_id} kaydedildi ({len(plan.dalgalar)} dalga).")
    print(f"Hedef: {plan.hedef}")
    for dalga in plan.dalgalar:
        print(f"\n  Dalga {dalga.ad}: {dalga.amac}")
        for g in dalga.gorevler:
            print(f"    - [{g.ajan}] {g.istem.splitlines()[0][:80]}")
        for k in dalga.kabul:
            print(f"    kabul: {k}")
    print("\nGorevleri kuyruga eklemek icin: orkestra plan-kuyruga "
          f"{plan_id} --dalga {plan.dalgalar[0].ad}")
    return 0


def _plan_goster(kuyruk: Queue, args) -> int:
    kayit = kuyruk.plan_al(args.id)
    if kayit is None:
        print(f"Hata: plan bulunamadi: {args.id}", file=sys.stderr)
        return 1
    if args.json:
        import json as _json

        print(_json.dumps(kayit, ensure_ascii=False, indent=2))
        return 0
    print(f"Plan #{kayit['id']}  ({kayit['olusturma']})")
    print(f"Hedef: {kayit['hedef']}")
    for dalga in kayit["json"].get("dalgalar", []):
        print(f"\n  Dalga {dalga['ad']}: {dalga['amac']}")
        for g in dalga.get("gorevler", []):
            print(f"    - [{g['ajan']}] {g['istem'].splitlines()[0][:80]}")
    return 0


def _plan_kuyruga(kuyruk: Queue, args) -> int:
    """SEÇİLEN tek dalganın görevlerini kuyruğa ekler. ASLA çalıştırmaz."""
    kayit = kuyruk.plan_al(args.id)
    if kayit is None:
        print(f"Hata: plan bulunamadi: {args.id}", file=sys.stderr)
        return 1
    veri = kayit["json"]
    try:
        plan = planner.Plan(
            hedef=kayit["hedef"],
            dalgalar=[
                planner.Dalga(
                    ad=d["ad"], amac=d.get("amac", ""),
                    gorevler=[planner.Gorev(ajan=g["ajan"], istem=g["istem"])
                              for g in d.get("gorevler", [])],
                    kabul=d.get("kabul", []),
                )
                for d in veri.get("dalgalar", [])
            ],
        )
    except (KeyError, TypeError) as hata:
        print(f"Hata: plan yapisi bozuk: {type(hata).__name__}", file=sys.stderr)
        return 1
    dalga = plan.dalga_bul(args.dalga)
    if dalga is None:
        mevcut = ", ".join(d.ad for d in plan.dalgalar)
        print(f"Hata: '{args.dalga}' bu planda yok. Mevcut: {mevcut}", file=sys.stderr)
        return 1
    if not args.tekrar:
        # Aynı dalga ikinci kez eklenirse `--tekrar` gerekir.
        isaretli = _plandan_eklenenler(kuyruk, args.id, dalga)
        if isaretli:
            print(
                f"Hata: '{dalga.ad}' dalgasi bu plandan zaten eklenmis "
                f"({isaretli} gorev). Tekrar eklemek icin --tekrar kullanin.",
                file=sys.stderr,
            )
            return 2
    eklendi = []
    for gorev, istem in plan.istemleri(dalga):
        # Kuyruğa eklenen istem SABİT ekleri (kabul + kanıt biçimi) içerir.
        yeni = kuyruk.ekle(gorev.ajan, istem)
        eklendi.append(yeni)
    print(f"Plan #{args.id} / Dalga {dalga.ad}: {len(eklendi)} gorev eklendi "
          f"(bekliyor). CALISTIRILMADI.")
    for g in eklendi:
        print(f"  gorev #{g.id}: {g.ajan}")
    return 0


def _plandan_eklenenler(kuyruk: Queue, plan_id: int, dalga) -> int:
    """Bu plandan bu dalganın görevleri kaç kez eklendi (istem eşleşmesi)."""
    istenen = {istem for _, istem in planner.Plan(hedef="x").istemleri(dalga)}
    if not istenen:
        return 0
    sayac = 0
    for gorev in kuyruk.liste():
        if gorev.istem in istenen:
            sayac += 1
    return sayac


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

    if args.komut == "durum":
        # Kule entegrasyonu: DB'ye YAZMAZ. Yazma yapan Queue baglami acilmaz
        # (sema/migration tetiklenmez); `durum.durum_oku` kendi `mode=ro`
        # baglantisini acar.
        if args.json:
            return durum_mod.calistir_ve_yaz(args.db, args.kota_toml)
        return durum_mod.insan_ozeti(args.db, args.kota_toml)

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
            if args.komut == "dogrula":
                return _dogrula(kuyruk, args)
            if args.komut == "planla":
                return _planla(kuyruk, args)
            if args.komut == "plan-goster":
                return _plan_goster(kuyruk, args)
            if args.komut == "plan-kuyruga":
                return _plan_kuyruga(kuyruk, args)
    except OrkestraHata as hata:
        print(f"Hata: {hata}", file=sys.stderr)
        return 1
    ayrac.error(f"bilinmeyen komut: {args.komut}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())