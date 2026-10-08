"""Yerel web paneli: Flask uygulamasi, JSON API ve guvenlik katmani (TASARIM.md §5).

Guvenlik (baglayici):
  * Sunucu koda sabit `127.0.0.1` adresine baglanir (`--host` secenegi yok).
  * `Host` basligi `127.0.0.1[:port]` / `localhost[:port]` degilse 403 (DNS rebinding).
  * Her POST: `Origin` sunucunun kendi kokeni (veya gecerli `KULE_FRAME_ORIGIN`) olmali,
    ve `X-CSRF` basligi sunucu baslangicinda uretilen jetonla eslesmeli; aksi 403.
  * CSP satir ici script/stil yasaklar; JS ve CSS `static/` dosyasindan gelir.
  * Istemciden gelen dosya yolu kullanilmaz: degisiklikler `Degisiklik` sozlugu olarak
    gelir, geri alma yalniz yedek kimligiyle (dogrulanmis) yapilir.
  * Deger dondren uclar gizli degiskenleri maskeler; acik deger yalnizca `goster=1` ve
    tek bir ad icin verilir.
"""

from __future__ import annotations

import hmac
import os
import re
import secrets
import sys
import webbrowser
from collections.abc import Callable, Iterable
from typing import Any

from flask import Flask, Response, jsonify, render_template, request

from .. import durum
from ..analiz import genislet, parcala
from ..degisiklik import (
    CakismaHatasi,
    Degisiklik,
    UygulamaHatasi,
    YetkiHatasi,
    eylem_adi,
    geri_al_plani,
    path_farki,
    uygula,
)
from ..gizli import gizli_mi, maskele
from ..kaynak import KULLANICI, Kaynak, KaynakHatasi
from ..yedek import YedekHatasi, yedekler

VARSAYILAN_PORT = 8797

# DNS rebinding korumasi: yalnizca gercek loopback adresleri.
HOST_DESENI = re.compile(r"^(127\.0\.0\.1|localhost)(:\d{1,5})?$", re.IGNORECASE)

# Tarayici eklentisi/iframe izni: yalnizca http://127.0.0.1:port veya http://localhost:port.
KULE_FRAME_ORIGIN_RE = re.compile(r"^http://(127\.0\.0\.1|localhost):[0-9]{1,5}$")

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

CSRF_BASLIGI = "X-CSRF"
MAKS_DEGISIKLIK = 200
MAKS_AD = 256
MAKS_DEGER = 32767   # Windows ortam degiskeni ust siniri
MAKS_YOL = 4096


class _Hata(Exception):
    """API katmaninda HTTP kodu ve Turkce mesajla donen hata."""

    def __init__(self, kod: int, mesaj: str) -> None:
        super().__init__(mesaj)
        self.kod = kod
        self.mesaj = mesaj


def csp() -> str:
    """KULE_FRAME_ORIGIN kaliba uyarsa frame-ancestors o kokene acilir; aksi halde 'none'."""
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


def _metin_yaniti(metin: str, kod: int) -> Response:
    return _guvenli_basliklar(Response(metin, status=kod, mimetype="text/plain; charset=utf-8"))


def _hata_yaniti(kod: int, mesaj: str, **ek: Any) -> Response:
    cevap = jsonify({"hata": mesaj, **ek})
    cevap.status_code = kod
    return _guvenli_basliklar(cevap)


def _origin_uygun(origin: str | None, host: str) -> bool:
    """POST kaynagi sunucunun kendi kokeni ya da (gecerliyse) KULE_FRAME_ORIGIN olmali."""
    if not origin:
        return False
    if origin.lower() == f"http://{host}".lower():
        return True
    kule = os.environ.get("KULE_FRAME_ORIGIN", "")
    return bool(KULE_FRAME_ORIGIN_RE.fullmatch(kule)) and origin == kule


# ------------------------------------------------------------------ veri yardimcilari

def _gorunen(deger: Any, gizli: bool) -> str | None:
    """Fark satirinda gosterilecek deger: gizli ise maskeli (bos deger bos kalir)."""
    if deger is None:
        return None
    return maskele(deger.metin) if gizli else deger.metin


