"""tekrar komut satırı: uret / sor / zor / durum.

Çıkış kodları: 0 başarı, 1 kart bulunamadı, 2 kullanım/okuma hatası, 3 cor hatası,
4 Telegram gönderilemedi.
Gizlilik (bağlayıcı): `uret` varsayılan olarak AĞA ÇIKMAZ; cor'a yalnız açık `--cor`
bayrağıyla gider. Çıktıya not içeriği ya da kart metni (cor akışında) yazılmaz.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from . import telegram, uret as uret_modulu
from .kartlar import Depo, DepoHatasi


def _bugun(deger: str | None) -> date:
    return date.fromisoformat(deger) if deger else date.today()


def _depo(args: argparse.Namespace) -> Depo:
    return Depo(Path(args.depo)) if args.depo else Depo.varsayilan()


def komut_uret(args: argparse.Namespace) -> int:
    from . import llm

    vault = Path(args.vault)
    if not vault.is_dir():
        print(f"Hata: vault bulunamadı: {vault}", file=sys.stderr)
        return 2
    depo = _depo(args)

    if args.kuru or not args.cor:
        gerekli, atlanan = uret_modulu.bekleyen_notlar(vault, depo)
        islenecek = min(len(gerekli), args.en_cok)
        print(f"{len(gerekli)} not yeni/değişmiş, {atlanan} not değişmemiş.")
        print(f"--cor ile {islenecek} cor çağrısı yapılır.")
        print("cor'a gönderilmedi (--cor ile gönder).")
        return 0

    try:
        istemci = llm.CorLLMClient(
            base_url=args.cor_url or llm.DEFAULT_BASE_URL,
            model=args.cor_model or llm.DEFAULT_MODEL,
        )
    except llm.LLMError as exc:
        print(f"Hata: {exc}", file=sys.stderr)
        return 2

    try:
        sonuc = uret_modulu.uret(vault, depo, istemci, _bugun(args.bugun), en_cok_not=args.en_cok)
    except llm.LLMError as exc:
        depo.kaydet()  # o ana kadar eklenenler kalsın
        print(f"UYARI: cor hatası ({exc}); o ana kadarki kartlar kaydedildi.", file=sys.stderr)
        return 3
    depo.kaydet()
    print(
        f"İşlenen not: {sonuc['islenen']}, eklenen kart: {sonuc['eklenen_kart']}, "
        f"boş: {sonuc['bos']}, sır nedeniyle atlanan: {sonuc['atlanan_sir']}, "
        f"değişmemiş: {sonuc['atlanan_degismemis']}"
    )
    return 0


def komut_sor(args: argparse.Namespace) -> int:
    depo = _depo(args)
    bugun = _bugun(args.bugun)
    kartlar = depo.vadesi_gelen(bugun, args.adet)
    if not kartlar:
        print("Bugün tekrar yok.")
        return 0

    for i, k in enumerate(kartlar, 1):
        print(f"{i}. {k.soru}")
        print(f"   {k.cevap}")

    if args.telegram:
        mesaj = telegram.kart_mesaji([(k.soru, k.cevap) for k in kartlar])
        if not telegram.gonder(mesaj):
            print(
                "Telegram'a gönderilemedi "
                f"({telegram.TOKEN_ENV} / {telegram.CHAT_ENV} ayarlı mı?)",
                file=sys.stderr,
            )
            return 4
        ilerlet = True
    else:
        ilerlet = args.kaydet

    if ilerlet:
        for k in kartlar:
            depo.goruldu(k.id, bugun)
        depo.kaydet()
    return 0


def komut_zor(args: argparse.Namespace) -> int:
    depo = _depo(args)
    if not depo.zor(args.id, _bugun(args.bugun)):
        print(f"Hata: kart bulunamadı: {args.id}", file=sys.stderr)
        return 1
    depo.kaydet()
    print("Zor işaretlendi, yarın tekrar.")
    return 0


def komut_durum(args: argparse.Namespace) -> int:
    ozet = _depo(args).ozet(_bugun(args.bugun))
    print(f"Toplam kart: {ozet['toplam']}")
    print(f"Vadesi gelen: {ozet['vadesi_gelen']}")
    print(f"Kaynak not sayısı: {ozet['kaynak_sayisi']}")
    kutular = ", ".join(f"kutu {k}: {n}" for k, n in sorted(ozet["kutular"].items())) or "yok"
    print(f"Kutular: {kutular}")
    return 0


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tekrar", description="Vault notlarından aralıklı tekrar kartları")
    ortak = argparse.ArgumentParser(add_help=False)
    ortak.add_argument("--depo", default=None, help="kart deposu dosyası (varsayılan: ~/.tekrar/kartlar.json)")
    ortak.add_argument("--bugun", default=None, help="YYYY-MM-DD (varsayılan: bugün)")
    alt = p.add_subparsers(dest="komut", required=True)

    u = alt.add_parser("uret", parents=[ortak], help="notlardan kart üret (varsayılan ağa çıkmaz)")
    u.add_argument("vault")
    u.add_argument("--cor", action="store_true", help="notları yerel cor proxy'sine gönder")
    u.add_argument("--kuru", action="store_true", help="yalnız ne yapılacağını yaz")
    u.add_argument("--en-cok", type=int, default=20, help="en çok kaç not işlensin")
    u.add_argument("--cor-url", default=None)
    u.add_argument("--cor-model", default=None)
    u.set_defaults(isle=komut_uret)

    s = alt.add_parser("sor", parents=[ortak], help="bugünün kartlarını göster/gönder")
    s.add_argument("--adet", type=int, default=5)
    s.add_argument("--telegram", action="store_true", help="Telegram'a gönder, başarılıysa kartlar ilerler")
    s.add_argument("--kaydet", action="store_true", help="terminalde gösterilen kartları ilerlet")
    s.set_defaults(isle=komut_sor)

    z = alt.add_parser("zor", parents=[ortak], help="kartı zor işaretle")
    z.add_argument("id")
    z.set_defaults(isle=komut_zor)

    d = alt.add_parser("durum", parents=[ortak], help="depo özeti")
    d.set_defaults(isle=komut_durum)
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
    except ValueError as exc:
        print(f"Hata: geçersiz değer ({exc})", file=sys.stderr)
        return 2
    except DepoHatasi as exc:
        print(f"Hata: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
