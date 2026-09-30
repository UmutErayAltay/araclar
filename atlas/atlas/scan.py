"""Repo kesfi + salt-okunur git durumu.

Guvenlik: repolara HIC BIR SEY yazilmaz. Yalnizca okuyan git komutlari calistirilir
(`status`, `log`, `rev-parse`, `rev-list`, `rev-parse --abbrev-ref`, `symbolic-ref`,
`for-each-ref`).
`fetch/push/pull/checkout/reset/clean/gc` hic calistirilmaz.
`GIT_OPTIONAL_LOCKS=0` ile index'in tazelenmesi engellenir.
"""

from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .db import delete_missing_repos, upsert_repos, utc_now

SKIP_DIRS = frozenset(
    {".git", "node_modules", ".venv", "venv", "target", "__pycache__"}
)

#: Sadece bunlar calistirilir; liste sinirli ve bilerek dar tutulur.
#: `fetch/push/pull/checkout/reset/clean/gc/filter-branch` burada YOK ve eklenmez.
#: `for-each-ref` yalnizca `refs/remotes` ALTINDA ref olup olmadigini sorar
#: (--count=1): salt-okunur, hicbir sey yazmaz/guncellemez.
#: `ls-files` yalnizca izlenen dosya listesi icin (Dalga B); -z ile okunur.
ALLOWED_GIT_SUBCOMMANDS = frozenset(
    {"status", "log", "rev-parse", "rev-list", "symbolic-ref", "remote", "for-each-ref", "ls-files"}
)

GIT_TIMEOUT = 60

DETACHED_BRANCH = "(detached)"

#: Bos depo: ne HEAD ne commit var.
UNBORN_MARKERS = frozenset({"HEAD", "ORIG_HEAD", "FETCH_HEAD", "MERGE_HEAD"})


class GitError(RuntimeError):
    """Bir repoda cikan hata; taramayi cokertmez."""


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


def run_git(repo: Path, args: list[str], timeout: int = GIT_TIMEOUT) -> str:
    if not args or args[0] not in ALLOWED_GIT_SUBCOMMANDS:
        raise GitError(f"izin verilmeyen git komutu: {' '.join(args)}")
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            env=git_env(),
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise GitError(str(exc)) from exc
    if proc.returncode != 0:
        raise GitError((proc.stderr or proc.stdout or "git basarisiz").strip())
    return proc.stdout


def is_repo(path: Path) -> bool:
    """Icinde .git klasoru VEYA dosyasi olan dizin (worktree/submodule icin dosya da olur)."""
    return (path / ".git").exists()


def find_repos(
    root: Path, depth: int = 3, hatalar: list[tuple[Path, str]] | None = None
) -> list[Path]:
    """Kokten `depth` seviyesine kadar repo kesfi.

    Bir dizin repo ise INDIRILMEZ (ic ice repo sayilmaz).
    node_modules/.venv/venv/target/__pycache__/.git hic girilmez.
    Sembolik link dongusune karsi (Path.resolve) korunur.

    Icine girilemeyen dizin (izin yok vb.) tarama cokertmez; `hatalar` verilmisse
    `(yol, aciklama)` olarak oraya eklenir. Boylece altindaki repolar SESSIZCE
    kaybolmaz (seffaflik).
    """
    found: list[Path] = []
    seen: set[Path] = set()
    try:
        base = root.resolve()
    except (OSError, RuntimeError):
        return []
    if not base.is_dir():
        return []
    def _erisilemedi(hata: OSError) -> None:
        if hatalar is not None:
            yol = Path(hata.filename) if hata.filename else base
            hatalar.append((yol, f"dizine girilemedi ({hata.strerror or type(hata).__name__}); altindaki repolar taranmadi"))

    for current, dirs, _files in os.walk(base, topdown=True, followlinks=False, onerror=_erisilemedi):
        current_path = Path(current)
        key = current_path.resolve() if current_path.is_symlink() else current_path
        if key in seen:  # ayni yer dongusu
            dirs[:] = []
            continue
        seen.add(key)
        if is_repo(current_path):
            found.append(current_path)
            dirs[:] = []  # repo icine inme
            continue
        depth_left = depth - (len(current_path.relative_to(base).parts))
        if depth_left <= 0:
            dirs[:] = []
            continue
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not (current_path / d).is_symlink())
    return sorted(found, key=lambda p: str(p))


def find_repo_paths(roots, depth: int = 3) -> list[Path]:
    """Tarama kapsamindaki TUM repo yollari (git durumu hic sorgulanmaz).

    Yeniden taramada hangi satirlarin silinecegini bilmek icin gerekir:
    git hatasi veren bir repo da kapsamdadir, yoksa satiri kaybolur.
    """
    paths: dict[str, Path] = {}
    for root in roots:
        root_path = Path(root).expanduser()
        if not root_path.is_dir():
            continue
        for repo_path in find_repos(root_path, depth=depth):
            paths[str(repo_path)] = repo_path
    return sorted(paths.values(), key=lambda p: str(p))


def _to_utc(commit_date_iso: str) -> str | None:
    text = commit_date_iso.strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def _has_commits(repo: Path) -> bool:
    try:
        run_git(repo, ["rev-parse", "--verify", "--quiet", "HEAD"])
        return True
    except GitError:
        return False


def _total_commits(repo: Path) -> int:
    out = run_git(repo, ["rev-list", "--count", "HEAD"])
    return int(out.strip() or 0)


