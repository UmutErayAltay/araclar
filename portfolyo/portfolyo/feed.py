"""Yazılar için Atom 1.0 beslemesi (`feed.xml`). Yalnız mutlak `site_url` ve en az bir yazı varsa üretilir."""

from __future__ import annotations

import html
from collections.abc import Sequence

from .html import sayfa_url


def _k(metin: object) -> str:
    return html.escape(str(metin), quote=True)


def atom_uret(ayar, yazilar: Sequence[object]) -> str | None:
    """Atom metnini döndürür; `site_url` ya da yazı yoksa None (besleme ve `<link>` hiç yazılmaz)."""
    site = sayfa_url(ayar)
    if not site or not yazilar:
        return None
    sahip = ayar.sahip
    sirali = sorted(yazilar, key=lambda y: (y.tarih, y.slug), reverse=True)
    giris = []
    for y in sirali:
        adres = sayfa_url(ayar, f"yazilar/{y.slug}.html")
        giris.append(
            "  <entry>\n"
            f"    <title>{_k(y.baslik)}</title>\n"
            f"    <id>{_k(adres)}</id>\n"
            f'    <link rel="alternate" type="text/html" href="{_k(adres)}"/>\n'
            f"    <updated>{_k(y.tarih)}T00:00:00Z</updated>\n"
            f"    <summary>{_k(y.ozet)}</summary>\n"
            "  </entry>\n"
        )
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<feed xmlns="http://www.w3.org/2005/Atom" xml:lang="tr">\n'
        f"  <title>{_k(sahip.ad)} · Yazılar</title>\n"
        f"  <id>{_k(site)}</id>\n"
        f'  <link rel="self" type="application/atom+xml" href="{_k(sayfa_url(ayar, "feed.xml"))}"/>\n'
        f'  <link rel="alternate" type="text/html" href="{_k(site)}"/>\n'
        f"  <updated>{_k(sirali[0].tarih)}T00:00:00Z</updated>\n"
        f"  <author><name>{_k(sahip.ad)}</name></author>\n"
        + "".join(giris)
        + "</feed>\n"
    )
