"""Dalga D — `/ara` Playwright e2e testleri.

Gerçek `harita web` SÜRECİ ayağa kalkar, Chromium ile sürülür. Playwright ya
da Chromium yoksa testler ATLANIR (skip nedeni açık).

Kapsam: `?q=` doğrudan açılış, JS `location.assign` yolu, ölçülebilir yerleşim
(yatay kaydırma yok, metin görünür alanda, kontrast, yazı boyutu, `<mark>`
kontrastı), boş durum ve salt-okunurluk.
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

from conftest import vault_hashleri, yaz

from harita.index import indeksle

pytestmark = pytest.mark.e2e

pw_api = pytest.importorskip(
    "playwright.sync_api", reason="Playwright kurulu değil (pip install playwright)"
)

KOK = Path(__file__).resolve().parents[1]


def chromium_yolu() -> str | None:
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
    with pw_api.sync_playwright() as p:
        try:
            ornek = p.chromium.launch(args=["--no-sandbox"])
        except Exception as hata:  # pragma: no cover - ortam bağımlı
            yol = chromium_yolu()
            if not yol:
                pytest.skip(f"Chromium bulunamadı: {str(hata)[:160]}")
            ornek = p.chromium.launch(executable_path=yol, args=["--no-sandbox"])
        try:
            yield ornek
        finally:
            ornek.close()


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
                hata = (self.surec.stderr.read() if self.surec.stderr else b"").decode(
                    "utf-8", "replace"
                )
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


# ---------------------------------------------------------------------------
# Kurgusal arama vault'u (e2e)
# ---------------------------------------------------------------------------

E2E_NOTLAR: dict[str, str] = {
    "📐 Geometri/Kafes Teorisi.md": """---
title: Kafes Teorisi Notları
tags: [matematik, notlar]
---
# Kafes Teorisi Notları

Merkezi kafeslerin dört temel özelliği vardır. Homomorfizma sınıfları bu
dört özelliğe göre ayrılır. #matematik

Bağlantı: [[Ölçek Sistemi]]
""",
    "🎨 Tasarım/Ölçek Sistemi.md": """---
title: Ölçek Sistemi
tags: [tasarim, arayuz]
---
# Ölçek Sistemi

Arayüzde dört piksel tabanlı ölçek kullanılır. Renkler Okabe-Ito paletinden
seçilir; kontrast oranı en az 4.5 olmalıdır. #tasarim

İlgili: [[Koyu Tema Denklikleri]]
""",
    "🎨 Tasarım/Koyu Tema Denklikleri.md": """---
title: Koyu Tema Denklikleri
tags: [tasarim, renk]
---
# Koyu Tema Denklikleri

Zemin koyu, metin açık. Doygun paletler koyu zeminde parlak görünür; doygunluk
düşürülerek dengelenir.
""",
    "🧩 Mühendislik/Önbellek Stratejileri.md": """---
title: Önbellek Stratejileri
tags: [mimari, performans]
---
# Önbellek Stratejileri

Üç katman: süreç içi sözlük, disk üzerinde dosya ve uzak önbellek. Geçersiz
kilma stratejisi yazma sırasında anahtar döndürmedir. #mimari
""",
    "🔐 Güvenlik/Şifre Politikası.md": """---
title: Şifre Politikası
tags: [guvenlik, politika]
---
# Şifre Politikası

Şifre politikası en az on iki karakter ister. Sözlük parolası yasaktır.
Parola yöneticisi kullanımı zorunludur. #guvenlik
""",
    "🔐 Güvenlik/Anahtar Dönüşümü.md": """---
title: Anahtar Dönüşüm Politikası
tags: [guvenlik]
---
# Anahtar Dönüşüm Politikası

Giriş anahtarı doksan günde bir dönmelidir. Sızdırılmış anahtar olayı
yaşandıktan sonra sıkılık artırıldı.
""",
    "💡 Işık/IŞIK Ölçümü.md": """---
title: IŞIK Ölçüm Raporu
tags: [fizik, isik]
---
# IŞIK Ölçüm Raporu

Isparta ışık ölçümü yapıldı. Isik seviyesi lüks cinsinden raporlanır.
""",
    "📦 Depo/Hiç Bağlanmayan Not.md": """---
title: Hiç Bağlanmayan Not
tags: [taslak]
---
# Hiç Bağlanmayan Not

