"""Git'e salt okunur erisim: `git -C <repo> <args>` sarmalayici.

Kural: bu modul YALNIZCA OKUR. `push`, `fetch`, `pull`, `remote add` gibi ag ya
da uzak degistiren komutlar HICBIR YERDE cagrilmaz; cagiranlar da yalnizca
`ls-tree`, `rev-list`, `status`, `log`, `rev-parse` gibi okuma komutlari gecirir.

Git yoksa veya calistirilamiyorsa `KesifHatasi` firlatilir; CLI bunu `Hata: ...`
olarak stderr'e yazar (traceback YOK), cikis kodu 2.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

#: Tek bir git komutunun beklenecegi azami sure (sn). Sonsuza kadar asili kalan
#: git, araci kilitler; sinir dolunca kesilip kullaniciya yol verilir.
GIT_ZAMAN_ASIMI = 30


class KesifHatasi(RuntimeError):
    """Kullanim/kesif hatasi: eksik yol, git deposu degil, git calismadi."""


def _calistir(repo: Path, args: list[str], *, sessiz: bool = False) -> str | None:
    """`git -C repo args` calistirir, STDOUT metnini dondurur.

    `sessiz=True` ise "bu bilgi YOK" durumu HATA DEGILDIR: komut cozulemediginde
    `None` doner (`rev-parse @{upstream}`, `origin/main` gibi KOSULLU sorgular
    olmayan bir referansta sessizce basarisiz olur -- bu bir ortam hatasi degil).

    Ortam hatasi (git yok, calistirilamiyor, zaman asimi) `sessiz` olsa bile
    `KesifHatasi` firlatir: sessizce gecilmez.

    Git'in kendi HATA METNI hicbir yere girmez; yalniz komut adi kullanilir.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=GIT_ZAMAN_ASIMI,
        )
    except FileNotFoundError:
        raise KesifHatasi("git bulunamadi (PATH'te 'git' yok)") from None
    except subprocess.TimeoutExpired:
        raise KesifHatasi(f"git zaman asimina ugradi: {args[0]}") from None
    except (OSError, subprocess.SubprocessError):
        raise KesifHatasi(f"git calistirilamadi: {args[0]}") from None
    if proc.returncode != 0:
        if sessiz:
            return None
        raise KesifHatasi(f"git komutu basarisiz: {args[0]}")
    return proc.stdout


def repo_mi(yol: Path) -> bool:
    """Dizin bir git deposu mu? (YALNIZCA var olma kontrolu, git calistirmaz)."""
    return (yol / ".git").exists()


def repo_coz(ad: str, kok: Path) -> Path:
    """`--repo <ad>` -> `<kok>/<ad>` yolunu dogrular.

    Kullanim hatasi: kok dizin yok, ad bos, `<kok>/<ad>` dizin degil veya git
    deposu degil. Hepsi `KesifHatasi` -> cikis kodu 2.
    """
    if not ad or ad.strip() != ad or ad in (".", ".."):
        raise KesifHatasi(f"gecersiz repo adi: {ad!r}")
    if not kok.is_dir():
        raise KesifHatasi(f"--kok bulunamadi: {kok}")
    yol = kok / ad
    if not yol.is_dir():
        raise KesifHatasi(f"repo dizini yok: {yol}")
    if not repo_mi(yol):
        raise KesifHatasi(f"git deposu degil: {yol}")
    return yol


def arac_hedefi(arac_repo: Path, ad: str) -> Path:
    """Tasinan kodun yeni yeri: `<arac-repo>/<ad>/`."""
    if not arac_repo.is_dir():
        raise KesifHatasi(f"--arac-repo bulunamadi: {arac_repo}")
    return arac_repo / ad


def sorgu(repo: Path, args: list[str]) -> str:
    """Okuma komutu calistirir; hata durumunda `KesifHatasi` firlatir."""
    return _calistir(repo, args) or ""


def sorgu_yoksa(repo: Path, args: list[str]) -> str | None:
    """KOSULLU sorgu: referans/cozumleme yoksa `None` doner, hata firlatmaz.

    Ortam hatasi (git yok) yine `KesifHatasi` firlatir.
    """
    return _calistir(repo, args, sessiz=True) or None


def kisa_hash(repo: Path, revizyon: str) -> str | None:
    """`revizyon`u kisaltilmis commit hash'ine cevirir; cozemezse `None`."""
    ham = sorgu_yoksa(repo, ["rev-parse", "--short", revizyon])
    return ham.strip().splitlines()[0].strip() if ham and ham.strip() else None


def ls_tree(repo: Path, revizyon: str) -> list[str] | None:
    """`git ls-tree -r --name-only <rev>` dosya listesi; cozemezse `None`."""
    ham = sorgu_yoksa(repo, ["ls-tree", "-r", "--name-only", revizyon])
    if ham is None:
        return None
    return [satir.strip() for satir in ham.splitlines() if satir.strip()]