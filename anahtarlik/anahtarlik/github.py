"""GitHub tarafi: origin deposu, workflow'larin kullandigi secret adlari, gh listesi.

BAYAT KURALI: HAM SIR HICBIR YERE CIKMAZ. `gh secret list` YALNIZ AD dondurur
(github, degeri vermez); degeri okumaya CALISILMAZ. Hata mesajlari yalnizca
hata sinifi adini tasir.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Callable, Sequence

__all__ = [
    "repo_adi",
    "workflow_secretlari",
    "gh_secretlari",
    "fark",
    "GhHata",
    "GhYok",
]

GH_TIMEOUT = 30

#: https/git/ssh iki bicimde de `owner/ad` cikarilir; github.com disi -> None.
#: Tam eslesme (`fullmatch`) sarttir: URL'nin SONUNA kadar gitmeli, yoksa
#: `https://evil.com/?x=https://github.com/o/r` da eslesirdi.
#: Sahis `ad` karakter siniri iki isi birden yapar: (a) `-` ile BASLAMAZ,
#: boylece `--repo` degeri `gh`'e bayrak olarak giremez; (b) `?`, `#`, `;`,
#: bosluk gibi karakterler barinamaz.
_GITHUB_URL = re.compile(
    r"(?:(?:https?|git|ssh)://(?:[^/@\s]+@)?|git@)?github\.com[/:]"
    r"(?P<ad>[A-Za-z0-9_.][A-Za-z0-9_.-]*/[A-Za-z0-9_.][A-Za-z0-9_.-]*?)"
    r"(?:\.git)?/?",
    re.IGNORECASE,
)

#: `secrets.NAME` referansi. `GITHUB_TOKEN` GitHub tarafindan otomatik
#: uretilir, repo secrets listesinde YOKTUR: bu yuzden disarida birakilir.
_SECRET_REF = re.compile(r"secrets\.([A-Za-z_][A-Za-z0-9_]*)")
GITHUB_TOKEN = "GITHUB_TOKEN"

#: gh ciktisini donduren varsayilan calistirici.
Calistir = Callable[[Sequence[str]], "subprocess.CompletedProcess"]


class GhHata(RuntimeError):
    """gh calisti ama hata verdi (yetki, kimlik dogrulama, ag, bozuk JSON)."""


class GhYok(RuntimeError):
    """gh komutu sistemde bulunamadi."""


def _calistir(komut: list[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            komut, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=GH_TIMEOUT,
        )
    except FileNotFoundError as exc:
        raise GhYok("gh bulunamadi") from exc
    except (OSError, subprocess.SubprocessError) as exc:
        raise GhHata(f"gh calistirilamadi: {exc.__class__.__name__}") from None


def _git(repo: Path, args: Sequence[str]) -> str:
    """`origin` uzak adresini okur; hata durumunda `GhHata` firlatir.

    Ortam TAMAMEN devralinir (Windows'ta `TMP`/`USERPROFILE` gibi degiskenler
    eksik olunca git patlar), uzerine yalnizca salt-okunurluk ayarlari eklenir.
    """
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_OPTIONAL_LOCKS"] = "0"
    env["LC_ALL"] = "C"
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), *args], capture_output=True, text=True,
            encoding="utf-8", errors="replace", env=env, timeout=GH_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise GhHata(f"git calistirilamadi: {exc.__class__.__name__}") from None
    if proc.returncode != 0:
        raise GhHata("origin alinamadi")
    return proc.stdout


def repo_adi(repo: Path) -> str | None:
    """`origin` uzak adresinden `owner/ad`; github.com degilse `None`."""
    try:
        url = _git(repo, ["remote", "get-url", "origin"]).strip()
    except GhHata:
        return None
    eslesme = _GITHUB_URL.fullmatch(url)
    return eslesme.group("ad") if eslesme else None


def workflow_secretlari(repo: Path) -> set[str]:
    """`.github/workflows/*.y*ml` icindeki `secrets.NAME` adlari.

    `GITHUB_TOKEN` haric: o GitHub tarafindan uretilir, tanimli olmasi gerekmez.
    """
    adlar: set[str] = set()
    dizin = repo / ".github" / "workflows"
    if not dizin.is_dir():
        return adlar
    for yol in sorted(dizin.iterdir()):
        if not yol.is_file() or not yol.name.endswith((".yml", ".yaml")):
            continue
        try:
            metin = yol.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for ad in _SECRET_REF.findall(metin):
            if ad != GITHUB_TOKEN:
                adlar.add(ad)
    return adlar


def gh_secretlari(
    repo_adi: str, calistir: Calistir = _calistir
) -> set[str] | None:
    """`gh secret list --repo X --json name` ile repo secret ADLARI.

    gh yoksa veya hata verirse `None` doner (`GhYok` / `GhHata` farkli
    yakalanabilsin diye ikisi de `None`a eslenir). gh DEGER vermez.
    """
    try:
        proc = calistir(
            ["gh", "secret", "list", "--repo", repo_adi, "--json", "name", "--"]
        )
    except GhYok:
        return None
    if proc.returncode != 0:
        raise GhHata("gh secret list basarisiz")
    try:
        veri = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        raise GhHata("gh ciktisi JSON okunamadi") from None
    if not isinstance(veri, list):
        raise GhHata("gh ciktisi liste degil")
    return {girdi["name"] for girdi in veri if isinstance(girdi, dict) and "name" in girdi}


def fark(
    repo: Path,
    workflow_adlar: set[str],
    calistir: Calistir = _calistir,
    yerel_adlar: set[str] | None = None,
) -> dict:
    """Workflow'un kullandigi secret GitHub'da TANIMLI MI? (asil soru).

    `workflow_adlar`: workflow'larin basvurdugu secret adlari.
    `yerel_adlar`: yerel `.env` adlari (verilmezse yerel kumeleri bos kalir).
    Yalniz AD kumeleri doner, sirali (deterministik) listeler.
    """
    sonuc: dict = {
        "workflow_var_gh_yok": [],
        "gh_var_workflow_kullanmiyor": [],
        "yerel_var_gh_yok": [],
        "gh_var_yerel_yok": [],
        "durum": "tamam",
    }
    ad = repo_adi(repo)
    if ad is None:
        sonuc["durum"] = "github-degil"
        return sonuc
    try:
        gh_adlar = gh_secretlari(ad, calistir=calistir)
    except GhHata:
        sonuc["durum"] = "hata"
        return sonuc
    if gh_adlar is None:
        sonuc["durum"] = "gh-yok"
        return sonuc

    workflow = set(workflow_adlar)
    sonuc["workflow_var_gh_yok"] = sorted(workflow - gh_adlar)
    sonuc["gh_var_workflow_kullanmiyor"] = sorted(gh_adlar - workflow)
    if yerel_adlar is not None:
        yerel = set(yerel_adlar)
        sonuc["yerel_var_gh_yok"] = sorted(yerel - gh_adlar)
        sonuc["gh_var_yerel_yok"] = sorted(gh_adlar - yerel)
    return sonuc