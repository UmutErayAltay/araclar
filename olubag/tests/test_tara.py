"""tara: pozitif/negatif bulgular, eslesme tablosu, belirsiz durum, izin listesi.

Salt-okunurluk: her testten sonra dosya agaci BIRE BIR ayni kalmalidir.
"""

from __future__ import annotations

from pathlib import Path

from conftest import js_repo, paketler, py_repo, sahte_repo, tree_hash, turler, turu

from olubag.tara import tara


# --------------------------------------------------------------------------
# Python: pozitif / negatif
# --------------------------------------------------------------------------


def test_kullanilan_bulgu_yok(tmp_path):
    """Import edilen bagimlilik BULGU DEGILDIR: negatif test."""
    repo = py_repo(tmp_path / "r", ["requests"], kaynak="import requests\n")
    veri = tara([repo])
    assert veri["ozet"] == {"repo": 1, "kullanilmayan": 0, "belirsiz": 0}


def test_kullanilmayan_bulgu(tmp_path):
    """Import edilmeyen bagimlilik `kullanilmayan` bulgusu verir: pozitif test."""
    repo = py_repo(tmp_path / "r", ["requests"], kaynak="print('merhaba')\n")
    veri = tara([repo])
    assert turu(veri, "requests") == "kullanilmayan"
    assert veri["ozet"]["kullanilmayan"] == 1


def test_bulgu_bildirildigi_dosyayi_gosterir(tmp_path):
    """Bulgu `dosya:satir` ile bildirildigi YERI gosterir (pyproject.toml:4)."""
    repo = py_repo(tmp_path / "r", ["requests"], kaynak="print('x')\n")
    bulgular = tara([repo])["repolar"][0]["bulgular"]
    assert bulgular[0]["dosya"] == "pyproject.toml"
    assert bulgular[0]["satir"] == 4


def test_birden_fazla_bulgu_sirali(tmp_path):
    """Coklu kullanilmayan bagimlilik tamam raporlanir."""
    repo = py_repo(tmp_path / "r", ["requests", "rich", "httpx"], kaynak="print('x')\n")
    assert paketler(tara([repo])) == {"requests", "rich", "httpx"}


# --------------------------------------------------------------------------
# Eşleme tablosu uçtan uca
# --------------------------------------------------------------------------


def test_pyyaml_yaml_import_ile_eslesir(tmp_path):
    """pyyaml bildirilip `import yaml` varsa KULLANILIR (bulgu yok)."""
    repo = py_repo(tmp_path / "r", ["pyyaml>=6.0"], kaynak="import yaml\n\nyaml.safe_load\n")
    assert tara([repo])["ozet"]["kullanilmayan"] == 0


def test_pyyaml_kullanilmissa_ama_ad_diger(tmp_path):
    """`import requests` varken pyyaml KULLANILMIS sayilmaz."""
    repo = py_repo(tmp_path / "r", ["pyyaml"], kaynak="import requests\n")
    assert turu(tara([repo]), "pyyaml") == "kullanilmayan"


def test_scikit_learn_sklearn_import_ile_eslesir(tmp_path):
    """scikit-learn -> sklearn eslesmesi uctan uca calisir."""
    repo = py_repo(tmp_path / "r", ["scikit-learn"], kaynak="from sklearn.cluster import KMeans\n")
    assert tara([repo])["ozet"]["kullanilmayan"] == 0


def test_pillow_pil_import_ile_eslesir(tmp_path):
    """pillow -> PIL eslesmesi uctan uca calisir."""
    repo = py_repo(tmp_path / "r", ["pillow"], kaynak="from PIL import Image\n")
    assert tara([repo])["ozet"]["kullanilmayan"] == 0


def test_psycopg2_import_ile_eslesir(tmp_path):
    """psycopg2-binary -> psycopg2 eslesmesi (wheel adindan bagimlilik adi cikarilir)."""
    repo = py_repo(tmp_path / "r", ["psycopg2-binary"], kaynak="import psycopg2\n")
    assert tara([repo])["ozet"]["kullanilmayan"] == 0


def test_python_docx_import_ile_eslesir(tmp_path):
    """python-docx -> docx: gercek projelerde (danis) karsilastigi yanlis pozitif."""
    repo = py_repo(tmp_path / "r", ["python-docx>=1.1"], kaynak="import docx\n")
    assert tara([repo])["ozet"]["kullanilmayan"] == 0


