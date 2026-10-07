"""Cikarim (analysis): kod kullanimlarini belgelerle karsilastirir, bulgular uretir.

Iki taraf karsilastirilir:
- KOD: `tara.repo_tara` -> kullanim AD'lari (+ dosya:satir)
- BELGE: `belge.belgeleri_tara` -> `.env.example` / README / compose AD'lari
- GIT: `git_iz` -> `.env` izleniyor mu, `.gitignore` kapsiyor mu

`.env.example` tanimlari `kullanilmayan` sayilir; README/compose'e gecen AD'ler
yalniz `belgelenmemis` filtresinde "belgelenmis" sayilir.

Genel/standart ortam degiskenleri (PATH, HOME, ...) hicbir bulgu uretmez.
"""

from __future__ import annotations

from pathlib import Path

from . import belge, git_iz, tara

SURUM = 1

#: Genel/standart ortam degiskenleri: `belgelenmemis` disarida birakilir.
#: Bunlar `.env.example`'da da cok gecer ve uygulama detayi degildir.
GENEL_DEGISKENLER = frozenset(
    {
        "PATH", "HOME", "USER", "PWD", "TMPDIR", "LANG", "CI", "NODE_ENV", "TMP", "TEMP",
        "OLDPWD", "SHELL", "TERM", "TZ", "HOSTNAME", "LOGNAME", "EDITOR",
        "PAGER", "DISPLAY", "XDG_CACHE_HOME", "XDG_CONFIG_HOME", "VIRTUAL_ENV",
        "PYTHONPATH", "PYTHONHOME", "PYTHONUNBUFFERED", "PYTHONDONTWRITEBYTECODE",
        "SYSTEMROOT", "COMSPEC", "PATHEXT", "PROGRAMFILES", "USERPROFILE",
        "APPDATA", "LOCALAPPDATA", "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE",
        "PORT", "HOST", "DEBUG",
    }
)


def _genel(ad: str) -> bool:
    """Bu degisken genel/standart mi? (belgelenmemis sayilmaz)"""
    return ad.upper() in GENEL_DEGISKENLER


def repo_analiz(repo: Path) -> dict:
    """Bir repo icin tum bulgulari uretir (dosya sistemi degismez)."""
    repo = Path(repo)
    atlanan: list[str] = []

    kullanimlar = tara.repo_tara(repo, atlanan)
    belgeler = belge.belgeleri_tara(repo, atlanan)

    kod_ads = {k["ad"] for k in kullanimlar}
    ornek_ads = set(belgeler["ornek"])
    belgelenmis = ornek_ads | set(belgeler["readme"]) | set(belgeler["compose"])

    # kod AD -> ilk kullanim (dosya:satir)
    ilk: dict[str, dict] = {}
    for k in kullanimlar:
        ilk.setdefault(k["ad"], k)

    bulgular: list[dict] = []

    # 1) belgelenmemis: kodda kullaniliyor, .env.example'da da README'de de yok
    for ad in sorted(kod_ads):
        if ad in belgelenmis or _genel(ad):
            continue
        kaynak = ilk[ad]
        bulgular.append(
            {
                "tur": "belgelenmemis",
                "ad": ad,
                "repo": str(repo),
                "dosya": kaynak["dosya"],
                "satir": kaynak["satir"],
            }
        )

    # 2) kullanilmayan: .env.example'da var, kodda hic yok
    for ad in sorted(ornek_ads - kod_ads):
        bulgular.append(
            {"tur": "kullanilmayan", "ad": ad, "repo": str(repo), "dosya": None, "satir": None}
        )

    # 3) env_gitignorede_degil: yerel .env var ama .gitignore kapsamiyor
    yerel_env = git_iz.env_dosyasi_var_mi(repo)
    if yerel_env and not git_iz.gitignore_env_kapsiyor_mi(repo):
        bulgular.append(
            {
                "tur": "env_gitignorede_degil",
                "ad": None,
                "repo": str(repo),
                "dosya": yerel_env[0],
                "satir": None,
                "detay": yerel_env,
            }
        )

    # 4) env_izleniyor: git ls-files icinde gercek .env (yuksek onem)
    for yol in git_iz.izlenen_env_dosyalari(repo):
        bulgular.append(
            {"tur": "env_izleniyor", "ad": None, "repo": str(repo), "dosya": yol, "satir": None}
        )

    return {
        "repo": str(repo),
        "bulgular": sorted(bulgular, key=lambda b: (b["tur"], b.get("ad") or "", b.get("dosya") or "")),
        "belgeler": belgeler,
        "atlanan": atlanan,
        "kod_adedi": len(kod_ads),
    }


def analiz(repolar: list[Path], zaman: str | None = None) -> dict:
    """Verilen repolari analiz eder; bulgu govdesini dondurur (yazmaz)."""
    from datetime import datetime, timezone

    kayitlar = [repo_analiz(repo) for repo in repolar]
    tum = [b for k in kayitlar for b in k["bulgular"]]
    return {
        "surum": SURUM,
        "tarih": zaman
        or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "repolar": kayitlar,
        "bulgular": tum,
        "toplam": len(tum),
    }
