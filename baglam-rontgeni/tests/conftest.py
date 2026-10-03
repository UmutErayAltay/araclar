"""baglam-rontgeni testleri icin ortak yardimcilar. Hicbir mock kutuphanesi yok.

Ag YOK. Gercek `~/.claude` HICBIR testte okunmaz/yazilmaz: `CLAUDE_DIR` ve
`RONTGEN_DIR` fixture'lari gecici dizine yonlendirir; alt yuklemede HOME da
geciciye cevrilir.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

#: ayar.oku'nun okuyacagi ayar govdesi (bilesikler kullanici tarafindan gelir).
VARSAYILAN_AYAR = {
    "model": "test-model",
    "skillOverrides": {},
    "enabledPlugins": {},
    "theme": "dark",
}


def sahte_claude_dir(
    yol: Path,
    ayar: dict | None = None,
    *,
    pluginler: dict[str, list[dict]] | None = None,
    skilller: dict[str, str] | None = None,
) -> Path:
    """Gecici bir CLAUDE_DIR kurar: settings.json + plugins + skills.

    pluginler: `ad@pazar` -> [{"installPath": ..., "lastUpdated": ...}, ...]
    skilller:  skill adi -> SKILL.md icerigi (`claude/skills/<ad>/SKILL.md`).
    """
    yol.mkdir(parents=True, exist_ok=True)
    (yol / "settings.json").write_text(
        json.dumps(ayar or VARSAYILAN_AYAR, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    if pluginler:
        kurulu = yol / "plugins"
        kurulu.mkdir(parents=True, exist_ok=True)
        (kurulu / "installed_plugins.json").write_text(
            json.dumps({"version": 1, "plugins": pluginler}, ensure_ascii=False),
            encoding="utf-8",
        )

    for ad, icerik in (skilller or {}).items():
        skill_dizini = yol / "skills" / ad
        skill_dizini.mkdir(parents=True, exist_ok=True)
        (skill_dizini / "SKILL.md").write_text(icerik, encoding="utf-8")
    return yol


def sahte_skill(icerik: str) -> str:
    """SKILL.md icerigi (frontmatter'da cok satirli `>` ve `|` test icin)."""
    return icerik


def sahte_plugin(yol: Path, skilller: dict[str, str] | None = None, *, mcp: dict | None = None) -> Path:
    """installPath altina skill'ler (ve istege bagli .mcp.json) yazar."""
    for ad, icerik in (skilller or {}).items():
        d = yol / "skills" / ad
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(icerik, encoding="utf-8")
    if mcp is not None:
        (yol / ".mcp.json").write_text(json.dumps(mcp), encoding="utf-8")
    return yol


def kur(settings: dict | None = None, **ayar_ek: object) -> dict:
    """VARSAYILAN_AYAR'i kopyalar ve ustune yazar (paylasilan sozlugu bozmaz)."""
    veri = json.loads(json.dumps(VARSAYILAN_AYAR))
    veri.update(settings or {})
    veri.update(ayar_ek)
    return veri


def ayar_oku(yol: Path) -> dict:
    return json.loads((yol / "settings.json").read_text(encoding="utf-8"))


def dosya_agaci(yol: Path) -> list[str]:
    """Dizindeki dosya adlari (yedek/temp kontrolu icin)."""
    return sorted(p.relative_to(yol).as_posix() for p in yol.rglob("*") if p.is_file())


def junction_kur(hedef: Path, kaynak: Path) -> bool:
    """Dizin junction'i kurar; kurulamazsa False (test `pytest.skip` cagirir).

    Windows'ta junction `mklink /J` ile ADMIN GEREKTIRMEZ (symlink'in aksine):
    dongu testleri bu yuzden gercekten calisir.
    """
    try:
        proc = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(hedef), str(kaynak)],
            capture_output=True,
            text=True,
        )
    except OSError:
        return False
    return proc.returncode == 0 and hedef.exists()


def symlink_kur(hedef: Path, kaynak: Path) -> bool:
    """Dosya/dizin symlink'i kurar; OLMAYANSA False (Windows'ta WinError 1314)."""
    try:
        os.symlink(kaynak, hedef, target_is_directory=kaynak.is_dir())
    except OSError:
        return False
    return True


def run_module_cli(
    *args: str, cwd: Path | str | None = None, env_ek: dict[str, str] | None = None
):
    """`python -m baglam_rontgeni ...` komutunu GERCEKTEN subprocess olarak calistirir.

    RONTGEN_DIR/CLAUDE_DIR varsayilanlari KULLANILMAZ: env once temizlenir, sonra
    testin yonlendirdigi degerler yazilir. HOME da geciciye cevrilir: test
    unutsa bile ~/.baglam-rontgeni ve ~/.claude YAZILMAZ.
    """
    temel = cwd if isinstance(cwd, Path) else (Path(cwd) if cwd else REPO_ROOT)
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT)
    env.pop("RONTGEN_DIR", None)
    env.pop("CLAUDE_DIR", None)
    env["HOME"] = env["USERPROFILE"] = str(temel)
    env.update(env_ek or {})
    return subprocess.run(
        [sys.executable, "-m", "baglam_rontgeni", *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        env=env,
    )


@pytest.fixture
def ev_isole(tmp_path: Path, monkeypatch) -> Path:
    """HOME/USERPROFILE'u gecici dizine cevirir: ~/.claude ve ~/.baglam-rontgeni YAZILMAZ."""
    ev = tmp_path / "ev"
    ev.mkdir()
    for ad in ("HOME", "USERPROFILE"):
        monkeypatch.setenv(ad, str(ev))
    return ev


@pytest.fixture
def claude_dir(tmp_path: Path, monkeypatch) -> Path:
    """CLAUDE_DIR'i gecici dizine yonlendirir (bos `.claude` kopyasi)."""
    dizin = tmp_path / "claude"
    monkeypatch.setenv("CLAUDE_DIR", str(dizin))
    return dizin


@pytest.fixture
def rapor_dizini(tmp_path: Path, monkeypatch) -> Path:
    """RONTGEN_DIR'i gecici dizine yonlendirir (kullanici raporu olusturulmaz)."""
    dizin = tmp_path / "raporlar"
    monkeypatch.setenv("RONTGEN_DIR", str(dizin))
    return dizin