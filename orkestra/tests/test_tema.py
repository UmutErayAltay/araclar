"""Tema testleri (Dalga E): `stil.css` AÇIK + KOYU iki temayı birlikte taşır.

Kapsam: `prefers-color-scheme: dark` bloğu VAR, açık değerler `:root`'ta,
metin/zemin kontrastı iki temada da >= 4.5:1 (HESAPLANIR, tahmin edilmez) ve
değişken tanımları dışında sabit hex/rgba KALMAZ (her iki temada doğru olsun).

Panelin kendi Okabe-Ito paleti (`--oi1..8`) de açık zeminde okunur kalmalı:
rozet metni `--panel-acik` üzerine basılır, bu yüzden o zeminle de >= 4.5:1.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest

from orkestra.queue import SEMA
from orkestra.web import sunucu
from orkestra.web.sunucu import app_olustur


@pytest.fixture()
def db(tmp_path):
    """Bereketli (yazılabilir) test DB'si — panel bunu mode=ro ile açar."""
    yol = tmp_path / "tema.db"
    b = sqlite3.connect(yol)
    b.row_factory = sqlite3.Row
    b.executescript(SEMA)
    b.commit()
    b.close()
    return yol


@pytest.fixture()
def istemci(db, tmp_path):
    cikti = tmp_path / "runs"
    cikti.mkdir()
    return app_olustur(db, cikti_dizini=cikti).test_client()

# -- renk yardimcilari ------------------------------------------------------


def _rgb(hexa: str) -> tuple[int, int, int]:
    """`#rrggbb` → `(r, g, b)`."""
    h = hexa.lstrip("#").strip()
    assert re.fullmatch(r"[0-9a-fA-F]{6}", h), f"hex bekleniyordu: {hexa}"
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _parlaklik(hexa: str) -> float:
    """Göreli parlaklık (WCAG 2.x)."""
    kanallar = []
    for b in _rgb(hexa):
        kan = b / 255
        kan = kan / 12.92 if kan <= 0.03928 else ((kan + 0.055) / 1.055) ** 2.4
        kanallar.append(kan)
    return 0.2126 * kanallar[0] + 0.7152 * kanallar[1] + 0.0722 * kanallar[2]


def _kontrast(birinci: str, ikinci: str) -> float:
    """İki renk arasındaki WCAG kontrast oranı (1..21)."""
    l1, l2 = _parlaklik(birinci), _parlaklik(ikinci)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


# -- stil.css cozumleme -----------------------------------------------------

KAYNAK = Path(sunucu.__file__).parent / "static" / "stil.css"

_ACIK_RE = re.compile(r":root\s*\{(.*?)\n\}", re.DOTALL)
_KOYU_RE = re.compile(
    r"@media\s*\(prefers-color-scheme:\s*dark\)\s*\{\s*:root\s*\{(.*?)\n  \}\n\}",
    re.DOTALL,
)
# Yalnızca gerçek değişken TANIMI olan satırlar. Anahtar `--` ÖNE ALINMAZ.
_TANIM_RE = re.compile(r"--([\w-]+)\s*:\s*([^;{}]+);")
_SABIT_RENK_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)")


def _yorumsuz() -> str:
    return re.sub(r"/\*.*?\*/", "", KAYNAK.read_text(encoding="utf-8"), flags=re.DOTALL)


def _temalar() -> dict[str, dict[str, str]]:
    """Açık ve koyu tema değişkenleri (SADEce somut renk değerleri).

    `var(--x)` ile başka bir değişkene bağlı olan değerler burada DÜŞER: onlar
    somut renk değildir. Varlıkları `test_indireksiyon_degiskenleri_iki_temada_var`
    ayrıca denetler.
    """
    kaynak = _yorumsuz()
    acik_m = _ACIK_RE.search(kaynak)
    koyu_m = _KOYU_RE.search(kaynak)
    assert acik_m, "acik temanin :root blogu bulunamadi"
    assert koyu_m, "koyu tema blogu bulunamadi"

    def coz(blok: str) -> dict[str, str]:
        return {
            ad: deger.strip()
            for ad, deger in _TANIM_RE.findall(blok)
            if not deger.strip().startswith("var(")
        }

    return {"acik": coz(acik_m.group(1)), "koyu": coz(koyu_m.group(1))}


