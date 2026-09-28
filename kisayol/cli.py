"""kp — paleti seç, komutu çalıştır.

Bu modül yalnızca "hangi mantık" sorusunu yanıtlar; mantığın kendisi
matcher.py'de saf durur. Buradaki tek sorumluluk soruyu sormak (questionary)
ve cevabı çalıştırmak (subprocess).

Seçim iptal edilirse (Ctrl-C / ESC) hiçbir komut çalıştırılmaz, program
sessizce 130 ile çıkar.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence

import questionary

from kisayol import __version__
from kisayol.config import ConfigError, ENV_VAR, help_message, load_config
from kisayol.matcher import build_items, format_item

CANCELLED_EXIT = 130


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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        config = load_config(args.config)
    except ConfigError as e:
        print(f"Hata: {e}", file=sys.stderr)
        return 1

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
