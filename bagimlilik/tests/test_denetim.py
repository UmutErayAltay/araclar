"""denetle_repo: manifest kesfi, sahte `calistir` ile karar mantigi, YAZMAMA kaniti.

Gercek pip-audit / npm audit CALISTIRILMAZ; `calistir` parametresi sahte
fonksiyonla degistirilir. Ag yok, sure yok.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from conftest import fixture_yukle, sahte_calistir, sahte_repo, tree_hash

from bagimlilik.denetim import denetle_repo

# --------------------------------------------------------------------------
# Manifest kesfi
# --------------------------------------------------------------------------


def test_requirements_dosyalari_bulunur(pip_audit_kurulu, tmp_path):
    """requirements*.txt (ve requirements-dev.txt gibi varyantlar) denetlenir.

    KOK + 1 seviye altindaki dizinler taranir; kaynak yolu repo kokune gore yazilir.
    """
    repo = sahte_repo(tmp_path / "r", {
        "requirements.txt": "flask==0.12\n",
        "requirements-dev.txt": "pytest==8\n",
        "alt/requirements-prod.txt": "idna==2.7\n",
    })
    c = sahte_calistir(fixture_yukle("pip_audit_temiz"))
    sonuc = denetle_repo(repo, calistir=c)
    assert {d.kaynak for d in sonuc.denetimler} == {
        "requirements.txt", "requirements-dev.txt", "alt/requirements-prod.txt",
    }
    assert all(d.ekosistem == "pip" for d in sonuc.denetimler)


def test_skip_dirs_ici_requirements_taranmaz(pip_audit_kurulu, tmp_path):
    """node_modules/.venv gibi SKIP_DIRS icindeki requirements.txt gorulmez."""
    repo = sahte_repo(tmp_path / "r", {
        "requirements.txt": "flask==0.12\n",
        "node_modules/paket/requirements.txt": "zararli==1\n",
        ".venv/requirements.txt": "zararli==1\n",
    })
    sonuc = denetle_repo(repo, calistir=sahte_calistir(fixture_yukle("pip_audit_temiz")))
    assert [d.kaynak for d in sonuc.denetimler] == ["requirements.txt"]


def test_pyproject_dependencies_gecici_dosyaya_yazilir(pip_audit_kurulu, tmp_path):
    """pyproject.toml [project].dependencies -> gecici requirements.txt; repoya dokunulmaz.

    argv icindeki -r dosyasinin ICERIGI pyproject satirlari olmalidir ve bu dosya
    repo disinda olmalidir (yol 'alt' gibi alt klasorde bile repo altinda degil).
    """
    repo = sahte_repo(tmp_path / "r", {"pyproject.toml": (
        '[project]\nname = "x"\nversion = "0.1"\n'
        'dependencies = ["flask==0.12", "idna==2.7"]\n'
    )})
    c = sahte_calistir(fixture_yukle("pip_audit_temiz"))
    sonuc = denetle_repo(repo, calistir=c)
    assert [(d.ekosistem, d.kaynak) for d in sonuc.denetimler] == [("pip", "pyproject.toml")]
    cagri = c.cagrilar[0]
    assert cagri["requirements"] == "flask==0.12\nidna==2.7\n"
    gecici = Path(cagri["argv"][cagri["argv"].index("-r") + 1])
    assert repo not in gecici.parents and repo != gecici
    assert not (repo / "requirements.txt").exists(), "pyproject repoya yazildi"


def test_pyproject_bagimliliksiz_denetlenmez(pip_audit_kurulu, tmp_path):
    """[project].dependencies yoksa hicbir sey denetlenmez — hata DEGIL (bos liste)."""
    repo = sahte_repo(tmp_path / "r", {"pyproject.toml": '[project]\nname = "x"\n'})
    c = sahte_calistir("{}")
    sonuc = denetle_repo(repo, calistir=c)
    assert sonuc.denetimler == []
    assert c.cagrilar == []


def test_pyproject_bozuk_toml_denetlenmez(pip_audit_kurulu, tmp_path):
    """Bozuk TOML sessizce gecirilir (denetlenmez), istisna firlatilmaz."""
    repo = sahte_repo(tmp_path / "r", {"pyproject.toml": "bu [gecerli] degil = = =\n"})
    c = sahte_calistir("{}")
    sonuc = denetle_repo(repo, calistir=c)
    assert sonuc.denetimler == [] and c.cagrilar == []


def test_package_json_ve_lock_ile_npm_denetimi(pip_audit_kurulu, tmp_path):
    """package.json + package-lock.json -> npm audit; kaynak 'package.json'."""
    repo = sahte_repo(tmp_path / "r", {
        "package.json": '{"name": "x"}',
        "package-lock.json": '{"lockfileVersion": 3}',
    })
    c = sahte_calistir(fixture_yukle("npm_audit_acikli"))
    sonuc = denetle_repo(repo, calistir=c)
    npm_denetim = [d for d in sonuc.denetimler if d.ekosistem == "npm"]
    assert len(npm_denetim) == 1
    assert (npm_denetim[0].kaynak, npm_denetim[0].durum) == ("package.json", "acik")
    assert npm_denetim[0].toplam == 69


def test_package_json_lock_yoksa_kilit_yok(pip_audit_kurulu, tmp_path):
    """package.json var, lock YOK -> denetlenemedi(kilit-yok); hicbir komut CALISTIRILMAZ."""
    repo = sahte_repo(tmp_path / "r", {"package.json": '{"name": "x"}'})
    c = sahte_calistir(fixture_yukle("npm_audit_acikli"))
    sonuc = denetle_repo(repo, calistir=c)
    assert [(d.durum, d.neden) for d in sonuc.denetimler] == [("denetlenemedi", "kilit-yok")]
    assert c.cagrilar == [], "kilit yokken npm cagrildi"


# --------------------------------------------------------------------------
# Karar mantigi: cikis kodu degil, JSON ayristirilabilirligi
# --------------------------------------------------------------------------


def test_cikis_kodu_1_ve_json_acik(pip_audit_kurulu, tmp_path):
    """pip-audit acik buldugunda rc=1 doner; bu HATA DEGIL -> durum 'acik'."""
    repo = sahte_repo(tmp_path / "r", {"requirements.txt": "flask==0.12\n"})
    sonuc = denetle_repo(repo, calistir=sahte_calistir(fixture_yukle("pip_audit_acikli"), rc=1))
    d = sonuc.denetimler[0]
    assert d.durum == "acik" and d.toplam == 9 and d.neden is None


def test_cikis_kodu_1_ve_json_temiz(pip_audit_kurulu, tmp_path):
    """Tum bulgularda toplam 0 ise durum 'temiz' (acik sayilmaz)."""
    repo = sahte_repo(tmp_path / "r", {"requirements.txt": "pypdf==6.19.0\n"})
    sonuc = denetle_repo(repo, calistir=sahte_calistir(fixture_yukle("pip_audit_temiz"), rc=0))
    assert sonuc.denetimler[0].durum == "temiz"


def test_npm_temiz_metadata_total_sifir(pip_audit_kurulu, tmp_path):
    """npm'de toplam metadata'dan gelir; 0 ise temiz, acik listesinden degil."""
    repo = sahte_repo(tmp_path / "r", {"package.json": "{}", "package-lock.json": "{}"})
    temiz = '{"metadata": {"vulnerabilities": {"total": 0}}}'
    sonuc = denetle_repo(repo, calistir=sahte_calistir(temiz))
    assert sonuc.denetimler[0].durum == "temiz"


def test_ayristirilamayan_cikti_asla_temiz_sayilmaz(pip_audit_kurulu, tmp_path):
    """Spinner/bozuk metin -> denetlenemedi(cikti-bozuk). 'temiz' KESINLIKLE olmaz.

    Regresyon: 'denetlenemedi ASLA temiz sayilmaz' baglayici kurali.
    """
    repo = sahte_repo(tmp_path / "r", {"requirements.txt": "flask==0.12\n"})
    for bozuk in ("- Collecting inputs\n", "", "not json"):
        sonuc = denetle_repo(repo, calistir=sahte_calistir(bozuk, rc=0))
        d = sonuc.denetimler[0]
        assert (d.durum, d.neden) == ("denetlenemedi", "cikti-bozuk")
        assert d.toplam == 0 and d.aciklar == []


def test_zaman_asimi(pip_audit_kurulu, tmp_path):
    """TimeoutExpired -> denetlenemedi(zaman-asimi); tarama cokmez."""
    repo = sahte_repo(tmp_path / "r", {"requirements.txt": "flask==0.12\n"})
    c = sahte_calistir(hata=subprocess.TimeoutExpired(cmd="pip_audit", timeout=5))
    sonuc = denetle_repo(repo, calistir=c, zaman_asimi=7)
    d = sonuc.denetimler[0]
    assert (d.durum, d.neden) == ("denetlenemedi", "zaman-asimi")
    assert c.cagrilar[0]["zaman_asimi"] == 7
    assert "7 saniyede" in d.ayrinti


def test_arac_yok(pip_audit_kurulu, tmp_path):
    """FileNotFoundError -> denetlenemedi(arac-yok)."""
    repo = sahte_repo(tmp_path / "r", {"requirements.txt": "flask==0.12\n"})
    sonuc = denetle_repo(repo, calistir=sahte_calistir(hata=FileNotFoundError("pip_audit yok")))
    assert (sonuc.denetimler[0].durum, sonuc.denetimler[0].neden) == ("denetlenemedi", "arac-yok")


def test_pip_audit_kurulu_degilse_arac_yok(tmp_path, monkeypatch):
    """pip_audit modulu yoksa (find_spec None) hic komut surulmez, 'arac-yok' doner."""
    import importlib.util

    monkeypatch.setattr(importlib.util, "find_spec", lambda *a, **k: None)
    repo = sahte_repo(tmp_path / "r", {"requirements.txt": "flask==0.12\n"})
    c = sahte_calistir(fixture_yukle("pip_audit_temiz"))
    sonuc = denetle_repo(repo, calistir=c)
    assert (sonuc.denetimler[0].neden) == "arac-yok"
    assert c.cagrilar == []


def test_beklenmeyen_istisna_taramayi_cokertmez(pip_audit_kurulu, tmp_path):
    """Bilinmeyen istisna (RuntimeError) -> denetlenemedi('hata'); diger repolar etkilenmez.

    Istisna sinifinda adi + mesaji ayrinti olarak korunur (neden='hata').
    """
    repo = sahte_repo(tmp_path / "r", {
        "requirements.txt": "flask==0.12\n",
        "alt/requirements.txt": "idna==2.7\n",
    })

    def patla(argv, cwd, zaman_asimi):
        if "alt" in str(argv):
            raise RuntimeError("beklenmeyen patlama")
        return 0, fixture_yukle("pip_audit_temiz"), ""

    sonuc = denetle_repo(repo, calistir=patla)
    durumlar = {d.kaynak: (d.durum, d.neden) for d in sonuc.denetimler}
    assert durumlar["requirements.txt"] == ("temiz", None)
    assert durumlar["alt/requirements.txt"] == ("denetlenemedi", "hata")
    assert "RuntimeError" in next(d for d in sonuc.denetimler if d.neden == "hata").ayrinti


def test_npm_hata_yollari(pip_audit_kurulu, tmp_path, monkeypatch):
    """npm'de timeout / arac-yok / hata ayni iki duruma iner, 'temiz' olmaz."""
    monkeypatch.setattr(shutil, "which", lambda _ad: "npm")
    repo = sahte_repo(tmp_path / "r", {"package.json": "{}", "package-lock.json": "{}"})
    senaryolar = {
        subprocess.TimeoutExpired(cmd="npm", timeout=3): "zaman-asimi",
        FileNotFoundError("npm yok"): "arac-yok",
        RuntimeError("patladi"): "hata",
    }
    for hata, neden in senaryolar.items():
        sonuc = denetle_repo(repo, calistir=sahte_calistir(hata=hata))
        d = sonuc.denetimler[0]
        assert (d.durum, d.neden) == ("denetlenemedi", neden)


