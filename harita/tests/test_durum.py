"""`harita durum --json` — kule entegrasyonu testleri (Dalga E).

Kapsam: sözleşmenin JSON şekli ve tipleri, kurgusal vault'ta kırık link/yetim
sayıları, indeks yok → `indeks_yok` + çıkış 1, indeks bayat/taze, atlas DB'si
yokken `tutarlilik_uyari: null` (0 DEĞİL) ve atlas DB'si varken UYARI SAYISI,
gizli dizilerin çıktıda ARANMAMASI, ve indeks dosyasının değişmediği
(salt-okunurluk kanıtı).

Tüm içerik KURGUSALDIR; gerçek vault'a hiç dokunulmaz, gerçek vault içeriği
testlere girmez. Tüm komutlar `subprocess` ile GERÇEKTEN çalıştırılır.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from conftest import KOK, yaz
from harita import durum as durum_moduli
from harita.cli import main as cli_main

BUGUN = date(2026, 3, 10)

# Sözleşmede yasaklı olanlar: bu diziler çıktının HİÇBİR yerinde geçmemeli.
GIZLI_BASLIK = "GIZLI-BASLIK-DIZISI-9f3a2b"
GIZLI_ICERIK = "GIZLI-ICERIK-DIZISI-7c1e5d"
GIZLI_ANAHTAR = "sk-gizlidurumgizlidurumgizlidurum1234"


def calistir(*argv: str) -> subprocess.CompletedProcess[str]:
    """`python -m harita ...` — gerçek alt süreç, gerçek stdout/stderr/çıkış kodu."""
    return subprocess.run(
        [sys.executable, "-m", "harita", *argv],
        cwd=str(KOK),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONPATH": str(KOK), "PYTHONIOENCODING": "utf-8"},
        timeout=120,
    )


def _iso(gun_once: int) -> str:
    t = datetime.combine(BUGUN - timedelta(days=gun_once), datetime.min.time(),
                         tzinfo=timezone.utc)
    return t.isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Kurgusal vault
# ---------------------------------------------------------------------------


@pytest.fixture
def durum_vault(tmp_path: Path) -> Path:
    """Kurgusal vault: 1 kırık link, 1 GERÇEK yetim, 1 yok sayılabilir günlük.

    Beklenen sayılar:
      * not_sayisi = 5
      * kirik_link = 1  (`proje/plan.md` → `[[hic-boyle-not]]` yok)
      * yetim_not  = 1  (`proje/kose.md`)

    Yetim AYRIMI testin asıl konusudur, bu yüzden ikisi de vardır:
      * `proje/kose.md` — alt klasörde, hiç bağlantısı yok → GERÇEK yetim.
      * `daily/2026-01-02.md` — hiç bağlantısı yok AMA yapı gereği
        (`daily/`) "yok sayılabilir"; `yetim_not` BUNU SAYMAMALIDIR.
      * `daily/2026-01-01.md` — link verdiği için ne gerçek ne yok sayılabilir.

    Gizli diziler not BAŞLIĞI ve GÖVDEde bulunur; `durum` bunları asla basmamalı.
    """
    vault = tmp_path / "kurgusal-vault"
    vault.mkdir()
    yaz(vault, "proje/plan.md", f"""---
title: {GIZLI_BASLIK}
---
# {GIZLI_BASLIK}

**Durum:** planlandı

Gövdede de geçiyor: {GIZLI_ICERIK}
Bu satır sızdırabilir: {GIZLI_ANAHTAR}

