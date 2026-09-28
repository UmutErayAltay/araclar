#!/usr/bin/env python3
"""Proje anlatı üreticisi komut satırı arayüzü.

Kullanım:
    python3 cli.py anlat <repo-yolu> [--out DOSYA.md]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from generator.narrator import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    CorLLMClient,
    NarratorError,
    generate_narration,
)
from generator.scanner import ScannerError, scan_repository

DEFAULT_OUT_NAME = "ANLATI.md"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="anlat",
        description="Bir git deposunu tarayıp Türkçe yazılı teknik anlatı üretir.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    anlat = subparsers.add_parser("anlat", help="Bir repo için anlatı üret")
    anlat.add_argument("repo", help="Taranacak git deposunun yolu")
    anlat.add_argument(
        "--out",
        metavar="DOSYA.md",
        help="Çıktı dosyası (varsayılan: <repo-yolu>/" + DEFAULT_OUT_NAME + ")",
    )
    anlat.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"cor proxy adresi (varsayılan: {DEFAULT_BASE_URL})",
    )
    anlat.add_argument(
        "--model", default=DEFAULT_MODEL, help=f"Kullanılacak model (varsayılan: {DEFAULT_MODEL})"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        scan = scan_repository(args.repo)
    except ScannerError as exc:
        print(f"Hata: {exc}", file=sys.stderr)
        return 1

    print(
        f"{scan.repo_name}: {len(scan.commits)} commit, "
        f"{len(scan.dependency_files)} bağımlılık dosyası, "
        f"{len(scan.documents)} doküman tarandı."
    )

    client = CorLLMClient(base_url=args.base_url, model=args.model)
    try:
        result = generate_narration(scan, client)
    except NarratorError as exc:
        print(f"Hata: {exc}", file=sys.stderr)
        return 1

    out_path = Path(args.out) if args.out else scan.repo_path / DEFAULT_OUT_NAME
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(result.markdown + "\n", encoding="utf-8")

    print(f"Anlatı üretildi ({result.model}): {out_path}")
    print(f"{len(result.markdown)} karakter yazıldı.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
