"""`discover_roots` altındaki git repolarını otomatik palet item'ına çevirir.

Bu bir collector katmanıdır: **asla raise etmez**. Var olmayan/erişilemeyen bir kök
sessizce atlanır, çünkü kullanıcı config'inde bırakılmış eski bir `~/Desktop`
yolu programın tümüyle çalışmamasını hak etmez — palet yine de geri kalanı
gösterir.

Taranan her repo için üretilen item "repoya gir" işlevidir: kullanıcının
`$SHELL`'i repo kökünde açılır. Daha özel bir komut isteniyorsa config'in
`items` listesine aynı `cwd` ile yazılır — matcher.py o zaman config'teki
item'ı öncelikli tutar.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterable

#: Bunlara inilmez: ya repoların içi ya da tarama için değersiz ağır dizinler.
SKIP_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    "build",
    "dist",
    ".mypy_cache",
    ".pytest_cache",
    ".tox",
}

MAX_DEPTH = 3


def default_shell() -> str:
    """Kullanıcının login shell'i; yoksa platformun kabuğu."""
    return os.environ.get("SHELL") or os.environ.get("COMSPEC") or "/bin/sh"


def find_repos(roots: Iterable[Any], max_depth: int = MAX_DEPTH) -> list[dict]:
    """Köklerin altında `.git` içeren dizinleri bulur, her biri için palet item'ı üretir.

    Sonuç kök adı + yol ile kararlı şekilde sıralanır. Bir repo bulunduğunda
    içine inilmez (iç içe repo taraması yok); gizli dizinler ve ağır build
    dizinleri atlanır.
    """
    repos = find_repo_paths(roots, max_depth=max_depth)
    shell = default_shell()
    return [
        {
            "label": path.name,
            "cwd": str(path),
            "command": shell,
            "tags": ["repo"],
        }
        for path in repos
    ]


def find_repo_paths(roots: Iterable[Any], max_depth: int = MAX_DEPTH) -> list[Path]:
    """`find_repos`'in ham yol döndüren katmanı — testler bunu kullanır."""
    found: list[Path] = []
    seen: set[Path] = set()

    for root in roots or []:
        if not isinstance(root, (str, os.PathLike)) or not str(root).strip():
            continue
        for path in _walk(Path(root).expanduser(), max_depth):
            if path not in seen:
                seen.add(path)
                found.append(path)

    return sorted(found, key=lambda p: (p.name, str(p)))


def _walk(root: Path, max_depth: int) -> list[Path]:
    """Tek bir kökün altını tarar. Hata durumunda boş liste döner."""
    try:
        if not root.is_dir():
            return []
    except OSError:
        return []

    found: list[Path] = []
    root_depth = len(root.parts)
    stack: list[Path] = [root]

    while stack:
        current = stack.pop()
        try:
            if not current.is_dir():
                continue
            if (current / ".git").exists():
                found.append(current)
                continue  # iç içe repo'ya inme
            if len(current.parts) - root_depth >= max_depth:
                continue
            children = sorted(current.iterdir())
        except OSError:  # PermissionError, yarı silinmiş mount, vs.
            continue

        for child in children:
            if _is_skippable(child):
                continue
            stack.append(child)

    return found


def _is_skippable(path: Path) -> bool:
    """Gizli ya da ağır dizin mi? Kontrol I/O hatasına dayanıklı olmalı."""
    if path.name in SKIP_DIR_NAMES or path.name.startswith("."):
        return True
    try:
        return not path.is_dir()
    except OSError:
        return True
