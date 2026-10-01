"""Salt-okunur Flask uygulaması: `/` graf, `/api/*`, `/kirik`, `/yetim`, `/saglik`.

Güvenlik (bağlayıcı):
  * Sunucu koda sabit `127.0.0.1` adresine bağlanır (`--host` seçeneği yok).
  * `Host` başlığı `127.0.0.1:<port>` veya `localhost:<port>` değilse 403
    (DNS rebinding koruması).
  * İndeks DB'si `mode=ro` ile açılır; vault dosyalarına hiç dokunulmaz.
  * Rota yüzeyi yalnızca sayısal id'dir: dosya sistemi yolu alan rotalar yok.
  * CSP satır içi script/stil yasaklar; JS ve CSS `static/` dosyasından gelir.
"""

from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path

from flask import Flask, Response, current_app, g, jsonify, render_template, request

from .. import index as indeks_modulu

# DNS rebinding koruması: yalnızca gerçek loopback adresleri kabul edilir.
# Port zorunlu değildir; `localhost` ve `127.0.0.1` yeterlidir.
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


# Renk körü-güvenli palet (Okabe-Ito). Sıra sabittir; `graf.js` aynı sırayı
# kullanır, böylece bir klasörün rengi graf ile lejantta aynıdır.
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


def guvenli_basliklar(cevap: Response) -> Response:
    """Her yanıta bağlayıcı güvenlik başlıklarını ekler."""
    cevap.headers["Content-Security-Policy"] = csp()
    cevap.headers["X-Content-Type-Options"] = "nosniff"
    cevap.headers["Referrer-Policy"] = "no-referrer"
    cevap.headers["Cache-Control"] = "no-store"
    return cevap


def _baglanti_al() -> sqlite3.Connection:
    if "harita_db" not in g:
        g.harita_db = indeks_modulu.baglan_salt_okunur(current_app.config["HARITA_DB"])
    return g.harita_db


def _baglanti_kapat(_hata: BaseException | None = None) -> None:
    baglanti = g.pop("harita_db", None)
    if baglanti is not None:
        baglanti.close()


