"""Tek dosyalık statik portfolyo HTML üreticisi.

JavaScript yok, dış kaynak (font/CDN/analitik) yok. CSP meta etiketiyle kilitli.
Sistem font yığını, açık/koyu tema, CSS Grid kart ızgarası, SVG etkinlik grafiği.
"""

from __future__ import annotations

import html
import urllib.parse
from collections.abc import Mapping, Sequence
from datetime import date

from .denetim import tara


# CSP: default-src 'none'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'
_CSP = (
    "default-src 'none'; "
    "style-src 'unsafe-inline'; "
    "img-src data:; "
    "base-uri 'none'; "
    "form-action 'none'"
)


_CSS = """
:root {
    --bg: #fafafa;
    --fg: #1a1a1a;
    --muted: #666;
    --card-bg: #fff;
    --card-border: #e5e5e5;
    --accent: #2563eb;
    --accent-hover: #1d4ed8;
    --chip-bg: #eef2ff;
    --chip-fg: #3730a3;
    --focus: #2563eb;
}
@media (prefers-color-scheme: dark) {
    :root {
        --bg: #0f0f0f;
        --fg: #f5f5f5;
        --muted: #a3a3a3;
        --card-bg: #1a1a1a;
        --card-border: #333;
        --accent: #60a5fa;
        --accent-hover: #93c5fd;
        --chip-bg: #1e1b4b;
        --chip-fg: #c7d2fe;
        --focus: #60a5fa;
    }
}
* { box-sizing: border-box; }
html { font-size: 16px; }
body {
    margin: 0;
    padding: 16px;
    font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    background: var(--bg);
    color: var(--fg);
    line-height: 1.6;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
}
header { margin-bottom: 32px; }
h1 { margin: 0 0 8px; font-size: 2rem; font-weight: 700; }
.unvan { color: var(--muted); margin: 0 0 16px; font-size: 1.1rem; }
.hakkinda { margin: 0; white-space: pre-wrap; color: var(--fg); }
main { flex: 1; width: 100%; max-width: 1200px; margin: 0 auto; }
.kart-izgara {
    display: grid;
    grid-template-columns: 1fr;
    gap: 20px;
}
@media (min-width: 700px) {
    .kart-izgara { grid-template-columns: repeat(2, 1fr); }
}
@media (min-width: 1100px) {
    .kart-izgara { grid-template-columns: repeat(3, 1fr); }
}
.kart {
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    border-radius: 12px;
    padding: 20px;
    display: flex;
    flex-direction: column;
    transition: border-color 0.2s, box-shadow 0.2s;
}
.kart:hover { border-color: var(--accent); box-shadow: 0 4px 12px rgba(0,0,0,0.08); }
@media (prefers-color-scheme: dark) {
    .kart:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.3); }
}
.kart-baslik {
    margin: 0 0 8px;
    font-size: 1.15rem;
    font-weight: 600;
}
.kart-baslik a {
    color: var(--fg);
    text-decoration: none;
    border-bottom: 1px solid transparent;
    transition: border-color 0.2s;
}
.kart-baslik a:hover { border-color: var(--accent); }
.kart-baslik a:focus-visible {
    outline: 2px solid var(--focus);
    outline-offset: 2px;
    border-radius: 2px;
}
.aciklama { margin: 0 0 12px; color: var(--muted); font-size: 0.95rem; }
.etiketler { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
.chip {
    background: var(--chip-bg);
    color: var(--chip-fg);
    padding: 3px 10px;
    border-radius: 999px;
    font-size: 0.75rem;
    font-weight: 500;
}
.diller { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
.istatistik { margin: 0 0 12px; font-size: 0.85rem; color: var(--muted); }
.readme-ozeti { margin: 0 0 12px; font-size: 0.9rem; color: var(--fg); background: var(--bg); padding: 12px; border-radius: 8px; border: 1px solid var(--card-border); }
.etkinlik { margin-top: auto; }
.etkinlik-svg { display: block; height: 44px; width: 100%; color: var(--accent); }
h2 { margin: 40px 0 16px; font-size: 1.3rem; font-weight: 600; }
.kategori:first-child h2, .kart-izgara + .yazilar h2 { margin-top: 0; }
.yazi-listesi { list-style: none; margin: 0; padding: 0; display: grid; gap: 16px; }
.yazi-listesi li { border-bottom: 1px solid var(--card-border); padding-bottom: 16px; }
.yazi-baslik { color: var(--fg); font-weight: 600; text-decoration: none; border-bottom: 1px solid transparent; }
.yazi-baslik:hover { border-color: var(--accent); }
.yazi-listesi time { margin-left: 10px; color: var(--muted); font-size: 0.85rem; }
.yazi-listesi .aciklama { margin: 6px 0 0; }
.yazi { max-width: 720px; margin: 0 auto; overflow-wrap: anywhere; }
.yazi h1 { font-size: 1.8rem; margin: 0 0 8px; }
.yazi h2 { margin: 32px 0 12px; }
.yazi h3 { margin: 24px 0 8px; font-size: 1.1rem; }
.yazi .yazi-meta { color: var(--muted); font-size: 0.9rem; margin: 0 0 24px; }
.yazi a { color: var(--accent); }
.yazi code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 0.9em; background: var(--chip-bg); padding: 1px 5px; border-radius: 4px; }
.yazi pre { overflow-x: auto; background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 8px; padding: 14px; }
.yazi pre code { background: none; padding: 0; overflow-wrap: normal; }
.yazi blockquote { margin: 16px 0; padding: 0 16px; border-left: 3px solid var(--accent); color: var(--muted); }
.geri { display: inline-block; margin-bottom: 20px; color: var(--accent); text-decoration: none; }
.ust-menu { display: flex; flex-wrap: wrap; gap: 8px 20px; margin-top: 20px; }
.ust-menu a { color: var(--accent); text-decoration: none; font-weight: 500; }
.ust-menu a:hover { text-decoration: underline; }
#projeler, #yazilar { scroll-margin-top: 16px; }
.baglantilar { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
.dugme { font-size: 0.8rem; font-weight: 500; padding: 3px 12px; border: 1px solid var(--accent); border-radius: 999px; color: var(--accent); text-decoration: none; }
.dugme:hover { background: var(--accent); color: var(--card-bg); }
.feed { font-size: 0.8rem; font-weight: 500; margin-left: 8px; color: var(--accent); text-decoration: none; }
.yazi-gezinme { display: flex; justify-content: space-between; gap: 16px; margin-top: 40px; padding-top: 20px; border-top: 1px solid var(--card-border); }
.yazi-gezinme a { color: var(--accent); text-decoration: none; max-width: 48%; }
.yazi-gezinme .sonraki { margin-left: auto; text-align: right; }
html { scroll-behavior: smooth; }
@media (prefers-reduced-motion: reduce) {
    html { scroll-behavior: auto; }
    * { transition: none !important; animation: none !important; }
}
@media print {
    body { background: #fff; color: #000; padding: 0; }
    .kart { box-shadow: none !important; break-inside: avoid; border-color: #999; }
    .ust-menu, .geri, .yazi-gezinme, .feed { display: none; }
    a { color: inherit; }
    .yazi a[href^="https"]::after { content: " (" attr(href) ")"; font-size: 0.8em; }
}
.diller .chip { background: transparent; border: 1px solid var(--card-border); color: var(--muted); }
footer {
    margin-top: 40px;
    padding-top: 20px;
    border-top: 1px solid var(--card-border);
    font-size: 0.85rem;
    color: var(--muted);
    text-align: center;
}
footer a { color: var(--accent); text-decoration: none; }
footer a:hover { text-decoration: underline; }
.sr-only {
    position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px;
    overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0;
}
"""


