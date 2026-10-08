"""Ortak test fikstürleri: gecici veri dizini ve DosyaKaynak ornekleri."""

from __future__ import annotations

import json
from collections.abc import Callable

import pytest

from yol.kaynak import DosyaKaynak


@pytest.fixture(autouse=True)
def _ortam_temiz(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("YOL_KAYNAK", raising=False)


@pytest.fixture
def yol_dir(tmp_path, monkeypatch: pytest.MonkeyPatch):
    kok = tmp_path / "yol-veri"
    monkeypatch.setenv("YOL_DIR", str(kok))
    return kok


@pytest.fixture
def dosya_kaynak(tmp_path) -> DosyaKaynak:
    yol = tmp_path / "ortam.json"
    veri = {
        "ayirici": ";",
        "windows": True,
        "sistem": {
            "Path": {"metin": "C:\\Windows\\system32;%SystemRoot%", "genisler": True},
        },
        "kullanici": {
            "Path": {"metin": "C:\\Users\\umut\\bin;C:\\Tools", "genisler": True},
            "EDITOR": {"metin": "code", "genisler": False},
        },
    }
    yol.write_text(json.dumps(veri, ensure_ascii=False), encoding="utf-8")
    return DosyaKaynak(yol)


@pytest.fixture
def posix_kaynak(tmp_path) -> Callable[..., str]:
    """POSIX bicimli JSON kaynagi yazar; --kaynak icin 'dosya:<yol>' metni doner."""
    yol = tmp_path / "posix.json"

    def kur(sistem: str | None, kullanici: str | None, ek_kullanici: dict | None = None) -> str:
        veri: dict = {"ayirici": ":", "windows": False, "sistem": {}, "kullanici": {}}
        if sistem is not None:
            veri["sistem"]["PATH"] = {"metin": sistem, "genisler": False}
        if kullanici is not None:
            veri["kullanici"]["PATH"] = {"metin": kullanici, "genisler": False}
        for ad, metin in (ek_kullanici or {}).items():
            veri["kullanici"][ad] = {"metin": metin, "genisler": False}
        yol.write_text(json.dumps(veri, ensure_ascii=False), encoding="utf-8")
        return f"dosya:{yol}"

    return kur
