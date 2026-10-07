"""haftalik testleri icin ortak yardimcilar. Hicbir mock kutuphanesi yok.

Ag YOK (cor/Telegram cagrisi yapilmaz), gercek dis YOK: git repolari ve cikti
dosyalari YALNIZCA gecici dizinde (tmp_path) kurulur. Kullanicinin ~/klasoru
hicbir testte okunmaz veya yazilmaz.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Testlerde uretilen `DEGER` dizeleri sentinel gibi kullanilir; hicbir
#: cikti/test mesajinda gormemelidirler.
GIZLI_DEGER = "GIZLI_DEGER_0123456789_ABCDEFGHIJKL"


def git_kur(yol: Path) -> Path:
    """GECERLI ama bos bir git deposu kurar. `commit.gpgsign` kapali: testler
    imzaya takilip gecmesin."""
    yol.mkdir(parents=True, exist_ok=True)
    for args in (
        ["init", "-q", "-b", "main", "."],
        ["config", "user.email", "test@example.com"],
        ["config", "user.name", "Test"],
        ["config", "commit.gpgsign", "false"],
    ):
        subprocess.run(
            ["git", "-C", str(yol), *args], capture_output=True, check=True, timeout=60
        )
    return yol


def _tarih(gun_once: int) -> str:
    """`gun_once` gun once yerel saat, git'in anlayacagi ISO bicimde."""
    an = datetime.now(timezone.utc) - timedelta(days=gun_once)
    return an.strftime("%Y-%m-%dT%H:%M:%S%z")


def commit_yap(
    repo: Path,
    dosya: str,
    icerik: str,
    *,
    gun_once: int = 1,
    mesaj: str = "degisiklik",
    yazar: str = "Test",
) -> None:
    """Gercek `git commit` yapar; TARIHI `gun_once` gun onceye ayarlar.

    `GIT_AUTHOR_DATE` + `GIT_COMMITTER_DATE` verilir: `git log --since` commit
    TARIHINE gore filtreler ve varsayilan olarak commit tarihi (committer date)
    kullanilir.
    """
    hedef = repo / dosya
    hedef.parent.mkdir(parents=True, exist_ok=True)
    hedef.write_text(icerik, encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "--", dosya], capture_output=True,
                   check=True, timeout=60)
    env = dict(os.environ)
    env["GIT_AUTHOR_DATE"] = _tarih(gun_once)
    env["GIT_COMMITTER_DATE"] = _tarih(gun_once)
    env["GIT_AUTHOR_NAME"] = yazar
    env["GIT_AUTHOR_EMAIL"] = f"{yazar}@example.com"
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", mesaj],
        capture_output=True, check=True, env=env, timeout=60,
    )


def repo_gun_icin(yol: Path, gun: int = 1, adet: int = 3, mesaj_onek: str = "is") -> Path:
    """Son `gun` gun icinde `adet` commit'i olan gercek bir repo kurar."""
    repo = git_kur(yol)
    for i in range(adet):
        commit_yap(
            repo, f"dosya{i}.txt", f"icerik {i}\n",
            gun_once=gun if i == 0 else gun + i,
            mesaj=f"{mesaj_onek} {i}",
        )
    return repo


class SahteIstemci:
    """`llm.CorLLMClient` yerine gecen sahte istemci (gercek ag YOK).

    `LLMError` verilen bir yanit, tam olarak cor'un firlattigi hatayi taklit eder.
    """

    def __init__(self, yanit: str | Exception = "SAHTE OZET"):
        self.yanit = yanit
        self.istemler: list[str] = []

    def complete(self, prompt: str) -> str:
        self.istemler.append(prompt)
        if isinstance(self.yanit, Exception):
            raise self.yanit
        return self.yanit


@pytest.fixture
def sahte_llm(monkeypatch: pytest.MonkeyPatch):
    """llm modulundeki istemci sinifini sahte ile degistirir; uretilen istemciyi dondurur."""
    def kur(yanit: str | Exception = "SAHTE OZET") -> SahteIstemci:
        istemci = SahteIstemci(yanit)
        monkeypatch.setattr(
            "haftalik.llm.CorLLMClient", lambda *a, **k: istemci, raising=True
        )
        return istemci
    return kur


@pytest.fixture
def telegram_yok(monkeypatch: pytest.MonkeyPatch) -> None:
    """Telegram ortam degiskenlerini temizler: test unutsa bile gercek hesap
    kullanilmaz."""
    monkeypatch.delenv("HAFTALIK_TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("HAFTALIK_TELEGRAM_CHAT_ID", raising=False)


def run_cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """`python -m haftalik ...` komutunu GERCEKTEN subprocess olarak calistirir.

    Cor/Telegram ortam degiskenleri ONCEDEN temizlenir: test unutsa bile kullanici
    gercegi calistirilmez. Yine de yalniz gecici dizinler uzerinde calisir.

    DIKKAT: alt surec oldugu icin `sahte_llm` fixture'si BURAYA ETKI ETMEZ.
    Sahte LLM gerektiren testler `run_cli_yerel`'i kullanir.
    """
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT)
    env.pop("COR_BASE_URL", None)
    env.pop("COR_MODEL", None)
    env.pop("HAFTALIK_TELEGRAM_BOT_TOKEN", None)
    env.pop("HAFTALIK_TELEGRAM_CHAT_ID", None)
    return subprocess.run(
        [sys.executable, "-m", "haftalik", *args],
        capture_output=True, text=True, env=env,
        cwd=str(cwd) if cwd else None, timeout=60,
    )


class Sonuc:
    """`run_cli_yerel`'in dondurdugu, `run_cli` ile ayni alanlara sahip sonuc."""

    def __init__(self, returncode: int, stdout: str, stderr: str) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

    def __repr__(self) -> str:
        return f"Sonuc({self.returncode}, stdout={self.stdout!r}, stderr={self.stderr!r})"


def run_cli_yerel(*args: str) -> Sonuc:
    """CLI'yi AYNI surec icinde calistirir; stdout/stderr yakalanir.

    `argparse` hatada `SystemExit` firlatir; burada yakalanip cikis kodu doner
    (ayni sekilde `main` traceback basilmadan `Hata: ...` yazar).
    Boylece `sahte_llm` fixture'si (in-process monkeypatch) ETKILI olur.
    """
    import contextlib
    import io

    from haftalik.cli import main

    out, err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            kod = main(list(args))
    except SystemExit as exc:  # argparse kullanim hatasi
        kod = exc.code if isinstance(exc.code, int) else 2
    return Sonuc(kod, out.getvalue(), err.getvalue())