def _tarih_gunu(deger: object) -> int | None:
    """`date` nesnesini ya da ISO metnini (YYYY-MM-DD) gün sayısına çevirir; olmazsa None."""
    if deger is None:
        return None
    if hasattr(deger, "toordinal"):
        return deger.toordinal()
    try:
        return date.fromisoformat(str(deger)).toordinal()
    except ValueError:
        return None


def _dil_etiketi(d: object, birim: str = "dosya") -> str:
    """Dil girdisi `(ad, sayi)` ya da düz metin olabilir; API verisinde sayı yüzdedir."""
    if isinstance(d, (tuple, list)) and len(d) == 2:
        return f"{d[0]} · %{d[1]}" if birim == "yuzde" else f"{d[0]} · {d[1]}"
    return str(d)


def _svg_cubuk(haftalik: list[int] | None) -> str:
    """12 haftalık commit sayısı için satır içi SVG çubuk grafiği üretir.

    Args:
        haftalik: 12 elemanlı liste (en eskiden en yeniye) veya None.

    Returns:
        SVG string (role="img" ve aria-label ile).
    """
    if not haftalik or len(haftalik) != 12:
        haftalik = [0] * 12

    max_deger = max(haftalik)
    if max_deger == 0:
        # Hepsi 0: düz çizgi
        bar_height = 2
        y = 38
        bars = ''.join(
            f'<rect x="{i * 8 + 1}" y="{y}" width="6" height="{bar_height}" fill="currentColor" opacity="0.3"/>'
            for i in range(12)
        )
        aria = "Son 12 haftada commit sayısı: hiç commit yok"
    else:
        bars = ''.join(
            f'<rect x="{i * 8 + 1}" y="{38 - int(v / max_deger * 36)}" width="6" height="{max(2, int(v / max_deger * 36))}" fill="currentColor" opacity="{0.3 + 0.7 * v / max_deger}"/>'
            for i, v in enumerate(haftalik)
        )
        aria = f"Son 12 haftada commit sayısı: {', '.join(str(v) for v in haftalik)}"

    return (
        f'<svg class="etkinlik-svg" role="img" aria-label="{html.escape(aria, quote=True)}" '
        f'viewBox="0 0 96 40" preserveAspectRatio="none" focusable="false">'
        f'{bars}</svg>'
    )


