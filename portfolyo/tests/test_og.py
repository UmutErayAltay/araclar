"""og: kart HTML'i, tarayıcı çağrısı, CLI entegrasyonu ve gerçek PNG (tarayıcı varsa)."""

from __future__ import annotations

import glob
import re
import struct
import subprocess
from pathlib import Path

import pytest

from portfolyo import cli, og
from portfolyo.denetim import tara
from test_cli import REPO, _ayar

GECERLI = """---
baslik: Sabit tarihli testler
tarih: 2026-10-01
ozet: Özet.
etiketler: [python]
herkese_acik: true
---
Merhaba.
"""


def _gercek_tarayici() -> str | None:
    bulunan = og.tarayici_bul()
    if bulunan:
        return bulunan
    adaylar = sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))
    return adaylar[-1] if adaylar else None


GERCEK = _gercek_tarayici()


# --- kart_html --------------------------------------------------------------------------

def test_kart_html_kacislar_ve_boyut():
    h = og.kart_html('<script>x</script>"', "<b>alt</b>", "<")
    assert "<script>" not in h and "<b>" not in h
    assert "&lt;script&gt;" in h and "1200px" in h and "630px" in h
    assert tara(h) == [] or all(b.tur != "dis-kaynak" for b in tara(h))


def test_kart_html_monogram_varsayilan_ve_punto():
    assert '<div class="harf">U</div>' in og.kart_html("umut")
    assert "font-size: 84px" in og.kart_html("Kısa")
    assert "font-size: 48px" in og.kart_html("x" * 80)


def test_kart_html_cihaz_rafi_renkleri():
    """Cihaz Rafı paleti: koyu panel, kehribar monogram kutusu. Yazı tipi sistem yığını."""
    h = og.kart_html("Başlık", "Alt başlık", "U")
    assert "background: #1b1c1e" in h and "color: #ece9e0" in h
    assert "background: #e8a317; color: #1b1c1e" in h   # monogram kutusu
    assert "color: #b4b0a4" in h                          # ikincil metin
    assert "@font-face" not in h and "url(" not in h     # headless Chrome'da font dosyası yok
    assert "system-ui" in h


# --- tarayici_bul / png_uret (sahte süreç) ----------------------------------------------

def test_tarayici_yoksa_none_ve_png_uretilmez(monkeypatch, tmp_path):
    monkeypatch.setattr(og.shutil, "which", lambda ad: None)
    monkeypatch.delenv("PORTFOLYO_TARAYICI", raising=False)
    assert og.tarayici_bul() is None
    assert og.png_uret("<html></html>", tmp_path / "a.png") is False
    assert not (tmp_path / "a.png").exists()


def test_tarayici_env_ve_aday_sirasi(monkeypatch):
    monkeypatch.setattr(og.shutil, "which", lambda ad: f"/bin/{ad}" if ad in ("chromium", "x-ozel") else None)
    monkeypatch.delenv("PORTFOLYO_TARAYICI", raising=False)
    assert og.tarayici_bul() == "/bin/chromium"
    monkeypatch.setenv("PORTFOLYO_TARAYICI", "x-ozel")
    assert og.tarayici_bul() == "/bin/x-ozel"
    assert og.tarayici_bul("yok-boyle") is None  # açık verilen bulunamazsa başkasına düşmez


def test_png_uret_komut_satiri_ve_kopyalama(monkeypatch, tmp_path):
    cagrilar = []

    def sahte(komut, **kw):
        cagrilar.append((komut, kw))
        ekran = next(a for a in komut if a.startswith("--screenshot=")).split("=", 1)[1]
        Path(ekran).write_bytes(b"\x89PNG-sahte")
        return subprocess.CompletedProcess(komut, 0, b"", b"")

    monkeypatch.setattr(og.shutil, "which", lambda ad: "/usr/bin/chrome")
    monkeypatch.setattr(og.subprocess, "run", sahte)
    hedef = tmp_path / "alt" / "k.png"
    assert og.png_uret("<html>kart</html>", hedef, "chrome") is True
    assert hedef.read_bytes() == b"\x89PNG-sahte"
    komut, kw = cagrilar[0]
    assert komut[0] == "/usr/bin/chrome" and "--headless=new" in komut and "--no-sandbox" in komut
    assert "--window-size=1200,630" in komut
    assert kw["timeout"] == 30 and kw.get("shell") is None
    assert komut[-1].startswith("file://")


