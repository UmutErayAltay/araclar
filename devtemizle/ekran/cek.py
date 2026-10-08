"""Panel ekran goruntuleri (FAKE veri). Calistirma: python3 ekran/cek.py (devtemizle kokunden).

Ne yapar:
  * Gecici dizinde sahte (uydurma adli) repo agaci kurar; ev dizinine dokunmaz.
  * DEVTEMIZLE_DIR'i gecici dizine yonlendirir, uygulamayi bos bir portta acar.
  * API uzerinden tarama tetikler (onbellek kapali: pip/npm/docker calismaz).
  * Playwright chromium ile masaustu/mobil, acik/koyu ekran goruntuleri ve
    secim + onay paneli acikken goruntu alir.
"""

from __future__ import annotations

import glob
import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

from werkzeug.serving import make_server

EKRAN = Path(__file__).resolve().parent
PAKET = EKRAN.parent
PAKET_YOLU = str(PAKET)


def _sahte_agac(kok: Path) -> None:
    """Uydurma repolar: gercek kullanici yolu, gercek proje adi yok."""
    def dosya(yol: Path, bayt: int) -> None:
        yol.parent.mkdir(parents=True, exist_ok=True)
        with yol.open("wb") as f:
            f.truncate(bayt)  # seyrek dosya: diskte yer kaplamaz, boyut gorunur

    def yasla(yol: Path, gun: float) -> None:
        zaman = time.time() - gun * 86400
        for kok_, dizinler, dosyalar in os.walk(yol):
            for ad in dizinler + dosyalar:
                os.utime(Path(kok_) / ad, (zaman, zaman))
        os.utime(yol, (zaman, zaman))

    def git_kur(repo: Path, kirli: bool) -> None:
        repo.mkdir(parents=True, exist_ok=True)
        (repo / ".gitignore").write_text(
            "node_modules/\n.next/\ndist/\n.venv/\n__pycache__/\ntarget/\n", encoding="utf-8")
        # Yalniz "kirli" repo gercek git deposu olur (izlenmeyen dosya -> rozet).
        # Digerleri sahte .git dizinidir: git durumu okunamaz, kirli sayilmaz.
        if kirli and shutil.which("git"):
            subprocess.run(["git", "init", "-q", str(repo)], check=False, capture_output=True)
        else:
            (repo / ".git").mkdir(exist_ok=True)
            (repo / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
        if kirli:
            dosya(repo / "not-taslak.txt", 120)

    # 1) Node uygulamasi: node_modules + .next + dist (dikkat)
    repo = kok / "demo-web-app"
    git_kur(repo, kirli=True)
    (repo / "package.json").write_text('{"name": "demo-web-app"}\n', encoding="utf-8")
    dosya(repo / "node_modules" / "sahte-kutuphane" / "index.js", 2_400_000)
    dosya(repo / "node_modules" / "ornek-araclar" / "index.js", 850_000)
    dosya(repo / ".next" / "cache" / "derleme.bin", 1_300_000)
    dosya(repo / "dist" / "bundle.js", 640_000)
    yasla(repo, 96)

    # 2) Python kutuphanesi: sanal ortam (pyvenv.cfg), __pycache__
    repo = kok / "kitaplik-ornek"
    git_kur(repo, kirli=False)
    (repo / "pyproject.toml").write_text('[project]\nname = "kitaplik-ornek"\n', encoding="utf-8")
    (repo / ".venv").mkdir(parents=True, exist_ok=True)
    (repo / ".venv" / "pyvenv.cfg").write_text("home = /opt/sahte-python\nversion = 3.11\n", encoding="utf-8")
    dosya(repo / ".venv" / "lib" / "paket.py", 3_200_000)
    dosya(repo / "kitaplik" / "__pycache__" / "modul.pyc", 210_000)
    yasla(repo, 14)

    # 3) Rust tool: target
    repo = kok / "arac-rust-sahte"
    git_kur(repo, kirli=False)
    (repo / "Cargo.toml").write_text('[package]\nname = "arac-rust-sahte"\n', encoding="utf-8")
    dosya(repo / "target" / "debug" / "arac", 9_800_000)
    yasla(repo, 210)

    # 4) Eski taslak: node_modules, cok eski
    repo = kok / "eski-blog-taslak"
    git_kur(repo, kirli=False)
    (repo / "package.json").write_text('{"name": "eski-blog-taslak"}\n', encoding="utf-8")
    dosya(repo / "node_modules" / "eski-paket" / "index.js", 1_100_000)
    yasla(repo, 480)


def _bos_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _istek(port: int, yol: str, govde: dict | None = None, csrf: str | None = None):
    url = f"http://127.0.0.1:{port}{yol}"
    basliklar = {"Origin": f"http://127.0.0.1:{port}"}
    veri = None
    if govde is not None:
        veri = json.dumps(govde).encode("utf-8")
        basliklar["Content-Type"] = "application/json"
        basliklar["X-CSRF"] = csrf or ""
    istek = urllib.request.Request(url, data=veri, headers=basliklar,
                                   method="POST" if govde is not None else "GET")
    with urllib.request.urlopen(istek, timeout=20) as cevap:
        return json.loads(cevap.read().decode("utf-8") or "{}")


def _tarama(port: int) -> None:
    sayfa = urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=20).read().decode("utf-8")
    csrf = re.search(r'<meta name="csrf" content="([^"]+)"', sayfa).group(1)
    _istek(port, "/api/tara", {"onbellek": False}, csrf)
    for _ in range(300):
        durum = _istek(port, "/api/durum")
        if durum["is"] == "bos":
            if durum["hata"]:
                raise SystemExit(f"tarama hatasi: {durum['hata']}")
            return
        time.sleep(0.1)
    raise SystemExit("tarama zaman asimina ugradi")