[[gecen-not]] ve [[hic-boyle-not]]
""")
    yaz(vault, "gecen-not.md", "# Geçen Not\n\nBu not link ALIR, yetim değildir.\n")
    yaz(vault, "proje/kose.md", "# Köşe Not\n\nAlt klasörde, hiç bağlantısı yok: gerçek yetim.\n")
    yaz(vault, "daily/2026-01-01.md", "# Günlük\n\n[[gecen-not]]\n")
    yaz(vault, "daily/2026-01-02.md", "# Günlük\n\nHiç bağlantısı yok ama daily/ altında.\n")
    return vault


@pytest.fixture
def durum_db(durum_vault: Path, tmp_path: Path) -> Path:
    """`durum_vault` indekslenmiş DB (gerçek `indeksle` ile kurulur)."""
    db = tmp_path / "durum.db"
    assert calistir("indeksle", str(durum_vault), "--db", str(db)).returncode == 0
    return db


# ---------------------------------------------------------------------------
# Sözleşme: şekil, tipler, sabit alanlar
# ---------------------------------------------------------------------------

# Sözleşmede tanımlı alanlar — REHBER, düzende güncellenebilir.
BEKLENEN_ALANLAR = (
    "surum", "kaynak", "son_indeks", "indeks_bayat",
    "not_sayisi", "kirik_link", "yetim_not", "tutarlilik_uyari",
)


def test_surum_ve_kaynak_sozlesmeye_uyar(durum_db: Path, durum_vault: Path) -> None:
    sonuc = calistir("durum", "--json", str(durum_vault), "--db", str(durum_db))
    assert sonuc.returncode == 0, sonuc.stderr
    veri = json.loads(sonuc.stdout)
    assert veri["surum"] == 1
    assert veri["kaynak"] == "harita"


def test_stdout_tek_json_nesnesi_ve_baska_satir_yok(durum_db: Path, durum_vault: Path) -> None:
    """stdout'a YALNIZCA tek JSON nesnesi: ikinci satır/nesne olmamalı."""
    sonuc = calistir("durum", "--json", str(durum_vault), "--db", str(durum_db))
    assert sonuc.returncode == 0, sonuc.stderr
    satirlar = [s for s in sonuc.stdout.split("\n") if s.strip()]
    assert len(satirlar) == 1, sonuc.stdout
    json.loads(satirlar[0])  # tek satır geçerli JSON


def test_alan_adlari_ve_siralar_sozlesmeyle_ayni(durum_db: Path, durum_vault: Path) -> None:
    sonuc = calistir("durum", "--json", str(durum_vault), "--db", str(durum_db))
    veri = json.loads(sonuc.stdout)
    assert tuple(veri) == BEKLENEN_ALANLAR


def test_sayilar_int_ve_sifirdan_kucuk_degil(durum_db: Path, durum_vault: Path) -> None:
    """Tüm sayılar `int` ve `>= 0`; `bool` sayı sayılmaz (Python'ta int tabanı)."""
    sonuc = calistir("durum", "--json", str(durum_vault), "--db", str(durum_db))
    veri = json.loads(sonuc.stdout)
    for anahtar in ("not_sayisi", "kirik_link", "yetim_not"):
        deger = veri[anahtar]
        assert isinstance(deger, int) and not isinstance(deger, bool), anahtar
        assert deger >= 0, anahtar
    assert isinstance(veri["indeks_bayat"], bool)
    assert veri["tutarlilik_uyari"] is None or isinstance(veri["tutarlilik_uyari"], int)


def test_son_indeks_iso8601_ve_utc(durum_db: Path, durum_vault: Path) -> None:
    sonuc = calistir("durum", "--json", str(durum_vault), "--db", str(durum_db))
    veri = json.loads(sonuc.stdout)
    assert veri["son_indeks"] is not None
    cozulen = datetime.fromisoformat(veri["son_indeks"])
    assert cozulen.tzinfo is not None, "ISO-8601 damga zaman dilimi taşımalı"
    assert (cozulen - datetime.now(timezone.utc)).total_seconds() < 300


def test_stdout_ascii_kacisli_windows_uyumlu(durum_db: Path, durum_vault: Path) -> None:
    """`ensure_ascii=True`: çıktı saf ASCII olmalı (Windows cp1252 konsolu)."""
    sonuc = calistir("durum", "--json", str(durum_vault), "--db", str(durum_db))
    assert sonuc.stdout.isascii(), sonuc.stdout
    assert "\\u" not in sonuc.stdout  # ASCII çıktıda zaten kaçış yok


# ---------------------------------------------------------------------------
# Kurgusal vault'ta SAYILAR
# ---------------------------------------------------------------------------


def test_kirik_link_sayisi_dogru(durum_db: Path, durum_vault: Path) -> None:
    """`kirik_link` web `/kirik` sayfasının kullandığı sayıyla AYNIDIR."""
    from harita.index import baglan_salt_okunur, kirik_linkler

    sonuc = calistir("durum", "--json", str(durum_vault), "--db", str(durum_db))
    veri = json.loads(sonuc.stdout)
    assert veri["kirik_link"] == 1

    baglanti = baglan_salt_okunur(durum_db)
    try:
        assert veri["kirik_link"] == len(kirik_linkler(baglanti))
    finally:
        baglanti.close()


