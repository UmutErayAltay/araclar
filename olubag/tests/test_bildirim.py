"""bildirim: pyproject/requirements/package.json ayristirma (extras, izinli gruplar)."""

from __future__ import annotations

from pathlib import Path

from conftest import sahte_repo

from olubag.bildirim import bildirim_dosyasi_mi, bildirimleri, package_json, pyproject, requirements


# --------------------------------------------------------------------------
# pyproject.toml
# --------------------------------------------------------------------------


def test_pyproject_dependencies_ve_optional(tmp_path):
    """Hem [project].dependencies hem optional-dependentials gruplari okunur."""
    repo = sahte_repo(
        tmp_path / "r",
        {
            "pyproject.toml": (
                '[project]\n'
                'name = "r"\n'
                'dependencies = ["pyyaml>=6.0", "requests"]\n'
                "\n"
                "[project.optional-dependencies]\n"
                'test = ["pytest", "pytest-cov"]\n'
                'dok = ["sphinx"]\n'
            )
        },
    )
    adlar = [k["paket"] for k in pyproject(repo / "pyproject.toml", repo)]
    assert adlar == ["pyyaml", "requests", "pytest", "pytest-cov", "sphinx"]


def test_pyproject_extras_satiri_ayiklanir(tmp_path):
    """Extras'li bagimlilik (`uvicorn[standard]`) adi `uvicorn` olarak raporlanir."""
    repo = sahte_repo(
        tmp_path / "r",
        {"pyproject.toml": '[project]\ndependencies = ["uvicorn[standard]>=0.20"]\n'},
    )
    assert [k["paket"] for k in pyproject(repo / "pyproject.toml", repo)] == ["uvicorn"]


def test_pyproject_satir_numarasi_gercek(tmp_path):
    """Bulunan satir, ham metindeki GERCEK satir numarasidir."""
    icerik = (
        "[build-system]\n"          # 1
        'requires = ["setuptools"]\n'  # 2
        "\n"                          # 3
        "[project]\n"                 # 4
        'name = "r"\n'                # 5
        'dependencies = ["requests"]\n'  # 6
    )
    repo = sahte_repo(tmp_path / "r", {"pyproject.toml": icerik})
    kayit = pyproject(repo / "pyproject.toml", repo)[0]
    assert kayit["satir"] == 6, icerik.splitlines()


def test_pyproject_bos_dependencies(tmp_path):
    """`dependencies` hic yoksa bos liste (hata degil)."""
    repo = sahte_repo(tmp_path / "r", {"pyproject.toml": '[project]\nname = "r"\n'})
    assert pyproject(repo / "pyproject.toml", repo) == []


def test_pyproject_bozuk_toml_sessiz_gecer(tmp_path):
    """Bozuk TOML: PATLAMAZ, bos liste doner (uydurma bulgu uretmez)."""
    repo = sahte_repo(tmp_path / "r", {"pyproject.toml": "[project\nname = ??\n"})
    assert pyproject(repo / "pyproject.toml", repo) == []


def test_pyproject_tool_bolumleri_yok_sayilir(tmp_path):
    """Yalniz [project] okunur; [tool.*] altindaki listeler bagimlilik DEGILDIR."""
    repo = sahte_repo(
        tmp_path / "r",
        {"pyproject.toml": '[project]\nname = "r"\n\n[tool.ruff]\nselect = ["E", "F"]\n'},
    )
    assert pyproject(repo / "pyproject.toml", repo) == []


# --------------------------------------------------------------------------
# requirements*.txt
# --------------------------------------------------------------------------


def test_requirements_satirlari_ve_konumlari(tmp_path):
    """Yorumlar atlanir, gecerli paketler KENDI satir numarasiyla raporlanir."""
    icerik = (
        "# yorum\n"           # 1
        "-r base.txt\n"       # 2
        "requests==2.31.0\n"  # 3
        "\n"                  # 4
        "PyYAML>=6.0  # not\n"  # 5
        "-e .\n"              # 6
    )
    repo = sahte_repo(tmp_path / "r", {"requirements.txt": icerik})
    kayitlar = requirements(repo / "requirements.txt", repo)
    assert [(k["paket"], k["satir"]) for k in kayitlar] == [
        ("requests", 3),
        ("pyyaml", 5),
    ]


