"""devtemizle web paneli: Flask uygulamasi (PLAN.md §6, TASARIM.md §5).

Guvenlik (BAGLAYICI):
  * Sunucu koda sabit `127.0.0.1` adresine baglanir; `--host` secenegi YOKTUR.
  * `Host` basligi `127.0.0.1[:port]` / `localhost[:port]` degilse 403 (DNS rebinding).
  * Her POST: `Origin` sunucunun kendi koku (veya gecerli KULE_FRAME_ORIGIN) olmali
    ve `X-CSRF` basligi uygulamaya ozgu jetonla eslesmeli; aksi halde 403.
  * Istemciden dosya yolu ALINMAZ: silme yalnizca rapordaki `id`lerle calisir,
    yollar sil_idler tarafindan rapordan cozulur ve guvenlik denetimlerinden gecer.
  * CSP satir ici script/stil yasaklar; JS ve CSS `static/` dosyasindan gelir.
  * Durum (tarama/silme) uygulama ornegine bagli; modul duzeyinde paylasilan
    durum YOKTUR (testler birden fazla uygulama olusturur).
"""

from __future__ import annotations

import hmac
import os
import re
import secrets
import threading
import webbrowser
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, render_template, request

from .. import is_akisi, rapor
from ..kesif import KesifHatasi
from ..sil import RaporYok, sil_idler

# DNS rebinding korumasi: yalnizca gercek loopback adresleri.
HOST_DESENI = re.compile(r"^(127\.0\.0\.1|localhost)(:\d{1,5})?$", re.IGNORECASE)

CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self'; "
    "img-src 'self' data:; "
    "frame-ancestors 'none'"
)

# Kule iframe ebeveyni: yalnizca http://127.0.0.1:PORT veya http://localhost:PORT.
KULE_FRAME_ORIGIN_RE = re.compile(r"^http://(127\.0\.0\.1|localhost):[0-9]{1,5}$")

#: Rapordaki aday/onbellek kimligi: sha1 onekinden uretilen kucuk hex dizisi.
ID_DESENI = re.compile(r"[0-9a-f]{8,40}")

#: Tek istekte en cok silinecek kimlik sayisi.
MAX_IDLER = 500


def csp() -> str:
    """Her istekte CSP uretir: KULE_FRAME_ORIGIN kaliba uyarsa frame-ancestors acilir."""
    origin = os.environ.get("KULE_FRAME_ORIGIN", "")
    if KULE_FRAME_ORIGIN_RE.fullmatch(origin):
        return CSP.replace("frame-ancestors 'none'", f"frame-ancestors {origin}")
    return CSP


def _guvenli_basliklar(cevap: Response) -> Response:
    cevap.headers["Content-Security-Policy"] = csp()
    cevap.headers["X-Content-Type-Options"] = "nosniff"
    cevap.headers["Referrer-Policy"] = "no-referrer"
    cevap.headers["Cache-Control"] = "no-store"
    return cevap


def _json_hata(mesaj: str, durum_kodu: int) -> Response:
    cevap = jsonify({"hata": mesaj})
    cevap.status_code = durum_kodu
    return _guvenli_basliklar(cevap)


def _accepted(govde: dict) -> Response:
    cevap = jsonify(govde)
    cevap.status_code = 202
    return _guvenli_basliklar(cevap)


def _hata_metni(exc: Exception) -> str:
    if isinstance(exc, (KesifHatasi, RaporYok)):
        return str(exc)
    return f"beklenmeyen bir hata oluştu ({type(exc).__name__})"


class _Durum:
    """Tek arka plan isi (tarama veya silme) ve son sonucu; kilitle korunur."""

    def __init__(self) -> None:
        self._kilit = threading.Lock()
        self._is = "bos"          # "bos" | "tarama" | "silme"
        self._adim = ""
        self._i = 0
        self._n = 0
        self._hata: str | None = None
        self._son_tur: str | None = None
        self._son_sonuc: dict | None = None
        self._silinen: set[str] = set()

    def baslat(self, is_: str, adim: str = "", n: int = 0) -> bool:
        """Yeni is baslatir; baska bir is surerken False doner (HTTP 409)."""
        with self._kilit:
            if self._is != "bos":
                return False
            self._is, self._adim, self._i, self._n = is_, adim, 0, n
            self._hata = None
            return True

    def ilerle(self, adim: str, i: int, n: int) -> None:
        with self._kilit:
            self._adim, self._i, self._n = adim, i, n

    def bitir(self, son_tur: str, son_sonuc: dict | None = None, hata: str | None = None) -> None:
        with self._kilit:
            self._is = "bos"
            self._son_tur = son_tur
            self._son_sonuc = son_sonuc
            self._hata = hata
            # Yeni basarili tarama: eski raporun silinen kayitlari artik gecersiz.
            if son_tur == "tara" and hata is None:
                self._silinen.clear()

    def silinen_ekle(self, kimlikler: list[str]) -> None:
        with self._kilit:
            self._silinen.update(kimlikler)

    def silinen(self) -> frozenset[str]:
        with self._kilit:
            return frozenset(self._silinen)

    def anlik(self) -> dict[str, Any]:
        with self._kilit:
            return {
                "is": self._is,
                "adim": self._adim,
                "i": self._i,
                "n": self._n,
                "hata": self._hata,
                "son_sonuc": self._son_sonuc,
                "son_tur": self._son_tur,
            }


