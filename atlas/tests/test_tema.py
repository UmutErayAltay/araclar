"""Panel teması: açık varsayılan + `prefers-color-scheme` koyu.

`atlas/web/static/stil.css` iki tema taşır:
  * açık tema varsayılan `:root` içinde,
  * koyu tema `@media (prefers-color-scheme: dark) { :root { ... } }` içinde.

Bu testler KAYNAĞI okur (tarayıcı yok):
  * koyu blok var mı, açık değerler gerçekten `:root`'ta mı,
  * `--yazi`/`--ikincil` her iki temada zeminine karşı >= 4.5:1 mi
    (WCAG 2.x bağıl parlaklık ile HESAPLANIR, tahmin edilmez),
  * Okabe-Ito paleti açık zeminde okunur kalıyor mu,
  * değişken tanımları dışında sabit hex/rgba kalmış mı.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from conftest import REPO_ROOT

STIL = REPO_ROOT / "atlas" / "web" / "static" / "stil.css"

#: Bir değişken tanımını ayıklayan desen: `--ad: deger;`
_DEGISKEN = re.compile(r"--([\w-]+)\s*:\s*([^;{}]+);")

#: Kök `:root { ... }` bloğunu (yorumsuz) yakalar.
_KOK_ROOT = re.compile(r":root\s*\{(.*?)\n\s*\}", re.DOTALL)

#: Koyu tema medya sorgusunu ve icindeki `:root` blogunu yakalar.
_KOYU_MEDIA = re.compile(
    r"@media\s*\(prefers-color-scheme:\s*dark\)\s*\{\s*:root\s*\{(.*?)\n\s*\}\s*\}",
    re.DOTALL,
)


# --------------------------------------------------------------------------
# Yardımcılar
# --------------------------------------------------------------------------


def _yorumsuz(metin: str) -> str:
    """CSS yorumlarını siler (yorumdaki renkler kaynak sayılmasın)."""
    return re.sub(r"/\*.*?\*/", "", metin, flags=re.DOTALL)


def _degiskenler(blok: str) -> dict[str, str]:
    """Bir `{}` blogundaki `--ad: deger` ciftlerini sozluk dondurur."""
    return {ad: deger.strip() for ad, deger in _DEGISKEN.findall(blok)}


def _kontrast(bir: str, iki: str) -> float:
    """WCAG 2.x kontrast orani (1..21); koyu agirligi DUZELTILMEZ."""
    la, lb = _parlaklik(bir), _parlaklik(iki)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


#: Testlerde kullanilan kisaltma (WCAG duzeltmesiyle birlikte hesaplar).
_yuksek = _kontrast


def _parlaklik(renk: str) -> float:
    """Göreli parlaklık (WCAG 2.x)."""
    h = renk.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(k * 2 for k in h)
    kanallar = []
    for i in (0, 2, 4):
        c = int(h[i : i + 2], 16) / 255
        kanallar.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * kanallar[0] + 0.7152 * kanallar[1] + 0.0722 * kanallar[2]


@pytest.fixture(scope="module")
def kaynak() -> str:
    return STIL.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def kok(kaynak: str) -> str:
    """Varsayilan (acik) tema degerleri."""
    eslesme = _KOK_ROOT.search(_yorumsuz(kaynak))
    assert eslesme, ":root blogu bulunamadi"
    return eslesme.group(1)


@pytest.fixture(scope="module")
def koyu(kaynak: str) -> str:
    """Koyu tema degerleri."""
    eslesme = _KOYU_MEDIA.search(_yorumsuz(kaynak))
    assert eslesme, "prefers-color-scheme: dark blogu bulunamadi"
    return eslesme.group(1)


@pytest.fixture(scope="module")
def tema_acik(kok: str) -> dict[str, str]:
    return _degiskenler(kok)


@pytest.fixture(scope="module")
def tema_koyu(koyu: str) -> dict[str, str]:
    return _degiskenler(koyu)


# --------------------------------------------------------------------------
# 1) Yapi: koyu blok ve varsayilan acik tema
# --------------------------------------------------------------------------


def test_koyu_tema_blogu_var(kaynak: str):
    """Koyu tema `prefers-color-scheme: dark` medya sorgusunda tanimli."""
    assert _KOYU_MEDIA.search(_yorumsuz(kaynak)), "@media (prefers-color-scheme: dark) { :root { ... } } yok"


def test_acik_tema_varsayilan_kok_root(kok: str):
    """Acik degerler `:root`'ta; koyu blogu degil."""
    d = _degiskenler(kok)
    # liman ile ayni acik degerler
    assert d["zemin"] == "#f7f8fa"
    assert d["yazi"] == "#1c2029"
    assert d["ikincil"] == "#556070"
    assert d["kenar"] == "#d3d9e2"
    assert d["vurgu"] == "#0072b2"
    assert d["panel"] == "#ffffff"
    assert d["panel-acik"] == "#eef1f6"
    assert d["bos"] == "#667085"
    assert d["uyari"] == "#a35b00"
    assert d["hata"] == "#b03000"
    assert d["basari"] == "#00704a"


