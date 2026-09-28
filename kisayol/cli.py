"""kp — paleti seç, komutu çalıştır, tüm notlarda ara.

Bu modül yalnızca "hangi mantık" sorusunu yanıtlar; mantığın kendisi
matcher.py'de ve search.py'de saf durur. Buradaki tek sorumluluk soruyu sormak
(questionary), cevabı çalıştırmak (subprocess) ve arama sonuçlarını yazdırmaktır.

Seçim iptal edilirse (Ctrl-C / ESC) hiçbir komut çalıştırılmaz, program
sessizce 130 ile çıkar.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Sequence

import questionary

from kisayol import __version__
from kisayol.config import ConfigError, ENV_VAR, help_message, load_config
from kisayol.matcher import build_items, format_item
from kisayol.search import SearchHit, search

CANCELLED_EXIT = 130

#: Alt komutun adı — Türkçe ve kısa, `kp ara "telegram"` gibi kullanılır.
SEARCH_COMMAND = "ara"
SEARCH_HELP = "Tüm search_roots içinde tam metin arar (vault + kod repoları)."

#: `--limit` varsayılanı: 50 satır ekrana sığar, `| less` ile gezilebilir.
DEFAULT_LIMIT = 50

#: `--limit` için üst sınır: binlerce satır ekrana boşalmaktan çok yorucudur,
#: kullanıcı zaten aramayı daraltabilir.
MAX_LIMIT = 1000

#: Sonuçta gösterilen eşleşen satırın uzunluk sınırı. Minify edilmiş tek
#: satırlık bir dosyada satır yüz milyonlarca karakter olabilir: `| less`
#: kilitlenir, boruya yazılıp script'e girerse çıktı kullanılamaz hâle gelir.
#: Kırpma sonuç satırında görünür (yoksa kullanıcı eşleşmenin nerede bittiğini
#: anlamaz) ve aramanın kendisine dokunmaz — eşleşme yine tam dosyada aranır.
MAX_LINE_PREVIEW = 500


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kp",
        description="Fuzzy-search ile sık kullandığın proje/komutları bul ve çalıştır.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_only",
        help="Seçim yapmadan paleti satır satır yazdırır ve çıkar.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help=f"Config dosyası yolu (varsayılan: ${ENV_VAR} veya ~/.config/kisayol/config.yaml).",
    )
    parser.add_argument("--version", action="version", version=f"kp {__version__}")

    # `ara` bir *alt komut*: hem adı hem sorgusu ayrı ayrı konumsal olmalı.
    # argparse tek bir konumsalı ikinci kez dolduramaz, bu yüzden subparser
    # şart — `kp ara telegram` tek sözcükte "ara"ya denk gelmezdi.
    # Palet seçenekleri (`--config`, `--list`) alt komutta da kabul edilir:
    # kullanıcı `kp --config X ara <sorgu>` yazdığında olduğu gibi çalışmasın.
    subparsers = parser.add_subparsers(dest="command", metavar="{ara}")
    ara = subparsers.add_parser(
        SEARCH_COMMAND,
        help=SEARCH_HELP,
        description=SEARCH_HELP,
    )
    ara.add_argument(
        "query",
        nargs="?",
        default="",
        metavar="sorgu",
        help="Aranacak metin. Boş bırakılırsa hata verilir.",
    )
    ara.add_argument(
        "--limit",
        type=_valid_limit,
        default=DEFAULT_LIMIT,
        metavar="N",
        help=f"En fazla N sonuç yazdır (varsayılan: {DEFAULT_LIMIT}).",
    )
    ara.add_argument(
        "--no-ripgrep",
        action="store_true",
        help="rg'yi yok sayıp saf Python taramasını zorla (motor karşılaştırması için).",
    )
    _add_common_arguments(ara)

    return parser


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    """Palet seçeneklerini alt komuta da ekler, iki şekilde de yazılabilsin.

    `default=SUPPRESS` şart: argparse alt komutun varsayılanını ana komuttaki
    değerin üstüne yazar. `kp --config X ara <sorgu>` yazıldığında alt komut
    `config=None` yazar ve `--config X` sessizce kaybolurdu.
    """
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_only",
        default=argparse.SUPPRESS,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--config",
        type=Path,
        dest="config",
        default=argparse.SUPPRESS,
        help=argparse.SUPPRESS,
    )


def _valid_limit(value: str) -> int:
    """Argparse hata mesajı düzgün olsun diye limiti burada doğruluyoruz."""
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("limit pozitif bir tam sayı olmalı.")
    return min(number, MAX_LIMIT)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        config = load_config(args.config)
    except ConfigError as e:
        print(f"Hata: {e}", file=sys.stderr)
        return 1

    if args.command == SEARCH_COMMAND:
        return _search(config, args)

    items = build_items(config)

    if not items:
        print("Palet boş — çalıştırılacak hiçbir kısayol yok.", file=sys.stderr)
        print(help_message(args.config), file=sys.stderr)
        return 1

    if args.list_only:
        for item in items:
            print(format_item(item))
        return 0

    chosen = _pick(items)
    if chosen is None:
        return CANCELLED_EXIT

    return _run(chosen)


def _search(config: dict, args: argparse.Namespace) -> int:
    """`kp ara` akışı: sorguyu doğrula, tara, biçimlendir.

    Burada bilinçli olarak raise yok — boş sorgu ya da kök eksikliği kullanıcıya
    ne yapması gerektiğini söyleyen bir mesajla, çıkış kodu 1 ile döner.
    """
    query = (getattr(args, "query", "") or "").strip()
    if not query:
        print("Sorgu boş. Örnek: kp ara telegram", file=sys.stderr)
        return 1

    roots = _search_roots(config)
    if not roots:
        print("search_roots boş — aranacak dizin tanımlı değil.", file=sys.stderr)
        print("Config'e ekle (bkz. config.yaml.example):\n  search_roots:", file=sys.stderr)
        for root in ("  - ~/Mt3Ui55OS", "  - ~/projeler"):
            print(root, file=sys.stderr)
        return 1

    hits = search(query, roots, use_ripgrep=False if args.no_ripgrep else None)
    if not hits:
        print(f"'{query}' için eşleşme yok ({len(roots)} kök tarandı).", file=sys.stderr)
        return 1

    for hit in hits[: args.limit]:
        print(format_hit(hit))
    return 0


def _search_roots(config: dict) -> list[str]:
    """Config'teki arama kökleri; bozuk girdiler zaten config'de atıldı."""
    roots = config.get("search_roots")
    return [str(r) for r in roots if str(r).strip()] if isinstance(roots, list) else []


def format_hit(hit: SearchHit) -> str:
    """`[kök] /mutlak/yol.py:12: telegram botu çalıştır`

    Kök etiketi başta: kullanıcı ilk bakışta sonucun vault'tan mı repodan mı
    geldiğini görür, uzun yolun arasında aramak zorunda kalmaz.

    Satır `MAX_LINE_PREVIEW` karaktere kırpılır; aşan yer `...` ile belli olur.
    """
    line = hit.line.strip()
    if len(line) > MAX_LINE_PREVIEW:
        line = line[:MAX_LINE_PREVIEW] + "..."
    return f"[{hit.root_label}] {hit.path}:{hit.line_number}: {line}"


def _pick(items: list[dict]) -> dict | None:
    """questionary ile interaktif seçim. UI katmanı olduğu için test edilmez.

    `use_search_filter=True` yazılan her karakteri "ara" olarak bağlar ve
    listede o harf geçen item'ları tutar; `use_jk_keys=False` bunun zorunlu
    eşidir (questionary ikisini birlikte kabul etmiyor: "j/k keys can be part
    of the prefix"). `use_shortcuts` kapalı çünkü rakamlar artık arama
    karakteri; ilk 9 item'a hızlı erişim isteyen varsa liste çok uzundur.

    `ask()` seçilen `value`yi döner; choices listesine düz metin koyduğumuz
    için bu seçili etiket, `items` içindeki karşılığına geri eşlenir.
    """
    choices = [format_item(item) for item in items]
    try:
        selected = questionary.select(
            "Çalıştırılacak kısayol:",
            choices=choices,
            use_search_filter=True,
            use_jk_keys=False,
        ).ask()
    except KeyboardInterrupt:
        return None

    if selected is None:
        return None
    return items[choices.index(selected)] if selected in choices else None


def _run(item: dict) -> int:
    """Seçilen komutu cwd'sinde çalıştırır; stdio miras kalır (shell, sunucu,
    uzun süren test normal terminal gibi davranır)."""
    cwd = item.get("cwd") or None
    try:
        result = subprocess.run(item["command"], shell=True, cwd=cwd)
    except KeyboardInterrupt:
        return 130
    except OSError as e:
        print(f"Komut çalıştırılamadı ({item['command']}): {e}", file=sys.stderr)
        return 1

    if result.returncode == 0:
        return 0

    # Boru/pipe'a yazarken kullanıcı, hangi komutun neden başarısız olduğunu
    # stdout'ta göremez; oraya bir satır düşüyoruz.
    if not sys.stdout.isatty():
        print(f"'{item['command']}' {result.returncode} ile bitti.", file=sys.stderr)
    return result.returncode


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
