#!/usr/bin/env python3
"""Kaynak `corclient.py`'yi tüketici repolara yazan senkron aracı.

Kullanım:
    python3 tools/sync.py YOL [YOL ...]            # yaz
    python3 tools/sync.py --check YOL [YOL ...]     # doğrula, sapma varsa 1
    python3 tools/sync.py --hepsi                   # repodaki TÜM <proje>/<paket>/_corclient.py'leri yaz
    python3 tools/sync.py --check --hepsi           # hepsini doğrula

Her hedefe, kaynağın BAYTLARI DEĞİŞTİRİLMEDEN, üstüne tek bir senkron
başlığı eklenerek yazılır:

    # SENKRON corclient surum=<__surum__> sha256=<kaynak baytlarının sha256'sı>

Hedef yollar koda GÖMÜLMEZ; yalnızca komut satırı argümanıdır (yerel yol
sızıntısı olmaz). `--check` üç bozulmayı yakalar: başlık yok, gövde elle
düzenlenmiş (sha256 tutmuyor), sürüm eski (sha256 bu repodaki güncel kaynakla
tutmuyor).
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
KAYNAK = KOK / "corclient.py"

BASLIK_IZARETI = "# SENKRON corclient surum="
BASLIK_DESENI = re.compile(
    r"^# SENKRON corclient surum=(?P<surum>\S+) sha256=(?P<sha256>[0-9a-f]{64})$"
)


def kaynak_surum() -> str:
    """Kaynak dosyanın `__surum__` değisi (import etmeden, metin olarak)."""
    for satir in KAYNAK.read_text(encoding="utf-8").splitlines():
        satir = satir.strip()
        if satir.startswith("__surum__"):
            deger = satir.split("=", 1)[1].strip().strip("\"'")
            return deger
    raise SystemExit(f"kaynakta __surum__ bulunamadı: {KAYNAK}")


def _lf(veri: bytes) -> bytes:
    """Satır sonlarını LF'ye indirir: Windows'ta `git autocrlf` kopyayı CRLF'ye
    çevirse de sha256 tutsun (hash yalnız LF biçimi üzerinden hesaplanır)."""
    return veri.replace(b"\r\n", b"\n")


def kaynak_govde() -> bytes:
    """Başlığın üstüne eklenecek kaynak BAYTLARI (LF biçiminde)."""
    return _lf(KAYNAK.read_bytes())


def govde_sha256(veri: bytes) -> str:
    return hashlib.sha256(veri).hexdigest()


def baslik_uret(surum: str, sha256: str) -> str:
    return f"{BASLIK_IZARETI}{surum} sha256={sha256}\n"


def _oku(yol: Path) -> bytes:
    if not yol.is_file():
        raise ValueError(f"dosya yok: {yol}")
    return yol.read_bytes()


def kontrol(yol: Path, beklenen_surum: str, beklenen_sha256: str) -> str | None:
    """`yol` sapmadaysa `None`, sapma varsa insan-okur açıklama döner."""
    try:
        ham = _oku(yol)
    except ValueError as hata:
        return str(hata)

    satirlar = _lf(ham).split(b"\n")
    if not satirlar or not satirlar[0].startswith(BASLIK_IZARETI.encode("utf-8")):
        return "senkron başlığı yok"

    eslesme = BASLIK_DESENI.match(satirlar[0].decode("utf-8", errors="replace"))
    if eslesme is None:
        return f"senkron başlığı bozuk: {satirlar[0].decode('utf-8', errors='replace')!r}"

    govde = b"\n".join(satirlar[1:])
    kayitli = eslesme.group("sha256")
    if govde_sha256(govde) != kayitli:
        return "gövde elle düzenlenmiş (başlıktaki sha256 gövdeyle tutmuyor)"
    if kayitli != beklenen_sha256:
        return (
            f"eski sürüm (başlıkta surum={eslesme.group('surum')}, "
            f"beklenen surum={beklenen_surum})"
        )
    return None


def yaz(yol: Path, surum: str, sha256: str, govde: bytes) -> None:
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_bytes(baslik_uret(surum, sha256).encode("utf-8") + govde)


def tum_kopyalar() -> list[Path]:
    """Bu repodaki tüm `_corclient.py` kopyaları (`<proje>/<paket>/_corclient.py`)."""
    return sorted(KOK.glob("*/*/_corclient.py"))


def main(argv: list[str] | None = None) -> int:
    ayristirici = argparse.ArgumentParser(
        prog="sync.py",
        description="corclient.py kaynağını tüketici repolara yaz / doğrula.",
    )
    ayristirici.add_argument(
        "--check",
        action="store_true",
        help="yazma; sapma varsa 1 döndür",
    )
    ayristirici.add_argument(
        "--hepsi",
        action="store_true",
        help="bu repodaki tüm <proje>/<paket>/_corclient.py dosyalarını hedef al",
    )
    ayristirici.add_argument("yollar", nargs="*", help="hedef _corclient.py yolu")
    args = ayristirici.parse_args(argv)
    if args.hepsi:
        args.yollar = [*args.yollar, *(str(y) for y in tum_kopyalar())]
    if not args.yollar:
        ayristirici.error("hedef yol ver ya da --hepsi kullan")

    if not KAYNAK.is_file():
        print(f"HATA: kaynak bulunamadı: {KAYNAK}", file=sys.stderr)
        return 2

    surum = kaynak_surum()
    govde = kaynak_govde()
    sha256 = govde_sha256(govde)

    kod = 0
    for ham_yol in args.yollar:
        yol = Path(ham_yol)
        if args.check:
            sorun = kontrol(yol, surum, sha256)
            if sorun is None:
                print(f"OK   {yol}")
            else:
                print(f"SAPMA {yol}: {sorun}", file=sys.stderr)
                kod = 1
        else:
            yaz(yol, surum, sha256, govde)
            print(f"YAZILDI {yol} (surum={surum} sha256={sha256})")
    return kod


if __name__ == "__main__":
    raise SystemExit(main())
