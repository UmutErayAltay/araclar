#!/usr/bin/env python3
"""README ekran görüntülerini üretir (Dalga C + Dalga D).

GÜVENLİK: Bu betik **tamamen kurgusal** veri kullanır. Gerçek yol, anahtar,
e-posta veya kişisel bilgi YOKTUR; ajan adları, istemler, kanıt dosyaları ve
kota sayıları burada uydurulur. Betik geçici bir DB kurar, `orkestra web`'i
başlatır, Playwright ile PNG alır ve `docs/ekran/` altına yazar.

    python3 scripts/ekran_goruntusu.py

Dalga D ekleri: kuyruk listesinde DÖRT FARKLI kanıt sonucu sınıfı (kanıtlı,
kanıtsız, başarısız, red şüphesi) birlikte görünür; görev detayında gözlemlenen
kanıtlar ve beyanlar AYRI listelerde durur. Görsel kanıt yolları metin olarak
gösterilir, panelde RESİM OLARAK GÖMÜLMEZ.

Playwright/Chromium yoksa betik açık hata verir (sessizce geçmez).
"""

from __future__ import annotations

import json
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from orkestra.queue import Queue  # noqa: E402

# -- KURGUSAL VERI ----------------------------------------------------------
# Bu isimler/ist metinler gerçek DEĞİLDİR; ekran görüntüleri için seçilmiştir.

AJANLAR = [
    ("panda-kodlayici", "kuyruk panelindeki durum rozetlerini incele ve bos durumu duzelt"),
    ("temsilci-metin", "README guvenlik bolumunu gozden gecir, yanlis ifade varsa duzelt"),
    ("deniz-etiket", "etiket kuralini sifirdan yaz ve testlerle dogrula"),
    ("kizil-zarif", "gecmis bir haftanin gunluk istek grafigini acikla"),
    ("poyraz-not", "gunluk rapor sablonunu yeniden yaz"),
]

DURUMLAR = ["bitti", "hata", "bitti", "onay-bekliyor", "bitti"]

# Dalga D: dört kanıt sonucu sınıfı KARIŞIK kuyrukta görünsün diye
# görevlerin son koşularına FARKLI kanıt durumları atanır.
#   1 kanitli · 2 kanitsiz · 3 basarisiz · 4 reddedildi-suphesi · 5 degerlendirilmedi
KANIT_SIRASI = ["kanitli", "kanitsiz", "basarisiz", "reddedildi-suphesi", "degerlendirilmedi"]

KOSU_LOG = """[uyari] ajan tanimi bulunamadi: panda-kodlayici (yalnizca istem gonderildi)
rozetleri okadim, dort rozet sinifi var: bekliyor, calisiyor, bitti, hata.
bitti durumu yesil, hata durumu kirmizi; ikisi de metin etiketi tasiyor.
onay-bekliyor durumunda isim yerine renk tek basina anlam tasimiyor.
"""

KOSU_LOG_HATA = """[uyari] ajan tanimi bulunamadi: deniz-etiket (yalnizca istem gonderildi)
deneme 2: dosya kilitli, tekrar deniyorum.
dosya kilidi 5 saniye sonra cozulmedi; islem durduruldu.
"""

# Kurgusal ajan raporları. Bunlar `report.degerlendir`'e beslenerek
# kanıt_ozeti üretir; içerik tamamen UYDURMADIR (gerçek proje/yol/sayı yok).
KOSU_LOG_KANITLI = """Rozet siniflarini yeniden yazdim ve bos durum blogunu ekledim.
Butun hizalama duzeltildi, sorunsuz.

## Kanit
- Test: pytest -q ekran/ → 14 passed in 0.42s
- Gorsel: ekran/kuyruk-kanitli.png — dort durum rozeti yan yana, tasma yok
"""

KOSU_LOG_BASARISIZ = """Etiket kuralini yazdim ama testlerden ikisi dustu.
## Kanit
- Test: pytest -q ekran/ → 2 failed, 12 passed in 0.51s
- Gorsel: ekran/etiket-basarisiz.png — uzun etiket kutu tasirdi
"""

KOSU_LOG_RED = """Gorevin kalanini ekleyemedim.
I was blocked from running the migration command by the permission layer.
## Kanit
- Test: pytest -q ekran/ → 12 passed in 0.40s
"""

KOSU_LOG_IDDIA = """Hizalama sorunu tamamen giderildi, her sey mükemmel.
## Kanit
- Test: pytest -q ekran/ → 18 passed in 0.55s
- Gorsel: ekran/yok-boyle-bir-dosya.png — iki etiket üst üste biniyor
"""


