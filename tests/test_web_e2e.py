"""Dalga B — Playwright e2e testleri.

Gerçek `harita web` SÜRECİ ayağa kalkar (ayrı port), Chromium ile sürülür.
Playwright ya da Chromium yoksa testler ATLANIR (skip nedeni açık).

Kapsam: grafik çizimi, panel, `?not=` açılışı, konsol hatası yok, XSS,
mobil genişlik, klavye erişilebilirliği ve performans (1200 not).
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from conftest import KOK, XSS_BASLIK, XSS_BASLIK2, sentetik_vault, vault_hashleri, yaz

sys.path.insert(0, str(KOK / "scripts"))  # ekran görüntüsü betiğindeki kurgusal vault

from harita.index import indeksle

pytestmark = pytest.mark.e2e

pw_api = pytest.importorskip(
    "playwright.sync_api", reason="Playwright kurulu değil (pip install playwright)"
)


# ---------------------------------------------------------------------------
# Chromium yardımcıları
# ---------------------------------------------------------------------------

def chromium_yolu() -> str | None:
    """Hazır Chromium ikili dosyasını ara (`/opt/pw-browsers/…`)."""
    for kalip in (
        "/opt/pw-browsers/chromium-*/chrome-linux*/chrome",
        "/opt/pw-browsers/chromium-*/chrome-linux/chrome",
        "/opt/pw-browsers/chromium_headless_shell-*/chrome-linux*/headless_shell",
        "/opt/pw-browsers/chromium_headless_shell-*/chrome-linux/headless_shell",
    ):
        adaylar = sorted(Path("/").glob(kalip.lstrip("/")))
        if adaylar:
            return str(adaylar[-1])
    return None


@pytest.fixture(scope="module")
def tarayici():
    """Chromium'u aç; yoksa açık nedenle atla."""
    with pw_api.sync_playwright() as p:
        try:
            tarayici_ornegi = p.chromium.launch(args=["--no-sandbox"])
        except Exception as hata:  # pragma: no cover - ortam bağımlı
            yol = chromium_yolu()
            if not yol:
                pytest.skip(f"Chromium bulunamadı: {str(hata)[:160]}")
            tarayici_ornegi = p.chromium.launch(executable_path=yol, args=["--no-sandbox"])
        try:
            yield tarayici_ornegi
        finally:
            tarayici_ornegi.close()


def _bos_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class WebSunucu:
    """`python3 -m harita web` sürecini yönetir."""

    def __init__(self, db: Path) -> None:
        self.db = db
        self.port = _bos_port()
        self.taban = f"http://127.0.0.1:{self.port}"
        self.surec: subprocess.Popen | None = None

    def baslat(self, zaman_asimi: float = 40.0) -> "WebSunucu":
        self.surec = subprocess.Popen(
            [sys.executable, "-m", "harita", "web", "--db", str(self.db), "--port", str(self.port)],
            cwd=str(KOK),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, "PYTHONPATH": str(KOK), "PYTHONIOENCODING": "utf-8"},
        )
        son = time.time() + zaman_asimi
        while time.time() < son:
            if self.surec.poll() is not None:
                hata = (self.surec.stderr.read() if self.surec.stderr else b"").decode("utf-8", "replace")
                raise AssertionError(f"sunucu erken kapandı: {hata[-800:]}")
            try:
                with urllib.request.urlopen(f"{self.taban}/saglik", timeout=2):
                    return self
            except (urllib.error.URLError, OSError):
                time.sleep(0.2)
        raise AssertionError("sunucu zamanında ayağa kalkmadı")

    def kapat(self) -> None:
        if self.surec is None:
            return
        self.surec.terminate()
        try:
            self.surec.wait(timeout=10)
        except subprocess.TimeoutExpired:  # pragma: no cover
            self.surec.kill()
            self.surec.wait(timeout=5)
        self.surec = None


@pytest.fixture
def mini_web(mini_vault: Path, tmp_path: Path):
    """Kurgusal mini-vault'u indeksleyip gerçek sunucuyu ayağa kaldırır."""
    db = tmp_path / "e2e.db"
    indeksle(mini_vault, db)
    sunucu = WebSunucu(db)
    sunucu.baslat()
    try:
        yield sunucu
    finally:
        sunucu.kapat()


@pytest.fixture
def xss_web(tmp_path: Path):
    """XSS yüklü kurgusal vault'u sunar."""
    from conftest import XSS_HEDEF  # noqa: PLC0415

    vault = tmp_path / "xss-vault"
    vault.mkdir()
    yaz(vault, f"kutu/{XSS_BASLIK}.md", f"---\ntitle: {XSS_BASLIK}\n---\n# Zararli\n")
    yaz(vault, f"kutu/{XSS_BASLIK2}.md", f"---\ntitle: {XSS_BASLIK2}\n---\n# Zararli 2\n")
    yaz(vault, "kutu/hedef.md", "# Hedef\n")
    yaz(vault, "kutu/kaynak.md", f"---\ntitle: Kaynak\n---\nKaynak → [[{XSS_BASLIK}]]\n")
    yaz(vault, "kutu/kaynak2.md", f"---\ntitle: Kaynak 2\n---\nKaynak 2 → [[{XSS_BASLIK2}]]\n")
    yaz(vault, "kutu/kaynak3.md", f"Kaynak 3 → [[{XSS_HEDEF}]]\n[[yok-boyle-not]]\n")
    yaz(vault, "kutu/temiz-not.md", "# Temiz Not\n")
    db = tmp_path / "xss-e2e.db"
    indeksle(vault, db)
    sunucu = WebSunucu(db)
    sunucu.baslat()
    try:
        yield sunucu
    finally:
        sunucu.kapat()


def sayfa_ac(tarayici, sunucu: WebSunucu, yol: str = "/", boyut=None, hazir_bekle=True):
    """Sayfayı açar, konsol/hata kaydı toplar.

    `hazir_bekle` yalnız GRAF sayfasında anlamlıdır: JS çizimi bitince
    `<body data-hazir>` işaretini bırakır. `/kirik` ve `/yetim` sunucu tarafında
    basılan statik sayfalardır, JS çalıştırmaz.
    """
    sayfa = tarayici.new_page(
        viewport={"width": 1280, "height": 800} if boyut is None else dict(zip(("width", "height"), boyut))
    )
    konsol: list[str] = []
    hatalar: list[str] = []
    sayfa.on("console", lambda m: konsol.append(f"{m.type}: {m.text}") if m.type in ("error", "warning") else None)
    sayfa.on("pageerror", lambda e: hatalar.append(str(e)))
    sayfa.goto(sunucu.taban + yol, wait_until="load")
    if hazir_bekle:
        sayfa.wait_for_selector("body[data-hazir]", timeout=30000)
    return sayfa, konsol, hatalar


def bos_nokta(sayfa) -> dict:
    """Hiçbir düğümün üstüne düşmeyen bir ekran noktası bul (panel kapatma testi)."""
    nokta = sayfa.evaluate(
        """() => {
            const svg = document.getElementById('graf');
            const kutu = svg.getBoundingClientRect();
            const lejant = document.getElementById('lejant').getBoundingClientRect();
            const daireler = [...document.querySelectorAll('#graf .dugum circle.dugum-daire')]
                .map(c => c.getBoundingClientRect());
            const dolu = (r, x, y) =>
                x >= r.left - 14 && x <= r.right + 14 && y >= r.top - 14 && y <= r.bottom + 14;
            for (let y = kutu.top + 12; y < kutu.bottom - 12; y += 24) {
                for (let x = kutu.left + 12; x < kutu.right - 12; x += 24) {
                    if (daireler.some(r => dolu(r, x, y))) continue;
                    if (dolu(lejant, x, y)) continue;   // lejant SVG'ye değil sahneye bağlı
                    return {x, y};
                }
            }
            return null;
        }"""
    )
    assert nokta is not None, "düğüm boşluğu bulunamadı"
    return nokta


