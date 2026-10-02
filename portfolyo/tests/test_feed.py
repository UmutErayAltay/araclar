"""feed (Atom), besleme bağlantısı kuralı, önceki/sonraki, okuma süresi ve CLI entegrasyonu."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import date
from types import SimpleNamespace

import pytest

from portfolyo import cli, feed
from portfolyo.denetim import tara
from portfolyo.html import render, render_yazi
from test_cli import REPO, _ayar
from test_html import _sahte_ayar

ATOM = "{http://www.w3.org/2005/Atom}"
BUGUN = date(2026, 10, 2)


def _y(slug, baslik="Başlık", tarih="2026-10-01", ozet="Özet", kelime=400):
    return SimpleNamespace(slug=slug, baslik=baslik, tarih=tarih, ozet=ozet, etiketler=(), govde_html="<p>x</p>", kelime=kelime)


# --- atom_uret --------------------------------------------------------------------------

def test_atom_gecerli_xml_sirali_ve_mutlak():
    ayar = _sahte_ayar(site_url="https://u.github.io")
    xml = feed.atom_uret(ayar, [_y("eski", "Eski", "2026-01-01"), _y("yeni", "Yeni", "2026-09-30")])
    kok = ET.fromstring(xml)
    assert kok.tag == ATOM + "feed"
    assert kok.find(ATOM + "id").text == "https://u.github.io/"
    assert kok.find(ATOM + "updated").text == "2026-09-30T00:00:00Z"
    girdiler = kok.findall(ATOM + "entry")
    assert [g.find(ATOM + "title").text for g in girdiler] == ["Yeni", "Eski"]
    assert girdiler[0].find(ATOM + "id").text == "https://u.github.io/yazilar/yeni.html"
    self_link = [l for l in kok.findall(ATOM + "link") if l.get("rel") == "self"][0]
    assert self_link.get("href") == "https://u.github.io/feed.xml"


def test_atom_yoksa_none():
    assert feed.atom_uret(_sahte_ayar(site_url=""), [_y("a")]) is None   # site_url yok
    assert feed.atom_uret(_sahte_ayar(site_url="https://u.github.io"), []) is None  # yazı yok


def test_atom_kacislar_ve_tum_kontrol_gecer():
    ayar = _sahte_ayar(site_url="https://u.github.io", sahip_ad="A & <B>")
    xml = feed.atom_uret(ayar, [_y("a", '<script>x</script> & "q"', ozet="<b>özet</b>")])
    kok = ET.fromstring(xml)  # kaçış bozuk olsaydı ayrıştırma patlardı
    assert kok.find(ATOM + "entry").find(ATOM + "title").text == '<script>x</script> & "q"'
    assert "<script>" not in xml and "<b>" not in xml
    assert tara(xml, link_denetimi=False) == []


# --- denetim: besleme <link> kuralı -----------------------------------------------------

@pytest.mark.parametrize("href", ["feed.xml", "../feed.xml"])
def test_feed_linki_gecer(href):
    assert tara(f'<link rel="alternate" type="application/atom+xml" href="{href}" title="Ad · Yazılar">') == []


@pytest.mark.parametrize(
    "etiket",
    [
        '<link rel="alternate" type="application/atom+xml" href="https://x.example/feed.xml" title="a">',
        '<link rel="alternate" type="application/atom+xml" href="//x.example/feed.xml" title="a">',
        '<link rel="alternate" type="application/rss+xml" href="feed.xml" title="a">',
        '<link rel="alternate" type="application/atom+xml" href="baska.xml" title="a">',
        '<link rel="alternate" type="application/atom+xml" href="../../feed.xml" title="a">',
        '<link rel="alternate" type="application/atom+xml" href="feed.xml" title="a" onload="x">',
        '<link rel="stylesheet" href="feed.xml">',
    ],
)
def test_baska_link_bulgu(etiket):
    assert [b.tur for b in tara(etiket)] == ["dis-kaynak"]


def test_link_denetimi_kapaliyken_digerleri_calisir():
    assert tara('<link rel="x"/>', link_denetimi=False) == []
    assert [b.tur for b in tara("<script>", link_denetimi=False)] == ["dis-kaynak"]


# --- html: gezinme, okuma süresi, besleme bağlantısı -------------------------------------

def test_yazi_sayfasi_okuma_suresi_ve_gezinme():
    ayar = _sahte_ayar(site_url="https://u.github.io")
    a, b, c = _y("a", "A", kelime=100), _y("b", "B", kelime=1000), _y("c", "C", kelime=0)
    orta = render_yazi(ayar, b, BUGUN, onceki=a, sonraki=c, feed=True)
    assert "5 dk okuma" in orta
    assert 'class="onceki" href="a.html" rel="prev">← A</a>' in orta
    assert 'class="sonraki" href="c.html" rel="next">C →</a>' in orta
    assert '<link rel="alternate" type="application/atom+xml" href="../feed.xml"' in orta
    assert "1 dk okuma" in render_yazi(ayar, c, BUGUN)  # en az 1
    ilk = render_yazi(ayar, a, BUGUN, sonraki=b)
    assert "rel=\"prev\"" not in ilk and "rel=\"next\"" in ilk
    assert 'class="yazi-gezinme"' not in render_yazi(ayar, a, BUGUN)
    assert tara(orta) == []


def test_gezinme_basliklari_kacislanir():
    ayar = _sahte_ayar()
    h = render_yazi(ayar, _y("x"), BUGUN, onceki=_y("o", "<img src=x>"))
    assert "<img" not in h and "&lt;img src=x&gt;" in h


def test_ana_sayfa_besleme_baglantisi_yalniz_istenince():
    ayar = _sahte_ayar(site_url="https://u.github.io")
    acik = render(ayar, {}, BUGUN, [_y("a")], feed=True)
    assert '<a class="feed" href="feed.xml">RSS</a>' in acik
    assert '<link rel="alternate" type="application/atom+xml" href="feed.xml"' in acik
    assert tara(acik) == []
    kapali = render(ayar, {}, BUGUN, [_y("a")])
    assert 'class="feed"' not in kapali and "atom+xml" not in kapali


# --- CLI ---------------------------------------------------------------------------------

GECERLI = """---
baslik: {b}
tarih: {t}
ozet: Özet.
etiketler: [python]
herkese_acik: true
---
{govde}
"""


def _kur(tmp_path, yazilar, site_url="https://testuser.github.io"):
    ayar = _ayar(tmp_path, [REPO], **({"site_url": site_url} if site_url else {}))
    yz = tmp_path / "yazilar"
    yz.mkdir(exist_ok=True)
    for slug, b, t in yazilar:
        (yz / f"{slug}.md").write_text(GECERLI.format(b=b, t=t, govde="kelime " * 450), encoding="utf-8")
    cikti = tmp_path / "site"
    return cli.main(["uret", str(ayar), "--cikti", str(cikti), "--bugun", "2026-10-02", "--yazilar", str(yz)]), cikti


def test_cli_feed_yazilir_ve_sayfalar_baglanir(tmp_path):
    kod, cikti = _kur(tmp_path, [("birinci", "Birinci", "2026-01-01"), ("ikinci", "İkinci", "2026-02-01"), ("ucuncu", "Üçüncü", "2026-03-01")])
    assert kod == 0
    kok = ET.fromstring((cikti / "feed.xml").read_text(encoding="utf-8"))
    assert [e.find(ATOM + "title").text for e in kok.findall(ATOM + "entry")] == ["Üçüncü", "İkinci", "Birinci"]
    orta = (cikti / "yazilar" / "ikinci.html").read_text(encoding="utf-8")
    assert 'href="birinci.html" rel="prev"' in orta and 'href="ucuncu.html" rel="next"' in orta  # önceki=daha eski
    assert "2 dk okuma" in orta
    ilk = (cikti / "yazilar" / "ucuncu.html").read_text(encoding="utf-8")  # en yeni: sonraki yok
    assert 'rel="next"' not in ilk and 'rel="prev"' in ilk
    assert "feed.xml" in (cikti / "index.html").read_text(encoding="utf-8")


def test_cli_site_url_yoksa_besleme_yok(tmp_path):
    kod, cikti = _kur(tmp_path, [("a", "A", "2026-01-01")], site_url=None)
    assert kod == 0 and not (cikti / "feed.xml").exists()
    assert "atom+xml" not in (cikti / "index.html").read_text(encoding="utf-8")


def test_cli_feed_icin_de_tek_bulguda_hicbir_sey_yazilmaz(tmp_path):
    ayar = _ayar(tmp_path, [REPO], site_url="https://testuser.github.io")
    yz = tmp_path / "yazilar"
    yz.mkdir()
    (yz / "a.md").write_text(GECERLI.format(b="Başlık", t="2026-01-01", govde="Yol: /home/umut/x"), encoding="utf-8")
    cikti = tmp_path / "site"
    assert cli.main(["uret", str(ayar), "--cikti", str(cikti), "--yazilar", str(yz)]) == 4
    assert not cikti.exists()
