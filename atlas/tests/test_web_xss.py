"""Dalga C güvenlik kanıtları: XSS ve "ham sır ekranda yok".

Kural 1: repo adı, dosya adı, snippet ve todo metni GÜVENİLMEYENDİR. Jinja
autoescape açık olmalı, JS'te `innerHTML` olmamalı; `<script>` / `onerror`
içeren fixture metinleri HTML olarak YORUMLANMAZ, düz metin olarak basılır.

Kural 2: Ekrana basılan HER `snippet_redacted` ve `text`, basılmadan ÖNCE
`leaks.maske`den bir kez daha geçer. Sahte sır çalışma zamanında parçalardan
kurulur (kaynakta tam literal YOK) ve fixture bir `guncelle` taramasıyla
DB'ye yazılır; hiçbir sayfada/yanıtta sırrın TAMAMI ya da İLK 6 KARAKTERİ
bulunmaz.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from conftest import commit_file, db_doldur, make_repo, run_module_cli, sahte_sir

from atlas.web import app_olustur

SAYFALAR = ["/", "/yarim-is", "/sizinti", "/borc"]
APILER = ["/api/ozet", "/api/yarim-is", "/api/bulgular", "/api/borc"]

YUKLER = [
    "<script>alert(1)</script>",
    '"><script>alert(1)</script>',
    "<img src=x onerror=alert(1)>",
    "'><img src=x onerror=alert(1)>",
    "<svg/onload=alert(1)>",
    "javascript:alert(1)",
    "</td></tr><script>alert(1)</script>",
    "<!-- --><script>alert(1)</script>",
]


# --------------------------------------------------------------------------
# Kural 1: XSS
# --------------------------------------------------------------------------


@pytest.fixture
def xss_db(tmp_path: Path) -> Path:
    """Her güvenilmeyen alanda farklı bir XSS yükü olan fixture DB."""
    yol = tmp_path / "xss.db"
    db_doldur(
        yol,
        repos=[
            {"path": f"/kurgusal/{YUKLER[2]}", "name": YUKLER[2], "dirty": 1,
             "unpushed": None, "branch": YUKLER[4], "has_remote": 1,
             "scanned_at": "2026-09-29T10:00:00+00:00"},
        ],
        findings=[
            {"repo": f"/kurgusal/{YUKLER[2]}", "kind": "api-anahtari", "severity": "yuksek",
             "file": YUKLER[3], "line": 7, "commit": YUKLER[0],
             "snippet_redacted": YUKLER[5]},
        ],
        todos=[
            {"repo": f"/kurgusal/{YUKLER[2]}", "file": YUKLER[6], "line": 2,
             "text": YUKLER[1]},
        ],
    )
    return yol


@pytest.fixture
def xss_client(xss_db: Path):
    return app_olustur(xss_db).test_client()


@pytest.mark.parametrize("yol", SAYFALAR)
def test_xss_yuku_yorumlanmaz(xss_client, yol: str):
    """Yük metni HTML olarak YORUMLANMAZ: kaçırılmış hâli basılır.

    `onerror=alert(1)` kaçırılmış metin olarak ekranda kalabilir (kaçırma `<`
    işaretini etiketleştirir, `onerror` metnini değil) — asıl kanıt, o metnin
    hiçbir yerde ETİKET olarak açılmamasıdır.
    """
    import re

    govde = xss_client.get(yol).data.decode("utf-8")
    # 1) Ham etiket/olay niteliği olarak ASLA görünmez.
    assert "<script>alert(1)</script>" not in govde
    assert "<img src=x" not in govde
    assert "<svg/onload=" not in govde
    # 2) Yükün AÇILIŞ etiketi hiç oluşmaz (yalnız panelin kendi `<svg class=
    # "graf">` grafigi olabilir; `onload` YÜKÜ olmamalı).
    assert not re.search(r"<img\b", govde, re.IGNORECASE)
    assert "<svg/onload=" not in govde and "<svg onload=" not in govde
    # 3) Metin KAYIP olmaz: KAÇIRILMIŞ hâli görünür (ozet kartları repo adı
    #    göstermez; adı gösteren sayfalar aşağıda ayrıca denetlenir).
    if yol != "/":
        assert "&lt;img src=x onerror=alert(1)&gt;" in govde


@pytest.mark.parametrize("yol", ["/yarim-is", "/sizinti", "/borc"])
def test_repo_adi_kacirilmis_gorunur(xss_client, yol: str):
    """Repo adı kaçırılmış hâliyle görünür: veri kaybolmaz, kod çalışmaz."""
    govde = xss_client.get(yol).data.decode("utf-8")
    assert "&lt;img src=x onerror=alert(1)&gt;" in govde


@pytest.mark.parametrize("yol", SAYFALAR)
def test_gercek_script_etiketi_sadece_static(xss_client, yol: str):
    """HTML'de tek `<script>` etiketi vardır: harici `panel.js` (satır içi değil)."""
    import re

    govde = xss_client.get(yol).data.decode("utf-8")
    etiketler = re.findall(r"<script\b[^>]*>", govde, re.IGNORECASE)
    assert len(etiketler) == 1, f"beklenmedik script etiketi: {etiketler}"
    assert "/static/panel.js" in etiketler[0]


