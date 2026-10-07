"""Git/.gitignore tarafi: `env_gitignorede_degil` ve `env_izleniyor` icin.

Guvenlik: git SALT-OKUNUR calistirilir (`GIT_OPTIONAL_LOCKS=0`: index'i
kilitlemez, yazmaz). `git` yoksa ya da calisamazsa BULGU URETILMEZ — sessizce
bos liste doner; yanlis pozitif uretmektense yokluk tercih edilir.

`.env*` izi `git check-ignore` benzeri basit bir kural ile: `.gitignore`
satirlarinda `.env`, `.env*` ya da `*.env` kaliplarindan biri var mi?
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .tara import AZAMI_DOSYA, SKIP_DIRS, env_dosyasi_mi, temiz_yol

GIT_TIMEOUT = 60


def git_env() -> dict[str, str]:
    """Git'i yan etkisiz ve salt-okunur calistirmak icin ortam."""
    env = dict(os.environ)
    env["GIT_OPTIONAL_LOCKS"] = "0"  # index'i kilitlemez/yazmaz
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_ASKPASS"] = "echo"
    env["GIT_PAGER"] = "cat"
    env["LC_ALL"] = "C"
    return env


def _git(repo: Path, args: list[str]) -> str | None:
    """`git` komutunu calistirir; git yoksa/basarisizsa None (bulgu yok)."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=git_env(),
            timeout=GIT_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout if proc.returncode == 0 else None


#: `.gitignore`'da `.env` ailesini kapatan kaliplar.
_ENV_KALIPLARI = frozenset(
    {".env", ".env*", "*.env", "**/.env", "**/.env*", "**/*.env", "env", "env.*"}
)


def gitignore_env_kapsiyor_mi(repo: Path) -> bool:
    """`.gitignore` `.env`'i kapsiyor mu? (basit kural: `.env`, `.env*`, `*.env`)."""
    try:
        if (repo / ".gitignore").stat().st_size > AZAMI_DOSYA:
            return False
        icerik = (repo / ".gitignore").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    for satir in icerik.splitlines():
        satir = satir.strip()
        if not satir or satir.startswith("#"):
            continue
        if satir.rstrip("/") in _ENV_KALIPLARI:
            return True
    return False


def env_dosyasi_var_mi(repo: Path) -> list[str]:
    """Repoda YEREL `.env*` dosyalari var mi? (ornek/sablon HARIC) — yol listesi.

    Bu dosyalar deger icerir; icerikleri HIC okunmaz, yalniz yollari raporlanir.
    """
    repo = Path(repo)
    bulunan: list[str] = []
    for mevcut, dizinler, dosyalar in os.walk(
        repo, topdown=True, followlinks=False, onerror=lambda _e: None
    ):
        dizinler[:] = [d for d in dizinler if d not in SKIP_DIRS]
        for ad in dosyalar:
            if env_dosyasi_mi(ad):
                bulunan.append(temiz_yol(Path(mevcut, ad).relative_to(repo).as_posix()))
    return sorted(bulunan)


def izlenen_env_dosyalari(repo: Path) -> list[str]:
    """`git ls-files` icindeki GERCEK `.env` dosyalari (ornek olmayan).

    Sablonlar (`.env.example`) izlenmis olsa bile sorun DEGILDIR; bu yuzden
    yalniz `env_dosyasi_mi` ile eslesenler doner.
    """
    citir = _git(Path(repo), ["ls-files", "-z"])
    if citir is None:
        return []
    return sorted(temiz_yol(yol) for yol in citir.split("\0") if yol and env_dosyasi_mi(yol))
