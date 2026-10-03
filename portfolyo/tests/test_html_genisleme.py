"""html: gerçek veri türleri (RepoVerisi), sıralama ve kaldırılan alanlar.

`test_html.py` yapıyı (raf/şerit/hero) kapsar; burada gerçek `RepoVerisi`
türleri ve veri kaybı davranışı ölçülür.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from portfolyo.denetim import tara
from portfolyo.git import RepoVerisi
from portfolyo.html import render
from test_html import BUGUN, _sahte_ayar


def _veri(**kw) -> RepoVerisi:
    d = dict(commit_sayisi=5, ilk_commit=None, son_commit="2026-09-01",
             haftalik=(0,) * 12, diller=(), readme_ozeti=None)
    return RepoVerisi(**{**d, **kw})


# --- gerçek RepoVerisi türleri ---------------------------------------------------------------

def test_iso_metin_tarihlerle_siralama():
    repolar = [{"ad": "a-eski"}, {"ad": "b-yeni"}]
    veriler = {"a-eski": _veri(son_commit="2023-05-01"), "b-yeni": _veri(son_commit="2026-05-01")}
    cikti = render(_sahte_ayar(repolar=repolar, siralama="aktivite"), veriler, BUGUN)
    assert cikti.index("b-yeni") < cikti.index("a-eski")


def test_veri_none_son_commite_gore_ente_sirada():
    repolar = [{"ad": "eski-repo"}, {"ad": "yeni-repo"}, {"ad": "yok-repo"}]
    veriler = {"eski-repo": _veri(son_commit="2024-01-01"),
               "yeni-repo": _veri(son_commit="2024-12-01"), "yok-repo": None}
    cikti = render(_sahte_ayar(repolar=repolar, siralama="aktivite"), veriler, BUGUN)
    assert cikti.index("yeni-repo") < cikti.index("eski-repo") < cikti.index("yok-repo")


def test_son_commit_date_nesnesi_iso_yazilir():
    cikti = render(_sahte_ayar(repolar=[{"ad": "r"}]),
                   {"r": _veri(son_commit=date(2026, 9, 28))}, BUGUN)
    assert "2026-09-28" in cikti


def test_haftalik_dolu_degerler_olcere_girilir():
    cikti = render(_sahte_ayar(repolar=[{"ad": "r", "one_cikan": True}]),
                   {"r": _veri(haftalik=(0, 0, 9, 0, 0, 0, 9, 2, 0, 3, 2, 3))}, BUGUN)
    assert 'aria-label="Son 12 haftada commit sayısı: 0, 0, 9, 0, 0, 0, 9, 2, 0, 3, 2, 3"' in cikti
    assert '<div class="olcer-rakam"><b>5</b>' in cikti
    assert tara(cikti) == []


def test_gun_sayisi_grafik_ekseni_ve_sayisi_birlikte():
    cikti = render(_sahte_ayar(repolar=[{"ad": "r", "one_cikan": True}]),
                   {"r": _veri(haftalik=(1,) * 12)}, BUGUN)
    assert '<div class="olcer-pencere">' in cikti
    assert '<span>12 hafta önce</span><span>bu hafta</span>' in cikti


# --- kaldırılan alanlar --------------------------------------------------------------------

def test_dil_ve_readme_ozeti_cikmaz():
    """Cihaz Rafı kartında dil/readme bloğu yok; yalnız ölçer ve sayı var."""
    cikti = render(_sahte_ayar(repolar=[{"ad": "r"}]),
                   {"r": _veri(diller=(("Python", 7),), readme_ozeti="Bu bir README.")}, BUGUN)
    assert "Python · 7" not in cikti and "Bu bir README." not in cikti
    assert "<svg" in cikti and "<b>5</b>" in cikti


# --- ek bağlantılar -------------------------------------------------------------------------

def test_baglanti_yoksa_baglar_kapsayicisi_yok():
    ayar = _sahte_ayar(repolar=[{"ad": "r", "one_cikan": True}])
    ayar.repolar[0].url = ""
    cikti = render(ayar, {}, BUGUN)
    assert '<div class="baglar">' not in cikti


def test_etiket_yoksa_yigin_kapsayicisi_yok():
    cikti = render(_sahte_ayar(repolar=[{"ad": "r", "etiketler": []}]), {}, BUGUN)
    assert '<ul class="yigin">' not in cikti