def _kanit_ozeti(kanit: str, *, gorsel: str = "", gecerli: bool = True,
                 gerekce: str = "gecerli png", git: bool | None = None,
                 iddia: str = "", beyan: str = "",
                 passed: int = 14, failed: int | None = None) -> str:
    """Kurgusal `kanit_ozeti` JSON'u (gerçek `report.Degerlendirme` biçiminde)."""
    return json.dumps(
        {
            "sonuc": kanit,
            "gorseller": ([{"yol": gorsel, "gecerli": gecerli, "gerekce": gerekce,
                            "cozulmus": gorsel, "bayt": 4096, "yeni_mi": True}]
                          if gorsel else []),
            "testler": ([{"tur": "pytest", "passed": passed, "failed": failed,
                           "error": None,
                           "metin": (f"{failed} failed, {passed} passed" if failed
                                     else f"{passed} passed in 0.42s")}]
                        if beyan else []),
            "iddialar": [iddia] if iddia else [],
            "beyanlar": [beyan] if beyan else [],
            "gorsel_beyanlar": [],
            "gerekceler": ([{"kural": "test-basarisiz", "sonuc": kanit,
                             "kanit": f"pytest: {failed} failed/0 error"}]
                           if failed else [])
                          + [{"kural": "gozlemlenen-kanit", "sonuc": kanit,
                              "kanit": gerekce}],
            "uyarilar": [],
            "git_degisti": git,
            "rapor_dosyasi": "",
            "kanit_durumu": kanit,
            "gozlemlenen_kanit_sayi": (1 if gecerli else 0) + (1 if git else 0),
        },
        ensure_ascii=False,
    )

# Kurgusal kota: 14 günlük istek serisi.
KOTA_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"
KOTA_SERI = [12, 18, 9, 23, 31, 27, 14, 8, 19, 44, 41, 36, 29, 34]
LIMIT = 50

MASAUSTU = {"width": 1440, "height": 900}
MOBIL = {"width": 390, "height": 844}

# ÖLÇÜLEBİLİR e2e kriterleri (Dalga C'den gelen, Dalga D ile genişletilmiş):
#  * yatay taşma yok
#  * görünür alanda beyaz varsayılan kontrol yok (metin kutusu gibi)
#  * yazı ≥ 11 px
#  * metin/arka plan kontrastı ≥ 4.5
#  * kanıt rozeti renk + METİN taşıyor (rozet_ok)
#  * içerik başlık çubuğunun arkasında kalmıyor (ust_tasma)
OLCUM_JS = """
() => {
  const lum = (c) => {
    const f = (v) => { v /= 255; return v <= 0.03928 ? v/12.92 : Math.pow((v+0.055)/1.055, 2.4); };
    return 0.2126*f(c[0]) + 0.7152*f(c[1]) + 0.0722*f(c[2]);
  };
  const parse = (s) => {
    const m = s.match(/[\\d.]+/g);
    return m ? m.map(Number) : [0,0,0,1];
  };
  const bgOf = (el) => {
    let n = el;
    while (n && n !== document.documentElement) {
      const bg = getComputedStyle(n).backgroundColor;
      const p = parse(bg);
      if (p.length === 3 || p[3] === 1) return p;
      n = n.parentElement;
    }
    return parse(getComputedStyle(document.body).backgroundColor);
  };
  const ratio = (a, b) => {
    const l1 = lum(a), l2 = lum(b);
    return (Math.max(l1,l2)+0.05) / (Math.min(l1,l2)+0.05);
  };
  const out = { tasma: document.documentElement.scrollWidth > window.innerWidth + 1,
                beyaz: 0, min_yazi: 999, min_kontrast: 99, rozet: 0,
                rozet_ok: true, ust_tasma: 0 };
  const rozetMetin = ['KANITLI','KANITSIZ','BAŞARISIZ','RED ŞÜPHESİ','DEĞERLENDİRİLMEDİ',
                      'kanıtlı','kanıtsız','başarısız','red şüphesi','değerlendirilmedi'];
  const text = document.body.innerText || '';
  for (const el of document.querySelectorAll('body *')) {
    if (!el.children.length && (el.textContent||'').trim()) {
      const st = getComputedStyle(el);
      if (st.display === 'none' || st.visibility === 'hidden') continue;
      const fs = parseFloat(st.fontSize);
      if (fs && fs < out.min_yazi) out.min_yazi = fs;
      const r = ratio(parse(st.color), bgOf(el));
      if (r < out.min_kontrast) out.min_kontrast = r;
      // Beyaz varsayılan kontrol: `input`/`textarea` arka planı beyaz mı?
      if (['INPUT','TEXTAREA','SELECT'].includes(el.tagName)) {
        const bg = parse(getComputedStyle(el).backgroundColor);
        if (bg[0] > 248 && bg[1] > 248 && bg[2] > 248) out.beyaz++;
      }
    }
  }
  const rozetler = document.querySelectorAll('.rozet.kanit-kanitli, .rozet.kanit-kanitsiz, '
    + '.rozet.kanit-basarisiz, .rozet.kanit-reddedildi-suphesi, .rozet.kanit-degerlendirilmedi');
  out.rozet = rozetler.length;
  if (out.rozet > 0) {
    for (const r of rozetler) {
      const m = rozetMetin.find(t => (r.textContent||'').toLowerCase().includes(t.toLowerCase()));
      if (!m) { out.rozet_ok = false; break; }
    }
  } else { out.rozet_ok = false; }
  // Başlık çubuğunun ARKASINDA kalan içerik var mı? Başlık `position:sticky`
  // DEĞİL; `h1` başlık çubuğunun İÇİNDEDİR ve bu tasma değildir. Bu yüzden
  // yalnız `main` altındaki başlıklar denetlenir.
  const bas = document.querySelector('header');
  if (bas) {
    const hb = bas.getBoundingClientRect();
    for (const el of document.querySelectorAll('main h1, main h2')) {
      const r = el.getBoundingClientRect();
      if (r.width > 0 && r.top < hb.bottom && r.bottom > hb.top) { out.ust_tasma++; break; }
    }
  }
  return out;
}
"""

