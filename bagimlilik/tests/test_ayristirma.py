"""Ayristirma: pip-audit ve npm audit JSON -> (sayilar, aciklar). Ag YOK, sadece fixture."""

from __future__ import annotations

import json

import pytest
from conftest import FIXTURES, fixture_yukle

from bagimlilik.denetim import parse_npm_audit, parse_pip_audit

# --------------------------------------------------------------------------
# pip-audit
# --------------------------------------------------------------------------


def test_pip_temiz_fixture_sifir_acik():
    """Temiz fixture'da HICBIR acik ve sayim yok; tum sayilar sifir."""
    sayilar, aciklar = parse_pip_audit(fixture_yukle("pip_audit_temiz"))
    assert aciklar == []
    assert sayilar == {"kritik": 0, "yuksek": 0, "orta": 0, "dusuk": 0, "bilinmiyor": 0}


def test_pip_acikli_fixture_tekillestirilir():
    """Ayni (paket, id) birden fazla kez gecse de acik BIR kez sayilir.

    Fixture'da flask/PYSEC-2019-179 ve requests/PYSEC-2018-28 iki kez,
    idna/PYSEC-2024-60 iki kez geciyor: ham sayim 12, tekillestirilmis 9.
    """
    sayilar, aciklar = parse_pip_audit(fixture_yukle("pip_audit_acikli"))
    kimlikler = [(a.paket, a.id) for a in aciklar]
    assert len(kimlikler) == len(set(kimlikler)), "tekillestirme calismiyor"
    assert sayilar["bilinmiyor"] == len(aciklar) == 9


def test_pip_cve_aliasi_tercih_edilir():
    """Kimlik PYSEC-... degil, aliases icindeki CVE-... olur (rapor CVE ile okunur)."""
    _, aciklar = parse_pip_audit(fixture_yukle("pip_audit_acikli"))
    assert all(a.id.startswith("CVE-") for a in aciklar)
    assert "CVE-2019-1010083" in {a.id for a in aciklar}


def test_pip_cve_aliasi_yoksa_kendi_id_si_kullanilir():
    """Aliases icinde CVE yoksa PYSEC/GHSA kimligi oldugu gibi kalir."""
    metin = json.dumps(
        {"dependencies": [{"name": "x", "version": "1", "vulns": [
            {"id": "PYSEC-2000-1", "fix_versions": [], "aliases": ["GHSA-aaaa-bbbb-cccc"]}]}]}
    )
    _, aciklar = parse_pip_audit(metin)
    assert [a.id for a in aciklar] == ["PYSEC-2000-1"]


def test_pip_siddet_hep_bilinmiyor():
    """pip-audit siddet VERMEZ: her acik 'bilinmiyor', kritik/yuksek/orta/dusuk 0 kalir."""
    sayilar, aciklar = parse_pip_audit(fixture_yukle("pip_audit_acikli"))
    assert sayilar["bilinmiyor"] == 9
    for anahtar in ("kritik", "yuksek", "orta", "dusuk"):
        assert sayilar[anahtar] == 0
    assert {a.siddet for a in aciklar} == {"bilinmiyor"}


def test_pip_duzeltme_surumleri_birlestirilir():
    """fix_versions listesi virgulle birlestirilir; bos liste None (duzeltme yok)."""
    metin = json.dumps(
        {"dependencies": [{"name": "x", "version": "1", "vulns": [
            {"id": "A", "fix_versions": ["1.2", "1.3", "2.0"], "aliases": ["CVE-1"]},
            {"id": "B", "fix_versions": [], "aliases": ["CVE-2"]}]}]}
    )
    _, aciklar = parse_pip_audit(metin)
    duzeltmeler = {a.id: a.duzeltme for a in aciklar}
    assert duzeltmeler == {"CVE-1": "1.2,1.3,2.0", "CVE-2": None}


def test_pip_bos_ve_null_vulns_listesi_cokmez():
    """vulns/dependencies anahtarlari yoksa ya da null ise sonuc bos, hata yok."""
    for metin in ("{}", json.dumps({"dependencies": None})):
        sayilar, aciklar = parse_pip_audit(metin)
        assert aciklar == [] and sayilar["bilinmiyor"] == 0


# --------------------------------------------------------------------------
# npm audit
# --------------------------------------------------------------------------


def test_npm_sayilar_metadata_dan_gelir():
    """Sayilar metadata.vulnerabilities'tan: 3 kritik, 35 yuksek, 17 orta, low+info dusuk."""
    sayilar, _ = parse_npm_audit(fixture_yukle("npm_audit_acikli"))
    assert sayilar == {"kritik": 3, "yuksek": 35, "orta": 17, "dusuk": 14, "bilinmiyor": 0}


def test_npm_low_ve_info_dusuk_toplanir():
    """npm'de 'info' ve 'low' ayri etiketler; raporda ikisi de 'dusuk' olur."""
    metin = json.dumps({"metadata": {"vulnerabilities": {"info": 2, "low": 3, "total": 5}}})
    sayilar, _ = parse_npm_audit(metin)
    assert sayilar["dusuk"] == 5


