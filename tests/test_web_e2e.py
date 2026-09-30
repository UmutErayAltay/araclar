"""Dalga C e2e: GERÇEK `atlas web` süreci + Playwright/Chromium.

Bu testler Flask test client DEĞİL, gerçek bir sunucu süreci ve gerçek bir
tarayıcı kullanır. Kurgusal (uydurma) veriyle çalışır: gerçek repo adı, yol,
kişi adı veya anahtar YOKTUR.

Ölçülebilir kabul kriterleri:
  * Tüm sayfalar çizilir; konsol ve `pageerror` BOŞ.
  * XSS yükü çalışmaz (`window.__xss` tanımsız).
  * Masaüstü (1440x900) ve mobil (390x844): yatay kaydırma YOK.
  * TÜM görünür metin öğeleri pencere genişliği içinde.
  * Hiçbir öğe gezinme çubuğunun ARKASINDA kalmaz.
  * Buton/kontrollerin hesaplanmış arka planı BEYAZ DEĞİL.
  * Ana metin/zemin kontrastı >= 4.5:1.
  * SVG etiketleri >= 11 px ve birbirini kesmiyor.
  * Süzgeç formu çalışır (`/sizinti?siddet=yuksek` yalnız yüksek gösterir).
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from conftest import REPO_ROOT, db_doldur

pytestmark = pytest.mark.e2e

#: Chromium yolu (bu makinede `/opt/pw-browsers` altinda kurulu).
BROWSER_YOLU = os.environ.get("PW_CHROMIUM", "/opt/pw-browsers")

MASAUSTU = {"width": 1440, "height": 900}
MOBIL = {"width": 390, "height": 844}

SAYFALAR = ["/", "/yarim-is", "/sizinti", "/borc"]


def _kayitli_browser() -> str | None:
    """Chromium yürütülebilirini bulur (yoksa test atlanır)."""
    adaylar = [
        os.environ.get("PW_CHROMIUM_EXECUTABLE"),
        str(Path(BROWSER_YOLU) / "chromium-1243" / "chrome-linux" / "chrome"),
        str(Path(BROWSER_YOLU) / "chromium-1194" / "chrome-linux" / "chrome"),
        shutil.which("chromium"),
        shutil.which("google-chrome"),
    ]
    for aday in adaylar:
        if aday and Path(aday).exists():
            return aday
    return None


def _bos_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="module")
def kurgusal_db(tmp_path_factory) -> Path:
    """E2E için kurgusal veri: yollar `/kurgusal/...`, uydurma adlar."""
    dizin = tmp_path_factory.mktemp("e2e")
    sir = "sk-" + ("k" + "7") * 12  # parçalardan: kaynakta tam literal YOK
    db_doldur(
        dizin / "e2e.db",
        repos=[
            {"path": "/kurgusal/ornek-api", "name": "ornek-api", "dirty": 4,
             "unpushed": 3, "branch": "main", "last_commit_at": "2026-09-29T09:12:00+00:00",
             "has_remote": 1, "scanned_at": "2026-09-29T10:00:00+00:00"},
            {"path": "/kurgusal/demo-arayuz", "name": "demo-arayuz", "dirty": 0,
             "unpushed": None, "branch": "feat/yeni", "last_commit_at": "2026-09-28T14:03:00+00:00",
             "has_remote": 1, "scanned_at": "2026-09-29T10:00:00+00:00"},
            {"path": "/kurgusal/ornek-kutuphane", "name": "ornek-kutuphane", "dirty": 1,
             "unpushed": 1, "branch": "main", "last_commit_at": "2026-09-25T08:44:00+00:00",
             "has_remote": 1, "scanned_at": "2026-09-29T10:00:00+00:00"},
            {"path": "/kurgusal/deneme-araci", "name": "deneme-araci", "dirty": 0,
             "unpushed": 0, "branch": "main", "last_commit_at": "2026-09-20T11:22:00+00:00",
             "has_remote": 0, "scanned_at": "2026-09-29T10:00:00+00:00"},
        ],
        findings=[
            {"repo": "/kurgusal/ornek-api", "kind": "api-anahtari", "severity": "yuksek",
             "file": "app/yapilandirma.py", "line": 18, "commit": None,
             "snippet_redacted": f'token = "{sir}"'},
            {"repo": "/kurgusal/ornek-api", "kind": "ozel-anahtar", "severity": "yuksek",
             "file": "certs/servis.pem", "line": 1, "commit": "a1b2c3d",
             "snippet_redacted": "-----BEGIN RSA PRIVATE KEY-----…"},
            {"repo": "/kurgusal/demo-arayuz", "kind": "env-izlenen", "severity": "yuksek",
             "file": ".env.production", "line": None, "commit": None,
             "snippet_redacted": None},
            {"repo": "/kurgusal/demo-arayuz", "kind": "kisisel-yol", "severity": "orta",
             "file": "belgeler/kurulum.md", "line": 9, "commit": "e4f5a6b",
             "snippet_redacted": "klasor: C:\\Users\\<kullanici>\\belgeler"},
            {"repo": "/kurgusal/ornek-kutuphane", "kind": "e-posta", "severity": "dusuk",
             "file": "ILETISIM.md", "line": 3, "commit": None,
             "snippet_redacted": "iletisim: <e-posta>"},
            {"repo": "/kurgusal/deneme-araci", "kind": "gorsel-elle-kontrol", "severity": "bilgi",
             "file": "docs/ekran/ornek.png", "line": None, "commit": None,
             "snippet_redacted": "elle kontrol et (kişisel veri/yol/anahtar var mı)"},
        ],
        todos=[
            {"repo": "/kurgusal/ornek-api", "file": "app/yapilandirma.py", "line": 31,
             "text": "# TODO: ortam degiskenlerini tek noktadan oku"},
            {"repo": "/kurgusal/ornek-api", "file": "app/yapilandirma.py", "line": 52,
             "text": "# FIXME: varsayilan degerler kaynakta duruyor"},
            {"repo": "/kurgusal/ornek-api", "file": "app/modeller.py", "line": 8,
             "text": "# TODO: model alanlarini dogrula"},
            {"repo": "/kurgusal/demo-arayuz", "file": "src/panel.js", "line": 210,
             "text": "// HACK: gecici; duzeltmeden once paneli acma"},
            {"repo": "/kurgusal/demo-arayuz", "file": "src/panel.js", "line": 244,
             "text": "// TODO: klavye kisayollari eksik"},
            {"repo": "/kurgusal/ornek-kutuphane", "file": "README.md", "line": 12,
             "text": "# XXX: ornekler guncel degil"},
        ],
    )
    return dizin / "e2e.db"


@pytest.fixture(scope="module")
def canli_sunucu(kurgusal_db: Path):
    """GERCEK `atlas web` alt sureci. Test sonunda kapatilir."""
    executable = _kayitli_browser()
    if executable is None:
        pytest.skip("Chromium bulunamadi (/opt/pw-browsers)")
    try:
        import playwright  # noqa: F401
    except ImportError:
        pytest.skip("playwright kurulu degil")

    port = _bos_port()
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT)
    env.pop("ATLAS_DB", None)
    surec = subprocess.Popen(
        [sys.executable, "-m", "atlas", "web", "--db", str(kurgusal_db), "--port", str(port)],
        cwd=str(REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
        text=True,
    )
    taban = f"http://127.0.0.1:{port}"
    for _ in range(100):  # 10 sn bekle
        if surec.poll() is not None:
            pytest.fail(f"atlas web erken sonlandi: {surec.stdout.read() if surec.stdout else ''}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)
    else:
        surec.kill()
        pytest.fail("atlas web 10 sn icinde acilmadi")
    yield {"taban": taban, "surec": surec, "chromium": executable}
    surec.terminate()
    try:
        surec.wait(timeout=10)
    except subprocess.TimeoutExpired:  # pragma: no cover
        surec.kill()


@pytest.fixture
def sayfa(canli_sunucu):
    """Yeni bir sayfa: konsol + sayfa hataları toplanır, test sonunda kapanır."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        tarayici = p.chromium.launch(
            executable_path=canli_sunucu["chromium"],
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        baglam = tarayici.new_context(viewport=MASAUSTU)
        sayfa_ = baglam.new_page()
        konsol: list[str] = []
        hatalar: list[str] = []
        sayfa_.on("console", lambda m: konsol.append(f"{m.type}: {m.text}")
                  if m.type in ("error", "warning") else None)
        sayfa_.on("pageerror", lambda e: hatalar.append(str(e)))
        sayfa_.gunucu = konsol  # type: ignore[attr-defined]
        sayfa_.hatalar = hatalar  # type: ignore[attr-defined]
        try:
            yield sayfa_
        finally:
            baglam.close()
            tarayici.close()


