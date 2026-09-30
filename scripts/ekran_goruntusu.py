#!/usr/bin/env python3
"""README ekran görüntülerini KURGUSAL veriyle üretir.

GÜVENLİK (bağlayıcı): Bu script yalnız UYDURMA veri kullanır.
  * Repo adları kurgusaldır (`ornek-api`, `demo-arayuz`, …).
  * Tüm yollar `/kurgusal/...` altındadır.
  * Gerçek repo adı, gerçek yol, gerçek kişi adı, gerçek anahtar veya
    gerçek e-posta YOKTUR. Ekranda görünecek tek "kişi" adı bile uydurmadır.
  * Sahte sır çalışma zamanında parçalardan kurulur; kaynakta tam literal yok.

Çıktı: `docs/ekran/{ozet-masaustu,yarim-is,sizinti-masaustu,borc,ozet-mobil}.png`

Kullanım:
    python3 scripts/ekran_goruntusu.py [--cikti docs/ekran] [--port 8799]
"""

from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_KOK))

from atlas import db as db_mod  # noqa: E402

#: Chromium arama yolu (ortam değişkeniyle de verilebilir).
CHROMIUM_ADAYLARI = [
    os.environ.get("PW_CHROMIUM_EXECUTABLE"),
    "/opt/pw-browsers/chromium-1243/chrome-linux/chrome",
    "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
]

MASAUSTU = {"width": 1440, "height": 900}
MOBIL = {"width": 390, "height": 844}

#: Sabit tarih: ekran görüntüleri tekrarlanabilir olsun (veri "taze").
TARAMA = "2026-09-30T09:15:00+00:00"


def _sahte_sir(n: int = 12) -> str:
    """Parçalardan kurulan sahte anahtar (kaynakta tam literal YOK)."""
    return "sk-" + ("k" + "7") * n


def _fake_ad(i: int) -> str:
    return f"kurgusal-kisi-{i}"


KURGUSAL_REPOLAR = [
    # (yol, ad, dirty, unpushed, dal, son commit, remote)
    ("/kurgusal/ornek-api", "ornek-api", 4, 3, "main", "2026-09-30T08:12:00+00:00", 1),
    ("/kurgusal/demo-arayuz", "demo-arayuz", 0, None, "feat/yeni-ozet", "2026-09-29T14:03:00+00:00", 1),
    ("/kurgusal/ornek-kutuphane", "ornek-kutuphane", 1, 1, "main", "2026-09-27T08:44:00+00:00", 1),
    ("/kurgusal/deneme-araci", "deneme-araci", 0, 0, "main", "2026-09-22T11:22:00+00:00", 0),
    ("/kurgusal/ornek-uygulama", "ornek-uygulama", 2, 0, "main", "2026-09-25T16:40:00+00:00", 1),
    ("/kurgusal/demo-servis", "demo-servis", 0, None, "main", "2026-09-20T09:05:00+00:00", 1),
    ("/kurgusal/ornek-arac", "ornek-arac", 7, 5, "gelistirme", "2026-09-26T13:31:00+00:00", 1),
    ("/kurgusal/demo-bibliyeka", "demo-bibliyeka", 0, 0, "main", "2026-09-18T10:10:00+00:00", 0),
    ("/kurgusal/ornek-notlar", "ornek-notlar", 1, 0, "main", "2026-09-24T12:12:00+00:00", 0),
]

