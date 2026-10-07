"""belge: `.env.example`, README ve docker-compose tarafi (yalniz ad).

Degerler bu modulle de hicbir yere girmez.
"""

from __future__ import annotations

from conftest import GIZLI_DEGER, sahte_repo

from ortam import belge


# --------------------------------------------------------------------------
# .env.example
# --------------------------------------------------------------------------


def test_ornek_adlari(tmp_path):
    """`.env.example` icindeki `AD=` satirlari tanimli degisken sayilir."""
    repo = sahte_repo(
        tmp_path / "r",
        {".env.example": f"# yorum\nexport DB_URL=\nAPI_KEY=\n\nBOZUK SATIR\nAPI_KEY=\n"},
    )
    veri = belge.belgeleri_tara(repo, [])
    assert veri["ornek"] == ["API_KEY", "DB_URL"]
    assert veri["dosyalar"]["ornek"] == [".env.example"]


def test_ornek_deger_basilmaz(tmp_path):
    """`AD=deger` satirinda deger okunmaz; yalniz AD raporlanir."""
    repo = sahte_repo(tmp_path / "r", {".env.example": f"SIFIR={GIZLI_DEGER}\n"})
    veri = belge.belgeleri_tara(repo, [])
    assert veri["ornek"] == ["SIFIR"]
    assert GIZLI_DEGER not in repr(veri)


def test_ornek_negatif_dosya_yok(tmp_path):
    """`.env.example` yoksa ornek AD kumesi BOSTUR (bulgu uretmez)."""
    repo = sahte_repo(tmp_path / "r", {".env": f"SIFIR={GIZLI_DEGER}\n"})
    assert belge.belgeleri_tara(repo, [])["ornek"] == []


def test_sample_adi_da_taninir(tmp_path):
    """`.env.sample` de sablon: ornek tarafina girer."""
    repo = sahte_repo(tmp_path / "r", {".env.sample": "X=1\n"})
    assert belge.belgeleri_tara(repo, [])["ornek"] == ["X"]


# --------------------------------------------------------------------------
# docker-compose
# --------------------------------------------------------------------------


def test_compose_environment_adlari(tmp_path):
    """docker-compose `environment:` altindaki AD'lar toplanir."""
    repo = sahte_repo(
        tmp_path / "r",
        {
            "docker-compose.yml": (
                "services:\n"
                "  app:\n"
                "    environment:\n"
                "      DB_HOST: localhost\n"
                "      DB_PORT: '5432'\n"
                "      DEBUG: 'true'\n"
                "    ports:\n"
                "      - '8080:8080'\n"
            )
        },
    )
    veri = belge.belgeleri_tara(repo, [])
    assert veri["compose"] == ["DB_HOST", "DB_PORT", "DEBUG"]
    assert veri["dosyalar"]["compose"] == ["docker-compose.yml"]


def test_compose_degisken_referansi(tmp_path):
    """`${AD}` bir referanstir: deger degil, AD sayilir."""
    repo = sahte_repo(
        tmp_path / "r",
        {"docker-compose.yml": "services:\n  app:\n    environment:\n      URL: ${API_URL}\n"},
    )
    assert "API_URL" in belge.belgeleri_tara(repo, [])["compose"]


def test_compose_negatif_environment_disi(tmp_path):
    """`ports:` altindaki satir `environment` DEGILDIR: AD sayilmaz."""
    repo = sahte_repo(
        tmp_path / "r",
        {"docker-compose.yml": "services:\n  app:\n    ports:\n      - '8080:8080'\n"},
    )
    assert belge.belgeleri_tara(repo, [])["compose"] == []


# --------------------------------------------------------------------------
# README
# --------------------------------------------------------------------------


def test_readme_adlari(tmp_path):
    """README'de gecen buyuk-harfli ortam adlari (tam kelime) belgelenmis sayilir."""
    repo = sahte_repo(
        tmp_path / "r",
        {"README.md": "Kurulum icin `DATABASE_URL` ve SENTRY_DSN ayarlayin.\n"},
    )
    veri = belge.belgeleri_tara(repo, [])
    assert {"DATABASE_URL", "SENTRY_DSN"} <= set(veri["readme"])


def test_readme_negatif_kucuk_harf(tmp_path):
    """Kucuk harfli `database_url` ortam adı DEGILDIR (sozluk metni)."""
    repo = sahte_repo(tmp_path / "r", {"README.md": "veritabini database_url ile kurun.\n"})
    assert belge.belgeleri_tara(repo, [])["readme"] == []
