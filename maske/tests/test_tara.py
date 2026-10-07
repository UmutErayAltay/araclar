"""tara: tur tespiti, kapsam disi kurallari, parmak izi (deger ASLA cikmaz)."""

from __future__ import annotations

from pathlib import Path

import pytest

from maske import tara

from conftest import GIZLI_AWS, GIZLI_GH, GIZLI_SIFRE, GIZLI_SK, SAHTE_AWS, repo_kur


def _tur(satir: str) -> str | None:
    """Tek satirdan bulunan ilk turun adini dondurur."""
    bulgular = tara.eslesmeler(satir)
    return bulgular[0][2] if bulgular else None


@pytest.mark.parametrize(
    "satir,tur",
    [
        (f'token = "{GIZLI_SK}"', "sk-anahtari"),
        (f"aws_key = {GIZLI_AWS}", "aws-anahtari"),
        (f"gh = {GIZLI_GH}", "github-token"),
        (f"API_KEY={GIZLI_SIFRE}", "anahtar-deger"),
        ("-----BEGIN RSA PRIVATE KEY-----", "ozel-anahtar"),
        (f"stripe = sk_live_{'a1B2c3D4' * 3}", "stripe-anahtari"),
    ],
)
def test_pozitif_turler(satir, tur):
    assert _tur(satir) == tur


@pytest.mark.parametrize(
    "satir",
    [
        "print('merhaba')",
        "API_KEY=<senin-anahtarin>",
        "API_KEY=xxxxxxxxxxxxxxxxxxxxxxxx",
        "api_key=${GITHAYIR}",
        "token = process.env.API_KEY",
        "API_KEY=changeme1234567890",
        "AKIAIOSFODNN7EXAMPLE",  # sahte isaretli (EXAMPLE)
        "yorum satiri: api_key = deneme",
    ],
)
def test_negatif_satirlar(satir):
    """Yer tutucu, kod referansi ve sahte isaretli deger bulgu DEGILDIR."""
    assert _tur(satir) is None


def test_bos_satir():
    assert tara.eslesmeler("") == []


def test_nul_lu_satir():
    assert tara.eslesmeler("a\x00b") == []


def test_etiket_eslesme_solundan_gelir():
    """`ad` etiketten okunur; deger etiket olamaz."""
    _, _, tur, ad = tara.eslesmeler(f'aws_token = "{GIZLI_AWS}"')[0]
    assert (tur, ad) == ("aws-anahtari", "aws_token")


def test_etiketsiz_satirda_ad_tur_adidir():
    """Saglayici deseni dogrudan eslesiyorsa eslesmenin kendisi AD OLABILMEZ."""
    _, _, tur, ad = tara.eslesmeler(GIZLI_AWS)[0]
    assert tur == "aws-anahtari"
    assert ad == "aws-anahtari"
    assert GIZLI_AWS not in ad  # ham deger ad olarak ASLA cikamaz


def test_etiket_kendisi_sira_benziyorsa_reddedilir():
    """Sira gibi gorunen etiket gosterilmez: rapor degeri sizdirirdi."""
    _, _, _tur_, ad = tara.eslesmeler(f"{GIZLI_AWS} = {GIZLI_AWS}")[0]
    assert GIZLI_AWS not in ad


def test_span_konumlari_dogru():
    satir = f'API_KEY={GIZLI_SIFRE}  # yorum'
    bas, bitis, _tur, _ad = tara.eslesmeler(satir)[0]
    assert satir[bas:bitis] == f"API_KEY={GIZLI_SIFRE}"


def test_kapsam_disi_dosyalar(tmp_path: Path):
    """Ornek dosyalar, test dosyalari ve tests/ dizini HEDEF DISIDIR."""
    assert tara.dosya_kapsam_disi(Path("a/b.example"), Path("a")) == "ornek-dosya"
    assert tara.dosya_kapsam_disi(Path("a/test_x.py"), Path("a")) == "test-dosyasi"
    assert tara.dosya_kapsam_disi(Path("a/tests/x.py"), Path("a")) == "tests-dizini"
    assert tara.dosya_kapsam_disi(Path("a/src/x.py"), Path("a")) is None


