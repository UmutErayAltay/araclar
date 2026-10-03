"""cli: API veri kaynağı, kategori/sıralama çıktısı (ağa çıkılmaz: sağlayıcı sahtelenir)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from portfolyo import cli, githubapi
from portfolyo.git import RepoVerisi
from test_cli import REPO, _ayar, _git_repo

SAHTE = RepoVerisi(commit_sayisi=9, ilk_commit=None, son_commit="2026-09-30", haftalik=None,
                   diller=(("Python", 100),), readme_ozeti=None, dil_birimi="yuzde")


@pytest.fixture()
def cagrilar(monkeypatch):
    kayit = []

    def sahte(sahip, repo, **kw):
        kayit.append((sahip, repo, kw))
        return SAHTE

    monkeypatch.setattr(githubapi, "repo_verisi_api", sahte)
    return kayit


def _site(tmp_path: Path) -> Path:
    return tmp_path / "site"


def test_veri_api_repo_icin_cagrilir_bayraksiz_da(tmp_path, cagrilar, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_TESTTOKEN")
    ayar = _ayar(tmp_path, [{**REPO, "veri": "api", "readme": True}, {**REPO, "ad": "yok-repo"}])
    assert cli.main(["uret", str(ayar), "--cikti", str(_site(tmp_path)), "--bugun", "2026-10-01"]) == 0
    assert [(s, r) for s, r, _ in cagrilar] == [("testuser", "demo")]  # yalnız veri:"api" olan
    assert cagrilar[0][2] == {"token": "ghp_TESTTOKEN", "readme": True}
    assert "<b>" in (_site(tmp_path) / "index.html").read_text(encoding="utf-8")


def test_api_bayragi_veri_belirtilmeyenleri_api_yapar_klonu_korur(tmp_path, cagrilar):
    klon = _git_repo(tmp_path / "klon")
    ayar = _ayar(tmp_path, [{**REPO, "ad": "a"}, {**REPO, "ad": "b", "klon": str(klon)}])
    assert cli.main(["uret", str(ayar), "--api", "--cikti", str(_site(tmp_path)), "--bugun", "2026-10-01"]) == 0
    assert [r for _, r, _ in cagrilar] == ["a"]  # b klondan okunur


def test_token_yoksa_none_gecer(tmp_path, cagrilar, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    ayar = _ayar(tmp_path, [{**REPO, "veri": "api"}])
    cli.main(["uret", str(ayar), "--cikti", str(_site(tmp_path))])
    assert cagrilar[0][2]["token"] is None


def test_api_okunamazsa_uyari_ama_calisir_token_sizmaz(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_TESTTOKEN")
    monkeypatch.setattr(githubapi, "repo_verisi_api", lambda *a, **k: None)
    ayar = _ayar(tmp_path, [{**REPO, "veri": "api"}])
    assert cli.main(["uret", str(ayar), "--cikti", str(_site(tmp_path))]) == 0
    c = capsys.readouterr()
    assert "demo" in c.err and "GitHub verisi okunamadı" in c.err
    assert "ghp_TESTTOKEN" not in c.out + c.err


def test_kontrol_kategori_ve_kaynak_gosterir(tmp_path, capsys):
    veri = {
        "sahip": {"ad": "T", "github": "testuser"},
        "kategoriler": ["Web"],
        "repolar": [{**REPO, "kategori": "Web", "veri": "api"}],
    }
    yol = tmp_path / "p.json"
    yol.write_text(json.dumps(veri), encoding="utf-8")
    assert cli.main(["kontrol", str(yol)]) == 0
    assert "demo [Web]: GitHub API" in capsys.readouterr().out


def test_ozel_repo_api_den_gelmez_sayfa_kartsiz_veriyle(tmp_path, monkeypatch):
    """Sağlayıcı özel repo için None dönerse kart yine yalnız yapılandırma metniyle çizilir."""
    monkeypatch.setattr(githubapi, "repo_verisi_api", lambda *a, **k: None)
    ayar = _ayar(tmp_path, [{**REPO, "veri": "api", "aciklama": "Yalnız yapılandırma"}])
    assert cli.main(["uret", str(ayar), "--cikti", str(_site(tmp_path))]) == 0
    sayfa = (_site(tmp_path) / "index.html").read_text(encoding="utf-8")
    assert "Yalnız yapılandırma" in sayfa and "commit ·" not in sayfa


# --- --siki ------------------------------------------------------------------------------

def test_siki_veri_alinamazsa_5_ve_hicbir_sey_yazilmaz(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(githubapi, "repo_verisi_api", lambda s, r, **k: None if r == "ozel" else SAHTE)
    ayar = _ayar(tmp_path, [{**REPO, "veri": "api"}, {**REPO, "ad": "ozel", "veri": "api"}])
    cikti = _site(tmp_path)
    assert cli.main(["uret", str(ayar), "--siki", "--cikti", str(cikti)]) == 5
    assert not cikti.exists()
    err = capsys.readouterr().err
    assert "--siki" in err and "ozel" in err


def test_siki_hepsi_tamamsa_yazar(tmp_path, cagrilar):
    ayar = _ayar(tmp_path, [{**REPO, "veri": "api"}])
    assert cli.main(["uret", str(ayar), "--siki", "--cikti", str(_site(tmp_path))]) == 0
    assert (_site(tmp_path) / "index.html").is_file()


def test_siki_yok_olan_repo_sorun_degil_klon_okunamazsa_sorun(tmp_path):
    ayar = _ayar(tmp_path, [REPO])  # veri: yok
    assert cli.main(["uret", str(ayar), "--siki", "--cikti", str(_site(tmp_path))]) == 0
    bozuk = _ayar(tmp_path, [{**REPO, "klon": str(tmp_path / "yok-klon")}])
    assert cli.main(["uret", str(bozuk), "--siki", "--cikti", str(tmp_path / "s2")]) == 5


def test_siki_olmadan_ayni_durum_yalniz_uyari(tmp_path, monkeypatch):
    monkeypatch.setattr(githubapi, "repo_verisi_api", lambda *a, **k: None)
    ayar = _ayar(tmp_path, [{**REPO, "veri": "api"}])
    assert cli.main(["uret", str(ayar), "--cikti", str(_site(tmp_path))]) == 0
