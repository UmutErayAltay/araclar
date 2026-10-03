"""devtemizle testleri icin ortak yardimcilar. Hicbir mock kutuphanesi yok.

Ag YOK: gercek git CALISTIRILMAZ (`.git` isaret dizini yeter), gercek disk
GECICI dizinlerde (tmp_path) silinir -- kullanici ~/kullanicinin gercek repolari
ve atlas DB'si hicbir testte okunmaz/yazilmaz.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

#: kesif bu tabloyu okur; atlas'in gercek semasi bu sutunlari icerir (fazlasi sutun zararsiz).
ATLAS_REPOS_SEMASI = (
    "CREATE TABLE repos (path TEXT PRIMARY KEY, name TEXT, scanned_at TEXT, "
    "dirty INTEGER, unpushed INTEGER, branch TEXT, last_commit_at TEXT, has_remote INTEGER)"
)

def sahte_repo(yol: Path, dosyalar: dict[str, str] | None = None, *, git: bool = True) -> Path:
    """Gercek git komutu CALISTIRMAZ: `.git` isaret dizini yeter.

    Silme testlerinin dis dunya dokunmadan calistigini kanitlamak icin
    `tree_hash` ile dosya agacinin hash'i alinir.
    """
    yol.mkdir(parents=True, exist_ok=True)
    if git:
        (yol / ".git").mkdir(exist_ok=True)
    for ad, icerik in (dosyalar or {}).items():
        hedef = yol / ad
        hedef.parent.mkdir(parents=True, exist_ok=True)
        hedef.write_text(icerik, encoding="utf-8")
    return yol


def sahte_aday(repo: Path, tur: str, *, bayt: int = 3, pyvenv_cfg: bool = False) -> Path:
    """repo altinda temizlenebilir bir aday dizini kurar.

    bayt: aday icindeki dosya boyutu (boslanacak bayt testleri icin).
    pyvenv_cfg: .venv/venv adayinda pyvenv.cfg yazilsin mi.
    """
    yol = repo / tur
    yol.mkdir(parents=True, exist_ok=True)
    if bayt:
        (yol / "paket.js").write_bytes(b"x" * bayt)
    if pyvenv_cfg:
        (yol / "pyvenv.cfg").write_text("home = C:/Python\n", encoding="utf-8")
    return yol


def sahte_aday_soyut(
    repo: Path, tur: str, *, yol: Path | None = None, boyut: int = 0, atlandi: str | None = None
) -> dict:
    """tara() ciktisi biciminde, bellekte uretilmis aday karti.

    tara sonucunu sahtelemek gereken sil testleri icin (orn. repo disina
    cozumlenen aday). Gercek dosya olusturulmaz.
    """
    return {
        "repo": str(repo),
        "yol": str(yol if yol is not None else repo / tur),
        "tur": tur,
        "boyut": boyut,
        "son_erisim": 0.0,
        "yas_gun": 99.0,
        "atlandi": atlandi,
    }


GUN = 86400.0


def eskit(yol: Path, gun: float, simdi: float | None = None) -> None:
    """Dizinin/dosyanin zaman damgalarini `gun` gunes eskider.

    Windows'ta atime yazmaz; mtime'i ATIME olarak da eskitiyoruz ki uygulama
    hangisini okusa da ayni yasi gorur (son erisim .git ile birlikte alinir).
    """
    simdi = time.time() if simdi is None else simdi
    zaman = simdi - gun * GUN
    os.utime(yol, (zaman, zaman))


def tree_hash(yol: Path) -> str:
    """Dizindeki tum dosyalarin (yol+icerik) sha256 toplami: silme etkisini olcer."""
    ozet = hashlib.sha256()
    for f in sorted(p for p in yol.rglob("*") if p.is_file() and not p.is_symlink()):
        ozet.update(str(f.relative_to(yol)).encode("utf-8"))
        ozet.update(b"\0")
        ozet.update(f.read_bytes())
        ozet.update(b"\0")
    return ozet.hexdigest()


def atlas_db_olustur(yol: Path, yollar: list[Path]) -> Path:
    """kesif'in okuyacagi `repos` tablosu olan gecici sqlite (satirlar yazilir)."""
    conn = sqlite3.connect(str(yol))
    try:
        conn.execute(ATLAS_REPOS_SEMASI)
        conn.executemany(
            "INSERT INTO repos (path, name) VALUES (?, ?)", [(str(p), p.name) for p in yollar]
        )
        conn.commit()
    finally:
        conn.close()
    return yol