@pytest.fixture(scope="module")
def temalar() -> dict[str, dict[str, str]]:
    return _temalar()


# -- iki tema da var --------------------------------------------------------


def test_koyu_tema_blogu_var():
    assert "prefers-color-scheme: dark" in _yorumsuz()


def test_color_scheme_ikisi_de_ilan_edilir(temalar):
    """Tarayici form kontrollerini de temaya uydurur."""
    assert "color-scheme: light dark" in _yorumsuz()


def test_her_degisken_iki_temada_da_tanimli(temalar):
    """Somut renk değerleri her iki temada da AYNı değişken kümesini doldurur.

    Bir değişken yalnızca açık temada kalmışsa koyu temada o renk boş kalır.
    (`var(...)` ile tanımlı aracı değişkenler aşağıdaki testte denetlenir.)
    """
    eksik = set(temalar["acik"]) ^ set(temalar["koyu"])
    assert not eksik, f"temalar arasında tanımı farklı değişkenler: {eksik}"


def test_indireksiyon_degiskenleri_iki_temada_var():
    """`--log-zemin` gibi ARACA değişkenler de iki temada tanımlı olmalı.

    Bunlar `var(...)` ile başka değişkenlere bağlıdır; `_temalar` onları
    değer listesine almaz, bu yüzden varlıkları ayrıca doğrulanır.
    """
    kaynak = _yorumsuz()
    for ad in ("log-zemin", "satir-ustu", "filtre-zemin", "filtre-etkin-zemin"):
        assert kaynak.count(f"--{ad}:") == 2, (
            f"--{ad} her iki temada da tanimli olmali (acik + koyu)"
        )


@pytest.mark.parametrize(
    "ad",
    ["zemin", "yazi", "ikincil", "kenar", "vurgu", "panel", "panel-acik",
     "bos", "uyari", "hata", "basari"],
)
def test_liman_paleti_iki_temada_da_tanimli(temalar, ad):
    assert ad in temalar["acik"], f"acik temada --{ad} yok"
    assert ad in temalar["koyu"], f"koyu temada --{ad} yok"


def test_acik_zemin_liman_ile_ayni(temalar):
    """liman ile paylasilan temel degerler birebir ayni."""
    assert temalar["acik"]["zemin"] == "#f7f8fa"
    assert temalar["acik"]["yazi"] == "#1c2029"
    assert temalar["acik"]["ikincil"] == "#556070"
    assert temalar["acik"]["kenar"] == "#d3d9e2"
    assert temalar["acik"]["vurgu"] == "#0072b2"
    assert temalar["acik"]["panel"] == "#ffffff"
    assert temalar["acik"]["panel-acik"] == "#eef1f6"
    assert temalar["acik"]["bos"] == "#667085"
    assert temalar["acik"]["uyari"] == "#a35b00"
    assert temalar["acik"]["hata"] == "#b03000"
    assert temalar["acik"]["basari"] == "#00704a"


# -- kontrast (HESAPLANIR) --------------------------------------------------


@pytest.mark.parametrize("tema", ["acik", "koyu"])
def test_yazi_zemin_kontrast(temalar, tema):
    """Ana metin/zemin kontrastı >= 4.5:1."""
    t = temalar[tema]
    oran = _kontrast(t["yazi"], t["zemin"])
    assert oran >= 4.5, f"{tema} temada yazi/zemin yalnizca {oran:.2f}:1"


@pytest.mark.parametrize("tema", ["acik", "koyu"])
def test_ikincil_zemin_kontrast(temalar, tema):
    """İkincil metin (`.ozet`, `th`, `dt`) >= 4.5:1."""
    t = temalar[tema]
    oran = _kontrast(t["ikincil"], t["zemin"])
    assert oran >= 4.5, f"{tema} temada ikincil/zemin yalnizca {oran:.2f}:1"


