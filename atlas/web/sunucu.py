"""Salt-okunur Flask paneli: ozet, yarim is, sizinti, borc, repo detayi.

Guvenlik (baglayici):
  * Sunucu koda sabit `127.0.0.1` adresine baglanir (`--host` secenegi yok).
  * `Host` basligi `127.0.0.1[:port]` / `localhost[:port]` degilse 403
    (DNS rebinding korumasi) — reddedilen istek DB'yi HIC ACMAZ.
  * DB `mode=ro` ile acilir; panel yalnizca OKUR, tarama TETIKLEMEZ.
  * Tum rotalar yalnizca GET'tir; digerleri 405. CSRF yuzeyi yoktur.
  * Rota yuzeyi sayisal id/sayfa ile sinirlidir; dosya sistemi yolu alan
    rotalar YOKTUR.
  * Ekrana/JSON'a cikan her snippet ve todo metni `leaks.maske`den bir kez
    daha gecer (savunma katmani: DB'de ham sir olmasa bile).
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import Flask, Response, abort, current_app, g, jsonify, render_template, request

from .. import leaks

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

# Renk kor-goren (Okabe-Ito). Sira sabittir; `panel.js` ve sablonlar ayni
# sirayi kullanir, boylece onem/tur rengi lejantla hep ayni.
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

#: Onem sirasi (yuksek -> bilgi). Gosterge hem renk hem METIN yazar; rozet
#: yalnizca renge dayanmaz.
ONEMLER = ("yuksek", "orta", "dusuk", "bilgi")

ONEM_RENKLERI = {
    "yuksek": "#D55E00",  # Okabe-Ito turuncu-kirmizi
    "orta": "#E69F00",
    "dusuk": "#56B4E9",
    "bilgi": "#999999",
}

#: Rozet metni: renk + metin birlikte (renk korlugunde de ayirt edilir).
ONEM_ETIKETLERI = {
    "yuksek": "yüksek",
    "orta": "orta",
    "dusuk": "düşük",
    "bilgi": "bilgi",
}

#: Bilinen turler (suzgec formu icin). Bilinmeyen tur de DB'den gelebilir.
TUR_ETIKETLERI = {
    "api-anahtari": "API anahtarı",
    "ozel-anahtar": "Özel anahtar",
    "env-izlenen": ".env izlenen",
    "kisisel-yol": "Kişisel yol",
    "e-posta": "E-posta",
    "gorsel-elle-kontrol": "Görsel (elle kontrol)",
}

#: `/sizinti` sayfa basi bulgu.
SAYFA_BOYUTU = 100

#: Veri 24 saatten eskiyse panel uyari gosterir.
BAYAT_ESIK_SAAT = 24


def guvenli_basliklar(cevap: Response) -> Response:
    """Her yanita baglayici guvenlik basliklarini ekler."""
    cevap.headers["Content-Security-Policy"] = CSP
    cevap.headers["X-Content-Type-Options"] = "nosniff"
    cevap.headers["Referrer-Policy"] = "no-referrer"
    cevap.headers["Cache-Control"] = "no-store"
    return cevap


# -- salt-okunur veritabani -------------------------------------------------


def db_ac(yol: Path | str) -> sqlite3.Connection:
    """DB'yi `mode=ro` ile acar; hicbir kosulda yazmaz."""
    yol = Path(yol).expanduser()
    baglanti = sqlite3.connect(f"file:{yol}?mode=ro", uri=True)
    baglanti.row_factory = sqlite3.Row
    return baglanti


def _baglanti_al() -> sqlite3.Connection:
    if "atlas_db" not in g:
        g.atlas_db = db_ac(current_app.config["ATLAS_DB"])
    return g.atlas_db


def _baglanti_kapat(_hata: BaseException | None = None) -> None:
    baglanti = g.pop("atlas_db", None)
    if baglanti is not None:
        baglanti.close()


# -- veri okuma + savunma katmani -------------------------------------------


def _temizle(metin: str | None) -> str:
    """Ekrana/JSON'a cikan metni maskeler (savunma katmani).

    DB'de `snippet_redacted`/`text` zaten maskeli olsa da, ekrana basilan
    HER metin bir kez daha `leaks.maske`den gecer: sizinti taramasinda
    yakalanmayan bir ham deger olsa bile ekrana cikmaz.
    """
    return leaks.maske(metin) if isinstance(metin, str) else ""


