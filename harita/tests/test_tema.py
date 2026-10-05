"""Tema testleri — `stil.css` açık + koyu tema düzeni ve kontrast ölçümü.

liman paneliyle aynı desen zorunludur:
    `:root` AÇIK varsayılan, koyu değerler
    `@media (prefers-color-scheme: dark) { :root { ... } }` içinde.

Burada ÖLÇÜLEN (tahmin edilmeyen) şeyler:
    * her iki temada `--yazi/--zemin` ve `--ikincil/--zemin` ≥ 4.5:1,
    * düğüm paleti her iki zeminde ≥ 3:1 (graf düğümleri renk körlüğü için
      paletten gelir; zemin üzerinde seçilebilir olmalı),
    * değişken tanımları dışında sabit hex/rgba KALMAMIŞ olması.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from conftest import KOK

STIL = KOK / "harita" / "web" / "static" / "stil.css"
GRAF_JS = KOK / "harita" / "web" / "static" / "graf.js"

#: Koyu temada DEĞİŞMEYECEK mevcut değerler (birebir korunmalı).
KOYU_DEGERLER = {
    "--zemin": "#0f1115",
    "--yazi": "#e6e6e6",
    "--ikincil": "#9aa3b2",
    "--kenar": "#232833",
    "--vurgu": "#56b4e9",
    "--panel-zemin": "#151922",
    "--bos": "#7a8496",
    "--uyari": "#d55e00",
}

#: Açık tema liman ile AYNI değerleri kullanır.
ACIK_BEKLENEN = {
    "--zemin": "#f7f8fa",
    "--yazi": "#1c2029",
    "--ikincil": "#556070",
    "--kenar": "#d3d9e2",
    "--vurgu": "#0072b2",
    "--bos": "#667085",
    "--uyari": "#a35b00",
}

#: Düğüm paleti değişkenleri (graf.js bu adları okur).
DUGUM_DEGISKENLERI = [f"--dugum-{i}" for i in range(1, 9)] + ["--dugum-diger"]

#: Metin/zemin kontrastı için WCAG 2.x eşiği.
KONTRAST_ESIK = 4.5
#: Graf düğümü / zemin kontrastı için eşik (non-text, WCAG 1.4.11).
DUGUM_ESIK = 3.0


@pytest.fixture(scope="module")
def css() -> str:
    return STIL.read_text(encoding="utf-8")


def _yorumlari_temizle(metin: str) -> str:
    """CSS yorumlarını boşaltır (yorumdaki renkleri saymamak için)."""
    return re.sub(r"/\*.*?\*/", "", metin, flags=re.S)


def _govde_bloklari(metin: str) -> list[str]:
    """`:root` bloklarını gövdesiyle döndürür (iç içe `@media` hariç değil —
    koyu blok `@media` içinde olduğu için metin olarak aranır)."""
    return re.findall(r":root\s*\{([^}]*)\}", metin, flags=re.S)


def _acik_kok(metin: str) -> dict[str, str]:
    """Açık tema `:root` bloğu: İLK `:root` (koyu blok `@media` içindedir)."""
    kok = _govde_bloklari(metin)[0]
    return dict(re.findall(r"(--[a-z0-9-]+)\s*:\s*([^;]+);", kok))


def _koyu_kok(metin: str) -> dict[str, str]:
    """Koyu tema `:root` bloğu: `prefers-color-scheme: dark` içindeki."""
    bloklar = re.findall(
        r"@media\s*\(prefers-color-scheme:\s*dark\)\s*\{\s*:root\s*\{([^}]*)\}",
        metin,
        flags=re.S,
    )
    assert bloklar, "koyu tema bloğu (@media (prefers-color-scheme: dark)) yok"
    return dict(re.findall(r"(--[a-z0-9-]+)\s*:\s*([^;]+);", bloklar[0]))


def _kontrast_orani(renk1: str, renk2: str) -> float:
    """WCAG 2.x göreli parlaklık kontrastı (test_web_e2e'deki ile aynı)."""

    def parlak(hex_renk: str) -> float:
        h = hex_renk.strip().lstrip("#")
        if len(h) == 3:
            h = "".join(k * 2 for k in h)
        kanal = [int(h[i : i + 2], 16) / 255 for i in (0, 2, 4)]
        don = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in kanal]
        return 0.2126 * don[0] + 0.7152 * don[1] + 0.0722 * don[2]

    a, b = parlak(renk1), parlak(renk2)
    if a < b:
        a, b = b, a
    return (a + 0.05) / (b + 0.05)