def _escape_all(obj: object) -> str:
    """Herhangi bir nesneyi string'e çevirip HTML kaçışlı hale getirir."""
    if obj is None:
        return ""
    return html.escape(str(obj), quote=True)


def _favicon(ad: str) -> str:
    """Adın ilk harfinden `data:` SVG monogram (dış dosya yok)."""
    harf = html.escape(next((c for c in ad if c.strip()), "•").upper(), quote=True)
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'>"
        "<rect width='32' height='32' rx='7' fill='#2563eb'/>"
        "<text x='16' y='23' font-size='20' font-family='sans-serif' font-weight='700' "
        f"text-anchor='middle' fill='#fff'>{harf}</text></svg>"
    )
    return f'<link rel="icon" href="data:image/svg+xml,{urllib.parse.quote(svg, safe="")}">'


def _meta(baslik: str, aciklama: str, url: str, tur: str, og_gorsel: str | None = None) -> str:
    """Açıklama + Open Graph + Twitter kartı. `og:image` yalnız başarıyla üretilmiş mutlak URL verilirse yazılır."""
    b, a = _escape_all(baslik), _escape_all(aciklama)
    satirlar = [
        f'<meta name="description" content="{a}">',
        f'<meta property="og:title" content="{b}">',
        f'<meta property="og:description" content="{a}">',
        f'<meta property="og:type" content="{tur}">',
        '<meta property="og:locale" content="tr_TR">',
        f'<meta name="twitter:card" content="{"summary_large_image" if og_gorsel else "summary"}">',
        '<meta name="theme-color" content="#fafafa" media="(prefers-color-scheme: light)">',
        '<meta name="theme-color" content="#0f0f0f" media="(prefers-color-scheme: dark)">',
    ]
    if url:
        satirlar.append(f'<meta property="og:url" content="{_escape_all(url)}">')
    if og_gorsel:
        satirlar += [
            f'<meta property="og:image" content="{_escape_all(og_gorsel)}">',
            '<meta property="og:image:width" content="1200">',
            '<meta property="og:image:height" content="630">',
            f'<meta property="og:image:alt" content="{b}">',
        ]
    return "\n    ".join(satirlar)


