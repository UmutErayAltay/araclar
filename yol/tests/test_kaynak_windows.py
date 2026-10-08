"""WindowsKaynak: gercek HKCU\\Environment uzerinde gecici degisken. PATH'e dokunmaz."""

from __future__ import annotations

import os
import uuid

import pytest

pytestmark = pytest.mark.skipif(os.name != "nt", reason="yalniz Windows (winreg gerekir)")


def test_hkcu_yaz_oku_sil_tip_korunur():
    from yol.kaynak import KULLANICI, Deger, WindowsKaynak

    kaynak = WindowsKaynak()
    ad = f"YOL_TEST_{uuid.uuid4().hex[:8]}"
    try:
        kaynak.yaz(KULLANICI, ad, Deger("duz-metin", False))
        assert kaynak.oku(KULLANICI)[ad] == Deger("duz-metin", False)

        kaynak.yaz(KULLANICI, ad, Deger("%USERPROFILE%\\x", True))
        okunan = kaynak.oku(KULLANICI)[ad]
        assert okunan == Deger("%USERPROFILE%\\x", True)
        assert okunan.genisler is True
    finally:
        kaynak.sil(KULLANICI, ad)
    assert ad not in kaynak.oku(KULLANICI)
