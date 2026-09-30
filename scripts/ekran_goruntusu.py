"""README ekran görüntülerini üretir (Dalga B).

KURGUSAL mini-vault: aşağıdaki notlar bu betiğin İÇİNDE uydurulur. Gerçek
vault'tan HİÇBİR başlık, yol, özet veya e-posta görüntüye girmez.

Çıktı: `docs/ekran/graf-masaustu.png`, `graf-panel-acik.png`,
`graf-mobil.png`, `kirik-liste.png`.

Kullanım:
    python3 scripts/ekran_goruntusu.py            # docs/ekran/ altına yazar
    python3 scripts/ekran_goruntusu.py --kaynak DIR
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

from harita.index import indeksle  # noqa: E402
from harita.web.sunucu import app_olustur  # noqa: E402

# ---------------------------------------------------------------------------
# KURGUSAL içerik. Buradaki hiçbir metin gerçek veri değildir.
# ---------------------------------------------------------------------------

KURGUSAL_NOTLAR: dict[str, str] = {
    "📐 Geometri/Kafes Teorisi.md": """---
title: Kafes Teorisi Notları
tags: [matematik, notlar]
---
# Kafes Teorisi Notları

Merkezi kafeslerin dört temel özelliği: değişmez alt kafes, atomik eleman,
bağımsız atomlar ve taban eleman. Kafesler arası homomorfizma sınıfları bu
dört özelliğe göre ayrılır. #matematik

Bağlantılar: [[Lattice Morphism]] ve [[Bölüm Halkaları]]
""",
    "📐 Geometri/Lattice Morphism.md": """---
title: Kafes Homomorfizmaları
aliases: [lattice morphism]
tags: [matematik]
---
# Kafes Homomorfizmaları

Bir kafes homomorfizması, birleşim ve kesişim işlemlerini koruyan
fonksiyondur. Çekirdek ve görüntü alt kafesleri incelenir.

Devamı: [[Kafes Teorisi Notları]]
""",
    "🎨 Tasarım/Ölçek Sistemi.md": """---
title: Ölçek Sistemi
tags: [tasarim, arayuz]
---
# Ölçek Sistemi

Arayüzde 4 px tabanlı bir ölçek kullanılır. Renkler Okabe-Ito paletinden
seçilir; kontrast oranı en az 4.5:1 olmalıdır. #tasarim

İlgili: [[Koyu Tema Denklikleri]]
""",
    "🎨 Tasarım/Koyu Tema Denklikleri.md": """---
title: Koyu Tema Denklikleri
tags: [tasarim, renk]
---
# Koyu Tema Denklikleri

Zemin `#0f1115`, metin `#e6e6e6`, ikincil metin `#9aa3b2`. Doygun
paletler koyu zeminde parlak görünür; doygunluk düşürülerek dengelenir.

Öncesi: [[Ölçek Sistemi]]
""",
    "🧩 Mühendislik/Önbellek Stratejileri.md": """---
title: Önbellek Stratejileri
tags: [mimari, performans]
---
# Önbellek Stratejileri

Üç katman: süreç içi sözlük, disk üzerinde dosya ve uzak önbellek.
Geçersiz kılma stratejisi yazma sırasında anahtar döndürmedir. #mimari

Bağlı: [[Kuyruk Tasarımı]] ve [[Ölçüm Notları]]
""",
    "🧩 Mühendislik/Kuyruk Tasarımı.md": """---
title: Kuyruk Tasarımı
tags: [mimari]
---
# Kuyruk Tasarımı

İş kuyruğu geri baskı (backpressure) destekler. Yeniden deneme üstel
geri çekilmeyle sınırlıdır; ölü mektup kutusu ayrı bir depoya taşınır.
""",
    "🧪 Deneyler/Tuş Eşlemesi.md": """---
title: Tuş Eşlemesi Deneyi
tags: [deney, arayuz]
---
# Tuş Eşlemesi Deneyi

Beş farklı tuş düzeni karşılaştırıldı. Kısayol tuşları öğrenme süresini
belirgin biçimde düşürdü. #deney

Kontrol grubu: [[Kullanıcı Araştırması]]
""",
    "🧪 Deneyler/Kullanıcı Araştırması.md": """---
title: Kullanıcı Araştırması
tags: [deney]
---
# Kullanıcı Araştırması

On iki katılımcıyla yarı yapılandırılmış görüşme. Görev başarı oranı
ve ilk etkileşim süresi ölçüldü. Katılımcı kodları kurgusaldır.
""",
    "📚 Kaynaklar/Okuma Listesi.md": """---