def test_npm_kurulu_degilse_arac_yok(pip_audit_kurulu, tmp_path, monkeypatch):
    """npm PATH'te yoksa (which None) denetim 'arac-yok'; komut surulmez."""
    monkeypatch.setattr(shutil, "which", lambda _ad: None)
    repo = sahte_repo(tmp_path / "r", {"package.json": "{}", "package-lock.json": "{}"})
    c = sahte_calistir(fixture_yukle("npm_audit_acikli"))
    sonuc = denetle_repo(repo, calistir=c)
    assert (sonuc.denetimler[0].durum, sonuc.denetimler[0].neden) == ("denetlenemedi", "arac-yok")
    assert c.cagrilar == []


def test_npm_bozuk_total_taramayi_cokertmemeli(pip_audit_kurulu, tmp_path, monkeypatch):
    """BULUNDU (denetim.py:281-283): metadata.vulnerabilities.total SAYI DEGILSE istisna kacar.

    `_cozum` icindeki ikinci `json.loads(stdout)` / `int(total)` cagrisi
    try/except DISINDA: bozuk total degerde ValueError denetle_repo'dan disari
    tasar. Sozlesme 'hicbir istisna disari tasmaz' ve 'denetlenemedi ASLA
    temiz sayilmaz' -> dogru davranis: denetlenemedi(cikti-bozuk).
    """
    monkeypatch.setattr(shutil, "which", lambda _ad: "npm")
    repo = sahte_repo(tmp_path / "r", {"package.json": "{}", "package-lock.json": "{}"})
    bozuk = json.dumps({"metadata": {"vulnerabilities": {"total": "not-a-number"}}, "vulnerabilities": {}})
    try:
        sonuc = denetle_repo(repo, calistir=sahte_calistir(bozuk))
    except ValueError as exc:
        pytest.fail(f"BOZUK TOTAL TARAMAYI COKERTIYOR (denetim.py:281): {exc}")
    d = sonuc.denetimler[0]
    assert (d.durum, d.neden) == ("denetlenemedi", "cikti-bozuk")
    assert d.toplam == 0


