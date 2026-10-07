"""tara: kaynak koddan ortam degiskeni KULLANIMI cikarimi (yalniz ad).

Her bulgu turu icin pozitif ve negatif test.
"""

from __future__ import annotations

from pathlib import Path

from conftest import GIZLI_DEGER, sahte_repo

from ortam import tara


def _adlar(bulgular: list[dict]) -> set[str]:
    return {b["ad"] for b in bulgular}


# --------------------------------------------------------------------------
# Python: os.environ["X"], os.environ.get("X"...), os.getenv("X"...)
# --------------------------------------------------------------------------


def test_python_uc_bicim(tmp_path):
    """Uc Python kullanim bicimi de taninir: [] , .get(), getenv()."""
    repo = sahte_repo(
        tmp_path / "r",
        {
            "a.py": 'API_KEY = os.environ["API_KEY"]\n'
            'DB_URL = os.environ.get("DB_URL", "")\n'
            'TOKEN = os.getenv("TOKEN")\n',
        },
    )
    atlandi: list[str] = []
    assert _adlar(tara.repo_tara(repo, atlandi)) == {"API_KEY", "DB_URL", "TOKEN"}


def test_python_bosluklu_yazim(tmp_path):
    """`os . environ [ "X" ]` bosluksuz yazilmis olsa da taninir."""
    repo = sahte_repo(tmp_path / "r", {"a.py": 'X = os . environ [ "BOSLUKLU" ]\n'})
    assert "BOSLUKLU" in _adlar(tara.repo_tara(repo, []))


def test_python_cok_satirli_cagri(tmp_path):
    """`os.environ.get(` sonraki satirdaki adi okur: bicimlendirici/kirilmis cagri.

    Bu kural olmadan kullanilan bir degisken `kullanilmayan` sanilirdi.
    """
    repo = sahte_repo(
        tmp_path / "r",
        {"a.py": 'x = os.environ.get(\n    "COK_SATIRLI"\n)\n'},
    )
    bulgu = tara.repo_tara(repo, [])[0]
    assert bulgu["ad"] == "COK_SATIRLI"
    assert bulgu["satir"] == 1  # cagrinin BASLADIGI satir


def test_python_negatif_yorum_disi_kod(tmp_path):
    """Yorum satirindan sonra gelen KOD satiri yine taranir (kayma yok)."""
    repo = sahte_repo(
        tmp_path / "r", {"a.py": '# os.environ["YORUMDA"]\ny = os.environ["GERCEKTE"]\n'}
    )
    assert _adlar(tara.repo_tara(repo, [])) == {"GERCEKTE"}


def test_python_satir_numarasi_dogru(tmp_path):
    """Bulgu gercek satir numarasini tasir (dosya:satir ciktisi icin)."""
    repo = sahte_repo(
        tmp_path / "r", {"a.py": "import os\n\nprint(1)\nX = os.getenv('ILK')\n"}
    )
    bulgu = tara.repo_tara(repo, [])[0]
    assert bulgu["ad"] == "ILK"
    assert bulgu["satir"] == 4
    assert bulgu["dosya"] == "a.py"


def test_python_negatif_yorum_satiri(tmp_path):
    """`# X = os.getenv("X")` bir YORUM: kullanim degildir."""
    repo = sahte_repo(tmp_path / "r", {"a.py": '# TOKEN = os.getenv("TOKEN")\n'})
    assert tara.repo_tara(repo, []) == []


def test_python_negatif_baska_dil_kurali(tmp_path):
    """Python dosyasinda `process.env.X` gecer ama Python kurali DEGILDIR."""
    repo = sahte_repo(tmp_path / "r", {"a.py": 'X = process.env["JS_ADI"]\n'})
    assert tara.repo_tara(repo, []) == []


# --------------------------------------------------------------------------
# JS/TS
# --------------------------------------------------------------------------


def test_js_noktali_ve_koseli(tmp_path):
    """`process.env.X` ve `process.env["X"]` ikisi de taninir."""
    repo = sahte_repo(
        tmp_path / "r", {"a.js": "const a = process.env.NOKTALI;\nconst b = process.env['KOSELI'];\n"}
    )
    assert _adlar(tara.repo_tara(repo, [])) == {"NOKTALI", "KOSELI"}


