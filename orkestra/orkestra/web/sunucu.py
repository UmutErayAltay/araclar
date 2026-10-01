"""Salt-okunur Flask paneli (Dalga C): kuyruk, görev detayı, kota.

Güvenlik (bağlayıcı):
  * Sunucu koda sabit `127.0.0.1` adresine bağlanır; `--host` seçeneği YOKTUR.
  * `Host` başlığı `127.0.0.1[:port]` / `localhost[:port]` değilse 403 — ve reddedilen
    istek bağlantı AÇILMADAN, hiçbir sorguya dokunmadan döner.
  * DB `mode=ro` (URI) ile açılır; panel hiçbir koşulda YAZMAZ.
  * Panel YALNIZCA görüntüler: iptal/tekrar CLI'dadır. Rota yüzeyi salt-GET'tir
    (diğer metotlar 405), dolayısıyla CSRF yüzeyi yoktur.
  * `istem`, `ajan`, `hata` ve log İÇERİĞİ güvenilmeyendir: Jinja autoescape
    açıktır, JS `textContent` kullanır (innerHTML yok), log `<pre>` içindedir.
  * Log dosyası yolu DB'den gelir: çözümlenmiş yol `--cikti-dizini` ALTINDA olmalıdır;
    dışarı çıkan (sembolik link dahil) yollar "log okunamadı" olarak gösterilir.
  * Ekrana çıkan HER metin (log dahil) `guard.maskele()`'den geçer.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path

from flask import Flask, Response, abort, current_app, g, jsonify, render_template, request

from .. import guard, quota, report

# DNS rebinding koruması: yalnızca gerçek loopback adresleri.
HOST_DESENI = re.compile(r"^(127\.0\.0\.1|localhost)(:\d{1,5})?$", re.IGNORECASE)

CSP = (
    "default-src 'none'; "
    "script-src 'self'; "
    "style-src 'self'; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "base-uri 'none'; "
    "form-action 'none'; "
    "frame-ancestors 'none'"
)

# İframe ebeveyni izni: yalnızca http://127.0.0.1:port veya http://localhost:port
KULE_FRAME_ORIGIN_RE = re.compile(r"^http://(127\.0\.0\.1|localhost):[0-9]{1,5}$")


def csp() -> str:
    """Her istekte CSP üretir: KULE_FRAME_ORIGIN kalıba uyarsa frame-ancestors açar."""
    origin = os.environ.get("KULE_FRAME_ORIGIN", "")
    if KULE_FRAME_ORIGIN_RE.fullmatch(origin):
        return CSP.replace("frame-ancestors 'none'", f"frame-ancestors {origin}")
    return CSP


# Renk körü-güvenli palet (Okabe-Ito). Sıra sabittir; `panel.js` aynı sırayı
# kullanır, böylece durum rozeti ile lejant/graf rengi aynıdır.
OKABE_ITO = (
    "#E69F00",
    "#56B4E9",
    "#009E73",
    "#F0E442",
    "#0072B2",
    "#D55E00",
    "#CC79A7",
    "#999999",
)

DURUM_RENKLERI = {
    "bekliyor": "#E69F00",
    "calisiyor": "#56B4E9",
    "bitti": "#009E73",
    "hata": "#D55E00",
    "onay-bekliyor": "#CC79A7",
    "iptal": "#999999",
}

# Rozet metni ASCII durum adı DEĞİL: renge tek başına dayanmaz (erişilebilirlik).
DURUM_ETIKETLERI = {
    "bekliyor": "bekliyor",
    "calisiyor": "çalışıyor",
    "bitti": "bitti",
    "hata": "hata",
    "onay-bekliyor": "onay bekliyor",
    "iptal": "iptal",
}

DURUM_DUZENI = re.compile(r"^[a-z-]{1,20}$")
LOG_SON_SATIR = 200
ISTEM_ONIZLEME = 100
VARSAYILAN_CIKTI_DIZINI = Path.home() / ".orkestra" / "runs"

# Dalga D kanıt rozetleri: renk + METİN (renge tek başına dayanmaz).
KANIT_RENKLERI = {
    report.KANITLI: "#009E73",       # Okabe-Ito yeşil
    report.KANITSIZ: "#E69F00",      # turuncu
    report.BASARISIZ: "#D55E00",     # kırmızı-turuncu
    report.REDDEDILDI: "#CC79A7",    # pembe
    report.DEGERLENDIRILMEDI: "#999999",
}
# Kanıt uyarısı taşıyan sınıflar: `liste`de ve detayda vurgulanır.
KANIT_UYARI = frozenset({report.KANITSIZ, report.BASARISIZ, report.REDDEDILDI})


def kanit_rozeti(satir) -> dict:
    """Bir koşu satırından kanıt rozeti üretir (eski DB'de alan YOKTUR).

    Sütun yoksa `degerlendirilmedi` döner — eski şema paneli BOZMAZ.
    """
    anahtarlar = satir.keys()
    durum = satir["kanit_durumu"] if "kanit_durumu" in anahtarlar else None
    if not durum or durum not in KANIT_RENKLERI:
        durum = report.DEGERLENDIRILMEDI
    return {
        "durum": durum,
        "etiket": report.SONUC_ETIKETLERI.get(durum, durum),
        "renk": KANIT_RENKLERI[durum],
        "uyari": durum in KANIT_UYARI,
    }


def guvenli_basliklar(cevap: Response) -> Response:
    """Her yanıta bağlayıcı güvenlik başlıklarını ekler."""
    cevap.headers["Content-Security-Policy"] = csp()
    cevap.headers["X-Content-Type-Options"] = "nosniff"
    cevap.headers["Referrer-Policy"] = "no-referrer"
    cevap.headers["Cache-Control"] = "no-store"
    return cevap


# -- salt-okunur veritabanı --------------------------------------------------


def db_ac(yol: Path | str) -> sqlite3.Connection:
    """DB'yi `mode=ro` ile açar; hiçbir koşulda yazmaz."""
    yol = Path(yol).expanduser()
    baglanti = sqlite3.connect(f"file:{yol}?mode=ro", uri=True)
    baglanti.row_factory = sqlite3.Row
    return baglanti


def _baglanti_al() -> sqlite3.Connection:
    if "orkestra_db" not in g:
        g.orkestra_db = db_ac(current_app.config["ORKESTRA_DB"])
    return g.orkestra_db


def _baglanti_kapat(_hata: BaseException | None = None) -> None:
    baglanti = g.pop("orkestra_db", None)
    if baglanti is not None:
        baglanti.close()


# -- veri okuma --------------------------------------------------------------


def _temizle(metin: str | None) -> str:
    """Ekrana/JSON'a çıkacak metni maskeler (savunma katmanı)."""
    return guard.maskele(metin) if isinstance(metin, str) else ""


def istem_onizleme(istem: str) -> str:
    """Tek satıra indirgenmiş, kısaltılmış VE MASKELİ istem (ilk 100 karakter).

    Maskeleme kısaltmadan SONRA uygulanır: 100. karakterde yarım kalan bir
    anahtarın kuyruğu da sızdırmasın diye, önce metin kesilir, sonra maskelenir.
    """
    tek = " ".join((istem or "").split())
    return guard.maskele(tek[:ISTEM_ONIZLEME])


def _satirdan_gorev(satir, baglanti: sqlite3.Connection | None = None) -> dict:
    kayit = {
        "id": satir["id"],
        "ajan": _temizle(satir["ajan"]),
        "istem": istem_onizleme(satir["istem"]),
        "durum": satir["durum"],
        "durum_etiket": DURUM_ETIKETLERI.get(satir["durum"], satir["durum"]),
        "olusturma": satir["olusturma"],
    }
    if baglanti is not None:
        rozet = _son_kosu_kaniti(baglanti, satir["id"])
        kayit["kanit"] = rozet or {
            "durum": report.DEGERLENDIRILMEDI,
            "etiket": report.SONUC_ETIKETLERI[report.DEGERLENDIRILMEDI],
            "renk": KANIT_RENKLERI[report.DEGERLENDIRILMEDI],
            "uyari": False,
        }
    return kayit


def gorevleri(baglanti: sqlite3.Connection, durum: str | None = None) -> list[dict]:
    """En yeni üstte olacak şekilde görev listesi.

    Her kayıt görevin SON koşusunun kanıt rozetini de taşır (yoksa
    "değerlendirilmedi"). Alt sorgu ESKİ DB'de de çalışır: sütun yoksa
    `runs` taraması boş döner.
    """
    if durum and DURUM_DUZENI.match(durum):
        sql = "SELECT * FROM tasks WHERE durum = ? ORDER BY id DESC"
        parametre: tuple = (durum,)
    else:
        sql = "SELECT * FROM tasks ORDER BY id DESC"
        parametre = ()
    return [_satirdan_gorev(s, baglanti) for s in baglanti.execute(sql, parametre)]


def _son_kosu_kaniti(
    baglanti: sqlite3.Connection, gorev_id: int
) -> dict | None:
    """Görevin son koşusunun kanıt rozetini döndürür; yoksa `None`."""
    try:
        satir = baglanti.execute(
            "SELECT * FROM runs WHERE task_id = ? ORDER BY id DESC LIMIT 1",
            (int(gorev_id),),
        ).fetchone()
    except sqlite3.OperationalError:
        # `runs.kanit_durumu` yok (eskiden başka bir şema): sessizce "değerlendirilmedi".
        return None
    return kanit_rozeti(satir) if satir is not None else None


def _kosular(baglanti: sqlite3.Connection, gorev_id: int) -> list[dict]:
    satirlar = baglanti.execute(
        "SELECT * FROM runs WHERE task_id = ? ORDER BY id", (int(gorev_id),)
    ).fetchall()
    kosular = []
    for satir in satirlar:
        kanit = satir["kanit_yollari"]
        try:
            kanit_listesi = json.loads(kanit) if kanit else []
        except (TypeError, ValueError):
            kanit_listesi = []
        ozet = None
        if "kanit_ozeti" in satir.keys() and satir["kanit_ozeti"]:
            try:
                ozet = json.loads(satir["kanit_ozeti"])
            except (TypeError, ValueError):
                ozet = None
        kosular.append(
            {
                "id": satir["id"],
                "baslangic": satir["baslangic"],
                "bitis": satir["bitis"],
                "cikis_kodu": satir["cikis_kodu"],
                "log_yolu": _temizle(satir["cikti_yolu"]),
                "kanit": [_temizle(k) for k in kanit_listesi],
                "hata": _temizle(satir["hata"]) if satir["hata"] else "",
                "kanit_rozet": kanit_rozeti(satir),
                # Gözlemlenen kanıtlar ve beyanlar AYRI listelenir.
                "gozlemlenen": _gozlemlenen_listesi(ozet),
                "beyan": _beyan_listesi(ozet),
                "gerekceler": _gerekce_listesi(ozet),
                "uyarilar": [_temizle(u) for u in (ozet or {}).get("uyarilar", [])],
            }
        )
    return kosular


def _gozlemlenen_listesi(ozet: dict | None) -> list[dict]:
    """GÖZLEMLENEN kanıtlar (orkestra'nın kendi baktığı)."""
    if not ozet:
        return []
    liste = []
    for g in ozet.get("gorseller", []):
        liste.append(
            {
                "gecerli": bool(g.get("gecerli")),
                "yol": _temizle(g.get("yol", "")),
                "gerekce": _temizle(g.get("gerekce", "")),
            }
        )
    if ozet.get("git_degisti") is not None:
        liste.append(
            {
                "gecerli": True,
                "yol": "git çalışma ağacı/HEAD",
                "gerekce": "değişti" if ozet["git_degisti"] else "değişmedi",
            }
        )
    return liste


def _beyan_listesi(ozet: dict | None) -> list[str]:
    """BEYANLAR (yalnızca metinde yazan) — kanıt sayılmaz."""
    if not ozet:
        return []
    liste: list[str] = []
    for t in ozet.get("testler", []):
        sayilar = f"{t.get('passed') or 0} test geçti"
        if t.get("failed"):
            sayilar += f", {t['failed']} başarısız"
        if t.get("error"):
            sayilar += f", {t['error']} hata"
        liste.append(f"test: {sayilar}")
    for i in ozet.get("iddialar", [])[:10]:
        liste.append(f"iddia: {i}")
    return [_temizle(x) for x in liste]


def _gerekce_listesi(ozet: dict | None) -> list[dict]:
    if not ozet:
        return []
    return [
        {"kural": _temizle(g.get("kural", "")), "kanit": _temizle(g.get("kanit", ""))}
        for g in ozet.get("gerekceler", [])
    ]


def gorev_detay(baglanti: sqlite3.Connection, gorev_id: int) -> dict | None:
    satir = baglanti.execute(
        "SELECT * FROM tasks WHERE id = ?", (int(gorev_id),)
    ).fetchone()
    if satir is None:
        return None
    detay = _satirdan_gorev(satir, baglanti)
    # Detayda istem kısaltılmaz: kullanıcı tam istemi görmek ister.
    detay["istem"] = _temizle(satir["istem"])
    detay["kosular"] = _kosular(baglanti, gorev_id)
    return detay


# -- log okuma (yol kaçışı koruması) ----------------------------------------


def guvenli_log_yolu(
    ham_yol: str | None, kok: Path
) -> Path | None:
    """DB'deki log yolunu doğrular; çözümlenmiş hâli `kok` ALTINDA değilse `None`.

    `..`, mutlak yol ve dışarıya işaret eden sembolik link reddedilir: `resolve()`
    + `is_relative_to` çifti sembolik linki de çözer, karşılaştırma çözülmüş
    yol üzerinden yapılır.
    """
    if not ham_yol:
        return None
    try:
        aday = Path(ham_yol).expanduser()
        if not aday.is_absolute():
            aday = kok / aday
        cozulmus = aday.resolve()
        kok_c = kok.expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return None
    if cozulmus == kok_c or not cozulmus.is_relative_to(kok_c):
        return None
    return cozulmus


def log_son_satirlar(ham_yol: str | None, kok: Path, adet: int = LOG_SON_SATIR) -> dict:
    """Log'un son `adet` satırını maskeli döndürür.

    Dosya yoksa/erişilemiyorsa `{"ok": False, ...}` — panel "log okunamadı" der.
    """
    yol = guvenli_log_yolu(ham_yol, kok)
    if yol is None or not yol.is_file():
        return {"ok": False, "metin": "", "satir": 0, "yol": ""}
    try:
        metin = yol.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"ok": False, "metin": "", "satir": 0, "yol": ""}
    satirlar = metin.splitlines()
    son = satirlar[-adet:]
    return {
        "ok": True,
        # Maskeleme EKRANA BASILMADAN önce: log içeriği de güvenilmeyendir.
        "metin": guard.maskele("\n".join(son)),
        "satir": len(son),
        "yol": _temizle(str(yol)),
    }