def test_ayrinti_kirpilmasi(pip_audit_kurulu, tmp_path):
    """ayrinti en fazla 300 karaktere kirpilir (devasa stderr raporu sisirmesin)."""
    repo = sahte_repo(tmp_path / "r", {"requirements.txt": "flask==0.12\n"})
    c = sahte_calistir("bozuk", rc=0, stderr="hata: " + "x" * 5000)
    sonuc = denetle_repo(repo, calistir=c)
    d = sonuc.denetimler[0]
    assert (d.durum, d.neden) == ("denetlenemedi", "cikti-bozuk")
    assert len(d.ayrinti) == 300


# --------------------------------------------------------------------------
# Regresyon: pip-audit argv'i
# --------------------------------------------------------------------------


def test_pip_argv_json_ve_spinner_kapat(pip_audit_kurulu, tmp_path):
    """argv'de `--format json` ve `--progress-spinner off` VAR olmali.

    Regresyon: spinner metni ('- Collecting inputs') stdout'a karisip JSON'u
    bozuyor; cikti katmani JSON ayristiramayinca 'denetlenemedi' oluyor.
    """
    repo = sahte_repo(tmp_path / "r", {"requirements.txt": "flask==0.12\n"})
    c = sahte_calistir(fixture_yukle("pip_audit_temiz"))
    denetle_repo(repo, calistir=c)
    argv = c.cagrilar[0]["argv"]
    assert "--format" in argv and argv[argv.index("--format") + 1] == "json"
    assert "--progress-spinner" in argv and argv[argv.index("--progress-spinner") + 1] == "off"
    assert argv[0].endswith(("python", "python.exe")) and "pip_audit" in argv


