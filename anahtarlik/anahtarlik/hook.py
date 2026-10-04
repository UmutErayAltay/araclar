"""Git pre-push hook: push ONCESI eklenen satirlari tarar.

BAYAT KURALI: HAM SIR HICBIR YERE CIKMAZ. Bu modul bulgulari yalnizca
`dosya:satir tur` ve `[maskeli:<tur>]` biciminde uretir. Git ciktisi (diff)
modul ICINDE kalir; hicbir exception mesajina girmez.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import IO, Sequence

from . import desen

__all__ = [
    "HOOK_ICERIK",
    "HOOK_ISARETI",
    "tara_push",
    "kur",
    "hook_tara_main",
    "GitHata",
]

GIT_TIMEOUT = 120

#: Pre-push betiginin 2. satiri: idempotentlik ve yabanci hook korumasi icin.
HOOK_ISARETI = "# anahtarlik-hook v1"

#: `kur()` bu isareti betigin PYTHONPATH satiriyla degistirir: modul, deponun
#: USTUNDEKI dizinden bulunur. `-P` (3.11+) bulunulan dizini sys.path'ten
#: cikarir; `-I` kullanilamaz, cunku o PYTHONPATH'yi de yok sayar.
YOL_ISARETI = "@ANAHTARLIK_YOLU@"

#: Git'in bize verdigi referans satiri:
#: `local_ref local_sha remote_ref remote_sha`
_PUSH_UYARI = (
    "anahtarlik: push ENGELLENDI - asagidaki satirlarda gizli anahtar "
    "izlenimi var (dosya:satir tur). Degerler raporda GOSTERILMEZ. "
    "Gecici olarak atlamak icin: git push --no-verify"
)

HOOK_ICERIK = f"""#!/bin/sh
{HOOK_ISARETI}
# Git pre-push hook. stdin'den "local_ref local_sha remote_ref remote_sha"
# satirlarini okur, eklenen satirlari tarar, bulgu varsa cikis kodu 1 doner.
#
# GUVENLIK: modul DEPO KOKUNDEN degil, asagidaki mutlak yoldan yuklenir.
# `python -m` bulunulan dizini sys.path'in BASINA koyar; kotu niyetli bir
# depoda `anahtarlik/` klasoru olsa kod calistirilirdi. `-P` bunu kapatir.
# (Modul `pip install` ile kuruluysa bu satir gereksizdir, zararsizdir.)
export PYTHONPATH='{YOL_ISARETI}'
export PYTHONSAFEPATH=1

for _py in python python3; do
  if command -v "$_py" >/dev/null 2>&1; then
    "$_py" -P -m anahtarlik hook-tara
    exit $?
  fi
done
if command -v py >/dev/null 2>&1; then
  py -3 -P -m anahtarlik hook-tara
  exit $?
fi

echo "anahtarlik: python bulunamadi - push taranmadan gonderildi (koruma KAPALI)." >&2
exit 0
"""


class GitHata(RuntimeError):
    """Git komutu calistirilamadi veya basarisiz oldu."""


def git_env() -> dict[str, str]:
    """Git'i yan etkisiz ve salt-okunur calistirmak icin ortam."""
    env = dict(os.environ)
    env["GIT_OPTIONAL_LOCKS"] = "0"
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_ASKPASS"] = "echo"
    env["GIT_PAGER"] = "cat"
    env["LC_ALL"] = "C"
    env["GIT_ADVICE"] = "0"
    return env


def _git(repo: Path, args: Sequence[str]) -> str:
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
    except (OSError, subprocess.SubprocessError) as exc:
        # Ham diff ciktisi `exc` icinde OLABILIR: mesaj ASLA git ciktisini
        # tasimaz, sadece komut ve hata turu yazilir.
        raise GitHata(f"git {' '.join(args[:2])} calistirilamadi: {exc.__class__.__name__}") from None
    if proc.returncode != 0:
        raise GitHata(f"git {' '.join(args[:2])} basarisiz (kod {proc.returncode})")
    return proc.stdout


