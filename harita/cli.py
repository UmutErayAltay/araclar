"""`harita` komut satırı arayüzü (Dalga A + Dalga B + Dalga C).

Alt komutlar: indeksle, kirik, yetim, etiketler, web, ozet, tutarlilik.
"""

from __future__ import annotations

import argparse
import os
import re
import sqlite3
import sys
from datetime import date
from pathlib import Path

from . import __version__, index as indeks_modulu

BOSLUK = " "

VARSAYILAN_VAULT = Path.home() / "Mt3Ui55OS"


def _tarih_coz(metin: str) -> date:
    """`YYYY-MM-DD` → date (testlerin "bugün"ü sabitlemesi için)."""
    from datetime import datetime

    return datetime.strptime(metin, "%Y-%m-%d").date()


def _akisi_ayarla() -> None:
    """Windows cp1252 konsolunda Türkçe karakterlerin çökmesini engeller."""
    for akis in (sys.stdout, sys.stderr):
        reconfigure = getattr(akis, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def _db_yolu(args: argparse.Namespace) -> Path:
    """Verilen `--db`, yoksa $HARITA_DB / ~/.harita/harita.db."""
    db = getattr(args, "db", None)
    return Path(db).expanduser() if db else indeks_modulu.varsayilan_db()


def _db_ac(db_yolu: str | None) -> sqlite3.Connection:
    yol = Path(db_yolu).expanduser() if db_yolu else indeks_modulu.varsayilan_db()
    if not yol.exists():
        raise SystemExit(f"İndeks bulunamadı: {yol}\nÖnce `harita indeksle VAULT` çalıştır.")
    baglanti = indeks_modulu.baglan(yol)
    indeks_modulu.sema_olustur(baglanti)
    return baglanti


def komut_indeksle(args: argparse.Namespace) -> int:
    vault = Path(args.vault)
    if not vault.is_dir():
        print(f"Hata: vault bulunamadı: {vault}", file=sys.stderr)
        return 2
    db_yolu = _db_yolu(args)
    ozet = indeks_modulu.indeksle(vault, db_yolu)
    print(f"İndeks: {db_yolu}")
    print(ozet.ozet_metni())
    return 0


def komut_kirik(args: argparse.Namespace) -> int:
    baglanti = _db_ac(_db_yolu(args))
    try:
        kirik = indeks_modulu.kirik_linkler(baglanti)
    finally:
        baglanti.close()
    if not kirik:
        print("Kırık link yok.")
        return 0
    print(f"Kırık link: {len(kirik)}")
    for yol, baslik, hedef in kirik[: args.ilk] if args.ilk else kirik:
        print(f"  {yol}{BOSLUK}({baslik}) → [[{hedef}]]")
    if args.ilk and len(kirik) > args.ilk:
        print(f"  ... ve {len(kirik) - args.ilk} tane daha")
    return 0


def komut_yetim(args: argparse.Namespace) -> int:
    baglanti = _db_ac(_db_yolu(args))
    try:
        bolum = indeks_modulu.yetim_ayir(baglanti)
        hepsi = indeks_modulu.yetim_notlar(baglanti)
    finally:
        baglanti.close()

    # Varsayılan: yalnız GERÇEK yetimler. `--tumu` Dalga A davranışını verir
    # (daily/ günlükleri ve kök dosyaları da listeler).
    if args.tumu:
        kayitlar = list(hepsi)
        baslik_satiri = f"Yetim not: {len(kayitlar)}"
    else:
        kayitlar = [(yol, baslik) for _, yol, baslik in bolum.gercek]
        baslik_satiri = f"Yetim not: {len(kayitlar)}"
        if len(bolum.yok_sayilabilir):
            baslik_satiri += f" (yok sayılabilir: {len(bolum.yok_sayilabilir)}, `--tumu` ile gör)"

    if not kayitlar:
        print("Yetim not yok.")
        return 0
    print(baslik_satiri)
    for yol, baslik_ad in kayitlar[: args.ilk] if args.ilk else kayitlar:
        print(f"  {yol}{BOSLUK}({baslik_ad})")
    if args.ilk and len(kayitlar) > args.ilk:
        print(f"  ... ve {len(kayitlar) - args.ilk} tane daha")
    return 0


def komut_etiketler(args: argparse.Namespace) -> int:
    baglanti = _db_ac(_db_yolu(args))
    try:
        etiketler = indeks_modulu.etiket_sikligi(baglanti, args.ilk)
    finally:
        baglanti.close()
    if not etiketler:
        print("Etiket yok.")
        return 0
    en_genis = max((str(adet) for _, adet in etiketler), key=len)
    for etiket, adet in etiketler:
        print(f"  {adet:>{len(en_genis)}}  #{etiket}")
    return 0


# Terminal çıktısı için: TTY ise ANSI kalın, değilse `«...»`.
_KALIN = "\033[1m"
_NORMAL = "\033[0m"
# TTY'yi taklit eden kod sayacı: alt süreçler de TTY sanmasın.
_KACIS_SIFIRLA = 0 if os.isatty(sys.stdout.fileno()) else 1  # noqa: E501


def _vurgula(metin: str, vurgular: list[tuple[int, int]]) -> str:
    """Alıntıdaki eşleşmeleri vurgular (TTY: kalın; değilse `«...»`).

    Vurgu parçaları KATLANMIŞ metin üzerinde bulunur; `katla` 1:1 eşlediği
    için ofsetler özgün metne aittir. Aralıklar zaten sıralı ve ayrık gelir.
    """
    if not vurgular:
        return metin
    parcalar: list[str] = []
    onceki = 0
    for bas, bit in vurgular:
        bas, bit = max(0, bas), min(len(metin), bit)
        if bas >= bit:
            continue
        parcalar.append(metin[onceki:bas])
        parca = metin[bas:bit]
        parcalar.append(f"{_KALIN}{parca}{_NORMAL}" if _KACIS_SIFIRLA == 0 else f"«{parca}»")
        onceki = bit
    parcalar.append(metin[onceki:])
    return "".join(parcalar)


def _konsol_temizle(metin: str) -> str:
    """Terminal kontrol karakterlerini (ANSI, CR, escape) kaldırır.

    Not içeriği kullanıcı verisidir; konsolu bozabilmesin diye temizlenir.
    """
    return _KONTROL_DESENI.sub("", metin)


_KONTROL_DESENI = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def komut_ara(args: argparse.Namespace) -> int:
    """BM25 tam-metin arama. Tamamen yerel: ağa çıkmaz, cor'u çağırmaz.

    Sonuç yoksa net mesaj + çıkış kodu 0; YALNIZCA hata sıfırdan farklıdır.
    """
    from . import ara as ara_modulu

    baglanti = _db_ac(_db_yolu(args))
    try:
        ayarlar = ara_modulu.Ayarlar(
            ilk=args.ilk,
            etiket=args.etiket,
            klasor=args.klasor,
            tam=args.tam,
        )
        sonuclar, _ = ara_modulu.ara(baglanti, args.sorgu, ayarlar)
    except ara_modulu.SorguHatasi as exc:
        print(f"Hata: {exc}", file=sys.stderr)
        return 2
    finally:
        baglanti.close()

    if args.json:
        import json

        veri = [
            {
                "puan": s.puan,
                "baslik": s.baslik,
                "yol": s.yol,
                "etiketler": s.etiketler,
                "alinti": s.alinti,
                "not_id": s.not_id,
            }
            for s in sonuclar
        ]
        print(json.dumps({"sorgu": args.sorgu, "sonuc": len(veri), "kayitlar": veri},
                         ensure_ascii=False, indent=2))
        return 0

    if not sonuclar:
        print(f"'{_konsol_temizle(args.sorgu)}' için sonuç yok.")
        return 0

    print(f"{len(sonuclar)} sonuç")
    for i, s in enumerate(sonuclar, 1):
        print(f"{i:>2}. {_konsol_temizle(s.baslik)}  ({s.puan:.3f})")
        print(f"    {_konsol_temizle(s.yol)}")
        if s.etiketler:
            rozetler = " ".join(f"#{_konsol_temizle(e)}" for e in s.etiketler)
            print(f"    {rozetler}")
        if s.alinti:
            print(f"    {_vurgula(_konsol_temizle(s.alinti), s.vurgular)}")
    return 0


def komut_web(args: argparse.Namespace) -> int:
    """Grafi sunar. Sunucu ADRESİ KODDA SABİTTİR: yalnız 127.0.0.1.

    `VAULT` verilirse önce indekslenir (salt okunur); sonra DB `mode=ro` ile
    açılır. `--host` seçeneği BİLEREK YOKTUR: dışarıya açmak için kod
    değiştirmek gerekir.
    """
    from .web import sunucu  # Flask yalnızca bu komutta yüklenir

    db_yolu = _db_yolu(args)
    if args.vault:
        vault = Path(args.vault)
        if not vault.is_dir():
            print(f"Hata: vault bulunamadı: {vault}", file=sys.stderr)
            return 2
        ozet = indeks_modulu.indeksle(vault, db_yolu)
        print(f"İndeks: {db_yolu}")
        print(ozet.ozet_metni())
    elif not db_yolu.exists():
        print(
            f"Hata: indeks bulunamadı: {db_yolu}\n"
            "Önce `harita indeksle VAULT` ya da `harita web VAULT` çalıştır.",
            file=sys.stderr,
        )
        return 2

    print(f"harita web → http://127.0.0.1:{args.port}  (yalnızca yerel; Ctrl+C ile dur)")
    try:
        sunucu.calistir(db_yolu, args.port)
    except KeyboardInterrupt:  # pragma: no cover
        print("\nDurduruldu.")
    return 0


def _ozet_dosyaya_yaz(ozet_modulu, dosya: str, vault: Path, cikti: str, veri, gonderilen) -> None:
    """Özeti dosyaya yazar; çözümlenen yol vault KÖKÜNDEYSE reddeder.

    Özet vault'a yazılmaz (Umut'un kararı): özet bir NOT değil, türetilmiş
    bir çıktıdır; vault'un kendisi salt okunur kalır.
    """
    hedef = Path(dosya).expanduser().resolve()
    kok = vault.expanduser().resolve()
    if hedef == kok or kok in hedef.parents:
        raise ValueError(f"özet vault'a yazılamaz (hedef vault içinde): {hedef}")
    hedef.parent.mkdir(parents=True, exist_ok=True)
    durum = (
        f"cor'a gönderildi: evet ({gonderilen} karakter)"
        if gonderilen is not None
        else "cor'a gönderildi: hayır"
    )
    kirp = f"\n{veri.kesilen_karakter} karakter kırpıldı" if veri.kesilen_karakter else ""
    hedef.write_text(
        f"{cikti}\n\n{ozet_modulu.kaynak_satiri(veri)}\n{durum}{kirp}\n",
        encoding="utf-8",
    )


def komut_ozet(args: argparse.Namespace) -> int:
    """Haftalık özet.

    Gizlilik (bağlayıcı): varsayılan davranış AĞA ÇIKMAZ, çıktı deterministik
    bir ham listedir. cor'a YALNIZCA açık `--cor` bayrağıyla gider.
    `--kuru` hiçbir içerik göstermeden ağa çıkmadan hangi dosyaların
    gönderileceğini yazar.
    """
    from . import llm as llm_modulu
    from . import ozet as ozet_modulu

    vault = Path(args.vault)
    if not vault.is_dir():
        print(f"Hata: vault bulunamadı: {vault}", file=sys.stderr)
        return 2

    try:
        veri = ozet_modulu.veri_topla(vault, gun=args.gun, bugun=args.bugun)
    except OSError as exc:
        print(f"Hata: vault okunamadı: {exc}", file=sys.stderr)
        return 2

    if args.kuru:
        toplam = veri.toplam_karakter
        print(f"Kuru çalışma: {len(veri.kaynaklar)} dosya, toplam {toplam} karakter")
        for kaynak in veri.kaynaklar:
            print(f"  {kaynak.karakter:>6}  {kaynak.yol}")
        print(f"Toplam: {toplam} karakter")
        return 0

    gonderilen: int | None = None
    if args.cor:
        try:
            istemci = llm_modulu.CorLLMClient(
                base_url=args.cor_url or llm_modulu.DEFAULT_BASE_URL,
                model=args.cor_model or llm_modulu.DEFAULT_MODEL,
            )
            cikti, gonderilen = ozet_modulu.ozet_yaz(veri, cor=True, istemci=istemci)
        except llm_modulu.LLMError as exc:
            # Başarı gibi GÖRÜNMEZ: uyarı + ham liste + çıkış kodu 3.
            print(f"UYARI: cor'a gönderilemedi ({exc}). Ham liste basılıyor.", file=sys.stderr)
            print(ozet_modulu.ham_liste(veri))
            print()
            print(ozet_modulu.kaynak_satiri(veri))
            print("cor'a gönderildi: hayır")
            return 3
    else:
        cikti, gonderilen = ozet_modulu.ozet_yaz(veri)

    if args.yaz:
        try:
            _ozet_dosyaya_yaz(ozet_modulu, args.yaz, vault, cikti, veri, gonderilen)
        except ValueError as exc:
            print(f"Hata: {exc}", file=sys.stderr)
            return 2

    print(cikti)
    print()
    print(ozet_modulu.kaynak_satiri(veri))
    if gonderilen is not None:
        print(f"cor'a gönderildi: evet ({gonderilen} karakter)")
    else:
        print("cor'a gönderildi: hayır")
    if veri.kesilen_karakter:
        print(f"{veri.kesilen_karakter} karakter kırpıldı")
    return 0


def komut_tutarlilik(args: argparse.Namespace) -> int:
    """Vault↔repo tutarlılığı. SALT OKUNUR; hiçbir şeyi değiştirmez."""
    from . import tutarlilik as tut_modulu

    vault = Path(args.vault)
    if not vault.is_dir():
        print(f"Hata: vault bulunamadı: {vault}", file=sys.stderr)
        return 2

    atlas_db = args.atlas_db or tut_modulu.VARSAYILAN_ATLAS_DB
    try:
        atlas = tut_modulu.atlas_oku(atlas_db)
    except SystemExit as exc:
        print(str(exc), file=sys.stderr)
        return 2

    esleme_yolu = Path(args.esleme).expanduser() if args.esleme else tut_modulu.VARSAYILAN_ESLESME
    eslesme = tut_modulu.eslesme_dosyasi_oku(esleme_yolu)

    rapor = tut_modulu.bulgular_uret(vault, atlas, eslesme, esik_gun=args.esik_gun)

    if args.json:
        import json

        print(json.dumps(rapor.sozluk(), ensure_ascii=False, indent=2))
    else:
        if rapor.atlas_uyari:
            print(f"UYARI: {rapor.atlas_uyari}")
        # "Kontrol edilenler" ÖNCE gelir: "0 uyarı" ya tutarlılık ya da
        # hiçbir şeyin eşleşmemiş olmasıdır — hangisi olduğu burada belli olur.
        print("Kontrol edilenler:")
        print("  " + rapor.kontrol_et_metni().replace("\n", "\n  "))
        for cift in rapor.ciftler:
            kaynak = cift.yontem + (" (tahmin)" if cift.tahmin else "")
            print(f"    - {cift.not_yolu} → {cift.repo}  [kaynak: {kaynak}, güven: {cift.guven}]")
        for baslik, liste in (("Uyarılar", rapor.uyarilar), ("Bilgiler", rapor.bilgiler)):
            print(f"{baslik} ({len(liste)}):")
            for b in liste:
                print(f"  [{b.guven}] {b.baslik} — {b.kural}")
                print(f"      gerekçe: {b.gerekce}")
                print(f"      öneri:   {b.oneri}")
        print(f"Kontrol edilemeyenler ({len(rapor.kontrol_edilemeyenler)}):")
        for ad in sorted(rapor.kontrol_edilemeyenler):
            print(f"  {ad}")

    if args.kati and rapor.uyarilar:
        return 1
    return 0


def arg_parser() -> argparse.ArgumentParser:
    # `--db` hem `harita --db X kirik` hem `harita kirik --db X` biçiminde çalışsın.
    # SUPPRESS: alt komut `--db` verilmediğinde, `default=None` üstteki değeri
    # ezip `harita --db X kirik` biçimini bozardı.
    ortak = argparse.ArgumentParser(add_help=False)
    ortak.add_argument(
        "--db",
        default=argparse.SUPPRESS,
        help="SQLite indeks dosyası (varsayılan: $HARITA_DB veya ~/.harita/harita.db)",
    )

    parser = argparse.ArgumentParser(
        prog="harita",
        parents=[ortak],
        description="Vault zihin haritası: not grafiğini indeksler ve sağlığını raporlar.",
    )
    parser.add_argument("--versiyon", action="version", version=f"harita {__version__}")
    alt = parser.add_subparsers(dest="komut", required=True)

    p = alt.add_parser("indeksle", parents=[ortak], help="Vault'u indeksle")
    p.add_argument("vault", help="Vault kökü")
    p.set_defaults(fonksiyon=komut_indeksle)

    p = alt.add_parser("kirik", parents=[ortak], help="Çözülemeyen linkleri listele")
    p.add_argument("--ilk", type=int, default=None, help="Yalnızca ilk N kaydı göster")
    p.set_defaults(fonksiyon=komut_kirik)

    p = alt.add_parser("yetim", parents=[ortak], help="Ne link alan ne link veren notları listele")
    p.add_argument("--ilk", type=int, default=None, help="Yalnızca ilk N kaydı göster")
    p.add_argument(
        "--tumu",
        action="store_true",
        help="`daily/` günlükleri ve kökteki tek-bileşenli dosyalar (yok sayılabilirler) dahil listele",
    )
    p.set_defaults(fonksiyon=komut_yetim)

    p = alt.add_parser("etiketler", parents=[ortak], help="Etiketleri sıklığa göre listele")
    p.add_argument("--ilk", type=int, default=None, help="Yalnızca ilk N etiketi göster")
    p.set_defaults(fonksiyon=komut_etiketler)

    p = alt.add_parser("ara", parents=[ortak], help="BM25 tam-metin arama (yerel)")
    p.add_argument("sorgu", help='Arama sorgusu; "tırnaklı ifade", -terim, etiket:ad')
    p.add_argument("--ilk", type=int, default=10, help="En fazla N sonuç (varsayılan: 10)")
    p.add_argument("--etiket", default=None, help="Etiket filtresi (sorguda `etiket:ad` da olur)")
    p.add_argument("--klasor", default=None, help="Klasör/yol öneki filtresi")
    p.add_argument(
        "--tam",
        action="store_true",
        help="Kök kesmeyi kapat: tam sözcük eşleşmesi",
    )
    p.add_argument("--json", action="store_true", help="JSON olarak bas")
    p.set_defaults(fonksiyon=komut_ara)

    p = alt.add_parser("web", parents=[ortak], help="Grafiği 127.0.0.1 üzerinde sun")
    p.add_argument("vault", nargs="?", help="Verilirse önce salt-okunur indeksler")
    p.add_argument("--port", type=int, default=8765, help="Dinlenecek port (varsayılan: 8765)")
    p.set_defaults(fonksiyon=komut_web)

    p = alt.add_parser("ozet", parents=[ortak], help="Haftalık özet (varsayılan: ağa çıkmaz)")
    p.add_argument("vault", nargs="?", default=str(VARSAYILAN_VAULT), help="Vault kökü")
    p.add_argument("--hafta", action="store_true", help="7 günlük pencere (varsayılan)")
    p.add_argument("--gun", type=int, default=7, help="Pencere gün sayısı (varsayılan: 7)")
    p.add_argument(
        "--cor",
        action="store_true",
        help="Özeti cor'a GÖNDER (varsayılan: ağa çıkmaz, ham liste basılır)",
    )
    p.add_argument("--cor-url", default=None, help="cor taban adresi (varsayılan: $COR_BASE_URL)")
    p.add_argument("--cor-model", default=None, help="cor modeli (varsayılan: $COR_MODEL)")
    p.add_argument(
        "--kuru",
        action="store_true",
        help="Hiçbir içerik göstermeden, ağa çıkmadan gönderilecek dosyaları yaz",
    )
    p.add_argument("--yaz", metavar="DOSYA", default=None, help="Özeti dosyaya yaz (vault içi REDDEDİLİR)")
    p.add_argument("--bugun", type=_tarih_coz, default=None, help=argparse.SUPPRESS)
    p.set_defaults(fonksiyon=komut_ozet)

    p = alt.add_parser(
        "tutarlilik", parents=[ortak], help="Vault notları ile atlas repo durumunu karşılaştır"
    )
    p.add_argument("vault", nargs="?", default=str(VARSAYILAN_VAULT), help="Vault kökü")
    p.add_argument(
        "--atlas-db",
        default=None,
        help="atlas SQLite DB'si (varsayılan: ~/.atlas/atlas.db)",
    )
    p.add_argument(
        "--esleme", default=None, help="Eşleme dosyası (varsayılan: ~/.harita/repolar.toml)"
    )
    p.add_argument("--esik-gun", type=int, default=30, help="Durgunluk eşiği (varsayılan: 30 gün)")
    p.add_argument("--json", action="store_true", help="JSON olarak bas")
    p.add_argument("--kati", action="store_true", help="Uyarı varsa çıkış kodu 1")
    p.add_argument("--bugun", type=_tarih_coz, default=None, help=argparse.SUPPRESS)
    p.set_defaults(fonksiyon=komut_tutarlilik)

    return parser


def main(argv: list[str] | None = None) -> int:
    _akisi_ayarla()
    args = arg_parser().parse_args(argv)
    return int(args.fonksiyon(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