KURGUSAL_BULGULAR = [
    ("/kurgusal/ornek-api", "api-anahtari", "yuksek", "app/yapilandirma.py", 18, None),
    ("/kurgusal/ornek-api", "ozel-anahtar", "yuksek", "certs/servis.pem", 1, "a1b2c3d"),
    ("/kurgusal/ornek-api", "e-posta", "dusuk", "ILETISIM.md", 42, None),
    ("/kurgusal/demo-arayuz", "env-izlenen", "yuksek", ".env.production", None, None),
    ("/kurgusal/demo-arayuz", "kisisel-yol", "orta", "belgeler/kurulum.md", 9, "e4f5a6b"),
    ("/kurgusal/ornek-kutuphane", "api-anahtari", "yuksek", "ornek/istemci.py", 77, None),
    ("/kurgusal/ornek-kutuphane", "kisisel-yol", "orta", "Ceviz/Notlar.md", 12, None),
    ("/kurgusal/deneme-araci", "gorsel-elle-kontrol", "bilgi", "docs/ekran/ornek.png", None, None),
    ("/kurgusal/ornek-uygulama", "api-anahtari", "yuksek", "src/yapilandirma.ts", 33, None),
    ("/kurgusal/ornek-uygulama", "kisisel-yol", "orta", "docs/kurulum.md", 5, "9f8e7d6"),
    ("/kurgusal/ornek-arac", "env-izlenen", "yuksek", ".env", None, None),
]

KURGUSAL_TODOLAR = [
    ("/kurgusal/ornek-api", "app/yapilandirma.py", 31, "# TODO: ortam degiskenlerini tek noktadan oku"),
    ("/kurgusal/ornek-api", "app/yapilandirma.py", 52, "# FIXME: varsayilanlar kaynak dosyada duruyor"),
    ("/kurgusal/ornek-api", "app/modeller.py", 8, "# TODO: model alanlarini dogrula"),
    ("/kurgusal/ornek-api", "app/modeller.py", 61, "# HACK: gecici; duzeltmeden kullanma"),
    ("/kurgusal/ornek-api", "tests/test_modeller.py", 22, "# TODO: kenar durum testleri eksik"),
    ("/kurgusal/demo-arayuz", "src/panel.js", 210, "// HACK: gecici; duzeltmeden once paneli acma"),
    ("/kurgusal/demo-arayuz", "src/panel.js", 244, "// TODO: klavye kisayollari eksik"),
    ("/kurgusal/demo-arayuz", "src/kart.js", 15, "// FIXME: yukseklik hesabi hatali"),
    ("/kurgusal/ornek-kutuphane", "README.md", 12, "# XXX: ornekler guncel degil"),
    ("/kurgusal/ornek-kutuphane", "ornek/istemci.py", 90, "# TODO: yeniden deneme ekle"),
    ("/kurgusal/ornek-kutuphane", "ornek/istemci.py", 118, "# TODO: hata tipini daralt"),
    ("/kurgusal/ornek-uygulama", "src/yapilandirma.ts", 66, "// FIXME: varsayilan degerler dagitik"),
    ("/kurgusal/ornek-uygulama", "src/gorunum.ts", 9, "// TODO: bos durum ekle"),
    ("/kurgusal/ornek-arac", "src/kesici.py", 4, "# TODO: giris noktasi"),
    ("/kurgusal/ornek-arac", "src/kesici.py", 40, "# TODO: hata toleransi"),
    ("/kurgusal/ornek-arac", "src/rapor.py", 17, "# FIXME: cikti siralamasi"),
]


def kurgusal_db_yaz(yol: Path) -> Path:
    """Tamamen UYDURMA veriyle geçici bir DB yazar."""
    con = db_mod.connect(yol)
    try:
        db_mod.upsert_repos(con, [
            {
                "path": p, "name": ad, "dirty": kirli, "unpushed": up,
                "branch": dal, "last_commit_at": son, "has_remote": uzak,
                "scanned_at": TARAMA,
            }
            for p, ad, kirli, up, dal, son, uzak in KURGUSAL_REPOLAR
        ])
        sir = _sahte_sir()
        for i, (repo, tur, onem, dosya, satir, commit) in enumerate(KURGUSAL_BULGULAR):
            if tur == "api-anahtari":
                # Ham sır BURAYA ASLA yazılmaz: maskeli metin üretilir.
                from atlas import leaks

                snip = leaks.maske(f'token = "{sir}"')
            elif tur == "ozel-anahtar":
                from atlas import leaks

                govde = "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQ" + "==" * 6
                snip = leaks.maske(
                    "-----BEGIN RSA PRIVATE KEY-----\n" + govde + "\n-----END RSA PRIVATE KEY-----"
                )
            elif tur == "kisisel-yol":
                snip = f"klasor: C:\\Users\\{_fake_ad(i)}\\belgeler"
            elif tur == "e-posta":
                snip = f"iletisim: {_fake_ad(i)}@ornek.invalid"
            elif tur == "env-izlenen":
                snip = None
            else:
                snip = "elle kontrol et (kişisel veri/yol/anahtar var mı)"
            con.execute(
                'INSERT INTO findings (repo, kind, severity, file, line, "commit", snippet_redacted) '
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (repo, tur, onem, dosya, satir, commit, snip),
            )
        for repo, dosya, satir, metin in KURGUSAL_TODOLAR:
            con.execute(
                "INSERT INTO todos (repo, file, line, text) VALUES (?, ?, ?, ?)",
                (repo, dosya, satir, metin),
            )
        con.commit()
    finally:
        con.close()
    return yol


