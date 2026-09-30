"""`danis` komut satırı arayüzü.

  danis hata <komut metni> <cikis_kodu>
  danis dosya <dosya_yolu> [soru]

Sözleşme: hata durumunda çıkış kodu HER ZAMAN 0 dışında, sessiz
başarısızlık yok. LLM'den boş/uyumsuz yanıt gelirse ham yanıt basılır.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from danis.dosya_metni import (
    BosDosyaError,
    DosyaBulunamadiError,
    DosyaTuruDesteklenmiyorError,
    IkiliDosyaError,
    metni_cikar,
)
from danis.hata_analiz import prompt_olustur, yaniti_ayikla
from danis.llm import CorLLMClient, LLMError

VARSAYILAN_SORU = "Bu dosyayı 3-5 cümleyle özetle."

# Yalnızca soru cümlesini sınırlar; dosya metni zaten MAX_KARAKTER ile kırpılıyor.
_MAX_SORU_UZUNLUK = 500


def _utf8_akislari_zorla() -> None:
    """stdout/stderr'ı UTF-8'e sabitler.

    Neden şart: Windows'ta stdout bir KONSOLA değil de bir BORUYA (yönlendirme,
    CI log toplama) bağlandığında Python ANSI kod sayfasını (varsayılan cp1252)
    kullanır. cp1252'de Türkçe noktasız "ı" (U+0131) yoktur; argparse `--help`
    metnini basarken `UnicodeEncodeError` fırlatıp süreci çökertiyordu.

    Neden `errors="replace"`: kodlanamayan bir karakter gelirse çökmek yerine
    yer tutucuyla devam et. Sessiz başarısızlık değil — asıl amaç ÇÖKMEMEK.
    """
    for akis in (sys.stdout, sys.stderr):
        if hasattr(akis, "reconfigure"):
            akis.reconfigure(encoding="utf-8", errors="replace")


def _hata_istemi(args: argparse.Namespace, client: CorLLMClient) -> int:
    ham = client.complete(prompt_olustur(args.komut, args.cikis_kodu))
    sonuc = yaniti_ayikla(ham)
    print(f"🔎 TEŞHİS: {sonuc['teshis']}")
    if sonuc["duzeltme"]:
        print(f"✅ DÜZELTME: {sonuc['duzeltme']}")
    return 0


def _dosya_istemi(args: argparse.Namespace, client: CorLLMClient) -> int:
    yol = Path(args.dosya_yolu)
    metin = metni_cikar(yol)

    soru = (args.soru or VARSAYILAN_SORU).strip()[:_MAX_SORU_UZUNLUK]
    print(client.complete(f"{soru}\n\n--- DOSYA İÇERİĞİ ---\n{metin}"))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="danis",
        description="Terminal hata asistanı ve 'bu dosyayı cor'a sor' aracı.",
    )
    alt_komutlar = parser.add_subparsers(dest="alt_komut", required=True)

    hata = alt_komutlar.add_parser("hata", help="başarısız bir komutu analiz ettir")
    hata.add_argument("komut", help="Başarısız olan komutun metni (tırnak içinde yaz)")
    hata.add_argument("cikis_kodu", type=int, help="Komutun çıkış kodu")
    hata.set_defaults(_calistir=_hata_istemi)

    dosya = alt_komutlar.add_parser("dosya", help="bir dosyanın içeriğini sor")
    dosya.add_argument("dosya_yolu", type=Path, help="txt/md/pdf/docx dosyasının yolu")
    dosya.add_argument(
        "soru", nargs="?", default=None, help=f'soru (varsayılan: "{VARSAYILAN_SORU}")'
    )
    dosya.set_defaults(_calistir=_dosya_istemi)
    return parser


def main(argv: list[str] | None = None) -> int:
    # argparse çalışmadan ÖNCE: `--help` bile Türkçe basıyor, kod sayfası
    # dar olduğunda ilk çöken yer burasıdır.
    _utf8_akislari_zorla()
    args = _parser().parse_args(argv)
    client = CorLLMClient()
    try:
        return args._calistir(args, client)
    except LLMError as exc:
        print(f"Hata: cor'a ulaşılamadı: {exc}", file=sys.stderr)
        return 1
    except DosyaBulunamadiError as exc:
        print(f"Hata: {exc}", file=sys.stderr)
        return 1
    except BosDosyaError as exc:
        print(f"Hata: {exc}", file=sys.stderr)
        return 1
    except DosyaTuruDesteklenmiyorError as exc:
        print(
            f"Hata: Bu dosya türü {exc}. Önce OCR ile metne çevirin "
            "(örn. kısayol projesi).",
            file=sys.stderr,
        )
        return 1
    except IkiliDosyaError as exc:
        print(
            f"Hata: {exc}. Bu içerik ikili; metne çevirmek için önce bir "
            "metin çıkarma aracı kullanın.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