def run_module_cli(
    *args: str, cwd: Path | str | None = None, env_ek: dict[str, str] | None = None
):
    """`python -m devtemizle ...` komutunu GERCEKTEN subprocess olarak calistirir.

    DEVTEMIZLE_DIR / ATLAS_DB varsayilanlari KULLANILMAZ: env once temizlenir,
    sonra testin yonlendirdigi degerler yazilir (kullanici raporu/atlas DB'si ezilmez).
    HOME da geciciye cevrilir: test unutsa bile ~/.devtemizle YAZILMAZ.
    """
    temel = cwd if isinstance(cwd, Path) else (Path(cwd) if cwd else REPO_ROOT)
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT)
    env.pop("ATLAS_DB", None)
    env.pop("DEVTEMIZLE_DIR", None)
    env["HOME"] = env["USERPROFILE"] = str(temel)
    env.update(env_ek or {})
    return subprocess.run(
        [sys.executable, "-m", "devtemizle", *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        env=env,
    )


def say(alan) -> int:
    """sil() sonucunun sayac alanini int'e cevirir (sayi ya da koleksiyon olabilir)."""
    if isinstance(alan, (list, tuple, set, dict)):
        return len(alan)
    return int(alan)


def nedenler(liste) -> list[str]:
    """'atlanan' / 'silinemedi' girdilerinden NEDEN METNI listesi cikarir.

    Uygulama her kaydi {"yol": ..., "neden": ...} sozlugu olarak yazar; testler
    kabut tipine degil neden METNINE bakar (sozlesme tipi sabitlemiyor).
    """
    return [
        str(girdi.get("neden")) if isinstance(girdi, dict) else str(girdi)
        for girdi in (liste or [])
    ]


@pytest.fixture
def ev_isole(tmp_path: Path, monkeypatch) -> Path:
    """HOME/USERPROFILE'u gecici dizine cevirir: ~/.devtemizle ve ~/.atlas YAZILMAZ.

    Ortam degiskenleri verilmediginde uygulama gercek kullanici dizinine
    duserdi; bu fixture olmadan bir CLI testi kullanicinin raporunu okuyabilirdi.
    """
    ev = tmp_path / "ev"
    ev.mkdir()
    for ad in ("HOME", "USERPROFILE"):
        monkeypatch.setenv(ad, str(ev))
    return ev


@pytest.fixture
def rapor_dizini(tmp_path: Path, monkeypatch) -> Path:
    """DEVTEMIZLE_DIR'i gecici dizine yonlendirir (kullanici dizini olusturulmaz)."""
    dizin = tmp_path / "raporlar"
    monkeypatch.setenv("DEVTEMIZLE_DIR", str(dizin))
    return dizin


@pytest.fixture
def symlink_kur(tmp_path: Path):
    """Dizin baglantisi (os.symlink) kuran fabrika; yetki yoksa testi ATLAR.

    Windows'ta symlink gelistirici modu/ yetkisi gerekir; yoksa sessizce
    gecmek yerine test atlanir.
    """
    deneme = tmp_path / "_deneme-baglanti"
    try:
        os.symlink(tmp_path, deneme, target_is_directory=True)
        deneme.unlink()
    except (OSError, NotImplementedError, AttributeError):
        pytest.skip("bu makinede os.symlink kullanilamiyor")

    def kur(hedef: Path, ad: str, *, ust: Path | None = None) -> Path:
        link = (ust or hedef.parent) / ad
        link.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(hedef, link, target_is_directory=True)
        return link

    return kur