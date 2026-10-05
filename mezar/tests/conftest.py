"""mezar testleri icin ortak yardimcilar. Hicbir mock kutuphanesi yok.

Ag YOK: gercek `git` komutlari CALISTIRILIR ama YALNIZCA gecici dizinlerde
(tmp_path) -- kullanici ~/kullanicinin gercek repolari hicbir testte
okunmaz/yazilmaz. Uzak olarak da gecici `bare` depo kullanilir; ag adresi
`file://` yerine YEREL yoldur, hicbir ag erisimi olmaz.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

#: `_benzersiz_gecici()` ile uretilen dizinler, modul yasam boyu tutulur.
_GECICI_DIZINLER: list[tempfile.TemporaryDirectory] = []

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Gercek git'in kullanici kimligi: test ortaminda kullanici adi ayarli
#: olmayabilir, bu yuzden commit'lerin KENDIMIZ adina olmasini garanti ederiz.
GIT_KIMLIK = (
    "-c", "user.name=mezar test",
    "-c", "user.email=test@localhost",
    "-c", "commit.gpgsign=false",
    "-c", "init.defaultBranch=main",
)


def git(repo: Path, *args: str) -> str:
    """`git -C repo ...` calistirir; hata durumunda test KIRILIR (beklenmedik)."""
    proc = subprocess.run(
        ["git", "-C", str(repo), *GIT_KIMLIK, *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
    )
    if proc.returncode != 0:
        raise AssertionError(f"git {args} basarisiz: {proc.stderr.strip()}")
    return proc.stdout


def yaz(yol: Path, icerik: str) -> Path:
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(icerik, encoding="utf-8")
    return yol


def mezar_tasi_repo(
    kok: Path,
    ad: str,
    dosyalar: dict[str, str] | None = None,
    *,
    bosalt: bool = True,
) -> Path:
    """Gercek bir git reposu kurar: once dosyalarla commit, sonra bosaltma commit'i.

    `dosyalar`: bosaltma ONCESI repoda olan dosyalar (bunlar HEAD~1'in listesidir).
    `bosalt=False`: bosaltma commit'i YAPILMAZ (HEAD~1 = son icerik commit'i).
    Bosaltmadan sonra calisma agacinda yalniz `README.md` kalir.
    """
    repo = kok / ad
    repo.mkdir(parents=True, exist_ok=True)
    git(repo, "init", "-q")
    for yol, icerik in (dosyalar or {}).items():
        yaz(repo / yol, icerik)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "ilk icerik")
    if bosalt:
        for yol in (dosyalar or {}):
            (repo / yol).unlink()
        yaz(repo / "README.md", "# arsivlendi\n")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "mezar tasi: icerik tasindi")
    return repo


def hedef_kopyala(arac_repo: Path, ad: str, dosyalar: dict[str, str]) -> Path:
    """`<arac-repo>/<ad>/` altina dosyalari kopyalar (tasinan kodun yeni yeri)."""
    hedef = arac_repo / ad
    for yol, icerik in dosyalar.items():
        yaz(hedef / yol, icerik)
    return hedef


def bare_uzak(kok: Path, ad: str) -> Path:
    """Yerel `bare` uzak depo olusturur (AG YOK: dosya yolu, dos:// degil)."""
    uzak = kok / f"{ad}-uzak.git"
    subprocess.run(
        ["git", "init", "-q", "--bare", str(uzak)], capture_output=True, text=True, timeout=60,
        check=True,
    )
    return uzak


def uzak_ekle_ve_gonder(repo: Path, uzak: Path, ad: str = "origin") -> None:
    """Repoya uzak ekler ve GONDERIR (test KAPATILABILIR yolunu kurmak icin).

    Bu BIR test ortami kurulumudur, aracin davranisi degil: `mezar` hicbir
    yerde push CALISTIRMAZ.
    """
    git(repo, "remote", "add", ad, str(uzak))
    git(repo, "push", "-q", "-u", ad, "HEAD:refs/heads/main")


def ortam(kok: Path) -> dict[str, str]:
    """CLI alt surecine verilecek izole ortam (HOME gecici: kullanicinin
    tuzu/anahtarlik dizini ASLA yazilmaz).

    Yalniz `kok` GECICI bir dizin oldugunda ev yolunu oraya kurar; `kok` proje
    koku ise oyun geri kazanilir olamaz, bu yuzden o zaman ev de gecicidir.
    """
    gecici = _tmp_path_mi(kok)
    ev = (kok if gecici else None) or _benzersiz_gecici()
    ev.mkdir(parents=True, exist_ok=True)
    return {
        "PYTHONPATH": str(REPO_ROOT),
        "HOME": str(ev),
        "USERPROFILE": str(ev),
        # `parmak.tuz()` anahtarlik'in kendi dizininde tuz arar; geciciye yonlendir.
        "ANAHTARLIK_DIR": str(ev / ".anahtarlik"),
    }


def _tmp_path_mi(yol: Path) -> bool:
    """`yol`, pytest'in `tmp_path` agacinin altinda mi? (otomatik temizlenir)"""
    return "pytest-of-" in yol.parts


def _benzersiz_gecici() -> Path:
    """`tmp_path` disinda kalan durumlar icin ayri gecici dizin.

    `TemporaryDirectory` nesnesi global bir KAYITTA tutulur: yoksayilirsa
    nesne yok edilir ve dizin ANINDA silinir, alt surec kullanmadan once.
    """
    gecici = tempfile.TemporaryDirectory(prefix="mezar-test-")
    _GECICI_DIZINLER.append(gecici)
    return Path(gecici.name)


def run_cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    """`python -m mezar ...` komutunu GERCEKTEN subprocess olarak calistirir."""
    return subprocess.run(
        [sys.executable, "-m", "mezar", *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(cwd) if cwd else None,
        env={**os.environ, **ortam(cwd or REPO_ROOT)},
        timeout=120,
    )