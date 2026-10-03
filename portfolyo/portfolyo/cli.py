"""portfolyo komut satırı: kontrol / uret.

Çıkış kodları: 0 başarı, 2 yapılandırma/kullanım hatası, 4 sızıntı denetimi bulgu verdi,
5 `--siki` modunda bir repo için veri alınamadı.
Ağa yalnız `veri: "api"` olan repolar (ya da `--api`) için ve yalnız sabit konak
api.github.com'a çıkılır. Yalnız yapılandırmada listelenen (ve `herkese_acik: true`
işaretli) repolar işlenir. Çıktıya yerel yollar ve token yazılmaz.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path

from . import denetim, feed, git, githubapi, html, og, yazi
from .ayar import Ayar, AyarHatasi, ayar_oku


def _bugun(deger: str | None) -> date:
    return date.fromisoformat(deger) if deger else date.today()


def _veri_kaynagi(repo, api_bayragi: bool) -> str:
    """Repo `veri` ayarı "yok" iken `--api` bayrağı onu API'ye çevirir; klon/api tercihi korunur."""
    return "api" if repo.veri == "yok" and api_bayragi else repo.veri


def _veriler(ayar: Ayar, bugun: date, api_bayragi: bool = False) -> dict[str, object | None]:
    """Her repo için veriyi toplar (klon ya da GitHub API; olmazsa/okunamazsa None)."""
    token = os.environ.get("GITHUB_TOKEN") or None
    veriler: dict[str, object | None] = {}
    for repo in ayar.repolar:
        kaynak = _veri_kaynagi(repo, api_bayragi)
        if kaynak == "klon" and repo.klon:
            veriler[repo.ad] = git.repo_verisi(Path(repo.klon), bugun, readme=repo.readme)
        elif kaynak == "api":
            veriler[repo.ad] = githubapi.repo_verisi_api(
                ayar.sahip.github, repo.ad, token=token, readme=repo.readme
            )
        else:
            veriler[repo.ad] = None
    return veriler


def komut_kontrol(args: argparse.Namespace) -> int:
    ayar = ayar_oku(Path(args.ayar))
    print(f"Yapılandırma geçerli: {len(ayar.repolar)} repo, hepsi herkese_acik: true.")
    for repo in ayar.repolar:
        durum = {
            "klon": "yerel klon",
            "api": "GitHub API",
            "yok": "veri yok (yalnız yapılandırma metni)",
        }[_veri_kaynagi(repo, getattr(args, "api", False))]
        print(f"  {repo.ad} [{repo.kategori}]: {durum}")
    return 0


def komut_uret(args: argparse.Namespace) -> int:
    ayar = ayar_oku(Path(args.ayar))
    bugun = _bugun(args.bugun)
    veriler = _veriler(ayar, bugun, args.api)

    eksikler: list[str] = []
    for repo in ayar.repolar:
        kaynak = _veri_kaynagi(repo, args.api)
        if kaynak != "yok" and veriler[repo.ad] is None:
            ne = "klon" if kaynak == "klon" else "GitHub verisi"
            print(f"UYARI: {repo.ad}: {ne} okunamadı, yalnız yapılandırma metni kullanılacak.", file=sys.stderr)
            eksikler.append(repo.ad)

    if args.siki and eksikler:
        # Sıkı mod (haftalık yayın): yeniden adlandırılmış/silinmiş/özel yapılmış repo ya da API hatası
        # sessizce kartsız yayınlanmasın; hiçbir şey yazılmaz, eski site yerinde kalır.
        print(
            f"Hata: --siki: {len(eksikler)} repo için veri alınamadı ({', '.join(eksikler)}); hiçbir dosya yazılmadı.",
            file=sys.stderr,
        )
        return 5

    yazilar: list[yazi.Yazi] = []
    if args.yazilar:
        klasor = Path(args.yazilar)
        if not klasor.is_dir():
            print("Hata: yazılar klasörü bulunamadı", file=sys.stderr)
            return 2
        try:
            yazilar, taslaklar = yazi.yazilari_oku(klasor)
        except yazi.YaziHatasi as exc:
            print(f"Hata: yazı: {exc}", file=sys.stderr)
            return 2
        for ad in taslaklar:
            print(f"Bilgi: {ad}: herkese_acik: true değil, yayınlanmadı.", file=sys.stderr)

    # Yazılacak TÜM sayfalar (göreli yol -> içerik); denetim hepsinden geçmeden hiçbiri yazılmaz.
    sayfalar = _sayfalar(ayar, veriler, bugun, yazilar, {})
    bulgular = _denetle(sayfalar, ayar.sahip.eposta)
    if bulgular:
        _bulgu_yaz(bulgular)
        return 4

    toplam = sum(len(s) for s in sayfalar.values())
    if args.kuru:
        print(f"Kuru çalışma: {len(ayar.repolar)} repo, {len(yazilar)} yazı, {toplam} karakter, denetim temiz. Yazılmadı.")
        return 0

    # Paylaşım görselleri: yalnız ilk denetimden SONRA üretilir; başarılı olanlar sayfaya bağlanır.
    gecici_png = tempfile.TemporaryDirectory(prefix="portfolyo-png-")
    try:
        pngler: dict[str, Path] = {}
        if args.og_gorsel:
            pngler = _og_uret(ayar, yazilar, Path(gecici_png.name))
        if pngler:
            og_url = {sayfa: html.sayfa_url(ayar, f"og/{png.name}") for sayfa, png in pngler.items()}
            sayfalar = _sayfalar(ayar, veriler, bugun, yazilar, og_url)
            bulgular = _denetle(sayfalar, ayar.sahip.eposta)  # son çıktı da kapıdan geçer
            if bulgular:
                _bulgu_yaz(bulgular)
                return 4

        cikti = Path(args.cikti)
        for yol, icerik in sayfalar.items():
            hedef = cikti / yol
            hedef.parent.mkdir(parents=True, exist_ok=True)
            hedef.write_text(icerik, encoding="utf-8")
        for png in pngler.values():
            (cikti / "og").mkdir(parents=True, exist_ok=True)
            shutil.copyfile(png, cikti / "og" / png.name)
        (cikti / ".nojekyll").write_text("", encoding="utf-8")
    finally:
        gecici_png.cleanup()
    ek = f", {len(pngler)} paylaşım görseli" if pngler else ""
    print(f"Yazıldı: index.html ({len(ayar.repolar)} repo) + {len(yazilar)} yazı sayfası{ek}. Denetim temiz.")
    return 0


