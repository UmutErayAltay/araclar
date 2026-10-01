"""`orkestra durum --json` sözleşme testleri (kule entegrasyonu, v1).

Kapsananlar:
  * ŞEKİL: tüm anahtar/tip denetimi, `surum == 1`, `kaynak == "orkestra"`,
    `gorev_durum` her `models.Durum` değerini içerir.
  * Kenar durumlar: boş DB, DB yok (`db_yok`), eski şema (`sema_eski`),
    kota verisi yok (`"kota": null`).
  * GİZLİLİK: içinde tanınabilir sahte "gizli" dize olan görev metni ve rapor
    fixture'ı → çıktıda ARANMADIĞI doğrulanır.
  * SAYIMLAR: `onay_bekleyen` / `basarisiz` / `kanitsiz_ya_da_supheli`
    fixture ile doğru.
  * CLI: gerçek alt süreçte çıkış kodları 0/1 ve stdout'ta TEK JSON satırı.

Tüm içerik KURGUSALDIR. Gizli kalıplar testin KENDİ sahte dizeleridir
(`sk-` + rakam içeren kurgusal anahtar, `AKIA...`, `api_key=...`); gerçek
anahtar/hesap YOKTUR ve hiçbir yere yazılmaz.

Ağa çıkmaz, cor çağırmaz, görev çalıştırmaz; `durum` yalnızca okur.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
import os
import sqlite3
import sys
from pathlib import Path

import pytest

from orkestra import durum
from orkestra.models import Durum
from orkestra.queue import SEMA_SURUM, Queue

REPO = Path(__file__).resolve().parent.parent

# Kurgusal sahte "gizli" dizeler (gerçek sır DEĞİL).
GIZLI_ANAHTAR = "sk-0kurgusal9bu8tamamenuydurma8anahtar"
GIZLI_AWS = "AKIA0KURGUSAL1234567"
GIZLI_ESLESME = "api_key=0kurgusal8deger"

# Sözleşmedeki TAM anahtar kümesi (eksik/ fazla alan olmamalı).
BEKLENEN_ANAHTARLAR = {
    "surum",
    "kaynak",
    "gorev_toplam",
    "gorev_durum",
    "onay_bekleyen",
    "basarisiz",
    "kanitsiz_ya_da_supheli",
    "kota",
}
KOTA_ANAHTARLARI = {"gun", "toplam_istek", "uyari_sayisi", "veri_var"}


# -- yardımcılar -------------------------------------------------------------


def calistir(*argv, db=None, timeout=60):
    """`python3 -m orkestra ...` komutunu GERÇEK alt süreçte koşturur."""
    cevre = dict(os.environ)
    cevre.pop("ORKESTRA_DB", None)
    cevre["PYTHONIOENCODING"] = "utf-8"
    cevre["PYTHONPATH"] = str(REPO)
    if db is not None:
        cevre["ORKESTRA_DB"] = str(db)
    import subprocess

    return subprocess.run(
        [sys.executable, "-m", "orkestra", *argv],
        cwd=str(REPO),
        env=cevre,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
    )


def _kosu_ekle(db_path, gorev_id: int, sinif: str | None) -> None:
    """Kanıt sınıfı belli bir koşu satırı yazar (doğrudan DB, worker YOK)."""
    b = sqlite3.connect(str(db_path))
    b.execute(
        "INSERT INTO runs (task_id, baslangic, bitis, cikis_kodu, kanit_durumu, "
        "kanit_ozeti) VALUES (?, '2026-09-30T06:00:00Z', '2026-09-30T06:05:00Z', 0, ?, '{}')",
        (gorev_id, sinif),
    )
    b.commit()
    b.close()


def _gorevler_ekle(q, adet: int) -> list[int]:
    """Kurgusal, temiz görevler ekler."""
    return [q.ekle("bunny-coder", f"kurgusal gorev {i}").id for i in range(1, adet + 1)]


# -- şekil / sözleşme --------------------------------------------------------


def test_sema_tum_anahtarlar_ve_tipler(db_yolu):
    """Başarılı çıktı tam olarak sözleşme şeklindedir."""
    q = Queue(db_yolu)
    _gorevler_ekle(q, 3)
    q.kapat()

    veri = durum.durum_oku(db_yolu)
    assert set(veri) == BEKLENEN_ANAHTARLAR
    assert veri["surum"] == 1
    assert veri["kaynak"] == "orkestra"
    assert isinstance(veri["gorev_toplam"], int) and veri["gorev_toplam"] == 3
    for alan in ("gorev_toplam", "onay_bekleyen", "basarisiz", "kanitsiz_ya_da_supheli"):
        assert isinstance(veri[alan], int), alan
        assert veri[alan] >= 0, alan
    assert isinstance(veri["gorev_durum"], dict)
    for deger, adet in veri["gorev_durum"].items():
        assert isinstance(deger, str) and isinstance(adet, int) and adet >= 0
    assert set(veri["kota"]) == KOTA_ANAHTARLARI
    assert isinstance(veri["kota"]["toplam_istek"], int)
    assert isinstance(veri["kota"]["uyari_sayisi"], int)
    assert isinstance(veri["kota"]["veri_var"], bool)
    assert veri["kota"]["gun"] == veri["kota"]["gun"].strip()
    assert len(veri["kota"]["gun"]) == 10  # YYYY-MM-DD


def test_gorev_durum_her_durum_degerini_icerir(db_yolu):
    """`gorev_durum` anahtarları `models.Durum` DEĞERLERİDİR; 0 olsa da var."""
    q = Queue(db_yolu)
    _gorevler_ekle(q, 1)
    q.kapat()

    veri = durum.durum_oku(db_yolu)
    assert set(veri["gorev_durum"]) == {d.value for d in Durum}
    assert "onay-bekliyor" in veri["gorev_durum"]


def test_bos_db_sifirlar(db_yolu):
    """DB var ama boş: sayılar 0, çıkış kodu 0, hata YOK."""
    q = Queue(db_yolu)
    q.kapat()

    veri = durum.durum_oku(db_yolu)
    assert "hata" not in veri
    assert veri["gorev_toplam"] == 0
    assert veri["gorev_durum"] == {d.value: 0 for d in Durum}
    assert veri["onay_bekleyen"] == 0
    assert veri["basarisiz"] == 0
    assert veri["kanitsiz_ya_da_supheli"] == 0


def test_db_yok_sabit_kod(tmp_path):
    """DB dosyası yoksa `db_yok` (sabit kod, yol/istisna YOK)."""
    veri = durum.durum_oku(tmp_path / "hic-yok.db")
    assert veri == {"surum": 1, "kaynak": "orkestra", "hata": "db_yok"}


def test_eski_sema_sabit_kod(db_yolu):
    """`user_version` eskiyse `sema_eski` — yazma/migration TETİKLENMEZ."""
    q = Queue(db_yolu)
    _gorevler_ekle(q, 2)
    q.kapat()
    b = sqlite3.connect(str(db_yolu))
    b.execute(f"PRAGMA user_version={SEMA_SURUM - 1}")
    b.commit()
    b.close()

    veri = durum.durum_oku(db_yolu)
    assert veri["hata"] == "sema_eski"
    # Migration YAPILMADI: sürüm yerinde duruyor.
    b = sqlite3.connect(str(db_yolu))
    assert b.execute("PRAGMA user_version").fetchone()[0] == SEMA_SURUM - 1
    b.close()


def test_kanit_sutunu_olmayan_sema_eski(db_yolu):
    """`runs.kanit_durumu` yoksa (eskiden başka şema) `sema_eski`.

    `kanitsiz_ya_da_supheli` tahmin EDİLMEZ; sütun yoksa hata kodu döner.
    """
    q = Queue(db_yolu)
    _gorevler_ekle(q, 1)
    q.kapat()
    b = sqlite3.connect(str(db_yolu))
    b.execute("ALTER TABLE runs DROP COLUMN kanit_durumu")
    b.commit()
    b.close()

    assert durum.durum_oku(db_yolu)["hata"] == "sema_eski"


def test_yabanci_db_sema_eski(tmp_path):
    """orkestra tablosu olmayan bir DB → `sema_eski`, çökmez."""
    yol = tmp_path / "yabanci.db"
    b = sqlite3.connect(str(yol))
    b.execute("CREATE TABLE baska (a INTEGER)")
    b.commit()
    b.close()

    assert durum.durum_oku(yol)["hata"] == "sema_eski"


def test_kota_verisi_yok_null(db_yolu):
    """`quota_snapshots` boşken `veri_var=False`; kota okunamazsa tam `null`."""
    q = Queue(db_yolu)
    _gorevler_ekle(q, 1)
    q.kapat()

    veri = durum.durum_oku(db_yolu)
    assert veri["kota"] is not None
    assert veri["kota"]["veri_var"] is False
    assert veri["kota"]["toplam_istek"] == 0

    # Kota tablosu YOKSA (okunamayan bölüm) → `kota: null`, komut yine 0 döner.
    b = sqlite3.connect(str(db_yolu))
    b.execute("DROP TABLE quota_snapshots")
    b.commit()
    b.close()
    veri = durum.durum_oku(db_yolu)
    assert veri["kota"] is None
    assert "hata" not in veri


def test_kota_sayilari(db_yolu):
    """Kota özeti mevcut `quota.kota_gorunumu` ile AYNI sayıları verir."""
    bugun = datetime.now(timezone.utc).date().isoformat()  # kota "bugünü" sayar; sabit tarih gün değişince kırılır
    q = Queue(db_yolu)
    q.baglanti_al().execute(
        "INSERT INTO quota_snapshots (model, gun, istek, maliyet) "
        f"VALUES ('ornek/model-a', '{bugun}', 40, 0)"
    )
    q.baglanti_al().execute(
        "INSERT INTO quota_snapshots (model, gun, istek, maliyet) "
        f"VALUES ('ornek/model-b', '{bugun}', 10, 0)"
    )  # ikinci model -> gün toplamı 50
    q.kapat()

    veri = durum.durum_oku(db_yolu)
    assert veri["kota"]["toplam_istek"] == 50
    assert veri["kota"]["veri_var"] is True


# -- gizlilik ---------------------------------------------------------------


def test_gizli_dize_aranmaz(db_yolu, tmp_path):
    """Görev metni/raporda tanınabilir sahte gizli dize → çıktıda YOK."""
    q = Queue(db_yolu)
    # `guard.istem_kontrol` bu kalıpları REDDEDER; bu yüzden fixture doğrudan
    # DB'ye yazılır (sızan yolun sınır testi).
    sizdirici = (
        f"gorev metni {GIZLI_ANAHTAR} ve {GIZLI_AWS} ve {GIZLI_ESLESME} "
        "/home/kurgusal/kullanici/gizli/rapor.md"
    )
    b = sqlite3.connect(str(db_yolu))
    b.execute(
        "INSERT INTO tasks (ajan, istem, durum, olusturma, rapor_dosyasi) "
        "VALUES ('bunny-coder', ?, 'bitti', '2026-09-30T06:00:00Z', 'rapor.md')",
        (sizdirici,),
    )
    b.commit()
    b.close()

    # Rapor dosyası da gizli dize içeriyor (fixture).
    rapor = tmp_path / "rapor.md"
    rapor.write_text(
        f"# Rapor\n\nanahtar: {GIZLI_ANAHTAR}\napi_key: {GIZLI_ESLESME}\n"
        "## Kanit\n- test: 3 passed\n- gorsel: ekran.png\n",
        encoding="utf-8",
    )

    veri = durum.durum_oku(db_yolu)
    ham = json.dumps(veri, ensure_ascii=False)
    for sizdirici_parca in (
        GIZLI_ANAHTAR,
        GIZLI_AWS,
        GIZLI_ESLESME,
        "sk-",
        "AKIA",
        "gizli",
        "kullanici",
        "rapor.md",
        "ekran.png",
        "gorev metni",
    ):
        assert sizdirici_parca not in ham, sizdirici_parca
    assert veri["gorev_toplam"] == 1


def test_db_dosya_yolu_sizmaz(db_yolu):
    """DB yolu/ajan adı çıktıya GİRMEZ."""
    q = Queue(db_yolu)
    q.ekle("bunny-coder", "temiz gorev")
    q.kapat()
    ham = json.dumps(durum.durum_oku(db_yolu), ensure_ascii=False)
    assert str(db_yolu) not in ham
    assert db_yolu.name not in ham
    assert "bunny" not in ham


# -- sayımlar ---------------------------------------------------------------


def test_onay_bekleyen_sayimi(db_yolu):
    q = Queue(db_yolu)
    ids = _gorevler_ekle(q, 4)
    q.gecis(ids[0], Durum.CALISIYOR)
    q.gecis(ids[0], Durum.ONAY_BEKLIYOR)
    q.gecis(ids[1], Durum.CALISIYOR)
    q.gecis(ids[1], Durum.ONAY_BEKLIYOR)
    q.kapat()

    veri = durum.durum_oku(db_yolu)
    assert veri["onay_bekleyen"] == 2
    assert veri["gorev_durum"]["onay-bekliyor"] == 2
    assert veri["gorev_durum"]["bekliyor"] == 2
    assert veri["gorev_toplam"] == 4


def test_basarisiz_ve_kanitsiz_sayimi(db_yolu):
    """`basarisiz` kendi alanında; `kanitsiz`+`reddedildi-suphesi` toplamda.

    Sinıf `runs.kanit_durumu`'ndan okunur (rapor sınıflandırmasının KENDİ
    saklanan sonucu) — burada yeni kural UYDURULMAZ.
    """
    q = Queue(db_yolu)
    ids = _gorevler_ekle(q, 5)
    q.kapat()
    _kosu_ekle(db_yolu, ids[0], "kanitli")
    _kosu_ekle(db_yolu, ids[1], "kanitsiz")
    _kosu_ekle(db_yolu, ids[2], "reddedildi-suphesi")
    _kosu_ekle(db_yolu, ids[3], "basarisiz")
    # 4. görev: koşu YOK → "degerlendirilmedi" (sınıf tahmin edilmez).

    veri = durum.durum_oku(db_yolu)
    assert veri["kanitsiz_ya_da_supheli"] == 2  # kanitsiz + reddedildi
    assert veri["basarisiz"] == 1
    assert veri["gorev_toplam"] == 5


def test_en_son_kosunun_sinifi_kullanilir(db_yolu):
    """Sınıf EN SON koşudan okunur (sözleşme: "en son koşunun sınıfı")."""
    q = Queue(db_yolu)
    gorev_id = _gorevler_ekle(q, 1)[0]
    q.kapat()
    _kosu_ekle(db_yolu, gorev_id, "kanitsiz")
    _kosu_ekle(db_yolu, gorev_id, "kanitli")
    assert durum.durum_oku(db_yolu)["kanitsiz_ya_da_supheli"] == 0

    q = Queue(db_yolu)
    gorev2 = q.ekle("bunny-coder", "ikinci gorev").id
    q.kapat()
    _kosu_ekle(db_yolu, gorev2, "kanitli")
    _kosu_ekle(db_yolu, gorev2, "kanitsiz")
    assert durum.durum_oku(db_yolu)["kanitsiz_ya_da_supheli"] == 1


def test_gercek_kosu_sinifi_kanitli_cikti(db_yolu):
    """Gerçek `queue` kanıt akışı üretir; `durum` onu OKUR, yeniden hesaplamaz.

    `calistir_bir` FakeRunner ile koşar (Dalga A deseni); bu test
    sınıflandırmanın `durum`'da doğru taşındığını gösterir.
    """
    from orkestra.models import RunSonuc

    class _Runner:
        cwd = None

        def calistir(self, gorev):
            return RunSonuc(cikis_kodu=0, kanit_yollari=[], hata=None)

    with Queue(db_yolu) as q:
        gorev = q.ekle("bunny-coder", "biraz uzun bir kurgusal gorev metni yazildi")
        g, kosu = q.calistir_bir(_Runner(), calisma_dizini=str(db_yolu.parent))
        assert kosu.kanit_durumu is not None
    veri = durum.durum_oku(db_yolu)
    # Görev metni iddia kalıbına takılır, gözlemlenen kanıt yok → "kanitsiz"
    assert veri["kanitsiz_ya_da_supheli"] == 1
    assert veri["kanitsiz_ya_da_supheli"] == (1 if kosu.kanit_durumu == "kanitsiz" else 0)


# -- salt-okunurluk ----------------------------------------------------------


def test_db_ye_yazmaz(db_yolu):
    """`durum` DB'ye yazmaz: ana dosya ve satır sayıları DEĞİŞMEZ.

    WAL kipinde salt-okunur bir bağlantı açmak `-shm`/`-wal` YAN dosyalarını
    oluşturabilir (SQLite'in kendi paylaşımlı bellek eşlemesi; `query_only`
    yazma yine de reddeder). Bu bir veri YAZIMI DEĞİLDİR ve mevcut web paneliyle
    birebir aynı davranıştır; test asıl gereksinimi ölçer: `.db` dosyasının
    KENDİSİ bayt bayt değişmez ve hiçbir satır/şema sürümü değişmez.
    """
    q = Queue(db_yolu)
    _gorevler_ekle(q, 3)
    q.kapat()
    icerik_once = db_yolu.read_bytes()
    satir_once = sqlite3.connect(str(db_yolu)).execute(
        "SELECT COUNT(*) FROM tasks"
    ).fetchone()[0]
    surum_once = sqlite3.connect(str(db_yolu)).execute(
        "PRAGMA user_version"
    ).fetchone()[0]

    durum.durum_oku(db_yolu)

    assert db_yolu.read_bytes() == icerik_once  # ana dosya DEĞİŞMEDİ
    b = sqlite3.connect(str(db_yolu))
    assert b.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == satir_once
    assert b.execute("PRAGMA user_version").fetchone()[0] == surum_once
    b.close()


# -- CLI --------------------------------------------------------------------


def test_cli_json_basari_ve_tek_satir(db_yolu):
    """Başarılı `durum --json`: çıkış 0, stdout TAMAMEN tek JSON satırı."""
    q = Queue(db_yolu)
    _gorevler_ekle(q, 2)
    q.kapat()

    cikti = calistir("durum", "--json", db=db_yolu)
    assert cikti.returncode == 0, cikti.stderr
    satirlar = [s for s in cikti.stdout.splitlines() if s.strip()]
    assert len(satirlar) == 1, cikti.stdout
    veri = json.loads(satirlar[0])
    assert veri["kaynak"] == "orkestra"
    assert veri["gorev_toplam"] == 2
    assert "hata" not in veri
    assert cikti.stderr == ""


def test_cli_json_db_yok_cikis_kodu_1(tmp_path):
    """DB yok: stdout YİNE de JSON, çıkış kodu 1."""
    cikti = calistir("durum", "--json", db=tmp_path / "yok.db")
    assert cikti.returncode == 1
    veri = json.loads(cikti.stdout.strip())
    assert veri == {"surum": 1, "kaynak": "orkestra", "hata": "db_yok"}
    # stderr'e de gizli/yol SIZMAZ.
    assert cikti.stderr == ""


def test_cli_json_eski_sema_cikis_kodu_1(db_yolu):
    q = Queue(db_yolu)
    _gorevler_ekle(q, 1)
    q.kapat()
    b = sqlite3.connect(str(db_yolu))
    b.execute("PRAGMA user_version=1")
    b.commit()
    b.close()

    cikti = calistir("durum", "--json", db=db_yolu)
    assert cikti.returncode == 1
    assert json.loads(cikti.stdout.strip())["hata"] == "sema_eski"


def test_cli_json_sayilar(db_yolu):
    q = Queue(db_yolu)
    ids = _gorevler_ekle(q, 3)
    q.gecis(ids[0], Durum.CALISIYOR)
    q.gecis(ids[0], Durum.ONAY_BEKLIYOR)
    q.kapat()
    _kosu_ekle(db_yolu, ids[1], "kanitsiz")

    veri = json.loads(calistir("durum", "--json", db=db_yolu).stdout)
    assert veri["onay_bekleyen"] == 1
    assert veri["kanitsiz_ya_da_supheli"] == 1
    assert veri["basarisiz"] == 0


def test_teknik_hata_sabit_kod(db_yolu, monkeypatch):
    """Beklenmedik teknik hata → `okunamadi`; yol/istisna metni SIZMAZ.

    Bu yüzden alt süreç DEĞİL, doğrudan `durum_oku` denenir (monkeypatch
    alt sürece taşınmaz).
    """
    q = Queue(db_yolu)
    _gorevler_ekle(q, 1)
    q.kapat()

    def _patla(yol):
        raise sqlite3.OperationalError("veritabani kilitli: /home/kurgusal/gizli.db")

    monkeypatch.setattr(durum, "db_ac", _patla)
    veri = durum.durum_oku(db_yolu)
    assert veri == {"surum": 1, "kaynak": "orkestra", "hata": "okunamadi"}

    # Sorgu SIRASINDA hata (bozuk dosya) → yine sabit kod.
    class _Bozuk:
        def execute(self, sql, *a, **k):
            raise sqlite3.DatabaseError("dizin bozuk: /home/kurgusal/gizli.db")

        def close(self):
            pass

    monkeypatch.setattr(durum, "db_ac", lambda yol: _Bozuk())
    assert durum.durum_oku(db_yolu)["hata"] == "okunamadi"


def test_cli_json_stderr_gizli_yok(db_yolu):
    q = Queue(db_yolu)
    _gorevler_ekle(q, 1)
    q.kapat()
    cikti = calistir("durum", "--json", db=db_yolu)
    assert GIZLI_ANAHTAR not in cikti.stdout + cikti.stderr
    assert str(db_yolu) not in cikti.stdout + cikti.stderr


def test_cli_json_ascii_tam(db_yolu):
    """Sözleşme 8: `ensure_ascii=True` → çıktı saf ASCII (Windows cp1252)."""
    q = Queue(db_yolu)
    _gorevler_ekle(q, 1)
    q.kapat()
    cikti = calistir("durum", "--json", db=db_yolu)
    assert cikti.stdout.isascii()


def test_cli_insan_ozeti(db_yolu):
    """`--json` verilmezse kısa insan-okur özet basılır (çıkış 0)."""
    q = Queue(db_yolu)
    _gorevler_ekle(q, 1)
    q.kapat()
    cikti = calistir("durum", db=db_yolu)
    assert cikti.returncode == 0, cikti.stderr
    assert "orkestra:" in cikti.stdout
    with pytest.raises(json.JSONDecodeError):
        json.loads(cikti.stdout.strip())


def test_cli_hedef_2_saniyen_altinda(db_yolu):
    """Sözleşme 6: tipik çalışma < 2 sn."""
    import time

    q = Queue(db_yolu)
    _gorevler_ekle(q, 20)
    q.kapat()
    bas = time.monotonic()
    cikti = calistir("durum", "--json", db=db_yolu, timeout=30)
    sure = time.monotonic() - bas
    assert cikti.returncode == 0
    assert sure < 2.0, f"{sure:.2f} sn"
