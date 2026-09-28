#!/usr/bin/env python3
"""Proje anlatı üreticisi komut satırı arayüzü.

Kullanım:
    python3 cli.py anlat <repo-yolu> [--out DOSYA.md]
    python3 cli.py sesli <repo-yolu> [--notebook-ami AD] [--out DOSYA.mp3]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from bridge.client import (
    DEFAULT_BASE_URL as BRIDGE_BASE_URL,
    DEFAULT_TIMEOUT,
    BridgeError,
    NotebookLMBridge,
    NotAuthenticatedError,
)

from generator.narrator import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    CorLLMClient,
    NarratorError,
    generate_narration,
)
from generator.scanner import ScannerError, scan_repository

DEFAULT_OUT_NAME = "ANLATI.md"
DEFAULT_AUDIO_OUT_NAME = "ANLATI.mp3"

NOT_CONNECTED_HELP = (
    "NotebookLM köprü sunucusu çalışmıyor. Önce kendi makinende ayrı bir "
    "terminalde şunları yap:\n"
    "  npm install @roomi-fields/notebooklm-mcp   # bir kerelik\n"
    "  npm run setup-auth                        # bir kerelik, tarayıcıda elle giriş\n"
    "  npm run start:http                        # her kullanımdan önce ayakta olmalı\n"
    "Köprü sunucusu çalışırken başka bir terminalde bu komutu tekrar çalıştır."
)

NOT_AUTHENTICATED_HELP = (
    "NotebookLM köprü sunucusu ayakta ama Google girişi yapılmamış. Köprü "
    "sunucusunun terminalinde `npm run setup-auth` çalıştırıp tarayıcıda elle "
    "giriş yap, sonra bu komutu tekrar dene."
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="anlat",
        description="Bir git deposunu tarayıp Türkçe teknik anlatı üretir.",
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

    sesli = subparsers.add_parser(
        "sesli", help="Yazılı anlatı üretip NotebookLM'den sesli özet (Audio Overview) indir"
    )
    sesli.add_argument("repo", help="Taranacak git deposunun yolu")
    sesli.add_argument(
        "--notebook-adi", metavar="AD", help="NotebookLM'de oluşturulacak notebook'un adı"
    )
    sesli.add_argument(
        "--out",
        metavar="DOSYA.mp3",
        help="Ses dosyasının çıktısı (varsayılan: <repo-yolu>/" + DEFAULT_AUDIO_OUT_NAME + ")",
    )
    sesli.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"cor proxy adresi (varsayılan: {DEFAULT_BASE_URL})",
    )
    sesli.add_argument(
        "--model", default=DEFAULT_MODEL, help=f"Kullanılacak model (varsayılan: {DEFAULT_MODEL})"
    )
    sesli.add_argument(
        "--bridge-url",
        default=BRIDGE_BASE_URL,
        metavar="ADRES",
        help=f"NotebookLM köprü sunucusunun adresi (varsayılan: {BRIDGE_BASE_URL})",
    )
    sesli.add_argument(
        "--dil",
        default="tr",
        metavar="KOD",
        help="Sesli özetin dili (varsayılan: tr; sunucu reddederse boş string ver)",
    )
    sesli.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        metavar="SANIYE",
        help=f"Köprü istekleri için zaman aşımı (varsayılan: {DEFAULT_TIMEOUT:.0f})",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "sesli":
        return run_sesli(args)
    return run_anlat(args)


def run_anlat(args: argparse.Namespace) -> int:
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


def run_sesli(args: argparse.Namespace) -> int:
    print("[1/6] NotebookLM köprü sunucusu kontrol ediliyor...")
    bridge = NotebookLMBridge(base_url=args.bridge_url, timeout=args.timeout)
    try:
        _check_bridge(bridge)
    except NotAuthenticatedError as exc:
        # BridgeError'ın alt sınıfı olduğu için önce bu yakalanmalı.
        print(f"Hata: {exc}", file=sys.stderr)
        print(NOT_AUTHENTICATED_HELP, file=sys.stderr)
        return 1
    except BridgeError as exc:
        # Yarım iş yapmayalım: köprü hazır değilse daha ilk adımda dur.
        print(f"Hata: {exc}", file=sys.stderr)
        print(NOT_CONNECTED_HELP, file=sys.stderr)
        return 1
    print(f"      Köprü hazır: {bridge.base_url}")

    try:
        scan = scan_repository(args.repo)
    except ScannerError as exc:
        print(f"Hata: {exc}", file=sys.stderr)
        return 1

    print(
        f"[2/6] {scan.repo_name}: {len(scan.commits)} commit, "
        f"{len(scan.dependency_files)} bağımlılık dosyası, "
        f"{len(scan.documents)} doküman tarandı."
    )

    client = CorLLMClient(base_url=args.base_url, model=args.model)
    try:
        result = generate_narration(scan, client)
    except NarratorError as exc:
        print(f"Hata: {exc}", file=sys.stderr)
        return 1

    # Yazılı anlatıyı da kaydediyoruz: NotebookLM'e giden metnin aynısı.
    written = scan.repo_path / DEFAULT_OUT_NAME
    written.parent.mkdir(parents=True, exist_ok=True)
    written.write_text(result.markdown + "\n", encoding="utf-8")
    print(f"[3/6] Yazılı anlatı üretildi ({result.model}): {written}")

    notebook_name = args.notebook_adi or f"{scan.repo_name} — teknik anlatı"
    instructions = (
        "Bu kaynak bir yazılım projesinin teknik anlatısı. Özellikle teknoloji "
        "seçimlerinin gerekçelerine, önemli tasarım kararlarına ve projenin "
        "zaman çizelgesine vurgu yap; iki konuşmacı birbirine katılsın."
    )

    try:
        print(f"[4/6] NotebookLM'de notebook oluşturuluyor: {notebook_name}")
        notebook_url = bridge.create_notebook(notebook_name)

        print(
            f"[5/6] Anlatı notebook'a kaynak olarak ekleniyor "
            f"({len(result.markdown)} karakter)..."
        )
        bridge.add_text_source(
            notebook_url, result.markdown, f"{scan.repo_name} teknik anlatısı"
        )

        print(
            "[6/6] Sesli özet (Audio Overview) üretiliyor. Bu işlem birkaç dakika "
            "sürebilir, sabırla bekleyin..."
        )
        bridge.generate_audio_overview(
            notebook_url, custom_instructions=instructions, language=args.dil.strip() or None
        )
    except BridgeError as exc:
        print(f"Hata: {exc}", file=sys.stderr)
        return 1

    out_path = Path(args.out) if args.out else scan.repo_path / DEFAULT_AUDIO_OUT_NAME
    try:
        saved = bridge.download_audio_overview(notebook_url, out_path)
    except BridgeError as exc:
        print(f"Hata: {exc}", file=sys.stderr)
        return 1

    print(f"Sesli anlatı indirildi: {saved} ({saved.stat().st_size} bayt)")
    print(f"NotebookLM notebook'u: {notebook_url}")
    return 0


def _check_bridge(bridge: NotebookLMBridge) -> None:
    """Köprü ayakta ve giriş yapılmış değilse `BridgeError`/`NotAuthenticatedError` yükseltir."""
    payload = bridge.health()
    if not payload.get("success"):
        error = payload.get("error")
        raise BridgeError(
            f"Köprü sağlık kontrolü başarısız: {error}"
            if error
            else "Köprü sağlık kontrolü başarısız."
        )
    if not bridge.is_authenticated():
        raise NotAuthenticatedError("Köprü ayakta ama Google girişi yapılmamış.")


if __name__ == "__main__":
    raise SystemExit(main())
