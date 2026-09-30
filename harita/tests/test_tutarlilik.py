"""Dalga C — vault↔repo tutarlılığı (`harita tutarlilik`) testleri.

Tüm içerik KURGUSALDIR. atlas DB'si testler İÇİNDE SQL ile kurulur (atlas
paketi import edilmez), böylece harici bir taramaya bağımlılık yoktur.

Kapsam: her kuralın pozitif+negatif durumu, `unpushed` NULL'da "pushlanmamış"
iddiasının olmaması, eşleme öncelikleri, eşleşmeyen/klonsuz repo, eski atlas
verisi uyarısı, şema uyuşmazlığı, durum sözcüğü tablosu (Türkçe/İngilizce,
İ/ı), `--json` ve `--kati`.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from conftest import yaz
from harita import tutarlilik as tut
from harita.cli import main as cli_main

BUGUN = date(2026, 3, 10)


def _iso(gun_once: int) -> str:
    """`bugun - gun_once` günü UTC ISO damgası."""
    t = datetime.combine(BUGUN - timedelta(days=gun_once), datetime.min.time(),
                         tzinfo=timezone.utc)
    return t.isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# atlas şeması (atlas paketi İÇE AKTARILMAZ; şema burada elle kurulur)
# ---------------------------------------------------------------------------

ATLAS_SEMA = """
CREATE TABLE repos (
    path            TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    scanned_at      TEXT NOT NULL,
    dirty           INTEGER NOT NULL DEFAULT 0,
    unpushed        INTEGER,
    branch          TEXT,
    last_commit_at  TEXT,
    has_remote      INTEGER NOT NULL DEFAULT 0
);
"""


def atlas_kur(
    yol: Path,
    satirlar: list[dict] | None = None,
    sema: str = ATLAS_SEMA,
) -> Path:
    """Test atlas DB'sini verilen satırlarla kurar."""
    baglanti = sqlite3.connect(yol)
    try:
        baglanti.executescript(sema)
        for s in satirlar or []:
            baglanti.execute(
                "INSERT INTO repos (path, name, scanned_at, dirty, unpushed, branch, "
                "last_commit_at, has_remote) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    s.get("path", f"/tmp/{s['name']}"),
                    s["name"],
                    s.get("scanned_at", _iso(0)),
                    s.get("dirty", 0),
                    s.get("unpushed", 0),
                    s.get("branch", "main"),
                    s.get("last_commit_at", _iso(1)),
                    s.get("has_remote", 1),
                ),
            )
        baglanti.commit()
    finally:
        baglanti.close()
    return yol


def repo(**kw) -> dict:
    """Kısayol: `repo(name="atlas", unpushed=None)`."""
    temel = {"name": "atlas", "scanned_at": _iso(0), "dirty": 0, "unpushed": 0,
             "branch": "main", "last_commit_at": _iso(2), "has_remote": 1}
    temel.update(kw)
    return temel


# ---------------------------------------------------------------------------
# Kurgusal vault
# ---------------------------------------------------------------------------


@pytest.fixture
def tc_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    vault.mkdir()
    # Eşleşen ve eşleşmeyen notlar.
    yaz(vault, "🏰 300-Projects/Atlas.md", f"""---
title: Atlas
repo: atlas
status: planlandı
---
# Atlas

Durum: planlandı
İlgili: [[harita]]
""")
    yaz(vault, "🏰 300-Projects/Orkestra.md", """---
title: Orkestra
repo: orkestra
status: bitti
---
# Orkestra
Bitti.
""")
    yaz(vault, "🏰 300-Projects/Harita.md", """---
title: Harita
status: aktif
---
# Harita

Devam ediyor. Repo: `harita`
""")
    yaz(vault, "🏰 300-Projects/Serbest.md", """---
title: Serbest Not
status: planlandı
---
# Serbest Not

Bu not HİÇBİR repo'ya eşleşmez; bulgu üretmemelidir.
""")
    yaz(vault, "🔮 850-Companion/Threads.md", """# Threads

## Active Threads
### Thread: 🟢 orkestra — orkestra tarafı

**Status:** aktif

### Thread: 🟡 qwen-lab — model denemeleri

**Status:** sürüyor, repo `qwen-lab`

### Thread: (işaretsiz) atlas — kapalı kalmış olabilir

**Status:** bitti
""")
    return vault