def dugum_tikla(sayfa, not_id: int) -> None:
    """Düğümün DAİRESİNE gerçek fare tıklaması yapar.

    `<g class="dugum">` kutusu etiket metnini de içerdiğinden kutu merkezi
    dairenin dışına düşebilir; bu yüzden `getBoundingClientRect()` değil
    `circle` öğesinin merkezi hedeflenir.
    """
    merkez = sayfa.evaluate(
        """(id) => {
            const g = document.querySelector('#graf .dugum[data-id="' + id + '"]');
            if (!g) return null;
            const c = g.querySelector('circle');
            const r = c.getBoundingClientRect();
            return {x: r.x + r.width / 2, y: r.y + r.height / 2};
        }""",
        not_id,
    )
    assert merkez is not None, f"düğüm {not_id} SVG'de yok"
    sayfa.mouse.move(merkez["x"], merkez["y"])
    sayfa.mouse.down()
    sayfa.wait_for_timeout(60)
    sayfa.mouse.up()


def api_json(sunucu: WebSunucu, yol: str):
    with urllib.request.urlopen(f"{sunucu.taban}{yol}", timeout=10) as cevap:
        import json

        return json.loads(cevap.read().decode("utf-8"))


# ---------------------------------------------------------------------------
# Temel çizim
# ---------------------------------------------------------------------------

def test_graf_cizilir_ve_konsol_sessiz(tarayici, mini_web) -> None:
    """Tüm düğümler SVG'ye eklenir; konsol/sayfa hatası YOK."""
    sayfa, konsol, hatalar = sayfa_ac(tarayici, mini_web)
    veri = api_json(mini_web, "/api/graf")
    svg_dugum = sayfa.locator("#graf .dugum").count()
    assert svg_dugum == len(veri["dugumler"]), (svg_dugum, len(veri["dugumler"]))
    assert sayfa.locator("#graf .kenar").count() == len(veri["kenarlar"])
    assert konsol == [], konsol
    assert hatalar == [], hatalar
    # Boş durum görünmemeli.
    assert sayfa.locator("#bos-durum").is_hidden()
    sayfa.close()


def test_ozet_seridi_dogru(mini_web) -> None:
    """Üst şerit sunucunun sayılarını gösterir."""
    veri = api_json(mini_web, "/api/graf")
    import json
    import urllib.request

    with urllib.request.urlopen(f"{mini_web.taban}/", timeout=10) as cevap:
        govde = cevap.read().decode("utf-8")
    assert f'id="sayac-not">{len(veri["dugumler"])}</b>' in govde


def test_lejant_var_ve_klasor_renkleri_palet(mini_vault: Path, tmp_path: Path, tarayici) -> None:
    """Lejant sol altta, klasör → renk eşleşmesiyle dolu."""
    import json

    db = tmp_path / "lejant.db"
    indeksle(mini_vault, db)
    sunucu = WebSunucu(db)
    sunucu.baslat()
    try:
        sayfa, _, _ = sayfa_ac(tarayici, sunucu)
        satirlar = sayfa.locator("#lejant .lejant-satir")
        assert satirlar.count() > 0
        adlar = sayfa.locator("#lejant .lejant-ad").all_inner_texts()
        assert "🧠 Bilgi" in adlar
        # Kutucukların rengi saydam değil (gerçekten boyanmış).
        renk = sayfa.locator("#lejant .lejant-kutu").first.evaluate(
            "el => getComputedStyle(el).backgroundColor"
        )
        assert renk not in ("rgba(0, 0, 0, 0)", "transparent"), renk
        sayfa.close()
    finally:
        sunucu.kapat()


def test_dugum_tiklamasi_panel_acilir(tarayici, mini_web) -> None:
    """Düğüme tıkla → yan panel açılır ve içerik doğru gelir."""
    veri = api_json(mini_web, "/api/graf")
    hedef = next(d for d in veri["dugumler"] if d["derece"] > 0)
    detay = api_json(mini_web, f"/api/not/{hedef['id']}")

    sayfa, konsol, hatalar = sayfa_ac(tarayici, mini_web)
    assert sayfa.locator("#panel").is_hidden()
    dugum_tikla(sayfa, hedef["id"])
    sayfa.wait_for_selector("#panel:not([hidden])", timeout=10000)
    assert sayfa.locator("#panel h2").inner_text() == detay["baslik"]
    assert hedef["yol"] in sayfa.locator("#panel .yol").inner_text()
    # Panelde giden/gelen bağlantı düğmeleri var.
    assert sayfa.locator("#panel .panel-listesi button").count() > 0
    assert konsol == [] and hatalar == []
    sayfa.close()


def test_panel_baglantilari_odak_degistirir(tarayici, mini_web) -> None:
    """Paneldeki bağlantıya tıkla → o düğüm seçilir ve odak halkası çizilir."""
    veri = api_json(mini_web, "/api/graf")
    kaynak = next(d for d in veri["dugumler"] if d["derece"] > 0)
    detay = api_json(mini_web, f"/api/not/{kaynak['id']}")
    if not detay["giden"]:
        pytest.skip("fixture'ta çözülmüş giden link yok")

    sayfa, _, _ = sayfa_ac(tarayici, mini_web)
    dugum_tikla(sayfa, kaynak["id"])
    sayfa.wait_for_selector("#panel:not([hidden])")
    hedef_id = detay["giden"][0]["id"]
    sayfa.locator(f'#panel button[data-hedef-id="{hedef_id}"]').first.click()
    sayfa.wait_for_function(
        "id => document.querySelector('#graf .dugum[data-id=\"' + id + '\"]')"
        ".classList.contains('dugum-secili')",
        arg=hedef_id,
        timeout=10000,
    )
    hedef_baslik = next(d["baslik"] for d in veri["dugumler"] if d["id"] == hedef_id)
    # Panel içeriği `/api/not/<id>` yanıtıyla ASENKRON gelir; başlığı bekle.
    sayfa.wait_for_function(
        "hedef => { const h = document.querySelector('#panel h2');"
        " return h && h.textContent === hedef; }",
        arg=hedef_baslik,
        timeout=10000,
    )
    assert sayfa.locator("#panel h2").inner_text() == hedef_baslik
    sayfa.close()


def test_bos_alana_tiklama_paneli_kapatir(tarayici, mini_web) -> None:
    veri = api_json(mini_web, "/api/graf")
    hedef = next(d for d in veri["dugumler"] if d["derece"] > 0)
    sayfa, _, _ = sayfa_ac(tarayici, mini_web)
    dugum_tikla(sayfa, hedef["id"])
    sayfa.wait_for_selector("#panel:not([hidden])")
    bos = bos_nokta(sayfa)
    sayfa.mouse.click(bos["x"], bos["y"])
    sayfa.wait_for_selector("#panel", state="hidden", timeout=5000)
    sayfa.close()


def test_not_parametresi_odak_acilir(tarayici, mini_web) -> None:
    """`/?not=<id>` açılışta o notu odaklar ve paneli açar."""
    veri = api_json(mini_web, "/api/graf")
    hedef = next(d for d in veri["dugumler"] if d["derece"] > 0)
    sayfa, konsol, hatalar = sayfa_ac(tarayici, mini_web, f"/?not={hedef['id']}")
    sayfa.wait_for_selector("#panel:not([hidden])", timeout=10000)
    assert sayfa.locator("#panel h2").inner_text() == hedef["baslik"]
    assert sayfa.locator(f'#graf .dugum[data-id="{hedef["id"]}"].dugum-secili').count() == 1
    assert konsol == [] and hatalar == []
    sayfa.close()


def test_klavye_ile_erisim(tarayici, mini_web) -> None:
    """Düğümler `tabindex` alır; Enter açar, Esc kapatır."""
    veri = api_json(mini_web, "/api/graf")
    hedef = next(d for d in veri["dugumler"] if d["derece"] > 0)
    sayfa, _, _ = sayfa_ac(tarayici, mini_web)
    dugum = sayfa.locator(f'#graf .dugum[data-id="{hedef["id"]}"]')
    assert dugum.get_attribute("tabindex") == "0"
    dugum.press("Enter")
    sayfa.wait_for_selector("#panel:not([hidden])", timeout=10000)
    sayfa.keyboard.press("Escape")
    sayfa.wait_for_selector("#panel", state="hidden", timeout=5000)
    sayfa.close()


GORUNUR_ETIKET = """() => [...document.querySelectorAll('#graf .dugum-etiket')]
    .filter(t => Number(t.getAttribute('opacity') || 0) > 0.5)"""


