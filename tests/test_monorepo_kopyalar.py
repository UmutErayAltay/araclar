"""Monorepo bütünlüğü: bu repodaki TÜM `_corclient.py` kopyaları güncel kaynakla tutmalı.

Ayrı repolar döneminde tüketici testi yalnız "elle düzenlendi mi"yi görebiliyordu;
şimdi hepsi aynı repoda olduğu için "kaynağın eski sürümü mü" de test edilir.
Düzeltme: `python3 tools/sync.py --hepsi`.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
SYNC = KOK / "tools" / "sync.py"

BEKLENEN = {
    "atlas/atlas/_corclient.py",
    "harita/harita/_corclient.py",
    "orkestra/orkestra/_corclient.py",
    "danis/danis/_corclient.py",
    "anlat/generator/_corclient.py",
}


def _kopyalar() -> set[str]:
    return {str(y.relative_to(KOK)).replace("\\", "/") for y in KOK.glob("*/*/_corclient.py")}


def test_beklenen_kopyalar_var_ve_baskasi_yok() -> None:
    """Yeni bir kopya eklenirse bu liste bilerek güncellenmeli (denetimsiz kopya olmasın)."""
    assert _kopyalar() == BEKLENEN


def test_tum_kopyalar_guncel() -> None:
    sonuc = subprocess.run(
        [sys.executable, str(SYNC), "--check", "--hepsi"],
        capture_output=True, text=True, cwd=KOK,
    )
    assert sonuc.returncode == 0, sonuc.stderr
    assert sonuc.stdout.count("OK ") == len(BEKLENEN)


@pytest.mark.parametrize("yol", sorted(BEKLENEN))
def test_kopya_tek_tek_guncel(yol: str) -> None:
    sonuc = subprocess.run(
        [sys.executable, str(SYNC), "--check", str(KOK / yol)],
        capture_output=True, text=True, cwd=KOK,
    )
    assert sonuc.returncode == 0, sonuc.stderr


def test_hepsi_bayragi_hedefsiz_hata_vermez_ama_bos_yollar_hata_verir() -> None:
    """`--hepsi` yokken hedef de yoksa araç açık bir hata ile çıkar (sessizce hiçbir şey yapmaz)."""
    sonuc = subprocess.run(
        [sys.executable, str(SYNC), "--check"], capture_output=True, text=True, cwd=KOK,
    )
    assert sonuc.returncode == 2
    assert "hedef" in sonuc.stderr