# -- grafik geometrisi -------------------------------------------------------

# Sabit taban genişlik: SVG `max-width` ile bundan büyüğe ÇIKMAZ, böylece
# viewport ne olursa olsun 11 px yazı gerçekten 11 px kalır (ölçülebilir).
GRAF_TABAN = 340
GRAF_YUKSEK = 132
GRAF_SOL = 34
GRAF_UST = 16
GRAF_SAG = 52  # limit etiketi ("limit 50", ~42 px) + 8 px pay için sağda yer
GRAF_ALT = 28
X_ETIKET_ADIM = 3  # 14 günde 5 etiket; hepsi görünür, hiçbiri üst üste binmez


def _guzel_tavan(deger: float) -> int:
    """Y ekseni için okunur bir tavan (1/2/5 × 10ⁿ)."""
    if deger <= 0:
        return 1
    for adim in (1, 2, 5, 10):
        if deger <= adim:
            return adim
    buyukluk = 10 ** (len(str(int(deger))) - 1)
    for katsayi in (1, 2, 5, 10):
        if deger <= katsayi * buyukluk:
            return int(katsayi * buyukluk)
    return int(deger)


def grafigi_hazirla(
    seri: list[dict], limit: int | None, taban: int = GRAF_TABAN
) -> dict:
    """Son 14 günün günlük isteklerini sıfır-bağımlılık SVG geometrisine çevirir.

    Koordinatlar sabit taban genişliğe göre ÜRETİLİR; `stil.css` SVG'yi
    `max-width: <taban>` ile kırpar, böylece ölçek hiçbir zaman 1'in altına
    düşmez ve 11 px etiketler küçülmez.
    """
    genislik = taban
    yukseklik = GRAF_YUKSEK
    sol, ust, sag, alt = GRAF_SOL, GRAF_UST, GRAF_SAG, GRAF_ALT
    plot_g = taban - sol - sag
    plot_y = yukseklik - ust - alt
    en_cok = max((g["istek"] for g in seri), default=0)
    tavan = _guzel_tavan(max(en_cok, limit or 0, 1))
    adet = max(len(seri), 1)

    def y_konum(deger: float) -> float:
        return ust + plot_y - (deger / tavan) * plot_y if tavan else float(ust + plot_y)

    dilim = plot_g / adet
    cubuk_g = max(dilim * 0.62, 2.0)
    cubuklar = []
    for indeks, gun in enumerate(seri):
        deger = gun["istek"]
        cubuk_y = y_konum(deger)
        cubuklar.append(
            {
                "x": round(sol + dilim * indeks + (dilim - cubuk_g) / 2, 2),
                "y": round(cubuk_y, 2),
                "genislik": round(cubuk_g, 2),
                "yukseklik": round(ust + plot_y - cubuk_y, 2),
                "deger": deger,
                "gun": gun["gun"],
                # Sıfır sütun: grafiğin "burada veri yok" olduğunu GÖSTERİR.
                "bos": deger == 0,
            }
        )

    etiketler = [
        {
            "x": round(sol + dilim * indeks + dilim / 2, 2),
            "metin": gun["gun"][8:10],  # ay-gün: yalnız gün numarası
        }
        for indeks, gun in enumerate(seri)
        if indeks % X_ETIKET_ADIM == 0
    ]

    izgara = [
        {"y": round(ust + plot_y * oran, 2), "metin": str(int(tavan * (1 - oran)))}
        for oran in (0.0, 0.5, 1.0)
    ]

    limit_cev = None
    if limit and limit <= tavan:
        limit_cev = {
            "y": round(y_konum(limit), 2),
            "x1": sol,
            "x2": taban - sag + 6,
            "metin": f"limit {limit}",
            "tx": taban - sag + 10,
        }

    return {
        "genislik": genislik,
        "yukseklik": yukseklik,
        "sol": sol,
        "ust": ust,
        "plot_y": round(ust + plot_y, 2),
        "sag": taban - sag,
        "cubuklar": cubuklar,
        "etiketler": etiketler,
        "izgara": izgara,
        "tavan": tavan,
        "limit": limit_cev,
        "bos": all(g["istek"] == 0 for g in seri),
    }


