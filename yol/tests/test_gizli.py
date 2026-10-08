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


@pytest.mark.parametrize("ad", ["DATABASE_URL", "DB_DSN", "SQL_CONNECTION", "SESSION_ID", "AUTH_COOKIE",
                                "APP_SIGNATURE", "BEARER_HEADER", "GITHUB_PAT", "OAUTH_SESSION"])
def test_yeni_gizli_desenler(ad: str):
    assert gizli_mi(ad)


def test_url_kimligi_degerden_gizli_sayilir():
    assert gizli_mi("CACHE_DIR", "https://umut:parola@sunucu/yol")
    assert not gizli_mi("CACHE_DIR", "https://sunucu/yol")
    assert not gizli_mi("CACHE_DIR", "C:\\Users\\umut")


def test_pwd_degerden_de_muaf():
    assert not gizli_mi("PWD", "https://umut:parola@sunucu")
    assert not gizli_mi("OLDPWD", "https://umut:parola@sunucu")


def test_maskele_bos_ve_uzunluk_sizdirmaz():
    assert maskele("") == ""
    assert maskele("x") == maskele("uzun-bir-deger-metni")
    assert "uzun" not in maskele("uzun-bir-deger-metni")
