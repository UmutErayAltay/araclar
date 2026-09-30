"""`atlas durum --json` sozlesmesi (kule entegrasyonu).

Kapsam: sozlesme semasi (anahtar/tip/surum/kaynak), bos DB / DB yok / tablo
eksik (eski sema) durumlari, BULGU SIZDIRMAZ (fixture'daki sahte "gizli"
dize ciktinin hicbir yerinde gecmez), `/api/ozet` ciktisinin refactor
sonrasi ayni kaldigi ve CLI'nin stdout/cikis kodu davranisi.

Tum fixture verisi KURGUSALDIR; gercek ad, yol, anahtar veya e-posta YOK.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from conftest import db_doldur, run_module_cli

from atlas import durum
from atlas.web import app_olustur
from atlas.web.sunucu import ozet_verisi as web_ozet_verisi

#: Sozlesmede tanimli alanlar. Yeni alan EKLENEBILIR; bu kumeye gore hepsi
#: mevcut olmak ZORUNDA.
SOZLESME_ALANLARI = {
    "surum", "kaynak", "son_tarama", "veri_bayat", "repo_sayisi", "kirli_repo",
    "push_bekleyen", "push_bilinmeyen", "bayat_readme", "bulgu_toplam",
    "bulgu_onem", "todo_toplam",
}

SAYI_ALANLARI = (
    "repo_sayisi", "kirli_repo", "push_bekleyen", "push_bilinmeyen",
    "bayat_readme", "bulgu_toplam", "todo_toplam",
)

#: Fixture'a bilerek konan, TANINABILIR sahte "gizli" dizi. Kaynakta tam
#: literal olarak yazilmaz; parcalardan kurulur. Ciktida GECMEMSEN
#: maskeleme/tasima dogru calisiyor demektir.
SAhte_GIZLI = "GIZLI-FIXTURE-" + "d0k0r" + "-4711"


def _taze(zaman_saat_geri: int = 1) -> str:
    """`scanned_at` icin GORECELI zaman (test yarin da gecer)."""
    return (datetime.now(timezone.utc) - timedelta(hours=zaman_saat_geri)).isoformat(
        timespec="seconds"
    )


def _sirli_fixture_db(yol: Path) -> Path:
    """BULGU SATIRLARI iceren kurgusal DB.

    Icerege taninabilir sahte gizli dizi, kisisel yol, anahtar ve commit
    basligi yazilir; bunlarin HICBIRI sozlesme ciktisinda gorunmemelidir.
    """
    return db_doldur(
        yol,
        repos=[
            {"path": "/kurgusal/ornek-api", "name": "ornek-api", "dirty": 3,
             "unpushed": 2, "branch": "main", "has_remote": 1, "scanned_at": _taze()},
            {"path": "/kurgusal/demo-arayuz", "name": "demo-arayuz", "dirty": 0,
             "unpushed": None, "branch": "feat/yeni", "has_remote": 1, "scanned_at": _taze()},
            {"path": "/kurgusal/temiz-repo", "name": "temiz-repo", "dirty": 0,
             "unpushed": 0, "branch": "main", "has_remote": 0, "scanned_at": _taze()},
        ],
        findings=[
            # DORT ayirt edilebilir sizinti cesidi: bulgu sayaci 5'e gelmeli,
            # ama metinler/anahtarlar ciktida GORUNMEMELI.
            {"repo": "/kurgusal/ornek-api", "kind": "api-anahtari", "severity": "yuksek",
             "file": "app/sablon.py", "line": 12, "commit": "abc1234",
             "snippet_redacted": f"…{SAhte_GIZLI}…"},
            {"repo": "/kurgusal/ornek-api", "kind": "ozel-anahtar", "severity": "yuksek",
             "file": "certs/kimlik.pem", "line": 1, "commit": "def5678",
             "snippet_redacted": SAhte_GIZLI},
            {"repo": "/kurgusal/ornek-api", "kind": "e-posta", "severity": "yuksek",
             "file": "C:/Users/kurgusal-kullanici/proje.py", "line": 3, "commit": None,
             "snippet_redacted": "kullanici@ornek.invalid"},
            {"repo": "/kurgusal/ornek-api", "kind": "gorsel-elle-kontrol", "severity": "dusuk",
             "file": "docs/ekran.png", "commit": None, "snippet_redacted": None},
            {"repo": "/kurgusal/demo-arayuz", "kind": "env-izlenen", "severity": "bilgi",
             "file": ".env", "commit": None, "snippet_redacted": None},
        ],
        todos=[
            {"repo": "/kurgusal/ornek-api", "file": f"mod{i}.py", "line": i, "text": "TODO: kurgusal is"}
            for i in range(4)
        ],
        readmes=[
            {"repo": "/kurgusal/ornek-api", "skor": 9, "seviye": "bayat",
             "behavior_commits_after": 7, "screenshot_age_days": 45},
            {"repo": "/kurgusal/demo-arayuz", "skor": 5, "seviye": "eskiyor",
             "behavior_commits_after": 4, "screenshot_age_days": 10},
            {"repo": "/kurgusal/temiz-repo", "skor": 1, "seviye": "taze",
             "behavior_commits_after": 1, "screenshot_age_days": 1},
        ],
    )


@pytest.fixture
def sirli_db(tmp_path: Path) -> Path:
    return _sirli_fixture_db(tmp_path / "sirli.db")


def _calistir_db(db_path: Path, *ek: str) -> subprocess.CompletedProcess:
    return run_module_cli("durum", "--db", str(db_path), *ek)


def _json_stdout(proc: subprocess.CompletedProcess) -> dict:
    """stdout'un TAMAMININ tek JSON nesnesi oldugunu dogrular."""
    ham = proc.stdout
    assert ham.endswith("\n"), "stdout satir sonuyla bitmeli"
    govde = json.loads(ham)  # bastan sona tek nesne: fazladan satir HATA
    assert isinstance(govde, dict), f"JSON nesnesi bekleniyordu: {type(govde)}"
    return govde