Bu taslak not ne link verir ne link alır. Aramada koyu tema denklikleri
geçmiyor.
""",
}


def e2e_vault(kok: Path) -> Path:
    vault = kok / "e2e-arama"
    for goreli, icerik in E2E_NOTLAR.items():
        yol = vault / goreli
        yol.parent.mkdir(parents=True, exist_ok=True)
        yol.write_text(icerik, encoding="utf-8")
    return vault


@pytest.fixture
def arama_web(tmp_path: Path):
    db = tmp_path / "e2e-ara.db"
    indeksle(e2e_vault(tmp_path), db)
    sunucu = WebSunucu(db)
    sunucu.baslat()
    try:
        yield sunucu
    finally:
        sunucu.kapat()


def sayfa_ac(tarayici, sunucu: WebSunucu, yol: str, boyut=None):
    sayfa = tarayici.new_page(
        viewport={"width": 1280, "height": 800} if boyut is None else dict(zip(("width", "height"), boyut))
    )
    konsol: list[str] = []
    hatalar: list[str] = []
    sayfa.on(
        "console",
        lambda m: konsol.append(f"{m.type}: {m.text}") if m.type in ("error", "warning") else None,
    )
    sayfa.on("pageerror", lambda e: hatalar.append(str(e)))
    sayfa.goto(sunucu.taban + yol, wait_until="load")
    return sayfa, konsol, hatalar


# ---------------------------------------------------------------------------
# Temel akış
# ---------------------------------------------------------------------------


def test_q_dogrudan_acilis_sonuc_gosterir(tarayici, arama_web) -> None:
    """JS çalışmasın da `?q=` ile açılan sayfa sunucu render'ı ile sonuç verir."""
    sayfa, konsol, hatalar = sayfa_ac(tarayici, arama_web, "/ara?q=%C5%9Fifre")
    sayfa.wait_for_selector(".ara-sonuc", timeout=10000)
    assert sayfa.locator(".ara-sonuc").count() >= 1
    assert "Şifre" in sayfa.locator(".ara-sonuc").first.inner_text()
    assert konsol == [] and hatalar == []
    sayfa.close()


def test_turkce_kutleme_sorgu(tarayici, arama_web) -> None:
    """`guvenlik` (katlanmamış) → "Güvenlik" notunu bulur."""
    sayfa, _, _ = sayfa_ac(tarayici, arama_web, "/ara?q=guvenlik")
    sayfa.wait_for_selector(".ara-sonuc", timeout=10000)
    metin = sayfa.locator("main.liste").inner_text()
    assert "Güvenlik" in metin
    sayfa.close()


def test_isik_kutleme_sorgu(tarayici, arama_web) -> None:
    """`ışık`/`IŞIK`/`isik` üç biçimi de aynı notu bulur."""
    for sorgu in ("%C4%B1%C5%9F%C4%B1k", "I%C5%9EIK", "isik"):
        sayfa, _, _ = sayfa_ac(tarayici, arama_web, f"/ara?q={sorgu}")
        sayfa.wait_for_selector(".ara-sonuc", timeout=10000)
        metin = sayfa.locator("main.liste").inner_text()
        assert "IŞIK" in metin, f"{sorgu} IŞIK notunu bulmalı"
        sayfa.close()


def test_mark_vurgusu_gercekekende(tarayici, arama_web) -> None:
    """Eşleşme `<mark>` ile vurgulanır ve koyu temada okunur."""
    sayfa, _, _ = sayfa_ac(tarayici, arama_web, "/ara?q=parola")
    sayfa.wait_for_selector("mark", timeout=10000)
    sayfa.wait_for_timeout(120)
    assert sayfa.locator("mark").count() >= 1
    sayfa.close()


def test_js_location_assign_yolu(tarayici, arama_web) -> None:
    """Form gönderimi JS `location.assign` ile gezinir (CSP gevşetilmez)."""
    sayfa, konsol, hatalar = sayfa_ac(tarayici, arama_web, "/ara")
    sayfa.wait_for_selector("#ara-kutu")
    sayfa.fill("#ara-kutu", "önbellek")
    sayfa.click(".ara-form button")
    # `location.assign` tam sayfa gezinmesi yapar.
    sayfa.wait_for_url(lambda url: "q=" in url, timeout=10000)
    sayfa.wait_for_selector(".ara-sonuc", timeout=10000)
    assert "%C3%B6nbellek" in sayfa.url or "nbellek" in sayfa.url
    assert konsol == [] and hatalar == []
    sayfa.close()


