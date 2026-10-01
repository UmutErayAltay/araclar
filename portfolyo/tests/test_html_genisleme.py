"""html: kategoriler, sıralama, meta etiketleri, favicon, API verisi, yazılar bölümü."""

from __future__ import annotations

import re
from datetime import date
from types import SimpleNamespace

from portfolyo.denetim import tara
from portfolyo.git import RepoVerisi
from portfolyo.html import render
from test_html import _sahte_ayar

BUGUN = date(2026, 10, 1)


def _veri(**kw) -> RepoVerisi:
    d = dict(commit_sayisi=5, ilk_commit=None, son_commit="2026-09-01",
             haftalik=(0,) * 12, diller=(), readme_ozeti=None)
    return RepoVerisi(**{**d, **kw})


def test_kategori_bolumleri_sirayla_ve_bos_olan_cizilmez():
    ayar = _sahte_ayar(
        kategoriler=["Web", "Veri", "Bos"],
        repolar=[{"ad": "v1", "kategori": "Veri"}, {"ad": "w1", "kategori": "Web"}, {"ad": "d1"}],
    )
    cikti = render(ayar, {}, BUGUN)
    basliklar = re.findall(r'<section class="kategori"><h2>([^<]+)</h2>', cikti)
    assert basliklar == ["Web", "Veri", "Diğer"]  # "Bos" yok, "Diğer" en sonda
    assert cikti.index("w1") < cikti.index("v1") < cikti.index("d1")
    assert "<h3 class=\"kart-baslik\"" in cikti


def test_kategorisiz_yapilandirmada_baslik_yok_ve_kart_h2():
    cikti = render(_sahte_ayar(repolar=[{"ad": "a"}]), {}, BUGUN)
    assert 'class="kategori"' not in cikti
    assert '<h2 class="kart-baslik"' in cikti


def test_manuel_siralama_yapilandirma_sirasidir_aktivite_son_commite_gore():
    repolar = [{"ad": "eski"}, {"ad": "yeni"}]
    veriler = {"eski": _veri(son_commit="2025-01-01"), "yeni": _veri(son_commit="2026-09-30")}
    manuel = render(_sahte_ayar(repolar=repolar), veriler, BUGUN)
    assert manuel.index(">eski<") < manuel.index(">yeni<")
    aktivite = render(_sahte_ayar(repolar=repolar, siralama="aktivite"), veriler, BUGUN)
    assert aktivite.index(">yeni<") < aktivite.index(">eski<")


def test_meta_etiketleri_ve_og_url():
    ayar = _sahte_ayar(sahip_ad="Ada Lovelace", sahip_hakkinda="Kısa tanıtım.", site_url="https://ada.github.io")
    cikti = render(ayar, {}, BUGUN)
    assert '<meta name="description" content="Kısa tanıtım.">' in cikti
    assert '<meta property="og:title" content="Ada Lovelace">' in cikti
    assert '<meta property="og:type" content="website">' in cikti
    assert '<meta property="og:url" content="https://ada.github.io/">' in cikti
    assert '<meta property="og:locale" content="tr_TR">' in cikti
    assert '<meta name="twitter:card" content="summary">' in cikti
    assert "og:image" not in cikti


def test_og_url_yoksa_etiket_yok():
    assert "og:url" not in render(_sahte_ayar(), {}, BUGUN)


def test_meta_degerleri_kacislanir():
    ayar = _sahte_ayar(sahip_ad='A"><script>x</script>', sahip_hakkinda='"><img src=x onerror=y>')
    cikti = render(ayar, {}, BUGUN)
    assert "<script>" not in cikti and "<img" not in cikti
    assert tara(cikti) == []


def test_favicon_data_svg_ve_denetimden_gecer():
    cikti = render(_sahte_ayar(sahip_ad="umut"), {}, BUGUN)
    m = re.search(r'<link rel="icon" href="(data:image/svg\+xml,[^"]+)">', cikti)
    assert m and "%3EU%3C" in m.group(1)  # büyük harf monogram
    assert cikti.count("<link") == 1
    assert tara(cikti) == []


def test_favicon_ad_harfi_kacislanir():
    cikti = render(_sahte_ayar(sahip_ad="<b>"), {}, BUGUN)
    assert tara(cikti) == []
    assert "%3Cb%3E" not in re.search(r'rel="icon" href="([^"]+)"', cikti).group(1)


def test_api_verisi_yuzde_gosterir_haftalik_none_grafik_cizmez():
    ayar = _sahte_ayar(repolar=[{"ad": "r"}])
    cikti = render(ayar, {"r": _veri(diller=(("Python", 72), ("CSS", 28)), dil_birimi="yuzde", haftalik=None)}, BUGUN)
    assert "Python · %72" in cikti and "CSS · %28" in cikti
    assert "<svg class=\"etkinlik-svg\"" not in cikti


def test_klon_verisi_dosya_sayisi_ve_grafik():
    ayar = _sahte_ayar(repolar=[{"ad": "r"}])
    cikti = render(ayar, {"r": _veri(diller=(("Python", 7),), haftalik=(1,) * 12)}, BUGUN)
    assert "Python · 7" in cikti and "%7" not in cikti
    assert "<svg class=\"etkinlik-svg\"" in cikti


def test_yazilar_bolumu_tarih_azalan_ve_kacisli():
    y = lambda slug, baslik, tarih: SimpleNamespace(slug=slug, baslik=baslik, tarih=tarih, ozet="Özet <b>", etiketler=())
    cikti = render(_sahte_ayar(), {}, BUGUN, [y("eski", "Eski", "2026-01-01"), y("yeni", "Yeni", "2026-09-01")])
    assert '<section class="yazilar"><h2>Yazılar</h2>' in cikti
    assert cikti.index("yazilar/yeni.html") < cikti.index("yazilar/eski.html")
    assert "Özet &lt;b&gt;" in cikti and "Özet <b>" not in cikti


def test_yazi_yoksa_bolum_yok():
    assert "Yazılar" not in render(_sahte_ayar(), {}, BUGUN)
    assert "Yazılar" not in render(_sahte_ayar(), {}, BUGUN, [])
