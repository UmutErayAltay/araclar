"""TODO/FIXME borcu taramasi: git'in İZLEDİĞİ metin dosyalarında işaret satırları.

BAĞLAYICI KURAL: todo metni DB'ye yazılmadan ÖNCE `leaks.maske` fonksiyonundan
GEÇER. Todo yorumu (`# API_KEY = sk-…`) bir sır taşıyabilir; tarama onu bulmadan
önce siler, ekrana/veritabanına maskelenmiş hâli gider.

Salt-okunurluk: `scan.ALLOWED_GIT_SUBCOMMANDS` içindeki `ls-files` dışında YENİ
git alt komutu EKLENMEZ. Dosyalar `leaks.dosya_oku_salt` ile açılır — yalnızca
okuma kipi, ikili/büyük dosya atlanır, sembolik link takip edilmez.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any, Iterable, NamedTuple

from . import leaks

#: Üretim/bağımlılık dizinleri: git izlese bile repo içeriği değildir.
HARC_DIRLER = ("node_modules/", ".venv/", "venv/", "vendor/", "dist/", "build/")

#: `TODO(sahip, 2026-01-01):` biçimi de eşleşir; parantezli sahibi maskeye girmez.
#: `IGNORECASE`: gerçek kod `// Fixme:` / `// fixme:` da yazar. Büyük/küçük
#: harf duyarsızlığı YANLIŞ POZİTİF ÜRETMEZ — kelime sınırı aynı kalır:
#: `todolist`, `todo_list`, `myTODO` hâlâ elenir (testlerle kanıtlı).
ISARET_DESENI = re.compile(r"\b(TODO|FIXME|XXX|HACK)\b", re.IGNORECASE)

#: `todo.py` içinde 160 karakterle kırpılır.
METIN_UST_SINIR = 160

#: Repo başına toplam süre üst sınırı; aşılırsa "kısmi tarama" uyarısı.
REPO_SURE_UST_SINIR = 120.0


def _norm(dosya: str) -> str:
    return f"/{dosya.replace(chr(92), '/')}/".lower()


def haric_mi(dosya: str) -> bool:
    """Üretim/bağımlılık dizini (`.git/` zaten `ls-files` dışıdır)."""
    norm = _norm(dosya)
    return any(f"/{dizin}" in norm for dizin in HARC_DIRLER)


def satiri_tara(satir: str, *, dosya: str, no: int, repo: str) -> list[dict[str, Any]]:
    """İşaret içeren tek satırdan MASKELENMİŞ todo kaydı üretir (yoksa boş liste).

    Metin `leaks.maske`'den geçirilir ve 160 karaktere kırpılır: parçalardan
    kurulmuş sahte sırın kaynakta tam literal'i bulunmasa bile kayda yazılan
    her karakter maskelenmiş olur.
    """
    if not ISARET_DESENI.search(satir):
        return []
    govde = satir.strip()
    if len(govde) > METIN_UST_SINIR:
        govde = govde[: METIN_UST_SINIR - 1] + "…"
    return [
        {
            "repo": repo,
            "file": dosya,
            "line": no,
            "text": leaks.maske(govde),
        }
    ]


def todo_dosyalari(lsfiles: Iterable[str]) -> list[str]:
    """Taranacak dosyalar: İZLENEN, üretim dizini olmayan (git izlese de)."""
    return sorted(d for d in lsfiles if not haric_mi(d))


def tara_calisma_agaci(repo: Path, *, timeout: int = 60) -> list[dict[str, Any]]:
    """Yalnızca `git ls-files` ile İZLENEN dosyaları tarar.

    `dosya_oku_salt` ikili (>NUL) ve >1 MiB dosyaları zaten `None` ile eler;
    ayrı bir ikili kontrolüne gerek yoktur.
    """
    lsfiles = leaks.ls_files(repo, timeout)
    bulgular: list[dict[str, Any]] = []
    for dosya in todo_dosyalari(lsfiles):
        veri = leaks.dosya_oku_salt(repo, dosya)
        if veri is None:
            continue
        metin = veri.decode("utf-8", "replace")
        for no, satir in enumerate(metin.splitlines(), start=1):
            bulgular.extend(satiri_tara(satir, dosya=dosya, no=no, repo=str(repo)))
    return bulgular


class RepoTarama(NamedTuple):
    repo: str
    todos: list[dict[str, Any]]
    uyarilar: list[str]


def tara_repo(repo: Path, *, timeout: int = 60) -> RepoTarama:
    """Tek repo'nun todo taraması. Hata olursa istisna fırlatır (üst seviye yakalar)."""
    baslangic = time.monotonic()
    todos = tara_calisma_agaci(repo, timeout=timeout)
    uyarilar: list[str] = []
    sure = time.monotonic() - baslangic
    if sure > REPO_SURE_UST_SINIR:
        uyarilar.append(f"kismi tarama: repo {sure:.0f} sn (ust sinir {REPO_SURE_UST_SINIR:.0f} sn)")
    return RepoTarama(repo=str(repo), todos=todos, uyarilar=uyarilar)


def tara_roots(roots: Iterable[Path], *, depth: int = 3) -> tuple[dict[str, list[dict[str, Any]]], list[tuple[Path, str]]]:
    """(repo -> todos, hatalar). Hatalı repo taramayı çökertmez."""
    from .scan import find_repo_paths
    from .scan import GitError

    sonuc: dict[str, list[dict[str, Any]]] = {}
    hatalar: list[tuple[Path, str]] = []
    for repo in find_repo_paths(roots, depth=depth):
        try:
            tarama = tara_repo(repo)
        except GitError as exc:
            hatalar.append((repo, str(exc)))
            continue
        except Exception as exc:  # beklenmeyen: taramayı çökertme
            hatalar.append((repo, type(exc).__name__))
            continue
        sonuc[tarama.repo] = tarama.todos
    return sonuc, hatalar