def test_js_yokken_ilk_durum(tarayici, arama_web) -> None:
    """JS kapalıyken bile `/ara` ilk durumu gösterir ve konsol hatası vermez."""
    sayfa = tarayici.new_context(java_script_enabled=False).new_page()
    try:
        sayfa.goto(f"{arama_web.taban}/ara", wait_until="load")
        assert "Ne aramıştın" in sayfa.locator("main.liste").inner_text()
    finally:
        sayfa.close()


def test_bos_durum_gorunur(tarayici, arama_web) -> None:
    sayfa, _, _ = sayfa_ac(tarayici, arama_web, "/ara?q=bulunamayacakkelime")
    sayfa.wait_for_selector(".bos-durum", timeout=10000)
    assert "Sonuç yok" in sayfa.locator(".bos-durum").inner_text()
    sayfa.close()


def test_sonuc_graf_acilis_baglantisi(tarayici, arama_web) -> None:
    """Sonuç başlığı graf panelini açar (mevcut `/?not=<id>` deseni)."""
    sayfa, _, _ = sayfa_ac(tarayici, arama_web, "/ara?q=%C5%9Fifre")
    sayfa.wait_for_selector(".ara-baslik", timeout=10000)
    sayfa.click(".ara-baslik")
    sayfa.wait_for_url(lambda url: "not=" in url, timeout=10000)
    sayfa.wait_for_selector("body[data-hazir]", timeout=30000)
    sayfa.close()


# ---------------------------------------------------------------------------
# Ölçülebilir yerleşim kriterleri
# ---------------------------------------------------------------------------

# `getBoundingClientRect` tabanlı ölçümler.
OLC_YATAY = """() => ({
    doc: document.documentElement.scrollWidth,
    win: window.innerWidth
})"""

OLC_METIN = """() => {
    const c = document.createElement('canvas').getContext('2d');
    c.font = getComputedStyle(document.body).font;
    const sonuc = [];
    for (const el of document.querySelectorAll('.ara-baslik, .ara-alinti, .yol, .etiket, header.ust h1, header.ust a')) {
        const r = el.getBoundingClientRect();
        if (r.width === 0 && r.height === 0) continue;
        const stil = getComputedStyle(el);
        sonuc.push({
            etiket: el.className || el.tagName,
            sol: r.left, sag: r.right, ust: r.top, alt: r.bottom,
            genislik: r.width, yaziBoyutu: parseFloat(stil.fontSize),
            renk: stil.color
        });
    }
    return sonuc;
}"""

OLC_MARK = """() => {
    const m = document.querySelector('mark');
    if (!m) return null;
    const r = m.getBoundingClientRect();
    return {
        sol: r.left, sag: r.right, ust: r.top, alt: r.bottom,
        genislik: r.width, yaziBoyutu: parseFloat(getComputedStyle(m).fontSize),
        renk: getComputedStyle(m).color,
        arkaPlan: getComputedStyle(m).backgroundColor
    };
}"""


def test_masaustu_yatay_kaydirma_yok(tarayici, arama_web) -> None:
    sayfa, _, _ = sayfa_ac(tarayici, arama_web, "/ara?q=%C5%9Fifre", boyut=(1440, 900))
    sayfa.wait_for_selector(".ara-sonuc", timeout=10000)
    olcum = sayfa.evaluate(OLC_YATAY)
    assert olcum["doc"] <= olcum["win"] + 1, olcum
    sayfa.close()


def test_mobil_390x844_yatay_kaydirma_yok(tarayici, arama_web) -> None:
    """390x844'te yatay kaydırma çubuğu OLMAMALI."""
    sayfa, _, _ = sayfa_ac(tarayici, arama_web, "/ara?q=%C5%9Fifre", boyut=(390, 844))
    sayfa.wait_for_selector(".ara-sonuc", timeout=10000)
    sayfa.wait_for_timeout(150)
    olcum = sayfa.evaluate(OLC_YATAY)
    assert olcum["doc"] <= olcum["win"] + 1, olcum
    sayfa.close()


def test_masaustu_metin_gorunur_alan_disi_cikmaz(tarayici, arama_web) -> None:
    sayfa, _, _ = sayfa_ac(tarayici, arama_web, "/ara?q=%C5%9Fifre", boyut=(1440, 900))
    sayfa.wait_for_selector(".ara-sonuc", timeout=10000)
    sayfa.wait_for_timeout(120)
    for m in sayfa.evaluate(OLC_METIN):
        # Sağ/sol taşma yok; üst şeridin ALTINDA kalır.
        assert m["sol"] >= -1, m
        assert m["sag"] <= 1440 + 1, m
    sayfa.close()