HEDEFLER = [
    ("/", "kuyruk-masaustu.png", MASAUSTU),
    ("/gorev/1", "gorev-detay.png", MASAUSTU),
    ("/kota", "kota-masaustu.png", MASAUSTU),
    ("/", "kuyruk-mobil.png", MOBIL),
    ("/kota", "kota-mobil.png", MOBIL),
    # Dalga D: görev detayı masaüstü + mobil (gözlemlenen/beyan listeleri ayrı).
    ("/gorev/1", "gorev-detay-mobil.png", MOBIL),
    ("/gorev/3", "gorev-detay-basarisiz.png", MASAUSTU),
]


def _bos_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _kurgusal_png(dosya: Path, renk: tuple[int, int, int]) -> None:
    """KURGUSAL, gerçek geçerli bir PNG yazar (imzası doğru, boyutu > 0).

    Kanıt rozetlerinin "gözlemlenen" satırları bu dosyalara bakar; metin
    dosyasına `.png` demek yerine GERÇEK imza yazılır ki paneldeki
    "geçti" işareti yalan söylemesin. İçerik kare renk bloklarından ibarettir.
    """
    import struct
    import zlib

    g = 64
    satir = b"\x00" + bytes(renk) * g
    ham = satir * g

    def _parca(tur: bytes, veri: bytes) -> bytes:
        return (struct.pack(">I", len(veri)) + tur + veri
                + struct.pack(">I", zlib.crc32(tur + veri) & 0xFFFFFFFF))

    govde = (b"\x89PNG\r\n\x1a\n"
             + _parca(b"IHDR", struct.pack(">IIBBBBB", g, g, 8, 2, 0, 0, 0))
             + _parca(b"IDAT", zlib.compress(ham))
             + _parca(b"IEND", b""))
    dosya.parent.mkdir(parents=True, exist_ok=True)
    dosya.write_bytes(govde)


