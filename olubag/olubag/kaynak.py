"""Kaynak tarama: hangi import adlari gercekten kullaniliyor?

- Python: `ast` ile (dosya CALISTIRILMAZ). Sozdizimi hatasi olan dosya ATLANIR.
- JS: `require('x')` / `from 'x'` / `import('x')` metin taramasi.

Ayrica `__import__` / `importlib.import_module` gibi DINAMIK kullanim varsa
o dosya "belirsiz" sayilir: adini calistirmadan cozulemez.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from .bildirim import JS_UZANTILARI
from .eslesme import MAKS_BOYUT, normalle

#: Dinamik import cagrilari: cozulebilir ad degil, `belirsiz` uretir.
DINAMIK = ("__import__", "import_module")

#: JS: require('x') / import('x') / import x from 'x' / export ... from 'x'
_JS_FROM = re.compile(r"""(?:^|[^.\w$])(?:import|export)\b[^;\n]*?\bfrom\s*['"]([^'"]+)['"]""")
_JS_CALL = re.compile(r"""(?:^|[^.\w$])(?:require|import)\s*\(\s*['"]([^'"]+)['"]""")


def okunabilir(yol: Path) -> bool:
    """Dosya metin olarak okunabilir mi (ikili/atlanmis/kotu kodlenmis degil mi)?"""
    try:
        if yol.is_symlink() or not yol.is_file():
            return False
        return yol.stat().st_size <= MAKS_BOYUT
    except OSError:
        return False


def _okunur_olarak(dosya: Path) -> str | None:
    """Metin olarak oku; okunamazsa None (bozuk kodlama ATLANIR)."""
    try:
        return dosya.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def python_importlari(dosya: Path) -> tuple[set[str], bool]:
    """(kullanilan import adlari, belirsiz mi).

    Adlar kucuk harfli verilir; `import a.b` icin ust paket `a` alinir.
    Sozdizimi hatasi: bos küme + belirsiz DEGIL (dosya atlanir, sanma).
    """
    kod = _okunur_olarak(dosya)
    if kod is None:
        return set(), False
    try:
        agac = ast.parse(kod)
    except (SyntaxError, ValueError):
        return set(), False
    adlar: set[str] = set()
    belirsiz = False
    for dugum in ast.walk(agac):
        if isinstance(dugum, ast.Import):
            for takma in dugum.names:
                adlar.add(takma.name.split(".")[0].lower())
        elif isinstance(dugum, ast.ImportFrom):
            if dugum.module:
                adlar.add(dugum.module.split(".")[0].lower())
            if dugum.level and dugum.module is None:
                # `from . import x`: gurel import, harici paket degil.
                continue
        elif isinstance(dugum, ast.Call):
            ad = getattr(dugum.func, "id", None) or getattr(dugum.func, "attr", None)
            if ad in DINAMIK:
                belirsiz = True
    return adlar, belirsiz


def js_importlari(dosya: Path) -> tuple[set[str], bool]:
    """(kullanilan modul adlari, belirsiz mi) — require/from/import('x') tarama."""
    kod = _okunur_olarak(dosya)
    if kod is None:
        return set(), False
    adlar = {m for m in _JS_FROM.findall(kod)} | {m for m in _JS_CALL.findall(kod)}
    # require.resolve('x') gibi dolayli kullanimlar cozulemez.
    belirsiz = any(a in kod for a in ("require.resolve(", "createRequire"))
    return adlar, belirsiz


def kaynak_dosyasi_mi(dosya: Path) -> bool:
    """Bu dosya kaynak kod mu (bagimlilik taramasi yapilacak mi)?"""
    return dosya.suffix == ".py" or dosya.suffix in JS_UZANTILARI


def js_modul_adi(ad: str) -> str:
    """JS modul adindan paket adi: 'lodash/fp' -> 'lodash', '@a/b/x' -> '@a/b'."""
    parcalar = ad.split("/")
    if ad.startswith("@"):
        return "/".join(parcalar[:2])
    return parcalar[0]


def normalle_js(ad: str) -> str:
    return normalle(js_modul_adi(ad))