def _git(sayfa_, yol: str, viewport=None):
    if viewport:
        sayfa_.set_viewport_size(viewport)
    cevap = sayfa_.goto(f"{sayfa_.base_url}{yol}" if hasattr(sayfa_, "base_url") else yol,
                        wait_until="networkidle")
    return cevap


#: Sayfa nesnesine taban adresini ekler (fixture icinde).
@pytest.fixture
def canli(sayfa, canli_sunucu):
    sayfa.goto_basi = canli_sunucu["taban"]  # type: ignore[attr-defined]
    return sayfa


def ac(sayfa_, canli_sunucu, yol: str, viewport=None):
    if viewport:
        sayfa_.set_viewport_size(viewport)
    cevap = sayfa_.goto(f"{canli_sunucu['taban']}{yol}", wait_until="networkidle")
    return cevap


# --------------------------------------------------------------------------
# 1) Sayfalar çizilir; konsol ve pageerror BOŞ
# --------------------------------------------------------------------------


@pytest.mark.parametrize("yol", SAYFALAR)
def test_sayfa_cizilir_konsol_bos(canli, canli_sunucu, yol: str):
    cevap = ac(canli, canli_sunucu, yol)
    assert cevap.status == 200
    assert canli.title(), "sayfa basligi yok"
    assert canli.locator("main").is_visible()
    assert canli.hatalar == [], f"pageerror: {canli.hatalar}"
    assert canli.gunucu == [], f"konsol ciktilari: {canli.gunucu}"