def _kisalt(metin: str, en_cok: int = 160) -> str:
    metin = " ".join(str(metin).split())
    return metin if len(metin) <= en_cok else metin[: en_cok - 1].rstrip() + "…"


def _siralama_anahtari(item: dict) -> tuple:
    gun = _tarih_gunu(item["son_commit"])
    kosul = (1, 0) if gun is None else (0, -gun)  # tarihsizler en sona
    return kosul, str(getattr(item["repo_cfg"], "ad", "")).casefold()


def _kart_html(repo_cfg: object, veri: object | None, seviye: int = 2) -> str:
    repo_ad = _escape_all(getattr(repo_cfg, "ad", ""))
    repo_aciklama = _escape_all(getattr(repo_cfg, "aciklama", ""))
    repo_url = _escape_all(getattr(repo_cfg, "url", ""))
    etiket_html = "".join(
        f'<span class="chip">{_escape_all(e)}</span>' for e in (getattr(repo_cfg, "etiketler", []) or [])
    )

    baglanti_html = "".join(
        f'<a class="dugme" href="{_escape_all(url)}" rel="noopener noreferrer" target="_blank">{_escape_all(ad)}</a>'
        for ad, url in (getattr(repo_cfg, "baglantilar", ()) or ())
    )
    if baglanti_html:
        baglanti_html = f'<div class="baglantilar">{baglanti_html}</div>'
    istatistik_html = dil_html = etkinlik_html = readme_html = ""
    if veri is not None:
        commit_sayisi = getattr(veri, "commit_sayisi", 0)
        son_commit = getattr(veri, "son_commit", None)
        haftalik = getattr(veri, "haftalik", None)
        diller = getattr(veri, "diller", []) or []
        birim = getattr(veri, "dil_birimi", "dosya")
        readme_ozeti = getattr(veri, "readme_ozeti", None)

        if son_commit and hasattr(son_commit, "isoformat"):
            son_commit_str = son_commit.isoformat()
        else:
            son_commit_str = str(son_commit) if son_commit else "—"
        istatistik_html = f'<p class="istatistik">{commit_sayisi} commit · son: {_escape_all(son_commit_str)}</p>'
        dil_html = "".join(f'<span class="chip">{_escape_all(_dil_etiketi(d, birim))}</span>' for d in diller)
        if haftalik is not None:  # None = veri yok: yanıltıcı "hiç commit yok" çizgisi çizilmez
            etkinlik_html = f'<div class="etkinlik">{_svg_cubuk(haftalik)}</div>'
        if readme_ozeti:
            readme_html = f'<p class="readme-ozeti">{_escape_all(readme_ozeti)}</p>'

    return f"""
        <article class="kart">
            <h{seviye} class="kart-baslik"><a href="{repo_url}" rel="noopener noreferrer" target="_blank">{repo_ad}</a></h{seviye}>
            <p class="aciklama">{repo_aciklama}</p>
            <div class="etiketler">{etiket_html}</div>
            {baglanti_html}
            <div class="diller">{dil_html}</div>
            {istatistik_html}
            {readme_html}
            {etkinlik_html}
        </article>
        """


def _bolumler(ayar, veriler: Mapping[str, object | None]) -> list[tuple[str | None, list[dict]]]:
    """(kategori başlığı | None, sıralı kart öğeleri) bölümleri. Boş kategori çıkmaz."""
    ogeler = []
    for repo_cfg in getattr(ayar, "repolar", []):
        if not getattr(repo_cfg, "ad", ""):
            continue
        veri = veriler.get(repo_cfg.ad) if veriler else None
        ogeler.append({
            "repo_cfg": repo_cfg,
            "veri": veri,
            "son_commit": getattr(veri, "son_commit", None) if veri is not None else None,
        })

    def sirala(liste: list[dict]) -> list[dict]:
        if getattr(ayar, "siralama", "manuel") == "aktivite":
            return sorted(liste, key=_siralama_anahtari)
        return liste  # manuel: yapılandırma sırası

    kategoriler = tuple(getattr(ayar, "kategoriler", ()) or ())
    if not kategoriler:
        return [(None, sirala(ogeler))]

    bolumler = []
    for ad in (*kategoriler, "Diğer"):
        grup = [o for o in ogeler if getattr(o["repo_cfg"], "kategori", "Diğer") == ad]
        if grup:
            bolumler.append((ad, sirala(grup)))
    return bolumler