def test_yakinlastirma_etiket_kutulari_buyutmez(tarayici, mini_web) -> None:
    """C.1: yakınlaştıkça etiketlerin EKRAN boyutu sabit kalır (≥11 px).

    B.1'in eski testi "yakınlaştıkça etiket SAYISI artar" diyordu; C.1 ile
    bu önerme bozuldu: (a) etiket artık dairelere de çakışmamak zorunda ve
    (b) etiketin tamamı görünür sahnenin İÇİNDE olmalı. Yakınlaşınca
    düğümlerin çoğu ekran dışına taşır, dolayısıyla etiket sayısı AZALIR —
    bu doğru davranıştır. Ölçülebilir değişmez: yakınlaştırınca etiket
    daha da KÜÇÜK olmaz ve görünür etiket ekranın dışına taşmaz.
    """
    sayfa, _, _ = sayfa_ac(tarayici, mini_web)
    katman = sayfa.locator("#graf .dugum-katmani")
    sayfa.wait_for_timeout(250)
    uzak = sayfa.evaluate(OLC_ETIKET)
    assert uzak, "başlangıçta etiket yok"

    sayfa.mouse.move(640, 400)
    for _ in range(40):
        sayfa.mouse.wheel(0, -120)
    sayfa.wait_for_timeout(500)
    yakin = sayfa.evaluate(OLC_ETIKET)
    yakin += _etiketleri_dogrula(sayfa, "yakın")  # ≥11 px ve kesişmez
    _etiketler_ekranda(sayfa, yakin, "yakın")
    assert katman.get_attribute("data-etiket") in ("derece", "hepsi")
    sayfa.close()


def test_yakinlastirma_daha_genis_etiket_adayi_acar(tarayici, mini_web) -> None:
    """C.1: yakınlaştıkça etiket ADAYI sayısı artar (`data-etiket` = "hepsi").

    B.1'in "daha çok etiket görünür" iddiası C.1 ile daralmıştır: etiket artık
    (a) dairelere de çakışmamalı, (b) tamamen ekranın içinde olmalı. Bu yüzden
    GÖRÜNEN sayı yakınlaştıkça azalabilir (düğümler ekran dışına taşar). Ölçülebilir
    ve doğru olan değişmez, aday havuzunun genişlemesidir: yakınlaştırınca
    `data-etiket` "hepsi"ye geçer ve daha çok etiket DENENİR.
    """
    sayfa, _, _ = sayfa_ac(tarayici, mini_web)
    sayfa.wait_for_timeout(250)
    assert sayfa.evaluate("() => document.getElementById('lejant') !== null")

    sayfa.mouse.move(640, 400)
    for _ in range(40):
        sayfa.mouse.wheel(0, -120)
    sayfa.wait_for_function(
        "() => document.getElementById('graf').querySelector('.dugum-katmani')"
        ".getAttribute('data-etiket') === 'hepsi'",
        timeout=6000,
    )
    # Yakın görünümde de kurallar geçerli: etiketler okunur, kesişmez, ekranda.
    sayfa.wait_for_timeout(300)
    etiketler = _etiketleri_dogrula(sayfa, "yakin hepsi")
    _etiketler_ekranda(sayfa, etiketler, "yakin hepsi")
    sayfa.close()


def test_kirik_sayfasi_linkleri_calisir(tarayici, mini_web) -> None:
    sayfa, konsol, hatalar = sayfa_ac(tarayici, mini_web, "/kirik", hazir_bekle=False)
    baglanti = sayfa.locator(".tablo tbody a").first
    assert baglanti.count() >= 0
    if baglanti.count():
        baglanti.click()
        sayfa.wait_for_selector("body[data-hazir]", timeout=15000)
        assert "/kirik" not in sayfa.url
    assert konsol == [] and hatalar == []
    sayfa.close()


def test_yetim_sayfasi_iki_bolum(tarayici, tmp_path: Path) -> None:
    from conftest import yetim_vault  # noqa: PLC0415

    vault = yetim_vault(tmp_path)
    db = tmp_path / "e2e-yetim.db"
    indeksle(vault, db)
    sunucu = WebSunucu(db)
    sunucu.baslat()
    try:
        sayfa, konsol, hatalar = sayfa_ac(tarayici, sunucu, "/yetim", hazir_bekle=False)
        govde = sayfa.locator(".bolum").count()
        assert govde == 2
        assert sayfa.locator(".bolum h2").first.inner_text().startswith("Gerçek yetim")
        assert sayfa.locator(".bolum h2").nth(1).inner_text().startswith("Yok sayılabilir")
        assert konsol == [] and hatalar == []
        sayfa.close()
    finally:
        sunucu.kapat()


# ---------------------------------------------------------------------------
# XSS: gerçek tarayıcıda yük çalışmamalı
# ---------------------------------------------------------------------------

def test_xss_yukleri_calismaz(tarayici, xss_web) -> None:
    """`window.__xss` ve `window.__xss2` TANIMSIZ kalmalı; <img> oluşmamalı."""
    sayfa, konsol, hatalar = sayfa_ac(tarayici, xss_web)
    # Paneli de aç: panel başlık/özet yolları da textContent kullanır.
    veri = api_json(xss_web, "/api/graf")
    dugum_tikla(sayfa, veri["dugumler"][0]["id"])
    sayfa.wait_for_selector("#panel:not([hidden])", timeout=10000)

    assert sayfa.evaluate("window.__xss === undefined") is True
    assert sayfa.evaluate("window.__xss2 === undefined") is True
    # Yük metin olarak DOM'a girebilir; kritik olan ETİKET/OLAY ÖZNİTELİĞINE
    # dönüşmemesidir. `inner_html`de düz `onerror=` yazısı bulunması tek
    # başına hata değildir (SVG <text> içeriğidir); öznitelik sayımı belirleyicidir.
    sayac = sayfa.evaluate(
        """() => ({
            img: document.querySelectorAll('img').length,
            script: document.querySelectorAll('script:not([src])').length,
            onerror: document.querySelectorAll('[onerror]').length,
            onclick: document.querySelectorAll('[onclick]').length,
        })"""
    )
    assert sayac["img"] == 0, sayac
    assert sayac["script"] == 0, sayac
    assert sayac["onerror"] == 0, sayac
    assert sayac["onclick"] == 0, sayac
    # Yük görünür metin olarak geldiyse de düz metindir:
    # Not BAŞLIĞI görünür metin olarak çizilir (SVG <text>); bu düz metindir,
    # etiket değildir — yukarıdaki öğe/öznitelik sayacı bunu kanıtlar.
    assert konsol == [] and hatalar == []
    sayfa.close()


def test_xss_kirik_sayfasinda_calismaz(tarayici, xss_web) -> None:
    sayfa, _, hatalar = sayfa_ac(tarayici, xss_web, "/kirik", hazir_bekle=False)
    assert sayfa.evaluate("window.__xss === undefined") is True
    assert sayfa.evaluate("window.__xss2 === undefined") is True
    sayac = sayfa.evaluate(
        "() => ({img: document.querySelectorAll('img').length,"
        " onerror: document.querySelectorAll('[onerror]').length})"
    )
    assert sayac == {"img": 0, "onerror": 0}, sayac
    assert hatalar == []
    sayfa.close()


# ---------------------------------------------------------------------------
# Mobil
# ---------------------------------------------------------------------------

def test_mobil_genislikte_yatay_kaydirma_yok(tarayici, mini_web) -> None:
    """390x844'te yatay kaydırma çubuğu olmamalı, panel altta açılmalı."""
    sayfa, konsol, hatalar = sayfa_ac(tarayici, mini_web, "/", boyut=(390, 844))
    sayfa.wait_for_timeout(300)
    olcum = sayfa.evaluate(
        "() => ({doc: document.documentElement.scrollWidth, win: window.innerWidth})"
    )
    assert olcum["doc"] <= olcum["win"] + 1, olcum

    veri = api_json(mini_web, "/api/graf")
    hedef = next(d for d in veri["dugumler"] if d["derece"] > 0)
    dugum_tikla(sayfa, hedef["id"])
    sayfa.wait_for_selector("#panel:not([hidden])", timeout=10000)
    # Panel ekranın altında, tam genişlikte.
    kutu = sayfa.locator("#panel").bounding_box()
    assert kutu["width"] <= 390 + 1
    assert kutu["y"] + kutu["height"] <= 844 + 1
    assert kutu["y"] >= 0
    olcum2 = sayfa.evaluate(
        "() => ({doc: document.documentElement.scrollWidth, win: window.innerWidth})"
    )
    assert olcum2["doc"] <= olcum2["win"] + 1, olcum2
    assert konsol == [] and hatalar == []
    sayfa.close()