def test_ts_dosyasi_taranir(tmp_path):
    """.ts dosyalari da taranir (beyaz liste degil)."""
    repo = sahte_repo(tmp_path / "r", {"a.ts": "const x = process.env.TS_ADI;\n"})
    assert "TS_ADI" in _adlar(tara.repo_tara(repo, []))


def test_js_negatif_yorum_satiri(tmp_path):
    """`// const x = process.env.X` bir YORUM: kullanim degildir."""
    repo = sahte_repo(tmp_path / "r", {"a.js": '// const x = process.env.YORUMDA;\n'})
    assert tara.repo_tara(repo, []) == []


# --------------------------------------------------------------------------
# Go
# --------------------------------------------------------------------------


def test_go_getenv(tmp_path):
    """Go'da `os.Getenv("X")` taninir."""
    repo = sahte_repo(tmp_path / "r", {"a.go": 'x := os.Getenv("GO_ADI")\n'})
    assert _adlar(tara.repo_tara(repo, [])) == {"GO_ADI"}


def test_go_negatif_baska_dil(tmp_path):
    """Go dosyasinda `process.env.X` Go kurali DEGILDIR."""
    repo = sahte_repo(tmp_path / "r", {"a.go": 'x := process.env.X\n'})
    assert tara.repo_tara(repo, []) == []


# --------------------------------------------------------------------------
# Atlama kurallari
# --------------------------------------------------------------------------


def test_atlanan_dizinlere_girilmez(tmp_path):
    """node_modules/.venv/.git altindaki kaynak gorulmez."""
    repo = sahte_repo(tmp_path / "r")
    for atlanacak in ("node_modules", ".venv", "venv", ".git", "dist", "build", "__pycache__"):
        yol = repo / atlanacak
        yol.mkdir(parents=True, exist_ok=True)
        (yol / "a.py").write_text('x = os.getenv("GIZLI_AD")\n', encoding="utf-8")
    assert tara.repo_tara(repo, []) == []


def test_env_dosyasi_kaynak_olarak_taranmaz(tmp_path):
    """`.env` bir KAYNAK degildir: icindeki degerler hic okunmaz."""
    repo = sahte_repo(
        tmp_path / "r",
        {".env": f"KODDA_OLMAYAN={GIZLI_DEGER}\n", ".env.local": f"A={GIZLI_DEGER}\n"},
    )
    assert tara.repo_tara(repo, []) == []


def test_bir_mb_ustu_dosya_atlanir(tmp_path):
    """1 MB'den buyuk kaynak okunmaz, neden `atlanan` listesine yazilir."""
    repo = sahte_repo(tmp_path / "r")
    (repo / "buyuk.py").write_text(
        'x = os.getenv("X")\n' + "# " + "y" * tara.AZAMI_DOSYA, encoding="utf-8"
    )
    atlandi: list[str] = []
    assert tara.repo_tara(repo, atlandi) == []
    assert any("buyuk" in neden for neden in atlandi), atlandi


def test_ikili_dosya_atlanir(tmp_path):
    """NUL bayti iceren (ikili) dosya metin sayilmaz, okunmaz."""
    repo = sahte_repo(tmp_path / "r")
    (repo / "gorsel.py").write_bytes(b'\x89PNG\x00\x00\x00os.getenv("SAHTE")\n')
    assert tara.repo_tara(repo, []) == []


# --------------------------------------------------------------------------
# DEGER KURALI
# --------------------------------------------------------------------------


def test_deger_hicbir_ciktiya_girmez(tmp_path):
    """Kaynak satirinda bir DEGER olsa bile bulguda yalniz AD + dosya:satir vardir."""
    repo = sahte_repo(tmp_path / "r", {"a.py": f'X = os.environ["AD_ONLY"] or "{GIZLI_DEGER}"\n'})
    bulgu = tara.repo_tara(repo, [])[0]
    assert set(bulgu) == {"ad", "dosya", "satir"}
    assert GIZLI_DEGER not in repr(bulgu)


# --------------------------------------------------------------------------
# env_dosyasi_mi ayrimi
# --------------------------------------------------------------------------


def test_env_dosyasi_mi_ayrimi():
    """`.env`/`.env.production` izlenen; `.env.example`/`.sample` ornek sayilir."""
    for gercek in (".env", ".env.local", ".env.production", "backend/.env"):
        assert tara.env_dosyasi_mi(gercek), gercek
    for ornek in (".env.example", ".env.sample", ".env.template", ".env.ornek"):
        assert not tara.env_dosyasi_mi(ornek), ornek