@pytest.mark.parametrize("tema", ["acik", "koyu"])
def test_dipnot_zemin_kontrast(temalar, tema):
    """Dipnot (`--bos`) de okunur olmalı: renge tek başına bırakılmaz."""
    t = temalar[tema]
    oran = _kontrast(t["bos"], t["zemin"])
    assert oran >= 4.5, f"{tema} temada bos/zemin yalnizca {oran:.2f}:1"


@pytest.mark.parametrize("tema", ["acik", "koyu"])
def test_vurgu_panel_kontrast(temalar, tema):
    """Bağlantı rengi (`.vurgu`) panel üzerinde >= 4.5:1."""
    t = temalar[tema]
    oran = _kontrast(t["vurgu"], t["panel"])
    assert oran >= 4.5, f"{tema} temada vurgu/panel yalnizca {oran:.2f}:1"


@pytest.mark.parametrize("tema", ["acik", "koyu"])
@pytest.mark.parametrize("ad", ["uyari", "hata", "basari"])
def test_durum_renkleri_panel_kontrast(temalar, tema, ad):
    """Durum/uyarı renkleri panel üzerinde okunur."""
    t = temalar[tema]
    oran = _kontrast(t[ad], t["panel"])
    assert oran >= 4.5, f"{tema} temada {ad}/panel yalnizca {oran:.2f}:1"


# -- Okabe-Ito paleti --------------------------------------------------------


@pytest.mark.parametrize("tema", ["acik", "koyu"])
@pytest.mark.parametrize("ad", ["oi1", "oi2", "oi3", "oi6", "oi7", "oi8"])
def test_rozet_paleti_panel_acik_kontrast(temalar, tema, ad):
    """ROZET METNİ `--panel-acik` üzerine basılır: her iki temada >= 4.5:1.

    Bu değişkenleri `.rozet.*` sınıfları metin olarak kullanır. Açık zeminde
    Okabe-Ito'nun kendisi (#F0E442 sarı) 1.3:1 ile okunmaz; `--oi*` bu yüzden
    açık temada aynı hue'yi koruyup koyulaştırır.
    """
    t = temalar[tema]
    oran = _kontrast(t[ad], t["panel-acik"])
    assert oran >= 4.5, f"{tema} temada --{ad}/panel-acik yalnizca {oran:.2f}:1"


@pytest.mark.parametrize("tema", ["acik", "koyu"])
@pytest.mark.parametrize("ad", ["oi4", "oi5"])
def test_graf_cubugu_paleti_panel_kontrast(temalar, tema, ad):
    """Graf ÇUBUĞU metin değildir (non-text): >= 3:1 yeterlidir.

    `--oi4`/`--oi5` yalnızca `graf-bar` `fill`inde kullanılır, rozet metninde
    değil; bu yüzden WCAG non-text eşiği (3:1) uygulanır.
    """
    t = temalar[tema]
    oran = _kontrast(t[ad], t["panel"])
    assert oran >= 3.0, f"{tema} temada --{ad}/panel yalnizca {oran:.2f}:1"


def test_acik_paleti_gercekten_koyulastirilmis(temalar):
    """Açık temada `--oi*` koyu temadaki (parlak) Okabe-Ito değil.

    Koyu temada palet DOĞAL Okabe-Ito'dur; açık temada aynı değerler kullanılsaydı
    sarı/gri tonları beyaz üzerinde görünmez olurdu.
    """
    for i in range(1, 9):
        ad = f"oi{i}"
        assert temalar["acik"][ad] != temalar["koyu"][ad], (
            f"--{ad} iki temada ayni: acik zeminde okunur olmaz"
        )
        assert _kontrast(temalar["acik"][ad], temalar["koyu"][ad]) > 0  # tanımlı


# -- sabit renk kalmiyor ---------------------------------------------------