def _fark_satirlari(degisiklikler: Iterable[Degisiklik], ayirici: str) -> list[dict]:
    """Degerleri gizli degiskenlerde maskeler; PATH icin eklenen/cikan girdi listesi verir."""
    satirlar: list[dict] = []
    for d in degisiklikler:
        gizli = gizli_mi(d.ad)
        satir: dict[str, Any] = {
            "kapsam": d.kapsam,
            "ad": d.ad,
            "eylem": eylem_adi(d),
            "gizli": gizli,
            "path": d.ad.casefold() == "path",
        }
        if satir["path"]:
            fark = path_farki(
                d.eski.metin if d.eski is not None else "",
                d.yeni.metin if d.yeni is not None else "",
                ayirici,
            )
            satir["eklenen"] = fark["eklenen"]
            satir["cikan"] = fark["cikan"]
            # Kume farki yinelenen/bos girdi kaldirmayi gostermez; sayilar bunu aciklar.
            satir["eski_sayi"] = len(parcala(d.eski.metin, ayirici)) if d.eski is not None else 0
            satir["yeni_sayi"] = len(parcala(d.yeni.metin, ayirici)) if d.yeni is not None else 0
        else:
            satir["eski"] = _gorunen(d.eski, gizli)
            satir["yeni"] = _gorunen(d.yeni, gizli)
        satirlar.append(satir)
    return satirlar


def _ad_denetle(ad: str) -> None:
    if not ad.strip() or len(ad) > MAKS_AD or "=" in ad or "\x00" in ad:
        raise _Hata(400, f"geçersiz ortam değişkeni adı: {ad[:40]!r}")


def _degisiklikleri_coz(veri: Any) -> list[Degisiklik]:
    """Istek govdesini dogrular ve `Degisiklik` listesine cevirir. Hicbir sey yazmaz."""
    ham = veri.get("degisiklikler") if isinstance(veri, dict) else None
    if not isinstance(ham, list) or not ham:
        raise _Hata(400, "uygulanacak değişiklik yok")
    if len(ham) > MAKS_DEGISIKLIK:
        raise _Hata(400, f"en fazla {MAKS_DEGISIKLIK} değişiklik gönderilebilir")
    liste: list[Degisiklik] = []
    gorulen: set[tuple[str, str]] = set()
    for kayit in ham:
        if not isinstance(kayit, dict):
            raise _Hata(400, "geçersiz değişiklik kaydı")
        try:
            d = Degisiklik.sozlukten(kayit)
        except ValueError as exc:
            raise _Hata(400, str(exc)) from exc
        if d.eski is None and d.yeni is None:
            raise _Hata(400, "boş değişiklik kaydı")
        _ad_denetle(d.ad)
        for deger in (d.eski, d.yeni):
            if deger is not None and (len(deger.metin) > MAKS_DEGER or "\x00" in deger.metin):
                raise _Hata(400, f"geçersiz değer: {d.kapsam}/{d.ad}")
        if (d.kapsam, d.ad) in gorulen:
            raise _Hata(400, f"aynı değişken bir uygulamada iki kez değişemez: {d.kapsam}/{d.ad}")
        gorulen.add((d.kapsam, d.ad))
        liste.append(d)
    return liste


def _onizleme_denetle(kaynak: Kaynak, liste: list[Degisiklik]) -> None:
    """Yazmadan once yetki ve beklenen eski deger kontrolu (uygula ile ayni kurallar)."""
    kapsamlar = list(dict.fromkeys(d.kapsam for d in liste))
    yazilamaz = [k for k in kapsamlar if not kaynak.yazilabilir(k)]
    if yazilamaz:
        raise _Hata(403, "yazılamayan kapsam: " + ", ".join(yazilamaz))
    mevcut = {k: kaynak.oku(k) for k in kapsamlar}
    cakisan = [f"{d.kapsam}/{d.ad}" for d in liste if mevcut[d.kapsam].get(d.ad) != d.eski]
    if cakisan:
        raise _Hata(409, "değişken siz düzenlerken başka yerden değişti: " + ", ".join(cakisan))


