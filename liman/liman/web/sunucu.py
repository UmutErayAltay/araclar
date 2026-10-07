"""Salt-okunur Flask paneli: dolu port tablosu + bos port listesi.

Guvenlik (baglayici):
  * Sunucu koda sabit `127.0.0.1` adresine baglanir (`--host` secenegi yok).
  * `Host` basligi `127.0.0.1[:port]` / `localhost[:port]` degilse 403
    (DNS rebinding korumasi) — reddedilen istek HICBIR tarama yapmaz.
  * Panel yalnizca OKUR: surec olusturmez/olmez, port kapatmaz, aga cikmaz.
  * Tum rotalar yalnizca GET'tir; digerleri 405. CSRF yuzeyi yoktur.
  * CSP satir ici script/stil yasaklar; JS ve CSS `static/` dosyasindan gelir.
  * Surec adi/komut metni GUVENILMEYENDIR: Jinja autoescape aciktir, JS'te
    `innerHTML` YOKTUR (`createElement` + `textContent` kullanilir).
"""

from __future__ import annotations

import os
import re
from typing import Any, Callable

from flask import Flask, Response, jsonify, render_template, request

from .. import bos as bos_modulu
from .. import tarama

# DNS rebinding korumasi: yalnizca gercek loopback adresleri.
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

#: Panelde gosterilen bos port listesi (aralik/adet). Web paneli de ayni varsayilani kullanir.
BOS_ARALIK = bos_modulu.VARSAYILAN_ARALIK
BOS_ADET = bos_modulu.VARSAYILAN_ADET


def csp() -> str:
    """Her istekte CSP uretir: KULE_FRAME_ORIGIN kaliba uyarsa frame-ancestors acar."""
    origin = os.environ.get("KULE_FRAME_ORIGIN", "")
    if KULE_FRAME_ORIGIN_RE.fullmatch(origin):
        return CSP.replace("frame-ancestors 'none'", f"frame-ancestors {origin}")
    return CSP


def guvenli_basliklar(cevap: Response) -> Response:
    """Her yanita baglayici guvenlik basliklarini ekler."""
    cevap.headers["Content-Security-Policy"] = csp()
    cevap.headers["X-Content-Type-Options"] = "nosniff"
    cevap.headers["Referrer-Policy"] = "no-referrer"
    cevap.headers["Cache-Control"] = "no-store"
    return cevap


def durum_verisi(kaynak: Callable[..., list[dict]] | None = None) -> dict[str, Any]:
    """Panelin tamami icin tek veri kaynagi: dinleyenler + ozet + bos portlar."""
    satirlar = tarama.dinleyenler(kaynak)
    return {
        "dinleyenler": satirlar,
        "ozet": tarama.ozet(satirlar),
        "bos": bos_modulu.bos_portlar(BOS_ARALIK, BOS_ADET),
    }


def app_olustur(kaynak: Callable[..., list[dict]] | None = None) -> Flask:
    """Salt-okunur panel uygulamasi. `kaynak` testler icin tarama kaynagini enjekte eder."""
    kok = os.path.dirname(os.path.abspath(__file__))
    uygulama = Flask(
        "liman.web",
        template_folder=os.path.join(kok, "sablonlar"),
        static_folder=os.path.join(kok, "static"),
    )
    uygulama.json.ensure_ascii = False  # Turkce karakterler JSON'da kacissiz

    @uygulama.before_request
    def _host_kontrolu() -> Response | None:
        """DNS rebinding korumasi. Reddedilen istek tarama YAPMAZ."""
        if not HOST_DESENI.match(request.host or ""):
            return guvenli_basliklar(
                Response(
                    "İsteğin Host başlığı reddedildi.",
                    status=403,
                    mimetype="text/plain; charset=utf-8",
                )
            )
        return None

    @uygulama.context_processor
    def _baglam() -> dict[str, Any]:
        """Her şablonda `yol` (aktif sayfa) kullanılabilir olsun."""
        return {"yol": request.path}

    @uygulama.after_request
    def _basliklari(cevap: Response) -> Response:
        return guvenli_basliklar(cevap)

    @uygulama.errorhandler(405)
    def _sadece_get(_hata) -> Response:
        return guvenli_basliklar(
            Response("yalnızca GET desteklenir", status=405, mimetype="text/plain; charset=utf-8")
        )

    @uygulama.get("/")
    def ana_sayfa() -> str:
        return render_template(
            "ana.html",
            veri=durum_verisi(kaynak),
            web_bos_aralik=BOS_ARALIK,
            web_bos_adet=BOS_ADET,
        )

    @uygulama.get("/api/durum")
    def api_durum() -> Response:
        return jsonify(durum_verisi(kaynak))

    return uygulama


def calistir(port: int = 8795) -> None:  # pragma: no cover — gerçek süreç
    """Sunucuyu BASLATIR. Adres kodda sabittir: `127.0.0.1` (`--host` yok)."""
    app_olustur().run(
        host="127.0.0.1", port=port, debug=False, use_reloader=False, threaded=True
    )
