"""Ekran goruntuleri: yalniz SAHTE veriyle. Paket disinda; calistirma:

    python3 yol/ekran/cek.py

Sunucu 127.0.0.1'de gecici bir porta kalkar; veri JSON'u ve yedek klasoru gecici dizindedir,
gercek PATH, kayit defteri ya da ~/.yol'a dokunmaz. Yazar: yol/ekran/*.png
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import threading

KLASOR = pathlib.Path(__file__).resolve().parent
KOK = KLASOR.parent
sys.path.insert(0, str(KOK))

GECICI = pathlib.Path(tempfile.mkdtemp(prefix="yol-ekran-"))
os.environ["YOL_DIR"] = str(GECICI / "veri")
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers")
# Sahte ortam: ad genislemesi icin (gercek kullanici bilgisi yok).
os.environ["SystemRoot"] = "C:\\Windows"
os.environ["USERPROFILE"] = "C:\\Users\\demo"
os.environ["LOCALAPPDATA"] = "C:\\Users\\demo\\AppData\\Local"

from playwright.sync_api import sync_playwright  # noqa: E402
from werkzeug.serving import make_server  # noqa: E402

from yol.kaynak import DosyaKaynak  # noqa: E402
from yol.web import uygulama_olustur  # noqa: E402

SAHTE_VERI = {
    "ayirici": ";",
    "windows": True,
    "sistem": {
        "Path": {
            "metin": "C:\\Windows\\system32;C:\\Windows;%SystemRoot%\\System32\\Wbem;C:\\Program Files\\Git\\cmd",
            "genisler": True,
        },
        "SystemRoot": {"metin": "C:\\Windows", "genisler": False},
        "JAVA_HOME": {"metin": "C:\\Program Files\\Java\\jdk-21", "genisler": False},
    },
    "kullanici": {
        "Path": {
            "metin": ";".join([
                "%USERPROFILE%\\bin",
                "C:\\Dev\\bin",
                "C:\\Dev\\node",
                "C:\\Dev\\bin",
                "C:\\Eski\\proje\\arac",
                "",
                "%LOCALAPPDATA%\\Microsoft\\WindowsApps",
                "C:\\Dev\\tools\\uv",
                "C:\\Program Files\\Git\\cmd",
            ]),
            "genisler": True,
        },
        "EDITOR": {"metin": "code --wait", "genisler": False},
        "API_TOKEN": {"metin": "sahte-anahtar-0000-ornek", "genisler": False},
        "PROJE_DIZINI": {"metin": "C:\\Dev\\ornek-proje", "genisler": False},
    },
}

# Sahte dosya sistemi: yalnizca bunlar 'var' sayilir (gercek diske bakmaz).
VAR_DIZIN_ONEKLERI = ("c:\\dev", "c:\\windows", "c:\\users\\demo", "c:\\program files")
VAR_DOSYALAR = {
    "c:\\dev\\bin\\python.exe", "c:\\dev\\bin\\git.exe", "c:\\dev\\node\\node.exe",
    "c:\\dev\\node\\npm.cmd", "c:\\dev\\tools\\uv\\uv.exe",
    "c:\\users\\demo\\appdata\\local\\microsoft\\windowsapps\\python.exe",
    "c:\\windows\\system32\\where.exe", "c:\\program files\\git\\cmd\\git.exe",
    "c:\\program files\\java\\jdk-21\\bin\\java.exe",
}


def sahte_dizin_var(yol: str) -> bool:
    return yol.casefold().startswith(VAR_DIZIN_ONEKLERI)


def sahte_dosya_var(yol: str) -> bool:
    return yol.casefold() in VAR_DOSYALAR


def sunucuyu_baslat(uygulama):
    sunucu = make_server("127.0.0.1", 0, uygulama, threaded=True)
    thread = threading.Thread(target=sunucu.serve_forever, daemon=True)
    thread.start()
    return sunucu, f"http://127.0.0.1:{sunucu.server_port}/"


def sayfa_hazir(sayfa):
    sayfa.wait_for_selector("#yol-kullanici .yol-satir")
    sayfa.wait_for_function("document.querySelector('#ozet-girdi').textContent !== '–'")


def main() -> int:
    veri_yolu = GECICI / "ortam.json"
    veri_yolu.write_text(json.dumps(SAHTE_VERI, ensure_ascii=False, indent=2), encoding="utf-8")
    kaynak = DosyaKaynak(veri_yolu)
    uygulama = uygulama_olustur(kaynak, dizin_var=sahte_dizin_var, dosya_var=sahte_dosya_var)
    uygulama.config["TESTING"] = True
    sunucu, adres = sunucuyu_baslat(uygulama)

    hatalar: list[str] = []
    try:
        with sync_playwright() as p:
            tarayici = p.chromium.launch(args=["--no-sandbox"])
            konfigurasyonlar = [
                ("masaustu-acik", {"width": 1280, "height": 800}, "light"),
                ("masaustu-koyu", {"width": 1280, "height": 800}, "dark"),
                ("mobil-acik", {"width": 390, "height": 844}, "light"),
                ("mobil-koyu", {"width": 390, "height": 844}, "dark"),
            ]
            for ad, boyut, tema in konfigurasyonlar:
                baglam = tarayici.new_context(viewport=boyut, color_scheme=tema,
                                              device_scale_factor=1)
                sayfa = baglam.new_page()
                sayfa.on("pageerror", lambda e: hatalar.append(f"{ad}: {e}"))
                sayfa.on("console", lambda m: hatalar.append(f"{ad} konsol: {m.text}")
                         if m.type == "error" else None)
                sayfa.goto(adres)
                sayfa_hazir(sayfa)
                sayfa.screenshot(path=str(KLASOR / f"{ad}.png"), full_page=True)
                baglam.close()

            # Onizleme: masaustu acik temada, taslaga bir kaldirma ekleyip onizleme acilir.
            baglam = tarayici.new_context(viewport={"width": 1280, "height": 800}, color_scheme="light")
            sayfa = baglam.new_page()
            sayfa.on("pageerror", lambda e: hatalar.append(f"onizleme: {e}"))
            sayfa.goto(adres)
            sayfa_hazir(sayfa)
            # Dördüncü girdi ("C:\\Dev\\bin" tekrarı) taslaktan kaldırılır.
            sayfa.locator("#yol-kullanici .yol-satir").nth(3).get_by_role(
                "button", name="kaldır").click()
            sayfa.locator("#taslak-onizle").click()
            sayfa.wait_for_selector("#onizleme:not([hidden])")
            sayfa.locator("#onizleme").screenshot(path=str(KLASOR / "onizleme.png"))
            baglam.close()
            tarayici.close()
    finally:
        sunucu.shutdown()

    if hatalar:
        print("JS hatalari:")
        for h in hatalar:
            print(" ", h)
        return 1
    print("ekran goruntuleri yazildi:", ", ".join(sorted(p.name for p in KLASOR.glob("*.png"))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
