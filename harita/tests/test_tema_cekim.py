"""Tarayıcıda tema geçişi: `graf.js` paleti CSS'ten okur ve tema değişince
düğüm renklerini yeniden çizer.

Bu test GERÇEK Chromium'da çalışır; renk değişimi ölçülür (tahmin edilmez).
"""

from __future__ import annotations

import pytest

# `demo_web` fikstürü bu dosyada tanımlı; yeniden kurmak yerine
# mevcut tanımı paylaşırız (aynı kurgusal demo vault'u).
from test_web_e2e import demo_web  # noqa: F401  (fikstür paylaşımı)

pytest.importorskip("playwright", reason="Playwright kurulu değil")


@pytest.fixture
def tarayici_modulu():
    """Chromium modül düzeyinde bir kez açılır."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        try:
            tarayici = p.chromium.launch(args=["--no-sandbox"])
        except Exception as hata:  # pragma: no cover - ortam bağımlı
            pytest.skip(f"Chromium bulunamadı: {str(hata)[:160]}")
        yield tarayici
        tarayici.close()


OLC_RENKLER = """() => {
    const daireler = Array.from(document.querySelectorAll('#graf .dugum circle.dugum-daire'));
    const lejant = Array.from(document.querySelectorAll('#lejant .lejant-kutu'));
    const etiket = document.querySelector('#graf .dugum-etiket');
    return {
        dugum: daireler.map(d => d.getAttribute('fill')),
        lejant: lejant.map(k => k.style.background),
        etiket: etiket ? getComputedStyle(etiket).fill : null,
        dugumKenar: daireler.length ? getComputedStyle(daireler[0]).stroke : null,
        zemin: getComputedStyle(document.body).backgroundColor
    };
}"""


def test_tema_degisince_dugum_renkleri_yeniden_cizilir(tarayici_modulu, demo_web) -> None:
    """`prefers-color-scheme` değişiminde düğüm `fill` ve lejant YENİLENİR.

    Panel iki temayı destekler; JS paleti sabit bilgi olarak taşımaz,
    `getComputedStyle` ile okur. Kullanıcı işletim sistemi temasını
    değiştirdiğinde grafın paleti değişmeden kalırsa düğümler zeminde
    okunmaz olurdu.
    """
    baglam = tarayici_modulu.new_context(color_scheme="light", viewport={"width": 1280, "height": 800})
    sayfa = baglam.new_page()
    try:
        sayfa.goto(demo_web.taban, wait_until="load")
        sayfa.wait_for_selector("body[data-hazir='1']", timeout=30000)
        sayfa.wait_for_timeout(300)

        acik = sayfa.evaluate(OLC_RENKLER)
        assert acik["dugum"], "düğüm çizilmedi"
        assert acik["zemin"] == "rgb(247, 248, 250)", acik["zemin"]   # #f7f8fa

        # İşletim sistemi temasını değiştir → `matchMedia` 'change' olayı.
        sayfa.evaluate("() => window.matchMedia('(prefers-color-scheme: dark)')")
        sayfa.emulate_media(color_scheme="dark")
        sayfa.wait_for_timeout(400)

        koyu = sayfa.evaluate(OLC_RENKLER)
        assert koyu["zemin"] == "rgb(15, 17, 21)", koyu["zemin"]      # #0f1115

        # Düğüm renkleri GERÇEKTEN değişti (aynı listede kalmadı).
        assert koyu["dugum"] != acik["dugum"], "düğüm renkleri yeniden çizilmedi"
        # Lejant da yeni paleti gösteriyor.
        assert koyu["lejant"] != acik["lejant"], "lejant yenilenmedi"
        # Etiket ve düğüm kenarı da temaya uydu.
        assert koyu["etiket"] != acik["etiket"], "etiket rengi değişmedi"
        assert koyu["dugumKenar"] != acik["dugumKenar"], "düğüm kenarı değişmedi"
    finally:
        sayfa.close()
        baglam.close()


def test_dugum_renkleri_koyu_temada_okabe_ito(tarayici_modulu, demo_web) -> None:
    """Koyu temada düğüm paleti Okabe-Ito'nun kendisidir (birebir)."""
    from harita.web.sunucu import OKABE_ITO

    baglam = tarayici_modulu.new_context(color_scheme="dark", viewport={"width": 1280, "height": 800})
    sayfa = baglam.new_page()
    try:
        sayfa.goto(demo_web.taban, wait_until="load")
        sayfa.wait_for_selector("body[data-hazir='1']", timeout=30000)
        sayfa.wait_for_timeout(300)
        renkler = sayfa.evaluate(OLC_RENKLER)
    finally:
        sayfa.close()
        baglam.close()

    buyuk = {c.lower() for c in renkler["dugum"]}
    for renk in OKABE_ITO:
        assert renk.lower() in buyuk, f"{renk} koyu temada yok: {sorted(buyuk)}"