def app_olustur(db_yolu: Path | str) -> Flask:
    """Verilen indeks DB'sini SALT OKUNUR açan Flask uygulaması."""
    kok = Path(__file__).parent
    uygulama = Flask(
        "harita.web",
        template_folder=str(kok / "sablonlar"),
        static_folder=str(kok / "static"),
    )
    uygulama.config["HARITA_DB"] = str(Path(db_yolu).expanduser())
    uygulama.json.ensure_ascii = False  # Türkçe karakterler JSON'da kaçışsız

    @uygulama.before_request
    def _host_kontrolu() -> Response | None:
        """DNS rebinding koruması: beklenmeyen Host başlığı reddedilir.

        Bağlantı AÇILMAZ: reddedilen istek indekse hiç dokunmaz.
        """
        if not HOST_DESENI.match(request.host or ""):
            yanit = Response(
                "İsteğin Host başlığı reddedildi.", status=403, mimetype="text/plain; charset=utf-8"
            )
            return guvenli_basliklar(yanit)
        return None

    @uygulama.before_request
    def _ac_baglanti() -> None:
        # before_request None döndürmek ZORUNLUDUR: aksi halde Flask yanıtı
        # burada keser ve görünüm hiç çalışmaz.
        _baglanti_al()

    uygulama.teardown_request(_baglanti_kapat)

    @uygulama.after_request
    def _basliklari(cevap: Response) -> Response:
        return guvenli_basliklar(cevap)

    @uygulama.get("/")
    def graf_sayfasi() -> str:
        # Özet şeridi tek sorguda; düğüm/kenar verisi JS'e `/api/graf` ile gider.
        return render_template(
            "graf.html",
            sayaclar=indeks_modulu.toplam_sayaclar(_baglanti_al()),
            acik_not=request.args.get("not", ""),
        )

    @uygulama.get("/api/graf")
    def api_graf() -> Response:
        baglanti = _baglanti_al()
        return jsonify(
            {
                "dugumler": indeks_modulu.graf_dugumleri(baglanti),
                "kenarlar": indeks_modulu.graf_kenarlari(baglanti),
            }
        )

    @uygulama.get("/api/not/<int:not_id>")
    def api_not(not_id: int) -> Response:
        detay = indeks_modulu.not_detay(_baglanti_al(), not_id)
        if detay is None:
            return jsonify({"hata": "not bulunamadı", "id": not_id}), 404
        return jsonify(detay)

    @uygulama.get("/kirik")
    def kirik_sayfasi() -> str:
        return render_template("kirik.html", kayitlar=indeks_modulu.kirik_linkler_detayli(_baglanti_al()))

    @uygulama.get("/yetim")
    def yetim_sayfasi() -> str:
        bolum = indeks_modulu.yetim_ayir(_baglanti_al())
        return render_template(
            "yetim.html", gercek=bolum.gercek, yok_sayilabilir=bolum.yok_sayilabilir
        )

    @uygulama.get("/saglik")
    def saglik() -> Response:
        return jsonify({"durum": "ok"})

    @uygulama.get("/ara")
    def ara_sayfasi() -> str:
        """Arama sayfası. YALNIZCA GET; form `form-action 'none'` yüzünden
        JS `location.assign` ile gönderilir. JS kapalıyken bile `?q=` ile
        doğrudan açılan sayfa sonuç gösterir (sunucu tarafı render).
        """
        from .. import ara as ara_modulu

        baglanti = _baglanti_al()
        sorgu = request.args.get("q", "").strip()
        sonuclar: list = []
        hata: str | None = None
        if sorgu:
            try:
                ayarlar = ara_modulu.Ayarlar(ilk=_ara_ilk(), etiket=None, klasor=None, tam=False)
                sonuclar, _ = ara_modulu.ara(baglanti, sorgu, ayarlar)
            except ara_modulu.SorguHatasi as exc:
                hata = str(exc)
        return render_template("ara.html", sorgu=sorgu, sonuclar=sonuclar, hata=hata)

    @uygulama.get("/api/ara")
    def api_ara() -> Response:
        from .. import ara as ara_modulu

        baglanti = _baglanti_al()
        sorgu = request.args.get("q", "").strip()
        if not sorgu:
            return jsonify({"hata": "sorgu boş", "sonuclar": []})
        try:
            ayarlar = ara_modulu.Ayarlar(ilk=_ara_ilk())
            sonuclar, _ = ara_modulu.ara(baglanti, sorgu, ayarlar)
        except ara_modulu.SorguHatasi as exc:
            return jsonify({"hata": str(exc), "sonuclar": []})
        return jsonify(
            {
                "sorgu": sorgu,
                "sonuclar": [
                    {
                        "puan": s.puan, "baslik": s.baslik, "yol": s.yol,
                        "etiketler": s.etiketler, "alinti": s.alinti,
                        "vurgular": [list(a) for a in s.vurgular],
                        "not_id": s.not_id,
                    }
                    for s in sonuclar
                ],
            }
        )

    return uygulama


def _ara_ilk() -> int:
    """`?ilk=` değerini güvenli sınıra çeker (üst sınır 50)."""
    from ..ara import EN_COK_SONUC

    try:
        deger = int(request.args.get("ilk", 10))
    except (TypeError, ValueError):
        return 10
    return max(1, min(deger, EN_COK_SONUC))


def calistir(db_yolu: Path | str, port: int) -> None:  # pragma: no cover
    """Sunucuyu BAŞLATIR. Adres kodda sabittir: `127.0.0.1`."""
    app_olustur(db_yolu).run(
        host="127.0.0.1", port=port, debug=False, use_reloader=False, threaded=True
    )