# ---------------------------------------------------------------------------
# Durum sözcüğü tablosu
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sozcuk,grup",
    [
        ("planlandı", "planli"), ("Planlandi", "planli"), ("PLANNED", "planli"),
        ("planned", "planli"), ("kod yok", "planli"), ("Henüz Kod Yok", "planli"),
        ("taslak", "planli"), ("fikir", "planli"),
        ("aktif", "aktif"), ("Aktif", "aktif"), ("devam", "aktif"),
        ("in progress", "aktif"), ("sürüyor", "aktif"), ("wip", "aktif"),
        ("tamam", "bitti"), ("TAMAM", "bitti"), ("bitti", "bitti"),
        ("done", "bitti"), ("archived", "bitti"), ("arşiv", "bitti"),
        ("kapalı", "bitti"), ("finished", "bitti"),
    ],
)
def test_durum_sozcukleri(sozcuk: str, grup: str) -> None:
    assert tut.durum_grup(sozcuk) == grup


@pytest.mark.parametrize("sozcuk", ["bilinmeyen", "", "   ", "xyzzy", "1234"])
def test_bilinmeyen_durum_sozcugu(sozcuk: str) -> None:
    assert tut.durum_grup(sozcuk) is None


def test_durum_sozcugu_i_icen_donusumler() -> None:
    """İ/ı ve I/i normalize ile eşleşir."""
    assert tut.durum_grup("TAMAM") == "bitti"
    assert tut.durum_grup("BİTTİ") == "bitti"
    assert tut.durum_grup("aktif") == "aktif"
    assert tut.durum_grup("Aktif") == "aktif"
    assert tut.durum_grup("Planlandı") == "planli"


def test_durum_metni_ara_satir_ve_frontmatter() -> None:
    assert tut.durum_metni_ara("**Durum:** planlandı") == "planli"
    assert tut.durum_metni_ara("status: bitti") == "bitti"
    assert tut.durum_metni_ara("**Durum:** aktif, devam ediyor") == "aktif"
    assert tut.durum_metni_ara("**Durum:** bilinmeyen") is None


def test_durum_satiri_frontmatteri_ezer(tmp_path: Path) -> None:
    vault = tmp_path / "v"
    vault.mkdir()
    yaz(vault, "P.md", """---
status: planlandı
---
# P

**Durum:** bitti
""")
    notlar = tut._notlari_tara(vault)
    assert notlar[0].durum == "bitti", "**Durum:** satırı frontmatter'ı EZER"


# ---------------------------------------------------------------------------
# atlas okuma / şema / tazelik
# ---------------------------------------------------------------------------


def test_atlas_okuma_basarili(tmp_path: Path) -> None:
    db = atlas_kur(tmp_path / "a.db", [repo(name="atlas")])
    veri = tut.atlas_oku(db)
    assert len(veri.repolar) == 1
    assert veri.repolar[0].name == "atlas"
    assert veri.repolar[0].last_commit_at is not None


def test_atlas_sema_uyusmazligi_net_hata(tmp_path: Path) -> None:
    """Beklenmeyen şema → açık hata (sessizce boş sonuç DEĞİL)."""
    yol = tmp_path / "bozuk.db"
    baglanti = sqlite3.connect(yol)
    baglanti.executescript(
        "CREATE TABLE repos (path TEXT PRIMARY KEY, name TEXT, scanned_at TEXT);"
    )
    baglanti.commit()
    baglanti.close()
    with pytest.raises(SystemExit) as exc:
        tut.atlas_oku(yol)
    mesaj = str(exc.value)
    assert "şema" in mesaj.lower()
    for eksik in ("dirty", "unpushed", "last_commit_at", "has_remote"):
        assert eksik in mesaj, f"eksik sütun adı belirtilmeli: {eksik}"