def _upstream(repo: Path) -> str | None:
    try:
        out = run_git(repo, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    except GitError:
        return None
    return out.strip() or None


def _current_branch(repo: Path, has_commits: bool) -> str:
    if not has_commits:
        # Bos depoda HEAD normalde unborn branch'i gosterir; symbolic-ref daha guvenilir.
        try:
            return run_git(repo, ["symbolic-ref", "--short", "HEAD"]).strip() or DETACHED_BRANCH
        except GitError:
            return DETACHED_BRANCH
    try:
        ad = run_git(repo, ["rev-parse", "--abbrev-ref", "HEAD"]).strip()
        # Detached HEAD'de git hata vermez, dogrudan "HEAD" yazar.
        if not ad or ad == "HEAD":
            return DETACHED_BRANCH
        return ad
    except GitError:
        pass
    try:
        return run_git(repo, ["rev-parse", "--short", "HEAD"]).strip() or DETACHED_BRANCH
    except GitError:
        return DETACHED_BRANCH


def _dirty_count(repo: Path) -> int:
    out = run_git(repo, ["status", "--porcelain"])
    return len([line for line in out.splitlines() if line.strip()])


def _has_remote_ref(repo: Path) -> bool:
    """`refs/remotes/` altinda en az bir ref var mi?

    Bu, uzak-takip (remote-tracking) bilgisinin YERELDE olup olmadigini sorar;
    ag erisimi gerektirmez, yalnizca yerel ref deposunu okur.
    """
    try:
        out = run_git(repo, ["for-each-ref", "--count=1", "refs/remotes"])
    except GitError:
        return False
    return bool(out.strip())


def _unpushed_count(repo: Path, has_commits: bool) -> int | None:
    """Push edilmemiş commit sayisi.

    `None` = BILINMIYOR: remote tanimli ama yerelde HICBIR uzak-takip ref'i yok.
    Bu durumda `--remotes` hicbir sey dislamaz ve sonuc "tum commitler" gibi
    gorunur; oysa gercek durum 0 da olabilir (her sey pushlanmis olabilir).
    `fetch` yasak oldugu icin burada dogru cevap "bilmiyorum"dur, uydurma sayi degil.
    """
    if not has_commits:
        return 0
    upstream = _upstream(repo)
    if upstream:
        try:
            out = run_git(repo, ["rev-list", "--count", f"{upstream}..HEAD"])
            return int(out.strip() or 0)
        except GitError:
            pass
    if _has_remote(repo) and not _has_remote_ref(repo):
        return None  # uzak-takip bilgisi yok: bilinmiyor
    # Upstream yok, ref var: once hicbir remote ref'inde olmayan commitler,
    # sonra (gUVENLI onlem) tum commitler.
    try:
        out = run_git(repo, ["rev-list", "--count", "HEAD", "--not", "--remotes"])
        return int(out.strip() or 0)
    except GitError:
        try:
            return _total_commits(repo)
        except GitError:
            return 0


def _has_remote(repo: Path) -> bool:
    try:
        out = run_git(repo, ["remote"])
    except GitError:
        return False
    return bool(out.strip())


def _last_commit_at(repo: Path, has_commits: bool) -> str | None:
    if not has_commits:
        return None
    try:
        return _to_utc(run_git(repo, ["log", "-1", "--format=%cI"]))
    except GitError:
        return None


def collect_repo(path: Path) -> dict:
    """Tek repo icin DB satirini dondurur. Hata olursa GitError firlatir.

    `unpushed` deger `None` olabilir (= bilinmiyor, bkz. `_unpushed_count`).
    """
    path = Path(path)
    has_commits = _has_commits(path)
    return {
        "path": str(path),
        "name": path.name or str(path),
        "scanned_at": utc_now(),
        "dirty": _dirty_count(path),
        "unpushed": _unpushed_count(path, has_commits),
        "branch": _current_branch(path, has_commits),
        "last_commit_at": _last_commit_at(path, has_commits),
        "has_remote": 1 if _has_remote(path) else 0,
    }


def scan_repo_safe(path: Path) -> tuple[dict | None, str | None]:
    """(satir, hata) doner; hata olursa satir None'dur."""
    try:
        return collect_repo(path), None
    except GitError as exc:
        return None, str(exc)
    except Exception as exc:  # beklenmeyen: taramayi cokertme
        return None, f"{type(exc).__name__}: {exc}"


def scan_roots(roots, depth: int = 3) -> tuple[list[dict], list[tuple[Path, str]]]:
    """Tum kokleri gezer, repolari toplar. Hatali repolar ayri listede."""
    repos: dict[str, dict] = {}
    errors: list[tuple[Path, str]] = []
    for root in roots:
        root_path = Path(root).expanduser()
        if not root_path.exists():
            errors.append((root_path, "kok dizin bulunamadi"))
            continue
        if not root_path.is_dir():
            errors.append((root_path, "kok bir dizin degil"))
            continue
        for repo_path in find_repos(root_path, depth=depth, hatalar=errors):
            row, err = scan_repo_safe(repo_path)
            if row is None:
                errors.append((repo_path, err or "bilinmeyen hata"))
            else:
                repos[row["path"]] = row
    return list(repos.values()), errors


def scan_and_sync(conn, roots, depth: int = 3) -> tuple[int, int, list[tuple[Path, str]]]:
    """Tara, DB'ye yaz (UPSERT), kapsam disinda kalan repo satirlarini sil.

    Doner: (guncellenen repo sayisi, silinen repo sayisi, hatalar).
    """
    in_scope = find_repo_paths(roots, depth=depth)
    repos, errors = scan_roots(roots, depth=depth)
    upsert_repos(conn, repos)
    # Kapsam daki YOL listesini kullan: git hatasi alan repo da kapsamdadir,
    # aksi halde satiri sessizce silinirdi.
    removed = delete_missing_repos(conn, [str(p) for p in in_scope])
    return len(repos), removed, errors
