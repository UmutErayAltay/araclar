"""gizli.py: gizli ad tespiti ve maskeleme."""

from __future__ import annotations

import pytest

from yol.gizli import gizli_mi, maskele


@pytest.mark.parametrize("ad", ["GITHUB_TOKEN", "db_password", "AWS_SECRET_ACCESS_KEY", "MY_PASS",
                                "APP_PWD_FILE", "CREDENTIAL_PATH", "PRIVATE_DIR", "api_key"])
def test_gizli_adlar(ad: str):
    assert gizli_mi(ad)


@pytest.mark.parametrize("ad", ["PATH", "HOME", "PWD", "OLDPWD", "pwd", "EDITOR", "TEMP"])
def test_gizli_olmayan_adlar(ad: str):
    assert not gizli_mi(ad)


def test_maskele_bos_ve_uzunluk_sizdirmaz():
    assert maskele("") == ""
    assert maskele("x") == maskele("uzun-bir-deger-metni")
    assert "uzun" not in maskele("uzun-bir-deger-metni")