@pytest.mark.parametrize("yol", SAYFALAR)
def test_yanit_basliklari_gelir(canli, canli_sunucu, yol: str):
    cevap = ac(canli, canli_sunucu, yol)
    assert cevap.headers["content-security-policy"].startswith("default-src 'none'")
    assert cevap.headers["x-content-type-options"] == "nosniff"
    assert cevap.headers["cache-control"] == "no-store"


def test_hepsi_bos_derken_sayfa_hatasi_yok(canli, canli_sunucu, kurgusal_db: Path):
    """Aynı sunucuda boş DB'ye geçilemez ama her rota 200 dönmeli (yukarıda)."""
    for yol in SAYFALAR:
        assert ac(canli, canli_sunucu, yol).status == 200


# --------------------------------------------------------------------------
# 2) Yatay kaydırma yok + görünür metin pencere içinde
# --------------------------------------------------------------------------


def _yatay_tasma(sayfa_) -> dict:
    return sayfa_.evaluate(
        "() => ({docW: document.documentElement.scrollWidth,"
        " innerW: window.innerWidth,"
        " bodyW: document.body.scrollWidth})"
    )


@pytest.mark.parametrize("yol", SAYFALAR)
@pytest.mark.parametrize("viewport,ad", [(MASAUSTU, "masaustu"), (MOBIL, "mobil")])
def test_yatay_kaydirma_cubugu_yok(canli, canli_sunucu, yol: str, viewport, ad: str):
    ac(canli, canli_sunucu, yol, viewport)
    o = _yatay_tasma(canli)
    assert o["docW"] <= o["innerW"] + 1, f"{ad} {yol}: {o}"
    assert o["bodyW"] <= o["innerW"] + 1, f"{ad} {yol}: {o}"


