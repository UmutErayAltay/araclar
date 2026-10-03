"""Paylaşım görseli (`og:image`): kart HTML'i üretir, sistemdeki tarayıcıyla 1200x630 PNG'ye çevirir.

Ek Python bağımlılığı yoktur. Tarayıcı bulunamazsa ya da çalışmazsa `png_uret` False döner ve
çağıran taraf sayfaya HİÇBİR `og:image` yazmaz (bozuk referans olmaz). Karta yalnız sayfada
zaten taranan alanlar girer (ad, unvan, yazı başlığı, tarih); PNG ikili olduğu için ayrıca taranamaz.
"""

from __future__ import annotations

import html
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

GENISLIK, YUKSEKLIK = 1200, 630
ZAMAN_ASIMI = 30
_ADAYLAR = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser")


def kart_html(baslik: str, alt_baslik: str = "", monogram: str = "") -> str:
    """1200x630 kart. Tüm metin kaçışlanır; uzun başlık 3 satırda kesilir."""
    b = html.escape(str(baslik), quote=True)
    a = html.escape(str(alt_baslik), quote=True)
    harf = html.escape((monogram or next((c for c in str(baslik) if c.strip()), "•"))[:1].upper(), quote=True)
    puntolar = 84 if len(str(baslik)) <= 28 else 64 if len(str(baslik)) <= 60 else 48
    return f"""<!doctype html>
<html lang="tr"><head><meta charset="utf-8"><style>
html, body {{ margin: 0; width: {GENISLIK}px; height: {YUKSEKLIK}px; overflow: hidden; }}
body {{ background: #1b1c1e; color: #ece9e0; display: flex; flex-direction: column; justify-content: center;
  padding: 0 88px; box-sizing: border-box; font-family: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; }}
.harf {{ width: 96px; height: 96px; border-radius: 22px; background: #e8a317; color: #1b1c1e; font-size: 56px; font-weight: 700;
  display: flex; align-items: center; justify-content: center; margin-bottom: 40px; }}
h1 {{ margin: 0; font-size: {puntolar}px; line-height: 1.12; font-weight: 700; display: -webkit-box;
  -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }}
p {{ margin: 28px 0 0; font-size: 36px; color: #b4b0a4; }}
</style></head><body><div class="harf">{harf}</div><h1>{b}</h1><p>{a}</p></body></html>
"""


def tarayici_bul(tarayici: str | None = None) -> str | None:
    """Verilen yol, `PORTFOLYO_TARAYICI` ya da PATH'teki bilinen Chrome/Chromium; yoksa None."""
    for aday in (tarayici, os.environ.get("PORTFOLYO_TARAYICI")):
        if aday:
            yol = shutil.which(aday)
            return yol if yol else None
    for ad in _ADAYLAR:
        yol = shutil.which(ad)
        if yol:
            return yol
    return None


def png_uret(kart: str, hedef: Path, tarayici: str | None = None) -> bool:
    """`kart` HTML'ini `hedef` PNG dosyasına çevirir. Her hata (tarayıcı yok, zaman aşımı, boş çıktı) → False."""
    exe = tarayici_bul(tarayici)
    if not exe:
        return False
    try:
        with tempfile.TemporaryDirectory(prefix="portfolyo-og-") as gecici:
            kok = Path(gecici)
            sayfa = kok / "kart.html"
            sayfa.write_text(kart, encoding="utf-8")
            cikti = kok / "kart.png"
            sonuc = subprocess.run(
                [
                    exe, "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
                    f"--window-size={GENISLIK},{YUKSEKLIK}", f"--user-data-dir={kok / 'profil'}",
                    f"--screenshot={cikti}", sayfa.as_uri(),
                ],
                capture_output=True, timeout=ZAMAN_ASIMI, check=False,
            )
            if sonuc.returncode != 0 or not cikti.is_file() or cikti.stat().st_size == 0:
                return False
            hedef.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(cikti, hedef)
            return True
    except (OSError, subprocess.SubprocessError):
        return False