def test_atlas_dosyasi_yoksa_hata(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        tut.atlas_oku(tmp_path / "yok.db")


def test_eski_atlas_verisi_uyarisi(tmp_path: Path) -> None:
    """`scanned_at` 24 saatten eskiyse çıktının başında uyarı."""
    db = atlas_kur(tmp_path / "a.db", [repo(name="atlas")])
    from datetime import datetime as _dt, timezone as _tz
    veri = tut.atlas_oku(db)
    referans = _dt(2026, 3, 10, 12, 0, tzinfo=_tz.utc)
    assert not tut.atlas_eski_mi(veri, simdi=referans), "taze tarama 'eski' sayılmamalı"

    eski = _iso(3)   # 3 gün önce
    db2 = atlas_kur(tmp_path / "b.db", [repo(name="atlas", scanned_at=eski)])
    veri2 = tut.atlas_oku(db2)
    assert tut.atlas_eski_mi(veri2, simdi=referans), "3 günlük tarama 'eski' olmalı"

    vault = tmp_path / "v"
    vault.mkdir()
    yaz(vault, "P.md", "---\nrepo: atlas\nstatus: aktif\n---\n# P\n")
    rapor = tut.bulgular_uret(vault, veri2, esik_gun=30, bugun=BUGUN)
    assert rapor.atlas_uyari is not None
    assert "eski" in rapor.atlas_uyari


# ---------------------------------------------------------------------------
# Kural 1: "planlandı" ama repoda kod var
# ---------------------------------------------------------------------------


def test_kural1_planli_ama_kod_var_uyari(tmp_path: Path) -> None:
    vault = tmp_path / "v"
    vault.mkdir()
    yaz(vault, "P.md", f"""---
repo: atlas
status: planlandı
---
# P

{_iso(2)} tarihinde kod yazıldı.
""")
    db = atlas_kur(tmp_path / "a.db", [repo(name="atlas", last_commit_at=_iso(2))])
    rapor = tut.bulgular_uret(vault, tut.atlas_oku(db), esik_gun=30, bugun=BUGUN)
    uyarilar = [b for b in rapor.uyarilar if b.kural == "planli-ama-kod-var"]
    assert len(uyarilar) == 1, uyarilar
    assert "atlas" in uyarilar[0].baslik
    assert uyarilar[0].onem == "uyari"


def test_kural1_negatif_kod_yok(tmp_path: Path) -> None:
    """Commit yoksa uyarı ÜRETİLMEZ."""
    vault = tmp_path / "v"
    vault.mkdir()
    yaz(vault, "P.md", "---\nrepo: atlas\nstatus: planlandı\n---\n# P\n")
    db = atlas_kur(tmp_path / "a.db", [repo(name="atlas", last_commit_at=None)])
    rapor = tut.bulgular_uret(vault, tut.atlas_oku(db), esik_gun=30, bugun=BUGUN)
    assert not [b for b in rapor.uyarilar if b.kural == "planli-ama-kod-var"]


def test_kural1_negatif_commit_eski(tmp_path: Path) -> None:
    """Son commit eşik günden eskiyse uyarı yok (kural 3 devreye girer)."""
    vault = tmp_path / "v"
    vault.mkdir()
    yaz(vault, "P.md", "---\nrepo: atlas\nstatus: planlandı\n---\n# P\n")
    db = atlas_kur(tmp_path / "a.db", [repo(name="atlas", last_commit_at=_iso(60))])
    rapor = tut.bulgular_uret(vault, tut.atlas_oku(db), esik_gun=30, bugun=BUGUN)
    assert not [b for b in rapor.uyarilar if b.kural == "planli-ama-kod-var"]


# ---------------------------------------------------------------------------
# Kural 2: "bitti" ama dirty / pushlanmamış
# ---------------------------------------------------------------------------


def test_kural2_bitti_ama_dirty_uyari(tmp_path: Path) -> None:
    vault = tmp_path / "v"
    vault.mkdir()
    yaz(vault, "P.md", "---\nrepo: atlas\nstatus: bitti\n---\n# P\n")
    db = atlas_kur(tmp_path / "a.db", [repo(name="atlas", dirty=3)])
    rapor = tut.bulgular_uret(vault, tut.atlas_oku(db), esik_gun=30, bugun=BUGUN)
    uyarilar = [b for b in rapor.uyarilar if b.kural == "bitti-ama-dirty"]
    assert len(uyarilar) == 1
    assert "3" in uyarilar[0].gerekce


def test_kural2_bitti_ama_pushlanmamis_uyari(tmp_path: Path) -> None:
    vault = tmp_path / "v"
    vault.mkdir()
    yaz(vault, "P.md", "---\nrepo: atlas\nstatus: bitti\n---\n# P\n")
    db = atlas_kur(tmp_path / "a.db", [repo(name="atlas", unpushed=2)])
    rapor = tut.bulgular_uret(vault, tut.atlas_oku(db), esik_gun=30, bugun=BUGUN)
    assert [b for b in rapor.uyarilar if b.kural == "bitti-ama-dirty"]


def test_kural2_negatif_temiz(tmp_path: Path) -> None:
    vault = tmp_path / "v"
    vault.mkdir()
    yaz(vault, "P.md", "---\nrepo: atlas\nstatus: bitti\n---\n# P\n")
    db = atlas_kur(tmp_path / "a.db", [repo(name="atlas", dirty=0, unpushed=0)])
    rapor = tut.bulgular_uret(vault, tut.atlas_oku(db), esik_gun=30, bugun=BUGUN)
    assert not [b for b in rapor.uyarilar if b.kural == "bitti-ama-dirty"]


def test_kural2_unpushed_null_da_pushlanmamis_demez(tmp_path: Path) -> None:
    """`unpushed` NULL = bilinmiyor; "pushlanmamış" iddiası ASLA yapılmaz."""
    vault = tmp_path / "v"
    vault.mkdir()
    yaz(vault, "P.md", "---\nrepo: atlas\nstatus: bitti\n---\n# P\n")
    db = atlas_kur(tmp_path / "a.db", [repo(name="atlas", dirty=0, unpushed=None)])
    rapor = tut.bulgular_uret(vault, tut.atlas_oku(db), esik_gun=30, bugun=BUGUN)
    # dirty de 0 olduğu için uyarı OLMAMALI.
    assert not [b for b in rapor.uyarilar if b.kural == "bitti-ama-dirty"]
    # Gerekçelerin hiçbirinde "pushlanmamış" geçmemeli.
    tum = " ".join(b.gerekce for b in rapor.tumu)
    assert "pushlanmamış" not in tum


# ---------------------------------------------------------------------------
# Kural 3: "aktif" ama durgun
# ---------------------------------------------------------------------------


def test_kural3_aktif_ama_durgun_bilgi(tmp_path: Path) -> None:
    vault = tmp_path / "v"
    vault.mkdir()
    yaz(vault, "P.md", "---\nrepo: atlas\nstatus: aktif\n---\n# P\n")
    db = atlas_kur(tmp_path / "a.db", [repo(name="atlas", last_commit_at=_iso(60))])
    rapor = tut.bulgular_uret(vault, tut.atlas_oku(db), esik_gun=30, bugun=BUGUN)
    bilgiler = [b for b in rapor.bilgiler if b.kural == "aktif-ama-durgun"]
    assert len(bilgiler) == 1
    assert bilgiler[0].onem == "bilgi"


def test_kural3_negatif_taze_commit(tmp_path: Path) -> None:
    vault = tmp_path / "v"
    vault.mkdir()
    yaz(vault, "P.md", "---\nrepo: atlas\nstatus: aktif\n---\n# P\n")
    db = atlas_kur(tmp_path / "a.db", [repo(name="atlas", last_commit_at=_iso(3))])
    rapor = tut.bulgular_uret(vault, tut.atlas_oku(db), esik_gun=30, bugun=BUGUN)
    assert not [b for b in rapor.bilgiler if b.kural == "aktif-ama-durgun"]


# ---------------------------------------------------------------------------
# Kural 4: vault'ta karşılığı olmayan aktif repo
# ---------------------------------------------------------------------------


def test_kural4_aktif_repo_vaultsuz_bilgi(tmp_path: Path) -> None:
    vault = tmp_path / "v"
    vault.mkdir()
    yaz(vault, "P.md", "---\nrepo: atlas\nstatus: aktif\n---\n# P\n")
    db = atlas_kur(tmp_path / "a.db", [
        repo(name="atlas", last_commit_at=_iso(2)),
        repo(name="gizli-repo", last_commit_at=_iso(3)),
    ])
    rapor = tut.bulgular_uret(vault, tut.atlas_oku(db), esik_gun=30, bugun=BUGUN)
    bilgiler = [b for b in rapor.bilgiler if b.kural == "vaultsuz-aktif-repo"]
    assert len(bilgiler) == 1
    assert "gizli-repo" in bilgiler[0].baslik
    assert "atlas" not in " ".join(b.baslik for b in bilgiler)


def test_kural4_negatif_durusuz_repo(tmp_path: Path) -> None:
    """7 günden eski commit'li repo "aktif" sayılmaz."""
    vault = tmp_path / "v"
    vault.mkdir()
    yaz(vault, "P.md", "---\nrepo: atlas\nstatus: aktif\n---\n# P\n")
    db = atlas_kur(tmp_path / "a.db", [
        repo(name="atlas", last_commit_at=_iso(2)),
        repo(name="eski-repo", last_commit_at=_iso(30)),
    ])
    rapor = tut.bulgular_uret(vault, tut.atlas_oku(db), esik_gun=30, bugun=BUGUN)
    assert not [b for b in rapor.bilgiler if "eski-repo" in b.baslik]


# ---------------------------------------------------------------------------
# Kural 5: Threads'ta açık konu, durgun repo
# ---------------------------------------------------------------------------


def test_kural5_Threads_acik_konu_durgun_repo(tc_vault: Path, tmp_path: Path) -> None:
    db = atlas_kur(tmp_path / "a.db", [
        repo(name="orkestra", last_commit_at=_iso(2)),
        repo(name="qwen-lab", last_commit_at=_iso(60)),
    ])
    rapor = tut.bulgular_uret(tc_vault, tut.atlas_oku(db), esik_gun=30, bugun=BUGUN)
    bilgiler = [b for b in rapor.bilgiler if b.kural == "konu-aktif-ama-repo-durgun"]
    assert len(bilgiler) == 1
    assert "qwen-lab" in bilgiler[0].baslik


def test_kural5_negatif_kapanmis_isaret(tc_vault: Path, tmp_path: Path) -> None:
    """İşaretsiz (kapalı) konu için bulgu yok."""
    db = atlas_kur(tmp_path / "a.db", [
        repo(name="orkestra", last_commit_at=_iso(2)),
        repo(name="qwen-lab", last_commit_at=_iso(2)),
        repo(name="atlas", last_commit_at=_iso(60)),
    ])
    rapor = tut.bulgular_uret(tc_vault, tut.atlas_oku(db), esik_gun=30, bugun=BUGUN)
    assert not [b for b in rapor.bilgiler if b.kural == "konu-aktif-ama-repo-durgun"]


# ---------------------------------------------------------------------------
# Eşleme
# ---------------------------------------------------------------------------


def test_esleme_frontmatter_yuksek_guven(tmp_path: Path) -> None:
    vault = tmp_path / "v"
    vault.mkdir()
    yaz(vault, "P.md", "---\nrepo: atlas\nstatus: aktif\n---\n# P\n")
    db = atlas_kur(tmp_path / "a.db", [repo(name="atlas")])
    atlas = tut.atlas_oku(db)
    not_ = tut._notlari_tara(vault)[0]
    r, yontem, tahmin = tut.eslestir(not_, atlas, {})
    assert r is not None and r.name == "atlas"
    assert yontem == "frontmatter" and tahmin is False


def test_esleme_dosyasi_yuksek_guven(tmp_path: Path) -> None:
    vault = tmp_path / "v"
    vault.mkdir()
    yaz(vault, "🏰 300-Projects/Atlas.md", "# Atlas\n")
    eslesme_yolu = tmp_path / "e.toml"
    eslesme_yolu.write_text(
        '[eslesme]\n"🏰 300-Projects/Atlas.md" = "atlas"\n', encoding="utf-8"
    )
    db = atlas_kur(tmp_path / "a.db", [repo(name="atlas")])
    atlas = tut.atlas_oku(db)
    eslesme = tut.eslesme_dosyasi_oku(eslesme_yolu)
    not_ = next(n for n in tut._notlari_tara(vault) if "Atlas" in n.yol)
    r, yontem, tahmin = tut.eslestir(not_, atlas, eslesme)
    assert r is not None and r.name == "atlas"
    assert yontem == "esleme dosyasi" and tahmin is False


def test_esleme_backtick_orta_guven_tahmin(tmp_path: Path) -> None:
    vault = tmp_path / "v"
    vault.mkdir()
    yaz(vault, "P.md", "# P\n\nProjeye bak: `atlas` deposu.\n")
    db = atlas_kur(tmp_path / "a.db", [repo(name="atlas")])
    atlas = tut.atlas_oku(db)
    not_ = tut._notlari_tara(vault)[0]
    r, yontem, tahmin = tut.eslestir(not_, atlas, {})
    assert r is not None and r.name == "atlas"
    assert yontem == "backtick" and tahmin is True


def test_esleme_oncelik_frontmatter_dosyadan_once(tmp_path: Path) -> None:
    """frontmatter, eşleme dosyasından ÖNCE gelir."""
    vault = tmp_path / "v"
    vault.mkdir()
    yaz(vault, "P.md", "---\nrepo: atlas\nstatus: aktif\n---\n# P\n`orkestra` da var.\n")
    eslesme = {"P.md": "orkestra"}
    db = atlas_kur(tmp_path / "a.db", [repo(name="atlas"), repo(name="orkestra")])
    atlas = tut.atlas_oku(db)
    not_ = tut._notlari_tara(vault)[0]
    r, yontem, _ = tut.eslestir(not_, atlas, eslesme)
    assert r.name == "atlas", "frontmatter kazanmalı"
    assert yontem == "frontmatter"


def test_esleme_bilinmeyen_backtick_eslesmez(tmp_path: Path) -> None:
    """Backtick'te geçen ama atlas'ta OLMAYAN ad eşleşme sayılmaz."""
    vault = tmp_path / "v"
    vault.mkdir()
    yaz(vault, "P.md", "# P\n\n`bilinmeyen-repo` ve `atlas`.\n")
    db = atlas_kur(tmp_path / "a.db", [repo(name="atlas")])
    atlas = tut.atlas_oku(db)
    not_ = tut._notlari_tara(vault)[0]
    r, _, _ = tut.eslestir(not_, atlas, {})
    assert r is not None and r.name == "atlas", "bilinen repo'ya eşleşmeli"


def test_eslesmeyen_not_bulgu_uretmez(tc_vault: Path, tmp_path: Path) -> None:
    db = atlas_kur(tmp_path / "a.db", [repo(name="atlas", last_commit_at=_iso(2))])
    rapor = tut.bulgular_uret(tc_vault, tut.atlas_oku(db), esik_gun=30, bugun=BUGUN)
    tum_baslik = " ".join(b.baslik for b in rapor.tumu)
    assert "Serbest" not in tum_baslik, "eşleşmeyen not bulgu ÜRETMEMELİ"
    assert rapor.eslesmeyenler >= 1


def test_klonsuz_repo_kontrol_edilemeyen_listesine(tmp_path: Path) -> None:
    """Not eşleşip repo atlas'ta yoksa → bulgu değil, kontrol edilemeyen."""
    vault = tmp_path / "v"
    vault.mkdir()
    yaz(vault, "P.md", "---\nrepo: atlas\nstatus: aktif\n---\n# P\n")
    # atlas DB'de atlas YOK, başka bir repo var.
    db = atlas_kur(tmp_path / "a.db", [repo(name="baskasi", last_commit_at=_iso(1))])
    rapor = tut.bulgular_uret(vault, tut.atlas_oku(db), esik_gun=30, bugun=BUGUN)
    # "atlas" eşleşmediği için bulgu yok.
    assert not [b for b in rapor.tumu if b.baslik == "atlas"]
    # Ama "baskasi" aktif ve vaultsuz → bilgi üretilir.
    assert [b for b in rapor.bilgiler if b.kural == "vaultsuz-aktif-repo"]


# ---------------------------------------------------------------------------
# Sözlük / çıktı biçimi
# ---------------------------------------------------------------------------


def test_rapor_sozluk_yapisi(tc_vault: Path, tmp_path: Path) -> None:
    db = atlas_kur(tmp_path / "a.db", [
        repo(name="atlas", last_commit_at=_iso(2)),
        repo(name="orkestra", dirty=5, last_commit_at=_iso(2)),
    ])
    rapor = tut.bulgular_uret(tc_vault, tut.atlas_oku(db), esik_gun=30, bugun=BUGUN)
    s = rapor.sozluk()
    # Dalga D: "Kontrol edilenler" bölümü JSON'a da eklendi ("0 uyarı"
    # sıfır çiftten mi yoksa sıfır bulgudan mı geliyor, ayırt edilebilsin).
    assert set(s) == {
        "uyarilar", "bilgiler", "kontrol_edilemeyenler", "atlas_uyari", "kontrol_edilenler"
    }
    for b in s["uyarilar"] + s["bilgiler"]:
        assert set(b) == {"onem", "guven", "kural", "baslik", "gerekce", "oneri"}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _calistir(argv: list[str]) -> tuple[int, str]:
    import io
    from contextlib import redirect_stderr, redirect_stdout

    cikti, hata = io.StringIO(), io.StringIO()
    with redirect_stdout(cikti), redirect_stderr(hata):
        kod = cli_main(argv)
    return kod, cikti.getvalue() + hata.getvalue()


def test_cli_json_cikti(tc_vault: Path, tmp_path: Path) -> None:
    db = atlas_kur(tmp_path / "a.db", [
        repo(name="atlas", last_commit_at=_iso(2)),
        repo(name="orkestra", dirty=5, last_commit_at=_iso(2)),
    ])
    kod, metin = _calistir([
        "tutarlilik", str(tc_vault), "--atlas-db", str(db), "--json",
        "--bugun", "2026-03-10",
    ])
    assert kod == 0
    veri = json.loads(metin)
    assert "uyarilar" in veri and "bilgiler" in veri
    assert isinstance(veri["uyarilar"], list)


def test_cli_kati_uyari_varken_kod_1(tc_vault: Path, tmp_path: Path) -> None:
    db = atlas_kur(tmp_path / "a.db", [repo(name="orkestra", dirty=5, last_commit_at=_iso(2))])
    kod, _ = _calistir([
        "tutarlilik", str(tc_vault), "--atlas-db", str(db), "--kati",
        "--bugun", "2026-03-10",
    ])
    assert kod == 1, "uyarı varken --kati çıkış kodu 1 vermeli"


def test_cli_kati_bugun_durumlu_uyari_kodu_1(tc_vault: Path, tmp_path: Path) -> None:
    """`--bugun` gerçekten dikkate alınınca uyarı görünür ve kod 1 olur.

    `tc_vault`'ta `Atlas.md` "planlandı" diyor; atlas'taki `atlas` reposunda
    2 gün önce commit VAR → kural 1 ("planlı-ama-kod-var") gerçekten bir
    uyarı üretir. Bu yüzden 0 kodu bekleyen eski test, `--bugun`'ın
    `bulgular_uret`'e İLETİLMEDİĞI bir kusurla yeşil kalıyordu: bayrak
    ayrıştırılıyor ama yok sayılıyordu ve karşılaştırma gerçek "bugün"
    (2026-09-30) ile yapılıyordu, eski commit 30 gün eşiğini geçtiği için
    uyarı yanlışlıkla düşüyordu. `--bugun` düzeltilince uyarı geri gelir.
    """
    db = atlas_kur(tmp_path / "a.db", [repo(name="atlas", last_commit_at=_iso(2))])
    kod, _ = _calistir([
        "tutarlilik", str(tc_vault), "--atlas-db", str(db), "--kati",
        "--bugun", "2026-03-10",
    ])
    assert kod == 1, "planlı not + repoda commit varsa uyarı beklenir"


def test_cli_kati_uyari_yokken_kod_0(tmp_path: Path) -> None:
    """Uyarı YOKSA `--kati` çıkış kodu 0 vermeli.

    Kurgusal vault'ta HİÇBİR notta durum sözcüğü yoktur: hiçbir not
    hiçbir kuralın adayı olmaz, dolayısıyla uyarı da üretilemez.
    Bu, gerçekten "ölçtük ve sıfır" olan tek durumdur -- bayatlık
    yanlış referans günü yüzünden "sıfır" görünen durum DEĞİLDİR.
    """
    vault = tmp_path / "sessiz-vault"
    vault.mkdir()
    yaz(vault, "not.md", "# Not\n\nDurum sözcüğü yok, yalnızca metin.\n")
    db = atlas_kur(tmp_path / "a.db", [repo(name="atlas", last_commit_at=_iso(2))])
    kod, _ = _calistir([
        "tutarlilik", str(vault), "--atlas-db", str(db), "--kati",
        "--bugun", "2026-03-10",
    ])
    assert kod == 0, "hiçbir kural tetiklenmiyorsa uyarı da olmaz"


def test_cli_esleme_dosyasi_kullanilir(tmp_path: Path) -> None:
    vault = tmp_path / "v"
    vault.mkdir()
    yaz(vault, "🏰 300-Projects/Orkestra.md", "---\nstatus: bitti\n---\n# O\n")
    eslesme = tmp_path / "e.toml"
    eslesme.write_text(
        '[eslesme]\n"🏰 300-Projects/Orkestra.md" = "orkestra"\n', encoding="utf-8"
    )
    db = atlas_kur(tmp_path / "a.db", [repo(name="orkestra", dirty=2, last_commit_at=_iso(1))])
    kod, metin = _calistir([
        "tutarlilik", str(vault), "--atlas-db", str(db), "--esleme", str(eslesme),
        "--kati", "--bugun", "2026-03-10",
    ])
    assert kod == 1
    assert "orkestra" in metin


def test_cli_sema_uyusmazligi_kod_2(tmp_path: Path) -> None:
    vault = tmp_path / "v"
    vault.mkdir()
    bozuk = tmp_path / "b.db"
    baglanti = sqlite3.connect(bozuk)
    baglanti.executescript("CREATE TABLE repos (path TEXT, name TEXT);")
    baglanti.commit()
    baglanti.close()
    kod, metin = _calistir([
        "tutarlilik", str(vault), "--atlas-db", str(bozuk), "--bugun", "2026-03-10",
    ])
    assert kod == 2
    assert "şema" in metin.lower()


def test_tutarlilik_vaultu_degistirmez(tc_vault: Path, tmp_path: Path) -> None:
    from conftest import vault_hashleri

    once = vault_hashleri(tc_vault)
    db = atlas_kur(tmp_path / "a.db", [
        repo(name="atlas", last_commit_at=_iso(2)),
        repo(name="orkestra", dirty=5, last_commit_at=_iso(2)),
    ])
    tut.bulgular_uret(tc_vault, tut.atlas_oku(db), esik_gun=30, bugun=BUGUN)
    assert vault_hashleri(tc_vault) == once, "tutarlılık vault'u DEĞİŞTİRDİ"


def test_esleme_dosyasi_yorumlari_ayiklanir(tmp_path: Path) -> None:
    yol = tmp_path / "e.toml"
    yol.write_text(
        "# yorum satırı\n"
        "[eslesme]\n"
        '"A.md" = "atlas"   # satır sonu yorumu\n'
        "[diger]\n"
        '"B.md" = "x"\n',
        encoding="utf-8",
    )
    sozluk = tut.eslesme_dosyasi_oku(yol)
    assert sozluk == {"A.md": "atlas"}, sozluk


# ---------------------------------------------------------------------------
# Yanlış pozitif korumaları (gerçek vault'ta bulundu, testle sabitlendi)
# ---------------------------------------------------------------------------


def test_kural4_vault_kendisi_bildirilmez(tmp_path: Path) -> None:
    """Vault'un KENDİ git deposu bir proje DEĞİLDİR.

    Gerçek vault'ta atlas, kök dizini taradığı için vault'u da kendi adıyla
    kaydediyordu; "bu repo için not aç" önermesi anlamsızdı.
    """
    vault = tmp_path / "kurgusal-vault"
    vault.mkdir()
    yaz(vault, "P.md", "---\nrepo: atlas\nstatus: aktif\n---\n# P\n")
    db = atlas_kur(tmp_path / "a.db", [
        repo(name="atlas", path="/home/user/atlas", last_commit_at=_iso(1)),
        repo(name="kurgusal-vault", path="/tmp/kurgusal-vault", last_commit_at=_iso(1)),
    ])
    rapor = tut.bulgular_uret(vault, tut.atlas_oku(db), esik_gun=30, bugun=BUGUN)
    adlar = [b.baslik for b in rapor.bilgiler if b.kural == "vaultsuz-aktif-repo"]
    assert "kurgusal-vault" not in adlar, "vault'un kendisi bildirilmemeli"


def test_kural4_remote_suz_repo_bildirilmez(tmp_path: Path) -> None:
    """`has_remote` olmayan repo paylaşılan/proje deposu sayılmaz."""
    vault = tmp_path / "v"
    vault.mkdir()
    yaz(vault, "P.md", "---\nrepo: atlas\nstatus: aktif\n---\n# P\n")
    db = atlas_kur(tmp_path / "a.db", [
        repo(name="atlas", last_commit_at=_iso(1)),
        repo(name="yerel-kopya", last_commit_at=_iso(1), has_remote=0),
    ])
    rapor = tut.bulgular_uret(vault, tut.atlas_oku(db), esik_gun=30, bugun=BUGUN)
    adlar = [b.baslik for b in rapor.bilgiler if b.kural == "vaultsuz-aktif-repo"]
    assert "yerel-kopya" not in adlar


def test_kural4_vaultta_adi_gecen_repo_bildirilmez(tmp_path: Path) -> None:
    """Repo vault'ta bir yerde ANILIYORSA karşılığı vardır.

    Gerçek vault'ta `anlat`, `obsstack` vb. yalnız günlük/Last-Session
    içinde geçiyordu; eşleme kuralları bunları yakalamadığı için 9 adet
    yanlış pozitif üretiliyordu.
    """
    vault = tmp_path / "v"
    vault.mkdir()
    yaz(vault, "P.md", "---\nrepo: atlas\nstatus: aktif\n---\n# P\n")
    yaz(vault, "daily/2026-09-30.md", "# Günlük\n\nBugün `anlat` reposunda çalışıldı.\n")
    db = atlas_kur(tmp_path / "a.db", [
        repo(name="atlas", last_commit_at=_iso(1)),
        repo(name="anlat", last_commit_at=_iso(1)),
    ])
    rapor = tut.bulgular_uret(vault, tut.atlas_oku(db), esik_gun=30, bugun=BUGUN)
    adlar = [b.baslik for b in rapor.bilgiler if b.kural == "vaultsuz-aktif-repo"]
    assert "anlat" not in adlar, "vault'ta anılan repo bildirilmemeli"


def test_kural4_hicbir_yerde_gecmeyen_repo_bildirilir(tmp_path: Path) -> None:
    """Yinelenen koruma: gerçekten hiç geçmeyen repo HÂLÂ bildirilir."""
    vault = tmp_path / "v"
    vault.mkdir()
    yaz(vault, "P.md", "---\nrepo: atlas\nstatus: aktif\n---\n# P\n")
    db = atlas_kur(tmp_path / "a.db", [
        repo(name="atlas", last_commit_at=_iso(1)),
        repo(name="yepyeni-repo", last_commit_at=_iso(1)),
    ])
    rapor = tut.bulgular_uret(vault, tut.atlas_oku(db), esik_gun=30, bugun=BUGUN)
    adlar = [b.baslik for b in rapor.bilgiler if b.kural == "vaultsuz-aktif-repo"]
    assert "yepyeni-repo" in adlar, "hiç geçmeyen gerçek repo bildirilmeli"


def test_tireli_durum_sozcugu_taninir() -> None:
    """Gerçek vault `status: in-progress` kullanıyor (tireli biçim)."""
    assert tut.durum_grup("in-progress") == "aktif"
    assert tut.durum_grup("in progress") == "aktif"
    assert tut.durum_grup("yapım aşamasında") == "aktif"


def test_in_progress_durumu_aktif_olarak_islenir(tmp_path: Path) -> None:
    vault = tmp_path / "v"
    vault.mkdir()
    yaz(vault, "P.md", """---
repo: atlas
status: in-progress
---
# P
""")
    db = atlas_kur(tmp_path / "a.db", [repo(name="atlas", last_commit_at=_iso(90))])
    rapor = tut.bulgular_uret(vault, tut.atlas_oku(db), esik_gun=30, bugun=BUGUN)
    assert [b for b in rapor.bilgiler if b.kural == "aktif-ama-durgun"], \
        "`in-progress` aktif sayılmalı, durgunluk bilgisi üretilmeli"