@pytest.mark.parametrize("hata", [subprocess.TimeoutExpired("c", 30), FileNotFoundError(), OSError("x")])
def test_png_uret_hatalari_false(monkeypatch, tmp_path, hata):
    monkeypatch.setattr(og.shutil, "which", lambda ad: "/usr/bin/chrome")

    def patla(*a, **k):
        raise hata

    monkeypatch.setattr(og.subprocess, "run", patla)
    assert og.png_uret("<html></html>", tmp_path / "a.png") is False


def test_png_uret_sifir_kod_degil_ya_da_bos_cikti_false(monkeypatch, tmp_path):
    monkeypatch.setattr(og.shutil, "which", lambda ad: "/usr/bin/chrome")
    monkeypatch.setattr(og.subprocess, "run", lambda k, **kw: subprocess.CompletedProcess(k, 1, b"", b"hata"))
    assert og.png_uret("<html></html>", tmp_path / "a.png") is False
    monkeypatch.setattr(og.subprocess, "run", lambda k, **kw: subprocess.CompletedProcess(k, 0, b"", b""))  # dosya yazılmadı
    assert og.png_uret("<html></html>", tmp_path / "a.png") is False


# --- CLI (sahte png_uret) ---------------------------------------------------------------

def _cli(tmp_path, *ek, site_url="https://testuser.github.io", yazilar=True):
    ayar = _ayar(tmp_path, [REPO], **({"site_url": site_url} if site_url else {}))
    yz = tmp_path / "yazilar"
    if yazilar:
        yz.mkdir(exist_ok=True)
        (yz / "sabit.md").write_text(GECERLI, encoding="utf-8")
    cikti = tmp_path / "site"
    kod = cli.main(["uret", str(ayar), "--cikti", str(cikti), "--bugun", "2026-10-01",
                    *(["--yazilar", str(yz)] if yazilar else []), *ek])
    return kod, cikti


def _sahte_basarili(monkeypatch):
    monkeypatch.setattr(og, "tarayici_bul", lambda t=None: "/usr/bin/chrome")
    monkeypatch.setattr(og, "png_uret", lambda kart, hedef, tarayici=None: (hedef.write_bytes(b"PNG") or True))


def test_og_gorsel_meta_ve_dosyalar(monkeypatch, tmp_path):
    _sahte_basarili(monkeypatch)
    kod, cikti = _cli(tmp_path, "--og-gorsel")
    assert kod == 0
    assert sorted(p.name for p in (cikti / "og").iterdir()) == ["sabit.png", "site.png"]
    ana = (cikti / "index.html").read_text(encoding="utf-8")
    yazi = (cikti / "yazilar" / "sabit.html").read_text(encoding="utf-8")
    assert '<meta property="og:image" content="https://testuser.github.io/og/site.png">' in ana
    assert '<meta property="og:image" content="https://testuser.github.io/og/sabit.png">' in yazi
    assert 'content="summary_large_image"' in ana and 'og:image:width" content="1200"' in ana
    assert tara(ana) == [] and tara(yazi) == []


def test_bayrak_yoksa_gorsel_yok(monkeypatch, tmp_path):
    _sahte_basarili(monkeypatch)
    kod, cikti = _cli(tmp_path)
    assert kod == 0 and not (cikti / "og").exists()
    assert "og:image" not in (cikti / "index.html").read_text(encoding="utf-8")