def test_npm_via_string_girdileri_atlanir():
    """via'daki string bir zincirdir (bildirim kaynagi degil), acik sayilmaz."""
    sayilar, aciklar = parse_npm_audit(fixture_yukle("npm_audit_acikli"))
    paketler = {a.paket for a in aciklar}
    assert "@jest/core" not in paketler, "sadece string via'li giris acik sayildi"
    assert len(aciklar) == 3
    assert sayilar["kritik"] == 3  # sayimlar metadata'dan, acik listesinden degil


def test_npm_kimlik_url_son_parcasidir():
    """Kimlik, advisory URL'inin son parcasidir: .../GHSA-xxxx -> GHSA-xxxx."""
    _, aciklar = parse_npm_audit(fixture_yukle("npm_audit_acikli"))
    assert [a.id for a in aciklar] == [
        "GHSA-4x5r-pxfx-6jf8", "GHSA-968p-4wvh-cqc8", "GHSA-fv7c-fp4j-7gwp",
    ]
    assert all("/" not in a.id for a in aciklar)


def test_npm_siddet_eslemesi():
    """critical->kritik, high->yuksek, moderate->orta, low->dusuk; bilinmeyen->bilinmiyor."""
    metin = json.dumps(
        {"vulnerabilities": {
            "a": {"via": [{"name": "a", "severity": "critical", "url": "https://x/GHSA-1"}]},
            "b": {"via": [{"name": "b", "severity": "high", "url": "https://x/GHSA-2"}]},
            "c": {"via": [{"name": "c", "severity": "moderate", "url": "https://x/GHSA-3"}]},
            "d": {"via": [{"name": "d", "severity": "low", "url": "https://x/GHSA-4"}]},
            "e": {"via": [{"name": "e", "severity": "info", "url": "https://x/GHSA-5"}]},
            "f": {"via": [{"name": "f", "severity": "cok-garip", "url": "https://x/GHSA-6"}]},
        }}
    )
    _, aciklar = parse_npm_audit(metin)
    assert {a.paket: a.siddet for a in aciklar} == {
        "a": "kritik", "b": "yuksek", "c": "orta", "d": "dusuk", "e": "dusuk", "f": "bilinmiyor",
    }


@pytest.mark.parametrize(
    "fix_available, beklenen",
    [
        ({"name": "lodash", "version": "4.17.21"}, "lodash@4.17.21"),
        (True, "mevcut"),
        (False, None),
    ],
    ids=["sozlu", "dogru-boolean", "yok"],
)
def test_npm_duzeltme_bicimleri(fix_available, beklenen):
    """fixAvailable: dict -> 'ad@surum', True -> 'mevcut', False -> None (duzeltme yok)."""
    metin = json.dumps(
        {"vulnerabilities": {
            "p": {"fixAvailable": fix_available,
                  "via": [{"name": "p", "severity": "high", "url": "https://x/GHSA-1"}]}}}
    )
    _, aciklar = parse_npm_audit(metin)
    assert aciklar[0].duzeltme == beklenen


def test_npm_temiz_ve_bos_ayristirma():
    """Acik yoksa tum sayilar sifir ve acik listesi bos (temiz senaryo)."""
    for metin in ("{}", json.dumps({"metadata": {"vulnerabilities": {"total": 0}}})):
        sayilar, aciklar = parse_npm_audit(metin)
        assert aciklar == [] and sum(sayilar.values()) == 0


# --------------------------------------------------------------------------
# Bozuk girdi: hata firlatma bicimi ayristirici KATMANINDA gecerlidir
# (denetleme katmani bunu yakalar -> test_denetim.py:cikti_bozuk)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bozuk",
    [
        "- Collecting inputs\n",
        "",
        "not json at all",
        "[1, 2, 3]",
        "null",
    ],
    ids=["spinner", "bos", "metin", "liste", "null"],
)
def test_bozuk_json_istisna_firlatir(bozuk):
    """Bozuk JSON dogrudan parse_* cagrisinda ValueError/AttributeError firlatir.

    Donusum yapmaz, sessizce bos saymaz: yukari katman bunu 'cikti-bozuk' yapar.
    """
    with pytest.raises((ValueError, AttributeError, TypeError)):
        parse_pip_audit(bozuk)
    with pytest.raises((ValueError, AttributeError, TypeError)):
        parse_npm_audit(bozuk)


# --------------------------------------------------------------------------
# Test verisi: gercek anahtar/sir yok
# --------------------------------------------------------------------------

#: Gercek sirlarin karsiligi: AWS erisim anahtari, GitHub PAT, acik API anahtari,
#: PEM ozel anahtar basligi, Bearer/JWT token.
GIZLI_KALIPLAR = [
    "AKIA",
    "ASIA",
    "ghp_",
    "gho_",
    "github_pat_",
    "sk-",
    "xoxb-",
    "-----BEGIN",
    "eyJhbGciOi",  # JWT
    "AIza",
    "://user:pass@",
]


@pytest.mark.parametrize("dosya", sorted(FIXTURES.glob("*.json")), ids=lambda p: p.name)
def test_fixture_larda_gercek_sir_yok(dosya):
    """Fixture metinlerinde gercek API anahtari/parola/ozel anahtar BULUNMAZ.

    Yalnizca public advisory kimlikleri (CVE-/GHSA-/PYSEC-) ve paket surumleri var.
    """
    icerik = dosya.read_text(encoding="utf-8")
    bulunan = [k for k in GIZLI_KALIPLAR if k in icerik]
    assert not bulunan, f"{dosya.name} icinde gercek sir kalibi: {bulunan}"