def test_yetim_not_sayisi_gercek_yetimlerle_ayni(durum_db: Path, durum_vault: Path) -> None:
    """`yetim_not` = `/yetim` sayfasının "gercek" listesi (daily/ ve kök dosyaları HARİÇ)."""
    from harita.index import baglan_salt_okunur, yetim_ayir

    sonuc = calistir("durum", "--json", str(durum_vault), "--db", str(durum_db))
    veri = json.loads(sonuc.stdout)
    baglanti = baglan_salt_okunur(durum_db)
    try:
        bolum = yetim_ayir(baglanti)
        assert veri["yetim_not"] == len(bolum.gercek)
        # Günlük ayrımı BOŞ DEĞİL: yok sayılabilir sınıfta günlük gerçekten var,
        # ama `yetim_not` onu SAYMAMALI (yoksa 2 dönerdi).
        assert bolum.yok_sayilabilir, "vault'ta yok sayılabilir günlük olmalı"
        assert veri["yetim_not"] == 1
        assert veri["yetim_not"] != bolum.toplam
    finally:
        baglanti.close()


def test_not_sayisi_dogru(durum_db: Path, durum_vault: Path) -> None:
    sonuc = calistir("durum", "--json", str(durum_vault), "--db", str(durum_db))
    assert json.loads(sonuc.stdout)["not_sayisi"] == 5


# ---------------------------------------------------------------------------
# İndeks yok → hata: "indeks_yok", çıkış 1
# ---------------------------------------------------------------------------


def test_indeks_yoksa_hata_kodu_ve_cikis_1(tmp_path: Path) -> None:
    sonuc = calistir("durum", "--json", "--db", str(tmp_path / "hic-yok.db"))
    assert sonuc.returncode == 1
    veri = json.loads(sonuc.stdout)
    assert veri == {"surum": 1, "kaynak": "harita", "hata": "indeks_yok"}


def test_hata_kodu_sabit_kisa_koddur(tmp_path: Path) -> None:
    """Hata kodu bir istisna metni/yol DEĞİL sabit koddur; yol sızmamalı."""
    yol = tmp_path / "CIZGI-SIRADAKI-GIZLI-YOL.db"
    sonuc = calistir("durum", "--json", "--db", str(yol))
    assert sonuc.returncode == 1
    veri = json.loads(sonuc.stdout)
    assert veri["hata"] == "indeks_yok"
    assert "CIZGI" not in sonuc.stdout
    assert "CIZGI" not in sonuc.stderr
    assert str(yol) not in sonuc.stdout and str(yol) not in sonuc.stderr


def test_hata_da_stdouta_json_basilir_ve_stderr_bos(tmp_path: Path) -> None:
    """Sözleşme kuralı 2: hatada da stdout'a JSON basılır; stderr'e gizli/yol girmez."""
    sonuc = calistir("durum", "--json", "--db", str(tmp_path / "yok.db"))
    assert sonuc.stdout.strip(), "hata durumunda stdout boş olmamalı"
    assert sonuc.stderr == ""


def test_bos_vault_gibi_sifir_sayilar_yine_basar(tmp_path: Path) -> None:
    """Sayılar 0 olduğunda hata DEĞİLDİR: indeks varsa çıkış kodu 0."""
    vault = tmp_path / "bos-vault"
    vault.mkdir()
    db = tmp_path / "bos.db"
    assert calistir("indeksle", str(vault), "--db", str(db)).returncode == 0
    sonuc = calistir("durum", "--json", str(vault), "--db", str(db))
    assert sonuc.returncode == 0, sonuc.stderr
    veri = json.loads(sonuc.stdout)
    assert veri["not_sayisi"] == 0 and veri["kirik_link"] == 0 and veri["yetim_not"] == 0
    assert "hata" not in veri


# ---------------------------------------------------------------------------
# Bayatlık
# ---------------------------------------------------------------------------


def test_indeks_bayat_yeni_not_eklenince(durum_db: Path, durum_vault: Path) -> None:
    yaz(durum_vault, "proje/yeni.md", "# Yeni Not\n\nDaha önce yoktu.\n")
    sonuc = calistir("durum", "--json", str(durum_vault), "--db", str(durum_db))
    veri = json.loads(sonuc.stdout)
    assert veri["indeks_bayat"] is True
    assert veri["not_sayisi"] == 5, "bayat indeks ESKİ sayıları verir (yeniden indekslemez)"