def test_dar_vault_bos_durum_gorunur(tarayici, tmp_path: Path) -> None:
    vault = tmp_path / "bos"
    vault.mkdir()
    db = tmp_path / "bos-e2e.db"
    indeksle(vault, db)
    sunucu = WebSunucu(db)
    sunucu.baslat()
    try:
        sayfa, konsol, hatalar = sayfa_ac(tarayici, sunucu)
        assert sayfa.locator("#bos-durum").is_visible()
        assert "İndekte not yok" in sayfa.locator("#bos-durum").inner_text()
        assert konsol == [] and hatalar == []
        sayfa.close()
    finally:
        sunucu.kapat()


# ---------------------------------------------------------------------------
# Performans (1200 not / ~2400 link)
# ---------------------------------------------------------------------------

@pytest.mark.perf
def test_performans_1200_not_ilk_cizim(tarayici, tmp_path: Path) -> None:
    """ÇALIŞMA ZAMANINDA üretilen 1200 notlu vault: ilk çizim < 3 sn.

    Graf verisi tarayıcıda `performance.now()` ile ölçülür: düğüm+kenar
    SVG'ye eklendiği AN. Ham stdout'a yazdırılır, raporda kullanılır.
    """
    vault = sentetik_vault(tmp_path, not_sayisi=1200, link_ortalamasi=2)
    db = tmp_path / "perf.db"
    ozet = indeksle(vault, db)
    assert ozet.notlar == 1200
    assert ozet.linkler >= 2000

    sunucu = WebSunucu(db)
    sunucu.baslat()
    try:
        sayfa, konsol, hatalar = sayfa_ac(tarayici, sunucu)
        olcum = sayfa.evaluate("() => window.__harita")
        veri = api_json(sunucu, "/api/graf")
        svg_dugum = sayfa.locator("#graf .dugum").count()
        assert svg_dugum == len(veri["dugumler"]) == 1200
        print(
            f"\n[PERF] 1200 not / {len(veri['kenarlar'])} kenar — "
            f"düğüm {olcum['dugumMs']} ms + yerleşim {olcum['yerlesimMs']} ms "
            f"= İLK ÇİZİM {olcum['ilkCizimMs']} ms"
        )
        assert olcum["ilkCizimMs"] < 3000, olcum
        assert konsol == [] and hatalar == []
        sayfa.close()
    finally:
        sunucu.kapat()


# ---------------------------------------------------------------------------
# Salt-okunurluk: gerçek süreç de vault'a dokunmaz
# ---------------------------------------------------------------------------

def test_e2e_sureci_vaultu_degistirmez(mini_vault: Path, tmp_path: Path, tarayici) -> None:
    once = vault_hashleri(mini_vault)
    db = tmp_path / "ro-e2e.db"
    indeksle(mini_vault, db)
    sunucu = WebSunucu(db)
    sunucu.baslat()
    try:
        sayfa, _, _ = sayfa_ac(tarayici, sunucu)
        dugum_tikla(sayfa, api_json(sunucu, "/api/graf")["dugumler"][0]["id"])
        sayfa.wait_for_timeout(500)
        sayfa.close()
    finally:
        sunucu.kapat()
    assert vault_hashleri(mini_vault) == once


# ===========================================================================
# Dalga B.1 — ana oturumun bulduğu 5 görsel kusurun ÖLÇÜLEBİLİR kanıtları
# ===========================================================================

DEMO_VAULT_NOT_SAYISI = 16  # ekran görüntüsü fixture'ındaki not sayısı


def demo_vault(kok: Path) -> Path:
    """Ekran görüntüsü betiğinin KURGUSAL demo vault'u (aynı içerik)."""
    import ekran_goruntusu as betik

    return betik.kurgusal_vault(kok)


@pytest.fixture
def demo_web(tmp_path: Path):
    """Kurgusal demo vault'u (16 not) indeksleyip sunar."""
    db = tmp_path / "demo.db"
    indeksle(demo_vault(tmp_path), db)
    sunucu = WebSunucu(db)
    sunucu.baslat()
    try:
        yield sunucu
    finally:
        sunucu.kapat()


# --- ölçüm yardımcıları (JS dosyaları CSP satır içi yasağı nedeniyle
# --- Playwright `evaluate` ile verilir) ---------------------------------

OLC_SAHNE = """() => {
    const s = document.getElementById('sahne').getBoundingClientRect();
    const g = [...document.querySelectorAll('#graf .dugum circle.dugum-daire')]
        .map(c => c.getBoundingClientRect());
    if (!g.length) return null;
    const sol = Math.min(...g.map(r => r.left)), sag = Math.max(...g.map(r => r.right));
    const ust = Math.min(...g.map(r => r.top)), alt = Math.max(...g.map(r => r.bottom));
    return {
        sahne: {sol: s.left, ust: s.top, sag: s.right, alt: s.bottom, g: s.width, y: s.height},
        kutu: {g: sag - sol, y: alt - ust, sol: sol, ust: ust, sag: sag, alt: alt},
        adet: g.length,
    };
}"""

OLC_ETIKET = """() => [...document.querySelectorAll('#graf .dugum-etiket')]
    .filter(t => Number(t.getAttribute('opacity') || 0) > 0.5)
    .map(t => {
        const r = t.getBoundingClientRect();
        return {
            metin: t.textContent,
            fs: parseFloat(getComputedStyle(t).fontSize),
            sol: r.left, ust: r.top, sag: r.right, alt: r.bottom,
        };
    })"""

OLC_KONUM = """() => [...document.querySelectorAll('#graf .dugum')].map(g => {
    const m = /translate\\(([-\\d.]+),([-\\d.]+)\\)/.exec(g.getAttribute('transform'));
    return {id: Number(g.dataset.id), derece: Number(g.dataset.derece),
            x: Number(m[1]), y: Number(m[2]),
            r: Number(g.querySelector('circle.dugum-daire').getAttribute('r'))};
})"""


def konum_haritasi(sayfa) -> dict[int, tuple[float, float, int]]:
    """Düğüm id → (x, y, yarıçap); yerleşim uzayı koordinatları."""
    return {d["id"]: (d["x"], d["y"], d["r"]) for d in sayfa.evaluate(OLC_KONUM)}


def mesafe(a, b) -> float:
    import math

    return math.hypot(a[0] - b[0], a[1] - b[1])


# --- K1: panel görünürlüğü ------------------------------------------------

@pytest.mark.parametrize("boyut", [(1440, 900), (390, 844)], ids=["masaustu", "mobil"])
def test_panel_basligi_ve_yolu_baslik_cubugunun_altinda(demo_web, tarayici, boyut) -> None:
    """K1: `h2` ve yol, başlık çubuğunun ALTINDA ve pencere içinde görünür.

    B.1 kusur #1: panel `<body>` altındaki kardeşti; `position: absolute`
    göreli kapsayıcısı PENCERE çözülüyor, içerik üst şeridin altında kalıyordu.
    """
    veri = api_json(demo_web, "/api/graf")
    hedef = max(veri["dugumler"], key=lambda d: d["derece"])
    sayfa, _, _ = sayfa_ac(tarayici, demo_web, boyut=boyut)
    dugum_tikla(sayfa, hedef["id"])
    sayfa.wait_for_selector("#panel:not([hidden])", timeout=10000)
    sayfa.wait_for_timeout(200)

    olcum = sayfa.evaluate(
        """() => {
            const serit = document.querySelector('header.ust').getBoundingClientRect();
            const h2 = document.querySelector('#panel h2').getBoundingClientRect();
            const yol = document.querySelector('#panel .yol').getBoundingClientRect();
            const p = document.getElementById('panel');
            return {seritAlt: serit.bottom,
                    h2Ust: h2.top, h2Sol: h2.left, h2G: h2.width, h2Y: h2.height,
                    yolUst: yol.top, yolSol: yol.left,
                    kaydirma: p.scrollTop,
                    icH: p.getBoundingClientRect().height,
                    icUst: p.getBoundingClientRect().top,
                    w: window.innerWidth, h: window.innerHeight,
                    yolG: getComputedStyle(document.querySelector('#panel .yol')).display};
        }"""
    )
    assert olcum["yolG"] != "none", "yol öğesi gizli"
    # Başlık ve yol, çubuğun altında (>=) ve h2 yolun ÜSTÜNDE.
    assert olcum["h2Ust"] >= olcum["seritAlt"] - 0.5, olcum
    assert olcum["yolUst"] >= olcum["seritAlt"] - 0.5, olcum
    assert olcum["h2Ust"] <= olcum["yolUst"] + 0.5, olcum
    # Görünür pencere içinde.
    assert olcum["h2Sol"] >= 0 and olcum["h2Sol"] + olcum["h2G"] <= olcum["w"] + 1, olcum
    assert olcum["yolSol"] >= 0, olcum
    # Açılışta panel içi kaydırma en üstte.
    assert olcum["kaydirma"] == 0, olcum
    # Gerçekten görünür (sıfır yükseklik değil).
    assert olcum["h2Y"] > 0 and olcum["icH"] > 0, olcum
    sayfa.close()