# --------------------------------------------------------------------------
# Sozlesme semasi
# --------------------------------------------------------------------------


def test_sozlesme_tum_alanlar(sirli_db: Path):
    v = _json_stdout(_calistir_db(sirli_db, "--json"))
    assert SOZLESME_ALANLARI <= set(v), f"eksik alan: {SOZLESME_ALANLARI - set(v)}"
    assert v["surum"] == 1
    assert v["kaynak"] == "atlas"


def test_sozlesme_sayi_tipleri(sirli_db: Path):
    v = _json_stdout(_calistir_db(sirli_db, "--json"))
    for alan in SAYI_ALANLARI:
        deger = v[alan]
        # `bool` bir `int` alt sinifidir; sayi alanlari bool OLMAMALI.
        assert isinstance(deger, int) and not isinstance(deger, bool), alan
        assert deger >= 0, alan
    assert isinstance(v["veri_bayat"], bool)
    assert isinstance(v["bulgu_onem"], dict)
    for onem, adet in v["bulgu_onem"].items():
        assert isinstance(adet, int) and not isinstance(adet, bool)
        assert adet >= 0


def test_sozlesme_bulgu_onem_anahtarlari(sirli_db: Path):
    """`bulgu_onem` anahtarlari `ONEMLER`'den gelir; dort anahtar da vardir."""
    v = _json_stdout(_calistir_db(sirli_db, "--json"))
    assert set(v["bulgu_onem"]) == set(durum.ONEMLER)


def test_sozlesme_sayilari_dogru(sirli_db: Path):
    """Fixture'daki bilinen sayilar sozlesmeye dogru yansimalidir."""
    v = _json_stdout(_calistir_db(sirli_db, "--json"))
    assert v["repo_sayisi"] == 3
    assert v["kirli_repo"] == 1
    assert v["push_bekleyen"] == 1      # unpushed>0 VE has_remote=1
    assert v["push_bilinmeyen"] == 1     # unpushed IS NULL
    assert v["bayat_readme"] == 2        # bayat + eskiyor
    assert v["bulgu_toplam"] == 5
    assert v["todo_toplam"] == 4
    assert v["bulgu_onem"]["yuksek"] == 3
    assert v["bulgu_onem"]["bilgi"] == 1
    assert v["bulgu_onem"]["dusuk"] == 1
    assert v["bulgu_onem"]["orta"] == 0  # yok sayilir ama 0 olarak raporlanir
    assert v["veri_bayat"] is False