#: Snippet YOKSA gosterilecek aciklama. Bos hucre ("-") kullaniciya
#: "eksik veri" izlenimi verir; `env-izlenen` turunde ise bu, icerigin
#: BILEREK okunmadigi anlamina gelir.
SNIPPET_YOK = "(içerik okunmadı)"


def _repo_adi(repo: str) -> str:
    """DB'deki tam yoldan gorunur repo adi (yolun son parcasi)."""
    return Path(repo).name or repo


def _siddet_gecerli(deger: str | None) -> str | None:
    return deger if deger in ONEMLER else None


def _sayfa_gecerli(deger: str | None) -> int:
    """Sayfa numarasi >= 1; gecersiz/0/negatif → 1."""
    try:
        sayfa = int(deger) if deger is not None else 1
    except (TypeError, ValueError):
        return 1
    return sayfa if sayfa >= 1 else 1


def ozet_verisi(conn: sqlite3.Connection) -> dict[str, Any]:
    """`/` ve `/api/ozet`: ozet kartlari."""
    satir = conn.execute(
        "SELECT COUNT(*) AS toplam, "
        "SUM(CASE WHEN dirty > 0 THEN 1 ELSE 0 END) AS kirli, "
        "SUM(CASE WHEN unpushed IS NULL THEN 1 ELSE 0 END) AS bilinmeyen, "
        "SUM(CASE WHEN unpushed > 0 AND has_remote = 1 THEN 1 ELSE 0 END) AS push_bekleyen, "
        "MAX(scanned_at) AS son_tarama "
        "FROM repos"
    ).fetchone()
    toplam = int(satir["toplam"] or 0)
    kirli = int(satir["kirli"] or 0)
    bilinmeyen = int(satir["bilinmeyen"] or 0)
    push_bekleyen = int(satir["push_bekleyen"] or 0)

    bulgu_sayaclari = {
        onem: 0 for onem in ONEMLER
    }
    for satir_b in conn.execute(
        "SELECT severity, COUNT(*) AS adet FROM findings GROUP BY severity"
    ):
        onem = satir_b["severity"]
        if onem in bulgu_sayaclari:
            bulgu_sayaclari[onem] = int(satir_b["adet"])
    toplam_bulgu = sum(bulgu_sayaclari.values())

    todo_toplam = int(conn.execute("SELECT COUNT(*) FROM todos").fetchone()[0])

    return {
        "repo_sayisi": toplam,
        "kirli_repo": kirli,
        "push_bekleyen": push_bekleyen,
        "push_bilinmeyen": bilinmeyen,
        "bulgu_sayaclari": bulgu_sayaclari,
        "toplam_bulgu": toplam_bulgu,
        "toplam_todo": todo_toplam,
        "son_tarama": satir["son_tarama"],
        "veri_bayat": veri_bayat_mi(satir["son_tarama"]),
    }


def veri_bayat_mi(son_tarama: str | None) -> bool:
    """Son tarama 24 saatten eski mi (ya da hic yok mu)?"""
    if not son_tarama:
        return True
    try:
        dt = datetime.fromisoformat(son_tarama)
    except ValueError:
        return True
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    yas = (datetime.now(timezone.utc) - dt).total_seconds()
    return yas > BAYAT_ESIK_SAAT * 3600