def _tema_hepsi(css: str) -> list[tuple[str, str, dict[str, str]]]:
    """(tema adı, zemin rengi, değişken→değer) üçlüleri."""
    return [
        ("acik", "#f7f8fa", _acik_kok(css)),
        ("koyu", "#0f1115", _koyu_kok(css)),
    ]


# ---------------------------------------------------------------------------
# Yapı: açık varsayılan, koyu @media içinde
# ---------------------------------------------------------------------------


def test_koyu_tema_blogu_var(css: str) -> None:
    """`prefers-color-scheme: dark` bloğu tanımlı olmalı."""
    assert "@media (prefers-color-scheme: dark)" in css
    assert re.search(
        r"@media\s*\(prefers-color-scheme:\s*dark\)\s*\{\s*:root\s*\{",
        css,
    ), "koyu tema değerleri `:root` içinde olmalı"


def test_color_scheme_ikisi_ilan_edilmis(css: str) -> None:
    """Tarayıcıya (form, kaydırma çubuğu) `light dark` bildirilir."""
    assert re.search(r"color-scheme:\s*light\s+dark", css)


def test_acik_tema_rootta_koyu_deger_degil(css: str) -> None:
    """Varsayılan `:root` koyu değil, AÇIK değerleri taşır."""
    acik = _acik_kok(css)
    assert acik["--zemin"].strip() == "#f7f8fa", acik["--zemin"]
    assert acik["--yazi"].strip() == "#1c2029", acik["--yazi"]


@pytest.mark.parametrize("ad,deger", sorted(ACIK_BEKLENEN.items()))
def test_acik_degerler_liman_ile_ayni(css: str, ad: str, deger: str) -> None:
    """liman ile paylaşılan her değer birebir aynı olmalı."""
    acik = _acik_kok(css)
    assert ad in acik, f"{ad} açık temada tanımsız"
    assert acik[ad].strip().lower() == deger, f"{ad} = {acik[ad]!r}, beklenen {deger}"


@pytest.mark.parametrize("ad,deger", sorted(KOYU_DEGERLER.items()))
def test_koyu_degerler_birebir_korunmus(css: str, ad: str, deger: str) -> None:
    """Koyu görünüm DEĞİŞMEZ: mevcut değerler aynen taşınır."""
    koyu = _koyu_kok(css)
    assert ad in koyu, f"{ad} koyu temada tanımsız"
    assert koyu[ad].strip().lower() == deger, f"{ad} = {koyu[ad]!r}, beklenen {deger}"


# ---------------------------------------------------------------------------
# Kontrast: ÖLÇÜLÜR (tahmin edilmez)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tema", ["acik", "koyu"])
@pytest.mark.parametrize("metin", ["--yazi", "--ikincil"])
def test_metin_zemin_kontrast_esigi(css: str, tema: str, metin: str) -> None:
    """`--yazi` ve `--ikincil`, kendi `--zemin`inde ≥ 4.5:1 vermeli."""
    for ad, zemin, degiskenler in _tema_hepsi(css):
        if ad != tema:
            continue
        oran = _kontrast_orani(degiskenler[metin], zemin)
        assert oran >= KONTRAST_ESIK, f"{tema} {metin} kontrastı {oran:.2f}:1 < 4.5:1"


@pytest.mark.parametrize("tema", ["acik", "koyu"])
@pytest.mark.parametrize("ad", DUGUM_DEGISKENLERI)
def test_dugum_paleti_zeminde_okunur(css: str, tema: str, ad: str) -> None:
    """Düğüm renkleri kendi zemininde ≥ 3:1 (seçilebilirlik)."""
    for tema_ad, zemin, degiskenler in _tema_hepsi(css):
        if tema_ad != tema:
            continue
        assert ad in degiskenler, f"{ad} {tema} temada tanımsız"
        renk = degiskenler[ad].strip()
        oran = _kontrast_orani(renk, zemin)
        assert oran >= DUGUM_ESIK, f"{tema} {ad}={renk} kontrastı {oran:.2f}:1 < 3:1"


@pytest.mark.parametrize("tema", ["acik", "koyu"])
def test_graf_etiket_zeminde_okunur(css: str, tema: str) -> None:
    """Graf etiketi kendi zemininde ≥ 4.5:1 (metin — etiket okunur olmalı)."""
    for tema_ad, zemin, degiskenler in _tema_hepsi(css):
        if tema_ad != tema:
            continue
        for ad in ("--graf-etiket", "--graf-etiket-sec"):
            assert ad in degiskenler, f"{ad} {tema} temada tanımsız"
            oran = _kontrast_orani(degiskenler[ad].strip(), zemin)
            assert oran >= KONTRAST_ESIK, f"{tema} {ad} kontrastı {oran:.2f}:1 < 4.5:1"