# --------------------------------------------------------------------------
# İzin listesi
# --------------------------------------------------------------------------


def test_pytest_kullanilmissa_sayilir(tmp_path):
    """pytest hic import edilmese de izinlidir: bulgu DEGILDIR."""
    repo = py_repo(tmp_path / "r", ["pytest"], kaynak="print('x')\n")
    assert tara([repo])["ozet"]["kullanilmayan"] == 0


def test_pytest_eklentisi_bulgu_degil(tmp_path):
    """pytest eklentileri (pytest-cov) izinlidir: bulgu DEGILDIR."""
    repo = py_repo(tmp_path / "r", ["pytest-cov", "pytest-asyncio"], kaynak="print('x')\n")
    assert tara([repo])["ozet"]["kullanilmayan"] == 0


def test_setuptools_hatchling_izinli(tmp_path):
    """Derleme araclari (setuptools, hatchling) izinlidir."""
    repo = py_repo(tmp_path / "r", ["setuptools", "hatchling"], kaynak="print('x')\n")
    assert tara([repo])["ozet"]["kullanilmayan"] == 0


# --------------------------------------------------------------------------
# Belirsiz durum (__import__ / importlib)
# --------------------------------------------------------------------------


def test_dinamik_import_belirsiz(tmp_path):
    """`__import__('ad')` kullanan kod varsa paket `belirsiz` sayilir, bulgu DEGILDIR."""
    repo = py_repo(tmp_path / "r", ["requests"], kaynak="import importlib\n\nimportlib.import_module('x')\n")
    veri = tara([repo])
    assert turu(veri, "requests") == "belirsiz"
    assert veri["ozet"]["kullanilmayan"] == 0, "belirsiz, kullanilmayan sayilmamali"
    assert veri["ozet"]["belirsiz"] == 1


def test_underscore_import_belirsiz(tmp_path):
    """Dogrudan `__import__(...)` cagrisi da belirsiz yapar."""
    repo = py_repo(tmp_path / "r", ["requests"], kaynak="def yukle():\n    __import__('x')\n")
    assert turu(tara([repo]), "requests") == "belirsiz"


def test_kullanilan_paket_belirsiz_olmaz(tmp_path):
    """Belirsizlik yalniz KULLANILMAYAN pakete uygulanir; kullanilan paket bulgu degil."""
    repo = py_repo(tmp_path / "r", ["requests"], kaynak="import requests\nimport importlib\n\nimportlib.import_module('x')\n")
    assert paketler(tara([repo])) == set(), "kullanilan paket belirsiz/isaretlenmemeli"


# --------------------------------------------------------------------------
# Sözdizimi hatalı / okunamayan dosyalar
# --------------------------------------------------------------------------


def test_sozdizimi_hatali_dosya_atlanir(tmp_path):
    """Bozuk Python dosyasi ATLANIR: import sayilmaz ama arac cokmez."""
    repo = py_repo(tmp_path / "r", ["requests"], kaynak="import requests\n")
    (repo / "bozuk.py").write_text("def (:\n  import ", encoding="utf-8")
    veri = tara([repo])
    assert veri["ozet"]["kullanilmayan"] == 0


# --------------------------------------------------------------------------
# JS tarafı
# --------------------------------------------------------------------------


def test_js_require_kullanilan(tmp_path):
    """`require('lodash')` varsa bagimlilik KULLANILIR (bulgu yok)."""
    repo = js_repo(tmp_path / "r", ["lodash"], kaynak="const _ = require('lodash');\n")
    assert tara([repo])["ozet"]["kullanilmayan"] == 0


def test_js_require_kullanilmayan(tmp_path):
    """JS'te hic require edilmeyen bagimlilik bulgu verir."""
    repo = js_repo(tmp_path / "r", ["express"], kaynak="const _ = require('lodash');\n")
    assert turu(tara([repo]), "express") == "kullanilmayan"


def test_js_import_from_kullanilan(tmp_path):
    """`import x from 'x'` ve `import('x')` de kullanilmis sayilir."""
    repo = js_repo(
        tmp_path / "r",
        ["chalk", "node-fetch"],
        kaynak="import chalk from 'chalk';\nconst f = await import('node-fetch');\n",
    )
    assert tara([repo])["ozet"]["kullanilmayan"] == 0