# --------------------------------------------------------------------------
# DIFF ayristirma
# --------------------------------------------------------------------------

_SIFIR_SHA = re.compile(r"\A0{4,}\Z")
_HUNK = re.compile(r"^@@+ (?:-\d+(?:,\d+)? )?\+(\d+)(?:,(\d+))? @@")


def _dosya_adi(baslik: str) -> str:
    """`+++ b/<yol>` basligindan depo-ici yolu cikarir."""
    yol = baslik[4:].split("\t", 1)[0].strip()
    if yol.startswith('"') and yol.endswith('"') and len(yol) >= 2:
        yol = yol[1:-1]
    if yol == "/dev/null":
        return ""
    if yol.startswith("b/"):
        yol = yol[2:]
    return yol


def _dosya_adi_git(baslik: str) -> str:
    """`diff --git a/<yol> b/<yol>` basligindan depo-ici yolu cikarir."""
    govde = baslik[len("diff --git ") :].strip()
    parcalar = govde.split(" b/")
    return parcalar[0][2:] if len(parcalar) == 2 else ""


def diff_tara(citir: str) -> list[dict]:
    """`git diff`/`git log -p` ciktisini tarar; yalniz `+` satirlari sayilir.

    Binary dosyalar `Binary files ... differ` diye yazilir: iclerinde `+`
    satiri OLMAZ, dolayisiyla kendiliginden atlanir.
    """
    bulgular: list[dict] = []
    dosya = ""
    env_dosyasi = False
    yeni_satir = 0
    for satir in citir.splitlines():
        if satir.startswith("diff --git "):
            dosya = _dosya_adi_git(satir)
            env_dosyasi = False
            continue
        if satir.startswith("+++ "):
            yeni_ad = _dosya_adi(satir)
            if yeni_ad:
                dosya = yeni_ad
            env_dosyasi = desen.env_dosyasi_mi(dosya)
            if env_dosyasi:
                # `.env` dosyasinin push'a girmesi KENDISI bir bulgu;
                # degeri OKUNMAZ (satirlari taranmaz).
                bulgular.append(
                    desen.bulgu(dosya, 0, desen.ENV_DOSYASI_TURU)
                )
            continue
        hunk = _HUNK.match(satir)
        if hunk:
            yeni_satir = int(hunk.group(1))
            continue
        # YENI dosyadaki satir sayaci yalniz `+` ve bosluk satirlariyla ilerler.
        # Git `-U0` kullansa bile hunk basligi/eski-cikti satirlari gorunur.
        if satir.startswith("+"):
            if not dosya or env_dosyasi or satir.startswith("+++"):
                continue
            tur = desen.satir_tara(satir[1:])
            if tur:
                bulgular.append(desen.bulgu(dosya, yeni_satir, tur))
            yeni_satir += 1
        elif satir.startswith(" ") or satir == "":
            yeni_satir += 1
    return bulgular


# --------------------------------------------------------------------------
# Push taramasi
# --------------------------------------------------------------------------


def tara_push(
    repo: Path, referanslar: list[tuple[str, str, str, str]]
) -> list[dict]:
    """Push edilen her ref icin EKLENEN satirlari tarar.

    `remote_sha` sifirsa (yeni dal) `git log <sha> --not --remotes` ile
    gonderilecek commit'lerin diff'i kullanilir. Silme push'u (local_sha sifir)
    atlanir: eklenen satir yoktur.
    """
    bulgular: list[dict] = []
    for _yerel_ref, yerel_sha, _uzak_ref, uzak_sha in referanslar:
        if _SIFIR_SHA.match(yerel_sha):  # silme push'u: taranacak yeni satir yok
            continue
        if _SIFIR_SHA.match(uzak_sha):
            citir = _git(
                repo,
                ["log", yerel_sha, "--not", "--remotes", "--format=commit %H", "-p", "-U0"],
            )
        else:
            citir = _git(repo, ["diff", "-U0", f"{uzak_sha}..{yerel_sha}"])
        bulgular.extend(diff_tara(citir))
    return bulgular


