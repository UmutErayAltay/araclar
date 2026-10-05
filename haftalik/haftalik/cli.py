"""haftalik komut satiri: uret.

Cikis kodlari: 0 basari, 1 cor erisilemedi / ozet uretilemedi, 2 kullanim hatasi.
Guvenlik: toplama SALT-OKUNURDUR (yalniz `git log`). Dosya YAZMA yalniz acik
`--cikti` bayragiyla olur ve mevcut bir dosyanin UZERINE yazmaz.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import ozet as ozet_modul
from . import telegram
from .topla import RepoHatasi, tarih_araligi, topla

KULLANIM_HATASI = 2
OZET_YOK = 1


def _yaz(cikti_yolu: str | None, metin: str) -> None:
    """`--cikti` verilmişse dosyaya yazar (VAR OLMAYAN dosyaya; üzerine yazmaz),
    verilmemişse stdout'a basar."""
    if not cikti_yolu:
        print(metin)
        return
    yol = Path(cikti_yolu)
    if yol.exists():
        raise RepoHatasi(f"çıktı dosyası zaten var, üzerine yazılmadı: {yol}")
    yol.write_text(metin, encoding="utf-8")
    print(f"yazıldı: {yol}", file=sys.stderr)


def _telegram_gonder(ozet: str) -> int | None:
    """Özeti Telegram'a gönderir; gönderilen mesaj sayısını döner.

    Ortam değişkenleri eksikse `RepoHatasi` verir; `main` bunu `Hata: ...` olarak
    basıp çıkış kodu 2 ile döner. Gönderim başarısızsa `None` döner.
    """
    eksik = [ad for ad in (telegram.TOKEN_ENV, telegram.CHAT_ENV) if not os.environ.get(ad)]
    if eksik:
        raise RepoHatasi(
            "--telegram için ortam değişkenleri ayarlı değil: " + ", ".join(eksik)
        )
    mesajlar = telegram.ozet_mesajlari(ozet)
    for mesaj in mesajlar:
        if not telegram.gonder(mesaj):
            return None
    return len(mesajlar)


def _komut_uret(args: argparse.Namespace) -> int:
    ozetler = topla([Path(k) for k in args.kok], args.gun)
    bas, bitis = tarih_araligi(args.gun)
    aralik = f"{bas}..{bitis}"

    if args.sadece_topla:
        # LLM'e HIC gitmeden toplanan veriyi bas.
        _yaz(args.cikti, ozet_modul.ham_markdown(ozetler, aralik, args.gun))
        return 0

    if not ozetler:
        print(
            f"Hata: son {args.gun} günde commit'i olan repo yok "
            "(--sadece-topla ile ham raporu görebilirsin).",
            file=sys.stderr,
        )
        return OZET_YOK

    from . import llm

    try:
        istemci = llm.CorLLMClient(
            base_url=args.cor_url or llm.DEFAULT_BASE_URL,
            model=args.model or llm.DEFAULT_MODEL,
        )
        yanit = istemci.complete(ozet_modul.prompt_olustur(ozetler, aralik))
    except llm.LLMError as exc:
        # Ham veri bir dosyaya YAZILMAZ; yalnız hata. (--sadece-topla her zaman çalışır.)
        if "bağlanılamadı" in str(exc):
            print("Hata: cor proxy'sine bağlanılamadı (cor start)", file=sys.stderr)
        else:
            print(f"Hata: {exc}", file=sys.stderr)
        return OZET_YOK

    ozet = ozet_modul.ozeti_temizle(yanit, aralik)
    if not ozet:
        print("Hata: cor boş özet döndürdü.", file=sys.stderr)
        return OZET_YOK

    if args.telegram:
        adet = _telegram_gonder(ozet)
        if adet is None:
            print(
                "Hata: Telegram'a gönderilemedi "
                f"({telegram.TOKEN_ENV} / {telegram.CHAT_ENV} ayarlı mı?)",
                file=sys.stderr,
            )
            return OZET_YOK
        print(f"Telegram'a gönderildi ({adet} mesaj).", file=sys.stderr)
        if not args.cikti:
            return 0

    _yaz(args.cikti, ozet + "\n")
    return 0


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="haftalik",
        description="Coklu repodaki son N gunun commit'lerini toplayip yerel cor "
                    "LLM'i ile Turkce haftalik ozete cevirir",
    )
    alt = p.add_subparsers(dest="komut", required=True)

    u = alt.add_parser("uret", help="commit'leri topla ve haftalik ozet uret")
    u.add_argument("--kok", action="append", default=[], metavar="DIZIN", required=True,
                   help="taranacak kok dizin (birden fazla verilebilir)")
    u.add_argument("--gun", type=int, default=7,
                   help="son kac gun bakilacak (varsayilan: 7)")
    u.add_argument("--cikti", default=None, metavar="DOSYA.md",
                   help="ozeti bu dosyaya yaz (dosya varsa UZERINE yazilmaz)")
    u.add_argument("--model", default=None,
                   help="cor modeli (varsayilan: COR_MODEL ya da stealth/space-bunny-alpha)")
    u.add_argument("--cor-url", default=None,
                   help="cor adresi (varsayilan: COR_BASE_URL ya da http://127.0.0.1:8787)")
    u.add_argument("--sadece-topla", action="store_true",
                   help="LLM'e gitmeden toplanan veriyi Markdown olarak bas")
    u.add_argument("--telegram", action="store_true", help="ozeti Telegram'a gonder")
    u.set_defaults(isle=_komut_uret)
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
    except RepoHatasi as exc:
        print(f"Hata: {exc}", file=sys.stderr)
        return KULLANIM_HATASI
    except ValueError as exc:
        print(f"Hata: geçersiz değer ({exc})", file=sys.stderr)
        return KULLANIM_HATASI


if __name__ == "__main__":
    raise SystemExit(main())
