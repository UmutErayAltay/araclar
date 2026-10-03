"""Tek dosyalık statik portfolyo HTML üreticisi (Cihaz Rafı tasarımı).

JavaScript yok, dış kaynak (font/CDN/analitik) yok. CSP meta etiketiyle kilitli.
Stil `stil.py`'den (CSS), sabit etiketler `metin.py`'den gelir; içerik yapılandırmadan.
"""

from __future__ import annotations

import html
import urllib.parse
from collections.abc import Mapping, Sequence
from datetime import date
from types import SimpleNamespace

from .denetim import tara
from .metin import m
from .stil import CSS


# CSP: default-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src 'self'; base-uri 'none'; form-action 'none'
_CSP = (
    "default-src 'none'; "
    "style-src 'unsafe-inline'; "
    "img-src data:; "
    "font-src 'self'; "
    "base-uri 'none'; "
    "form-action 'none'"
)

# Satır içi ikonlar (comp'tan birebir): 16x16, 1.6 kalınlık, dekoratif oldukları için aria-hidden.
_SVG_INDIR = (
    '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" '
    'stroke-linejoin="round" aria-hidden="true"><path d="M8 2v8M4.5 7 8 10.5 11.5 7M3 13.5h10"/></svg>'
)
_SVG_ZARF = (
    '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" '
    'stroke-linejoin="round" aria-hidden="true"><rect x="2" y="3.5" width="12" height="9" rx="1.5"/>'
    '<path d="m2.5 4.5 5.5 4.5 5.5-4.5"/></svg>'
)

_DIL_KODLARI = {"tr": "TR", "en": "EN"}


# --- küçük yardımcılar -------------------------------------------------------------------

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


def _escape_all(obj: object) -> str:
    """Herhangi bir nesneyi string'e çevirip HTML kaçışlı hale getirir."""
    if obj is None:
        return ""
    return html.escape(str(obj), quote=True)


def _kisalt(metin: str, en_cok: int = 160) -> str:
    metin = " ".join(str(metin).split())
    return metin if len(metin) <= en_cok else metin[: en_cok - 1].rstrip() + "…"


def _svg_cubuk(haftalik: Sequence[int] | None, dil: str = "tr") -> str:
    """12 haftalık commit sayısı için ızgaralı satır içi SVG çubuk grafiği.

    Args:
        haftalik: 12 elemanlı liste (en eskiden en yeniye) veya None (boş sayılır).
        dil: Etiket dili (`olcer_aria`, `hic_commit`).

    Returns:
        SVG string (role="img" ve aria-label ile).
    """
    if not haftalik or len(haftalik) != 12:
        haftalik = [0] * 12

    izgara = '<path class="izgara" d="M0 10H96M0 20H96M0 30H96"/>'
    en_cok = max(haftalik)
    if en_cok == 0:
        # Hepsi 0: düz çizgi (yanıltıcı yükseklik çizilmez)
        cubuklar = "".join(
            f'<rect x="{i * 8 + 1}" y="38" width="6" height="2" fill="currentColor" opacity="0.3"/>'
            for i in range(12)
        )
        deger = m(dil, "hic_commit")
    else:
        cubuklar = "".join(
            f'<rect x="{i * 8 + 1}" y="{38 - int(v / en_cok * 34)}" width="6" '
            f'height="{max(2, int(v / en_cok * 34))}" fill="currentColor" '
            f'opacity="{0.45 + 0.55 * v / en_cok:.2f}"/>'
            for i, v in enumerate(haftalik)
        )
        deger = ", ".join(str(v) for v in haftalik)

    etiket = html.escape(f'{m(dil, "olcer_aria")} {deger}', quote=True)
    return (
        f'<svg class="etkinlik-svg" role="img" aria-label="{etiket}" '
        f'viewBox="0 0 96 40" preserveAspectRatio="none" focusable="false">{izgara}{cubuklar}</svg>'
    )


def _favicon(ad: str) -> str:
    """Adın ilk harfinden `data:` SVG monogram (dış dosya yok)."""
    harf = html.escape(next((c for c in ad if c.strip()), "•").upper(), quote=True)
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'>"
        "<rect width='32' height='32' rx='7' fill='#1b1c1e'/>"
        "<text x='16' y='23' font-size='20' font-family='sans-serif' font-weight='700' "
        f"text-anchor='middle' fill='#e8a317'>{harf}</text></svg>"
    )
    return f'<link rel="icon" href="data:image/svg+xml,{urllib.parse.quote(svg, safe="")}">'