def _tarama_isi(
    durum: _Durum,
    kokler: list[Path] | None,
    atlas_db: Path | None,
    ev: bool,
    onbellek: bool,
) -> None:
    def ilerleme(adim: str, i: int, n: int) -> None:
        durum.ilerle(adim, i, n)

    try:
        veri = is_akisi.tam_tarama(
            kokler, atlas_db=atlas_db, ev=ev, onbellek=onbellek, ilerleme=ilerleme
        )
    except Exception as exc:  # arka plan: hata durumda saklanir, surec cokmez
        durum.bitir("tara", hata=_hata_metni(exc))
        return
    durum.bitir(
        "tara",
        son_sonuc={
            "aday_sayisi": len(veri.get("adaylar", [])),
            "repo_sayisi": len(veri.get("repolar", [])),
        },
    )


def _silme_isi(durum: _Durum, idler: list[str], dikkat_idler: list[str]) -> None:
    try:
        sonuc = sil_idler(idler, uygula=True, dikkat_idler=dikkat_idler)
    except Exception as exc:
        durum.bitir("sil", hata=_hata_metni(exc))
        return
    silinen = [a["id"] for a in sonuc.get("silindi", []) if a.get("id")]
    silinen += [
        o["id"] for o in sonuc.get("onbellek_sonuclari", []) if o.get("basarili") and o.get("id")
    ]
    durum.silinen_ekle(silinen)
    durum.bitir("sil", son_sonuc={**sonuc, "silinen_idler": silinen})


def _gorunum(veri: dict | None, silinen: frozenset[str]) -> dict | None:
    """Son raporun panel gorunumu: bu oturumda silinen kimlikler cikarilir (diske dokunmaz)."""
    if veri is None:
        return None
    adaylar = [a for a in veri.get("adaylar", []) if a.get("id") not in silinen]
    onbellekler = [o for o in veri.get("onbellekler", []) if o.get("id") not in silinen]
    repolar = []
    for r in veri.get("repolar", []):
        yeni = dict(r)
        yeni["aday_boyut"] = sum(a.get("boyut", 0) for a in adaylar if a.get("repo") == r.get("yol"))
        repolar.append(yeni)
    return {**veri, "adaylar": adaylar, "onbellekler": onbellekler, "repolar": repolar}


