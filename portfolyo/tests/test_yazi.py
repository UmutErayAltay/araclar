"""yazi: frontmatter, markdown alt kümesi, XSS, taslak kuralı, CLI entegrasyonu."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest

from portfolyo import cli
from portfolyo.denetim import tara
from portfolyo.yazi import YaziHatasi, frontmatter_ayir, markdown_html, yazi_oku, yazilari_oku
from test_cli import REPO, _ayar

GECERLI = """---
baslik: Sabit tarihli testler
tarih: 2026-10-01
ozet: Testler gün değişince kırılır.
etiketler: [python, test]
herkese_acik: true
---
## Giriş

Merhaba **dünya**, *vurgu* ve `kod`.
"""


def _yaz(klasor: Path, ad: str, icerik: str) -> Path:
    klasor.mkdir(exist_ok=True)
    yol = klasor / ad
    yol.write_text(icerik, encoding="utf-8")
    return yol


# --- frontmatter ----------------------------------------------------------------------

def test_gecerli_yazi(tmp_path):
    y = yazi_oku(_yaz(tmp_path, "sabit-tarih.md", GECERLI))
    assert (y.slug, y.baslik, y.tarih) == ("sabit-tarih", "Sabit tarihli testler", "2026-10-01")
    assert y.etiketler == ("python", "test")
    assert "<h2>Giriş</h2>" in y.govde_html and "<strong>dünya</strong>" in y.govde_html


def test_taslak_yayinlanmaz(tmp_path):
    for deger in ("false", "", "evet", "yes"):
        icerik = GECERLI.replace("herkese_acik: true", f"herkese_acik: {deger}")
        assert yazi_oku(_yaz(tmp_path, "t.md", icerik)) is None
    eksik = GECERLI.replace("herkese_acik: true\n", "")
    assert yazi_oku(_yaz(tmp_path, "t.md", eksik)) is None


def test_taslak_gecersiz_alanla_bile_yayinlanmaz_ama_bozuk_frontmatter_hata(tmp_path):
    taslak = "---\nbaslik: x\nherkese_acik: false\n---\ngovde"
    assert yazi_oku(_yaz(tmp_path, "t.md", taslak)) is None
    with pytest.raises(YaziHatasi):
        yazi_oku(_yaz(tmp_path, "b.md", "frontmattersiz"))


@pytest.mark.parametrize("ad", ["Buyuk.md", "bosluk var.md", "a_b.md", "ç.md", "x.markdown", ".md", "-a.md"])
def test_gecersiz_dosya_adi(tmp_path, ad):
    with pytest.raises(YaziHatasi, match="dosya adı"):
        yazi_oku(tmp_path / ad)


@pytest.mark.parametrize(
    "degistir,hata",
    [
        ("tarih: 2026-10-01 -> tarih: 2026-13-45", "tarih"),
        ("tarih: 2026-10-01 -> tarih: dün", "tarih"),
        ("baslik: Sabit tarihli testler -> baslik: ", "baslik"),
        (f"baslik: Sabit tarihli testler -> baslik: {'x' * 121}", "baslik"),
        (f"ozet: Testler gün değişince kırılır. -> ozet: {'x' * 201}", "ozet"),
        ("etiketler: [python, test] -> etiketler: [a, b, c, d, e, f]", "etiket"),
        ("etiketler: [python, test] -> etiketler: [" + "x" * 25 + "]", "etiket"),
        ("herkese_acik: true -> herkese_acik: true\nbilinmeyen: 1", "tanınmayan"),
        ("herkese_acik: true -> herkese_acik: true\nherkese_acik: true", "iki kez"),
        ("baslik: Sabit tarihli testler -> baslik: a\x00b", "kontrol"),
    ],
)
def test_yayina_acik_ama_bozuk_hatadir(tmp_path, degistir, hata):
    eski, yeni = degistir.split(" -> ")
    with pytest.raises(YaziHatasi, match=hata):
        yazi_oku(_yaz(tmp_path, "y.md", GECERLI.replace(eski, yeni)))


def test_frontmatter_kapanmazsa_hata():
    with pytest.raises(YaziHatasi):
        frontmatter_ayir("---\nbaslik: x\n")


def test_crlf_kabul_edilir(tmp_path):
    y = yazi_oku(_yaz(tmp_path, "c.md", GECERLI.replace("\n", "\r\n")))
    assert y.baslik == "Sabit tarihli testler"


def test_cok_buyuk_dosya_reddedilir(tmp_path):
    with pytest.raises(YaziHatasi, match="büyük"):
        yazi_oku(_yaz(tmp_path, "b.md", GECERLI + "x" * 200_001))


def test_yazilari_oku_siralar_ve_taslagi_ayirir(tmp_path):
    _yaz(tmp_path, "eski.md", GECERLI.replace("2026-10-01", "2026-01-01"))
    _yaz(tmp_path, "yeni.md", GECERLI)
    _yaz(tmp_path, "taslak.md", GECERLI.replace("herkese_acik: true", "herkese_acik: false"))
    yazilar, taslaklar = yazilari_oku(tmp_path)
    assert [y.slug for y in yazilar] == ["yeni", "eski"]
    assert taslaklar == ["taslak.md"]


def test_hata_dosya_adini_icerir(tmp_path):
    _yaz(tmp_path, "bozuk.md", GECERLI.replace("2026-10-01", "x"))
    with pytest.raises(YaziHatasi, match="bozuk.md"):
        yazilari_oku(tmp_path)


# --- markdown alt kümesi --------------------------------------------------------------

def test_basliklar_paragraf_ve_satir_birlestirme():
    h = markdown_html("## A\n### B\n\nilk satır\nikinci satır\n\nyeni")
    assert "<h2>A</h2>" in h and "<h3>B</h3>" in h
    assert "<p>ilk satır ikinci satır</p>" in h and "<p>yeni</p>" in h


def test_h1_desteklenmez_paragraf_olur():
    assert "<h1" not in markdown_html("# Baslik")


def test_listeler():
    assert markdown_html("- a\n- b") == "<ul><li>a</li><li>b</li></ul>"
    assert markdown_html("* a\n* b") == "<ul><li>a</li><li>b</li></ul>"
    assert markdown_html("1. bir\n2. iki") == "<ol><li>bir</li><li>iki</li></ol>"
    assert markdown_html("- a\n1. b") == "<ul><li>a</li></ul>\n<ol><li>b</li></ol>"


def test_alinti():
    assert markdown_html("> bir\n> iki") == "<blockquote><p>bir iki</p></blockquote>"


def test_kod_blogu_kacislanir_icinde_markdown_islenmez():
    h = markdown_html("```py\nx = '<b>' + **a**\n# not baslik\n```")
    assert h == "<pre><code>x = &#x27;&lt;b&gt;&#x27; + **a**\n# not baslik</code></pre>"


def test_kod_blogu_kapanmazsa_hata():
    with pytest.raises(YaziHatasi, match="kod bloğu"):
        markdown_html("```\nx")


def test_satir_ici_kod_icinde_isaretleme_yok():
    assert markdown_html("`**x** <b>`") == "<p><code>**x** &lt;b&gt;</code></p>"


def test_kalin_italik():
    assert markdown_html("**k** ve *i* ve **a *b* c**") == "<p><strong>k</strong> ve <em>i</em> ve <strong>a <em>b</em> c</strong></p>"
    assert markdown_html("2 * 3 * 4") == "<p>2 * 3 * 4</p>"  # boşluklu yıldız italik değil


def test_baglantilar():
    h = markdown_html("[g](https://example.com/a?b=1&c=2#x) [y](yazilar/x.html) [t](../index.html#bolum)")
    assert 'href="https://example.com/a?b=1&amp;c=2#x" rel="noopener noreferrer" target="_blank"' in h
    assert '<a href="yazilar/x.html">y</a>' in h and '<a href="../index.html#bolum">t</a>' in h


@pytest.mark.parametrize(
    "adres",
    ["javascript:alert(1)", "JaVaScRiPt:alert(1)", "data:text/html,x", "http://example.com", "//evil.example",
     "/mutlak", "https://a.com@evil.example", "ftp://x.io", "vbscript:x",
     "https://x.io/\"onmouseover=\"y", "https://x.io/*a*"],
)
def test_tehlikeli_baglantilar_reddedilir(adres):
    with pytest.raises(YaziHatasi, match="bağlantı"):
        markdown_html(f"[x]({adres})")


@pytest.mark.parametrize(
    "girdi",
    ["<script>alert(1)</script>", "<img src=x onerror=alert(1)>", "<iframe src=//e></iframe>",
     "<a href=\"javascript:x\">x</a>", "&lt;b&gt; <style>*{}</style>", "<link rel=stylesheet href=x>",
     "![img](https://x.io/a.png)", "<svg onload=alert(1)>"],
)
def test_ham_html_ve_gorsel_etkisiz(girdi):
    h = markdown_html(girdi)
    assert not re.search(r"<(script|img|iframe|style|link|svg)\b", h)
    assert "<a href=\"javascript" not in h
    assert tara(h) == []  # üretilen çıktı sızıntı denetiminden geçer


def test_baslikta_ve_listede_da_kacis():
    h = markdown_html("## <script>x</script>\n- <b>i</b>")
    assert "<script>" not in h and "&lt;script&gt;" in h and "&lt;b&gt;" in h


# --- CLI entegrasyonu -----------------------------------------------------------------

def _cli(tmp_path, yazilar_klasoru, *ek):
    ayar = _ayar(tmp_path, [REPO], site_url="https://testuser.github.io")
    cikti = tmp_path / "site"
    kod = cli.main(["uret", str(ayar), "--cikti", str(cikti), "--bugun", "2026-10-01",
                    "--yazilar", str(yazilar_klasoru), *ek])
    return kod, cikti


def test_cli_yazi_sayfalari_ve_ana_sayfa_bolumu(tmp_path):
    yz = tmp_path / "yazilar"
    _yaz(yz, "sabit.md", GECERLI)
    _yaz(yz, "taslak.md", GECERLI.replace("herkese_acik: true", "herkese_acik: false"))
    kod, cikti = _cli(tmp_path, yz)
    assert kod == 0
    assert sorted(p.name for p in (cikti / "yazilar").iterdir()) == ["sabit.html"]  # taslak yok
    ana = (cikti / "index.html").read_text(encoding="utf-8")
    assert 'href="yazilar/sabit.html"' in ana and "Yazılar" in ana and "taslak" not in ana
    sayfa = (cikti / "yazilar" / "sabit.html").read_text(encoding="utf-8")
    assert '<meta property="og:type" content="article">' in sayfa
    assert '<meta property="og:url" content="https://testuser.github.io/yazilar/sabit.html">' in sayfa
    assert 'href="../#icerik"' in sayfa and "<article" in sayfa
    assert "<h1>Sabit tarihli testler</h1>" in sayfa
    assert tara(sayfa) == [] and tara(ana) == []


def test_cli_denetim_bulgusu_hicbir_dosya_yazmaz(tmp_path, capsys):
    yz = tmp_path / "yazilar"
    _yaz(yz, "iyi.md", GECERLI)
    _yaz(yz, "kotu.md", GECERLI.replace("Merhaba", "Yol: /home/umut/gizli").replace("Sabit", "Kotu"))
    kod, cikti = _cli(tmp_path, yz)
    assert kod == 4
    assert not cikti.exists()  # ana sayfa ve iyi yazı DA yazılmadı
    err = capsys.readouterr().err
    assert "kotu.html" in err and "yerel-yol" in err and "umut/gizli" not in err


def test_cli_bozuk_yazi_2_ve_yazilar_yoksa_bolum_yok(tmp_path, capsys):
    yz = tmp_path / "yazilar"
    _yaz(yz, "b.md", GECERLI.replace("2026-10-01", "x"))
    kod, cikti = _cli(tmp_path, yz)
    assert kod == 2 and not cikti.exists()
    assert "b.md" in capsys.readouterr().err
    assert _cli(tmp_path, tmp_path / "yok-klasor")[0] == 2

    yz2 = tmp_path / "bos"
    yz2.mkdir()
    kod, cikti = _cli(tmp_path, yz2)
    assert kod == 0 and "Yazılar" not in (cikti / "index.html").read_text(encoding="utf-8")
    assert not (cikti / "yazilar").exists()


def test_cli_kuru_yazmaz(tmp_path):
    yz = tmp_path / "yazilar"
    _yaz(yz, "sabit.md", GECERLI)
    kod, cikti = _cli(tmp_path, yz, "--kuru")
    assert kod == 0 and not cikti.exists()