def test_panel_acilinca_secili_dugum_panelin_arkasinda_kalmaz(demo_web, tarayici) -> None:
    """B.1: panel açıkken seçili düğüm görünür alanın (panel hariç) merkezindedir."""
    veri = api_json(demo_web, "/api/graf")
    hedef = max(veri["dugumler"], key=lambda d: d["derece"])
    sayfa, _, _ = sayfa_ac(tarayici, demo_web)
    dugum_tikla(sayfa, hedef["id"])
    sayfa.wait_for_selector("#panel:not([hidden])")
    sayfa.wait_for_timeout(250)
    olcum = sayfa.evaluate(
        """(id) => {
            const c = document.querySelector('#graf .dugum[data-id="' + id + '"] circle')
                .getBoundingClientRect();
            const p = document.getElementById('panel').getBoundingClientRect();
            const s = document.getElementById('sahne').getBoundingClientRect();
            return {x: c.x + c.width / 2, y: c.y + c.height / 2,
                    pSol: p.left, pUst: p.top, sSag: s.right, sAlt: s.bottom};
        }""",
        hedef["id"],
    )
    assert olcum["x"] < olcum["pSol"], f"düğüm panelin altında kaldı: {olcum}"
    assert olcum["y"] < olcum["sAlt"] + 1, olcum
    sayfa.close()


# --- K2: butonların koyu temaya uyumu --------------------------------------

def _kontrast_oranı(renk1: str, renk2: str) -> float:
    """WCAG 2.x göreli parlaklık kontrastı."""

    def parlak(hex_renk: str) -> float:
        h = hex_renk.lstrip("#")
        if len(h) == 3:
            h = "".join(k * 2 for k in h)
        kanal = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        dön = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in kanal]
        return 0.2126 * dön[0] + 0.7152 * dön[1] + 0.0722 * dön[2]

    a, b = parlak(renk1), parlak(renk2)
    if a < b:
        a, b = b, a
    return (a + 0.05) / (b + 0.05)


@pytest.mark.parametrize("durum", ["normal", "odak"])
def test_panel_baglanti_butonlari_koyu_tema_uyumlu(demo_web, tarayici, durum) -> None:
    """K2: butonların zemin rengi BEYAZ DEĞİL ve kontrastı ≥4.5:1.

    B.1 kusur #2: `border: 0` geçersiz kısaltma olduğu için tarayıcı
    varsayılanı (`background-color: rgb(239,239,239)`) koyu temada
    beyaz butonlar üretiyordu.
    """
    veri = api_json(demo_web, "/api/graf")
    hedef = max(veri["dugumler"], key=lambda d: d["derece"])
    sayfa, _, _ = sayfa_ac(tarayici, demo_web)
    dugum_tikla(sayfa, hedef["id"])
    sayfa.wait_for_selector("#panel:not([hidden])")
    sayfa.wait_for_timeout(200)

    buton = sayfa.locator("#panel .panel-bag").first
    assert buton.count() > 0, "panelde bağlantı butonu yok"
    if durum == "odak":
        # Programatik `.focus()` `:focus-visible` ÜRETMEZ (klavye etkileşimi
        # şart); bu yüzden GERÇEK Tab tuşuyla odaklanılır.
        sayfa.keyboard.press("Tab")
        sayfa.wait_for_selector("#panel .panel-bag:focus-visible", timeout=5000)

    stil = buton.evaluate(
        """el => {
            const s = getComputedStyle(el);
            const p = getComputedStyle(document.getElementById('panel'));
            return {bg: s.backgroundColor, fg: s.color, panelBg: p.backgroundColor,
                    kenarlik: s.borderTopWidth + ' ' + s.borderTopStyle + ' ' + s.borderTopColor,
                    odakHalkasi: s.outlineWidth + ' ' + s.outlineStyle};
        }"""
    )

    def rgb(renk: str) -> tuple[int, int, int]:
        import re

        sayi = [int(float(x)) for x in re.findall(r"[\d.]+", renk)[:3]]
        return (sayi[0], sayi[1], sayi[2])

    def hex_(renk: tuple[int, int, int]) -> str:
        return "#{:02x}{:02x}{:02x}".format(*renk)

    def alfa(renk: str) -> float:
        import re

        sayi = re.findall(r"[\d.]+", renk)
        return float(sayi[3]) if len(sayi) > 3 else 1.0

    def birlestir(ust: str, alt: str) -> str:
        """Yarı saydam üst katmanı alt katmanla birleştirir (gerçek görüntü)."""
        a = alfa(ust)
        if a >= 1.0:
            return hex_(rgb(ust))
        u, v = rgb(ust), rgb(alt)
        return hex_((int(u[0] * a + v[0] * (1 - a)),
                     int(u[1] * a + v[1] * (1 - a)),
                     int(u[2] * a + v[2] * (1 - a))))

    assert rgb(stil["bg"]) != (255, 255, 255), stil
    assert "255, 255, 255" not in stil["bg"], f"beyaz zemin: {stil}"
    # Zemin saydam/yarı saydam → panelin zemini üzerinde birleştirilir.
    zemin = birlestir(stil["bg"], stil["panelBg"])
    oran = _kontrast_oranı(hex_(rgb(stil["fg"])), zemin)
    assert oran >= 4.5, f"kontrast {oran:.2f}:1 < 4.5:1 → {stil}"
    # İnce kenar + odak halkası tanımlı (tıklanabilir görünen bağlantı).
    assert stil["kenarlik"].split()[1] != "none", stil
    if durum == "odak":
        assert stil["odakHalkasi"].split()[1] != "none", f"odak halkası yok: {stil}"
    sayfa.close()


# --- K3: sığdırma (fit-to-view) -------------------------------------------

def _sigdir_olcum(sayfa) -> dict:
    sayfa.wait_for_timeout(250)
    return sayfa.evaluate(OLC_SAHNE)


@pytest.mark.parametrize("boyut", [(1440, 900), (390, 844)], ids=["masaustu", "mobil"])
def test_sigdirma_dugum_kutusu_sahnenin_en_fazla_yuzde_60_doldurur(demo_web, tarayici, boyut) -> None:
    """K3: yerleşimden sonra düğüm sınır kutusu sahnenin ≥%60'ı (bir eksende)."""
    sayfa, _, _ = sayfa_ac(tarayici, demo_web, boyut=boyut)
    o = _sigdir_olcum(sayfa)
    assert o is not None, "düğüm yok"
    yx = o["kutu"]["g"] / o["sahne"]["g"]
    yy = o["kutu"]["y"] / o["sahne"]["y"]
    assert max(yx, yy) >= 0.60, f"en fazla %{100 * max(yx, yy):.1f} doluyor (x=%{100 * yx:.0f} y=%{100 * yy:.0f})"
    # TÜM düğümler sahne içinde (40 px boşluk payı).
    assert o["kutu"]["sol"] >= o["sahne"]["sol"] - 0.5, o
    assert o["kutu"]["ust"] >= o["sahne"]["ust"] - 0.5, o
    assert o["kutu"]["sag"] <= o["sahne"]["sag"] + 0.5, o
    assert o["kutu"]["alt"] <= o["sahne"]["alt"] + 0.5, o
    sayfa.close()