def _yazilar_bolumu(yazilar: Sequence[object], feed: bool = False) -> str:
    if not yazilar:
        return ""
    rss = ' <a class="feed" href="feed.xml">RSS</a>' if feed else ""
    satirlar = []
    for y in sorted(yazilar, key=lambda y: str(getattr(y, "tarih", "")), reverse=True):
        slug = _escape_all(getattr(y, "slug", ""))
        satirlar.append(
            f'<li><a class="yazi-baslik" href="yazilar/{slug}.html">{_escape_all(getattr(y, "baslik", ""))}</a>'
            f'<time datetime="{_escape_all(getattr(y, "tarih", ""))}">{_escape_all(getattr(y, "tarih", ""))}</time>'
            f'<p class="aciklama">{_escape_all(getattr(y, "ozet", ""))}</p></li>'
        )
    return f'<section class="yazilar" id="yazilar"><h2>Yazılar{rss}</h2><ul class="yazi-listesi">{"".join(satirlar)}</ul></section>'


def _feed_link(ayar, href: str | None) -> str:
    if not href:
        return ""
    baslik = f'{getattr(getattr(ayar, "sahip", None), "ad", "")} · Yazılar'
    return f'<link rel="alternate" type="application/atom+xml" href="{href}" title="{_escape_all(baslik)}">'


def _belge(
    ayar, *, baslik: str, aciklama: str, url: str, tur: str, ust: str, icerik: str, bugun: date,
    og_gorsel: str | None = None, feed_href: str | None = None,
) -> str:
    """Ortak sayfa iskeleti: CSP, meta, favicon, üst, içerik, alt bilgi."""
    sahip = getattr(ayar, "sahip", None)
    ad = getattr(sahip, "ad", "")
    github = _escape_all(getattr(sahip, "github", ""))
    github_url = f"https://github.com/{github}" if github else "#"
    return f"""<!doctype html>
<html lang="tr">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta http-equiv="Content-Security-Policy" content="{_CSP}">
    <title>{_escape_all(baslik)}</title>
    {_meta(baslik, aciklama, url, tur, og_gorsel)}
    {_favicon(str(ad))}
    {_feed_link(ayar, feed_href)}
    <style>{_CSS}</style>
</head>
<body>
    {ust}
    <main>
        {icerik}
    </main>
    <footer>
        <p>Otomatik üretildi: {bugun.isoformat()}</p>
        <p><a href="{github_url}" rel="noopener noreferrer" target="_blank">@{github}</a></p>
    </footer>
</body>
</html>
"""


def sayfa_url(ayar, yol: str = "") -> str:
    taban = getattr(getattr(ayar, "sahip", None), "site_url", "") or ""
    return f"{taban.rstrip('/')}/{yol}" if taban else ""