def test_son_tarama_iso8601(sirli_db: Path):
    """`son_tarama` ISO-8601 metnidir (tarih/zaman degil)."""
    v = _json_stdout(_calistir_db(sirli_db, "--json"))
    assert isinstance(v["son_tarama"], str)
    assert datetime.fromisoformat(v["son_tarama"]).tzinfo is not None


def test_stdout_tek_satir(sirli_db: Path):
    """Sozlesme: stdout'da YALNIZCA tek JSON nesnesi, baska satir yok."""
    proc = _calistir_db(sirli_db, "--json")
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.count("\n") == 1, repr(proc.stdout)


def test_stdout_ascii_guvenli(sirli_db: Path):
    """Windows uyumu: `ensure_ascii=True` — stdout saf ASCII kalsin."""
    proc = _calistir_db(sirli_db, "--json")
    ham = proc.stdout
    assert ham.isascii(), f"stdout ASCII disi karakter tasiyor: {ham!r}"


# --------------------------------------------------------------------------
# Gizlilik: bulgu icerigi/yol/anahtar CIKTI DISINDA
# --------------------------------------------------------------------------


def test_bulgu_metni_cikta_yok(sirli_db: Path):
    """Fixture'daki sahte gizli dize ciktinin HICBIR yerinde gecmez.

    Hem JSON metni hem ayristirilmis nesne denetlenir; ayrica kisiyel yol,
    anahtar degeri, commit basligi ve bulgu dosya yollari da aranir.
    """
    proc = _calistir_db(sirli_db, "--json")
    ham = proc.stdout

    assert SAhte_GIZLI not in ham, "sahte gizli dize ciktiya sizdi"
    # Parcalara bolunmus hali de gecmemeli.
    assert "d0k0r" not in ham and "4711" not in ham

    # Kanit: dize gercekten DB'de VAR (yoksa test bos gecerdi).
    conn = durum.db_ac(sirli_db)
    try:
        sayi = conn.execute(
            "SELECT COUNT(*) FROM findings WHERE snippet_redacted LIKE ?", (f"%{SAhte_GIZLI}%",)
        ).fetchone()[0]
    finally:
        conn.close()
    assert sayi == 2, f"fixture kaniti: DB'de {sayi} satir var, 2 bekleniyordu"

    v = _json_stdout(proc)
    # Butun JSON string'inde de yok (ayristirma sonrasi).
    assert SAhte_GIZLI not in json.dumps(v, ensure_ascii=False)
    # Bulgunun KENDISI: dosya, commit, e-posta, kisisel yol, anahtar degeri.
    for sizinti in (
        "sablon.py", "kimlik.pem", "ekran.png", ".env", "abc1234", "def5678",
        "kullanici@ornek.invalid", "kurgusal-kullanici", "C:/Users", "api-anahtari",
        "ornek-api", "demo-arayuz", "temiz-repo", "feat/yeni", "/kurgusal",
    ):
        assert sizinti not in ham, f"bulgu/repo ayrintisi sizdi: {sizinti}"


def test_hata_govdesi_sir_tasimaz(tmp_path: Path):
    """Hata kodu SABITTIR; istisna metni, yol veya SQL girmez."""
    bozuk = tmp_path / "bozuk.db"
    bozuk.write_bytes(b"bu bir sqlite dosyasi degil, gizli: " + SAhte_GIZLI.encode())

    proc = _calistir_db(bozuk, "--json")
    v = _json_stdout(proc)
    assert proc.returncode == 1
    assert v == {"surum": 1, "kaynak": "atlas", "hata": "okunamadi"}
    # SQLite'in hata metaji yol tasiyabilir; hicbiri cikida olmamali.
    assert str(bozuk) not in proc.stdout and str(bozuk) not in proc.stderr
    assert SAhte_GIZLI not in proc.stdout and SAhte_GIZLI not in proc.stderr
    assert "sqlite" not in proc.stdout.lower()