def _model_renkleri(modeller: list[str]) -> dict[str, str]:
    """Model adı → Okabe-Ito rengi. Sıra bağımsız: adın hash'i seçer."""
    import hashlib

    renkler: dict[str, str] = {}
    for model in modeller:
        # crc32 yerine sha256'ın ilk 4 baytı: kararlı ve Python'a bağlı değil
        # (Python'un `hash()`'i her çalıştırmada değişir).
        ozet = hashlib.sha256(model.encode("utf-8")).digest()
        renkler[model] = OKABE_ITO[ozet[0] % len(OKABE_ITO)]
    return renkler


# -- uygulama ---------------------------------------------------------------


def app_olustur(
    db_yolu: Path | str,
    cikti_dizini: Path | str | None = None,
    kota_toml: Path | str | None = None,
) -> Flask:
    """Verilen DB'yi SALT OKUNUR açan Flask uygulaması."""
    kok = Path(__file__).parent
    uygulama = Flask(
        "orkestra.web",
        template_folder=str(kok / "sablonlar"),
        static_folder=str(kok / "static"),
    )
    uygulama.config["ORKESTRA_DB"] = str(Path(db_yolu).expanduser())
    uygulama.config["CIKTI_DIZINI"] = str(
        Path(cikti_dizini).expanduser() if cikti_dizini is not None
        else VARSAYILAN_CIKTI_DIZINI
    )
    uygulama.config["KOTA_TOML"] = str(kota_toml) if kota_toml is not None else None
    uygulama.config["KOK_DIZINI"] = str(kok)
    uygulama.config["OKABE_ITO"] = list(OKABE_ITO)
    uygulama.json.ensure_ascii = False  # Türkçe karakterler JSON'da kaçışsız

    @uygulama.before_request
    def _host_kontrolu() -> Response | None:
        """DNS rebinding koruması.

        Reddedilen istek bağlantı AÇILMADAN döner: `_ac_baglanti` sırası bu
        kontrolden sonra gelir, yani 403 alan istek hiçbir sorgu yapmaz.
        """
        if not HOST_DESENI.match(request.host or ""):
            return guvenli_basliklar(
                Response(
                    "İsteğin Host başlığı reddedildi.",
                    status=403,
                    mimetype="text/plain; charset=utf-8",
                )
            )
        return None

    @uygulama.before_request
    def _ac_baglanti() -> None:
        # None döndürmek ZORUNLU: aksi halde Flask yanıtı burada keser.
        _baglanti_al()

    uygulama.teardown_request(_baglanti_kapat)

    @uygulama.after_request
    def _basliklari(cevap: Response) -> Response:
        return guvenli_basliklar(cevap)

    @uygulama.errorhandler(405)
    def _sadece_get(_hata) -> Response:
        return guvenli_basliklar(
            Response("yalnızca GET desteklenir", status=405, mimetype="text/plain; charset=utf-8")
        )

    # -- sayfalar ---------------------------------------------------------

    @uygulama.get("/")
    def kuyruk_sayfasi() -> str:
        durum = request.args.get("durum", "")
        if not DURUM_DUZENI.match(durum or ""):
            durum = ""
        kayitlar = gorevleri(_baglanti_al(), durum or None)
        return render_template(
            "kuyruk.html",
            kayitlar=kayitlar,
            durum=durum,
            durum_listesi=sorted(DURUM_ETIKETLERI),
            toplam=len(kayitlar),
            palet=OKABE_ITO,
            durum_renkleri=DURUM_RENKLERI,
        )

    @uygulama.get("/gorev/<int:gorev_id>")
    def gorev_sayfasi(gorev_id: int) -> str:
        detay = gorev_detay(_baglanti_al(), gorev_id)
        if detay is None:
            abort(404)
        son_kosu = detay["kosular"][-1] if detay["kosular"] else None
        log = log_son_satirlar(
            son_kosu["log_yolu"] if son_kosu else None,
            Path(uygulama.config["CIKTI_DIZINI"]),
        )
        return render_template(
            "gorev.html",
            gorev=detay,
            log=log,
            palet=OKABE_ITO,
            durum_renkleri=DURUM_RENKLERI,
        )

    @uygulama.get("/kota")
    def kota_sayfasi() -> str:
        limitler = quota.limitleri_yukle(uygulama.config["KOTA_TOML"])
        gorunum = quota.kota_gorunumu(_baglanti_al(), limitler)
        # Renk model ADINA göre kararlıdır (sıra bağımsız): aynı model her
        # açılışta aynı rengi alır, lejant ile graf hep uyuşur.
        renkler = _model_renkleri([m.model for m in gorunum.modeller])
        grafikler = {
            m.model: grafigi_hazirla(m.seri, m.limit) for m in gorunum.modeller
        }
        return render_template(
            "kota.html",
            gorunum=gorunum,
            grafikler=grafikler,
            model_renkleri=renkler,
            palet=OKABE_ITO,
            durum_renkleri=DURUM_RENKLERI,
        )

    # -- api --------------------------------------------------------------

    @uygulama.get("/api/gorevler")
    def api_gorevler() -> Response:
        durum = request.args.get("durum", "")
        if not DURUM_DUZENI.match(durum or ""):
            durum = ""
        return jsonify({"gorevler": gorevleri(_baglanti_al(), durum or None)})

    @uygulama.get("/api/gorev/<int:gorev_id>")
    def api_gorev(gorev_id: int) -> Response:
        detay = gorev_detay(_baglanti_al(), gorev_id)
        if detay is None:
            return jsonify({"hata": "gorev bulunamadi", "id": gorev_id}), 404
        son_kosu = detay["kosular"][-1] if detay["kosular"] else None
        detay["log"] = log_son_satirlar(
            son_kosu["log_yolu"] if son_kosu else None,
            Path(uygulama.config["CIKTI_DIZINI"]),
        )
        return jsonify(detay)

    @uygulama.get("/api/kota")
    def api_kota() -> Response:
        limitler = quota.limitleri_yukle(uygulama.config["KOTA_TOML"])
        gorunum = quota.kota_gorunumu(_baglanti_al(), limitler)
        return jsonify(
            {
                "gun": gorunum.gun,
                "limit_kaynagi": gorunum.limit_kaynagi,
                "toplam_istek": gorunum.toplam_istek,
                "uyari_sayisi": gorunum.uyari_sayisi,
                "veri_var": gorunum.veri_var,
                "modeller": [
                    {
                        "model": m.model,
                        "etiket": m.etiket,
                        "istek": m.istek,
                        "limit": m.limit,
                        "durum": m.durum,
                        "yuzde": m.yuzde,
                        "seri": m.seri,
                    }
                    for m in gorunum.modeller
                ],
            }
        )

    @uygulama.get("/saglik")
    def saglik() -> Response:
        return jsonify({"durum": "ok"})

    return uygulama


def calistir(
    db_yolu: Path | str,
    port: int = 8780,
    cikti_dizini: Path | str | None = None,
    kota_toml: Path | str | None = None,
) -> None:  # pragma: no cover — gerçek sunucu e2e'de çalıştırılır
    """Sunucuyu BAŞLATIR. Adres kodda sabittir: `127.0.0.1` (`--host` yok)."""
    app_olustur(db_yolu, cikti_dizini, kota_toml).run(
        host="127.0.0.1", port=port, debug=False, use_reloader=False, threaded=True
    )