def yarim_is_verisi(conn: sqlite3.Connection) -> dict[str, list[dict[str, Any]]]:
    """`/yarim-is` ve `/api/yarim-is`: uc bolum.

    1) kirli: commit'lenmemis degisiklik var.
    2) pushlanmamis commit'i var ve BILINIYOR (unpushed > 0, remote'lu).
    3) push durumu BILINMIYOR (`unpushed IS NULL`) — "atlas fetch yapmaz".
    """
    kirli = conn.execute(
        "SELECT path, name, dirty, branch FROM repos WHERE dirty > 0 "
        "ORDER BY name COLLATE NOCASE, path"
    ).fetchall()
    push = conn.execute(
        "SELECT path, name, unpushed, branch FROM repos "
        "WHERE unpushed > 0 AND has_remote = 1 "
        "ORDER BY name COLLATE NOCASE, path"
    ).fetchall()
    bilinmeyen = conn.execute(
        "SELECT path, name, branch FROM repos WHERE unpushed IS NULL "
        "ORDER BY name COLLATE NOCASE, path"
    ).fetchall()

    def _repo_id(conn_: sqlite3.Connection, path: str) -> int | None:
        satir = conn_.execute("SELECT rowid FROM repos WHERE path = ?", (path,)).fetchone()
        return int(satir["rowid"]) if satir else None

    return {
        "kirli": [
            {
                "id": _repo_id(conn, r["path"]),
                "name": _temizle(r["name"]),
                "dirty": int(r["dirty"]),
                "branch": _temizle(r["branch"]),
            }
            for r in kirli
        ],
        "push_bekleyen": [
            {
                "id": _repo_id(conn, r["path"]),
                "name": _temizle(r["name"]),
                "unpushed": int(r["unpushed"]),
                "branch": _temizle(r["branch"]),
            }
            for r in push
        ],
        "push_bilinmeyen": [
            {
                "id": _repo_id(conn, r["path"]),
                "name": _temizle(r["name"]),
                "branch": _temizle(r["branch"]),
            }
            for r in bilinmeyen
        ],
    }