def test_pip_requirements_yol_argv_de_gecer(pip_audit_kurulu, tmp_path):
    """-r argumani repo icindeki GERCEK requirements dosyasini gosterir (yerinde okunur)."""
    req = tmp_path / "r" / "requirements.txt"
    repo = sahte_repo(tmp_path / "r", {"requirements.txt": "flask==0.12\n"})
    c = sahte_calistir(fixture_yukle("pip_audit_temiz"))
    denetle_repo(repo, calistir=c)
    assert c.cagrilar[0]["argv"][c.cagrilar[0]["argv"].index("-r") + 1] == str(req)


# --------------------------------------------------------------------------
# Regresyon: npm gecici dizinde calisir
# --------------------------------------------------------------------------


def test_npm_gecici_dizinde_calisir_ve_kopyalar(pip_audit_kurulu, tmp_path, monkeypatch):
    """npm denetimi repo DIŞINDAKI gecici dizinde surulur; cwd repo DEGILDIR.

    cwd'de package.json + package-lock.json kopyalari vardir (npm bunlari okur).
    """
    monkeypatch.setattr(shutil, "which", lambda _ad: "npm")
    repo = sahte_repo(tmp_path / "r", {"package.json": '{"name": "x"}', "package-lock.json": "{}"})
    c = sahte_calistir(fixture_yukle("npm_audit_acikli"))
    denetle_repo(repo, calistir=c)
    cagri = c.cagrilar[0]
    assert Path(cagri["cwd"]) != repo
    assert repo not in Path(cagri["cwd"]).parents
    assert cagri["cwd_icerik"] == ["package-lock.json", "package.json"]
    assert cagri["argv"][1:] == ["audit", "--json", "--package-lock-only"]


# --------------------------------------------------------------------------
# YAZMAMA KANITI
# --------------------------------------------------------------------------


