#!/usr/bin/env python3
"""README ekran görüntülerini üretir (Dalga C).

GÜVENLİK: Bu betik **tamamen kurgusal** veri kullanır. Gerçek yol, anahtar,
e-posta veya kişisel bilgi YOKTUR; ajan adları, istemler ve kota sayıları
burada uydurulur. Betik geçici bir DB kurar, `orkestra web`'i başlatır,
Playwright ile beş PNG alır ve `docs/ekran/` altına yazar.

    python3 scripts/ekran_goruntusu.py

Playwright/Chromium yoksa betik açık hata verir (sessizce geçmez).
"""

from __future__ import annotations

import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from orkestra.queue import SEMA  # noqa: E402

# -- KURGUSAL VERI ----------------------------------------------------------
# Bu isimler/ist metinler gerçek DEĞİLDİR; ekran görüntüleri için seçilmiştir.

AJANLAR = [
    ("panda-kodlayici", "kuyruk panelindeki durum rozetlerini incele ve bos durumu duzelt"),
    ("temsilci-metin", "README guvenlik bolumunu gozden gecir, yanlis ifade varsa duzelt"),
    ("deniz-etiket", "etiket kuralini sifirdan yaz ve testlerle dogrula"),
    ("kizil-zarif", "gecmis bir haftanin gunluk istek grafigini acikla"),
]

DURUMLAR = ["bitti", "hata", "bitti", "onay-bekliyor"]

KOSU_LOG = """[uyari] ajan tanimi bulunamadi: panda-kodlayici (yalnizca istem gonderildi)
rozetleri okadim, dort rozet sinifi var: bekliyor, calisiyor, bitti, hata.
bitti durumu yesil, hata durumu kirmizi; ikisi de metin etiketi tasiyor.
onay-bekliyor durumunda isim yerine renk tek basina anlam tasimiyor.
kuyruk bos gorundugu icin bos-durum blogunu cizdim.
"""

KOSU_LOG_HATA = """[uyari] ajan tanimi bulunamadi: deniz-etiket (yalnizca istem gonderildi)
deneme 2: dosya kilitli, tekrar deniyorum.
dosya kilidi 5 saniye sonra cozulmedi; islem durduruldu.
"""

# Kurgusal kota: 14 günlük istek serisi.
KOTA_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"
KOTA_SERI = [12, 18, 9, 23, 31, 27, 14, 8, 19, 44, 41, 36, 29, 34]
LIMIT = 50

MASAUSTU = {"width": 1440, "height": 900}
MOBIL = {"width": 390, "height": 844}

HEDEFLER = [
    ("/", "kuyruk-masaustu.png", MASAUSTU),
    ("/gorev/1", "gorev-detay.png", MASAUSTU),
    ("/kota", "kota-masaustu.png", MASAUSTU),
    ("/", "kuyruk-mobil.png", MOBIL),
    ("/kota", "kota-mobil.png", MOBIL),
]


def _bos_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def kurgusal_db_kur(dizin: Path) -> tuple[Path, Path]:
    """Kurgusal görev + kota verili DB ve log dizini kurar."""
    db = dizin / "ekran.db"
    b = sqlite3.connect(db)
    b.executescript(SEMA)
    runs = dizin / "runs"
    runs.mkdir(exist_ok=True)

    for sira, ((ajan, istem), durum) in enumerate(zip(AJANLAR, DURUMLAR), start=1):
        b.execute(
            "INSERT INTO tasks (ajan,istem,durum,olusturma) VALUES (?,?,?,?)",
            (ajan, istem, durum, f"2026-09-{25 + sira:02d}T0{sira}:15:00Z"),
        )
        gorev_id = b.execute("SELECT last_insert_rowid()").fetchone()[0]
        log = runs / f"{gorev_id}.log"
        metin = KOSU_LOG_HATA if durum == "hata" else KOSU_LOG
        log.write_text(metin, encoding="utf-8")
        hata = "claude cikis kodu 1" if durum == "hata" else None
        bitis = None if durum == "onay-bekliyor" else f"2026-09-{25 + sira:02d}T0{sira}:16:20Z"
        b.execute(
            "INSERT INTO runs (task_id,baslangic,bitis,cikis_kodu,cikti_yolu,kanit_yollari,hata) "
            "VALUES (?,?,?,?,?,?,?)",
            (gorev_id, f"2026-09-{25 + sira:02d}T0{sira}:15:05Z", bitis,
             1 if durum == "hata" else 0, str(log), "[]", hata),
        )

    from datetime import datetime, timedelta, timezone

    bugun = datetime(2026, 9, 30, tzinfo=timezone.utc)
    for geri, adet in enumerate(reversed(KOTA_SERI)):
        gun = (bugun - timedelta(days=geri)).date().isoformat()
        b.execute(
            "INSERT INTO quota_snapshots (model,gun,istek,maliyet) VALUES (?,?,?,0)",
            (KOTA_MODEL, gun, adet),
        )
    b.commit()
    b.close()
    return db, runs


def sunucu_baslat(db: Path, runs: Path, toml: Path) -> tuple[subprocess.Popen, int]:
    port = _bos_port()
    surec = subprocess.Popen(
        [sys.executable, "-m", "orkestra", "--db", str(db), "web",
         "--port", str(port), "--cikti-dizini", str(runs), "--kota-toml", str(toml)],
        cwd=str(KOK), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    adres = f"http://127.0.0.1:{port}"
    for _ in range(100):
        if surec.poll() is not None:
            raise RuntimeError(f"orkestra web hemen sonlandi: {surec.stdout.read()[:400]}")
        try:
            urllib.request.urlopen(f"{adres}/saglik", timeout=1).read()
            return surec, port
        except (urllib.error.URLError, OSError):
            time.sleep(0.1)
    surec.kill()
    raise RuntimeError("orkestra web zamaninda acilmadi")


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Hata: playwright kurulu degil (pip install playwright).", file=sys.stderr)
        return 1

    cikti = KOK / "docs" / "ekran"
    cikti.mkdir(parents=True, exist_ok=True)

    gecici = Path(tempfile.mkdtemp(prefix="orkestra-ekran-"))
    try:
        db, runs = kurgusal_db_kur(gecici)
        toml = gecici / "kota.toml"
        toml.write_text(f'[limitler]\n"{KOTA_MODEL}" = {LIMIT}\n', encoding="utf-8")

        surec, port = sunucu_baslat(db, runs, toml)
        base = f"http://127.0.0.1:{port}"
        try:
            with sync_playwright() as p:
                tarayici = p.chromium.launch(args=["--no-sandbox"])
                for yol, ad, olcu in HEDEFLER:
                    sayfa = tarayici.new_page(viewport=olcu)
                    sayfa.goto(f"{base}{yol}", wait_until="networkidle")
                    sayfa.wait_for_timeout(300)
                    sayfa.screenshot(path=str(cikti / ad), full_page=True)
                    tasma = sayfa.evaluate(
                        "() => document.documentElement.scrollWidth > window.innerWidth"
                    )
                    sayfa.close()
                    print(f"  {ad}: yatay tasma={tasma}")
                tarayici.close()
        finally:
            surec.terminate()
            try:
                surec.wait(timeout=10)
            except subprocess.TimeoutExpired:
                surec.kill()
    finally:
        shutil.rmtree(gecici, ignore_errors=True)

    print(f"\n5 ekran goruntusu yazildi: {cikti}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