# --------------------------------------------------------------------------
# Bos DB / DB yok / tablo eksik (eski sema)
# --------------------------------------------------------------------------


def test_db_yok_hata_kodu(tmp_path: Path):
    """DB dosyasi YOK: sabit `db_yok`, cikis kodu 1, stdout'ta JSON."""
    proc = _calistir_db(tmp_path / "hic-yok.db", "--json")
    v = _json_stdout(proc)
    assert proc.returncode == 1
    assert v == {"surum": 1, "kaynak": "atlas", "hata": "db_yok"}
    assert proc.stdout.count("\n") == 1


def test_db_yok_stderr_bos_sir_yok(tmp_path: Path):
    """Hata durumunda da stderr'de yol/istisna metni BASILMAZ."""
    yok = tmp_path / "yok.db"
    proc = _calistir_db(yok, "--json")
    assert proc.returncode == 1
    assert str(yok) not in proc.stderr
    assert "Traceback" not in proc.stderr


def test_bos_db_sifir_ve_bayat(tmp_path: Path):
    """DB var ama hic satir yok: sayilar 0, `son_tarama: null`, bayat true."""
    from atlas import db as db_mod

    yol = tmp_path / "bos.db"
    conn = db_mod.connect(yol)
    conn.close()

    v = _json_stdout(_calistir_db(yol, "--json"))
    assert v["surum"] == 1 and v["kaynak"] == "atlas"
    assert v["son_tarama"] is None, "hic tarama yoksa zaman null (0 DEGIL)"
    assert v["veri_bayat"] is True
    for alan in SAYI_ALANLARI:
        assert v[alan] == 0, alan
    assert v["bulgu_onem"] == {onem: 0 for onem in durum.ONEMLER}


def _eski_sema_db(yol: Path) -> Path:
    """Dalga D ONCESI sema: `repos`/`findings`/`todos` var, `readme_status` YOK.

    `unpushed` NOT NULL (sema surumu 0) — A oncesinden kalma gercek DB sekli.
    """
    conn = sqlite3.connect(str(yol))
    try:
        conn.execute(
            "CREATE TABLE repos (path TEXT PRIMARY KEY, name TEXT NOT NULL, "
            "scanned_at TEXT NOT NULL, dirty INTEGER NOT NULL DEFAULT 0, "
            "unpushed INTEGER NOT NULL, branch TEXT, last_commit_at TEXT, "
            "has_remote INTEGER NOT NULL DEFAULT 0)"
        )
        conn.execute(
            "CREATE TABLE findings (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "repo TEXT NOT NULL, kind TEXT NOT NULL, severity TEXT, file TEXT, "
            "line INTEGER, \"commit\" TEXT, snippet_redacted TEXT)"
        )
        conn.execute(
            "CREATE TABLE todos (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "repo TEXT NOT NULL, file TEXT, line INTEGER, text TEXT)"
        )
        conn.execute(
            "INSERT INTO repos (path, name, scanned_at, dirty, unpushed, branch, has_remote) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("/kurgusal/eski", "eski", _taze(), 1, 2, "main", 1),
        )
        conn.execute(
            "INSERT INTO findings (repo, kind, severity, file, \"commit\", snippet_redacted) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("/kurgusal/eski", "api-anahtari", "yuksek", "a.py", "aaa", SAhte_GIZLI),
        )
        conn.commit()
    finally:
        conn.close()
    return yol


def test_eski_sema_tablo_eksik(tmp_path: Path):
    """`readme_status` YOKSA (eski sema) hata DEGILDIR: sayilar 0, kod 0."""
    yol = _eski_sema_db(tmp_path / "eski.db")

    proc = _calistir_db(yol, "--json")
    v = _json_stdout(proc)
    assert proc.returncode == 0, proc.stderr
    assert "hata" not in v
    assert v["surum"] == 1 and v["kaynak"] == "atlas"
    assert v["repo_sayisi"] == 1
    assert v["kirli_repo"] == 1
    assert v["push_bekleyen"] == 1
    assert v["bulgu_toplam"] == 1          # eski semada bulgu YINE okunur
    assert v["bulgu_onem"]["yuksek"] == 1
    assert v["bayat_readme"] == 0          # tablo yok -> 0, HATA degil
    assert v["todo_toplam"] == 0
    assert v["veri_bayat"] is False
    assert SAhte_GIZLI not in proc.stdout