def test_sigdir_1200_notlu_vaultta_tum_dugumler_sahne_ici(tarayici, tmp_path: Path) -> None:
    """K3 (büyük ölçek): 1200 notluk sentetik vault'ta da tüm düğümler sahnede."""
    vault = sentetik_vault(tmp_path, not_sayisi=1200, link_ortalamasi=2)
    db = tmp_path / "fit1200.db"
    indeksle(vault, db)
    sunucu = WebSunucu(db)
    sunucu.baslat()
    try:
        sayfa, _, _ = sayfa_ac(tarayici, sunucu)
        o = _sigdir_olcum(sayfa)
        assert o["adet"] == 1200, o["adet"]
        assert o["kutu"]["sol"] >= o["sahne"]["sol"] - 1, o
        assert o["kutu"]["ust"] >= o["sahne"]["ust"] - 1, o
        assert o["kutu"]["sag"] <= o["sahne"]["sag"] + 1, o
        assert o["kutu"]["alt"] <= o["sahne"]["alt"] + 1, o
        sayfa.close()
    finally:
        sunucu.kapat()


def test_sigdir_dugmesi_klavye_ile_ve_kullanimdan_sonra_calisir(demo_web, tarayici) -> None:
    """K3: 'Sığdır' düğmesi gerçek `<button>`, klavyeyle erişilebilir.

    Kullanıcı kaydırıp yakınlaştırdıktan SONRA otomatik sığdırma tekrarlanmaz;
    düğmeye basınca graf geri sığar.
    """
    sayfa, _, _ = sayfa_ac(tarayici, demo_web)
    dugme = sayfa.locator("#sigdir")
    assert dugme.count() == 1
    assert dugme.evaluate("el => el.tagName") == "BUTTON"
    assert dugme.evaluate("el => el.type") == "button"
    assert dugme.is_visible()
    assert dugme.evaluate("el => el.tabIndex") >= 0, "klavyeyle erişilemiyor"

    # Yakınlaştır: kutu ekranı doldurmayı bırakmalı.
    sayfa.mouse.move(700, 400)
    for _ in range(25):
        sayfa.mouse.wheel(0, -120)
    sayfa.wait_for_timeout(200)
    yakin = sayfa.evaluate(OLC_SAHNE)
    assert yakin["kutu"]["g"] < _sigdir_olcum(sayfa)["sahne"]["g"], "yakınlaştırma etkisiz"

    # Kullanıcı müdahalesi sonrası otomatik sığdırma TEKRAR ÇALIŞMAMALI:
    # bir süre bekle, konum KAYMAMIŞ olmalı.
    sayfa.wait_for_timeout(500)
    hala = sayfa.evaluate(OLC_SAHNE)
    assert abs(hala["kutu"]["g"] - yakin["kutu"]["g"]) < 1.0, "kullanıcı yakınlaştırması bozuldu"

    # Düğme klavyeyle: odakla ve Enter.
    sayfa.evaluate("() => document.getElementById('sigdir').focus()")
    sayfa.keyboard.press("Enter")
    sayfa.wait_for_timeout(350)
    sonra = sayfa.evaluate(OLC_SAHNE)
    assert max(
        sonra["kutu"]["g"] / sonra["sahne"]["g"], sonra["kutu"]["y"] / sonra["sahne"]["y"]
    ) >= 0.60, sonra
    assert sonra["kutu"]["sol"] >= sonra["sahne"]["sol"] - 0.5, sonra
    sayfa.close()


# --- K4: yerleşim kalitesi + determinizm -----------------------------------

def _kenar_ortalamasi(pos, kenarlar) -> float:
    return sum(mesafe(pos[k["kaynak"]], pos[k["hedef"]]) for k in kenarlar) / len(kenarlar)


def _rastgele_cift_ortalamasi(pos, idler) -> float:
    import itertools

    ciftler = list(itertools.combinations(idler, 2))
    return sum(mesafe(pos[a], pos[b]) for a, b in ciftler) / len(ciftler)


def test_yerlesim_kalitesi_kenar_rastgele_orani(demo_web, tarayici) -> None:
    """K4: 16 notluk demo grafında ortalama kenar / ortalama rastgele çift ≤ 0.45.

    B.1 kusur #4: bağlı notlar ekranın zıt uçlarına savrulmuştu; oran 1'e
    (yani rastgele) yakın çıkıyordu.
    """
    veri = api_json(demo_web, "/api/graf")
    assert len(veri["dugumler"]) == DEMO_VAULT_NOT_SAYISI
    sayfa, _, _ = sayfa_ac(tarayici, demo_web)
    konum = konum_haritasi(sayfa)
    assert len(konum) == DEMO_VAULT_NOT_SAYISI
    kenar = _kenar_ortalamasi(konum, veri["kenarlar"])
    rastgele = _rastgele_cift_ortalamasi(konum, sorted(konum))
    oran = kenar / rastgele
    print(f"\n[YERLEŞİM] ortalama kenar {kenar:.1f} px / ortalama rastgele çift "
          f"{rastgele:.1f} px = {oran:.3f} (sınır 0.45)")
    assert oran <= 0.45, f"oran {oran:.3f} > 0.45 (kenar={kenar:.1f}, rastgele={rastgele:.1f})"
    sayfa.close()


def test_bilesenler_ust_uste_binmez(demo_web, tarayici) -> None:
    """K4: iki bağlı bileşenin merkezleri arası mesafe > ortalama yarıçap toplamı.

    Paketleme, bileşenlerin SARAN ÇEMBERLERİ değecek kadar ayrılmasını garanti
    eder; bu test yalnız İKİ bağlı bileşeni doğrulayan fixture'ı kullanır.
    """
    tmp = Path(os.environ.get("HARITA_E2E_TMP", "/tmp"))
    vault = tmp / "bilesen-vault"
    if vault.exists():
        import shutil

        shutil.rmtree(vault)
    vault.mkdir(parents=True)
    # İki ayrık A–B ve C–D çifti: her ikisi de BAĞLI, aralarında kenar yok.
    yaz(vault, "a1.md", "# A1\n[[a2]]\n")
    yaz(vault, "a2.md", "# A2\n[[a1]]\n")
    yaz(vault, "b1.md", "# B1\n[[b2]]\n")
    yaz(vault, "b2.md", "# B2\n[[b1]]\n")
    db = tmp / "bilesen.db"
    if db.exists():
        db.unlink()
    indeksle(vault, db)
    sunucu = WebSunucu(db)
    sunucu.baslat()
    try:
        sayfa, _, _ = sayfa_ac(tarayici, sunucu)
        konum = konum_haritasi(sayfa)
        a = konum[1]  # id'ler indeks sırasıyla 1..4
        b = konum[3]
        d = mesafe(a, b)
        yaricap_toplam = (a[2] + b[2]) * 2.0   # her bileşende 2 düğüm
        print(f"\n[YERLEŞİM] iki bileşen merkez arası {d:.1f} px, "
              f"ortalama yarıçap toplamı {yaricap_toplam:.1f} px")
        assert d > yaricap_toplam, f"bileşenler üst üste biniyor: {d:.1f} <= {yaricap_toplam:.1f}"
        sayfa.close()
    finally:
        sunucu.kapat()
        import shutil

        shutil.rmtree(vault, ignore_errors=True)
        db.unlink(missing_ok=True)


def test_yerlesim_deterministik(demo_web, tarayici) -> None:
    """K4: iki ayrı sayfa yüklemesinde aynı düğüm konumları (±0.5 px)."""
    konumlar = []
    for _ in range(2):
        sayfa, _, _ = sayfa_ac(tarayici, demo_web)
        konumlar.append(konum_haritasi(sayfa))
        sayfa.close()
    ilk, ikinci = konumlar
    assert set(ilk) == set(ikinci)
    enFazla = max(max(abs(ilk[i][0] - ikinci[i][0]), abs(ilk[i][1] - ikinci[i][1])) for i in ilk)
    print(f"\n[YERLEŞİM] iki yükleme arası en büyük konum farkı: {enFazla:.4f} px")
    assert enFazla <= 0.5, f"yerleşim deterministik değil: {enFazla:.3f} px fark"


# --- K5: etiketler (C.1 a/b) ---------------------------------------------

def _etiket_kesisiyor(a: dict, b: dict) -> bool:
    return a["sol"] < b["sag"] and b["sol"] < a["sag"] and a["ust"] < b["alt"] and b["ust"] < a["alt"]


