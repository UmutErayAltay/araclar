"""olc: karakter/4 token tahmini ve katmanli sayimlar.

Gercek tokenizer CAGRILMAZ; butun sayilar `len(metin)/4` yukari yuvarlanmistir.
"""

from __future__ import annotations

import math

import pytest

from baglam_rontgeni import olc


@pytest.mark.parametrize("uzunluk", [0, 1, 3, 4, 5, 7, 8, 100, 401, 4001])
def test_tahmin_ceiling_dorde_bolme(uzunluk):
    """tahmin = ceil(len/4): 4'un katinda bolme, artiginda YUKARI yuvarlama."""
    assert olc.tahmin("x" * uzunluk) == math.ceil(uzunluk / 4)


def test_tahmin_karisik_metin_uzunlugunu_kullanir():
    """Tahmin metnin KARAKTER sayisindan cikar; kod noktasi/harf ayrimi yok."""
    assert olc.tahmin("şğıİ") == math.ceil(4 / 4) == 1


def test_tahmin_bos_metin_sifir():
    """Bos metin 0 token (sifira bolme/ceil patlamasi yok)."""
    assert olc.tahmin("") == 0


def test_skill_acilis_ad_ve_aciklamayi_toplar():
    """Acilis maliyeti = ad + aciklama birlikte (ikisi de her acilista yuklenir)."""
    assert olc.skill_acilis("harita", "aciklama") == olc.tahmin("harita\naciklama")


def test_skill_govdesi_yalniz_govdeyi_olcer():
    """Cagrilinca maliyeti YALNIZ govdedir; ad/aciklama karismaz."""
    assert olc.skill_govde("x" * 40) == 10
    assert olc.skill_govde("") == 0


def test_claude_md_tamamini_olcer():
    """CLAUDE.md tamamen acilista yuklenir: maliyet dosyanin tamami."""
    assert olc.claude_md("y" * 800) == 200


def test_skill_acilis_aciklama_yoksa_sadece_ad():
    """Aciklama alani yoksa acilis maliyeti yalniz ad (yine sifir degil)."""
    assert olc.skill_acilis("harita", "") == olc.tahmin("harita\n")