def _referanslari_oku(stdin: IO[str]) -> list[tuple[str, str, str, str]]:
    """stdin'den `local_ref local_sha remote_ref remote_sha` satirlarini okur."""
    referanslar = []
    for satir in stdin:
        parcalar = satir.split()
        if len(parcalar) < 4:
            continue
        referanslar.append((parcalar[0], parcalar[1], parcalar[2], parcalar[3]))
    return referanslar


def hook_tara_main(stdin: IO[str], repo: Path) -> int:
    """Hook girisi: bulgu varsa stderr'e Turkce kisa rapor + cikis 1, yoksa 0."""
    try:
        bulgular = tara_push(repo, _referanslari_oku(stdin))
    except GitHata as exc:
        print(f"anahtarlik: git okunamadi ({exc}); taramada bulgu YOK sayildi.", file=sys.stderr)
        return 0
    if not bulgular:
        return 0
    print(_PUSH_UYARI, file=sys.stderr)
    for b in bulgular:
        print(f"  {b['dosya']}:{b['satir']} {b['tur']} {b['onizleme']}", file=sys.stderr)
    return 1


# --------------------------------------------------------------------------
# Hook kurulumu
# --------------------------------------------------------------------------


def _git_dizini(repo: Path) -> Path | None:
    """`.git` dizini. Worktree/submodule'de `.git` bir DOSYADIR."""
    dot_git = repo / ".git"
    if dot_git.is_dir():
        return dot_git
    if dot_git.exists():  # worktree / submodule
        try:
            yol = _git(repo, ["rev-parse", "--git-path", "hooks"])
        except GitHata:
            return None
        return Path(yol) if Path(yol).is_absolute() else (repo / yol)
    return None


def _hooks_dizini(repo: Path, git_dir: Path) -> tuple[Path, str | None]:
    """Hook dizinini bulur: `core.hooksPath` varsa O, yoksa `<git-dir>/hooks`."""
    try:
        ayar = _git(repo, ["config", "--get", "core.hooksPath"]).strip()
    except GitHata:
        ayar = ""
    if ayar:
        yol = Path(ayar)
        return (yol if yol.is_absolute() else repo / yol), ayar
    return git_dir / "hooks", None


def _repo_icinde(yol: Path, repo: Path) -> bool:
    try:
        yol.resolve().relative_to(repo.resolve())
    except (ValueError, OSError):
        return False
    return True


#: Guvenli yuklemenin kaniti: `-P` bayragi olmadan eski hook SIZDIRIR
#: (bulunulan dizindeki sahte `anahtarlik/` paketini calistirir).
_GUVENLI_CAGIRMA = "-P -m anahtarlik"


def _bizimki(metin: str) -> bool:
    """Bu hook bizim mi? (isareti var mi) -> yabanci hook ASLA ezilmez."""
    return HOOK_ISARETI in metin


def _guvenli(metin: str) -> bool:
    """Bizim hook, ama en guncel (guvenli) surum mu?

    Eski surum isareti tasiyordu ama `-P` yoktu: sadece isarete bakmak onlari
    `guncel` sayardi ve acik birakirdi. Artik eski surum de bizim sayilir
    (isareti var) ama `eski-surum` olarak ISLENIR ve yeniden yazilir.
    """
    return _bizimki(metin) and _GUVENLI_CAGIRMA in metin


