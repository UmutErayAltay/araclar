"""390 px'de yatay taşma denetimi — her iki temada.

Panel artık iki temayı destekliyor; taşma denetimi ikisinde de yapılır.
"""

from __future__ import annotations

import pytest

pytest.importorskip("playwright", reason="Playwright kurulu değil")

from test_tema_cekim import tarayici_modulu  # noqa: F401  (fikstür paylaşımı)
from test_web_e2e import demo_web  # noqa: F401  (fikstür paylaşımı)

OLC_TASMA = """() => ({
    belge: document.documentElement.scrollWidth,
    pencere: window.innerWidth,
    genislik: document.documentElement.clientWidth
})"""


@pytest.mark.parametrize("tema", ["dark", "light"])
@pytest.mark.parametrize("yol", ["/", "/ara?q=parola", "/kirik", "/yetim"])
def test_mobilde_yatay_tasma_yok(tarayici_modulu, demo_web, tema: str, yol: str) -> None:
    """390 px genişlikte sayfa yatay TAŞMAZ (her sayfa, her tema).

    `documentElement.scrollWidth` pencere genişliğini aşarsa yatay kaydırma
    çıkar. Tema değişimi ölçüyü etkilememelidir.
    """
    baglam = tarayici_modulu.new_context(color_scheme=tema, viewport={"width": 390, "height": 844})
    sayfa = baglam.new_page()
    try:
        sayfa.goto(demo_web.taban + yol, wait_until="load")
        sayfa.wait_for_timeout(700)
        o = sayfa.evaluate(OLC_TASMA)
    finally:
        sayfa.close()
        baglam.close()

    assert o["belge"] <= o["pencere"] + 1, (
        f"{tema} {yol}: yatay taşma — belge {o['belge']} px > pencere {o['pencere']} px"
    )