def test_okunamayan_db_hata_kodu(tmp_path: Path):
    """Bozuk/okunamayan dosya: sabit `okunamadi` (yol/SQL cikmaz)."""
    bozuk = tmp_path / "bozuk.db"
    bozuk.write_text("bu sqlite degil", encoding="utf-8")
    proc = _calistir_db(bozuk, "--json")
    v = _json_stdout(proc)
    assert proc.returncode == 1
    assert v["hata"] == "okunamadi"
    assert str(bozuk) not in proc.stdout


def test_bozuk_db_sema_kurulmaz(tmp_path: Path):
    """Hata durumunda komut HICbir sey YAZMAZ: dosya baytlari ayni."""
    bozuk = tmp_path / "bozuk.db"
    bozuk.write_text("bu sqlite degil", encoding="utf-8")
    once = bozuk.read_bytes()
    _calistir_db(bozuk, "--json")
    assert bozuk.read_bytes() == once, "komut dosyayi degistirdi"


def test_durum_sifir_dosya_doldurmaz(tmp_path: Path):
    """DB YOKSA `-wal`/`-shm` gibi yan dosyalar OLUSMAZ (yazma yok)."""
    yol = tmp_path / "yok.db"
    _calistir_db(yol, "--json")
    assert list(tmp_path.iterdir()) == [], "okuma disi yan dosya olustu"


# --------------------------------------------------------------------------
# Salt-okunurluk ve yan etkisizlik
# --------------------------------------------------------------------------


def test_db_salt_okunur_acilir(sirli_db: Path):
    """`atlas durum` DB'yi `mode=ro` ile acar: yazma denemesi hata verir."""
    conn = durum.db_ac(sirli_db)
    try:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("INSERT INTO repos (path, name, scanned_at) VALUES ('x','x','x')")
    finally:
        conn.close()


def test_calistirma_db_yi_degistirmez(sirli_db: Path):
    """Komut calistiktan sonra DB baytlari BIREBIR ayni (yazma/yeniden tarama yok)."""
    once = sirli_db.read_bytes()
    proc = _calistir_db(sirli_db, "--json")
    assert proc.returncode == 0
    assert sirli_db.read_bytes() == once


def test_tarama_tetiklenmez(sirli_db: Path, tmp_path: Path):
    """Komut yalniz OKUR: yeni repo satiri YAZILMAZ, `scanned_at` degismez."""
    conn = durum.db_ac(sirli_db)
    try:
        once = [tuple(r) for r in conn.execute("SELECT * FROM repos ORDER BY path")]
    finally:
        conn.close()
    _calistir_db(sirli_db, "--json")
    conn = durum.db_ac(sirli_db)
    try:
        sonra = [tuple(r) for r in conn.execute("SELECT * FROM repos ORDER BY path")]
    finally:
        conn.close()
    assert once == sonra


# --------------------------------------------------------------------------
# `/api/ozet` ciktisi refactor oncesi/sonrasi AYNI
# --------------------------------------------------------------------------


def test_api_ozet_ayni_sayi_kaynagi(sirli_db: Path):
    """Web ve CLI AYNI fonksiyondan sayi alir; `/api/ozet` sekli korunur."""
    conn = durum.db_ac(sirli_db)
    try:
        ortak = web_ozet_verisi(conn)
    finally:
        conn.close()
    v = _json_stdout(_calistir_db(sirli_db, "--json"))

    assert v["repo_sayisi"] == ortak["repo_sayisi"]
    assert v["kirli_repo"] == ortak["kirli_repo"]
    assert v["push_bekleyen"] == ortak["push_bekleyen"]
    assert v["push_bilinmeyen"] == ortak["push_bilinmeyen"]
    assert v["bayat_readme"] == ortak["bayat_readme"]
    assert v["bulgu_toplam"] == ortak["toplam_bulgu"]
    assert v["todo_toplam"] == ortak["toplam_todo"]
    assert v["son_tarama"] == ortak["son_tarama"]
    assert v["veri_bayat"] == ortak["veri_bayat"]
    assert v["bulgu_onem"] == ortak["bulgu_sayaclari"]