@pytest.mark.parametrize("yol", SAYFALAR)
@pytest.mark.parametrize("viewport,ad", [(MASAUSTU, "masaustu"), (MOBIL, "mobil")])
def test_gorunur_metinler_pencere_ici(canli, canli_sunucu, yol: str, viewport, ad: str):
    """TÜM görünür metin öğeleri `getBoundingClientRect()` ile pencere içinde."""
    ac(canli, canli_sunucu, yol, viewport)
    tasanlar = canli.evaluate(
        """() => {
          const genislik = document.documentElement.clientWidth;
          const kotu = [];
          const seciciler = 'h1,h2,h3,p,td,th,li,a,span,strong,code,pre,label,dt,dd,button,div';
          for (const el of document.querySelectorAll(seciciler)) {
            const st = getComputedStyle(el);
            if (st.display === 'none' || st.visibility === 'hidden' || el.offsetParent === null
                && st.position !== 'fixed') continue;
            const r = el.getBoundingClientRect();
            if (r.width === 0 && r.height === 0) continue;
            // Metin içeren öğeler: içinde gerçek metin olsun.
            const metin = (el.innerText || '').trim();
            if (!metin) continue;
            if (r.right > genislik + 1 || r.left < -1) {
              kotu.push({tag: el.tagName, cls: el.className, metin: metin.slice(0, 50),
                         left: Math.round(r.left), right: Math.round(r.right)});
            }
          }
          return kotu;
        }"""
    )
    assert tasanlar == [], f"{ad} {yol} tasma: {tasanlar[:5]}"


# --------------------------------------------------------------------------
# 3) Gezinme çubuğu içeriği kapatmaz
# --------------------------------------------------------------------------


@pytest.mark.parametrize("yol", SAYFALAR)
@pytest.mark.parametrize("viewport,ad", [(MASAUSTU, "masaustu"), (MOBIL, "mobil")])
def test_gezinme_cubugu_iceriği_kapatmaz(canli, canli_sunucu, yol: str, viewport, ad: str):
    """Çubuk HER sayfada tam görünür ve içeriğin ilk öğesi çubuğun ALTINDA başlar."""
    ac(canli, canli_sunucu, yol, viewport)
    sonuc = canli.evaluate(
        """() => {
          const cubuk = document.querySelector('header.ust');
          const icerik = document.querySelector('main');
          if (!cubuk || !icerik) return {hata: 'cubuk/icerik yok'};
          const c = cubuk.getBoundingClientRect();
          const i = icerik.getBoundingClientRect();
          const cubukGizli = cubuk.scrollWidth > cubuk.clientWidth + 1
            || cubuk.scrollHeight > cubuk.clientHeight + 1;
          return {
            cubukUst: c.top, cubukAlt: c.bottom, cubukGizli: cubukGizli,
            icerikUst: i.top,
            navGorunur: getComputedStyle(cubuk).visibility === 'visible'
                        && getComputedStyle(cubuk).display !== 'none',
          };
        }"""
    )
    assert "hata" not in sonuc, sonuc
    assert sonuc["navGorunur"] is True, f"{ad} {yol}: navigasyon gorunur degil"
    assert sonuc["cubukGizli"] is False, f"{ad} {yol}: cubuk tasiyor/kesiliyor"
    assert sonuc["cubukAlt"] <= sonuc["icerikUst"] + 1, (
        f"{ad} {yol}: icerik cubugun ALTINDA degil {sonuc}"
    )


@pytest.mark.parametrize("yol", SAYFALAR)
def test_navigasyon_linkleri_her_sayfada_tam(canli, canli_sunucu, yol: str):
    ac(canli, canli_sunucu, yol)
    for hedef in ["/", "/yarim-is", "/sizinti", "/borc"]:
        bulunan = canli.locator(f'header.ust a[href="{hedef}"]')
        assert bulunan.count() == 1, f"{hedef} linki eksik ({yol})"
        assert bulunan.is_visible(), f"{hedef} linki gorunur degil ({yol})"


# --------------------------------------------------------------------------
# 4) Beyaz kontrol yok + kontrast
# --------------------------------------------------------------------------