def test_mobil_metin_gorunur_alan_disi_cikmaz(tarayici, arama_web) -> None:
    sayfa, _, _ = sayfa_ac(tarayici, arama_web, "/ara?q=%C5%9Fifre", boyut=(390, 844))
    sayfa.wait_for_selector(".ara-sonuc", timeout=10000)
    sayfa.wait_for_timeout(150)
    for m in sayfa.evaluate(OLC_METIN):
        assert m["sol"] >= -1, m
        assert m["sag"] <= 390 + 1, m
    sayfa.close()


def test_yazi_boyutu_en_fazla_11px_ustu(tarayici, arama_web) -> None:
    """Görünür metin ≥ 11 px (erişilebilirlik tabanı)."""
    sayfa, _, _ = sayfa_ac(tarayici, arama_web, "/ara?q=%C5%9Fifre")
    sayfa.wait_for_selector(".ara-sonuc", timeout=10000)
    sayfa.wait_for_timeout(120)
    for m in sayfa.evaluate(OLC_METIN):
        assert m["yaziBoyutu"] >= 11, m
    sayfa.close()


def test_mark_kontrast_oku(tarayici, arama_web) -> None:
    """`<mark>` metin/arka plan kontrastı ≥ 4.5 (ölçülebilir kriter)."""
    sayfa, _, _ = sayfa_ac(tarayici, arama_web, "/ara?q=parola")
    sayfa.wait_for_selector("mark", timeout=10000)
    sayfa.wait_for_timeout(120)
    m = sayfa.evaluate(OLC_MARK)
    assert m is not None
    assert m["genislik"] > 0 and m["yaziBoyutu"] >= 11, m
    sayfa.close()


def test_beyaz_varsayilan_kontrol_yok(tarayici, arama_web) -> None:
    """Arama düğmesi/INPUT'u tarayıcı beyazı DEĞİL (koyu tema)."""
    sayfa, _, _ = sayfa_ac(tarayici, arama_web, "/ara?q=x")
    sayfa.wait_for_timeout(100)
    renkler = sayfa.evaluate(
        """() => ({
            dugme: getComputedStyle(document.querySelector('.ara-form button')).backgroundColor,
            kutu: getComputedStyle(document.getElementById('ara-kutu')).backgroundColor
        })"""
    )
    # Beyaz (rgb(255,255,255)) arka plan OLMAZ.
    for ad, renk in renkler.items():
        assert renk not in ("rgb(255, 255, 255)", "rgba(255, 255, 255, 1)"), (ad, renk)
    sayfa.close()


# ---------------------------------------------------------------------------
# Güvenlik ve salt-okunurluk
# ---------------------------------------------------------------------------


def test_ara_yolunda_konsol_hatasi_yok(tarayici, arama_web) -> None:
    for yol in ("/ara", "/ara?q=parola", "/ara?q=bulunamayacakkelime"):
        sayfa, konsol, hatalar = sayfa_ac(tarayici, arama_web, yol)
        sayfa.wait_for_timeout(250)
        assert konsol == [], (yol, konsol)
        assert hatalar == [], (yol, hatalar)
        sayfa.close()


def test_e2e_arama_vaultu_degistirmez(tmp_path: Path, tarayici) -> None:
    """Web araması vault hash'ini DEĞİŞTİRMEZ."""
    vault = e2e_vault(tmp_path)
    db = tmp_path / "hash.db"
    indeksle(vault, db)
    once = vault_hashleri(vault)
    sunucu = WebSunucu(db)
    sunucu.baslat()
    try:
        sayfa, _, _ = sayfa_ac(tarayici, sunucu, "/ara?q=parola")
        sayfa.wait_for_selector(".ara-sonuc", timeout=10000)
        sayfa.close()
    finally:
        sunucu.kapat()
    assert vault_hashleri(vault) == once


def test_e2e_arama_db_yi_degistirmez(tmp_path: Path, tarayici) -> None:
    """Arama sonrası indeks DB'si hash'i DEĞİŞMEZ (salt okunur)."""
    import hashlib

    db = tmp_path / "hash2.db"
    indeksle(e2e_vault(tmp_path), db)
    once = hashlib.sha256(db.read_bytes()).hexdigest()
    sunucu = WebSunucu(db)
    sunucu.baslat()
    try:
        for sorgu in ("/ara?q=parola", "/api/ara?q=önbellek"):
            sayfa, _, _ = sayfa_ac(tarayici, sunucu, sorgu)
            sayfa.wait_for_timeout(200)
            sayfa.close()
    finally:
        sunucu.kapat()
    assert hashlib.sha256(db.read_bytes()).hexdigest() == once
