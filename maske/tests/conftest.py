"""maske testleri icin ortak yardimcilar. Hicbir mock kutuphanesi yok.

Ag YOK. Gercek git CALISTIRILMAZ (`.git` isaret dizini yeter), gercek disk
GECICI dizinlerde (tmp_path) kurulur -- kullanici ~/kullanicinin gercek
repolari hicbir testte okunmaz/yazilmaz.

DEPO KURALLARI: hicbir test maske/ agacina yazmaz. Parmak izi tuzu kullanici
veri dizinindedir (`MASKE_TUZ_DIZINI`, yoksa `~/.maske/`) -- alt surecler
icinde de geciciye yonlendirilir. `test_hicbir_test_repo_yazmaz` bunu ispatlar.

YAPAY secret'lar `SENTINEL` isareti tasir: ham halleri hicbir ciktida gecmemeli.
"""

from __future__ import annotations

import atexit
import hashlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

#: `cwd` verilmediginde alt sureclerin calistigi ve TUZun yazildigi gecici
#: dizin. Modul yuklenirken bir kez kurulur, sure sonunda silinir. Boylece
#: `run_module_cli()` hicbir parametre aldiginda bile repo govdesi yazma alani
#: OLMAZ (eski varsayilan REPO_ROOT idi ve tuzu depo icine yaziyordu).
_GECICI = Path(tempfile.mkdtemp(prefix="maske-test-"))
atexit.register(lambda: __import__("shutil").rmtree(_GECICI, ignore_errors=True))

#: `anahtarlik` tespit desenlerinin yakalayacagi yapay degerler.
GIZLI_SK = "sk-SENTINEL8fHq2Lp9Zx4Wq7Nb3"
GIZLI_AWS = "AKIA4T2LQ9ZKXB8WCMZP"
GIZLI_GH = "ghp_SENTINEL9dQw4ErTy8UiOp1AsDfGhJkL7zXcVb"
GIZLI_SIFRE = "SENTINEL4xKq9wZmT2vBn7Lp"
#: Acikca sahte isaretli: bulgu OLMAMALI.
SAHTE_AWS = "AKIAIOSFODNN7EXAMPLE"


def repo_kur(kok: Path, dosyalar: dict[str, str] | None = None, *, git: bool = True) -> Path:
    """Gecici bir repo + dosyalar kurar (`git=True` ise `.git` isaret dizini).

    Icerik `str` ise LF, `bytes` ise OLDUGU GIBI yazilir (CRLF testi icin).
    """
    kok.mkdir(parents=True, exist_ok=True)
    if git:
        (kok / ".git").mkdir(exist_ok=True)
    for ad, icerik in (dosyalar or {}).items():
        hedef = kok / ad
        hedef.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(icerik, bytes):
            hedef.write_bytes(icerik)
        else:
            hedef.write_text(icerik, encoding="utf-8")
    return kok


def tree_hash(yol: Path) -> str:
    """Dosya agacinin (yol+icerik) sha256 toplami: yazma etkisini olcer."""
    ozet = hashlib.sha256()
    for f in sorted(p for p in yol.rglob("*") if p.is_file() and not p.is_symlink()):
        ozet.update(str(f.relative_to(yol)).encode("utf-8"))
        ozet.update(b"\0")
        ozet.update(f.read_bytes())
        ozet.update(b"\0")
    return ozet.hexdigest()


def run_module_cli(
    *args: str,
    cwd: Path | str | None = None,
    env_ek: dict[str, str] | None = None,
    tuz_dizini: Path | str | None = None,
):
    """`python -m maske ...` komutunu GERCEKTEN subprocess olarak calistirir.

    TuZ (parmak izi tuzu) ve HOME geciciye yonlendirilir: test unutsa bile ne
    gercek ev NE DEPO yazilir. `cwd` verilmezse calisma dizini de gecictir --
    repo govdesi hicbir testte yan etki alani degildir (bkz.
    `test_hiçbir_test_repo_yazmaz`). `maske/__init__.py` kardes dizini kendisi
    ekledigi icin PYTHONPATH yeterlidir.
    """
    gecici = Path(cwd) if cwd is not None else _GECICI
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT)
    env.pop("ANAHTARLIK_DIR", None)
    env.pop("MASKE_TUZ_DIZINI", None)
    env["HOME"] = env["USERPROFILE"] = str(gecici)
    # Kullanici veri dizini = gecici tuz. `ANAHTARLIK_DIR` de ayni yere
    # yazilir: maske `tuz.hazirla()` ile bunu zaten kendisi yapar, ama test
    # unutsa bile guvence bu satir.
    env["MASKE_TUZ_DIZINI"] = env["ANAHTARLIK_DIR"] = str(
        Path(tuz_dizini) if tuz_dizini is not None else gecici / ".maske"
    )
    env.update(env_ek or {})
    return subprocess.run(
        [sys.executable, "-m", "maske", *args],
        cwd=str(gecici),
        capture_output=True,
        text=True,
        env=env,
    )


@pytest.fixture
def ev_isole(tmp_path: Path, monkeypatch) -> Path:
    """HOME/USERPROFILE ve tuz dizinini geciciye cevirir: gercek ev YAZILMAZ."""
    ev = tmp_path / "ev"
    ev.mkdir()
    for ad in ("HOME", "USERPROFILE"):
        monkeypatch.setenv(ad, str(ev))
    monkeypatch.setenv("MASKE_TUZ_DIZINI", str(ev / ".maske"))
    monkeypatch.setenv("ANAHTARLIK_DIR", str(ev / ".maske"))
    return ev