def render(
    ayar, veriler: Mapping[str, object | None], bugun: date, yazilar: Sequence[object] = (),
    og_gorsel: str | None = None, feed: bool = False,
) -> str:
    """Ana sayfa HTML'ini üretir (kategoriler, kartlar, varsa yazılar)."""
    sahip = getattr(ayar, "sahip", None)
    ad = getattr(sahip, "ad", "")
    unvan = getattr(sahip, "unvan", "")
    hakkinda = getattr(sahip, "hakkinda", "")

    bolumler = []
    for baslik, ogeler in _bolumler(ayar, veriler):
        kartlar = "\n".join(_kart_html(o["repo_cfg"], o["veri"], 2 if baslik is None else 3) for o in ogeler)
        izgara = f'<div class="kart-izgara">{kartlar}</div>'
        if baslik is None:
            bolumler.append(izgara)
        else:
            bolumler.append(f'<section class="kategori"><h2>{_escape_all(baslik)}</h2>{izgara}</section>')
    projeler = f'<div id="projeler">{"".join(bolumler)}</div>'

    github = _escape_all(getattr(sahip, "github", ""))
    menu = ['<a href="#projeler">Projeler</a>']
    if yazilar:
        menu.append('<a href="#yazilar">Yazılar</a>')
    if github:
        menu.append(f'<a href="https://github.com/{github}" rel="noopener noreferrer" target="_blank">GitHub</a>')
    ust = f"""<header>
        <h1>{_escape_all(ad)}</h1>
        <p class="unvan">{_escape_all(unvan)}</p>
        <p class="hakkinda">{_escape_all(hakkinda)}</p>
        <nav class="ust-menu" aria-label="Sayfa bölümleri">{"".join(menu)}</nav>
    </header>"""
    return _belge(
        ayar,
        baslik=str(ad),
        aciklama=_kisalt(hakkinda or unvan or ad),
        url=sayfa_url(ayar),
        tur="website",
        ust=ust,
        icerik=projeler + _yazilar_bolumu(yazilar, feed),
        bugun=bugun,
        og_gorsel=og_gorsel,
        feed_href="feed.xml" if feed and yazilar else None,
    )


def _okuma_dk(kelime: object) -> int:
    return max(1, round((kelime if isinstance(kelime, int) else 0) / 200))


def _gezinme(onceki: object | None, sonraki: object | None) -> str:
    """Yazı sonunda eski/yeni yazıya göreli bağlantılar (aynı `yazilar/` klasörü)."""
    parcalar = []
    if onceki is not None:
        parcalar.append(
            f'<a class="onceki" href="{_escape_all(onceki.slug)}.html" rel="prev">← {_escape_all(onceki.baslik)}</a>'
        )
    if sonraki is not None:
        parcalar.append(
            f'<a class="sonraki" href="{_escape_all(sonraki.slug)}.html" rel="next">{_escape_all(sonraki.baslik)} →</a>'
        )
    return f'<nav class="yazi-gezinme" aria-label="Diğer yazılar">{"".join(parcalar)}</nav>' if parcalar else ""


def render_yazi(
    ayar, yazi: object, bugun: date, og_gorsel: str | None = None,
    onceki: object | None = None, sonraki: object | None = None, feed: bool = False,
) -> str:
    """Tek yazı sayfası: aynı CSS/CSP/meta, '← Ana sayfa', okuma süresi, önceki/sonraki ve <article>."""
    slug = str(getattr(yazi, "slug", ""))
    etiketler = "".join(
        f'<span class="chip">{_escape_all(e)}</span>' for e in (getattr(yazi, "etiketler", ()) or ())
    )
    tarih = _escape_all(getattr(yazi, "tarih", ""))
    dk = _okuma_dk(getattr(yazi, "kelime", 0))
    ust = '<header><a class="geri" href="../index.html">← Ana sayfa</a></header>'
    # govde_html yazi.markdown_html çıktısıdır (kaçışlı, yalnız izinli etiketler)
    icerik = f"""<article class="yazi">
        <h1>{_escape_all(getattr(yazi, "baslik", ""))}</h1>
        <p class="yazi-meta"><time datetime="{tarih}">{tarih}</time> · {dk} dk okuma</p>
        {getattr(yazi, "govde_html", "")}
        <div class="etiketler">{etiketler}</div>
        {_gezinme(onceki, sonraki)}
    </article>"""
    return _belge(
        ayar,
        baslik=f'{getattr(yazi, "baslik", "")} · {getattr(getattr(ayar, "sahip", None), "ad", "")}',
        aciklama=str(getattr(yazi, "ozet", "")),
        url=sayfa_url(ayar, f"yazilar/{slug}.html"),
        tur="article",
        ust=ust,
        icerik=icerik,
        bugun=bugun,
        og_gorsel=og_gorsel,
        feed_href="../feed.xml" if feed else None,
    )


# Kendi kendini denetle: üretilen HTML'in kendi tara()'sını geçmesi gerekir
def _kendi_denetimi(html_metin: str) -> list:
    """Üretilen HTML'i denetim.tarayıcıdan geçirir (testlerde kullanılır)."""
    return tara(html_metin)