def test_requirements_dev_adi_ayni_kuralda(tmp_path):
    """Dev adli requirements dosyasi da ayni sekilde ayristirilir."""
    repo = sahte_repo(tmp_path / "r", {"requirements-dev.txt": "pytest==8.0\nblack\n"})
    assert [k["paket"] for k in requirements(repo / "requirements-dev.txt", repo)] == [
        "pytest",
        "black",
    ]


def test_requirements_bos_dosya(tmp_path):
    """Bos requirements.txt: bos liste, hata degil."""
    repo = sahte_repo(tmp_path / "r", {"requirements.txt": ""})
    assert requirements(repo / "requirements.txt", repo) == []


# --------------------------------------------------------------------------
# package.json
# --------------------------------------------------------------------------


def test_package_json_yalniz_dependencies(tmp_path):
    """devDependencies HARIC: bildirilen uygulama bagimliliklari okunur."""
    repo = sahte_repo(
        tmp_path / "r",
        {
            "package.json": (
                '{\n'
                '  "name": "r",\n'
                '  "dependencies": {"lodash": "^4.0.0", "express": "^4.0.0"},\n'
                '  "devDependencies": {"jest": "^29.0.0"}\n'
                "}\n"
            )
        },
    )
    adlar = [k["paket"] for k in package_json(repo / "package.json", repo)]
    assert adlar == ["lodash", "express"], "devDependencies karistirilmemeli, sira bildirim sirasi"


def test_package_json_scoped_paket(tmp_path):
    """Scoped paket adi (@scope/ad) oldugu gibi korunur."""
    repo = sahte_repo(
        tmp_path / "r",
        {"package.json": '{\n"dependencies": {"@scope/ad": "^1.0.0"}\n}\n'},
    )
    assert [k["paket"] for k in package_json(repo / "package.json", repo)] == ["@scope/ad"]


def test_package_json_bozuk_json_sessiz_gecer(tmp_path):
    """Bozuk JSON: patlamaz, bos liste doner."""
    repo = sahte_repo(tmp_path / "r", {"package.json": "{bozuk"})
    assert package_json(repo / "package.json", repo) == []


def test_package_json_dependencies_yok(tmp_path):
    """`dependencies` anahtari yoksa bos liste (dosya yine de bildirim dosyasidir)."""
    repo = sahte_repo(tmp_path / "r", {"package.json": '{\n"name": "r"\n}\n'})
    assert package_json(repo / "package.json", repo) == []


# --------------------------------------------------------------------------
# tur tespiti
# --------------------------------------------------------------------------


def test_bildirim_dosyasi_tespiti():
    """Yalniz bildirim dosyalari tespit edilir; kaynak dosya degildir."""
    assert bildirim_dosyasi_mi(Path("requirements.txt")) is True
    assert bildirim_dosyasi_mi(Path("requirements-dev.txt")) is True
    assert bildirim_dosyasi_mi(Path("pyproject.toml")) is True
    assert bildirim_dosyasi_mi(Path("package.json")) is True
    assert bildirim_dosyasi_mi(Path("app.py")) is False
    assert bildirim_dosyasi_mi(Path("index.js")) is False


def test_bildirimleri_dosya_turune_gore(tmp_path):
    """Tek giris noktasi dogru modulu secer: pyproject okur, kaynak dosya bos."""
    repo = sahte_repo(tmp_path / "r", {"pyproject.toml": '[project]\ndependencies = ["requests"]\n'})
    assert [k["paket"] for k in bildirimleri(repo / "pyproject.toml", repo)] == ["requests"]
    assert bildirimleri(repo / "app.py", repo) == []