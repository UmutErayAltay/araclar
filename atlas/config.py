"""Yapilandirma: ~/.atlas/config.toml (roots) ve veritabani yolu cozumlemesi."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

CONFIG_DIRNAME = ".atlas"
CONFIG_FILENAME = "config.toml"
DEFAULT_DB_NAME = "atlas.db"
DB_ENV_VAR = "ATLAS_DB"
DEFAULT_DEPTH = 3


def atlas_dir() -> Path:
    return Path.home() / CONFIG_DIRNAME


def default_db_path() -> Path:
    """ATLAS_DB ortam degiskeni, yoksa ~/.atlas/atlas.db."""
    env = os.environ.get(DB_ENV_VAR)
    if env:
        return _expanduser(env)
    return atlas_dir() / DEFAULT_DB_NAME


def config_path() -> Path:
    return atlas_dir() / CONFIG_FILENAME


def load_roots() -> list[Path]:
    """config.toml'daki `roots`, yoksa [Path.home()]."""
    path = config_path()
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except (FileNotFoundError, NotADirectoryError, IsADirectoryError, PermissionError, tomllib.TOMLDecodeError):
        return [Path.home()]
    roots = data.get("roots")
    if not isinstance(roots, list) or not roots:
        return [Path.home()]
    out: list[Path] = []
    for item in roots:
        if isinstance(item, str) and item:
            out.append(_expanduser(item))
    return out or [Path.home()]


def _expanduser(deger: str) -> Path:
    """`~` genisletmesi; PATH/home hatasi veya sembolik link dongusu olursa
    yolu oldugu gibi dondurur (taramayi cokertmemek icin)."""
    try:
        return Path(deger).expanduser()
    except (RuntimeError, OSError, KeyError):
        return Path(deger)
