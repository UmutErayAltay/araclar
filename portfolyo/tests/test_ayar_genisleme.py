"""ayar: kategoriler, siralama, kategori, veri, sahip.site_url."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from portfolyo.ayar import AyarHatasi, ayar_oku

SAHIP = {"ad": "Test", "unvan": "Dev", "github": "testuser", "hakkinda": "Merhaba."}
REPO = {"ad": "demo", "herkese_acik": True}


def _oku(tmp_path: Path, **ek) -> object:
    veri = {"sahip": SAHIP, "repolar": [REPO], **ek}
    yol = tmp_path / "p.json"
    yol.write_text(json.dumps(veri, ensure_ascii=False), encoding="utf-8")
    return ayar_oku(yol)


def test_varsayilanlar_geriye_uyumlu(tmp_path):
    a = _oku(tmp_path)
    assert a.kategoriler == () and a.siralama == "manuel"
    assert a.repolar[0].kategori == "Diğer" and a.repolar[0].veri == "yok"
    assert a.sahip.site_url == ""


def test_kategoriler_ve_repo_kategorisi(tmp_path):
    a = _oku(tmp_path, kategoriler=["Web", "Veri"], repolar=[{**REPO, "kategori": "Veri"}])
    assert a.kategoriler == ("Web", "Veri")
    assert a.repolar[0].kategori == "Veri"


def test_repo_kategorisi_listede_olmali(tmp_path):
    with pytest.raises(AyarHatasi, match="kategoriler"):
        _oku(tmp_path, kategoriler=["Web"], repolar=[{**REPO, "kategori": "Yok"}])
    with pytest.raises(AyarHatasi, match="kategoriler"):  # liste hiç yokken de
        _oku(tmp_path, repolar=[{**REPO, "kategori": "Web"}])


@pytest.mark.parametrize(
    "kategoriler",
    ["Web", [1], [""], ["  "], ["a", "a"], ["x" * 41], ["a\x00b"], [f"k{i}" for i in range(9)]],
)
def test_kategoriler_gecersiz(tmp_path, kategoriler):
    with pytest.raises(AyarHatasi):
        _oku(tmp_path, kategoriler=kategoriler)


def test_siralama(tmp_path):
    assert _oku(tmp_path, siralama="aktivite").siralama == "aktivite"
    for kotu in ("rastgele", 3, None):
        with pytest.raises(AyarHatasi, match="siralama"):
            _oku(tmp_path, siralama=kotu)


def test_veri_kaynagi(tmp_path):
    assert _oku(tmp_path, repolar=[{**REPO, "klon": "/x"}]).repolar[0].veri == "klon"
    assert _oku(tmp_path, repolar=[{**REPO, "veri": "api"}]).repolar[0].veri == "api"
    with pytest.raises(AyarHatasi, match="veri"):
        _oku(tmp_path, repolar=[{**REPO, "veri": "ftp"}])
    with pytest.raises(AyarHatasi, match="klon"):
        _oku(tmp_path, repolar=[{**REPO, "veri": "klon"}])


@pytest.mark.parametrize(
    "url",
    ["http://x.github.io", "javascript:alert(1)", "https://", "https://a b.io",
     "https://x.io/\"onload=", "https://x.io?q=1", "https://x.io/<b>", 5],
)
def test_site_url_gecersiz(tmp_path, url):
    with pytest.raises(AyarHatasi, match="site_url"):
        _oku(tmp_path, sahip={**SAHIP, "site_url": url})


def test_site_url_gecerli(tmp_path):
    a = _oku(tmp_path, sahip={**SAHIP, "site_url": "https://testuser.github.io"})
    assert a.sahip.site_url == "https://testuser.github.io"


def test_bilinmeyen_anahtar_hala_reddedilir(tmp_path):
    with pytest.raises(AyarHatasi):
        _oku(tmp_path, ekstra=1)
    with pytest.raises(AyarHatasi):
        _oku(tmp_path, repolar=[{**REPO, "ekstra": 1}])


# --- baglantilar -------------------------------------------------------------------------

def test_baglantilar_varsayilan_bos_ve_gecerli(tmp_path):
    assert _oku(tmp_path).repolar[0].baglantilar == ()
    b = [{"ad": "Demo", "url": "https://demo.example/a?b=1"}, {"ad": "Doküman", "url": "https://d.example"}]
    assert _oku(tmp_path, repolar=[{**REPO, "baglantilar": b}]).repolar[0].baglantilar == (
        ("Demo", "https://demo.example/a?b=1"), ("Doküman", "https://d.example"))


@pytest.mark.parametrize(
    "baglantilar",
    [
        "x", {"ad": "a", "url": "https://x.io"},
        [{"ad": "a", "url": "https://x.io"}] * 4,                       # en fazla 3
        [{"ad": "", "url": "https://x.io"}], [{"ad": "x" * 21, "url": "https://x.io"}],
        [{"ad": "a\x00", "url": "https://x.io"}], [{"url": "https://x.io"}], [{"ad": "a"}],
        [{"ad": "a", "url": "http://x.io"}], [{"ad": "a", "url": "javascript:alert(1)"}],
        [{"ad": "a", "url": "//x.io"}], [{"ad": "a", "url": "https://x.io/\"onload=1"}],
        [{"ad": "a", "url": "https://x.io/" + "a" * 300}], [{"ad": "a", "url": "https://u@x.io"}],
        [{"ad": "a", "url": 5}], [{"ad": 5, "url": "https://x.io"}], [{"ad": "a", "url": "https://x.io", "ek": 1}],
        ["metin"],
    ],
)
def test_baglantilar_gecersiz(tmp_path, baglantilar):
    with pytest.raises(AyarHatasi, match="baglantilar"):
        _oku(tmp_path, repolar=[{**REPO, "baglantilar": baglantilar}])