def _sayfalar(ayar: Ayar, veriler, bugun: date, yazilar, og: dict[str, str]) -> dict[str, str]:
    besleme = feed.atom_uret(ayar, yazilar)
    sayfalar = {"index.html": html.render(ayar, veriler, bugun, yazilar, og_gorsel=og.get("index.html"), feed=bool(besleme))}
    for i, y in enumerate(yazilar):  # yazilar tarih azalan: i-1 daha yeni, i+1 daha eski
        yol = f"yazilar/{y.slug}.html"
        sayfalar[yol] = html.render_yazi(
            ayar, y, bugun, og_gorsel=og.get(yol),
            onceki=yazilar[i + 1] if i + 1 < len(yazilar) else None,
            sonraki=yazilar[i - 1] if i > 0 else None,
            feed=bool(besleme),
        )
    if besleme:
        sayfalar["feed.xml"] = besleme
    return sayfalar


def _denetle(sayfalar: dict[str, str], izinli_eposta: str = "") -> list:
    """Sızıntı denetimi. `izinli_eposta` (yapılandırmadaki kendi e-postası) bulgu sayılmaz."""
    izinli = [izinli_eposta] if izinli_eposta else []
    bulgular = []
    for yol, icerik in sayfalar.items():
        bulgular += [(yol, b) for b in
                     denetim.tara(icerik, izinli, link_denetimi=not yol.endswith(".xml"))]
    return bulgular


def _bulgu_yaz(bulgular: list) -> None:
    print("Hata: sızıntı denetimi bulgu verdi, hiçbir dosya yazılmadı:", file=sys.stderr)
    for yol, b in bulgular:
        print(f"  {yol}: [{b.tur}] {b.ornek}", file=sys.stderr)


def _og_uret(ayar: Ayar, yazilar, hedef: Path) -> dict[str, Path]:
    """Sayfa yolu -> üretilmiş PNG. `site_url` ya da tarayıcı yoksa uyarıp boş döner (hiç bozuk referans yok)."""
    if not ayar.sahip.site_url:
        print("UYARI: --og-gorsel için sahip.site_url gerekli (mutlak URL); görsel üretilmedi.", file=sys.stderr)
        return {}
    if og.tarayici_bul() is None:
        print("UYARI: Chrome/Chromium bulunamadı; paylaşım görseli üretilmedi.", file=sys.stderr)
        return {}
    isler = {"index.html": ("site.png", og.kart_html(ayar.sahip.ad, ayar.sahip.unvan, ayar.sahip.ad[:1]))}
    for y in yazilar:
        isler[f"yazilar/{y.slug}.html"] = (
            f"{y.slug}.png",
            og.kart_html(y.baslik, f"{ayar.sahip.ad} · {y.tarih}", ayar.sahip.ad[:1]),
        )
    sonuc: dict[str, Path] = {}
    for sayfa, (ad, kart) in isler.items():
        png = hedef / ad
        if og.png_uret(kart, png):
            sonuc[sayfa] = png
        else:
            print(f"UYARI: {ad} üretilemedi; o sayfa görselsiz kalacak.", file=sys.stderr)
    return sonuc


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="portfolyo", description="Allowlist'li statik portfolyo üreticisi")
    alt = p.add_subparsers(dest="komut", required=True)

    k = alt.add_parser("kontrol", help="yapılandırmayı doğrula (dosya yazmaz)")
    k.add_argument("ayar")
    k.add_argument("--api", action="store_true", help="`veri` belirtilmeyen repolar API'den okunur varsay")
    k.set_defaults(isle=komut_kontrol)

    u = alt.add_parser("uret", help="index.html üret")
    u.add_argument("ayar")
    u.add_argument("--cikti", required=True, help="çıktı klasörü (index.html + .nojekyll yazılır)")
    u.add_argument("--bugun", default=None, help="YYYY-MM-DD (varsayılan: bugün)")
    u.add_argument("--kuru", action="store_true", help="denetle ama dosya yazma")
    u.add_argument("--yazilar", default=None, help="yazı klasörü (*.md; yalnız herkese_acik: true olanlar yayınlanır)")
    u.add_argument("--og-gorsel", action="store_true", help="paylaşım görselleri (og/*.png) üret; Chrome/Chromium ve sahip.site_url gerekir")
    u.add_argument("--siki", action="store_true", help="veri alınamayan repo olursa hata ver (çıkış 5), hiçbir şey yazma")
    u.add_argument("--api", action="store_true", help="`veri` belirtilmeyen repolar için GitHub API'sini kullan")
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