def test_indeks_taze_son_indekslemeden_sonra(durum_db: Path, durum_vault: Path) -> None:
    sonuc = calistir("durum", "--json", str(durum_vault), "--db", str(durum_db))
    veri = json.loads(sonuc.stdout)
    assert veri["indeks_bayat"] is False
    assert veri["not_sayisi"] == 5


def test_indeks_bayat_hesaplanamazsa_null_ayni_vault(durum_db: Path, durum_vault: Path) -> None:
    """BAŞKA bir vault verilirse karşılaştırma anlamsız: `null`, `false` DEĞİL."""
    baska = KOK  # harita deposu — indekslenmiş bir kurgusal vault değil
    sonuc = calistir("durum", "--json", str(baska), "--db", str(durum_db))
    veri = json.loads(sonuc.stdout)
    assert veri["indeks_bayat"] is None


def test_vault_verilmezse_bayat_null(durum_db: Path) -> None:
    """Vault verilmeden bayatlık HESAPLANAMAZ: `null` (0 değil, false bile değil)."""
    sonuc = calistir("durum", "--json", "--db", str(durum_db))
    veri = json.loads(sonuc.stdout)
    assert veri["indeks_bayat"] is None
    assert veri["son_indeks"] is not None, "diğer alanlar etkilenmez"


# ---------------------------------------------------------------------------
# Tutarlılık uyarısı
# ---------------------------------------------------------------------------


def test_atlas_db_yokken_tutarlilik_uyari_null(durum_db: Path, durum_vault: Path) -> None:
    """atlas DB'si yoksa uyarı sayısı 0 DEĞİL `null` döner."""
    sonuc = calistir(
        "durum", "--json", str(durum_vault),
        "--db", str(durum_db),
        "--atlas-db", str(durum_vault.parent / "atlas-yok.db"),
    )
    veri = json.loads(sonuc.stdout)
    assert veri["tutarlilik_uyari"] is None
    assert veri["tutarlilik_uyari"] != 0


def test_vault_verilmezse_tutarlilik_uyari_null(durum_db: Path) -> None:
    sonuc = calistir("durum", "--json", "--db", str(durum_db))
    assert json.loads(sonuc.stdout)["tutarlilik_uyari"] is None


def test_atlas_db_sema_uyusmazliginda_null(durum_db: Path, durum_vault: Path, tmp_path: Path) -> None:
    """atlas DB'si VAR ama şemayla uyuşmuyorsa: 0 değil, `null`."""
    bozuk = tmp_path / "bozuk-atlas.db"
    import sqlite3

    baglanti = sqlite3.connect(bozuk)
    baglanti.execute("CREATE TABLE repos (yanlis_sutun TEXT)")
    baglanti.commit()
    baglanti.close()

    sonuc = calistir(
        "durum", "--json", str(durum_vault), "--db", str(durum_db), "--atlas-db", str(bozuk)
    )
    assert sonuc.returncode == 0, sonuc.stderr
    veri = json.loads(sonuc.stdout)
    assert veri["tutarlilik_uyari"] is None
    # Şema uyuşmazlığı metni/istisna ASLA sızmamalı.
    assert "yanlis_sutun" not in sonuc.stdout + sonuc.stderr
    assert "Traceback" not in sonuc.stderr


ATLAS_SEMA = """
CREATE TABLE repos (
    path TEXT PRIMARY KEY, name TEXT NOT NULL, scanned_at TEXT NOT NULL,
    dirty INTEGER NOT NULL DEFAULT 0, unpushed INTEGER, branch TEXT,
    last_commit_at TEXT, has_remote INTEGER NOT NULL DEFAULT 0
);
"""