title: Okuma Listesi
tags: [kaynak]
---
# Okuma Listesi

- Kafes teorisi el kitapları
- Arayüz ölçek sistemi kılavuzları
- Kuyruk tabanlı mimari makaleleri

Bağlantı: [[Eksik Referans Notu]]
""",
    "📚 Kaynaklar/Bağımsız Çalışma.md": """---
title: Bağımsız Çalışma
tags: [kaynak]
---
# Bağımsız Çalışma

Deney tasarımı için bağımsız bir çalışma notu tutulur. Deniz seviyesi,
kimyasal bileşikler ve parçacık hızları üzerine denemeler.
""",
    "daily/2026-03-01.md": """---
title: Günlük 2026-03-01
tags: [gunluk]
---
# Günlük 2026-03-01

Kafes notlarını genişlettim. Ölçek sistemi için koyu tema denkliklerini
tamamladım. Yarın önbellek stratejilerine bakacağım.
""",
    "daily/2026-03-02.md": """---
title: Günlük 2026-03-02
tags: [gunluk]
---
# Günlük 2026-03-02

Tuş eşlemesi deneyini başlattım. Etiket sistemi biraz dağınık.
""",
    "README.md": """---
title: Kurgusal Demo Kütüphanesi
---
# Kurgusal Demo Kütüphanesi

Bu kütüphane `harita` aracının ekran görüntüleri için üretilmiştir.
Tüm içerik uydurmadır. #demo
""",
    "CLAUDE.md": """---
title: Kurgusal Çalışma Talimatı
---
# Kurgusal Çalışma Talimatı

Bu dosya demo içindir. Gerçek bir çalışma talimatı değildir.
""",
    "📦 Depo/Hiç Bağlanmayan Not.md": """---
title: Hiç Bağlanmayan Not
---
# Hiç Bağlanmayan Not

Bu not ne link verir ne link alır. Grafın uçlarından biridir; bağlanmayı
bekleyen bir taslak olarak tutulur.
""",
}

# Ekran görüntüsü senaryoları için seçilen kırık hedefler.
KIRIK_HEDEFLER = [
    "Kırık Kaynak Notu",
    "Eksik Deney Raporu",
    "Silinmiş Prototip",
]


def kurgusal_vault(kok: Path) -> Path:
    """KURGUSAL demo vault'unu `kok` altına yazar."""
    vault = kok / "demo-vault"
    for goreli, icerik in KURGUSAL_NOTLAR.items():
        yol = vault / goreli
        yol.parent.mkdir(parents=True, exist_ok=True)
        yol.write_text(icerik, encoding="utf-8")
    # Kırık link üreten üç kaynak not (graf ve /kirik ekranı için).
    govde = "\n\n".join(f"[[{hedef}]]" for hedef in KIRIK_HEDEFLER)
    yol = vault / "📚 Kaynaklar/Eksik Referanslar.md"
    yol.write_text(
        f"---\ntitle: Eksik Referans Notu\ntags: [kaynak]\n---\n"
        f"# Eksik Referans Notu\n\nHenüz yazılmamış kaynaklar: {govde}\n",
        encoding="utf-8",
    )
    return vault


def chromium_yolu() -> str | None:
    for kalip in (
        "/opt/pw-browsers/chromium-*/chrome-linux*/chrome",
        "/opt/pw-browsers/chromium-*/chrome-linux/chrome",
        "/opt/pw-browsers/chromium_headless_shell-*/chrome-linux*/headless_shell",
        "/opt/pw-browsers/chromium_headless_shell-*/chrome-linux/headless_shell",
    ):
        adaylar = sorted(Path("/").glob(kalip.lstrip("/")))
        if adaylar:
            return str(adaylar[-1])
    return None


def _ac(p):
    """Chromium'u açar; hazır yol yoksa varsayılana güvenir."""
    bayraklar = ["--no-sandbox", "--force-color-profile=srgb", "--font-render-hinting=none"]
    try:
        return p.chromium.launch(args=bayraklar)
    except Exception as hata:  # pragma: no cover - ortam bağımlı
        yol = chromium_yolu()
        if not yol:
            raise SystemExit(f"Chromium bulunamadı: {str(hata)[:200]}")
        return p.chromium.launch(executable_path=yol, args=bayraklar)