def test_repo_tarama_bulgular(tmp_path: Path, ev_isole):
    repo = repo_kur(
        tmp_path / "r",
        {
            "app.py": f'KEY = "{GIZLI_SK}"\n',
            "tests/test_x.py": f'KEY = "{GIZLI_SK}"\n',  # hedef disi
            "ayarlar.env.example": f"K={GIZLI_SK}\n",  # hedef disi
        },
    )
    veri = tara.tara([repo])
    assert len(veri["bulgar"]) == 1
    b = veri["bulgar"][0]
    assert b["dosya"] == "app.py" and b["satir"] == 1 and b["tur"] == "sk-anahtari"


def test_ayni_satirda_iki_bulgu(tmp_path: Path, ev_isole):
    repo = repo_kur(tmp_path / "r", {"a.py": f'a = {GIZLI_AWS}  secret = {GIZLI_SIFRE}\n'})
    assert len(tara.tara([repo])["bulgar"]) == 2


def test_kritik_dosyalar_ve_derinlik(tmp_path: Path, ev_isole):
    """`.git` ve dev klasorler hicbir zaman taranmaz."""
    repo = repo_kur(tmp_path / "r", {})
    (repo / ".git").mkdir(exist_ok=True)
    (repo / ".git" / "config").write_text(f'KEY = "{GIZLI_SK}"\n', encoding="utf-8")
    (repo / "node_modules").mkdir()
    (repo / "node_modules" / "p.js").write_text(f"K={GIZLI_SK}\n", encoding="utf-8")
    assert tara.tara([repo])["bulgar"] == []


def test_buyuk_dosya_atlanir(tmp_path: Path, ev_isole):
    repo = repo_kur(tmp_path / "r", {})
    (repo / "dev.txt").write_text(f"K = {GIZLI_SK}\n" + "x" * (1024 * 1024), encoding="utf-8")
    veri = tara.tara([repo])
    assert veri["bulgar"] == []
    assert veri["atlanan"]  # gerekce raporda


def test_ikili_dosya_sessizce_gecilir(tmp_path: Path, ev_isole):
    repo = repo_kur(tmp_path / "r", {})
    (repo / "logo.bin").write_bytes(b"\x89PNG\x00\x01" + b"\x00" * 64)
    assert tara.tara([repo])["bulgar"] == []


def test_crlf_dosya_satir_numarasi(tmp_path: Path, ev_isole):
    repo = repo_kur(tmp_path / "r", {"a.txt": f"ilk\r\nK={GIZLI_SK}\r\nson\r\n".encode()})
    b = tara.tara([repo])["bulgar"][0]
    assert b["satir"] == 2


def test_son_satirsatir_sonusuz(tmp_path: Path, ev_isole):
    repo = repo_kur(tmp_path / "r", {"a.txt": f"K={GIZLI_SK}".encode()})
    assert tara.tara([repo])["bulgar"][0]["satir"] == 1


def test_bulgu_degeri_icermez(tmp_path: Path, ev_isole):
    """Rapor govdesi hicbir yerde ham deger TASICAMAZ."""
    repo = repo_kur(tmp_path / "r", {"a.py": f'KEY="{GIZLI_SK}"\nAWS={GIZLI_AWS}\n'})
    veri = tara.tara([repo])
    metin = repr(veri)
    assert GIZLI_SK not in metin and GIZLI_AWS not in metin
    assert all(b["izi"] for b in veri["bulgar"])  # her biri tuzlu iz


def test_en_kisa_span_iz_alir(tmp_path: Path, ev_isole):
    """Her turun EN KISA eslesmesi `parmak.ASGARI_UZUNLUK`'tan uzundur.

    Bu bir sozlesmedir: `izi` alani `None` OLABILMEZ, cunku maske `izi`'yi
    rotasyon listesinde anahtar olarak kullanir (anahtarsiz kayitlar ayni sir
    gibi gorunurdu). Desenler `anahtarlik`'tadir; bu test, o sozlesmenin
    maske tarafinda kirilmadigini gorunur kilar.
    """
    from anahtarlik import parmak

    repo = repo_kur(tmp_path / "r", {"a.py": f"aws = {GIZLI_AWS}\n"})
    bulgu = tara.tara([repo])["bulgar"][0]
    assert bulgu["izi"] is not None
    assert len(bulgu["izi"]) == parmak.IZI_UZUNLUK
    # Bilinen EN KISA desen span'i (slack: 15 karakter) bile iz alir.
    repo2 = repo_kur(tmp_path / "r2", {"b.py": "s = xoxb-" + "a" * 10 + "\n"})
    assert tara.tara([repo2])["bulgar"][0]["izi"] is not None
    assert parmak.ASGARI_UZUNLUK < 15