"""Olcüm: karakter/4 kaba token tahmini.

Dogruluk sarti: gercek tokenizer cagrilmaz (bagimlilik yok, modelden bagimsiz).
Her sayi TAHMINdir; raporda `tahmin_notu` ile belirtilir.
"""

from __future__ import annotations

import math


def tahmin(metin: str) -> int:
    """Metnin token tahmini: ceil(len / 4)."""
    return math.ceil(len(metin) / 4)


def skill_acilis(ad: str, aciklama: str) -> int:
    """Skill'in her oturum acilista yuklenen kismi: name + description metni."""
    return tahmin(f"{ad}\n{aciklama}")


def skill_govde(metin: str) -> int:
    """Skill'in YALNIZ cagrilinda yuklenen govde token tahmini."""
    return tahmin(metin)


def claude_md(metin: str) -> int:
    """CLAUDE.md tamamen acilista yuklenir: maliyet = dosyanin tamami."""
    return tahmin(metin)