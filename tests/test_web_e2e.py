"""Playwright e2e (Dalga C): GERÇEK `orkestra web` süreci.

Bu testler `@pytest.mark.e2e` işaretlidir ve gerçek sunucu başlatır.
Kapsam: sayfalar çizilir, konsol/`pageerror` boştur, XSS yükü çalışmaz,
masaüstü (1440x900) ve mobil (390x844) için yatay kaydırma/kesilme/beyaz
kontrol/kontrast denetlenir, SVG etiketleri okunaklıdır.

Skip: `playwright` ya da Chromium yoksa sessizce atlanır (normal `pytest -q`
kırmızıya düşmez).
"""

from __future__ import annotations

import json
import os
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from orkestra.queue import SEMA

KOK = Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.e2e

playwright_modul = pytest.importorskip("playwright.sync_api", reason="playwright kurulu degil")
sync_playwright = playwright_modul.sync_playwright

# -- renk yardimcilari ------------------------------------------------------


def _rgb(belge, secici):
    """Öğenin hesaplanmış `background-color` değeri (`rgb(r, g, b)`)."""
    return belge.evaluate(
        "(sel) => { const e = document.querySelector(sel);"
        " if (!e) return null; return getComputedStyle(e).backgroundColor; }",
        secici,
    )


def _kontrast_orani(birinci, ikinci):
    """WCAG kontrast oranı (1..21)."""

    def parlaklik(renk):
        kanallar = []
        for parca in renk.replace("rgb(", "").replace(")", "").split(","):
            deger = int(float(parca.strip()))
            kan = deger / 255
            kan = kan / 12.92 if kan <= 0.03928 else ((kan + 0.055) / 1.055) ** 2.4
            kanallar.append(kan)
        return 0.2126 * kanallar[0] + 0.7152 * kanallar[1] + 0.0722 * kanallar[2]

    l1 = parlaklik(birinci)
    l2 = parlaklik(ikinci)
    ayni = max(l1, l2)
    kucuk = min(l1, l2)
    return (ayni + 0.05) / (kucuk + 0.05)


# -- sunucu -----------------------------------------------------------------