def test_js_scoped_paket(tmp_path):
    """Scoped bagimlilik @scope/ad: `require('@scope/ad')` ile eslesir."""
    repo = js_repo(tmp_path / "r", ["@scope/ad"], kaynak="const x = require('@scope/ad');\n")
    assert tara([repo])["ozet"]["kullanilmayan"] == 0


def test_js_alt_yol_modul_adina_indirgenir(tmp_path):
    """`require('lodash/fp')` -> paket adi 'lodash' olarak eslesir."""
    repo = js_repo(tmp_path / "r", ["lodash"], kaynak="const fp = require('lodash/fp');\n")
    assert tara([repo])["ozet"]["kullanilmayan"] == 0


def test_js_devdependencies_bulgu_vermez(tmp_path):
    """devDependencies TARAMADA HİÇ YOK sayilir: hicbir bulgu uretmez."""
    repo = sahte_repo(
        tmp_path / "r",
        {
            "package.json": '{\n"dependencies": {"express": "^4.0.0"},\n"devDependencies": {"jest": "^29.0.0"}\n}\n',
            "index.js": "const x = 1;\n",
        },
    )
    assert paketler(tara([repo])) == {"express"}, "jest (devDependency) bulgu vermemeli"


def test_js_ve_python_ayri_degerlendirilir(tmp_path):
    """JS bagimliligi Python import'undan ETKILENMEZ."""
    repo = sahte_repo(
        tmp_path / "r",
        {
            "package.json": '{\n"dependencies": {"express": "^4.0.0"}\n}\n',
            "index.js": "console.log(1);\n",
            "app.py": "import requests\n",
        },
    )
    assert paketler(tara([repo])) == {"express"}


# --------------------------------------------------------------------------
# Çoklu bildirim / tekrarlar
# --------------------------------------------------------------------------


def test_ayni_paket_iki_dosyada_tek_bulgu(tmp_path):
    """Ayni paket pyproject VE requirements'ta ise TEK KEZ raporlanir."""
    repo = sahte_repo(
        tmp_path / "r",
        {
            "pyproject.toml": '[project]\ndependencies = ["requests"]\n',
            "requirements.txt": "requests==2.31.0\n",
            "app.py": "print('x')\n",
        },
    )
    veri = tara([repo])
    assert veri["ozet"]["kullanilmayan"] == 1
    assert len(tara([repo])["repolar"][0]["bulgular"]) == 1


# --------------------------------------------------------------------------
# Salt-okunurluk ve tarama sinirlari
# --------------------------------------------------------------------------


def test_tarama_diski_degistirmez(tmp_path):
    """SALT-OKUNUR: tara sonrasi dosya agaci BIRE BIR ayni."""
    repo = py_repo(tmp_path / "r", ["requests", "rich"], kaynak="import rich\n")
    once = tree_hash(repo)
    tara([repo])
    assert tree_hash(repo) == once, "olubag diske yazdi"


def test_node_modules_icine_girilmez(tmp_path):
    """node_modules icindeki kaynak taranmaz (bagimlilik agaci, proje kodu degil)."""
    repo = sahte_repo(
        tmp_path / "r",
        {
            "pyproject.toml": '[project]\ndependencies = ["requests"]\n',
            "app.py": "print('x')\n",
            "node_modules/paket/index.js": "const express = require('express');\n",
        },
    )
    assert turu(tara([repo]), "requests") == "kullanilmayan"


def test_bos_repo_bulgu_yok(tmp_path):
    """Bagimlilik bildirmeyen repo: bulgu yok (hata degil)."""
    repo = sahte_repo(tmp_path / "r", {"app.py": "print('x')\n"})
    assert tara([repo])["ozet"]["kullanilmayan"] == 0


def test_beyan_listesi_tum_paketleri_icerir(tmp_path):
    """beyan listesi tum bildirilen paketleri icerir (izinliler dahil)."""
    repo = py_repo(tmp_path / "r", ["requests", "pytest"], kaynak="import requests\n")
    assert tara([repo])["repolar"][0]["beyan"] == ["pytest", "requests"]