def _chromium() -> str:
    adaylar = sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome"))
    if not adaylar:
        raise SystemExit("chromium bulunamadi: /opt/pw-browsers")
    return adaylar[-1]


def _demo_ac(sayfa) -> None:
    """Birden fazla aday iceren sahte repoyu acar (ekranda tablo gorunsun)."""
    sayfa.locator("#repo-listesi details.repo", has_text="demo-web-app").locator("summary").click()


def _ekran_goruntuleri(port: int) -> None:
    from playwright.sync_api import sync_playwright

    url = f"http://127.0.0.1:{port}/"
    hedefler = [
        ("masaustu-acik", {"width": 1280, "height": 800}, "light"),
        ("masaustu-koyu", {"width": 1280, "height": 800}, "dark"),
        ("mobil-acik", {"width": 390, "height": 844}, "light"),
        ("mobil-koyu", {"width": 390, "height": 844}, "dark"),
    ]
    with sync_playwright() as p:
        tarayici = p.chromium.launch(executable_path=_chromium(), args=["--no-sandbox"])
        try:
            for ad, boyut, sema in hedefler:
                baglam = tarayici.new_context(viewport=boyut, color_scheme=sema)
                sayfa = baglam.new_page()
                sayfa.goto(url)
                sayfa.wait_for_selector("#repo-listesi details.repo")
                _demo_ac(sayfa)
                sayfa.wait_for_timeout(200)
                sayfa.screenshot(path=str(EKRAN / f"{ad}.png"), full_page=True)
                baglam.close()

            # Onay: masaustu acik, iki guvenli + bir dikkat ogesi secili, panel acik.
            baglam = tarayici.new_context(viewport={"width": 1280, "height": 800}, color_scheme="light")
            sayfa = baglam.new_page()
            sayfa.goto(url)
            sayfa.wait_for_selector("#repo-listesi details.repo")
            _demo_ac(sayfa)
            kutular = sayfa.locator("#repo-listesi details[open] input[type=checkbox]")
            kutular.nth(0).check()  # node_modules (guvenli)
            kutular.nth(1).check()  # .next (guvenli)
            kutular.nth(2).check()  # dist (dikkat: onay panelinde uyari gorunur)
            sayfa.locator("#onizle").click()
            sayfa.wait_for_selector("#onay:not([hidden])")
            sayfa.wait_for_timeout(200)
            sayfa.screenshot(path=str(EKRAN / "onay.png"))
            baglam.close()
        finally:
            tarayici.close()


def main() -> None:
    gecici = Path(tempfile.mkdtemp(prefix="devtemizle-ekran-"))
    try:
        os.environ["DEVTEMIZLE_DIR"] = str(gecici / "raporlar")
        os.environ.pop("KULE_FRAME_ORIGIN", None)
        import sys
        sys.path.insert(0, PAKET_YOLU)
        from devtemizle.web import uygulama_olustur

        kok = gecici / "projeler"
        _sahte_agac(kok)
        port = _bos_port()
        uygulama = uygulama_olustur(kokler=[kok])
        sunucu = make_server("127.0.0.1", port, uygulama, threaded=True)
        threading.Thread(target=sunucu.serve_forever, daemon=True).start()
        try:
            _tarama(port)
            _ekran_goruntuleri(port)
        finally:
            sunucu.shutdown()
    finally:
        shutil.rmtree(gecici, ignore_errors=True)
    for ad in ("masaustu-acik", "masaustu-koyu", "mobil-acik", "mobil-koyu", "onay"):
        print(EKRAN / f"{ad}.png")


if __name__ == "__main__":
    main()
