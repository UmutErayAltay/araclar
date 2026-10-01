"""portfolyo komut satırı: kontrol / uret.

Çıkış kodları: 0 başarı, 2 yapılandırma/kullanım hatası, 4 sızıntı denetimi bulgu verdi.
Ağ kullanılmaz; yalnız yapılandırmada listelenen (ve `herkese_acik: true` işaretli)
repolar işlenir. Çıktıya yerel yollar yazılmaz.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from . import denetim, git, html
from .ayar import Ayar, AyarHatasi, ayar_oku


def _bugun(deger: str | None) -> date:
    return date.fromisoformat(deger) if deger else date.today()


def _veriler(ayar: Ayar, bugun: date) -> dict[str, object | None]:
    """Her repo için klon varsa git verisini toplar (yoksa/okunamazsa None)."""
    veriler: dict[str, object | None] = {}
    for repo in ayar.repolar:
        veriler[repo.ad] = (
            git.repo_verisi(Path(repo.klon), bugun, readme=repo.readme) if repo.klon else None
        )
    return veriler


def komut_kontrol(args: argparse.Namespace) -> int:
    ayar = ayar_oku(Path(args.ayar))
    print(f"Yapılandırma geçerli: {len(ayar.repolar)} repo, hepsi herkese_acik: true.")
    for repo in ayar.repolar:
        durum = "klon tanımlı" if repo.klon else "klon yok (yalnız yapılandırma metni)"
        print(f"  {repo.ad}: {durum}")
    return 0


def komut_uret(args: argparse.Namespace) -> int:
    ayar = ayar_oku(Path(args.ayar))
    bugun = _bugun(args.bugun)
    veriler = _veriler(ayar, bugun)

    for repo in ayar.repolar:
        if repo.klon and veriler[repo.ad] is None:
            print(f"UYARI: {repo.ad}: klon okunamadı, yalnız yapılandırma metni kullanılacak.", file=sys.stderr)

    sayfa = html.render(ayar, veriler, bugun)
    bulgular = denetim.tara(sayfa)
    if bulgular:
        print("Hata: sızıntı denetimi bulgu verdi, hiçbir dosya yazılmadı:", file=sys.stderr)
        for b in bulgular:
            print(f"  [{b.tur}] {b.ornek}", file=sys.stderr)
        return 4

    if args.kuru:
        print(f"Kuru çalışma: {len(ayar.repolar)} repo, {len(sayfa)} karakterlik sayfa, denetim temiz. Yazılmadı.")
        return 0

    cikti = Path(args.cikti)
    cikti.mkdir(parents=True, exist_ok=True)
    (cikti / "index.html").write_text(sayfa, encoding="utf-8")
    (cikti / ".nojekyll").write_text("", encoding="utf-8")
    print(f"Yazıldı: index.html ({len(ayar.repolar)} repo). Denetim temiz.")
    return 0


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="portfolyo", description="Allowlist'li statik portfolyo üreticisi")
    alt = p.add_subparsers(dest="komut", required=True)

    k = alt.add_parser("kontrol", help="yapılandırmayı doğrula (dosya yazmaz)")
    k.add_argument("ayar")
    k.set_defaults(isle=komut_kontrol)

    u = alt.add_parser("uret", help="index.html üret")
    u.add_argument("ayar")
    u.add_argument("--cikti", required=True, help="çıktı klasörü (index.html + .nojekyll yazılır)")
    u.add_argument("--bugun", default=None, help="YYYY-MM-DD (varsayılan: bugün)")
    u.add_argument("--kuru", action="store_true", help="denetle ama dosya yazma")
    u.set_defaults(isle=komut_uret)
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
    except AyarHatasi as exc:
        print(f"Hata: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"Hata: geçersiz değer ({exc})", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"Hata: dosya işlemi başarısız ({exc.strerror or exc.__class__.__name__})", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