def kurgusal_db_kur(dizin: Path) -> tuple[Path, Path, Path]:
    """Kurgusal görev + kanıt + kota verili DB ve log dizini kurar.

    `Queue` gerçek şemayı kurar (Dalga D sütunları dahil); `SEMA` tek başına
    kullanılsaydı kanıt sütunları eksik kalırdı.
    """
    db = dizin / "ekran.db"
    kuyruk = Queue(db)
    b = kuyruk._baglanti
    runs = dizin / "runs"
    runs.mkdir(exist_ok=True)
    ekran = dizin / "ekran"
    ekran.mkdir(exist_ok=True)

    # Görev 1'in kanıtı GERÇEK dosyalara bakar (gözlemlenen kanıt).
    _kurgusal_png(ekran / "kuyruk-kanitli.png", (36, 92, 168))
    _kurgusal_png(ekran / "etiket-basarisiz.png", (176, 74, 12))
    # Görev 3'ün gördüğü dosya YOKTUR: iddia var ama kanıt yok -> "kanıtsız".

    kanit_ozetleri = {
        1: _kanit_ozeti("kanitli", gorsel="ekran/kuyruk-kanitli.png", git=True,
                         iddia="Hizalama sorunu tamamen giderildi.",
                         beyan="Test: pytest -q ekran/ → 14 passed in 0.42s"),
        2: _kanit_ozeti("kanitsiz", gorsel="ekran/yok-boyle-bir-dosya.png",
                         gecerli=False, gerekce="dosya diskte yok",
                         iddia="Etiket tasmasi sorunsuz cozuldu."),
        3: _kanit_ozeti("basarisiz", gorsel="ekran/etiket-basarisiz.png",
                         iddia="Etiket kurali yazildi.",
                         beyan="Test: pytest -q ekran/ → 2 failed, 12 passed in 0.51s",
                         passed=12, failed=2),
        4: _kanit_ozeti("reddedildi-suphesi", git=None,
                         iddia="Gorevin kalanini ekleyemedim.",
                         beyan="Test: pytest -q ekran/ → 12 passed in 0.40s"),
        5: _kanit_ozeti("degerlendirilmedi"),
    }
    log_metni = {
        1: KOSU_LOG_KANITLI, 2: KOSU_LOG_IDDIA, 3: KOSU_LOG_BASARISIZ,
        4: KOSU_LOG_RED, 5: KOSU_LOG,
    }

    for sira, ((ajan, istem), durum) in enumerate(zip(AJANLAR, DURUMLAR), start=1):
        b.execute(
            "INSERT INTO tasks (ajan,istem,durum,olusturma) VALUES (?,?,?,?)",
            (ajan, istem, durum, f"2026-09-{25 + sira:02d}T0{sira}:15:00Z"),
        )
        gorev_id = b.execute("SELECT last_insert_rowid()").fetchone()[0]
        log = runs / f"{gorev_id}.log"
        log.write_text(log_metni.get(sira, KOSU_LOG), encoding="utf-8")
        hata = "claude cikis kodu 1" if durum == "hata" else None
        if sira == 4:
            hata = "izin-reddi-suphesi"
        bitis = None if durum == "onay-bekliyor" else f"2026-09-{25 + sira:02d}T0{sira}:16:20Z"
        kanit = KANIT_SIRASI[sira - 1]
        b.execute(
            "INSERT INTO runs (task_id,baslangic,bitis,cikis_kodu,cikti_yolu,"
            "kanit_yollari,hata,kanit_durumu,kanit_ozeti) VALUES (?,?,?,?,?,?,?,?,?)",
            (gorev_id, f"2026-09-{25 + sira:02d}T0{sira}:15:05Z", bitis,
             1 if durum == "hata" else 0, str(log), "[]", hata, kanit,
             kanit_ozetleri[sira]),
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
    kuyruk.kapat()
    return db, runs, ekran


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
        db, runs, _ekran = kurgusal_db_kur(gecici)
        toml = gecici / "kota.toml"
        toml.write_text(f'[limitler]\n"{KOTA_MODEL}" = {LIMIT}\n', encoding="utf-8")

        surec, port = sunucu_baslat(db, runs, toml)
        base = f"http://127.0.0.1:{port}"
        olcumler: list[str] = []
        try:
            with sync_playwright() as p:
                tarayici = p.chromium.launch(args=["--no-sandbox"])
                for yol, ad, olcu in HEDEFLER:
                    sayfa = tarayici.new_page(viewport=olcu)
                    sayfa.goto(f"{base}{yol}", wait_until="networkidle")
                    sayfa.wait_for_timeout(300)
                    sayfa.screenshot(path=str(cikti / ad), full_page=True)
                    # ÖLÇÜLEBİLİR e2e kriterleri (Dalga C + D).
                    olcum = sayfa.evaluate(OLCUM_JS)
                    sayfa.close()
                    olcumler.append(
                        f"  {ad}: tasma={olcum['tasma']} "
                        f"beyaz_kutu={olcum['beyaz']} "
                        f"min_yazi={olcum['min_yazi']}px "
                        f"min_kontrast={olcum['min_kontrast']} "
                        f"rozet={olcum['rozet']} "
                        f"ust_taşma={olcum['ust_tasma']}"
                    )
                    if not olcum["rozet_ok"]:
                        print(f"  UYARI {ad}: kanit rozeti eksik", file=sys.stderr)
                tarayici.close()
        finally:
            surec.terminate()
            try:
                surec.wait(timeout=10)
            except subprocess.TimeoutExpired:
                surec.kill()
    finally:
        shutil.rmtree(gecici, ignore_errors=True)

    print("\n".join(olcumler))
    print(f"\n{len(HEDEFLER)} ekran goruntusu yazildi: {cikti}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