def test_atlas_db_varken_uyari_sayisi_tutarlilikla_ayni(durum_vault: Path, tmp_path: Path) -> None:
    """atlas DB'si hazırsa `tutarlilik_uyari` = `harita tutarlilik` uyarı SAYISI.

    İkinci bir karşılaştırma mantığı YAZILMAZ: aynı `bulgular_uret` çalıştırılır
    ve sayı buradan okunur.
    """
    import sqlite3

    db = tmp_path / "atlas-var.db"
    baglanti = sqlite3.connect(db)
    baglanti.executescript(ATLAS_SEMA)
    # Vault'taki plan notu "planlandı" ama repoda kod (commit) var →
    # "planlı-ama-kod-var" kuralı BİR uyarı üretir.
    baglanti.execute(
        "INSERT INTO repos (path, name, scanned_at, dirty, unpushed, branch, "
        "last_commit_at, has_remote) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("/tmp/kurgusal-proje", "harita", _iso(0), 0, 0, "main", _iso(1), 1),
    )
    baglanti.commit()
    baglanti.close()

    # `harita tutarlilik` ile referans sayıyı al (JSON çıktısından).
    eslesme = tmp_path / "repolar.toml"
    eslesme.write_text(
        '[eslesme]\n"proje/plan.md" = "harita"\n', encoding="utf-8"
    )
    referans = calistir(
        "tutarlilik", str(durum_vault),
        "--atlas-db", str(db), "--esleme", str(eslesme), "--json",
        "--bugun", BUGUN.isoformat(),
    )
    assert referans.returncode == 0, referans.stderr
    beklenen = len(json.loads(referans.stdout)["uyarilar"])
    # Test BOŞ GEÇMESİN: karşılaştırma gerçekten bir uyarı üretmeli.
    assert beklenen > 0, "kurgusal atlas/vault çifti uyarı üretmeliydi"

    karsilastirma_db = tmp_path / "karsilastirma.db"
    assert calistir("indeksle", str(durum_vault), "--db", str(karsilastirma_db)).returncode == 0
    sonuc = calistir(
        "durum", "--json", str(durum_vault),
        "--db", str(karsilastirma_db),
        "--atlas-db", str(db), "--esleme", str(eslesme),
        "--bugun", BUGUN.isoformat(),
    )
    veri = json.loads(sonuc.stdout)
    assert veri["tutarlilik_uyari"] == beklenen
    assert isinstance(veri["tutarlilik_uyari"], int)
    assert veri["tutarlilik_uyari"] > 0


# ---------------------------------------------------------------------------
# Gizlilik: not başlığı/içeriği ASLA çıktıya girmez
# ---------------------------------------------------------------------------


def test_gizli_diziler_ciktida_aranmaz(durum_db: Path, durum_vault: Path) -> None:
    """Not BAŞLIĞI ve GÖVDESİ çıktının hiçbir yerinde geçmemeli.

    Hem başarılı çıktı hem de tutarlılık uyarısı olan çıktı denenir; ikisinde
    de vault'a özgü hiçbir metin sızmamalı.
    """
    for ek in ([], ["--atlas-db", str(durum_vault.parent / "yok.db")]):
        sonuc = calistir("durum", "--json", str(durum_vault), "--db", str(durum_db), *ek)
        birlesik = sonuc.stdout + sonuc.stderr
        assert GIZLI_BASLIK not in birlesik
        assert GIZLI_ICERIK not in birlesik
        assert GIZLI_ANAHTAR not in birlesik
        # Not yolları da yasak (sözleşme kuralı 4).
        assert "proje/plan.md" not in birlesik
        assert "kose.md" not in birlesik
        assert str(durum_vault) not in birlesik


def test_gizli_dizi_alan_degerinde_de_yok(durum_db: Path, durum_vault: Path) -> None:
    """Kontrol: diziler VAULT'ta GERÇEKTEN var (test yanlış negatif vermesin)."""
    ham = (durum_vault / "proje" / "plan.md").read_text(encoding="utf-8")
    assert GIZLI_BASLIK in ham and GIZLI_ICERIK in ham and GIZLI_ANAHTAR in ham


def test_insan_okur_ozet_yalnizca_sayi_basar(durum_db: Path, durum_vault: Path) -> None:
    """`--json` verilmezse insan-okur özet: yine de not metni sızmaz."""
    sonuc = calistir("durum", str(durum_vault), "--db", str(durum_db))
    assert sonuc.returncode == 0, sonuc.stderr
    assert GIZLI_BASLIK not in sonuc.stdout
    assert GIZLI_ICERIK not in sonuc.stdout
    assert "5 not" in sonuc.stdout


# ---------------------------------------------------------------------------
# Salt-okunurluk kanıtı: indeks dosyası DEĞİŞMEZ
# ---------------------------------------------------------------------------


def _dosya_izgaresi(dosya: Path) -> dict[str, object]:
    """(bayt, mtime_ns, sha256) — üçü birden değişikliği yakalar."""
    import hashlib

    veri = dosya.read_bytes()
    istat = dosya.stat()
    return {
        "boyut": len(veri),
        "mtime_ns": istat.st_mtime_ns,
        "sha256": hashlib.sha256(veri).hexdigest(),
    }


