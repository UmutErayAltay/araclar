"""Toplama: repolardaki son N gunun commit'lerini SALT-OKUNUR okur.

Güvenlik:
  * Git alt süreçleri `shell=False` argüman listesiyle çağrılır.
  * `GIT_OPTIONAL_LOCKS=0`: git index'i kilitlemez/yazmaz.
  * Sadece `git log` (okuma). Hiçbir dosya değiştirilmez.
  * Bir repo okunamazsa (git yok, çöktü, izin yok) o repo ATLANIR ve sessizce
    "commit yok" sayılmaz.
  * TARİH FİLTRESİ PYTHON'DA YAPILIR, `git --since` ile DEĞİL. Git `--since`
    geçmişte ilerlerken pencere dışına ilk çıktığı commit'te DALLARI KESER: HEAD'i
    eski olan bir repoda, HEAD üzerinden erişilebilen tüm yeni commit'ler sessizce
    kaybolurdu. `--all` bunu çözmez (yalnız HEAD'e işaret eden dal varsa). Bu yüzden
    log sınırsız alınır, `commit date`'e göre burada süzülür.
  * Aşırı büyük repoda `MAKS_COMMIT` sınırı devreye girer ve SINIR DOLDUĞU
    bildirilir — sessiz kırpma yapılmaz.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

GIT_TIMEOUT = 60

#: Repo başına en çok okunacak commit satırı (aşırı büyük repoda bellek/corrupt koruması).
#: Dolduğunda `RepoOzeti.sinir_doldu` True olur ve özet bunu belirtir.
MAKS_COMMIT = 2000

#: `--shortstat` satırındaki "3 files changed, 12 insertions(+), 4 deletions(-)" deseni.
_SHORTSTAT_RE = re.compile(r"(\d+) files? changed(?:, (\d+) insertions?\(\+\))?(?:, (\d+) deletions?\(-\))?")


class RepoHatasi(Exception):
    """Verilen kok/repo okunamadi (kullanim hatasi)."""


@dataclass
class Commit:
    """Tek bir commit satırı (ham log'dan ayrıştırılmış)."""

    kisa: str
    yazar: str
    tarih: str
    konu: str
    eklenen: int = 0
    silinen: int = 0


@dataclass
class RepoOzeti:
    """Bir repoda tek bir pencere içindeki commit özeti."""

    yol: Path
    ad: str
    commitler: list[Commit] = field(default_factory=list)
    eklenen: int = 0
    silinen: int = 0
    sinir_doldu: bool = False

    @property
    def adet(self) -> int:
        return len(self.commitler)

    @property
    def aktif(self) -> bool:
        """Pencere içinde en az bir commit'i var mı?"""
        return bool(self.commitler)


def git_env() -> dict[str, str]:
    """Git'i yan etkisiz ve salt-okunur çalıştırmak için ortam."""
    env = dict(os.environ)
    env["GIT_OPTIONAL_LOCKS"] = "0"  # index'i kilitlemez/yazmaz
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_ASKPASS"] = "echo"
    env["GIT_PAGER"] = "cat"
    env["LC_ALL"] = "C"
    return env


def _git(repo: Path, args: list[str]) -> subprocess.CompletedProcess[str] | None:
    """`git -C repo ...` çalıştırır; git yoksa/çökerse None."""
    try:
        return subprocess.run(
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


def _log_bicim(gun: int) -> str:
    """`git --since` argümanı.

    Git tarih çözümlemesi İngilizce anahtar sözcüklerle çalışır; "gün önce" Türkçe
    yazılırsa git bunu YANLIŞ çözer ve pencere BOŞ kalır (sessiz yanlış sonuç).
    Bu yüzden komut satırına İngilizce "N days ago" verilir, kullanıcıya gösterilen
    metin Türkçedir.
    """
    return f"{gun} days ago"


def repo_bulgulari(kok: Path) -> list[Path]:
    """`kok` bir repo ise [kok]; değilse altındaki repolar (derinlik 3, içine girmez)."""
    kok = Path(kok)
    if not kok.exists():
        raise RepoHatasi(f"verilen yol bulunamadı: {kok}")
    if (kok / ".git").exists():
        return [kok]
    if not kok.is_dir():
        raise RepoHatasi(f"verilen yol dizin değil ve repo değil: {kok}")

    SKIP = frozenset({".git", "node_modules", "__pycache__", ".venv", "venv", ".pytest_cache"})
    DERINLIK = 3
    bulunan: list[Path] = []
    for mevcut, dizinler, _dosyalar in os.walk(
        kok, topdown=True, followlinks=False, onerror=lambda _e: None
    ):
        dizinler[:] = sorted(d for d in dizinler if d not in SKIP)
        yol = Path(mevcut)
        if (yol / ".git").exists():
            bulunan.append(yol)
            dizinler[:] = []  # repo içine inme
            continue
        if len(yol.relative_to(kok).parts) >= DERINLIK:
            dizinler[:] = []
    return bulunan


def _satirlari_ciz(
    proc: subprocess.CompletedProcess[str], gun: int
) -> tuple[list[Commit], bool]:
    """`git log --pretty=format:... --shortstat` çıktısını commit'lere çevirir.

    Pencere `(bugün - gun gün, bugün]` içindeki commit'ler kalır; filtre `commit date`
    (committer) üzerinden yapılır.

    Returns:
        (penceredeki commit'ler, `-n MAKS_COMMIT` sınırı dolduğu için liste
        kırpılmış olabilir mi)
    """
    esik = date.today() - timedelta(days=gun)
    commitler: list[Commit] = []
    sinir_doldu = False
    for ham in proc.stdout.splitlines():
        satir = ham.strip()
        if not satir:
            continue
        if satir.startswith("==="):
            # "===<kisa>|<yazar>|<yazar tarihi>|<commit tarihi>|<konu>"
            # Konu '|' içerebilir; ilk 4'e bölünür.
            parcalar = satir[3:].split("|", 4)
            if len(parcalar) < 5:
                continue
            kisa, yazar, yazar_tarih, commit_tarih, konu = parcalar
            try:
                commit_gun = date.fromisoformat(commit_tarih)
            except ValueError:
                continue  # okunamayan tarih: veri bozuk, atlanır
            if commit_gun <= esik:
                continue  # pencere dışı
            commitler.append(
                Commit(kisa=kisa, yazar=yazar, tarih=yazar_tarih, konu=konu)
            )
            if len(commitler) >= MAKS_COMMIT:
                sinir_doldu = True
            continue
        # --shortstat satırı: en son commit'in eklenen/silinenini topla
        if commitler:
            es = _SHORTSTAT_RE.search(satir)
            if es:
                commitler[-1].eklenen += int(es.group(2) or 0)
                commitler[-1].silinen += int(es.group(3) or 0)
    return commitler, sinir_doldu


def repo_ozeti(repo: Path, gun: int) -> RepoOzeti | None:
    """Son `gun` günün commit'lerini okur; git yoksa/boşsa None (commit yok demektir)."""
    repo = Path(repo)
    proc = _git(repo, [
        "log",
        "--all",
        "--no-merges",
        "--shortstat",
        "-n", str(MAKS_COMMIT),
        "--date=short",
        "--pretty=format:===%h|%an|%ad|%cd|%s",
    ])
    if proc is None or proc.returncode != 0:
        return None
    commitler, sinir_doldu = _satirlari_ciz(proc, gun)
    if not commitler:
        return None
    return RepoOzeti(
        yol=repo,
        ad=repo.name,
        commitler=commitler,
        eklenen=sum(c.eklenen for c in commitler),
        silinen=sum(c.silinen for c in commitler),
        sinir_doldu=sinir_doldu,
    )


def topla(kokler: list[Path], gun: int) -> list[RepoOzeti]:
    """Verilen köklerin altındaki TÜM repolarda son `gun` günü toplar.

    Commit'i olmayan repo listede YOKTUR (istem yalnız aktif repoları görür).
    Aynı repo iki kökte de geçerse bir kez sayılır.
    """
    if gun < 1:
        raise RepoHatasi(f"--gun en az 1 olmalı: {gun}")

    gorulen: list[Path] = []
    for kok in kokler:
        for repo in repo_bulgulari(Path(kok)):
            if repo not in gorulen:
                gorulen.append(repo)

    ozetler: list[RepoOzeti] = []
    for repo in gorulen:
        ozet = repo_ozeti(repo, gun)
        if ozet is not None and ozet.aktif:
            ozetler.append(ozet)
    return ozetler


def tarih_araligi(gun: int, bugun: date | None = None) -> tuple[str, str]:
    """(bugün, bugün-gun) gün sayısını 'YYYY-MM-DD..YYYY-MM-DD' biçiminde verir."""
    bugun = bugun or date.today()
    return (bugun - timedelta(days=gun)).isoformat(), bugun.isoformat()