def test_degisken_tanimi_disi_sabit_renk_yok():
    """Yorumlar ve `:root` tanımları hariç sabit hex/rgba KALMAZ.

    Sabit renk iki temada da doğru çalışmaz; hepsi bir değişkene bağlı olmalı.
    """
    kaynak = _yorumsuz()
    # Her `--ad: deger;` tanımını boşalt, kalanları tara.
    temiz = _TANIM_RE.sub("", kaynak)
    kalan = _SABIT_RENK_RE.findall(temiz)
    assert not kalan, f"degisken tanimi disinda sabit renk kaldi: {kalan}"


def test_sabit_renk_sadece_degisken_taniminda(temalar):
    """Tüm hex değerleri gerçekten bir değişkene atanmış olmalı."""
    tanimli = {v.lower() for v in temalar["acik"].values() if v.startswith("#")}
    for deger in temalar["acik"].values():
        if deger.startswith("#"):
            assert _SABIT_RENK_RE.fullmatch(deger), deger
    assert tanimli, "acik temada hex deger yok"


def test_log_kutusu_temaya_bağli():
    """Log kutusu zeminı sabit koyu değil: metin `var(--yazi)` ile okunur.

    Sabit koyu zemin + acik temada koyu metin = okunmaz log.
    """
    kaynak = _yorumsuz()
    assert "background: var(--log-zemin)" in kaynak
    assert "--log-zemin" in kaynak


def test_satir_ustu_ve_filtre_temaya_bağli():
    """Satır üstü vurgusu ve filtre çipi zeminı tema değişkeni kullanır."""
    kaynak = _yorumsuz()
    assert "background: var(--satir-ustu)" in kaynak
    assert "background: var(--filtre-zemin)" in kaynak


# -- graf renkleri temaya bagli --------------------------------------------


def test_graf_cubugu_rengi_tema_degiskeni():
    """Model grafiği çubuğu sabit hex DEĞİL, `var(--oiN)` olmalı.

    Sabit hex verilseydi açık temada sarı çubuklar beyaz üzerinde görünmezdi.
    """
    from orkestra.web.sunucu import _model_renkleri

    renkler = _model_renkleri(["a/b:free", "c/d", "e/f"])
    assert renkler
    for model, renk in renkler.items():
        assert renk.startswith("var(--oi"), f"{model}: {renk} tema degiskeni degil"
        assert renk in {f"var(--oi{i})" for i in range(1, 9)}, renk


def test_graf_renkleri_kararli():
    """Aynı model her açılışta aynı rengi alır (hash sırası değişmez)."""
    from orkestra.web.sunucu import _model_renkleri

    modeller = ["nvidia/nemotron-3-ultra-550b-a55b:free", "a/b:free"]
    assert _model_renkleri(modeller) == _model_renkleri(modeller)


def test_sablon_graf_fill_degisken_kullanir(istemci, db):
    """Kota şablonu çubuk rengini `model_renkleri`'nden alır (hex değil)."""
    import sqlite3

    b = sqlite3.connect(db)
    for gun in ("2026-09-28", "2026-09-29", "2026-09-30"):
        b.execute(
            "INSERT INTO quota_snapshots (model, gun, istek, maliyet) VALUES (?,?,?,0)",
            ("a/b:free", gun, 7),
        )
    b.commit()
    b.close()
    govde = istemci.get("/kota").get_data(as_text=True)
    assert 'fill="var(--oi' in govde


# -- panel.js renk sabiti kullanmaz ----------------------------------------


def test_panel_js_renk_sabiti_yok():
    """panel.js'te tema değişkenine bağlanacak sabit renk OLMAMALI.

    panel.js yalnız ilerleme çubuğu genişliğini taşır; renk işi CSS'te.
    """
    kaynak = (Path(sunucu.__file__).parent / "static" / "panel.js").read_text(
        encoding="utf-8"
    )
    kod = re.sub(r"/\*.*?\*/", "", kaynak, flags=re.DOTALL)
    assert not _SABIT_RENK_RE.search(kod), "panel.js'te sabit renk var"