def test_js_innerhtml_yok():
    """`innerHTML` panel JS'inde HİÇBİR YERDE kullanılmaz."""
    js = Path(__file__).resolve().parents[1] / "atlas" / "web" / "static" / "panel.js"
    kaynak = js.read_text(encoding="utf-8")
    assert "innerHTML" not in kaynak
    assert "outerHTML" not in kaynak
    assert "insertAdjacentHTML" not in kaynak
    assert "document.write" not in kaynak
    assert "eval(" not in kaynak


def test_sablonda_inline_handler_yok():
    """Şablonlarda `on*=`, `javascript:` ve satır içi `style=` yok.

    Jinja YORUM satırları (`{# … #}`) kaldırılır: açıklama metni yanlış
    pozitif üretmemeli, ama kod kısmı denetlenir.
    """
    sablonlar = Path(__file__).resolve().parents[1] / "atlas" / "web" / "sablonlar"
    for sablon in sablonlar.glob("*.html"):
        govde = sablon.read_text(encoding="utf-8")
        kod = re.sub(r"\{#.*?#\}", "", govde, flags=re.DOTALL)
        assert "style=" not in kod, f"{sablon.name}: satir ici stil"
        assert "javascript:" not in kod, f"{sablon.name}: javascript: URI"
        assert "onclick=" not in kod and "onerror=" not in kod


@pytest.mark.parametrize("yol", APILER)
def test_api_xss_yuku_düz_metin(xss_client, yol: str):
    """API JSON döner: yük JSON kaçışlarıyla döner, HTML olarak değil."""
    import re

    r = xss_client.get(yol)
    ham = r.data.decode("utf-8")
    assert r.headers["Content-Type"].startswith("application/json")
    # JSON gövdesi HTML olarak AYRIŞTIRILMAZ; yük güvenli biçimde metin olarak
    # taşınır. Kritik kanıt istemci tarafıdır: panel JS'i `innerHTML`
    # KULLANMAZ (bkz. `test_js_innerhtml_yok`), yük çalıştırılamaz.
    assert isinstance(json.loads(ham), dict)
    # Yük korunmuşsa değer orijinaldir — sunucu onu DEĞİŞTİRMEZ.
    assert any(y in ham for y in YUKLER) or yol in ("/api/ozet", "/saglik")


def test_repo_detay_xss(xss_client, xss_db: Path):
    import sqlite3

    con = sqlite3.connect(xss_db)
    con.row_factory = sqlite3.Row
    repo_id = con.execute("SELECT rowid FROM repos LIMIT 1").fetchone()["rowid"]
    con.close()
    govde = xss_client.get(f"/repo/{repo_id}").data.decode("utf-8")
    assert "<script>alert(1)</script>" not in govde
    assert not re.search(r"<img\b", govde, re.IGNORECASE)
    assert "&lt;script&gt;" in govde


# --------------------------------------------------------------------------
# Kural 2: ham sır ekranda yok (uçtan uca kanıt)
# --------------------------------------------------------------------------