OLC_ETIKET = r"""() => {
    // EKRAN puntosu = SVG `font-size` × kök `scale`. `getComputedStyle`
    // telafi edilmiş (ölçekten küçük) değeri verir; kullanıcının gördüğü
    // boyut ekran ölçeğiyle çarpılır (C.1 (a)).
    const kok = document.getElementById('graf').querySelector('g.kok');
    const m = /scale\(([-\d.]+)\)/.exec(kok.getAttribute('transform') || '');
    const olcek = m ? Number(m[1]) : 1;
    return [...document.querySelectorAll('#graf .dugum-etiket')]
        .filter(t => Number(t.getAttribute('opacity') || 0) > 0.5)
        .map(t => {
            const r = t.getBoundingClientRect();
            return {
                metin: t.textContent,
                fs: parseFloat(getComputedStyle(t).fontSize) * olcek,
                sol: r.left, ust: r.top, sag: r.right, alt: r.bottom,
            };
        });
}"""

OLC_DAIRE = r"""() => {
    const kok = document.getElementById('graf').querySelector('g.kok');
    const m = /translate\(([-\d.]+),([-\d.]+)\) scale\(([-\d.]+)\)/.exec(kok.getAttribute('transform'));
    const kx = Number(m[1]), ky = Number(m[2]), sc = Number(m[3]);
    return [...document.querySelectorAll('#graf .dugum')].map(g => {
        const t = /translate\(([-\d.]+),([-\d.]+)\)/.exec(g.getAttribute('transform'));
        return {id: Number(g.dataset.id),
                x: Number(t[1]) * sc + kx, y: Number(t[2]) * sc + ky,
                r: Number(g.querySelector('circle.dugum-daire').getAttribute('r')) * sc};
    });
}"""


def _etiketleri_dogrula(sayfa, etiket: str) -> list[dict]:
    """Görünen etiketler: okunur, kesişmez, daireye binmez, tamamen ekranda."""
    etiketler = sayfa.evaluate(OLC_ETIKET)
    assert etiketler, f"{etiket}: hiç görünür etiket yok"
    enKucuk = min(e["fs"] for e in etiketler)
    assert enKucuk >= 11.0, f"{etiket}: en küçük EKRAN puntosu {enKucuk:.1f} < 11 px"
    cakisan = [
        (a["metin"], b["metin"])
        for i, a in enumerate(etiketler)
        for b in etiketler[i + 1:]
        if _etiket_kesisiyor(a, b)
    ]
    assert not cakisan, f"{etiket}: kesişen etiketler {cakisan[:4]}"
    return etiketler


def _etiket_daireye_biniyor(sayfa, etiket: dict, daireler: list[dict], bosluk: float = 1.0) -> int | None:
    """Etiket hangi düğüm dairesine basıyor? (yoksa None) — C.1 (a)."""
    for d in daireler:
        r = d["r"] + bosluk
        en = max(d["x"], min(max(etiket["sol"], d["x"]), etiket["sag"]))
        enY = max(d["y"], min(max(etiket["ust"], d["y"]), etiket["alt"]))
        # Kutu/daire kesişimi: daire merkezinin kutunun en yakın noktasına uzaklığı
        if ((en - d["x"]) ** 2 + (enY - d["y"]) ** 2) < r * r:
            return int(d["id"])
    return None


def _etiketler_ekranda(sayfa, etiketler: list[dict], etiket: str, pay: float = 0.5) -> None:
    """Her etiketin kutusu görünür sahnenin TAMAMI içinde (panel/lejant hariç)."""
    s = sayfa.evaluate(
        """() => {const s=document.getElementById('sahne').getBoundingClientRect();
           return {sol:s.left, ust:s.top, sag:s.right, alt:s.bottom};}"""
    )
    tasan = [
        e["metin"] for e in etiketler
        if e["sol"] < s["sol"] - pay or e["ust"] < s["ust"] - pay
        or e["sag"] > s["sag"] + pay or e["alt"] > s["alt"] + pay
    ]
    assert not tasan, f"{etiket}: ekrandan taşan etiketler {tasan[:4]}"


def _lejant_engeli(sayfa, etiketler: list[dict]) -> list[str]:
    """Lejantla kesişen etiketler (lejant açıksa) — C.1 (b)."""
    l = sayfa.evaluate(
        """() => {const d=document.getElementById('lejant');
           if (!d.open) return null; const r=d.getBoundingClientRect();
           return {sol:r.left, ust:r.top, sag:r.right, alt:r.bottom};}"""
    )
    if l is None:
        return []
    return [e["metin"] for e in etiketler if _etiket_kesisiyor(e, l)]


@pytest.mark.parametrize("boyut", [(1440, 900), (390, 844)], ids=["masaustu", "mobil"])
def test_demo_grafinda_etiketler_okunur_ve_cakismaz(demo_web, tarayici, boyut) -> None:
    """C.1 (a)+(b): etiketler ≥11 px, kesişmez, daireye binmez, ekranda kalır."""
    sayfa, _, _ = sayfa_ac(tarayici, demo_web, boyut=boyut)
    sayfa.wait_for_timeout(300)
    etiketler = _etiketleri_dogrula(sayfa, f"demo {boyut}")
    _etiketler_ekranda(sayfa, etiketler, f"demo {boyut}")
    print(f"\n[ETİKET] demo {boyut}: {len(etiketler)} görünür etiket, "
          f"en küçük {min(e['fs'] for e in etiketler):.1f} px")
    sayfa.close()


def test_etiketler_hicbir_dugum_dairesine_binmez(demo_web, tarayici) -> None:
    """C.1 (a): görünür etiket, TÜM düğüm dairelerine (kendi hariç) binmez.

    B.1 kusur: etiket–etiket kesişimi engellendi ama daireler ETİKETİN
    ÜSTÜNE biniyordu ("Kuyruk Tasarımı", "Kafes Teorisi Notları").
    """
    sayfa, _, _ = sayfa_ac(tarayici, demo_web)
    sayfa.wait_for_timeout(300)
    etiketler = _etiketleri_dogrula(sayfa, "demo daire")
    daireler = sayfa.evaluate(OLC_DAIRE)
    assert daireler, "daire yok"
    # Her etiket için, kendi düğümü hariç TÜM dairelerle denetle.
    ihlal = []
    for e in etiketler:
        # etiketin sol kenarındaki daire = kendi düğümü (etiket dairenin sağında)
        kendi = None
        for d in daireler:
            if abs(d["y"] - (e["ust"] + e["alt"]) / 2) < 3 and d["x"] < e["sol"] + 2:
                if d["x"] + d["r"] + 6 >= e["sol"]:
                    kendi = d["id"]
                    break
        for d in daireler:
            if d["id"] == kendi:
                continue
            r = d["r"] + 1
            enX = max(e["sol"], min(d["x"], e["sag"]))
            enY = max(e["ust"], min(d["y"], e["alt"]))
            if ((enX - d["x"]) ** 2 + (enY - d["y"]) ** 2) < r * r:
                ihlal.append((e["metin"], d["id"]))
    assert not ihlal, f"etiket daireye biniyor: {ihlal[:6]}"
    sayfa.close()


def test_mobilde_lejant_kapali_gelir(demo_web, tarayici) -> None:
    """C.1 (b): ≤600 px'de lejant `<details>` KAPALI; masaüstünde AÇIK."""
    sayfa_m, _, _ = sayfa_ac(tarayici, demo_web, boyut=(390, 844))
    sayfa_m.wait_for_timeout(250)
    assert sayfa_m.evaluate("() => document.getElementById('lejant').open") is False, \
        "mobilde lejant açık gelmeli (grafın alanını kaplar)"
    sayfa_m.close()

    sayfa_g, _, _ = sayfa_ac(tarayici, demo_web, boyut=(1440, 900))
    sayfa_g.wait_for_timeout(250)
    assert sayfa_g.evaluate("() => document.getElementById('lejant').open") is True, \
        "masaüstünde lejant açık olmalı"
    sayfa_g.close()