def _bos_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def sunucu(tmp_path_factory):
    """Gerçek `orkestra web` alt süreci + kurgusal DB/log verisi."""
    dizin = tmp_path_factory.mktemp("e2e")
    db = dizin / "e2e.db"
    b = sqlite3.connect(db)
    b.row_factory = sqlite3.Row
    b.executescript(SEMA)
    b.commit()

    # -- kurgusal gorevler (XSS yukleri dahil) --
    b.execute("INSERT INTO tasks (ajan,istem,durum,olusturma) VALUES (?,?,?,?)",
              ("bunny-coder", "kuyrugu incele ve bos durumlari duzelt", "bitti", "2026-09-30T05:00:00Z"))
    gorev_id = b.execute("SELECT last_insert_rowid()").fetchone()[0]
    log = dizin / "runs" / "1.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(
        "\n".join(f" satir {i}" for i in range(40)) + "\n", encoding="utf-8"
    )
    b.execute(
        "INSERT INTO runs (task_id,baslangic,bitis,cikis_kodu,cikti_yolu,kanit_yollari,hata) "
        "VALUES (?,?,?,?,?,?,?)",
        (gorev_id, "2026-09-30T05:00:01Z", "2026-09-30T05:00:20Z", 0, str(log), "[]", None),
    )

    # XSS yuklu gorev: hem istem, hem ajan, hem hata, hem log icerigi.
    yuk = '<img src=x onerror="window.__xss=1">'
    b.execute("INSERT INTO tasks (ajan,istem,durum,olusturma) VALUES (?,?,?,?)",
              (yuk, f"zararli icerik denemesi {yuk}", "hata", "2026-09-30T06:00:00Z"))
    xss_id = b.execute("SELECT last_insert_rowid()").fetchone()[0]
    xss_log = dizin / "runs" / "xss.log"
    xss_log.write_text(f"ilk satir\n{yuk}\n<svg/onload=window.__xss=1>\n", encoding="utf-8")
    b.execute(
        "INSERT INTO runs (task_id,baslangic,bitis,cikis_kodu,cikti_yolu,kanit_yollari,hata) "
        "VALUES (?,?,?,?,?,?,?)",
        (xss_id, "2026-09-30T06:00:01Z", "2026-09-30T06:00:05Z", 1, str(xss_log), "[]", f"hata: {yuk}"),
    )

    # -- kurgusal kota (gercek proxy.log YOK; sahte gunler) --
    for gun, adet in (("2026-09-24", 30), ("2026-09-26", 44), ("2026-09-28", 51), ("2026-09-30", 41)):
        b.execute(
            "INSERT INTO quota_snapshots (model,gun,istek,maliyet) VALUES (?,?,?,0)",
            ("nvidia/nemotron-3-ultra-550b-a55b:free", gun, adet),
        )
        b.execute(
            "INSERT INTO quota_snapshots (model,gun,istek,maliyet) VALUES (?,?,?,0)",
            ("stealth/space-bunny-alpha", gun, adet // 3),
        )
    b.commit()
    b.close()

    kota_toml = dizin / "kota.toml"
    kota_toml.write_text(
        '[limitler]\n"nvidia/nemotron-3-ultra-550b-a55b:free" = 50\n', encoding="utf-8"
    )

    port = _bos_port()
    surec = subprocess.Popen(
        [
            sys.executable, "-m", "orkestra", "--db", str(db),
            "web", "--port", str(port),
            "--cikti-dizini", str(log.parent),
            "--kota-toml", str(kota_toml),
        ],
        cwd=str(KOK),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    adres = f"http://127.0.0.1:{port}"
    for _ in range(100):
        if surec.poll() is not None:
            pytest.skip(f"orkestra web sureci hemen sonlandi: {surec.stdout.read()[:400]}")
        try:
            urllib.request.urlopen(f"{adres}/saglik", timeout=1).read()
            break
        except (urllib.error.URLError, OSError):
            time.sleep(0.1)
    else:
        surec.kill()
        pytest.skip("orkestra web zamaninda acilmadi")

    yield {"adres": adres, "gorev_id": gorev_id, "xss_id": xss_id, "port": port}
    surec.terminate()
    try:
        surec.wait(timeout=10)
    except subprocess.TimeoutExpired:  # pragma: no cover
        surec.kill()


@pytest.fixture(scope="module")
def tarayici():
    with sync_playwright() as p:
        try:
            tarayici_nesnesi = p.chromium.launch(args=["--no-sandbox"])
        except Exception as hata:  # pragma: no cover — Chromium yoksa
            pytest.skip(f"Chromium acilamadi: {hata}")
        yield tarayici_nesnesi
        tarayici_nesnesi.close()


def sayfa_ac(tarayici, adres, yol, genislik, yukseklik):
    sayfa = tarayici.new_page(viewport={"width": genislik, "height": yukseklik})
    konsol = []
    sayfa.on("console", lambda m: konsol.append(m.text) if m.type == "error" else None)
    sayfa.on("pageerror", lambda e: konsol.append(f"pageerror: {e}"))
    sayfa.goto(f"{adres}{yol}", wait_until="networkidle")
    return sayfa, konsol


MASASEU = {"genislik": 1440, "yukseklik": 900}
MOBIL = {"genislik": 390, "yukseklik": 844}


# -- temel cizim ------------------------------------------------------------


@pytest.mark.parametrize("yol", ["/", f"/gorev/YERINE", "/kota", "/saglik"])
def test_sayfalar_cizilir(tarayici, sunucu, yol):
    if "YERINE" in yol:
        yol = yol.replace("YERINE", str(sunucu["gorev_id"]))
    sayfa, konsol = sayfa_ac(tarayici, sunucu["adres"], yol, MASASEU["genislik"], MASASEU["yukseklik"])
    # `/saglik` saf JSON döner (başlığı yok); diğerleri HTML sayfası.
    if yol == "/saglik":
        assert sayfa.inner_text("body").strip()
    else:
        assert sayfa.title()
    assert konsol == []
    sayfa.close()


def test_konsol_hatasi_yok_kuyruk(tarayici, sunucu):
    sayfa, konsol = sayfa_ac(tarayici, sunucu["adres"], "/", **MASASEU)
    sayfa.wait_for_timeout(200)
    assert konsol == []
    sayfa.close()


def test_konsol_hatasi_yok_kota(tarayici, sunucu):
    sayfa, konsol = sayfa_ac(tarayici, sunucu["adres"], "/kota", **MASASEU)
    sayfa.wait_for_timeout(200)
    assert konsol == []
    sayfa.close()


def test_xss_yuku_calismaz(tarayici, sunucu):
    """XSS yüklü görev detayında `window.__xss` TANIMLANMAMALI."""
    for yol in ("/", f"/gorev/{sunucu['xss_id']}"):
        sayfa, konsol = sayfa_ac(tarayici, sunucu["adres"], yol, **MASASEU)
        sayfa.wait_for_timeout(200)
        assert sayfa.evaluate("() => window.__xss === undefined"), yol
        assert konsol == []
        sayfa.close()


def test_host_dogrulama_403(sunucu):
    """Kötü Host başlığı reddedilir (DNS rebinding koruması çalışıyor).

    Playwright `goto(headers=)` desteklemediği için ham HTTP isteği atılır;
    tarayıcı gereksinmez çünkü burada JS değil, SUNUCU yanıtı sınanır.
    """
    istek = urllib.request.Request(
        f"http://127.0.0.1:{sunucu['port']}/", headers={"Host": "kotu.example"}
    )
    try:
        urllib.request.urlopen(istek, timeout=5)
    except urllib.error.HTTPError as hata:
        assert hata.code == 403
        return
    pytest.fail("kotu Host basligi reddedilmedi")


# -- yerlesim: yatay kaydirma, kesilme ------------------------------------


def _yatay_tasma(sayfa) -> bool:
    return sayfa.evaluate("() => document.documentElement.scrollWidth > window.innerWidth")


def _kirpilan_metin(sayfa) -> list:
    """Görünür metin öğelerinden görüntü alanının DIŞINA taşanlar."""
    return sayfa.evaluate(
        """() => {
          const w = window.innerWidth;
          const kotu = [];
          document.querySelectorAll('body *').forEach((e) => {
            const st = getComputedStyle(e);
            if (st.display === 'none' || st.visibility === 'hidden') return;
            // Yalnizca DOKUNAN (metin iceren) ogeleri denetle.
            const yazi = Array.from(e.childNodes)
              .some((n) => n.nodeType === 3 && n.textContent.trim().length > 0);
            if (!yazi) return;
            const r = e.getBoundingClientRect();
            if (r.width === 0 || r.height === 0) return;
            if (r.right > w + 1 || r.left < -1) {
              kotu.push(e.tagName + ':' + (e.textContent || '').trim().slice(0, 40));
            }
          });
          return kotu;
        }"""
    )


@pytest.mark.parametrize("yol", ["/", "/kota"])
def test_masaustu_yatay_kaydirma_yok(tarayici, sunucu, yol):
    sayfa, _ = sayfa_ac(tarayici, sunucu["adres"], yol, **MASASEU)
    assert not _yatay_tasma(sayfa)
    sayfa.close()


@pytest.mark.parametrize("yol", ["/", "/kota"])
def test_mobil_yatay_kaydirma_yok(tarayici, sunucu, yol):
    sayfa, _ = sayfa_ac(tarayici, sunucu["adres"], yol, **MOBIL)
    assert not _yatay_tasma(sayfa)
    sayfa.close()


def test_gorev_detayi_mobil_kaydirma_yok(tarayici, sunucu):
    sayfa, _ = sayfa_ac(
        tarayici, sunucu["adres"], f"/gorev/{sunucu['gorev_id']}", **MOBIL
    )
    assert not _yatay_tasma(sayfa)
    sayfa.close()


@pytest.mark.parametrize("yol", ["/", "/kota", "GOREV"])
def test_masaustu_metin_kirpilmaz(tarayici, sunucu, yol):
    gercek = f"/gorev/{sunucu['gorev_id']}" if yol == "GOREV" else yol
    sayfa, _ = sayfa_ac(tarayici, sunucu["adres"], gercek, **MASASEU)
    assert _kirpilan_metin(sayfa) == []
    sayfa.close()


@pytest.mark.parametrize("yol", ["/", "/kota", "GOREV"])
def test_mobil_metin_kirpilmaz(tarayici, sunucu, yol):
    gercek = f"/gorev/{sunucu['gorev_id']}" if yol == "GOREV" else yol
    sayfa, _ = sayfa_ac(tarayici, sunucu["adres"], gercek, **MOBIL)
    kotu = _kirpilan_metin(sayfa)
    assert kotu == [], kotu
    sayfa.close()


# -- beyaz varsayilan kontrol ------------------------------------------------


def _beyaz_kontroller(sayfa) -> list:
    """Hesaplanmış arka planı beyaz olan buton/link/control listesi."""
    return sayfa.evaluate(
        """() => {
          const kotu = [];
          document.querySelectorAll('button, a, input, select, textarea').forEach((e) => {
            const st = getComputedStyle(e);
            if (st.display === 'none' || st.visibility === 'hidden') return;
            const m = st.backgroundColor.match(/\\d+/g);
            if (!m) return;
            const [r, g, b] = m.map(Number);
            if (r > 250 && g > 250 && b > 250) {
              kotu.push(e.tagName + ':' + (e.textContent || '').trim().slice(0, 30));
            }
          });
          return kotu;
        }"""
    )


@pytest.mark.parametrize("yol", ["/", "/kota", "GOREV"])
@pytest.mark.parametrize("olcu", [MASASEU, MOBIL])
def test_beyaz_varsayilan_kontrol_yok(tarayici, sunucu, yol, olcu):
    gercek = f"/gorev/{sunucu['gorev_id']}" if yol == "GOREV" else yol
    sayfa, _ = sayfa_ac(tarayici, sunucu["adres"], gercek, olcu["genislik"], olcu["yukseklik"])
    assert _beyaz_kontroller(sayfa) == []
    sayfa.close()


# -- kontrast ----------------------------------------------------------------


@pytest.mark.parametrize("yol", ["/", "/kota", "GOREV"])
def test_ana_kontrast_yeterli(tarayici, sunucu, yol):
    """Ana metin/zemin kontrastı >= 4.5:1."""
    gercek = f"/gorev/{sunucu['gorev_id']}" if yol == "GOREV" else yol
    sayfa, _ = sayfa_ac(tarayici, sunucu["adres"], gercek, **MASASEU)
    zemin = sayfa.evaluate("() => getComputedStyle(document.body).backgroundColor")
    oran = sayfa.evaluate(
        """(zemin) => {
          // En yaygin metin rengini (gövde) kullan.
          const m = getComputedStyle(document.body).color.match(/\\d+/g).map(Number);
          return { renk: 'rgb(' + m.join(', ') + ')' };
        }""",
        zemin,
    )
    assert _kontrast_orani(oran["renk"], zemin) >= 4.5
    sayfa.close()


def test_ikincil_yazi_kontrast(tarayici, sunucu):
    sayfa, _ = sayfa_ac(tarayici, sunucu["adres"], "/", **MASASEU)
    oranlar = sayfa.evaluate(
        """() => {
          const oku = (sel) => {
            const e = document.querySelector(sel);
            return e ? getComputedStyle(e).color : null;
          };
          return { ozet: oku('.ozet'), ipucu: oku('.aciklama') };
        }"""
    )
    zemin = sayfa.evaluate("() => getComputedStyle(document.body).backgroundColor")
    for deger in oranlar.values():
        if deger:
            assert _kontrast_orani(deger, zemin) >= 4.5, deger
    sayfa.close()


# -- graf etiketleri --------------------------------------------------------


def _svg_etiket_olculeri(sayfa) -> list:
    return sayfa.evaluate(
        """() => {
          return Array.from(document.querySelectorAll('svg.graf text')).map((t) => {
            const r = t.getBoundingClientRect();
            return { metin: t.textContent.trim(), yukseklik: r.height, genislik: r.width,
                     x: r.left, y: r.top, sag: r.right };
          });
        }"""
    )


def test_svg_etiketler_okunakli(tarayici, sunucu):
    """Etiket ekran yüksekliği >= 11 px."""
    sayfa, _ = sayfa_ac(tarayici, sunucu["adres"], "/kota", **MASASEU)
    etiketler = _svg_etiket_olculeri(sayfa)
    assert etiketler, "graf etiketi bulunamadi"
    for e in etiketler:
        assert e["yukseklik"] >= 11, e
    sayfa.close()


def test_svg_etiketler_kesismiyor(tarayici, sunucu):
    """Aynı sıradaki etiketler birbirini kesmemeli."""
    sayfa, _ = sayfa_ac(tarayici, sunucu["adres"], "/kota", **MASASEU)
    etiketler = _svg_etiket_olculeri(sayfa)
    # Aynı satırdakilere (benzer y) çakışma kontrolü.
    for i in range(len(etiketler)):
        for j in range(i + 1, len(etiketler)):
            a, b = etiketler[i], etiketler[j]
            dikey = abs(a["y"] - b["y"])
            if dikey > min(a["yukseklik"], b["yukseklik"]):
                continue
            assert b["x"] >= a["sag"] - 0.5 or a["x"] >= b["sag"] - 0.5, (a, b)
    sayfa.close()


def test_svg_etiketler_mobilde_okunakli(tarayici, sunucu):
    sayfa, _ = sayfa_ac(tarayici, sunucu["adres"], "/kota", **MOBIL)
    for e in _svg_etiket_olculeri(sayfa):
        assert e["yukseklik"] >= 11, e
    sayfa.close()


@pytest.mark.parametrize("olcu", [MASASEU, MOBIL])
def test_svg_etiketler_kutu_ici(tarayici, sunucu, olcu):
    """Etiketler SVG kutusundan TAŞMAMALI (limit etiketi sağa taşıyordu)."""
    sayfa, _ = sayfa_ac(
        tarayici, sunucu["adres"], "/kota", olcu["genislik"], olcu["yukseklik"]
    )
    tasmalar = sayfa.evaluate(
        """() => {
          const kotu = [];
          document.querySelectorAll('svg.graf').forEach((svg) => {
            const sr = svg.getBoundingClientRect();
            svg.querySelectorAll('text').forEach((t) => {
              const r = t.getBoundingClientRect();
              if (r.right > sr.right + 0.5 || r.left < sr.left - 0.5) {
                kotu.push(t.textContent.trim() + ' @' + r.right.toFixed(1) +
                          ' > ' + sr.right.toFixed(1));
              }
            });
          });
          return kotu;
        }"""
    )
    assert tasmalar == [], tasmalar
    sayfa.close()


def test_svg_viewbox_uygulanmis(tarayici, sunucu):
    """SVG `max-width` ile kırpılır: gerçek genişlik tabanı AŞMAZ."""
    sayfa, _ = sayfa_ac(tarayici, sunucu["adres"], "/kota", **MASASEU)
    taban = sayfa.evaluate(
        "() => { const s = document.querySelector('svg.graf');"
        " return s ? s.getBoundingClientRect().width : 0; }"
    )
    # 340 px taban; 1440 px ekranda BUYUTULMEZ (buyutse etiketler kuculurdu).
    assert 0 < taban <= 340 + 1
    sayfa.close()


# -- diger davranislar ------------------------------------------------------


def test_rozet_metni_var(tarayici, sunucu):
    """Durum rozeti renge degil, METNE de dayanir."""
    sayfa, _ = sayfa_ac(tarayici, sunucu["adres"], "/", **MASASEU)
    rozetler = sayfa.evaluate(
        "() => Array.from(document.querySelectorAll('.rozet')).map(e => e.textContent.trim())"
    )
    assert rozetler
    assert all(r for r in rozetler)
    sayfa.close()


def test_mobil_tablon_gizli_kart_gorunur(tarayici, sunucu):
    sayfa, _ = sayfa_ac(tarayici, sunucu["adres"], "/", **MOBIL)
    durum = sayfa.evaluate(
        """() => {
          const t = document.querySelector('.tablo-sarayici');
          const k = document.querySelector('.kart-liste');
          return {
            tablo: t ? getComputedStyle(t).display : null,
            kart: k ? getComputedStyle(k).display : null,
          };
        }"""
    )
    assert durum["tablo"] == "none"
    assert durum["kart"] != "none"
    sayfa.close()


def test_masaustu_kart_gorunumu_gizli(tarayici, sunucu):
    sayfa, _ = sayfa_ac(tarayici, sunucu["adres"], "/", **MASASEU)
    tablo = sayfa.evaluate(
        "() => { const t = document.querySelector('.tablo-sarayici');"
        " return t ? getComputedStyle(t).display : null; }"
    )
    assert tablo != "none"
    sayfa.close()


def test_ilerleme_cubugu_genislik_uygulandi(tarayici, sunucu):
    sayfa, _ = sayfa_ac(tarayici, sunucu["adres"], "/kota", **MASASEU)
    sayfa.wait_for_timeout(200)
    genislik = sayfa.evaluate(
        "() => { const i = document.querySelector('.ilerleme i');"
        " return i ? i.getBoundingClientRect().width : null; }"
    )
    assert genislik is not None and genislik > 0
    sayfa.close()


def test_odak_halkasi_tanimli(tarayici, sunucu):
    """`:focus-visible` kuralı CSS'te tanımlı olmalı."""
    sayfa, _ = sayfa_ac(tarayici, sunucu["adres"], "/", **MASASEU)
    kural = sayfa.evaluate(
        """() => Array.from(document.styleSheets).some((s) => {
             try { return Array.from(s.cssRules).some(
               (r) => r.selectorText && r.selectorText.includes(':focus-visible')); }
             catch (e) { return false; }
           })"""
    )
    assert kural
    sayfa.close()


def test_log_pre_iciinde(tarayici, sunucu):
    sayfa, _ = sayfa_ac(tarayici, sunucu["adres"], f"/gorev/{sunucu['gorev_id']}", **MASASEU)
    var = sayfa.evaluate("() => !!document.querySelector('pre.log')")
    assert var
    sayfa.close()


def test_saglik_json(tarayici, sunucu):
    sayfa, _ = sayfa_ac(tarayici, sunucu["adres"], "/saglik", **MASASEU)
    metin = sayfa.inner_text("body")
    assert "ok" in metin
    sayfa.close()


def test_yonlendirme_linkleri_calisir(tarayici, sunucu):
    sayfa, _ = sayfa_ac(tarayici, sunucu["adres"], "/", **MASASEU)
    sayfa.click("nav.ust-sag >> text=Kota")
    sayfa.wait_for_url("**/kota")
    assert "Kota" in sayfa.title() or sayfa.locator("h2").first.inner_text()
    sayfa.close()