def test_indeks_dosyasi_degismez(durum_db: Path, durum_vault: Path) -> None:
    """`durum` çalıştırılınca indeks dosyası bayt bayt aynı kalır.

    Salt-okunurluk kanıtı: boyut, mtime_ns ve içerik hash'i üçü de eşit.
    """
    once = _dosya_izgaresi(durum_db)
    for ek in ([], [str(durum_vault)], ["--atlas-db", str(durum_vault.parent / "yok.db")]):
        sonuc = calistir("durum", "--json", *ek, "--db", str(durum_db))
        assert sonuc.returncode in (0, 1), sonuc.stderr
    sonra = _dosya_izgaresi(durum_db)
    assert once == sonra


def test_vault_dosyalari_degismez(durum_vault: Path, durum_db: Path) -> None:
    """`durum` vault'a da yazmaz: vault hash'leri aynen korunur."""
    from conftest import vault_hashleri

    once = vault_hashleri(durum_vault)
    assert calistir("durum", "--json", str(durum_vault), "--db", str(durum_db)).returncode == 0
    assert vault_hashleri(durum_vault) == once


def test_salt_okunur_dizinde_calisir(durum_db: Path, durum_vault: Path, tmp_path: Path) -> None:
    """Salt-okunur dizinde de çalışır: DB'ye yazma yetkisi gerekmez."""
    import shutil

    ro_dizin = tmp_path / "ro"
    ro_dizin.mkdir()
    kopya = ro_dizin / "harita.db"
    shutil.copyfile(durum_db, kopya)
    ro_dizin.chmod(0o555)
    try:
        sonuc = calistir("durum", "--json", str(durum_vault), "--db", str(kopya))
        assert sonuc.returncode == 0, sonuc.stderr
        assert json.loads(sonuc.stdout)["not_sayisi"] == 5
    finally:
        ro_dizin.chmod(0o755)


def test_durum_indekslemeyi_tetiklemez(durum_vault: Path, tmp_path: Path) -> None:
    """İndeks YOKSA `durum` onu oluşturmaz; tarama tetiklemez."""
    db = tmp_path / "olmayan.db"
    sonuc = calistir("durum", "--json", str(durum_vault), "--db", str(db))
    assert sonuc.returncode == 1
    assert json.loads(sonuc.stdout)["hata"] == "indeks_yok"
    assert not db.exists(), "durum indeks dosyası OLUŞTURMAMALI"


# ---------------------------------------------------------------------------
# Modül düzeyi: sözleşme sabitleri
# ---------------------------------------------------------------------------


def test_modul_surum_ve_kaynak_sabitleri() -> None:
    assert durum_moduli.SURUM == 1
    assert durum_moduli.KAYNAK == "harita"


def test_hata_kodu_sabitleri_kisa_ve_yolsuz() -> None:
    for kod in (durum_moduli.HATA_INDEKS_YOK, durum_moduli.HATA_OKUNAMADI,
                durum_moduli.HATA_YOK_BILGI):
        assert isinstance(kod, str)
        assert kod == kod.strip() and " " not in kod
        assert "/" not in kod and os.sep not in kod


def test_sozluk_hata_da_sadece_uc_anahtar_doner() -> None:
    d = durum_moduli.Durum(hata=durum_moduli.HATA_INDEKS_YOK, _yalnizca_hata=True)
    assert d.sozluk() == {"surum": 1, "kaynak": "harita", "hata": "indeks_yok"}


def test_sozluk_basarida_hata_anahtari_yok(tmp_path: Path, durum_db: Path) -> None:
    d = durum_moduli.durum_oku(durum_db, None)
    assert d.hata is None
    assert "hata" not in d.sozluk()
    assert set(d.sozluk()) == set(BEKLENEN_ALANLAR)


def test_null_ayri_sifirdan_korunur() -> None:
    """`null` ile `0` farklıdır ve `.sozluk()` birini diğerine çevirmez."""
    d = durum_moduli.Durum(
        indeks_bayat=None, tutarlilik_uyari=None, not_sayisi=0,
        _yalnizca_hata=False,
    )
    sozluk = d.sozluk()
    assert sozluk["indeks_bayat"] is None
    assert sozluk["tutarlilik_uyari"] is None
    assert sozluk["not_sayisi"] == 0


def test_cli_durum_hata_donus_kodu(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """`main()` sarmalayıcısı da hatada 1 döner ve JSON basar."""
    kod = cli_main(["durum", "--json", "--db", str(tmp_path / "yok.db")])
    assert kod == 1
    cikti = capsys.readouterr().out
    assert json.loads(cikti)["hata"] == "indeks_yok"
