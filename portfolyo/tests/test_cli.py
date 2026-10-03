"""cli.py: kontrol/uret akışı, denetim kapısı ve çıkış kodları."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from portfolyo import cli


def _ayar(tmp_path: Path, repolar: list[dict], **sahip) -> Path:
    veri = {
        "sahip": {"ad": "Test Kişi", "unvan": "Geliştirici", "github": "testuser",
                  "hakkinda": "Merhaba.", **sahip},
        "repolar": repolar,
    }
    yol = tmp_path / "portfolyo.json"
    yol.write_text(json.dumps(veri, ensure_ascii=False), encoding="utf-8")
    return yol


def _git_repo(yol: Path) -> Path:
    yol.mkdir()
    env = ["-c", "commit.gpgsign=false", "-c", "user.name=t", "-c", "user.email=t@t.invalid"]
    subprocess.run(["git", "init", "-q"], cwd=yol, check=True, capture_output=True)
    (yol / "a.py").write_text("x", encoding="utf-8")
    subprocess.run(["git", "add", "a.py"], cwd=yol, check=True, capture_output=True)
    subprocess.run(["git", *env, "commit", "-q", "-m", "ilk"], cwd=yol, check=True, capture_output=True)
    return yol


REPO = {"ad": "demo", "herkese_acik": True, "aciklama": "Demo repo", "etiketler": ["Python"]}


def test_kontrol_gecerli(tmp_path, capsys):
    assert cli.main(["kontrol", str(_ayar(tmp_path, [REPO]))]) == 0
    out = capsys.readouterr().out
    assert "1 repo" in out and "demo" in out


def test_kontrol_ozel_repo_reddedilir(tmp_path, capsys):
    ayar = _ayar(tmp_path, [{**REPO, "herkese_acik": False}])
    assert cli.main(["kontrol", str(ayar)]) == 2
    err = capsys.readouterr().err
    assert "Hata" in err and "Traceback" not in err


def test_ayar_dosyasi_yok_2(tmp_path, capsys):
    assert cli.main(["kontrol", str(tmp_path / "yok.json")]) == 2


def test_uret_dosya_yazar_klonla(tmp_path, capsys):
    klon = _git_repo(tmp_path / "klon")
    ayar = _ayar(tmp_path, [{**REPO, "klon": str(klon)}])
    cikti = tmp_path / "site"
    assert cli.main(["uret", str(ayar), "--cikti", str(cikti), "--bugun", "2026-10-01"]) == 0
    assert sorted(p.name for p in cikti.iterdir()) == [".nojekyll", "index.html"]
    sayfa = (cikti / "index.html").read_text(encoding="utf-8")
    assert "demo" in sayfa and "<b>1</b>" in sayfa
    assert "https://github.com/testuser/demo" in sayfa
    assert str(klon) not in sayfa and str(tmp_path) not in capsys.readouterr().out  # yol sızmaz


def test_uret_klonsuz_calisir(tmp_path):
    cikti = tmp_path / "site"
    assert cli.main(["uret", str(_ayar(tmp_path, [REPO])), "--cikti", str(cikti)]) == 0
    assert "Demo repo" in (cikti / "index.html").read_text(encoding="utf-8")


def test_uret_okunamayan_klon_uyarir_ama_calisir(tmp_path, capsys):
    ayar = _ayar(tmp_path, [{**REPO, "klon": str(tmp_path / "yok")}])
    assert cli.main(["uret", str(ayar), "--cikti", str(tmp_path / "site")]) == 0
    err = capsys.readouterr().err
    assert "klon okunamadı" in err and str(tmp_path) not in err


def test_uret_denetim_bulgusu_4_ve_hicbir_sey_yazilmaz(tmp_path, capsys):
    sir = "sk-" + "a" * 30
    ayar = _ayar(tmp_path, [{**REPO, "aciklama": f"anahtar {sir}"}])
    cikti = tmp_path / "site"
    assert cli.main(["uret", str(ayar), "--cikti", str(cikti)]) == 4
    err = capsys.readouterr().err
    assert "api-anahtari" in err and sir not in err  # maskeli
    assert not cikti.exists()


def test_uret_eposta_ve_yerel_yol_bulgu(tmp_path):
    ayar = _ayar(tmp_path, [{**REPO, "aciklama": "bana ulaş: kisi@example.com"}])
    assert cli.main(["uret", str(ayar), "--cikti", str(tmp_path / "s")]) == 4
    ayar2 = _ayar(tmp_path, [{**REPO, "aciklama": "/home/umut/proje"}])
    assert cli.main(["uret", str(ayar2), "--cikti", str(tmp_path / "s2")]) == 4


def test_uret_kuru_yazmaz(tmp_path, capsys):
    cikti = tmp_path / "site"
    assert cli.main(["uret", str(_ayar(tmp_path, [REPO])), "--cikti", str(cikti), "--kuru"]) == 0
    assert not cikti.exists()
    assert "Yazılmadı" in capsys.readouterr().out


def test_gecersiz_tarih_2(tmp_path):
    assert cli.main(["uret", str(_ayar(tmp_path, [REPO])), "--cikti", str(tmp_path / "s"),
                     "--bugun", "yarin"]) == 2


def test_xss_aciklama_kacislanir(tmp_path):
    ayar = _ayar(tmp_path, [{**REPO, "aciklama": "<script>alert(1)</script>"}])
    # denetim `<script`'i dış-kaynak sayar ama kaçışlı hali (&lt;script) sayfaya girer
    cikti = tmp_path / "s"
    assert cli.main(["uret", str(ayar), "--cikti", str(cikti)]) == 0
    sayfa = (cikti / "index.html").read_text(encoding="utf-8")
    assert "<script" not in sayfa and "&lt;script" in sayfa