def chromium_bul() -> str | None:
    import shutil

    for aday in [*CHROMIUM_ADAYLARI, shutil.which("chromium"), shutil.which("google-chrome")]:
        if aday and Path(aday).exists():
            return aday
    return None


def bos_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="README ekran goruntulerini uret (KURGUSAL veri).")
    parser.add_argument("--cikti", default="docs/ekran", help="cikti dizini")
    parser.add_argument("--port", type=int, default=0, help="gecici port (0 = otomatik)")
    args = parser.parse_args(argv)

    cikti = Path(args.cikti)
    if not cikti.is_absolute():
        cikti = REPO_KOK / cikti
    cikti.mkdir(parents=True, exist_ok=True)

    chromium = chromium_bul()
    if chromium is None:
        print("Chromium bulunamadi (/opt/pw-browsers)", file=sys.stderr)
        return 1
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright kurulu degil", file=sys.stderr)
        return 1

    gecici = Path(tempfile.mkdtemp(prefix="atlas-ekran-"))
    db_yolu = kurgusal_db_yaz(gecici / "kurgusal.db")
    port = args.port or bos_port()
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_KOK)
    env.pop("ATLAS_DB", None)
    surec = subprocess.Popen(
        [sys.executable, "-m", "atlas", "web", "--db", str(db_yolu), "--port", str(port)],
        cwd=str(REPO_KOK), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        for _ in range(100):
            if surec.poll() is not None:
                print(f"Sunucu erken sonlandi:\n{surec.stdout.read() if surec.stdout else ''}",
                      file=sys.stderr)
                return 1
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.1)
        else:
            print("Sunucu acilmadi", file=sys.stderr)
            return 1

        taban = f"http://127.0.0.1:{port}"
        isler = [
            ("ozet-masaustu.png", "/", MASAUSTU),
            ("yarim-is.png", "/yarim-is", MASAUSTU),
            ("sizinti-masaustu.png", "/sizinti", MASAUSTU),
            ("borc.png", "/borc", MASAUSTU),
            ("ozet-mobil.png", "/", MOBIL),
        ]
        with sync_playwright() as p:
            tarayici = p.chromium.launch(
                executable_path=chromium, args=["--no-sandbox", "--disable-dev-shm-usage"]
            )
            try:
                for ad, yol, viewport in isler:
                    baglam = tarayici.new_context(
                        viewport=viewport, device_scale_factor=2, color_scheme="dark"
                    )
                    sayfa = baglam.new_page()
                    sayfa.goto(f"{taban}{yol}", wait_until="networkidle")
                    sayfa.wait_for_timeout(220)  # JS ile cubuklar olcülensin
                    hedef = cikti / ad
                    sayfa.screenshot(path=str(hedef), full_page=True)
                    print(f"yazildi: {hedef}")
                    baglam.close()
            finally:
                tarayici.close()
    finally:
        surec.terminate()
        try:
            surec.wait(timeout=10)
        except subprocess.TimeoutExpired:  # pragma: no cover
            surec.kill()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())