def ekran_goruntuleri_al(kaynak: Path) -> list[Path]:
    """Dört PNG üretir; üretilen yolları döndürür."""
    from playwright.sync_api import sync_playwright

    db = kaynak / "demo.db"
    indeksle(kurgusal_vault(kaynak), db)

    uygulama = app_olustur(db)
    cikti = KOK / "docs" / "ekran"
    cikti.mkdir(parents=True, exist_ok=True)

    uretilen: list[Path] = []

    # Flask'ın kendi sunucusu: aynı uygulama, gerçek HTTP, yalnız loopback.
    import threading

    from werkzeug.serving import make_server

    http = make_server("127.0.0.1", 0, uygulama, threaded=True)
    port = http.server_port
    is_parcacigi = threading.Thread(target=http.serve_forever, daemon=True)
    is_parcacigi.start()
    taban = f"http://127.0.0.1:{port}"

    try:
        with sync_playwright() as p:
            tarayici = _ac(p)
            try:
                # 1) Masaüstü graf
                sayfa = tarayici.new_page(viewport={"width": 1440, "height": 900})
                sayfa.goto(taban, wait_until="load")
                sayfa.wait_for_selector("body[data-hazir]")
                sayfa.wait_for_timeout(400)
                yol = cikti / "graf-masaustu.png"
                sayfa.screenshot(path=str(yol))
                uretilen.append(yol)

                # 2) Panel açık: derecesi en yüksek düğüm GERÇEK tıklamayla seçilir.
                hedef_sira = sayfa.evaluate(
                    """() => {
                        const dugumler = [...document.querySelectorAll('#graf .dugum')];
                        let enIyi = 0, enCok = -1;
                        dugumler.forEach((d, i) => {
                            const derece = Number(d.dataset.derece || 0);
                            if (derece > enCok) { enCok = derece; enIyi = i; }
                        });
                        return enIyi;
                    }"""
                )
                # Tıklama DÜĞÜMÜN DAİRESİNE yapılır: `<g>` kutusu etiket metnini
                # de içerdiğinden merkezi dairenin dışına düşebilir.
                merkez = sayfa.evaluate(
                    """(i) => {
                        const c = document.querySelectorAll('#graf .dugum')[i].querySelector('circle');
                        const r = c.getBoundingClientRect();
                        return {x: r.x + r.width / 2, y: r.y + r.height / 2};
                    }""",
                    hedef_sira,
                )
                sayfa.mouse.move(merkez["x"], merkez["y"])
                sayfa.mouse.down()
                sayfa.wait_for_timeout(60)
                sayfa.mouse.up()
                sayfa.wait_for_selector("#panel:not([hidden])", timeout=10000)
                sayfa.wait_for_timeout(350)
                yol = cikti / "graf-panel-acik.png"
                sayfa.screenshot(path=str(yol))
                uretilen.append(yol)
                sayfa.close()

                # 3) Kırık link listesi
                sayfa = tarayici.new_page(viewport={"width": 1440, "height": 900})
                sayfa.goto(f"{taban}/kirik", wait_until="load")
                sayfa.wait_for_selector(".tablo tbody tr")
                sayfa.wait_for_timeout(200)
                yol = cikti / "kirik-liste.png"
                sayfa.screenshot(path=str(yol))
                uretilen.append(yol)
                sayfa.close()

                # 4) Mobil görünüm (390x844)
                sayfa = tarayici.new_page(viewport={"width": 390, "height": 844})
                sayfa.goto(taban, wait_until="load")
                sayfa.wait_for_selector("body[data-hazir]")
                sayfa.wait_for_timeout(400)
                yol = cikti / "graf-mobil.png"
                sayfa.screenshot(path=str(yol))
                uretilen.append(yol)
                sayfa.close()
            finally:
                tarayici.close()
    finally:
        http.shutdown()
    return uretilen


def main() -> int:
    ayristirici = argparse.ArgumentParser(description=__doc__)
    ayristirici.add_argument("--kaynak", default=None, help="Geçici çalışma dizini")
    args = ayristirici.parse_args()

    gecici = None
    if args.kaynak:
        kaynak = Path(args.kaynak)
        kaynak.mkdir(parents=True, exist_ok=True)
    else:
        gecici = tempfile.TemporaryDirectory(prefix="harita-gorsel-")
        kaynak = Path(gecici.name)

    try:
        uretilen = ekran_goruntuleri_al(kaynak)
    finally:
        if gecici is not None:
            gecici.cleanup()

    for yol in uretilen:
        print(yol.relative_to(KOK))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())