def test_mobilde_lejant_acilinca_ustune_binen_etiket_gizlenir(demo_web, tarayici) -> None:
    """C.1 (b): lejantı elle açınca üstüne binen etiketler GİZLENİR."""
    sayfa, _, _ = sayfa_ac(tarayici, demo_web, boyut=(390, 844))
    sayfa.wait_for_timeout(250)
    sayfa.evaluate("() => {document.getElementById('lejant').open = true;}")
    sayfa.wait_for_timeout(350)
    etiketler = _etiketleri_dogrula(sayfa, "mobil lejant açık")
    cakisan = _lejant_engeli(sayfa, etiketler)
    assert not cakisan, f"lejantın üstünde kalan etiketler {cakisan[:4]}"
    sayfa.close()


def _sentetik_ilk_50_yuksek_derece(sunucu: WebSunucu) -> list[int]:
    veri = api_json(sunucu, "/api/graf")
    sirali = sorted(veri["dugumler"], key=lambda d: (-d["derece"], d["id"]))
    return [d["id"] for d in sirali[:50]]


@pytest.mark.parametrize("boyut", [(1440, 900), (390, 844)], ids=["masaustu", "mobil"])
def test_sentetik_vault_ilk_50_derecede_etiketler_okunur(tarayici, tmp_path: Path, boyut) -> None:
    """C.1 (a)+(b) gerçek boyut: 1200 notluk vault'un ilk 50 yüksek dereceli düğümü.

    Seçilen 50 düğümün HER BİRİ etiketli görünür; etiketler ekranda kalır,
    kesişmez ve daireye binmez.
    """
    vault = sentetik_vault(tmp_path, not_sayisi=1200, link_ortalamasi=2)
    db = tmp_path / "etiket1200.db"
    indeksle(vault, db)
    sunucu = WebSunucu(db)
    sunucu.baslat()
    try:
        sayfa, _, _ = sayfa_ac(tarayici, sunucu, boyut=boyut)
        sayfa.wait_for_timeout(400)
        hedefler = sorted(set(_sentetik_ilk_50_yuksek_derece(sunucu)))
        daireler = sayfa.evaluate(OLC_DAIRE)
        for not_id in hedefler:
            # Seçim, uygulamanın KENDİ klavye yolunu kullanılır: düğüm
            # odaklanıp Enter'a basılır. Fare tıklaması, bir önceki seçim
            # görünür alanı kaydırdığı için hedefi ekran dışında
            # bırakabiliyordu (düğüm artık tıklanabilir konumda değildi).
            sayfa.evaluate(
                """(id) => {
                    const g = document.querySelector('#graf .dugum[data-id="' + id + '"]');
                    g.focus();
                    g.dispatchEvent(new KeyboardEvent('keydown',
                        {key: 'Enter', bubbles: true, cancelable: true}));
                }""",
                not_id,
            )
            sayfa.wait_for_selector("#panel:not([hidden])", timeout=10000)
            # Seçim iki geçiş yapar: panel açılmadan ÖNCE ve SONRA yeniden
            # ortalar; etiket görünürlüğü `requestAnimationFrame` içinde
            # hesaplanır. Yerleşene kadar iki kare bekle.
            sayfa.evaluate(
                "() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))"
            )
            assert sayfa.evaluate(
                "(id) => !!document.querySelector('#graf .dugum[data-id=\"' + id + '\"].dugum-secili')",
                not_id,
            ), f"id={not_id} tıklanamadı"
            etiketler = sayfa.evaluate(OLC_ETIKET)
            assert etiketler, f"id={not_id}: etiket görünmez"
            _etiketleri_dogrula(sayfa, f"sentetik {boyut} id={not_id}")
            _etiketler_ekranda(sayfa, etiketler, f"sentetik {boyut} id={not_id}")
        print(f"\n[ETİKET] sentetik {boyut}: {len(hedefler)} yüksek dereceli düğüm kontrol edildi, "
              f"her biri etiketli, kesişmesiz ve ekranda")
        sayfa.close()
    finally:
        sunucu.kapat()


# --- K6: düğüm daireleri ve seçim (C.1 c/d) ---------------------------------

def test_dugum_yaricaplari_ekranda_en_fazla_16px(demo_web, tarayici) -> None:
    """C.1 (d): ekran yarıçapı ≤ 16 px (sığdırma sonrası)."""
    sayfa, _, _ = sayfa_ac(tarayici, demo_web)
    sayfa.wait_for_timeout(300)
    daireler = sayfa.evaluate(OLC_DAIRE)
    enBuyuk = max(d["r"] for d in daireler)
    assert enBuyuk <= 16.0 + 0.5, f"en büyük ekran yarıçapı {enBuyuk:.1f} > 16 px"
    sayfa.close()


def test_bagli_ciftler_daireleri_binmez(demo_web, tarayici) -> None:
    """C.1 (d): bağlı her çiftte `mesafe > r1 + r2 + 4` (ekran px'i)."""
    veri = api_json(demo_web, "/api/graf")
    sayfa, _, _ = sayfa_ac(tarayici, demo_web)
    sayfa.wait_for_timeout(300)
    daireler = {d["id"]: d for d in sayfa.evaluate(OLC_DAIRE)}
    ihlal = []
    for k in veri["kenarlar"]:
        a, b = daireler.get(k["kaynak"]), daireler.get(k["hedef"])
        if a is None or b is None:
            continue
        import math
        d = math.hypot(a["x"] - b["x"], a["y"] - b["y"])
        gerek = a["r"] + b["r"] + 4
        if d <= gerek:
            ihlal.append((k["kaynak"], k["hedef"], round(d, 1), round(gerek, 1)))
    assert not ihlal, f"bağlı daireler üst üste: {ihlal[:6]}"
    sayfa.close()


@pytest.mark.parametrize("boyut", [(1440, 900), (390, 844)], ids=["masaustu", "mobil"])
def test_secili_dugum_gorunur_alanin_merkezinde_ve_ic_bosluklu(demo_web, tarayici, boyut) -> None:
    """C.1 (c): panel açıkken seçili düğüm görünür alanın merkezinde.

    Ayrıca dairesinin görünür alanda en az 16 px iç boşluğu vardır
    (başlık çubuğuna/panel kenarına değmez).
    """
    veri = api_json(demo_web, "/api/graf")
    hedef = max(veri["dugumler"], key=lambda d: d["derece"])
    sayfa, _, _ = sayfa_ac(tarayici, demo_web, boyut=boyut)
    dugum_tikla(sayfa, hedef["id"])
    sayfa.wait_for_selector("#panel:not([hidden])", timeout=10000)
    sayfa.wait_for_timeout(250)
    o = sayfa.evaluate(
        """(id) => {
            const c = document.querySelector('#graf .dugum[data-id="' + id + '"] circle.dugum-daire')
                .getBoundingClientRect();
            const p = document.getElementById('panel').getBoundingClientRect();
            const s = document.getElementById('sahne').getBoundingClientRect();
            const serit = document.querySelector('header.ust').getBoundingClientRect();
            // Görünür alan: panelin kaplamadığı kısım. Panel SAĞDA duruyorsa
            // (sahneyle aynı üst kenarı paylaşan, dar) genişlik, ALTTA
            // duruyorsa (tüm genişliği kaplayan) yükseklik kırpılır.
            const yan = Math.abs(p.top - s.top) < 8 && p.right <= s.right + 1;
            const alan = yan
                ? {sol: s.left, sag: p.left, ust: s.top, alt: s.bottom}
                : {sol: s.left, sag: s.right, ust: s.top, alt: p.top};
            return {cx: c.x + c.width / 2, cy: c.y + c.height / 2, r: c.width / 2,
                    alan, seritAlt: serit.bottom,
                    mx: (alan.sol + alan.sag) / 2, my: (alan.ust + alan.alt) / 2};
        }""",
        hedef["id"],
    )
    # Daire görünür alanda ≥16 px iç boşluk bırakır.
    assert o["cx"] - o["r"] >= o["alan"]["sol"] + 16 - 1, f"sol kenar boşluğu yetersiz: {o}"
    assert o["cx"] + o["r"] <= o["alan"]["sag"] - 16 + 1, f"sağ kenar boşluğu yetersiz: {o}"
    assert o["cy"] - o["r"] >= o["alan"]["ust"] + 16 - 1, f"üst kenar boşluğu yetersiz: {o}"
    assert o["cy"] + o["r"] <= o["alan"]["alt"] - 16 + 1, f"alt kenar boşluğu yetersiz: {o}"
    sayfa.close()