def _uygula_yaniti(kaynak: Kaynak, liste: list[Degisiklik]) -> Response:
    try:
        yedek = uygula(kaynak, liste)
    except CakismaHatasi as exc:
        return _hata_yaniti(409, str(exc))
    except YetkiHatasi as exc:
        return _hata_yaniti(403, str(exc))
    except UygulamaHatasi as exc:
        return _hata_yaniti(500, str(exc), geri_yuklendi=exc.geri_yuklendi)
    except YedekHatasi as exc:
        return _hata_yaniti(500, f"yedek alınamadı, hiçbir şey yazılmadı: {exc}")
    except ValueError as exc:
        return _hata_yaniti(400, str(exc))
    return jsonify({"yedek": yedek, "uygulanan": len(liste)})


def _durum_verisi(kaynak: Kaynak, dizin_var: Callable[[str], bool],
                  dosya_var: Callable[[str], bool]) -> dict[str, Any]:
    yol = durum.path_durumu(kaynak, dizin_var=dizin_var, dosya_var=dosya_var)
    kayitlar: dict[str, dict] = {}
    for kapsam in kaynak.kapsamlar():
        ad, deger = durum.path_kaydi(kaynak.oku(kapsam))
        kayitlar[kapsam] = {
            "ad": ad,
            "metin": deger.metin if deger is not None else "",
            "genisler": deger.genisler if deger is not None else False,
            "var": deger is not None,
            "yazilabilir": kaynak.yazilabilir(kapsam),
        }
    yedek_listesi = yedekler()
    return {
        "platform": durum.platform_bilgisi(kaynak),
        "path": {"girdiler": yol["girdiler"], "kayitlar": kayitlar, "oneri": yol["oneri"]},
        "komutlar": yol["komutlar"],
        "ozet": yol["ozet"],
        "yedek": {"son": yedek_listesi[0] if yedek_listesi else None, "sayi": len(yedek_listesi)},
    }


# -------------------------------------------------------------------- uygulama

