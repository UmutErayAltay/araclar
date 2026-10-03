"""portfolyo.html testleri: Cihaz Rafı yapısı, meta, favicon, denetim, escaping."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import date
from types import SimpleNamespace

import pytest

from portfolyo.denetim import tara
from portfolyo.html import render, render_yazi, sayfa_url
from portfolyo.metin import m


@dataclass
class SahteRepoVerisi:
    """Test için sahte RepoVerisi."""
    commit_sayisi: int = 10
    ilk_commit: str | None = "2024-01-01"
    son_commit: str | None = "2024-06-15"
    haftalik: tuple[int, ...] | None = None
    diller: tuple[tuple[str, int], ...] | None = None
    readme_ozeti: str | None = "Bu bir test README özeti."


def _sahhte_led(metin: str, tur: str = "") -> SimpleNamespace:
    return SimpleNamespace(metin=metin, tur=tur)


def _sahte_ayar(**kwargs) -> SimpleNamespace:
    """Test için sahte ayar nesnesi oluşturur.

    Yeni alanlar (dil, deneyim, eğitim, yetenekler, CV, LED...) ayar.py'de henüz
    tanımlı olmayabilir; bu yüzden hepsi isteğe bağlı varsayılanlıdır.
    """
    sahip = SimpleNamespace(
        ad=kwargs.get("sahip_ad", "Test Kullanıcı"),
        unvan=kwargs.get("sahip_unvan", "Geliştirici"),
        github=kwargs.get("sahip_github", "testuser"),
        hakkinda=kwargs.get("sahip_hakkinda", "Test hakkındayım.\nİkinci satır."),
        site_url=kwargs.get("site_url", ""),
        eposta=kwargs.get("sahip_eposta", ""),
        linkedin=kwargs.get("sahip_linkedin", ""),
        konum=kwargs.get("sahip_konum", ""),
        cv_tr=kwargs.get("sahip_cv_tr", ""),
        cv_en=kwargs.get("sahip_cv_en", ""),
        ledler=kwargs.get("sahip_ledler", ()),
    )
    repolar = []
    for r in kwargs.get("repolar", [{}]):
        repo = SimpleNamespace(
            ad=r.get("ad", "test-repo"),
            aciklama=r.get("aciklama", "Test açıklaması"),
            url=r.get("url", "https://github.com/testuser/test-repo"),
            etiketler=r.get("etiketler", ["python", "test"]),
            kategori=r.get("kategori", "Diğer"),
            one_cikan=r.get("one_cikan", False),
            baglantilar=r.get("baglantilar", ()),
        )
        repolar.append(repo)
    return SimpleNamespace(
        sahip=sahip,
        repolar=repolar,
        kategoriler=tuple(kwargs.get("kategoriler", ())),
        siralama=kwargs.get("siralama", "manuel"),
        dil=kwargs.get("dil", "tr"),
        dil_baglantisi=kwargs.get("dil_baglantisi", ""),
        deneyim=list(kwargs.get("deneyim", ())),
        egitim=list(kwargs.get("egitim", ())),
        yetenekler=list(kwargs.get("yetenekler", ())),
    )


def _veri(**kw) -> SahteRepoVerisi:
    d = dict(commit_sayisi=5, ilk_commit=None, son_commit="2026-09-01",
             haftalik=(0,) * 12, diller=(), readme_ozeti=None)
    return SahteRepoVerisi(**{**d, **kw})


BUGUN = date(2026, 10, 1)


# --- temel üretim -------------------------------------------------------------------------

def test_temel_uretim_calisir():
    cikti = render(_sahte_ayar(), {"test-repo": SahteRepoVerisi()}, BUGUN)
    assert cikti.startswith("<!doctype html>")
    assert '<html lang="tr">' in cikti
    assert '<meta charset="utf-8">' in cikti
    assert 'name="viewport"' in cikti
    assert "Test Kullanıcı" in cikti and "test-repo" in cikti
    assert "Otomatik üretildi: 2026-10-01" in cikti


def test_raf_yapisi_ve_serit_main_disi():
    cikti = render(_sahte_ayar(), {}, BUGUN)
    serit = cikti.index('<header class="serit">')
    main = cikti.index('<main class="raf" id="icerik">')
    assert serit < main < cikti.index('<p class="alt-not">')
    assert cikti.count("<main") == 1
    assert '<a class="skip" href="#icerik">' in cikti


def test_marka_noktali_bas_harfler():
    cikti = render(_sahte_ayar(sahip_ad="Umut Eray Altay"), {}, BUGUN)
    assert 'class="marka" href="#icerik">U.E.A</a>' in cikti


def _baslik_seviyeleri(cikti: str) -> list[int]:
    return [int(t[1]) for t in re.findall("<(h[1-6])[ >]", cikti)]


def test_tek_h1_ve_baslik_sirasi():
    ayar = _sahte_ayar(
        repolar=[{"ad": "bir", "one_cikan": True}, {"ad": "iki", "kategori": "Web"}],
        kategoriler=("Web",),
        deneyim=[SimpleNamespace(rol="Stajyer", kurum="X", tarih="2024")],
        egitim=[SimpleNamespace(derece="Muhendis", okul="BMU", tarih="2024")],
        yetenekler=[SimpleNamespace(grup="Diller", ogeler=("Python",))],
    )
    cikti = render(ayar, {}, BUGUN)
    seviyeler = _baslik_seviyeleri(cikti)
    assert seviyeler.count(1) == 1
    assert seviyeler[0] == 1, "h1 sayfada ilk başlık olmalı"
    # Başlıklar bir seviye atlayamaz (h2 -> h4 gibi)
    atlanan = [(a, b) for a, b in zip(seviyeler, seviyeler[1:]) if b - a > 1]
    assert atlanan == [], f"atlanan seviye: {atlanan}"


def test_dekoratif_kulaklar_aria_hidden():
    cikti = render(_sahte_ayar(), {}, BUGUN)
    assert cikti.count('<i class="kulak" aria-hidden="true"></i>') >= 2


# --- CSP ve güvenlik ----------------------------------------------------------------------

def test_csp_meta_var():
    cikti = render(_sahte_ayar(), {}, BUGUN)
    assert "default-src 'none'" in cikti
    assert "style-src 'unsafe-inline'" in cikti
    assert "img-src data:" in cikti
    assert "font-src 'self'" in cikti
    assert "base-uri 'none'" in cikti
    assert "form-action 'none'" in cikti


def test_hic_javascript_ve_dis_stil_dosyasi_yok():
    cikti = render(_sahte_ayar(), {}, BUGUN)
    assert "<script" not in cikti.lower()
    assert 'rel="stylesheet"' not in cikti
    assert "<link" not in cikti.replace('<link rel="icon"', "").replace(
        '<link rel="alternate"', ""
    )


def test_denetim_kendi_sifir_bulgu():
    ayar = _sahte_ayar(
        sahip_eposta="umut@example.com",
        sahip_linkedin="https://www.linkedin.com/in/x",
        sahip_cv_tr="cv/tr.pdf", sahip_cv_en="cv/en.pdf",
        sahip_konum="Bursa", sahip_ledler=[_sahhte_led("İş arıyorum", "eylem")],
        repolar=[{"ad": "bir", "one_cikan": True}, {"ad": "iki"}],
        kategoriler=("Web", "Diğer"),
        deneyim=[SimpleNamespace(rol="Stajyer", kurum="X", tarih="2024", aciklama="Y")],
        egitim=[SimpleNamespace(derece="Muhendis", okul="BMU", tarih="2020-2024", ek="")],
        yetenekler=[SimpleNamespace(grup="Diller", ogeler=("Python",))],
    )
    veri = {"bir": _veri(haftalik=(0,) * 11 + (3,))}
    cikti = render(ayar, veri, BUGUN)
    assert tara(cikti, izinli_eposta=["umut@example.com"]) == []


def test_xss_kacis_tum_alanlar():
    xss = '<script>alert(1)</script>'
    xss2 = '"><img src=x onerror=alert(1)>'
    ayar = _sahte_ayar(
        sahip_ad=xss, sahip_unvan=xss2, sahip_hakkinda=xss,
        repolar=[{"ad": xss, "aciklama": xss2, "url": "https://github.com/t/t",
                  "etiketler": [xss, xss2]}],
    )
    cikti = render(ayar, {}, BUGUN)
    assert xss not in cikti and xss2 not in cikti
    assert html.escape(xss, quote=True) in cikti
    assert html.escape(xss2, quote=True) in cikti
    assert tara(cikti) == []


# --- meta ---------------------------------------------------------------------------------

def test_meta_etiketleri_ve_og_url():
    ayar = _sahte_ayar(sahip_ad="Ada Lovelace", sahip_hakkinda="Kısa tanıtım.",
                       site_url="https://ada.github.io")
    cikti = render(ayar, {}, BUGUN)
    assert '<meta name="description" content="Kısa tanıtım.">' in cikti
    assert '<meta property="og:title" content="Ada Lovelace">' in cikti
    assert '<meta property="og:type" content="website">' in cikti
    assert '<meta property="og:url" content="https://ada.github.io/">' in cikti
    assert '<meta property="og:locale" content="tr_TR">' in cikti
    assert '<meta name="twitter:card" content="summary">' in cikti
    assert 'name="theme-color" content="#b3afa4"' in cikti
    assert 'name="theme-color" content="#08090a"' in cikti
    assert "og:image" not in cikti


def test_og_url_yoksa_etiket_yok():
    assert "og:url" not in render(_sahte_ayar(), {}, BUGUN)


def test_meta_degerleri_kacislanir():
    cikti = render(_sahte_ayar(sahip_ad='A"><script>x</script>',
                                sahip_hakkinda='"><img src=x onerror=y>'), {}, BUGUN)
    assert "<script>" not in cikti and "<img" not in cikti
    assert tara(cikti) == []


# --- favicon ------------------------------------------------------------------------------

def test_favicon_data_svg_ve_denetimden_gecer():
    cikti = render(_sahte_ayar(sahip_ad="umut"), {}, BUGUN)
    m = re.search(r'<link rel="icon" href="(data:image/svg\+xml,[^"]+)">', cikti)
    assert m and "%3EU%3C" in m.group(1)
    assert cikti.count("<link") == 1
    assert tara(cikti) == []


def test_favicon_kare_renkleri_ve_kacis():
    cikti = render(_sahte_ayar(sahip_ad="<b>"), {}, BUGUN)
    ikon = re.search(r'rel="icon" href="([^"]+)"', cikti).group(1)
    assert "%3Cb%3E" not in ikon
    assert "#1b1c1e" in cikti and "#e8a317" in cikti


# --- projeler: öne çıkan / satır ------------------------------------------------------------

def test_one_cikan_unit_ve_digerleri_satir():
    ayar = _sahte_ayar(repolar=[{"ad": "bir", "one_cikan": True}, {"ad": "iki"}])
    cikti = render(ayar, {}, BUGUN)
    assert 'class="unit one"' in cikti
    assert cikti.count('class="satir"') == 1
    assert '<h3 class="pr-ad">' in cikti
    assert "<h4>" in cikti


def test_one_cikan_yoksa_bolum_cikmaz_hepsi_satir():
    cikti = render(_sahte_ayar(repolar=[{"ad": "a"}, {"ad": "b"}]), {}, BUGUN)
    assert 'class="unit one"' not in cikti
    assert m("tr", "oneci_baslik") not in cikti
    assert cikti.count('class="satir"') == 2
    assert m("tr", "diger_baslik") in cikti


def test_one_cikan_yapilandirma_sirasini_korur():
    repolar = [{"ad": "a", "one_cikan": True}, {"ad": "b", "one_cikan": True}]
    cikti = render(_sahte_ayar(repolar=repolar), {}, BUGUN)
    assert cikti.index(">a<") < cikti.index(">b<")


# --- etiket dengesi (kapanışı unutulan <a> açıklamayı bağlantıya çevirmişti) -------------------

def _dengesiz_etiketler(sayfa: str) -> list[str]:
    from html.parser import HTMLParser

    bos = {"meta", "link", "br", "img", "input", "hr", "path", "rect"}
    yigin: list[str] = []
    sorunlar: list[str] = []

    class P(HTMLParser):
        def handle_starttag(self, tag, attrs):
            if tag not in bos:
                yigin.append(tag)

        def handle_startendtag(self, tag, attrs):
            pass

        def handle_endtag(self, tag):
            if tag in bos:
                return
            if not yigin or yigin[-1] != tag:
                sorunlar.append(f"</{tag}> beklenmiyordu (açık: {yigin[-3:]})")
                if tag in yigin:
                    while yigin and yigin.pop() != tag:
                        pass
            else:
                yigin.pop()

    P().feed(sayfa)
    return sorunlar + [f"<{t}> kapanmadı" for t in yigin]


def test_tum_bolumlerle_etiketler_dengeli():
    ayar = _sahte_ayar(
        repolar=[
            {"ad": "bir", "one_cikan": True, "kategori": "K"},
            {"ad": "iki", "kategori": "K"},
        ],
        kategoriler=["K"],
        sahip_eposta="a@b.co", sahip_cv_tr="/cv/a.pdf", sahip_cv_en="/cv/b.pdf",
        sahip_konum="Bursa", sahip_ledler=[_sahhte_led("İş arıyorum", "eylem")],
        dil_baglantisi="/en/",
        deneyim=[SimpleNamespace(rol="r", kurum="k", tarih="t", aciklama="a")],
        egitim=[SimpleNamespace(derece="d", okul="o", tarih="t", ek="e")],
        yetenekler=[SimpleNamespace(grup="g", ogeler=("x", "y"))],
    )
    assert _dengesiz_etiketler(render(ayar, {"bir": _veri(), "iki": _veri()}, BUGUN)) == []


def test_one_cikan_baslik_baglantisi_kapanir():
    cikti = render(_sahte_ayar(repolar=[{"ad": "bir", "one_cikan": True}]), {}, BUGUN)
    assert re.search(r'<h3 class="pr-ad"><a [^>]*>bir</a></h3>', cikti)


def test_konum_led_degil_duz_yazidir():
    ayar = _sahte_ayar(sahip_konum="Bursa", sahip_ledler=[_sahhte_led("İş arıyorum", "eylem")])
    cikti = render(ayar, {}, BUGUN)
    assert '<p class="konum">Bursa</p>' in cikti
    assert ">Bursa</li>" not in cikti


def test_repo_led_ve_toplam_olcer():
    ayar = _sahte_ayar(repolar=[{"ad": "bir", "one_cikan": True}, {"ad": "iki"}])
    ayar.repolar[0].led = SimpleNamespace(metin="Yerelde çalışır", tur="acik")
    veriler = {"bir": _veri(haftalik=(1,) * 12), "iki": _veri(haftalik=(2,) * 12)}
    cikti = render(ayar, veriler, BUGUN)
    assert '<ul class="ledler pr-durum"><li class="led led--acik">Yerelde çalışır</li></ul>' in cikti
    assert 'class="olcer-toplam"' in cikti
    assert "3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3" in cikti  # 1 + 2 toplamı
    assert 'class="olcer-toplam"' not in render(ayar, {}, BUGUN)  # veri yoksa toplam ölçer yok


def test_kategori_basliklari_h3_alt_ve_satirlar():
    ayar = _sahte_ayar(
        kategoriler=("Web", "Veri", "Bos"),
        repolar=[{"ad": "v1", "kategori": "Veri"}, {"ad": "w1", "kategori": "Web"}, {"ad": "d1"}],
    )
    cikti = render(ayar, {}, BUGUN)
    basliklar = [b for b in ("Web", "Veri", "Diğer") if f'<h3 class="alt">{b}</h3>' in cikti]
    assert basliklar == ["Web", "Veri", "Diğer"]
    assert '<h3 class="alt">Bos</h3>' not in cikti
    assert cikti.count('<div class="satirlar">') == 3
    assert cikti.index(">w1<") < cikti.index(">v1<") < cikti.index(">d1<")


def test_kategorisiz_yapilandirmada_grup_basligi_yok():
    cikti = render(_sahte_ayar(repolar=[{"ad": "a"}]), {}, BUGUN)
    assert '<h3 class="alt">' not in cikti
    assert '<div class="satirlar">' in cikti


def test_manuel_siralama_yapilandirma_sirasidir_aktivite_son_commite_gore():
    repolar = [{"ad": "eski"}, {"ad": "yeni"}]
    veriler = {"eski": _veri(son_commit="2025-01-01"), "yeni": _veri(son_commit="2026-09-30")}
    manuel = render(_sahte_ayar(repolar=repolar), veriler, BUGUN)
    assert manuel.index(">eski<") < manuel.index(">yeni<")
    aktivite = render(_sahte_ayar(repolar=repolar, siralama="aktivite"), veriler, BUGUN)
    assert aktivite.index(">yeni<") < aktivite.index(">eski<")


# --- ölçer ---------------------------------------------------------------------------------

def test_veri_none_olcer_ve_commit_sayisi_yok():
    ayar = _sahte_ayar(repolar=[{"ad": "r"}])
    cikti = render(ayar, {"r": None}, BUGUN)
    assert "<svg" not in cikti
    assert 'class="olcer-pencere"' not in cikti
    assert 'class="sayi"' not in cikti
    assert "hiç commit yok" not in cikti


def test_haftalik_none_grafik_cizmez():
    ayar = _sahte_ayar(repolar=[{"ad": "r"}])
    cikti = render(ayar, {"r": _veri(haftalik=None)}, BUGUN)
    assert "<svg" not in cikti
    assert "<b>5</b>" in cikti  # sayı/tarih yine durur


def test_olcer_izgara_ve_aria_label():
    haftalik = (0, 1, 2, 0, 5, 3, 0, 0, 1, 0, 0, 0)
    ayar = _sahte_ayar(repolar=[{"ad": "r", "one_cikan": True}])
    cikti = render(ayar, {"r": _veri(haftalik=haftalik)}, BUGUN)
    assert '<path class="izgara" d="M0 10H96M0 20H96M0 30H96"/>' in cikti
    assert 'aria-label="Son 12 haftada commit sayısı: 0, 1, 2, 0, 5, 3, 0, 0, 1, 0, 0, 0"' in cikti


def test_olcer_hepsi_sifir_duz_cizgi():
    ayar = _sahte_ayar(repolar=[{"ad": "r", "one_cikan": True}])
    cikti = render(ayar, {"r": _veri(haftalik=(0,) * 12)}, BUGUN)
    assert 'aria-label="Son 12 haftada commit sayısı: hiç commit yok"' in cikti
    assert 'opacity="0.3"' in cikti


def test_olcer_ekseni_yalniz_one_unitede():
    one = render(_sahte_ayar(repolar=[{"ad": "r", "one_cikan": True}]),
                 {"r": _veri(haftalik=(1,) * 12)}, BUGUN)
    satir = render(_sahte_ayar(repolar=[{"ad": "r"}]), {"r": _veri(haftalik=(1,) * 12)}, BUGUN)
    assert 'class="olcer-eksen"' in one
    assert 'class="olcer-eksen"' not in satir


def test_diller_yuzde_ve_dosya_birimi_cikmaz_artik():
    """Dil yığını yeni rafta yok; yalnız ölçer ve sayı kalır."""
    ayar = _sahte_ayar(repolar=[{"ad": "r"}])
    cikti = render(ayar, {"r": _veri(diller=(("Python", 72),))}, BUGUN)
    assert "Python · %72" not in cikti


# --- hero, deneyim, eğitim, yetenekler --------------------------------------------------------

def test_hero_pitch_paragraflari_ayrilir():
    cikti = render(_sahte_ayar(sahip_hakkinda="Satır 1\nSatır 2\n\nSatır 3"), {}, BUGUN)
    assert cikti.count('<p class="pitch">') == 2
    assert "white-space: pre-wrap" not in cikti
    assert "Satır 3" in cikti


def test_led_siniflari():
    ayar = _sahte_ayar(sahip_ledler=[_sahhte_led("A", "eylem"), _sahhte_led("B", "acik"),
                                     _sahhte_led("C"), _sahhte_led("D", "kapali")],
                        sahip_konum="Bursa")
    cikti = render(ayar, {}, BUGUN)
    assert 'class="led led--eylem">A</li>' in cikti
    assert 'class="led led--acik">B</li>' in cikti
    assert 'class="led">C</li>' in cikti
    assert 'class="led">D</li>' in cikti
    assert '<p class="konum">Bursa</p>' in cikti


def test_iki_kolon_deneyim_ve_egitim():
    ayar = _sahte_ayar(
        deneyim=[SimpleNamespace(rol="Yazılım stajyeri", kurum="Ünver", tarih="2024", aciklama="Bot geliştirdim.")],
        egitim=[SimpleNamespace(derece="Bilgisayar mühendisliği", okul="BMU", tarih="2020 – 2024",
                                ek="Not 3.4 / 4.0")],
    )
    cikti = render(ayar, {}, BUGUN)
    assert '<div class="iki">' in cikti
    assert 'id="deneyim"' in cikti and 'id="egitim"' in cikti
    assert "<h3>Yazılım stajyeri</h3>" in cikti
    assert '<p class="kurum">Ünver</p>' in cikti
    assert '<span class="tarih">2020 – 2024</span><span class="ek">Not 3.4 / 4.0</span>' in cikti
    assert 'class="yetenek"' not in cikti


def test_yetenekler_bos_kategori_yok():
    cikti = render(_sahte_ayar(
        yetenekler=[SimpleNamespace(grup="Diller", ogeler=("Python", "Go"))]), {}, BUGUN)
    assert 'id="yetenekler"' in cikti
    assert "<dt>Diller</dt><dd>Python · Go</dd>" in cikti


def test_bolumler_yoksa_menu_ve_bolum_gorunmez():
    cikti = render(_sahte_ayar(repolar=[{"ad": "a"}]), {}, BUGUN)
    assert 'href="#deneyim"' not in cikti and 'id="deneyim"' not in cikti
    assert 'href="#yetenekler"' not in cikti and 'id="yetenekler"' not in cikti
    assert 'href="#projeler"' in cikti and 'id="projeler"' in cikti


# --- iletişim / CV --------------------------------------------------------------------------

def test_cv_yolu_bosken_indirme_dugmesi_yok():
    cikti = render(_sahte_ayar(), {}, BUGUN)
    assert " download" not in cikti
    assert "CV indir" not in cikti


def test_cv_dugmeleri_ve_cv_not():
    ayar = _sahte_ayar(sahip_cv_tr="cv/tr.pdf", sahip_cv_en="cv/en.pdf")
    cikti = render(ayar, {}, BUGUN)
    assert '<a class="tus tus--eylem" href="cv/tr.pdf" download>' in cikti
    assert "CV indir" in cikti
    assert '<a href="cv/en.pdf" download>' in cikti
    assert '<p class="cv-not">CV: <a href="cv/tr.pdf" download>Türkçe (PDF)</a>' in cikti
    assert "English (PDF)" in cikti


def test_cv_not_yalniz_tanimli_yollar():
    cikti = render(_sahte_ayar(sahip_cv_en="cv/en.pdf"), {}, BUGUN)
    # TR sayfasında birincil düğme cv_tr boş: not yalnız tanımlı olan yolu listeler
    assert '<a href="cv/en.pdf" download>English (PDF)</a>' in cikti
    assert "cv/tr.pdf" not in cikti
    assert render(_sahte_ayar(), {}, BUGUN).count('<p class="cv-not">') == 0


def test_eposta_gitHub_linkedin_guvenli():
    ayar = _sahte_ayar(sahip_eposta="umut@example.com",
                       sahip_linkedin="https://www.linkedin.com/in/x")
    cikti = render(ayar, {}, BUGUN)
    assert 'href="mailto:umut@example.com"' in cikti
    assert 'href="https://www.linkedin.com/in/x" rel="noopener noreferrer" target="_blank"' in cikti
    assert tara(cikti, izinli_eposta=["umut@example.com"]) == []


# --- dil ------------------------------------------------------------------------------------

def test_dil_anahtari_yoksa_cikmaz():
    assert '<nav class="dil"' not in render(_sahte_ayar(), {}, BUGUN)


def test_dil_anahtari_aria_current_ve_href():
    cikti = render(_sahte_ayar(dil_baglantisi="/en/"), {}, BUGUN)
    assert '<a href="." lang="tr" hreflang="tr" aria-current="true">TR</a>' in cikti
    assert '<a href="/en/" lang="en" hreflang="en">EN</a>' in cikti


def test_en_dil_etiketleri_ve_lang():
    cikti = render(_sahte_ayar(dil="en", dil_baglantisi="/"), {}, BUGUN)
    assert '<html lang="en">' in cikti
    assert '<meta property="og:locale" content="en_US">' in cikti
    assert m("en", "menu_projeler") in cikti and m("en", "menu_iletisim") in cikti
    assert 'aria-current="true">EN</a>' in cikti


# --- yazılar ---------------------------------------------------------------------------------

def test_yazilar_bolumu_tarih_azalan_ve_kacisli():
    y = lambda slug, baslik, tarih: SimpleNamespace(  # noqa: E731
        slug=slug, baslik=baslik, tarih=tarih, ozet="Özet <b>", etiketler=())
    cikti = render(_sahte_ayar(), {}, BUGUN, [y("eski", "Eski", "2026-01-01"),
                                              y("yeni", "Yeni", "2026-09-01")])
    assert '<div class="ray" id="yazilar"><h2>' in cikti
    assert cikti.index("yazilar/yeni.html") < cikti.index("yazilar/eski.html")
    assert "Özet &lt;b&gt;" in cikti and "Özet <b>" not in cikti
    assert '<li><a href="#yazilar">' in cikti


def test_yazi_yoksa_bolum_ve_menu_baglantisi_yok():
    cikti = render(_sahte_ayar(), {}, BUGUN)
    assert m("tr", "yazi_baslik") not in cikti
    assert 'href="#yazilar"' not in cikti and 'id="yazilar"' not in cikti


# --- bağlantı güvenliği ----------------------------------------------------------------------

def test_repo_baglantilari_kacisli_ve_guvenli():
    ayar = _sahte_ayar(repolar=[{"ad": "r", "one_cikan": True}])
    ayar.repolar[0].baglantilar = (("Demo", "https://demo.example/a?b=1&c=2"),
                                   ("<b>Doc</b>", "https://doc.example"))
    cikti = render(ayar, {}, BUGUN)
    assert 'href="https://demo.example/a?b=1&amp;c=2" rel="noopener noreferrer" target="_blank">Demo</a>' in cikti
    assert "&lt;b&gt;Doc&lt;/b&gt;" in cikti and "<b>Doc" not in cikti
    assert tara(cikti) == []


def test_baglanti_yoksa_baglar_kapsayicisi_yok():
    ayar = _sahte_ayar(repolar=[{"ad": "r", "one_cikan": True}])
    ayar.repolar[0].url = ""
    cikti = render(ayar, {}, BUGUN)
    assert '<div class="baglar">' not in cikti


# --- yazı sayfası ----------------------------------------------------------------------------

def _yazi(**kw) -> SimpleNamespace:
    d = dict(slug="sabit", baslik="Sabit yazı", tarih="2026-10-01", ozet="Özet.",
             kelime=400, etiketler=("python",), govde_html="<p>Gövde.</p>")
    return SimpleNamespace(**{**d, **kw})


def test_yazi_sayfasi_yapi():
    cikti = render_yazi(_sahte_ayar(), _yazi(), BUGUN)
    assert '<div class="ray"' not in cikti
    assert '<section class="unit yazi">' in cikti
    assert "<article>" in cikti
    assert '<h1>Sabit yazı</h1>' in cikti
    assert '<p class="yazi-meta">' in cikti
    assert "2 " + m("tr", "dk_okuma") in cikti
    assert '<a class="geri" href="../#icerik">' in cikti
    assert '<ul class="yigin"><li>python</li></ul>' in cikti


def test_yazi_sayfasi_menu_kok_goreli():
    cikti = render_yazi(_sahte_ayar(), _yazi(), BUGUN)
    assert 'href="../#projeler"' in cikti and 'href="../#iletisim"' in cikti
    assert "index.html" not in cikti
    assert '<nav class="dil"' not in cikti  # yazı sayfalarında dil anahtarı yok


def test_yazi_sayfasi_onceki_sonraki():
    cikti = render_yazi(_sahte_ayar(), _yazi(), BUGUN,
                        onceki=_yazi(slug="eski", baslik="Eski"),
                        sonraki=_yazi(slug="yeni", baslik="Yeni"))
    assert '<a class="onceki" href="eski.html" rel="prev">' in cikti
    assert '<a class="sonraki" href="yeni.html" rel="next">' in cikti


def test_yazi_sayfasi_denetim_temiz():
    cikti = render_yazi(_sahte_ayar(sahip_ad="A B"), _yazi(baslik="Başlık & <b>"), BUGUN, feed=True)
    assert "Başlık &amp; &lt;b&gt;" in cikti
    assert tara(cikti) == []
    assert '<link rel="alternate" type="application/atom+xml" href="../feed.xml"' in cikti


# --- ortak ------------------------------------------------------------------------------------

def test_sayfa_url_ve_denetim_yardimci():
    ayar = _sahte_ayar(site_url="https://ada.github.io")
    assert sayfa_url(ayar) == "https://ada.github.io/"
    assert sayfa_url(ayar, "og/a.png") == "https://ada.github.io/og/a.png"
    assert sayfa_url(_sahte_ayar(), "a") == ""
    from portfolyo.html import _kendi_denetimi
    assert _kendi_denetimi("<html>temiz</html>") == []
    assert _kendi_denetimi("a@b.com", izinli_eposta=["a@b.com"]) == []
    assert [b.tur for b in _kendi_denetimi("a@b.com")] == ["eposta"]


def test_yeni_alanlar_yoksa_bolumler_cikmaz():
    """ayar.py yeni alanları henüz taşımıyor olabilir: eksik alan sayfayı bozmaz."""
    ayar = _sahte_ayar()
    for alan in ("dil", "dil_baglantisi", "deneyim", "egitim", "yetenekler"):
        delattr(ayar, alan)
    for alan in ("eposta", "linkedin", "konum", "cv_tr", "cv_en", "ledler"):
        delattr(ayar.sahip, alan)
    cikti = render(ayar, {}, BUGUN)
    assert '<div class="iki">' not in cikti
    assert 'class="yetenek"' not in cikti
    assert tara(cikti) == []