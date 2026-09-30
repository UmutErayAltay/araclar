"""`generator/_corclient.py` senkron bütünlüğü (elle düzenleme / bozulma kontrolü).

`_corclient.py`, `corclient` reposundan `tools/sync.py` ile yazılır ve ELLE
düzenlenmez. Başlıktaki sha256, dosya gövdesiyle tutmalıdır. Satır sonları
LF'ye indirilerek hesaplanır (Windows `autocrlf` kopyayı CRLF'ye çevirebilir).
Bu test corclient reposuna ERİŞMEZ; güncellik kontrolü `sync.py --check` ile yapılır.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

_KOPYA = Path(__file__).resolve().parent.parent / "generator" / "_corclient.py"
_BASLIK = re.compile(r"^# SENKRON corclient surum=(?P<surum>\S+) sha256=(?P<sha>[0-9a-f]{64})$")


def _oku() -> tuple[str, bytes]:
    ham = _KOPYA.read_bytes().replace(b"\r\n", b"\n")
    baslik, _, govde = ham.partition(b"\n")
    return baslik.decode("utf-8"), govde


def test_kopya_var_ve_baslikli() -> None:
    assert _KOPYA.is_file(), f"{_KOPYA} yok; `corclient/tools/sync.py` ile yazın"
    baslik, _ = _oku()
    assert _BASLIK.match(baslik), f"senkron başlığı yok/bozuk: {baslik!r}"


def test_govde_basliktaki_hash_ile_tutuyor() -> None:
    """Elle düzenleme → KIRMIZI. Düzeltme: `corclient/tools/sync.py` ile yeniden yaz."""
    baslik, govde = _oku()
    eslesme = _BASLIK.match(baslik)
    assert eslesme is not None
    assert hashlib.sha256(govde).hexdigest() == eslesme.group("sha"), (
        "_corclient.py elle düzenlenmiş; kaynak `corclient/corclient.py`'dir"
    )