def uygulama_olustur(kaynak: Kaynak, *,
                     dizin_var: Callable[[str], bool] | None = None,
                     dosya_var: Callable[[str], bool] | None = None) -> Flask:
    """Panel uygulamasi. `dizin_var`/`dosya_var` yalnizca test ve ekran goruntusu icin enjekte edilir."""
    kok = os.path.dirname(os.path.abspath(__file__))
    uygulama = Flask(
        "yol.web",
        template_folder=os.path.join(kok, "sablonlar"),
        static_folder=os.path.join(kok, "static"),
    )
    uygulama.json.ensure_ascii = False  # Turkce karakterler JSON'da kacissiz

    dizin_denetle = dizin_var or os.path.isdir
    dosya_denetle = dosya_var or os.path.isfile
    csrf_jetonu = secrets.token_urlsafe(32)

    @uygulama.before_request
    def _istek_denetimi() -> Response | None:
        """Host, Origin ve CSRF. Reddedilen istek hicbir is mantigi calistirmaz."""
        host = request.host or ""
        if not HOST_DESENI.fullmatch(host):
            return _metin_yaniti("İsteğin Host başlığı reddedildi.", 403)
        if request.method == "POST":
            if not _origin_uygun(request.headers.get("Origin"), host):
                return _metin_yaniti("İsteğin Origin başlığı reddedildi.", 403)
            gelen = request.headers.get(CSRF_BASLIGI, "")
            if not hmac.compare_digest(gelen.encode("utf-8"), csrf_jetonu.encode("utf-8")):
                return _metin_yaniti("CSRF jetonu geçersiz.", 403)
        return None

    @uygulama.after_request
    def _basliklar(cevap: Response) -> Response:
        return _guvenli_basliklar(cevap)

    @uygulama.errorhandler(_Hata)
    def _api_hatasi(hata: _Hata) -> Response:
        return _hata_yaniti(hata.kod, hata.mesaj)

    @uygulama.errorhandler(KaynakHatasi)
    def _kaynak_hatasi(hata: KaynakHatasi) -> Response:
        return _hata_yaniti(500, f"ortam kaynağı okunamadı veya yazılamadı: {hata}")

    @uygulama.errorhandler(405)
    def _yalniz_belirli_yontem(_hata: Exception) -> Response:
        return _metin_yaniti("bu adres bu yöntemi desteklemiyor", 405)

    @uygulama.errorhandler(404)
    def _bulunamadi(_hata: Exception) -> Response:
        return _metin_yaniti("bulunamadı", 404)

    @uygulama.get("/")
    def ana_sayfa() -> str:
        return render_template("ana.html", csrf_jetonu=csrf_jetonu)

    @uygulama.get("/api/durum")
    def api_durum() -> Response:
        return jsonify(_durum_verisi(kaynak, dizin_denetle, dosya_denetle))

    @uygulama.get("/api/yedekler")
    def api_yedekler() -> Response:
        return jsonify({"yedekler": yedekler()})

    @uygulama.get("/api/yedek/<yedek_id>/fark")
    def api_yedek_fark(yedek_id: str) -> Response:
        try:
            plan = geri_al_plani(kaynak, yedek_id)
        except YedekHatasi as exc:
            raise _Hata(404, str(exc)) from exc
        return jsonify({"id": yedek_id, "fark": _fark_satirlari(plan, kaynak.ayirici)})

    @uygulama.get("/api/degiskenler")
    def api_degiskenler() -> Response:
        kapsam = request.args.get("kapsam") or None
        ad = request.args.get("ad") or None
        goster = request.args.get("goster") == "1"
        if goster:
            # Acik deger yalnizca tek bir ad icin ve acikca istenirse verilir.
            if not ad:
                raise _Hata(400, "değeri göstermek için tek bir ad belirtin")
            kayitlar = [
                k for k in durum.degiskenler(kaynak, goster=True)
                if k["ad"] == ad and (kapsam is None or k["kapsam"] == kapsam)
            ]
            if not kayitlar:
                raise _Hata(404, f"değişken bulunamadı: {ad}")
            return jsonify({"degiskenler": kayitlar})
        kayitlar = durum.degiskenler(kaynak, goster=False)
        if kapsam is not None:
            kayitlar = [k for k in kayitlar if k["kapsam"] == kapsam]
        return jsonify({"degiskenler": kayitlar})

    @uygulama.post("/api/onizle")
    def api_onizle() -> Response:
        liste = _degisiklikleri_coz(request.get_json(silent=True))
        _onizleme_denetle(kaynak, liste)
        return jsonify({"fark": _fark_satirlari(liste, kaynak.ayirici)})

    @uygulama.post("/api/uygula")
    def api_uygula() -> Response:
        liste = _degisiklikleri_coz(request.get_json(silent=True))
        return _uygula_yaniti(kaynak, liste)

    @uygulama.post("/api/geri-al/<yedek_id>")
    def api_geri_al(yedek_id: str) -> Response:
        try:
            plan = geri_al_plani(kaynak, yedek_id)
        except YedekHatasi as exc:
            raise _Hata(404, str(exc)) from exc
        if not plan:
            return jsonify({"yedek": None, "uygulanan": 0})
        return _uygula_yaniti(kaynak, plan)

    @uygulama.post("/api/dizin-var")
    def api_dizin_var() -> Response:
        veri = request.get_json(silent=True)
        if not isinstance(veri, dict) or not isinstance(veri.get("yol"), str):
            raise _Hata(400, "yol metni bekleniyor")
        yol = veri["yol"].strip()
        if not yol or len(yol) > MAKS_YOL or "\x00" in yol:
            return jsonify(False)
        cozumlu = genislet(yol, durum.ortam_olustur(kaynak), kaynak.windows)
        return jsonify(bool(dizin_denetle(cozumlu)))

    return uygulama


def calistir(kaynak: Kaynak, port: int = VARSAYILAN_PORT, ac: bool = False) -> int:  # pragma: no cover
    """Sunucuyu baslatir. Adres kodda sabittir: `127.0.0.1` (`--host` yok)."""
    uygulama = uygulama_olustur(kaynak)
    url = f"http://127.0.0.1:{port}/"
    print(f"yol paneli: {url} (durdurmak icin Ctrl+C)", file=sys.stderr)
    if ac:
        webbrowser.open(url)
    uygulama.run(host="127.0.0.1", port=port, debug=False, use_reloader=False, threaded=True)
    return 0
