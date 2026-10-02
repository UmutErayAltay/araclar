#!/usr/bin/env python3
"""Üreticiyi (portfolyo) site reposuna `generator/` olarak kopyalar (vendoring).

Kullanım:
    python3 tools/portfolyo_yayinla.py SITE_KLONU           # kopyala, KAYNAK.txt'yi güncelle
    python3 tools/portfolyo_yayinla.py --check SITE_KLONU   # yazmadan karşılaştır, fark varsa 1

Kopyalananlar: `portfolyo/portfolyo/*.py` -> `generator/portfolyo/`, `portfolyo/tests/*.py` -> `generator/tests/`.
Kaynakta artık olmayan `.py` dosyaları hedeften kaldırılır (yalnız bu iki klasörde). Araç COMMIT/PUSH
YAPMAZ; farkı gözden geçirip sen (ya da ben) commit'lersin. Hedef yol koda gömülmez, yalnız argümandır.
Yanlış klasöre yazmamak için hedefte `portfolyo.json` bulunmalıdır.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
ESLEME = (
    (Path("portfolyo") / "portfolyo", Path("generator") / "portfolyo"),
    (Path("portfolyo") / "tests", Path("generator") / "tests"),
)


def kaynak_sha(kok: Path = KOK) -> str:
    try:
        sonuc = subprocess.run(
            ["git", "-C", str(kok), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=20, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return "bilinmiyor"
    sha = sonuc.stdout.strip()
    return sha if sonuc.returncode == 0 and len(sha) == 40 else "bilinmiyor"


def _kaynak_metni(sha: str) -> str:
    return (
        "Bu klasör, üretici kaynak kodunun kopyasıdır (vendoring). Düzenleme yapma; kaynakta değiştir, buraya yeniden kopyala.\n\n"
        "kaynak:   araclar/portfolyo/{portfolyo,tests}/*.py   (özel depo)\n"
        f"commit:   {sha}\n"
        "kopyalama: python3 tools/portfolyo_yayinla.py <bu-reponun-klonu>\n"
        "çalıştırma: PYTHONPATH=generator python -m portfolyo uret portfolyo.json --api --siki --og-gorsel --yazilar yazilar --cikti _site\n"
        "test:      PYTHONPATH=generator python -m pytest generator/tests -q\n"
    )


def kopyala(site: Path, *, yaz: bool = True, kok: Path = KOK) -> dict[str, list[str]]:
    """Fark özetini döndürür: {"yeni": [...], "guncel": [...], "ayni": [...], "silinen": [...]} (göreli yollar)."""
    if not (site / "portfolyo.json").is_file():
        raise SystemExit("Hata: hedefte portfolyo.json yok; doğru site klonu mu?")
    ozet: dict[str, list[str]] = {"yeni": [], "guncel": [], "ayni": [], "silinen": []}
    for kaynak_rel, hedef_rel in ESLEME:
        kaynak, hedef = kok / kaynak_rel, site / hedef_rel
        dosyalar = sorted(kaynak.glob("*.py"))
        adlar = {d.name for d in dosyalar}
        for d in dosyalar:
            h = hedef / d.name
            rel = (hedef_rel / d.name).as_posix()
            if not h.is_file():
                ozet["yeni"].append(rel)
            elif h.read_bytes() != d.read_bytes():
                ozet["guncel"].append(rel)
            else:
                ozet["ayni"].append(rel)
                continue
            if yaz:
                hedef.mkdir(parents=True, exist_ok=True)
                h.write_bytes(d.read_bytes())
        if hedef.is_dir():
            for h in sorted(hedef.glob("*.py")):
                if h.name not in adlar:
                    ozet["silinen"].append((hedef_rel / h.name).as_posix())
                    if yaz:
                        h.unlink()
    if yaz:
        (site / "generator").mkdir(parents=True, exist_ok=True)
        (site / "generator" / "KAYNAK.txt").write_text(_kaynak_metni(kaynak_sha(kok)), encoding="utf-8")
    return ozet


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("site", help="site reposunun yerel klonu")
    p.add_argument("--check", action="store_true", help="yazma; fark varsa 1 döndür")
    args = p.parse_args(argv)
    ozet = kopyala(Path(args.site), yaz=not args.check)
    fark = bool(ozet["yeni"] or ozet["guncel"] or ozet["silinen"])
    print(f"yeni {len(ozet['yeni'])}, güncellenen {len(ozet['guncel'])}, aynı {len(ozet['ayni'])}, silinen {len(ozet['silinen'])}")
    for anahtar in ("yeni", "guncel", "silinen"):
        for rel in ozet[anahtar]:
            print(f"  {anahtar}: {rel}")
    if args.check:
        return 1 if fark else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
