"""Tek dosyalık statik portfolyo HTML üreticisi.

JavaScript yok, dış kaynak (font/CDN/analitik) yok. CSP meta etiketiyle kilitli.
Sistem font yığını, açık/koyu tema, CSS Grid kart ızgarası, SVG etkinlik grafiği.
"""

from __future__ import annotations

import html
from collections.abc import Mapping
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


def _dil_etiketi(d: object) -> str:
    """Dil girdisi `(ad, dosya_sayisi)` ya da düz metin olabilir."""
    if isinstance(d, (tuple, list)) and len(d) == 2:
        return f"{d[0]} · {d[1]}"
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


def render(ayar, veriler: Mapping[str, object | None], bugun: date) -> str:
    """Tek dosyalık portfolyo HTML'ini üretir.

    Args:
        ayar: Yapılandırma nesnesi (sahip.{ad,unvan,github,hakkinda},
              repolar[i].{ad,aciklama,url,etiketler} alanlarına erişir).
        veriler: Repo adı -> RepoVerisi benzeri nesne veya None (klon yoksa).
                 Beklenen alanlar: commit_sayisi, ilk_commit, son_commit,
                 haftalik (12 elemanlı liste), diller, readme_ozeti.
        bugun: Üretim tarihi (ISO formatında footer'a yazılır).

    Returns:
        Tam HTML belgesi string'i.
    """
    # Sahip bilgileri
    sahip_ad = _escape_all(getattr(getattr(ayar, "sahip", None), "ad", ""))
    sahip_unvan = _escape_all(getattr(getattr(ayar, "sahip", None), "unvan", ""))
    sahip_github = _escape_all(getattr(getattr(ayar, "sahip", None), "github", ""))
    sahip_hakkinda = _escape_all(getattr(getattr(ayar, "sahip", None), "hakkinda", ""))

    # Repoları topla ve sırala: son_commit azalan (None en sona), eşitlikte ad
    kart_verileri = []
    for repo_cfg in getattr(ayar, "repolar", []):
        repo_ad = getattr(repo_cfg, "ad", "")
        if not repo_ad:
            continue

        veri = veriler.get(repo_ad) if veriler else None

        son_commit = None
        if veri is not None:
            son_commit = getattr(veri, "son_commit", None)

        kart_verileri.append({
            "repo_cfg": repo_cfg,
            "veri": veri,
            "son_commit": son_commit,
        })

    # Sıralama: son_commit azalan (None en sona), sonra ad
    def _siralama_anahtari(item):
        gun = _tarih_gunu(item["son_commit"])
        if gun is None:
            return (1, 0)  # tarihsizler en sona
        return (0, -gun)

    kart_verileri.sort(key=lambda x: (_siralama_anahtari(x), str(getattr(x["repo_cfg"], "ad", "")).casefold()))

    # Kart HTML'lerini oluştur
    kart_html_list = []
    for item in kart_verileri:
        repo_cfg = item["repo_cfg"]
        veri = item["veri"]

        repo_ad = _escape_all(getattr(repo_cfg, "ad", ""))
        repo_aciklama = _escape_all(getattr(repo_cfg, "aciklama", ""))
        repo_url = _escape_all(getattr(repo_cfg, "url", ""))
        repo_etiketler = getattr(repo_cfg, "etiketler", []) or []

        # Etiket çipleri
        etiket_html = ''.join(
            f'<span class="chip">{_escape_all(e)}</span>' for e in repo_etiketler
        )

        if veri is not None:
            # Veri varsa: istatistikler, diller, etkinlik, readme özeti
            commit_sayisi = getattr(veri, "commit_sayisi", 0)
            son_commit = getattr(veri, "son_commit", None)
            haftalik = getattr(veri, "haftalik", None)
            diller = getattr(veri, "diller", []) or []
            readme_ozeti = getattr(veri, "readme_ozeti", None)

            son_commit_str = son_commit.isoformat() if son_commit and hasattr(son_commit, "isoformat") else (str(son_commit) if son_commit else "—")
            istatistik_html = f'<p class="istatistik">{commit_sayisi} commit · son: {_escape_all(son_commit_str)}</p>'

            dil_html = ''.join(
                f'<span class="chip">{_escape_all(_dil_etiketi(d))}</span>' for d in diller
            )

            etkinlik_html = f'<div class="etkinlik">{_svg_cubuk(haftalik)}</div>'

            readme_html = ""
            if readme_ozeti:
                readme_html = f'<p class="readme-ozeti">{_escape_all(readme_ozeti)}</p>'
        else:
            # Klon yok: sadece yapılandırma metni
            istatistik_html = ""
            dil_html = ""
            etkinlik_html = ""
            readme_html = ""

        kart_html = f"""
        <article class="kart">
            <h2 class="kart-baslik"><a href="{repo_url}" rel="noopener noreferrer" target="_blank">{repo_ad}</a></h2>
            <p class="aciklama">{repo_aciklama}</p>
            <div class="etiketler">{etiket_html}</div>
            <div class="diller">{dil_html}</div>
            {istatistik_html}
            {readme_html}
            {etkinlik_html}
        </article>
        """
        kart_html_list.append(kart_html)

    kartlar_html = "\n".join(kart_html_list)

    # Footer
    github_url = f"https://github.com/{sahip_github}" if sahip_github else "#"
    footer_html = f"""
    <footer>
        <p>Otomatik üretildi: {bugun.isoformat()}</p>
        <p><a href="{github_url}" rel="noopener noreferrer" target="_blank">@{sahip_github}</a></p>
    </footer>
    """

    # Tam HTML
    html_out = f"""<!doctype html>
<html lang="tr">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta http-equiv="Content-Security-Policy" content="{_CSP}">
    <title>{sahip_ad}</title>
    <style>{_CSS}</style>
</head>
<body>
    <header>
        <h1>{sahip_ad}</h1>
        <p class="unvan">{sahip_unvan}</p>
        <p class="hakkinda">{sahip_hakkinda}</p>
    </header>
    <main>
        <div class="kart-izgara">
            {kartlar_html}
        </div>
    </main>
    {footer_html}
</body>
</html>
"""
    return html_out


# Kendi kendini denetle: üretilen HTML'in kendi tara()'sını geçmesi gerekir
def _kendi_denetimi(html_metin: str) -> list:
    """Üretilen HTML'i denetim.tarayıcıdan geçirir (testlerde kullanılır)."""
    return tara(html_metin)