"""olubag testleri icin ortak yardimcilar. Hicbir mock kutuphanesi yok.

Ag YOK: gercek git CALISTIRILMAZ (`.git` isaret dizini yeter), tum dizin
agaci tmp_path altinda kurulur -- kullanicinin gercek repolari hicbir testte
okunmaz. Bu arac salt-okunur oldugu icin agac BIRE BIR ayni kalmalidir.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def sahte_repo(yol: Path, dosyalar: dict[str, str] | None = None, *, git: bool = True) -> Path:
    """Gercek git komutu CALISTIRILMAZ: `.git` isaret dizini yeter.

    Sagmalik (olubag hicbir sey yazmaz) testleri icin `tree_hash` ile agacin
    hash'i alinir.
    """
    yol.mkdir(parents=True, exist_ok=True)
    if git:
        (yol / ".git").mkdir(exist_ok=True)
    for ad, icerik in (dosyalar or {}).items():
        hedef = yol / ad
        hedef.parent.mkdir(parents=True, exist_ok=True)
        hedef.write_text(icerik, encoding="utf-8")
    return yol


def py_repo(yol: Path, bagimliliklar: list[str], *, kaynak: str = "", **dosyalar: str) -> Path:
    """[project].dependencies bildiren pyproject'li sahte Python projesi.

    kaynak: varsa `kaynak.py` olarak yazilir (import satiri taramasi icin).
    """
    govde = ['[project]', 'name = "r"', 'version = "0.1.0"']
    if bagimliliklar:
        govde.append("dependencies = [" + ", ".join(f'"{b}"' for b in bagimliliklar) + "]")
    dosyalar = dict(dosyalar)
    if kaynak:
        dosyalar["kaynak.py"] = kaynak
    return sahte_repo(yol, {"pyproject.toml": "\n".join(govde) + "\n", **dosyalar})


def js_repo(yol: Path, bagimliliklar: list[str], *, kaynak: str = "") -> Path:
    """dependencies bildiren package.json'lu sahte JS projesi."""
    govde = ['{', '  "name": "r",']
    if bagimliliklar:
        govde.append(
            '  "dependencies": {' + ", ".join(f'"{b}": "^1.0.0"' for b in bagimliliklar) + "}"
        )
    dosyalar = {"package.json": "\n".join(govde) + "\n}\n"}
    if kaynak:
        dosyalar["index.js"] = kaynak
    return sahte_repo(yol, dosyalar)


def turler(veri: dict, repo_adi: str | None = None) -> list[tuple[str, str, str]]:
    """(paket, tur, dosya:satir) ucluleri — sirali.

    Testler karti sozlugu TUTMAZ, sozlesmedeki alanlara bakar.
    """
    satirlar = []
    for r in veri["repolar"]:
        if repo_adi is not None and r["repo"].split("/")[-1] != repo_adi:
            continue
        for b in r["bulgular"]:
            satirlar.append((b["paket"], b["tur"], f"{b['dosya']}:{b['satir']}"))
    return sorted(satirlar)


def paketler(veri: dict, repo_adi: str | None = None) -> set[str]:
    return {p for p, _t, _c in turler(veri, repo_adi)}


def turu(veri: dict, paket: str, repo_adi: str | None = None) -> str | None:
    for ad, t, _c in turler(veri, repo_adi):
        if ad == paket:
            return t
    return None


def tree_hash(yol: Path) -> str:
    """Dizindeki tum dosyalarin (yol+icerik) sha256 toplami: salt-okunurluk olcumu."""
    ozet = hashlib.sha256()
    for f in sorted(p for p in yol.rglob("*") if p.is_file() and not p.is_symlink()):
        ozet.update(str(f.relative_to(yol)).encode("utf-8"))
        ozet.update(b"\0")
        ozet.update(f.read_bytes())
        ozet.update(b"\0")
    return ozet.hexdigest()


def run_module_cli(*args: str, cwd: Path | str | None = None, env_ek: dict[str, str] | None = None):
    """`python -m olubag ...` komutunu GERCEKTEN subprocess olarak calistirir.

    ATLAS_DB varsayilani KULLANILMAZ (env temizlenir): testin yonlendirdigi
    deger yazilir, kullanici atlas DB'si ezilmez/okunmaz.
    """
    temel = cwd if isinstance(cwd, Path) else (Path(cwd) if cwd else REPO_ROOT)
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT)
    env.pop("ATLAS_DB", None)
    env["HOME"] = env["USERPROFILE"] = str(temel)
    env.update(env_ek or {})
    return subprocess.run(
        [sys.executable, "-m", "olubag", *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        env=env,
    )


@pytest.fixture
def ev_isole(tmp_path: Path, monkeypatch) -> Path:
    """HOME/USERPROFILE'u gecici dizine cevirir: ~/.atlas YAZILMAZ/OKUNMAZ."""
    ev = tmp_path / "ev"
    ev.mkdir()
    for ad in ("HOME", "USERPROFILE"):
        monkeypatch.setenv(ad, str(ev))
    return ev