def bulgular_verisi(
    conn: sqlite3.Connection,
    *,
    siddet: str | None = None,
    tur: str | None = None,
    repo: str | None = None,
    sayfa: int = 1,
) -> dict[str, Any]:
    """`/sizinti` ve `/api/bulgular`: suzgecli, sayfali bulgu listesi."""
    kosul: list[str] = []
    degerler: list[Any] = []
    if siddet:
        kosul.append("severity = ?")
        degerler.append(siddet)
    if tur:
        kosul.append("kind = ?")
        degerler.append(tur)
    if repo:
        kosul.append("repo = ?")
        degerler.append(repo)
    where = (" WHERE " + " AND ".join(kosul)) if kosul else ""

    toplam = int(
        conn.execute(f"SELECT COUNT(*) FROM findings{where}", tuple(degerler)).fetchone()[0]
    )
    sayfa_boyutu = SAYFA_BOYUTU
    sayfa = max(1, sayfa)
    toplam_sayfa = max(1, (toplam + sayfa_boyutu - 1) // sayfa_boyutu)
    sayfa = min(sayfa, toplam_sayfa)
    kayma = (sayfa - 1) * sayfa_boyutu

    satirlar = conn.execute(
        "SELECT repo, kind, severity, file, line, \"commit\", snippet_redacted "
        f"FROM findings{where} "
        "ORDER BY CASE severity WHEN 'yuksek' THEN 0 WHEN 'orta' THEN 1"
        " WHEN 'dusuk' THEN 2 ELSE 3 END, repo, file, line, id "
        "LIMIT ? OFFSET ?",
        (*degerler, sayfa_boyutu, kayma),
    ).fetchall()

    kayitlar = []
    for r in satirlar:
        kayitlar.append(
            {
                "repo": _temizle(_repo_adi(r["repo"])),
                "tur": _temizle(r["kind"]),
                "tur_etiket": _temizle(TUR_ETIKETLERI.get(r["kind"], r["kind"])),
                "onem": _temizle(r["severity"]),
                "onem_etiket": _temizle(ONEM_ETIKETLERI.get(r["severity"], r["severity"])),
                "dosya": _temizle(r["file"] or ""),
                "satir": r["line"],
                "commit": _temizle(r["commit"]) if r["commit"] else "",
                "yer": "geçmişte" if r["commit"] else "çalışma ağacında",
                # Snippet EKRANA BASILMADAN once bir kez daha maskelenir.
                "snippet": _temizle(r["snippet_redacted"] or "") or SNIPPET_YOK,
            }
        )
    return {
        "kayitlar": kayitlar,
        "toplam": toplam,
        "sayfa": sayfa,
        "sayfa_boyutu": sayfa_boyutu,
        "toplam_sayfa": toplam_sayfa,
        "suzgec": {"siddet": siddet, "tur": tur, "repo": repo},
    }


def borc_verisi(conn: sqlite3.Connection) -> dict[str, Any]:
    """`/borc` ve `/api/borc`: repo basina todo yogunlugu + kayitlar."""
    ozet = conn.execute(
        "SELECT repo, COUNT(*) AS adet FROM todos GROUP BY repo "
        "ORDER BY adet DESC, repo COLLATE NOCASE"
    ).fetchall()
    kayitlar = conn.execute(
        "SELECT repo, file, line, text FROM todos ORDER BY repo, file, line, id"
    ).fetchall()

    en_cok = max((int(r["adet"]) for r in ozet), default=0)
    ozet_list = [
        {
            "repo": _temizle(_repo_adi(r["repo"])),
            "adet": int(r["adet"]),
            # Yogunluk yuzdesi: en yogun repo %100. Boslukta bolme yok.
            "oran": (int(r["adet"]) / en_cok * 100.0) if en_cok else 0.0,
        }
        for r in ozet
    ]
    hepsi = [
        {
            "repo": _temizle(_repo_adi(r["repo"])),
            "dosya": _temizle(r["file"] or ""),
            "satir": r["line"],
            # Todo metni EKRANA BASILMADAN once bir kez daha maskelenir.
            "metin": _temizle(r["text"] or ""),
        }
        for r in kayitlar
    ]
    return {
        "ozet": ozet_list,
        "kayitlar": hepsi,
        "toplam": sum(x["adet"] for x in ozet_list),
        "en_cok": en_cok,
    }


def repo_detay(conn: sqlite3.Connection, repo_id: int) -> dict[str, Any] | None:
    """`/repo/<int:id>`: repo karti + o repoya ait bulgular ve todo'lar.

    `id` = `repos` tablosunun rowid'idir (AD DEGIL: ad cakismasi olabilir).
    """
    satir = conn.execute(
        "SELECT rowid, path, name, dirty, unpushed, branch, last_commit_at, has_remote "
        "FROM repos WHERE rowid = ?",
        (int(repo_id),),
    ).fetchone()
    if satir is None:
        return None

    yol = satir["path"]
    bulgular = conn.execute(
        "SELECT kind, severity, file, line, \"commit\", snippet_redacted FROM findings "
        "WHERE repo = ? "
        "ORDER BY CASE severity WHEN 'yuksek' THEN 0 WHEN 'orta' THEN 1"
        " WHEN 'dusuk' THEN 2 ELSE 3 END, file, line, id",
        (yol,),
    ).fetchall()
    todo_list = conn.execute(
        "SELECT file, line, text FROM todos WHERE repo = ? ORDER BY file, line, id",
        (yol,),
    ).fetchall()

    return {
        "id": int(satir["rowid"]),
        "name": _temizle(satir["name"]),
        "path": _temizle(yol),
        "dirty": int(satir["dirty"]),
        "unpushed": satir["unpushed"],
        "unpushed_bilinmiyor": satir["unpushed"] is None,
        "branch": _temizle(satir["branch"] or ""),
        "last_commit_at": _temizle(satir["last_commit_at"] or ""),
        "has_remote": bool(satir["has_remote"]),
        "bulgular": [
            {
                "tur": _temizle(b["kind"]),
                "tur_etiket": _temizle(TUR_ETIKETLERI.get(b["kind"], b["kind"])),
                "onem": _temizle(b["severity"]),
                "onem_etiket": _temizle(ONEM_ETIKETLERI.get(b["severity"], b["severity"])),
                "dosya": _temizle(b["file"] or ""),
                "satir": b["line"],
                "commit": _temizle(b["commit"]) if b["commit"] else "",
                "yer": "geçmişte" if b["commit"] else "çalışma ağacında",
                "snippet": _temizle(b["snippet_redacted"] or "") or SNIPPET_YOK,
            }
            for b in bulgular
        ],
        "todos": [
            {
                "dosya": _temizle(t["file"] or ""),
                "satir": t["line"],
                "metin": _temizle(t["text"] or ""),
            }
            for t in todo_list
        ],
    }


# -- uygulama ---------------------------------------------------------------


def app_olustur(db_yolu: Path | str) -> Flask:
    """Verilen DB'yi SALT OKUNUR acan Flask uygulamasi."""
    kok = Path(__file__).parent
    uygulama = Flask(
        "atlas.web",
        template_folder=str(kok / "sablonlar"),
        static_folder=str(kok / "static"),
    )
    uygulama.config["ATLAS_DB"] = str(Path(db_yolu).expanduser())
    uygulama.config["OKABE_ITO"] = list(OKABE_ITO)
    uygulama.json.ensure_ascii = False  # Turkce karakterler JSON'da kacissiz

    @uygulama.before_request
    def _host_kontrolu() -> Response | None:
        """DNS rebinding korumasi.

        Reddedilen istek baglanti ACILMADAN doner: `_ac_baglanti` bu
        kontrolden SONRA gelir, yani 403 alan istek hicbir sorgu yapmaz.
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
        # None dondurmek ZORUNLU: aksi halde Flask yaniti burada keser.
        _baglanti_al()

    uygulama.teardown_request(_baglanti_kapat)

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

    # -- sayfalar ---------------------------------------------------------

    @uygulama.get("/")
    def ozet_sayfasi() -> str:
        conn = _baglanti_al()
        return render_template(
            "ozet.html",
            veri=ozet_verisi(conn),
            onem_renkleri=ONEM_RENKLERI,
            onemler=ONEMLER,
            onem_etiketleri=ONEM_ETIKETLERI,
        )

    @uygulama.get("/yarim-is")
    def yarim_is_sayfasi() -> str:
        return render_template("yarim_is.html", veri=yarim_is_verisi(_baglanti_al()))

    @uygulama.get("/sizinti")
    def sizinti_sayfasi() -> str:
        conn = _baglanti_al()
        siddet = _siddet_gecerli(request.args.get("siddet"))
        tur = request.args.get("tur") or None
        repo = request.args.get("repo") or None
        sayfa = _sayfa_gecerli(request.args.get("sayfa"))
        veri = bulgular_verisi(
            conn, siddet=siddet, tur=tur, repo=repo, sayfa=sayfa
        )
        return render_template(
            "sizinti.html",
            veri=veri,
            siddet=siddet,
            tur=tur,
            repo=repo,
            onemler=ONEMLER,
            onem_etiketleri=ONEM_ETIKETLERI,
            tur_etiketleri=TUR_ETIKETLERI,
            onem_renkleri=ONEM_RENKLERI,
        )

    @uygulama.get("/borc")
    def borc_sayfasi() -> str:
        return render_template("borc.html", veri=borc_verisi(_baglanti_al()))

    @uygulama.get("/repo/<int:repo_id>")
    def repo_sayfasi(repo_id: int) -> str:
        detay = repo_detay(_baglanti_al(), repo_id)
        if detay is None:
            abort(404)
        return render_template(
            "repo.html",
            repo=detay,
            onem_renkleri=ONEM_RENKLERI,
            tur_etiketleri=TUR_ETIKETLERI,
        )

    @uygulama.get("/saglik")
    def saglik() -> Response:
        return jsonify({"durum": "ok"})

    # -- api --------------------------------------------------------------

    @uygulama.get("/api/ozet")
    def api_ozet() -> Response:
        return jsonify(ozet_verisi(_baglanti_al()))

    @uygulama.get("/api/yarim-is")
    def api_yarim_is() -> Response:
        return jsonify(yarim_is_verisi(_baglanti_al()))

    @uygulama.get("/api/bulgular")
    def api_bulgular() -> Response:
        conn = _baglanti_al()
        return jsonify(
            bulgular_verisi(
                conn,
                siddet=_siddet_gecerli(request.args.get("siddet")),
                tur=request.args.get("tur") or None,
                repo=request.args.get("repo") or None,
                sayfa=_sayfa_gecerli(request.args.get("sayfa")),
            )
        )

    @uygulama.get("/api/borc")
    def api_borc() -> Response:
        return jsonify(borc_verisi(_baglanti_al()))

    return uygulama


def calistir(db_yolu: Path | str, port: int = 8770) -> None:  # pragma: no cover
    """Sunucuyu BASLATIR. Adres kodda sabittir: `127.0.0.1` (`--host` yok)."""
    app_olustur(db_yolu).run(
        host="127.0.0.1", port=port, debug=False, use_reloader=False, threaded=True
    )