@pytest.mark.parametrize("ad, dosyalar", [
    ("pip", {"requirements.txt": "flask==0.12\n", "pyproject.toml": '[project]\ndependencies = ["idna==2.7"]\n'}),
    ("npm", {"package.json": '{"name": "x"}', "package-lock.json": "{}"}),
    ("npm-kilit-yok", {"package.json": '{"name": "x"}'}),
    ("karisik", {"requirements.txt": "flask==0.12\n", "package.json": "{}", "package-lock.json": "{}"}),
    ("desteklenmeyen", {"go.mod": "module x\n", "Cargo.toml": "[package]\nname='x'\n"}),
], ids=lambda v: v if isinstance(v, str) else "")
def test_denetleme_repoya_hicbir_sey_yazmaz(pip_audit_kurulu, tmp_path, monkeypatch, ad, dosyalar):
    """denetle_repo oncesi/sonrasi tum dosyalarin (yol+içerik) hash'i AYNI kalir.

    Gecici dosyalar repoya degil tempfile dizinine yazilir; npm kopyalari da oraya.
    Kanit: tree_hash (yol+icerik sha256 toplami) degismez.
    """
    monkeypatch.setattr(shutil, "which", lambda _ad: "npm")
    repo = sahte_repo(tmp_path / ad, dosyalar)
    once = tree_hash(repo)
    denetle_repo(repo, calistir=sahte_calistir(fixture_yukle("npm_audit_acikli")))
    assert tree_hash(repo) == once, "denetleme repoya dosya yazdi/degistirdi"
    assert not (repo / "node_modules").exists()


def test_node_modules_ve_yeni_dosya_olusmaz(pip_audit_kurulu, tmp_path, monkeypatch):
    """npm denetimi sonrasi repo kokunde node_modules ya da yeni dosya olusmaz."""
    monkeypatch.setattr(shutil, "which", lambda _ad: "npm")
    repo = sahte_repo(tmp_path / "r", {"package.json": "{}", "package-lock.json": "{}"})
    denetle_repo(repo, calistir=sahte_calistir(fixture_yukle("npm_audit_acikli")))
    assert sorted(p.name for p in repo.iterdir()) == [".git", "package-lock.json", "package.json"]


# --------------------------------------------------------------------------
# Desteklenmeyen ekosistemler
# --------------------------------------------------------------------------


def test_desteklenmeyen_manifestler_listelenir(tmp_path):
    """.csproj / build.gradle / go.mod / Cargo.toml / pom.xml desteklenmez olarak raporlanir."""
    repo = sahte_repo(tmp_path / "r", {
        "go.mod": "module x\n",
        "Cargo.toml": "[package]\n",
        "pom.xml": "<project/>\n",
        "app.csproj": "<Project/>\n",
        "build.gradle": "plugins {}\n",
        "alt/go.mod": "module y\n",
    })
    sonuc = denetle_repo(repo, calistir=sahte_calistir("{}"))
    assert set(sonuc.desteklenmeyen) == {
        "go.mod", "Cargo.toml", "pom.xml", "app.csproj", "build.gradle", "alt/go.mod",
    }
    assert sonuc.denetimler == []


def test_bos_repo_sonucsuz_doner(tmp_path):
    """Hicbir manifesti olmayan repo: denetim yok, hata yok, desteklenmeyen yok."""
    sonuc = denetle_repo(sahte_repo(tmp_path / "bos"), calistir=sahte_calistir("{}"))
    assert sonuc.denetimler == [] and sonuc.desteklenmeyen == []
    assert sonuc.ad == "bos" and sonuc.yol.endswith("bos")


def test_is_adi_ve_yol_dogru(tmp_path):
    """RepoSonuc yol/ad alanlari denetlenen dizini yansitir."""
    repo = sahte_repo(tmp_path / "benim-proje")
    sonuc = denetle_repo(repo, calistir=sahte_calistir("{}"))
    assert sonuc.yol == str(repo) and sonuc.ad == "benim-proje"


def test_varsayilan_calistirici_alt_surece_utf8_verir():
    """pip-audit Windows'ta UTF-8 requirements'i cp1254 ile okuyup cokuyordu (artemis repo'su)."""
    import sys
    from bagimlilik.denetim import _calistir

    rc, out, _ = _calistir([sys.executable, "-c", "import os;print(os.environ.get('PYTHONUTF8'))"], None, 30)
    assert rc == 0 and out.strip() == "1"