def _meta(
    baslik: str, aciklama: str, url: str, tur: str, dil: str = "tr", og_gorsel: str | None = None
) -> str:
    """Açıklama + Open Graph + Twitter kartı. `og:image` yalnız üretilmiş mutlak URL verilirse yazılır."""
    b, a = _escape_all(baslik), _escape_all(aciklama)
    satirlar = [
        f'<meta name="description" content="{a}">',
        f'<meta property="og:title" content="{b}">',
        f'<meta property="og:description" content="{a}">',
        f'<meta property="og:type" content="{tur}">',
        f'<meta property="og:locale" content="{_escape_all(m(dil, "locale"))}">',
        f'<meta name="twitter:card" content="{"summary_large_image" if og_gorsel else "summary"}">',
        '<meta name="theme-color" content="#b3afa4" media="(prefers-color-scheme: light)">',
        '<meta name="theme-color" content="#08090a" media="(prefers-color-scheme: dark)">',
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


def _sayfa_url(ayar, yol: str) -> str:
    taban = getattr(getattr(ayar, "sahip", None), "site_url", "") or ""
    return f"{taban.rstrip('/')}/{yol}" if taban else ""


def _belge(
    ayar, *, baslik: str, aciklama: str, url: str, tur: str, ust: str, icerik: str, bugun: date,
    dil: str = "tr", og_gorsel: str | None = None, feed_href: str | None = None,
) -> str:
    """Ortak sayfa iskeleti: CSP, meta, favicon, şerit, `main.raf`, alt not."""
    sahip = getattr(ayar, "sahip", None)
    github = _escape_all(getattr(sahip, "github", ""))
    github_url = f"https://github.com/{github}" if github else "#"
    alt_not = (
        f'<p class="alt-not">{_escape_all(m(dil, "uretildi"))} {bugun.isoformat()}'
        f'{" · " if github else ""}'
        f'<a href="{github_url}" rel="noopener noreferrer" target="_blank">@{github}</a></p>'
    )
    return f"""<!doctype html>
<html lang="{_escape_all(dil)}">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta http-equiv="Content-Security-Policy" content="{_CSP}">
    <title>{_escape_all(baslik)}</title>
    {_meta(baslik, aciklama, url, tur, dil, og_gorsel)}
    {_favicon(str(getattr(sahip, "ad", "")))}
    {_feed_link(ayar, feed_href)}
    <style>{CSS}</style>
</head>
<body>
    <a class="skip" href="#icerik">{_escape_all(m(dil, "atla"))}</a>
    {ust}
    <main class="raf" id="icerik">
        {icerik}
    </main>
    {alt_not}
</body>
</html>
"""


# --- ortak parçalar ----------------------------------------------------------------------

def _unit(sinif: str, icerik: str) -> str:
    """1U ünite: iki dekoratif kulak + yüzey. `sinif` boşsa yalnız `unit`."""
    tam = f"unit {sinif}".strip()
    return (
        f'<section class="{tam}"><i class="kulak" aria-hidden="true"></i>'
        f'<div class="yuz">{icerik}</div><i class="kulak" aria-hidden="true"></i></section>'
    )


def _ray(baslik: str, kimlik: str = "", sag: str = "", *, sinif: str = "") -> str:
    """Bölüm başlığı rayı: `<h2>` + isteğe bağlı sağ metin ve `id` (menü hedefi)."""
    hedef = f' id="{_escape_all(kimlik)}"' if kimlik else ""
    tam = f"ray {sinif}".strip()
    return f'<div class="{tam}"{hedef}><h2>{baslik}</h2>{sag}</div>'


def _yigin(etiketler: object) -> str:
    """Etiket yığını (`ul.yigin`); etiket yoksa boş dize."""
    ogeler = "".join(f"<li>{_escape_all(e)}</li>" for e in (etiketler or ()))
    return f'<ul class="yigin">{ogeler}</ul>' if ogeler else ""


def _son_commit(veri: object) -> str:
    son = getattr(veri, "son_commit", None)
    if son and hasattr(son, "isoformat"):
        return son.isoformat()
    return str(son) if son else "—"


def _olcer_pencere(veri: object | None, dil: str, eksenli: bool) -> str:
    """`.olcer-pencere` (çubuk grafik + isteğe bağlı eksen). Veri ya da haftalık yoksa boş."""
    if veri is None:
        return ""
    haftalik = getattr(veri, "haftalik", None)
    if haftalik is None:  # None = veri yok: yanıltıcı "hiç commit yok" çizgisi çizilmez
        return ""
    eksen = (
        f'<div class="olcer-eksen"><span>{_escape_all(m(dil, "hafta_once"))}</span>'
        f'<span>{_escape_all(m(dil, "bu_hafta"))}</span></div>'
        if eksenli else ""
    )
    return f'<div class="olcer-pencere">{_svg_cubuk(haftalik, dil)}{eksen}</div>'


def _kayit(kayit: object) -> str:
    """Deneyim/eğitim kaydı: rol (ya da derece) + kurum (ya da okul) + tarih (+ ek) + açıklama."""
    rol = getattr(kayit, "rol", "") or getattr(kayit, "derece", "")
    kurum = getattr(kayit, "kurum", "") or getattr(kayit, "okul", "")
    tarih = getattr(kayit, "tarih", "") or ""
    ek = getattr(kayit, "ek", "") or ""
    parcalar = [f'<h3>{_escape_all(rol)}</h3>']
    if kurum:
        parcalar.append(f'<p class="kurum">{_escape_all(kurum)}</p>')
    if tarih:
        parcalar.append(f'<span class="tarih">{_escape_all(tarih)}</span>')
    if ek:
        parcalar.append(f'<span class="ek">{_escape_all(ek)}</span>')
    if getattr(kayit, "aciklama", ""):
        parcalar.append(f"<p>{_escape_all(kayit.aciklama)}</p>")
    return f'<div class="kayit">{"".join(parcalar)}</div>'


# --- şerit -------------------------------------------------------------------------------

def _marka(ad: str) -> str:
    """Adın baş harfleri noktalı: "Umut Eray Altay" -> "U.E.A"."""
    return ".".join(parca[0] for parca in str(ad).split() if parca)

def _menu(dil: str, bolumler: Sequence[str], *, kok: str = "") -> str:
    """Bölüm menüsü; yalnız gerçekten var olan bölümler listelenir (ölü bağlantı olmaz).
    `kok` yazı sayfası için kök-göreli önek (`../`)."""
    etiketler = {
        "projeler": "menu_projeler", "deneyim": "menu_deneyim", "yetenekler": "menu_yetenekler",
        "egitim": "menu_egitim", "yazilar": "menu_yazilar", "iletisim": "menu_iletisim",
    }
    li = "".join(
        f'<li><a href="{kok}#{_escape_all(kimlik)}">{_escape_all(m(dil, etiketler[kimlik]))}</a></li>'
        for kimlik in bolumler
    )
    return f'<ul class="menu">{li}</ul>'


def _dil_anahtari(ayar, dil: str) -> str:
    """Dil anahtarı. `ayar.dil_baglantisi` boşsa (tek dilli site) hiç çıkmaz."""
    baglanti = getattr(ayar, "dil_baglantisi", "") or ""
    if not baglanti:
        return ""
    diger = "en" if dil == "tr" else "tr"
    parcalar = []
    for kod in ("tr", "en"):
        etiket = _DIL_KODLARI[kod]
        if kod == dil:
            parcalar.append(f'<a href="." lang="{kod}" hreflang="{kod}" aria-current="true">{etiket}</a>')
        elif kod == diger:
            parcalar.append(
                f'<a href="{_escape_all(baglanti)}" lang="{kod}" hreflang="{kod}">{etiket}</a>'
            )
    return f'<nav class="dil" aria-label="{_escape_all(m(dil, "dil_etiket"))}">{"".join(parcalar)}</nav>'


def _cv_dugmesi(ayar, dil: str, *, kucuk: bool) -> str:
    """Sayfa diline göre birincil CV düğmesi; yol boşsa düğme çıkmaz."""
    yol = getattr(getattr(ayar, "sahip", None), "cv_tr" if dil == "tr" else "cv_en", "") or ""
    if not yol:
        return ""
    sinif = "tus tus--eylem tus--kucuk" if kucuk else "tus tus--eylem"
    return (
        f'<a class="{sinif}" href="{_escape_all(yol)}" download>'
        f'{_SVG_INDIR}{_escape_all(m(dil, "cv_kisa" if kucuk else "cv_indir"))}</a>'
    )


def _serit(ayar, dil: str, bolumler: Sequence[str], *, kok: str = "") -> str:
    """Yapışkan şerit: marka, menü, dil anahtarı, küçük CV düğmesi."""
    icerik = (
        f'<a class="marka" href="{kok}#icerik">'
        f'{_escape_all(_marka(getattr(getattr(ayar, "sahip", None), "ad", "")))}</a>'
        f'{_menu(dil, bolumler, kok=kok)}{_dil_anahtari(ayar, dil)}{_cv_dugmesi(ayar, dil, kucuk=True)}'
    )
    return f'<header class="serit"><div class="raf" style="padding-bottom:0">{_unit("", icerik)}</div></header>'


def _feed_link(ayar, href: str | None) -> str:
    if not href:
        return ""
    baslik = f'{getattr(getattr(ayar, "sahip", None), "ad", "")} · Yazılar'
    return f'<link rel="alternate" type="application/atom+xml" href="{href}" title="{_escape_all(baslik)}">'


# --- projeler ----------------------------------------------------------------------------

def _siralama_anahtari(item: dict) -> tuple:
    gun = _tarih_gunu(item["veri"].son_commit) if item["veri"] is not None else None
    kosul = (1, 0) if gun is None else (0, -gun)  # tarihsizler en sona
    return kosul, str(getattr(item["repo_cfg"], "ad", "")).casefold()


def _ogeler(ayar, veriler: Mapping[str, object | None]) -> list[dict]:
    """Adı boş olmayan her repo için (yapılandırma, veri) çifti."""
    return [
        {"repo_cfg": r, "veri": (veriler or {}).get(getattr(r, "ad", ""))}
        for r in getattr(ayar, "repolar", [])
        if getattr(r, "ad", "")
    ]


def _sirala(ayar, ogeler: list[dict]) -> list[dict]:
    if getattr(ayar, "siralama", "manuel") == "aktivite":
        return sorted(ogeler, key=_siralama_anahtari)
    return ogeler  # manuel: yapılandırma sırası


def _baglar(repo_cfg: object) -> str:
    """GitHub düğmesi + yapılandırılmış ek bağlantılar (`.baglar`)."""
    parcalar = []
    url = getattr(repo_cfg, "url", "")
    if url:
        parcalar.append(
            f'<a class="tus tus--kucuk" href="{_escape_all(url)}" rel="noopener noreferrer" '
            f'target="_blank">GitHub</a>'
        )
    for ad, hedef in (getattr(repo_cfg, "baglantilar", ()) or ()):
        parcalar.append(
            f'<a class="tus tus--kucuk" href="{_escape_all(hedef)}" rel="noopener noreferrer" '
            f'target="_blank">{_escape_all(ad)}</a>'
        )
    return f'<div class="baglar">{"".join(parcalar)}</div>' if parcalar else ""


def _kart_html(repo_cfg: object, veri: object | None, seviye: int = 3, dil: str = "tr") -> str:
    """Öne çıkan ünite (`.unit.one`): ad, açıklama, etiketler, bağlantılar, ölçer."""
    ad = _escape_all(getattr(repo_cfg, "ad", ""))
    url = _escape_all(getattr(repo_cfg, "url", ""))
    sol = (
        f'<div><h{seviye} class="pr-ad"><a href="{url}" rel="noopener noreferrer" target="_blank">{ad}</a></h{seviye}>'
        f'<p class="pr-aciklama">{_escape_all(getattr(repo_cfg, "aciklama", ""))}</p>'
        f'{_yigin(getattr(repo_cfg, "etiketler", ()))}{_repo_led(repo_cfg)}{_baglar(repo_cfg)}</div>'
    )
    sag = ""
    if veri is not None:
        sag = (
            f'<div class="olcer">{_olcer_pencere(veri, dil, eksenli=True)}'
            f'<div class="olcer-rakam"><b>{_escape_all(getattr(veri, "commit_sayisi", 0))}</b>'
            f'<span>{_escape_all(m(dil, "commit"))}</span></div>'
            f'<p class="olcer-tarih">{_escape_all(m(dil, "son_commit"))} {_escape_all(_son_commit(veri))}</p></div>'
        )
    return _unit("one", sol + sag)


def _repo_led(repo_cfg: object) -> str:
    """Yapılandırmada `led` verilmişse ünitenin kendi durum satırı (`.ledler.pr-durum`)."""
    led = getattr(repo_cfg, "led", None)
    if not led or not getattr(led, "metin", ""):
        return ""
    return (
        f'<ul class="ledler pr-durum"><li class="led{_led_sinif(getattr(led, "tur", ""))}">'
        f'{_escape_all(led.metin)}</li></ul>'
    )


def _satir_html(repo_cfg: object, veri: object | None, dil: str = "tr") -> str:
    """1U satır: ad, açıklama + etiketler, ölçer, commit sayısı."""
    ad = _escape_all(getattr(repo_cfg, "ad", ""))
    url = _escape_all(getattr(repo_cfg, "url", ""))
    return (
        f'<div class="satir"><div><h4><a href="{url}" rel="noopener noreferrer" target="_blank">{ad}</a></h4></div>'
        f'<div><p>{_escape_all(getattr(repo_cfg, "aciklama", ""))}</p>'
        f'{_yigin(getattr(repo_cfg, "etiketler", ()))}</div>'
        f'{_olcer_pencere(veri, dil, eksenli=False)}'
        f'{_sayi(veri, dil)}</div>'
    )


def _sayi(veri: object | None, dil: str) -> str:
    """Satırın sağ sütunu: commit sayısı + son commit tarihi. Veri yoksa boş."""
    if veri is None:
        return ""
    return (
        f'<div class="sayi"><b>{_escape_all(getattr(veri, "commit_sayisi", 0))}</b>'
        f'{_escape_all(m(dil, "commit"))}<span>{_escape_all(_son_commit(veri))}</span></div>'
    )


def _diger_bolum(ayar, ogeler: list[dict], dil: str) -> str:
    """Kategori grupları: `h3.alt` + `.satirlar`. Kategorisiz yapılandırmada grup başlığı çıkmaz."""
    parcalar = []
    for ad, grup in _gruplar(ayar, ogeler):
        satirlar = "".join(_satir_html(o["repo_cfg"], o["veri"], dil) for o in _sirala(ayar, grup))
        baslik = f'<h3 class="alt">{_escape_all(ad)}</h3>' if ad else ""
        parcalar.append(f'{baslik}<div class="satirlar">{satirlar}</div>')
    return "".join(parcalar)


def _gruplar(ayar, ogeler: list[dict]) -> list[tuple[str, list[dict]]]:
    """(kategori başlığı, öğeler) listesi; boş kategori çıkmaz, "Diğer" en sonda.
    `kategoriler` tanımlı değilse tek grup, başlıksız döner."""
    kategoriler = tuple(getattr(ayar, "kategoriler", ()) or ())
    if not kategoriler:
        return [("", ogeler)] if ogeler else []
    sonuc = []
    for ad in (*kategoriler, "Diğer"):
        grup = [o for o in ogeler if getattr(o["repo_cfg"], "kategori", "Diğer") == ad]
        if grup:
            sonuc.append((ad, grup))
    return sonuc


def _yazilar_bolumu(yazilar: Sequence[object], feed: bool = False, dil: str = "tr") -> str:
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
    baslik = f'{_escape_all(m(dil, "yazi_baslik"))}{rss}'
    return _unit("", _ray(baslik, "yazilar") + f'<ul class="yazi-listesi">{"".join(satirlar)}</ul>')


# --- ana sayfa ----------------------------------------------------------------------------

def _toplam_olcer(ayar, veriler: Mapping[str, object | None], dil: str) -> str:
    """Tüm projelerin 12 haftalık commit toplamı (yalnız verisi olan repolar). Hiç veri yoksa boş."""
    toplam: list[int] = []
    for repo in getattr(ayar, "repolar", ()):
        veri = veriler.get(getattr(repo, "ad", "")) if veriler else None
        hafta = getattr(veri, "haftalik", None) if veri is not None else None
        if hafta is None or len(hafta) != 12:
            continue
        toplam = [a + b for a, b in zip(toplam or [0] * 12, hafta)]
    if not toplam:
        return ""
    pencere = _olcer_pencere(SimpleNamespace(haftalik=toplam), dil, eksenli=False)
    return f'<div class="olcer-toplam">{pencere}<p>{_escape_all(m(dil, "olcer_toplam"))}</p></div>'


def _hero(ayar, dil: str, veriler: Mapping[str, object | None] | None = None) -> str:
    sahip = getattr(ayar, "sahip", None)
    h1 = f'<h1>{_escape_all(getattr(sahip, "ad", ""))}</h1>'
    unvan = f'<p class="unvan">{_escape_all(getattr(sahip, "unvan", ""))}</p>' if getattr(sahip, "unvan", "") else ""
    # `hakkinda`: paragraf boşluğunda `\n\n` ile böl, `white-space: pre-wrap` yok
    paragraflar = "".join(
        f'<p class="pitch">{_escape_all(" ".join(parca.split()))}</p>'
        for parca in str(getattr(sahip, "hakkinda", "")).split("\n\n")
        if parca.strip()
    )
    sol = f'<div>{h1}{unvan}{paragraflar}</div>'

    konum = getattr(sahip, "konum", "") or ""  # konum LED değil: sönük LED "kapalı" okunur, düz serigraf yazı
    ledler = "".join(
        f'<li class="led{_led_sinif(getattr(led, "tur", ""))}">{_escape_all(getattr(led, "metin", ""))}</li>'
        for led in list(getattr(sahip, "ledler", ()) or ())
    )
    led_html = f'<ul class="ledler">{ledler}</ul>' if ledler else ""
    konum_html = f'<p class="konum">{_escape_all(konum)}</p>' if konum else ""
    toplam = _toplam_olcer(ayar, veriler or {}, dil)
    cv_not = _cv_not(ayar, dil)
    return _unit(
        "hero",
        f'{sol}<div class="kontrol">{toplam}{led_html}{konum_html}<div class="tuslar">{_hero_dugmeleri(ayar, dil)}</div>{cv_not}</div>',
    )


def _led_sinif(tur: object) -> str:
    return {"eylem": " led--eylem", "acik": " led--acik"}.get(str(tur), "")


def _cv_not(ayar, dil: str) -> str:
    """`.cv-not`: iki dildeki CV'nin tamamı (yollar boşsa listelenmez)."""
    sahip = getattr(ayar, "sahip", None)
    parcalar = []
    for yol_alani, anahtar in (("cv_tr", "cv_tr"), ("cv_en", "cv_en")):
        yol = getattr(sahip, yol_alani, "") or ""
        if yol:
            parcalar.append(
                f'<a href="{_escape_all(yol)}" download>{_escape_all(m(dil, anahtar))}</a>'
            )
    if not parcalar:
        return ""
    return f'<p class="cv-not">{_escape_all(m(dil, "cv_etiket"))} {" · ".join(parcalar)}</p>'


def _hero_dugmeleri(ayar, dil: str) -> str:
    """CV indir, e-posta, GitHub, LinkedIn — yalnız yapılandırmada olanlar."""
    sahip = getattr(ayar, "sahip", None)
    parcalar = [_cv_dugmesi(ayar, dil, kucuk=False)]
    eposta = getattr(sahip, "eposta", "") or ""
    if eposta:
        parcalar.append(
            f'<a class="tus" href="mailto:{_escape_all(eposta)}">{_SVG_ZARF}{_escape_all(m(dil, "eposta"))}</a>'
        )
    github = getattr(sahip, "github", "") or ""
    if github:
        parcalar.append(
            f'<a class="tus" href="https://github.com/{_escape_all(github)}" rel="noopener noreferrer" '
            f'target="_blank">GitHub</a>'
        )
    linkedin = getattr(sahip, "linkedin", "") or ""
    if linkedin:
        parcalar.append(
            f'<a class="tus" href="{_escape_all(linkedin)}" rel="noopener noreferrer" '
            f'target="_blank">LinkedIn</a>'
        )
    return "".join(p for p in parcalar if p)


def _iletisim(ayar, dil: str) -> str:
    sahip = getattr(ayar, "sahip", None)
    eposta = getattr(sahip, "eposta", "") or ""
    dugmeler = []
    if eposta:
        dugmeler.append(f'<a class="tus tus--eylem tus--posta" href="mailto:{_escape_all(eposta)}">{_SVG_ZARF}{_escape_all(eposta)}</a>')
    dugmeler.append(_cv_dugmesi(ayar, dil, kucuk=False))
    for alan, etiket in (("linkedin", "LinkedIn"), ("github", "GitHub")):
        deger = getattr(sahip, alan, "") or ""
        if deger:
            url = f"https://github.com/{deger}" if alan == "github" else deger
            dugmeler.append(
                f'<a class="tus" href="{_escape_all(url)}" rel="noopener noreferrer" '
                f'target="_blank">{etiket}</a>'
            )
    sol = (
        f'<div><h2 id="iletisim">{_escape_all(m(dil, "iletisim_baslik"))}</h2>'
        f'<p>{_escape_all(m(dil, "iletisim_metin"))}</p></div>'
    )
    return _unit("iletisim", f'{sol}<div class="tuslar">{"".join(dugmeler)}</div>')


def render(
    ayar, veriler: Mapping[str, object | None], bugun: date, yazilar: Sequence[object] = (),
    og_gorsel: str | None = None, feed: bool = False,
) -> str:
    """Ana sayfa HTML'ini üretir (şerit, hero, öne çıkanlar, diğer projeler, deneyim, yetenekler, yazılar, iletişim)."""
    dil = getattr(ayar, "dil", "tr") or "tr"
    sahip = getattr(ayar, "sahip", None)
    ad = str(getattr(sahip, "ad", ""))

    hepsi = _ogeler(ayar, veriler)
    oneciler = _sirala(ayar, [o for o in hepsi if getattr(o["repo_cfg"], "one_cikan", False)])
    digerleri = [o for o in hepsi if not getattr(o["repo_cfg"], "one_cikan", False)]

    # `#projeler` rayı: öne çıkan varsa ona, yoksa "Diğer projeler" ünitesine gider
    parcalar = [
        _hero(ayar, dil, veriler),
        _ray(
            _escape_all(m(dil, "oneci_baslik" if oneciler else "diger_baslik")),
            "projeler",
            f"<p>{_escape_all(m(dil, 'oneci_alt'))}</p>" if oneciler else "",
            sinif="ray--raf",
        ),
    ]
    if oneciler:
        parcalar += [_kart_html(o["repo_cfg"], o["veri"], 3, dil) for o in oneciler]

    if _gruplar(ayar, digerleri):
        # "Diğer projeler" başlığı yalnız öne çıkan bölüm varsa ayrı ray olarak durur
        ic = _ray(_escape_all(m(dil, "diger_baslik")), "diger") if oneciler else ""
        parcalar.append(_unit("", ic + _diger_bolum(ayar, digerleri, dil)))

    deneyim = _kayit_bolumu(getattr(ayar, "deneyim", ()), "deneyim_baslik", "deneyim", dil)
    egitim = _kayit_bolumu(getattr(ayar, "egitim", ()), "egitim_baslik", "egitim", dil)
    if deneyim or egitim:
        parcalar.append(f'<div class="iki">{deneyim}{egitim}</div>')

    yetenek = _yetenek_bolumu(ayar, dil)
    if yetenek:
        parcalar.append(yetenek)
    yazi_html = _yazilar_bolumu(yazilar, feed, dil)
    if yazi_html:
        parcalar.append(yazi_html)
    parcalar.append(_iletisim(ayar, dil))

    # Menü yalnız sayfada gerçekten var olan bölümlere bağlanır (ölü bağlantı olmaz)
    bolumler = ["projeler"]
    bolumler += [k for k, v in (("deneyim", deneyim), ("egitim", egitim)) if v]
    if yetenek:
        bolumler.append("yetenekler")
    if yazi_html:
        bolumler.append("yazilar")
    bolumler.append("iletisim")
    return _belge(
        ayar,
        baslik=ad,
        aciklama=_kisalt(getattr(sahip, "hakkinda", "") or getattr(sahip, "unvan", "") or ad),
        url=_sayfa_url(ayar, ""),
        tur="website",
        ust=_serit(ayar, dil, bolumler),
        icerik="".join(parcalar),
        bugun=bugun,
        dil=dil,
        og_gorsel=og_gorsel,
        feed_href="feed.xml" if feed and yazilar else None,
    )


def _kayit_bolumu(kayitlar: Sequence[object], baslik_anahtari: str, kimlik: str, dil: str) -> str:
    """Deneyim ya da eğitim ünitesi; kayıt yoksa boş dize."""
    kayitlar = list(kayitlar or ())
    if not kayitlar:
        return ""
    ic = _ray(_escape_all(m(dil, baslik_anahtari)), kimlik) + "".join(_kayit(k) for k in kayitlar)
    return _unit("", ic)


def _yetenek_bolumu(ayar, dil: str) -> str:
    """Yetenekler ünitesi (`dl.yetenek`); yetenek yoksa boş dize."""
    gruplar = list(getattr(ayar, "yetenekler", ()) or ())
    if not gruplar:
        return ""
    satirlar = "".join(
        f"<div><dt>{_escape_all(getattr(g, 'grup', ''))}</dt>"
        f"<dd>{_escape_all(' · '.join(str(o) for o in (getattr(g, 'ogeler', ()) or ())))}</dd></div>"
        for g in gruplar
    )
    ic = _ray(_escape_all(m(dil, "yetenek_baslik")), "yetenekler") + f'<dl class="yetenek">{satirlar}</dl>'
    return _unit("", ic)


# --- yazı sayfası -------------------------------------------------------------------------

def _okuma_dk(kelime: object) -> int:
    return max(1, round((kelime if isinstance(kelime, int) else 0) / 200))


def _gezinme(onceki: object | None, sonraki: object | None, dil: str) -> str:
    """Yazı sonunda eski/yeni yazıya göreli bağlantılar (aynı `yazilar/` klasörü)."""
    parcalar = []
    if onceki is not None:
        parcalar.append(
            f'<a class="onceki" href="{_escape_all(onceki.slug)}.html" rel="prev">'
            f"← {_escape_all(onceki.baslik)}</a>"
        )
    if sonraki is not None:
        parcalar.append(
            f'<a class="sonraki" href="{_escape_all(sonraki.slug)}.html" rel="next">'
            f"{_escape_all(sonraki.baslik)} →</a>"
        )
    if not parcalar:
        return ""
    return f'<nav class="yazi-gezinme" aria-label="{_escape_all(m(dil, "diger_yazilar"))}">{"".join(parcalar)}</nav>'


def render_yazi(
    ayar, yazi: object, bugun: date, og_gorsel: str | None = None,
    onceki: object | None = None, sonraki: object | None = None, feed: bool = False,
) -> str:
    """Tek yazı sayfası: aynı şerit/CSP/meta, `.geri`, okuma süresi, önceki/sonraki ve `<article>`."""
    dil = "tr"  # yazı sayfaları yalnız Türkçe; dil anahtarı ve bölüm rayı yok
    slug = str(getattr(yazi, "slug", ""))
    tarih = _escape_all(getattr(yazi, "tarih", ""))
    icerik = (
        f'<article><a class="geri" href="../#icerik">{_escape_all(m(dil, "ana_sayfa"))}</a>'
        f'<h1>{_escape_all(getattr(yazi, "baslik", ""))}</h1>'
        f'<p class="yazi-meta"><time datetime="{tarih}">{tarih}</time> · '
        f'{_okuma_dk(getattr(yazi, "kelime", 0))} {_escape_all(m(dil, "dk_okuma"))}</p>'
        f'{getattr(yazi, "govde_html", "")}'  # yazi.markdown_html çıktısıdır (kaçışlı, yalnız izinli etiketler)
        f'{_yigin(getattr(yazi, "etiketler", ()))}{_gezinme(onceki, sonraki, dil)}</article>'
    )
    return _belge(
        ayar,
        baslik=f'{getattr(yazi, "baslik", "")} · {getattr(getattr(ayar, "sahip", None), "ad", "")}',
        aciklama=str(getattr(yazi, "ozet", "")),
        url=_sayfa_url(ayar, f"yazilar/{slug}.html"),
        tur="article",
        # Yazı sayfasında bölüm rayı yok; menü kök-göreli (`../#...`) çalışır
        ust=_serit(ayar, dil, ["projeler", "yazilar", "iletisim"], kok="../"),
        icerik=_unit("yazi", icerik),
        bugun=bugun,
        dil=dil,
        og_gorsel=og_gorsel,
        feed_href="../feed.xml" if feed else None,
    )


def sayfa_url(ayar, yol: str = "") -> str:
    """Mutlak site URL'si; `site_url` yoksa boş dize (meta etiketi yazılmaz)."""
    return _sayfa_url(ayar, yol)


# Kendi kendini denetle: üretilen HTML'in kendi tara()'sını geçmesi gerekir
def _kendi_denetimi(html_metin: str, izinli_eposta: Sequence[str] = ()) -> list:
    """Üretilen HTML'i denetim.tarayıcıdan geçirir (testlerde kullanılır)."""
    return tara(html_metin, izinli_eposta=izinli_eposta)