def _betik() -> str:
    """Kurulacak betik: modul yolu bu kurulumun gercek dizinine baglanir.

    Yol `sh` tasiyla tek tirnak icinde yazilir; tirnak/backslash iceren bir
    yol `shlex.quote` ile kacisli olur (yoksa betik SÖZ dizgisi olur).
    """
    try:
        kok = str(Path(__file__).resolve().parent.parent)
    except OSError:
        return HOOK_ICERIK.replace(f"'{YOL_ISARETI}'", "'.'")  # cozulemedi: en az calisir
    return HOOK_ICERIK.replace(f"'{YOL_ISARETI}'", shlex.quote(kok))


def kur(repo: Path, uygula: bool = False, ortak: bool = False) -> dict:
    """pre-push hook'unu kurar. VARSAYILAN KURU CALISTIRMA (uygula=False).

    `uygula=False` iken dosya sistemine HIC dokunulmaz; sadece yapilacak
    islem bildirilir. Yabanci bir hook varsa ASLA ustune yazilmaz.

    `core.hooksPath` repo DISINI gosteriyorsa (genelde global ayar) o dizin
    TUM repolarda calisir: `ortak=True` verilmeden oraya yazilmaz
    (`durum: ortak-hooks-dizini`).
    """
    git_dir = _git_dizini(repo)
    if git_dir is None:
        return {"durum": "git-depo-degil", "yol": None, "hooks_path": None}
    hooks_dizini, hooks_path = _hooks_dizini(repo, git_dir)
    hedef = hooks_dizini / "pre-push"
    sonuc = {
        "durum": "yok",
        "yol": str(hedef),
        "hooks_path": hooks_path,
        "hooks_dizini": str(hooks_dizini),
        "ortak": hooks_path is not None and not _repo_icinde(hooks_dizini, repo),
    }
    if sonuc["ortak"] and not ortak:
        sonuc["durum"] = "ortak-hooks-dizini"
        sonuc["uygulandi"] = False
        return sonuc

    if hedef.is_symlink():
        # Link uzerinden yazmak repo DISINDAKI bir dosyayi ezebilir
        # (os.replace linki izlemez ama yine de kurulumun isi degil).
        sonuc["durum"] = "simgeler"
        sonuc["ayrinti"] = "pre-push bir sembolik bag; ustune yazilmadi"
        sonuc["uygulandi"] = False
        return sonuc

    if hedef.exists():
        try:
            mevcut = hedef.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            sonuc["durum"] = "okunamadi"
            sonuc["ayrinti"] = exc.__class__.__name__
            return sonuc
        sonuc["durum"] = "guncel" if _guvenli(mevcut) else ("eski-surum" if _bizimki(mevcut) else "yabanci-hook-var")
        if not uygula:
            sonuc["uygulandi"] = False
            return sonuc
        if sonuc["durum"] == "guncel":
            sonuc["uygulandi"] = False  # idempotent: tekrar yazmaz
            return sonuc
        if sonuc["durum"] == "yabanci-hook-var":
            sonuc["uygulandi"] = False  # ASLA ustune yazma
            return sonuc

    if not uygula:
        sonuc["uygulandi"] = False
        return sonuc

    try:
        hooks_dizini.mkdir(parents=True, exist_ok=True)
        # Atomik yazim: ayni dizinde gecici dosya -> os.replace.
        # Betik `sh` ile calistigi icin satir sonlari KESINLIKLE LF olmali.
        fd, gecici = tempfile.mkstemp(dir=str(hooks_dizini), prefix=".pre-push.")
        try:
            with os.fdopen(fd, "wb") as dosya:
                dosya.write(_betik().encode("utf-8"))
            os.replace(gecici, hedef)
        except BaseException:
            Path(gecici).unlink(missing_ok=True)
            raise
        try:
            os.chmod(hedef, 0o755)
        except OSError:
            pass  # Windows'ta chmod yetsizse de hook dosyasi yazildi
    except OSError as exc:
        sonuc["durum"] = "yazilamadi"
        sonuc["ayrinti"] = exc.__class__.__name__
        return sonuc

    sonuc["durum"] = "yazildi"
    sonuc["uygulandi"] = True
    return sonuc