"""CLI: loopback dışı `--base-url`, traceback DEĞİL `Hata:` mesajı ve çıkış kodu 1 verir; iş yarım kalmaz."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_anlat_uzak_base_url_hata_mesaji_ve_kod_1(sample_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from cli import main

    kod = main(["anlat", str(sample_repo), "--base-url", "http://ornek.com:8787"])

    err = capsys.readouterr().err
    assert kod == 1
    assert err.startswith("Hata:") and "loopback" in err
    assert "Traceback" not in err
    assert not (sample_repo / "ANLATI.md").exists()