@pytest.mark.parametrize("tema", ["acik", "koyu"])
def test_kenar_cizgisi_zeminden_ayrilir(css: str, tema: str) -> None:
    """Kenar (bağlantı) çizgisi zeminden AYRILIR.

    Çizgi METİN DEĞİLDİR: görevi düğümler arasındaki ilişkiyi göstermektir,
    bu yüzden WCAG metin eşiği değil, görünürlük (≥1.5:1) ölçülür. Koyu
    temadaki mevcut değer (#39414f) birebir korunur.
    """
    for tema_ad, zemin, degiskenler in _tema_hepsi(css):
        if tema_ad != tema:
            continue
        ad = "--graf-kenar-cizgi"
        assert ad in degiskenler, f"{ad} {tema} temada tanımsız"
        oran = _kontrast_orani(degiskenler[ad].strip(), zemin)
        assert oran >= 1.5, f"{tema} {ad} kontrastı {oran:.2f}:1 < 1.5:1 (görünmez)"


@pytest.mark.parametrize("tema", ["acik", "koyu"])
def test_mark_vurgusu_kontrast_esigi(css: str, tema: str) -> None:
    """Arama vurgusu (sarı zemin) her iki temada ≥ 4.5:1."""
    for tema_ad, _zemin, degiskenler in _tema_hepsi(css):
        if tema_ad != tema:
            continue
        oran = _kontrast_orani(
            degiskenler["--vurgu-sari-yazi"].strip(),
            degiskenler["--vurgu-sari"].strip(),
        )
        assert oran >= KONTRAST_ESIK, f"{tema} mark kontrastı {oran:.2f}:1"


def test_acik_palette_ton_korunmus(css: str) -> None:
    """Açık palet, koyu paletin koyulaştırılmışıdır: renk koru için AYRI tonlar.

    Okabe-Ito'nun sekiz rengi altı ayrı ton ailesine düşer (gri "diğer"
    kendi ailesidir). Aynı aileden iki renk yan yana gelirse renk körlüğünde
    karışırlar; burada böyle bir çakışma olmadığı doğrulanır.
    """
    OI_AD = {1: "turuncu", 2: "gok", 3: "yesil", 4: "sari",
             5: "mavi", 6: "kirmizi", 7: "mor", 8: "gri"}
    koyu = _koyu_kok(css)
    acik = _acik_kok(css)
    gorulen = set()
    for i in range(1, 9):
        ad = f"--dugum-{i}"
        a, k = acik[ad].strip().lower(), koyu[ad].strip().lower()
        if a == k:
            # Renk zaten açık zeminde 3:1 veriyorsa koyulastirilmamıştir.
            assert _kontrast_orani(a, "#f7f8fa") >= DUGUM_ESIK, f"{ad}={a}"
        gorulen.add(OI_AD[i])
    assert len(gorulen) == 8, f"ton aileleri çakışıyor: {sorted(gorulen)}"


# ---------------------------------------------------------------------------
# Değişkenleştirme: tanım dışında sabit renk kalmamalı
# ---------------------------------------------------------------------------


def test_tanim_disi_sabit_renk_yok(css: str) -> None:
    """Değişken tanımları ve yorumlar dışında hex/rgba/hsl KALMAMALI."""
    govde = _yorumlari_temizle(css)
    # `--ad: deger;` tanımlarını geçici olarak nötrleştir.
    govde = re.sub(r"--[a-z0-9-]+\s*:\s*[^;{}]+;", "TANIM;", govde)
    kalan = re.findall(r"#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(", govde)
    assert not kalan, f"tanım dışında sabit renk var: {sorted(set(kalan))}"


def test_dugum_renkleri_yalnizca_degisken_uzerinden(css: str) -> None:
    """Düğüm disk rengi CSS'te değişkenden gelir (graf.js de öyle okur)."""
    assert "var(--graf-dugum-kenar)" in css
    assert "var(--graf-etiket)" in css
    js = GRAF_JS.read_text(encoding="utf-8")
    assert "getPropertyValue" in js, "graf.js tema değişkenlerini okumuyor"
    assert "matchMedia" in js, "graf.js tema değişimini dinlemiyor"


def test_graf_js_tema_degisiminde_yeniden_cizer() -> None:
    """`prefers-color-scheme` değişiminde düğüm `fill`'i yeniden yazılır."""
    js = GRAF_JS.read_text(encoding="utf-8")
    assert "(prefers-color-scheme: dark)" in js
    assert 'setAttribute("fill"' in js, "düğüm rengi yeniden yazılmıyor"
    assert "temayi_uygula" in js