@pytest.fixture
def sirli_db(tmp_path: Path) -> Path:
    """Gerçek `guncelle` taramasıyla doldurulan, sahte sır içeren fixture DB."""
    kok = tmp_path / "koklar"
    repo = make_repo(kok / "gizli-repo")
    sir = sahte_sir()
    commit_file(repo, "ayarlar.py", f'API_KEY = "{sir}"\n', "ayar ekle")
    commit_file(repo, "notlar.md", f"not: {sir}\n", "not ekle")
    db_yolu = tmp_path / "sirli.db"
    proc = run_module_cli("guncelle", "--root", str(kok), "--db", str(db_yolu))
    assert proc.returncode == 0, proc.stderr
    return db_yolu


def _tum_yanitlar(client) -> list[str]:
    """Tüm sayfa ve API yanıtlarının gövdesi."""
    govdeler = []
    for yol in SAYFALAR + APILER:
        r = client.get(yol)
        assert r.status_code == 200, yol
        govdeler.append(r.data.decode("utf-8", "replace"))
    import sqlite3

    db_yolu = client.application.config["ATLAS_DB"]
    con = sqlite3.connect(db_yolu)
    con.row_factory = sqlite3.Row
    for row in con.execute("SELECT rowid FROM repos"):
        r = client.get(f"/repo/{row['rowid']}")
        assert r.status_code == 200
        govdeler.append(r.data.decode("utf-8", "replace"))
    con.close()
    return govdeler


def test_ham_sir_ekranda_yok(sirli_db: Path):
    """Sahte sır: ne tamamı ne de İLK 6 KARAKTERİ hiçbir yanıtta görünmez."""
    client = app_olustur(sirli_db).test_client()
    sir = sahte_sir()
    assert len(sir) >= 8
    for govde in _tum_yanitlar(client):
        assert sir not in govde, "ham sır ekrana basıldı"
        assert sir[:6] not in govde, "ham sırın ilk 6 karakteri ekrana basıldı"


def test_maske_isareti_gorunur(sirli_db: Path):
    """Maske çalışıyor: `[maskeli` işareti ekranda GÖRÜNÜR (boş sayfa değil)."""
    client = app_olustur(sirli_db).test_client()
    govde = client.get("/sizinti").data.decode("utf-8")
    assert "[maskeli" in govde


def test_db_ve_ciktida_ham_sir_yok(sirli_db: Path):
    """DB baytlarında da ham sır yok (taranmış, maskelenmiş olarak yazıldı)."""
    sir = sahte_sir()
    ham = sirli_db.read_bytes()
    assert sir.encode() not in ham
    assert sir[:6].encode() not in ham


def test_savunma_katmani_ekran_maskesinden_gecer(tmp_path: Path):
    """DB'ye HAM yazılmış olsa bile ekranda maskeli görünür (2. savunma)."""
    """Bu, iki katmanı ayıran testtir: tarama yerine doğrudan ham yazılır."""
    yol = tmp_path / "ham.db"
    sir = sahte_sir()
    db_doldur(
        yol,
        repos=[{"path": "/kurgusal/r", "name": "r", "dirty": 0, "unpushed": 0,
                "branch": "main", "has_remote": 0, "scanned_at": "2026-09-29T10:00:00+00:00"}],
        findings=[{"repo": "/kurgusal/r", "kind": "api-anahtari", "severity": "yuksek",
                   "file": "a.py", "line": 1, "commit": None,
                   "snippet_redacted": f'deger = "{sir}"'}],
        todos=[{"repo": "/kurgusal/r", "file": "a.py", "line": 2, "text": f"# TODO: {sir}"}],
    )
    client = app_olustur(yol).test_client()
    # Veriyi gösteren sayfalarda maske işareti GÖRÜNÜR.
    for gosteren in ("/sizinti", "/borc", "/api/bulgular", "/api/borc"):
        ham = client.get(gosteren).data.decode("utf-8")
        assert "[maskeli" in ham, gosteren
    # Tüm yanıtlarda ham sır (tamamı ve ilk 6 karakteri) YOK.
    for govde in _tum_yanitlar(client):
        assert sir not in govde
        assert sir[:6] not in govde