@pytest.mark.parametrize("yol", ["/sizinti", "/borc"])
@pytest.mark.parametrize("viewport,ad", [(MASAUSTU, "masaustu"), (MOBIL, "mobil")])
def test_beyaz_kontrol_yok(canli, canli_sunucu, yol: str, viewport, ad: str):
    """Süzgeç kontrolleri (select/input/button) hesaplanmış arka planı BEYAZ DEĞİL.

    `/borc` form içermez; test o sayfada kontrol bulunamayacağı için
    ayrıca doğrulanır (aşağıda).
    """
    """Buton/select/input hesaplanmış arka planı `rgb(255, 255, 255)` DEĞİL."""
    ac(canli, canli_sunucu, yol, viewport)
    beyazlar = canli.evaluate(
        """() => {
          const kotu = [];
          for (const el of document.querySelectorAll('button, select, input, a.btn')) {
            const st = getComputedStyle(el);
            if (st.display === 'none' || st.visibility === 'hidden') continue;
            const r = el.getBoundingClientRect();
            if (r.width === 0 || r.height === 0) continue;
            kotu.push({tag: el.tagName, arka: st.backgroundColor, sinir: st.borderColor});
          }
          return kotu;
        }"""
    )
    if yol == "/sizinti":
        assert beyazlar, "kontrol bulunamadi (test bos gecmis olurdu)"
    for k in beyazlar:
        assert k["arka"] != "rgb(255, 255, 255)", f"{ad} {yol}: BEYAZ kontrol {k}"


@pytest.mark.parametrize("viewport", [MASAUSTU, MOBIL])
def test_borc_form_kontrolu_yok(canli, canli_sunucu, viewport):
    """`/borc` yalnız GÖRÜNTÜLEYİCİ bir sayfa: form/buton kontrolü YOKTUR."""
    ac(canli, canli_sunucu, "/borc", viewport)
    assert canli.locator("form").count() == 0
    assert canli.locator("button, select, input").count() == 0


def test_ana_kontrast_canli(canli, canli_sunucu):
    """Ana metin/zemin kontrastı >= 4.5:1."""
    ac(canli, canli_sunucu, "/")
    oran = canli.evaluate(
        """() => {
          const st = getComputedStyle(document.body);
          function parlaklik(renk) {
            const m = renk.match(/\\d+/g).map(Number);
            const [r, g, b] = m;
            const f = (c) => { c /= 255; return c <= 0.03928 ? c/12.92 : Math.pow((c+0.055)/1.055, 2.4); };
            return 0.2126*f(r) + 0.7152*f(g) + 0.0722*f(b);
          }
          const a = parlaklik(st.color), b = parlaklik(st.backgroundColor);
          return (Math.max(a,b) + 0.05) / (Math.min(a,b) + 0.05);
        }"""
    )
    assert oran >= 4.5, f"kontrast {oran:.2f} < 4.5:1"


def test_ikincil_metin_kontrast(canli, canli_sunucu):
    """İkincil metin de okunabilir (>= 4.5:1)."""
    ac(canli, canli_sunucu, "/")
    oran = canli.evaluate(
        """() => {
          const el = document.querySelector('.aciklama, .ozet');
          const st = getComputedStyle(el);
          function parlaklik(renk) {
            const [r, g, b] = renk.match(/\\d+/g).map(Number);
            const f = (c) => { c /= 255; return c <= 0.03928 ? c/12.92 : Math.pow((c+0.055)/1.055, 2.4); };
            return 0.2126*f(r) + 0.7152*f(g) + 0.0722*f(b);
          }
          let arka = st.backgroundColor;
          let e = el;
          while (arka === 'rgba(0, 0, 0, 0)' && e.parentElement) {
            e = e.parentElement; arka = getComputedStyle(e).backgroundColor;
          }
          const a = parlaklik(st.color), b = parlaklik(arka);
          return (Math.max(a,b) + 0.05) / (Math.min(a,b) + 0.05);
        }"""
    )
    assert oran >= 4.5, f"ikincil kontrast {oran:.2f} < 4.5:1"