def uygulama_olustur(
    kokler: list[Path | str] | None = None,
    ev: bool = False,
    atlas_db: Path | str | None = None,
) -> Flask:
    """Web paneli uygulamasi. Tarama kokleri YALNIZ burada (sunucu) belirlenir."""
    kok = os.path.dirname(os.path.abspath(__file__))
    uygulama = Flask(
        "devtemizle.web",
        template_folder=os.path.join(kok, "sablonlar"),
        static_folder=os.path.join(kok, "static"),
    )
    uygulama.json.ensure_ascii = False  # Turkce karakterler JSON'da kacissiz
    uygulama.config["DEVTEMIZLE_CSRF"] = secrets.token_urlsafe(32)

    kok_listesi = [Path(k).expanduser() for k in kokler] if kokler else None
    atlas = Path(atlas_db).expanduser() if atlas_db else None
    durum = _Durum()

    @uygulama.before_request
    def _istek_denetimi() -> Response | None:
        """Host, ve (POST icin) Origin + CSRF denetimi. Reddedilen istek is BASLATMAZ."""
        if not HOST_DESENI.match(request.host or ""):
            return _guvenli_basliklar(
                Response("İsteğin Host başlığı reddedildi.", status=403,
                         mimetype="text/plain; charset=utf-8")
            )
        if request.method != "POST":
            return None

        beklenen = uygulama.config["DEVTEMIZLE_CSRF"]
        gelen = request.headers.get("X-CSRF", "")
        if not hmac.compare_digest(gelen.encode("utf-8"), beklenen.encode("utf-8")):
            return _json_hata("CSRF jetonu geçersiz.", 403)

        kabul = {request.host_url.rstrip("/")}
        kule = os.environ.get("KULE_FRAME_ORIGIN", "")
        if KULE_FRAME_ORIGIN_RE.fullmatch(kule):
            kabul.add(kule)
        if request.headers.get("Origin", "") not in kabul:
            return _json_hata("Origin reddedildi.", 403)
        return None

    @uygulama.after_request
    def _basliklari(cevap: Response) -> Response:
        return _guvenli_basliklar(cevap)

    @uygulama.errorhandler(405)
    def _yontem(_hata) -> Response:
        return _guvenli_basliklar(
            Response("izin verilmeyen yöntem", status=405, mimetype="text/plain; charset=utf-8")
        )

    @uygulama.get("/")
    def ana_sayfa() -> str:
        return render_template("ana.html", csrf=uygulama.config["DEVTEMIZLE_CSRF"])

    @uygulama.get("/api/rapor")
    def api_rapor() -> Response:
        silinen = durum.silinen()
        gorunum = _gorunum(rapor.yukle(), silinen)
        ozet = rapor.ozet_kartlari(gorunum or {})
        temizlenen = ozet["simdiye_kadar_temizlenen"]
        if gorunum and gorunum.get("repolar"):
            ozet["taranan_repo"] = len(gorunum["repolar"])
        return jsonify({
            "rapor": gorunum,
            "ozet": ozet,
            "dagilim": rapor.dagilim_cubugu(gorunum or {}),
            "temizlenen_toplam": temizlenen,
            "silinen_idler": sorted(silinen),
        })

    @uygulama.get("/api/durum")
    def api_durum() -> Response:
        return jsonify(durum.anlik())

    @uygulama.post("/api/tara")
    def api_tara() -> Response:
        veri = request.get_json(silent=True)
        if veri is None:
            veri = {}
        if not isinstance(veri, dict):
            return _json_hata("İstek gövdesi bir JSON nesnesi olmalı.", 400)
        onbellek = veri.get("onbellek", False)
        if not isinstance(onbellek, bool):
            return _json_hata("onbellek true veya false olmalı.", 400)

        if not durum.baslat("tarama", "kesif", 0):
            return _json_hata("Başka bir tarama ya da silme sürüyor.", 409)
        is_parcacigi = threading.Thread(
            target=_tarama_isi,
            args=(durum, kok_listesi, atlas, ev, onbellek),
            name="devtemizle-tara",
            daemon=True,
        )
        uygulama.config["DEVTEMIZLE_IS"] = is_parcacigi
        is_parcacigi.start()
        return _accepted({"durum": "basladi"})

    @uygulama.post("/api/sil")
    def api_sil() -> Response:
        veri = request.get_json(silent=True)
        if not isinstance(veri, dict):
            return _json_hata("İstek gövdesi bir JSON nesnesi olmalı.", 400)
        idler = veri.get("idler")
        if not isinstance(idler, list) or not (1 <= len(idler) <= MAX_IDLER):
            return _json_hata(f"idler: 1 ile {MAX_IDLER} arasında kimlik listesi olmalı.", 400)
        if not all(isinstance(x, str) and ID_DESENI.fullmatch(x) for x in idler):
            return _json_hata("Geçersiz kimlik.", 400)
        # Dikkat (risk != guvenli) yalnizca burada ACIKCA listelenen kimlikler icin
        # gecerlidir; genel bir bayrak dikkat silmeyi acmaz.
        dikkat_idler = veri.get("dikkat_idler", [])
        if not isinstance(dikkat_idler, list):
            return _json_hata("dikkat_idler bir liste olmalı.", 400)
        if not all(isinstance(x, str) and ID_DESENI.fullmatch(x) for x in dikkat_idler):
            return _json_hata("Geçersiz kimlik.", 400)
        if not set(dikkat_idler) <= set(idler):
            return _json_hata("dikkat_idler, idler içinde olmalı.", 400)

        essiz = list(dict.fromkeys(idler))
        dikkat_essiz = list(dict.fromkeys(dikkat_idler))
        if not durum.baslat("silme", "sil", len(essiz)):
            return _json_hata("Başka bir tarama ya da silme sürüyor.", 409)
        is_parcacigi = threading.Thread(
            target=_silme_isi,
            args=(durum, essiz, dikkat_essiz),
            name="devtemizle-sil",
            daemon=True,
        )
        uygulama.config["DEVTEMIZLE_IS"] = is_parcacigi
        is_parcacigi.start()
        return _accepted({"durum": "basladi", "n": len(essiz)})

    return uygulama


def calistir(port: int = 8796, ac: bool = False, **kw: Any) -> None:  # pragma: no cover - gercek surec
    """Sunucuyu BASLATIR. Adres kodda sabittir: `127.0.0.1` (`--host` yok).

    kw: uygulama_olustur parametreleri (kokler, ev, atlas_db).
    ac: True ise sunucu acildiktan sonra tarayici acilir.
    """
    uygulama = uygulama_olustur(**kw)
    url = f"http://127.0.0.1:{port}"
    print(f"Web paneli baslatiliyor: {url}")
    if ac:
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    uygulama.run(host="127.0.0.1", port=port, debug=False, use_reloader=False, threaded=True)