def test_color_scheme_ikisi_ilan_eder(kok: str):
    """Tarayici arac cubugu/girdi denetimleri temaya uyar."""
    assert "color-scheme: light dark" in kok


def test_koyu_tema_degerleri_degismedi(tema_koyu: dict[str, str]):
    """Koyu gorunum DEGISMEMIS olmali: degerler birebir korunur."""
    beklenen = {
        "zemin": "#0f1115", "yazi": "#e6e6e6", "ikincil": "#9aa3b2",
        "kenar": "#232833", "vurgu": "#56b4e9", "panel": "#151922",
        "panel-acik": "#1c2130", "bos": "#7a8496",
        "uyari": "#E69F00", "hata": "#D55E00", "basari": "#009E73",
    }
    for ad, deger in beklenen.items():
        assert tema_koyu[ad] == deger, f"koyu --{ad} degisti"


def test_her_iki_tema_ayni_degiskenleri_tasiyor(tema_acik: dict, tema_koyu: dict):
    """Koyu blogu, acik blogun TUM anahtar degiskenlerini tanimlamali."""
    eksik = set(tema_acik) - set(tema_koyu)
    assert not eksik, f"koyu temada tanimsiz: {sorted(eksik)}"


# --------------------------------------------------------------------------
# 2) Kontrast (HESAPLANIR)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("tema_adi", ["acik", "koyu"])
def test_ana_metin_kontrast(tema_adi: str, tema_acik: dict, tema_koyu: dict):
    """--yazi / --zemin >= 4.5:1 (her iki temada)."""
    tema = tema_acik if tema_adi == "acik" else tema_koyu
    oran = _yuksek(tema["yazi"], tema["zemin"])
    assert oran >= 4.5, f"{tema_adi}: --yazi/--zemin kontrasti {oran:.2f} < 4.5:1"


@pytest.mark.parametrize("tema_adi", ["acik", "koyu"])
def test_ikincil_metin_kontrast(tema_adi: str, tema_acik: dict, tema_koyu: dict):
    """--ikincil / --zemin >= 4.5:1 (her iki temada)."""
    tema = tema_acik if tema_adi == "acik" else tema_koyu
    oran = _yuksek(tema["ikincil"], tema["zemin"])
    assert oran >= 4.5, f"{tema_adi}: --ikincil/--zemin kontrasti {oran:.2f} < 4.5:1"


@pytest.mark.parametrize("tema_adi", ["acik", "koyu"])
def test_metin_panel_uzerinde_kontrast(tema_adi: str, tema_acik: dict, tema_koyu: dict):
    """Panel zemini de okunabilir olmali (rozetler `.panel` uzerinde durur)."""
    tema = tema_acik if tema_adi == "acik" else tema_koyu
    for ad in ("yazi", "ikincil"):
        oran = _yuksek(tema[ad], tema["panel"])
        assert oran >= 4.5, f"{tema_adi}: --{ad}/--panel {oran:.2f} < 4.5:1"


@pytest.mark.parametrize("tema_adi", ["acik", "koyu"])
def test_okabe_ito_paleti_acik_zeminde_okunur(tema_adi: str, tema_acik: dict, tema_koyu: dict):
    """--oi1..--oi8 her iki temada zemin uzerinde >= 3:1 (rozet/grafik dolgusu)."""
    tema = tema_acik if tema_adi == "acik" else tema_koyu
    for i in range(1, 9):
        ad = f"oi{i}"
        assert ad in tema, f"{tema_adi}: --{ad} tanimsiz"
        oran = _yuksek(tema[ad], tema["zemin"])
        assert oran >= 3.0, f"{tema_adi}: --{ad} zeminde {oran:.2f} < 3:1"