def test_api_ozet_anahtarlari_geriye_uyumlu(sirli_db: Path):
    """Refactor `/api/ozet` ciktisindan HICBIR anahtar KAYBOLMADI."""
    c = app_olustur(sirli_db).test_client()
    v = json.loads(c.get("/api/ozet").data.decode("utf-8"))
    for eski in ("repo_sayisi", "kirli_repo", "push_bekleyen", "push_bilinmeyen",
                 "bulgu_sayaclari", "toplam_bulgu", "toplam_todo", "son_tarama",
                 "veri_bayat", "readme_sayaclari", "readme_toplam", "bayat_readme"):
        assert eski in v, f"geriye uyumluluk bozuldu: {eski}"
    assert set(v["bulgu_sayaclari"]) == set(durum.ONEMLER)


def test_api_ozet_eski_sema_da_calisir(tmp_path: Path):
    """`readme_status` olmayan DB'de `/api/ozet` 200 verir (0 degerleriyle)."""
    yol = _eski_sema_db(tmp_path / "eski-api.db")
    r = app_olustur(yol).test_client().get("/api/ozet")
    assert r.status_code == 200
    v = json.loads(r.data.decode("utf-8"))
    assert v["bayat_readme"] == 0
    assert v["readme_toplam"] == 0
    assert v["toplam_bulgu"] == 1


# --------------------------------------------------------------------------
# CLI davranisi
# --------------------------------------------------------------------------


def test_json_ckisi_sifir(sirli_db: Path):
    proc = _calistir_db(sirli_db, "--json")
    assert proc.returncode == 0
    assert proc.stderr == ""


def test_jsonsuz_tek_satir_ozet(sirli_db: Path):
    """`atlas durum` (--json'siz): tek satir insan ozeti."""
    proc = _calistir_db(sirli_db)
    assert proc.returncode == 0
    satirlar = [s for s in proc.stdout.splitlines() if s.strip()]
    assert len(satirlar) == 1, f"tek satir bekleniyordu: {satirlar}"
    satir = satirlar[0]
    for beklenen in ("repo 3", "kirli 1", "push bekleyen 1", "bayat README 2",
                     "bulgu 5", "todo 4", "veri taze"):
        assert beklenen in satir, beklenen
    # Ozet satirinde de sizinti/repo ayrintisi OLMAMALI.
    for sizinti in (SAhte_GIZLI, "ornek-api", "sablon.py", "/kurgusal"):
        assert sizinti not in satir, sizinti


def test_jsonsuz_tek_satir_bos_db(tmp_path: Path):
    """Bos DB'de `--json`'suz cikti da tek satirdir (0'lar)."""
    from atlas import db as db_mod

    yol = tmp_path / "bos.db"
    conn = db_mod.connect(yol)
    conn.close()
    proc = _calistir_db(yol)
    assert proc.returncode == 0
    satirlar = [s for s in proc.stdout.splitlines() if s.strip()]
    assert len(satirlar) == 1
    assert "repo 0" in satirlar[0] and "veri bayat" in satirlar[0]


def test_help_ve_tam_komut_hazir():
    """Yeni alt komut argparse'te gorunur."""
    yardim = run_module_cli("durum", "--help")
    assert yardim.returncode == 0
    assert "--json" in yardim.stdout
    assert "--db" in yardim.stdout
    kok = run_module_cli("--help")
    assert "durum" in kok.stdout


def test_sonraki_ag_sureci_yok(sirli_db: Path):
    """Komut hizli (< 2 sn): tarama/LLM adimi calismaz."""
    import time

    basla = time.monotonic()
    proc = _calistir_db(sirli_db, "--json")
    gecen = time.monotonic() - basla
    assert proc.returncode == 0
    assert gecen < 2.0, f"cok yavas: {gecen:.2f} sn"
