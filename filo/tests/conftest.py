"""filo testleri icin ortak yardimcilar. Hicbir mock kutuphanesi yok.

Ag YOK: gercek `cor` CALISTIRILMAZ. Her test gecici dizinde (tmp_path) sahte
repolar ve sahte bir `cor` betigi kurar; bu betikler gercek ag/egitim yoktur,
stdin'i okuyup sabit metin yazar ya da kasten hata/zaman asimi uretir.

Yazma testleri YALNIZCA tmp_path altindadir: gercek kullanicinin repolari hicbir
testte degistirilmez. `filo-ciktilari` varsayilan cikti dizini testte asla
olusmaz (her test --cikti verir).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Sahte `cor`: gercek claude yok, ag yok. `--cor` ile bu dosya verilir.
SAHTE_COR = """\
#!{python}
import sys

konum = " ".join(sys.argv[1:])
girdi = sys.stdin.read()
if "{vaka}" == "uyur":
    import time
    time.sleep({uyku})
elif "{vaka}" == "hata":
    sys.stderr.write("sahte cor hatasi\\n")
    sys.exit(3)
elif "{vaka}" == "yok":
    sys.stderr.write("baglanilamiyor\\n")
    sys.exit(9)
else:
    sys.stdout.write("# rapor\\n\\n")
    sys.stdout.write("konum: " + konum + "\\n")
    sys.stdout.write("istem satiri: " + str(len(girdi.splitlines())) + "\\n")
"""


def sahte_repo(yol: Path, dosyalar: dict[str, str] | None = None) -> Path:
    """Gecici bir repo kurar: gercek git CALISTIRILMAZ (`.git` isaret dizini yeter)."""
    yol.mkdir(parents=True, exist_ok=True)
    (yol / ".git").mkdir(exist_ok=True)
    for ad, icerik in (dosyalar or {"README.md": "ornek\n"}).items():
        hedef = yol / ad
        hedef.parent.mkdir(parents=True, exist_ok=True)
        hedef.write_text(icerik, encoding="utf-8")
    return yol


def sahte_cor(yol: Path, *, vaka: str = "ok", uyku: int = 30) -> Path:
    """Sahte `cor` betigi kurar ve calistirilabilir yapar.

    vaka: "ok" (sabit rapor yazar) | "hata" (exit 3) | "yok" (exit 9) | "uyur".
    """
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(
        SAHTE_COR.format(python=sys.executable, vaka=vaka, uyku=uyku), encoding="utf-8"
    )
    yol.chmod(0o755)
    return yol


def gorev_dosyasi(yol: Path, metin: str = "Bu depoyu incele ve ozetle.\n") -> Path:
    """Gorev metni dosyasi (dagitilacak istem)."""
    yol.write_text(metin, encoding="utf-8")
    return yol


def run_module_cli(
    *args: str, cwd: Path | str | None = None, env_ek: dict[str, str] | None = None
):
    """`python -m filo ...` komutunu GERCEKTEN subprocess olarak calistirir.

    COR_MODEL varsayilani KULLANILMAZ: env once temizlenir, sonra testin
    yonlendirdigi degerler yazilir. HOME da geciciye cevrilir: test unutsa bile
    ./filo-ciktilari YAZILMAZ.
    """
    temel = cwd if isinstance(cwd, Path) else (Path(cwd) if cwd else REPO_ROOT)
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT)
    env.pop("COR_MODEL", None)
    env["HOME"] = env["USERPROFILE"] = str(temel)
    env.update(env_ek or {})
    return subprocess.run(
        [sys.executable, "-m", "filo", *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        env=env,
    )