@pytest.mark.parametrize("tema_adi", ["acik", "koyu"])
def test_durum_renkleri_okunur(tema_adi: str, tema_acik: dict, tema_koyu: dict):
    """--uyari/--hata/--basari/--vurgu ana zemin uzerinde >= 4.5:1.

    NOT: koyu temada `--hata`/`--bos` `--panel-acik` uzerinde 4.5 altindadir
    (4.15 / 4.25). Bu DEGISMEYEN koyu degerlerinden gelir; koyu gorunum
    birebir korunacagi icin burada yalniz ana zemin (`--zemin`) denetlenir.
    """
    tema = tema_acik if tema_adi == "acik" else tema_koyu
    for ad in ("uyari", "hata", "basari", "vurgu"):
        oran = _yuksek(tema[ad], tema["zemin"])
        assert oran >= 4.5, f"{tema_adi}: --{ad}/--zemin {oran:.2f} < 4.5:1"


@pytest.mark.parametrize("tema_adi", ["acik", "koyu"])
def test_acik_tema_rozet_renkleri_rozet_yuzeyinde_okunur(
    tema_adi: str, tema_acik: dict, tema_koyu: dict
):
    """ACIK temada rozet yuzeyi (`.rozet` -> `--panel-acik`) okunur kalmali.

    `.rozet` bu renkleri metin olarak tasir: yuksek/orta/dusuk/push/bilgi.
    """
    if tema_adi != "acik":
        pytest.skip("koyu degerler degistirilemez; acik tema icin gecerli")
    tema = tema_acik
    for ad in ("hata", "uyari", "vurgu", "basari", "oi7", "oi8"):
        oran = _yuksek(tema[ad], tema["panel-acik"])
        assert oran >= 4.5, f"acik: --{ad}/--panel-acik {oran:.2f} < 4.5:1"


@pytest.mark.parametrize("tema_adi", ["acik", "koyu"])
def test_bos_not_rengi_kendi_yuzeyinde_okunur(tema_adi: str, tema_acik: dict, tema_koyu: dict):
    """`--bos` yalniz `.lejant-not` (`--panel`) ve `.alt` (`--zemin`) uzerinde
    kullanilir; bu iki yuzeyde okunur olmalidir."""
    tema = tema_acik if tema_adi == "acik" else tema_koyu
    for zemin_ad in ("zemin", "panel"):
        oran = _yuksek(tema["bos"], tema[zemin_ad])
        assert oran >= 4.5, f"{tema_adi}: --bos/--{zemin_ad} {oran:.2f} < 4.5:1"


def test_kaynak_kutusu_her_iki_temada_okunur(tema_acik: dict, tema_koyu: dict):
    """Snippet kutusu (`.snippet`) her iki temada metni okunur kilar."""
    for tema_adi, tema in (("acik", tema_acik), ("koyu", tema_koyu)):
        oran = _yuksek(tema["yazi"], tema["kaynak-zemin"])
        assert oran >= 4.5, f"{tema_adi}: --yazi/--kaynak-zemin {oran:.2f} < 4.5:1"


# --------------------------------------------------------------------------
# 3) SABIT RENK KALMADI
# --------------------------------------------------------------------------


def test_degisken_tanimlari_disinda_sabit_renk_yok(kaynak: str):
    """`:root` bloklari disinda hex/rgba OLMAZ; her renk bir degiskendir."""
    govde = _yorumsuz(kaynak)

    def _cikar(_eslesme: re.Match) -> str:
        return ":root{/*degisken-tanimlari*/}"

    kurallar = re.sub(r":root\s*\{[^{}]*\}", _cikar, govde)
    assert not re.findall(r"#[0-9a-fA-F]{3,8}\b", kurallar), "kural disi sabit hex var"
    assert not re.findall(r"\brgba?\s*\(", kurallar), "kural disi sabit rgb(a) var"


def test_satir_hover_dolgusu_degiskendir(kaynak: str):
    """Tablo satir hover dolgusu sabit rgba DEGIL, degisken kullanir."""
    assert "var(--satir-hover)" in kaynak