# --------------------------------------------------------------------------
# 5) SVG etiketleri >= 11 px ve kesişmez
# --------------------------------------------------------------------------


def test_svg_etiketleri_okunur(canli, canli_sunucu):
    """SVG metin etiketleri >= 11 px ve birbirleriyle KESİŞMEZ."""
    for yol in ("/", "/borc"):
        ac(canli, canli_sunucu, yol)
        kutu = canli.evaluate(
            """() => {
              const etiketler = [];
              for (const svg of document.querySelectorAll('svg.graf')) {
                for (const t of svg.querySelectorAll('text')) {
                  const st = getComputedStyle(t);
                  if (st.display === 'none') continue;
                  const r = t.getBoundingClientRect();
                  etiketler.push({
                    metin: (t.textContent || '').trim(),
                    boyut: parseFloat(st.fontSize),
                    x: r.left, y: r.top, genislik: r.width, yukseklik: r.height,
                  });
                }
              }
              return etiketler;
            }"""
        )
        if not kutu:
            continue
        for e in kutu:
            assert e["boyut"] >= 11, f"{yol}: '{e['metin']}' {e['boyut']}px < 11px"
        for i in range(len(kutu)):
            for j in range(i + 1, len(kutu)):
                a, b = kutu[i], kutu[j]
                cakisma = (
                    a["x"] < b["x"] + b["genislik"] and b["x"] < a["x"] + a["genislik"]
                    and a["y"] < b["y"] + b["yukseklik"] and b["y"] < a["y"] + a["yukseklik"]
                )
                assert not cakisma, (
                    f"{yol}: '{a['metin']}' ile '{b['metin']}' kesisiyor"
                )


def test_borc_cubuklari_olculu_genislik(canli, canli_sunucu):
    """Yoğunluk çubukları JS ile GERÇEKTEN genişlik alır (0 değil)."""
    ac(canli, canli_sunucu, "/borc")
    genislikler = canli.evaluate(
        "() => [...document.querySelectorAll('.cubuk')].map(c => c.getBoundingClientRect().width)"
    )
    assert genislikler, "cubuk bulunamadi"
    assert max(genislikler) > 10, f"cubuklar olcu almadi: {genislikler}"


# --------------------------------------------------------------------------
# 6) XSS yükü çalışmaz
# --------------------------------------------------------------------------


def test_xss_yuku_calismaz(canli, canli_sunucu, tmp_path_factory, kurgusal_db: Path):
    """Gerçek tarayıcıda yük basılır, `window.__xss` TANIMSIZ kalır.

    Ayrı DB: XSS yüklü kayıtlar eklenir, aynı sunucu DB'yi okur (mode=ro,
    panel yazmaz — yeni bağlantı yeni bağlamda açar).
    """
    from conftest import db_doldur

    xss_db = db_doldur(
        kurgusal_db.with_name("e2e-xss.db"),
        repos=[{"path": "/kurgusal/xss", "name": '<img src=x onerror="window.__xss=1">',
                "dirty": 1, "unpushed": None, "branch": "main", "has_remote": 1,
                "scanned_at": "2026-09-29T10:00:00+00:00"}],
        findings=[{"repo": "/kurgusal/xss", "kind": "api-anahtari", "severity": "yuksek",
                   "file": "<script>window.__xss=1</script>", "line": 1, "commit": None,
                   "snippet_redacted": "<script>window.__xss=1</script>"}],
        todos=[{"repo": "/kurgusal/xss", "file": "<script>window.__xss=1</script>",
                "line": 2, "text": "<script>window.__xss=1</script>"}],
    )

    # Yeni surec, XSS DB ile.
    port = _bos_port()
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT)
    env.pop("ATLAS_DB", None)
    surec = subprocess.Popen(
        [sys.executable, "-m", "atlas", "web", "--db", str(xss_db), "--port", str(port)],
        cwd=str(REPO_ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        env=env, text=True,
    )
    try:
        for _ in range(100):
            if surec.poll() is not None:
                pytest.fail("XSS sunucusu erken sonlandi")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.1)
        taban = f"http://127.0.0.1:{port}"
        for yol in ("/", "/yarim-is", "/sizinti", "/borc"):
            canli.goto(f"{taban}{yol}", wait_until="networkidle")
            assert canli.evaluate("() => typeof window.__xss") == "undefined", (
                f"XSS {yol} üzerinde çalıştı"
            )
            assert canli.hatalar == [], f"{yol} pageerror: {canli.hatalar}"
    finally:
        surec.terminate()
        try:
            surec.wait(timeout=10)
        except subprocess.TimeoutExpired:  # pragma: no cover
            surec.kill()