def test_site_url_yoksa_uyarir_gorsel_yok(monkeypatch, tmp_path, capsys):
    _sahte_basarili(monkeypatch)
    kod, cikti = _cli(tmp_path, "--og-gorsel", site_url=None)
    assert kod == 0 and not (cikti / "og").exists()
    assert "site_url" in capsys.readouterr().err
    assert "og:image" not in (cikti / "index.html").read_text(encoding="utf-8")


def test_tarayici_yoksa_uyarir_sayfa_yine_yazilir(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(og, "tarayici_bul", lambda t=None: None)
    kod, cikti = _cli(tmp_path, "--og-gorsel")
    assert kod == 0 and (cikti / "index.html").is_file() and not (cikti / "og").exists()
    assert "Chrome/Chromium bulunamadı" in capsys.readouterr().err
    assert "og:image" not in (cikti / "index.html").read_text(encoding="utf-8")


def test_kismi_basari_yalniz_uretilene_meta(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(og, "tarayici_bul", lambda t=None: "/usr/bin/chrome")
    monkeypatch.setattr(
        og, "png_uret",
        lambda kart, hedef, tarayici=None: hedef.name == "site.png" and (hedef.write_bytes(b"PNG") or True),
    )
    kod, cikti = _cli(tmp_path, "--og-gorsel")
    assert kod == 0
    assert "og/site.png" in (cikti / "index.html").read_text(encoding="utf-8")
    assert "og:image" not in (cikti / "yazilar" / "sabit.html").read_text(encoding="utf-8")
    assert "sabit.png üretilemedi" in capsys.readouterr().err


def test_denetim_bulgusunda_png_uretilmez_hicbir_sey_yazilmaz(monkeypatch, tmp_path):
    cagrilar = []
    monkeypatch.setattr(og, "tarayici_bul", lambda t=None: "/usr/bin/chrome")
    monkeypatch.setattr(og, "png_uret", lambda *a, **k: cagrilar.append(a) or True)
    ayar = _ayar(tmp_path, [REPO], site_url="https://testuser.github.io", hakkinda="Yol /home/umut/gizli")
    cikti = tmp_path / "site"
    assert cli.main(["uret", str(ayar), "--cikti", str(cikti), "--og-gorsel"]) == 4
    assert cagrilar == [] and not cikti.exists()


def test_kuru_calismada_png_uretilmez(monkeypatch, tmp_path):
    cagrilar = []
    monkeypatch.setattr(og, "tarayici_bul", lambda t=None: "/usr/bin/chrome")
    monkeypatch.setattr(og, "png_uret", lambda *a, **k: cagrilar.append(a) or True)
    kod, cikti = _cli(tmp_path, "--og-gorsel", "--kuru")
    assert kod == 0 and cagrilar == [] and not cikti.exists()


# --- gerçek tarayıcı --------------------------------------------------------------------

@pytest.mark.skipif(GERCEK is None, reason="Chrome/Chromium yok")
def test_gercek_png_1200x630(tmp_path):
    hedef = tmp_path / "k.png"
    assert og.png_uret(og.kart_html("Ğüşiöç Türkçe başlık", "Alt başlık", "Ğ"), hedef, GERCEK) is True
    veri = hedef.read_bytes()
    assert veri[:8] == b"\x89PNG\r\n\x1a\n"
    assert struct.unpack(">II", veri[16:24]) == (1200, 630)


@pytest.mark.skipif(GERCEK is None, reason="Chrome/Chromium yok")
def test_gercek_cli_uctan_uca(monkeypatch, tmp_path):
    monkeypatch.setenv("PORTFOLYO_TARAYICI", GERCEK)
    kod, cikti = _cli(tmp_path, "--og-gorsel")
    assert kod == 0
    for ad in ("site.png", "sabit.png"):
        assert struct.unpack(">II", (cikti / "og" / ad).read_bytes()[16:24]) == (1200, 630)