# --------------------------------------------------------------------------
# 7) Süzgeç formu çalışır
# --------------------------------------------------------------------------


def test_siddet_suzgeci_calisir(canli, canli_sunucu):
    """`/sizinti?siddet=yuksek` yalnız YÜKSEK bulguları gösterir."""
    ac(canli, canli_sunucu, "/sizinti")
    tum = canli.locator(".tablo-sarayici tbody tr").count()
    assert tum == 6, f"tum bulgu sayisi {tum} != 6"

    cevap = ac(canli, canli_sunucu, "/sizinti?siddet=yuksek")
    assert cevap.status == 200
    yuksek = canli.locator(".tablo-sarayici tbody tr").count()
    assert yuksek == 3, f"yuksek bulgu sayisi {yuksek} != 3"
    rozetler = canli.locator(".tablo-sarayici .rozet.yuksek").count()
    assert rozetler == 3
    assert canli.locator(".tablo-sarayici .rozet.dusuk").count() == 0
    assert canli.locator(".tablo-sarayici .rozet.bilgi").count() == 0
    # Filtre seçimi korunur.
    assert canli.locator("#f-siddet").input_value() == "yuksek"


def test_tur_suzgeci_calisir(canli, canli_sunucu):
    ac(canli, canli_sunucu, "/sizinti?tur=api-anahtari")
    assert canli.locator(".tablo-sarayici tbody tr").count() == 1
    assert canli.locator("#f-tur").input_value() == "api-anahtari"


def test_formu_gondererek_suzgecle(canli, canli_sunucu):
    """Formu gerçekten GÖNDERMEK de çalışır (GET)."""
    ac(canli, canli_sunucu, "/sizinti")
    canli.select_option("#f-siddet", "yuksek")
    canli.click("button[type=submit]")
    canli.wait_for_load_state("networkidle")
    assert "siddet=yuksek" in canli.url
    assert canli.locator(".tablo-sarayici tbody tr").count() == 3


def test_bos_suzgec_bos_durum(canli, canli_sunucu):
    """`ornek-kutuphane` yalnız `e-posta` bulgusuna sahip; `api-anahtari` YOK.

    Aynı repoda hem eşleşen hem eşleşmeyen tür bulunur: süzgecin gerçekten
    SADECE istenen türü gösterdiğini de kanıtlar.
    """
    cevap = ac(canli, canli_sunucu, "/sizinti?repo=/kurgusal/ornek-kutuphane&tur=api-anahtari")
    assert cevap.status == 200
    assert canli.locator(".tablo-sarayici tbody tr").count() == 0
    assert canli.locator(".bos-durum").is_visible()
    assert "Bu filtrede bulgu yok" in canli.locator(".bos-durum").inner_text()


# --------------------------------------------------------------------------
# 8) Mobil: tablo -> kart geçişi
# --------------------------------------------------------------------------


def test_mobilde_tablo_kart_olur(canli, canli_sunucu):
    ac(canli, canli_sunucu, "/sizinti", MOBIL)
    assert not canli.locator(".tablo-sarayici").is_visible(), "masaustu tablosu gorunuyor"
    assert canli.locator(".kart-liste").is_visible(), "kart gorunumu acik degil"
    assert canli.locator(".kart-liste .kart").count() == 6


def test_masaustunde_tablo_gorunur(canli, canli_sunucu):
    ac(canli, canli_sunucu, "/sizinti", MASAUSTU)
    assert canli.locator(".tablo-sarayici").is_visible()
    assert not canli.locator(".kart-liste").is_visible()