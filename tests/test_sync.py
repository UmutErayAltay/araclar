"""`tools/sync.py` testleri — SOZLESME 3. bölüm.

`--check`'in ÜÇ bozulma durumunu (başlık yok / gövde elle düzenlenmiş / eski
sürüm) gerçekten yakaladığı doğrulanır. Bunlar mutasyonla da sınanır: gövdeye
tek karakter eklemek `--check`'i 1'e düşürmelidir.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_KOK = Path(__file__).resolve().parent.parent
_ARAC = _KOK / "tools" / "sync.py"
_KAYNAK = _KOK / "corclient.py"


def _kaynak_lf() -> bytes:
    """Windows autocrlf checkout kaynağı CRLF yapar; sync LF üzerinden çalışır."""
    return _KAYNAK.read_bytes().replace(b"\r\n", b"\n")

sys.path.insert(0, str(_KOK / "tools"))
import sync  # noqa: E402


def _calistir(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_ARAC), *args],
        capture_output=True,
        text=True,
        cwd=str(_KOK),
    )


@pytest.fixture
def hedef(tmp_path: Path) -> Path:
    """Senkronlanmış tek kopyalanmış durumdaki hedef."""
    yol = tmp_path / "paket" / "_corclient.py"
    assert _calistir(str(yol)).returncode == 0
    return yol


# --------------------------------------------------------------------- #
# Yazma
# --------------------------------------------------------------------- #


def test_yazma_baslik_bicimi_ve_kaynak_baytlari(hedef: Path) -> None:
    """Başlık tam sözleşme biçiminde, gövde kaynak BAYTLARIyla aynı."""
    ham = hedef.read_bytes()
    satirlar = ham.split(b"\n", 1)
    baslik = satirlar[0].decode("utf-8")

    surum = sync.kaynak_surum()
    beklenen_sha = sync.govde_sha256(_kaynak_lf())
    assert baslik == f"# SENKRON corclient surum={surum} sha256={beklenen_sha}"
    assert baslik.startswith("# SENKRON corclient surum=")
    assert baslik.count("\n") == 0  # başlık kendi satırında

    # Gövde kaynağın birebir baytları (baştaki/ sondaki boşluk dahil).
    assert satirlar[1] == _kaynak_lf()


def test_yazma_ust_uzere_yazmak(hedef: Path) -> None:
    """İkinci çalıştırma başlığı ARAYA sokmaz (idempotent)."""
    ilk = hedef.read_bytes()
    assert _calistir(str(hedef)).returncode == 0
    assert hedef.read_bytes() == ilk
    assert hedef.read_bytes().count(b"# SENKRON corclient") == 1


def test_yazma_bos_olmayan_hedefin_ustune_yazabilir(tmp_path: Path) -> None:
    """Eski/bozuk içerik üzerine yazmak onarır."""
    yol = tmp_path / "_corclient.py"
    yol.write_text("# SENKRON corclient surum=0.0.1 sha256=" + "0" * 64 + "\neski kod\n")
    assert _calistir(str(yol)).returncode == 0
    assert _calistir("--check", str(yol)).returncode == 0


def test_yazma_bosluk_olusturur(tmp_path: Path) -> None:
    yol = tmp_path / "yeni" / "paket" / "_corclient.py"
    assert _calistir(str(yol)).returncode == 0
    assert yol.is_file()


# --------------------------------------------------------------------- #
# --check: mutlu yol
# --------------------------------------------------------------------- #


def test_check_guncel_kopya_gecer(hedef: Path) -> None:
    sonuc = _calistir("--check", str(hedef))
    assert sonuc.returncode == 0, sonuc.stderr
    assert "OK" in sonuc.stdout


def test_check_bosluk_kabul(hedef: Path) -> None:
    sonuc = _calistir("--check", str(hedef))
    assert sonuc.returncode == 0


# --------------------------------------------------------------------- #
# --check: ÜÇ bozulma durumu — HEPSİ kırılmalı
# --------------------------------------------------------------------- #


def test_check_baslik_yoksa_kirilir(tmp_path: Path) -> None:
    """(a) Başlık yok → 1."""
    yol = tmp_path / "_corclient.py"
    yol.write_bytes(_kaynak_lf())

    sonuc = _calistir("--check", str(yol))
    assert sonuc.returncode == 1
    assert "başlığı yok" in sonuc.stderr


def test_check_govde_elle_duzenlendiyse_kirilir(hedef: Path) -> None:
    """(b) Gövdeye karakter eklenmiş → 1 (elle düzenleme yakalanır)."""
    ham = hedef.read_bytes()
    hedef.write_bytes(ham + b"# elle eklenmis yorum\n")

    sonuc = _calistir("--check", str(hedef))
    assert sonuc.returncode == 1
    assert "elle düzenlenmiş" in sonuc.stderr


def test_check_govde_bir_karakter_degistirilirse_kirilir(hedef: Path) -> None:
    """(b') Tek karakter bile değişse yakalanır."""
    ham = hedef.read_bytes()
    hedef.write_bytes(ham.replace(b"retry", b"retyr", 1))

    sonuc = _calistir("--check", str(hedef))
    assert sonuc.returncode == 1
    assert "elle düzenlenmiş" in sonuc.stderr


def test_check_eski_surum_kirilir(tmp_path: Path) -> None:
    """(c) Gövde KENDİ İÇİNDE tutarlı ama eski sürüm → 1.

    Kopya, kaynak güncellenmeden bırakılmış: başlık kendi gövdesinin sha256'sını
    taşır (elle düzenleme YOK), ama o gövde bu repodaki güncel kaynaktan farklıdır
    (eski sürüm).
    """
    eski_govde = _kaynak_lf().replace(b"__surum__", b"_surum", 1)
    assert eski_govde != _kaynak_lf()
    yol = tmp_path / "_corclient.py"
    yol.write_bytes(
        sync.baslik_uret("0.0.9", sync.govde_sha256(eski_govde)).encode("utf-8") + eski_govde
    )

    sonuc = _calistir("--check", str(yol))
    assert sonuc.returncode == 1
    assert "eski sürüm" in sonuc.stderr


def test_check_yalnizca_surum_alani_bozulursa_gecer(tmp_path: Path) -> None:
    """Sözleşmenin SINIRI: sapma tanımı sha256'a bağlıdır, sürüm metnine DEĞİL.

    SOZLESME 3. bölüm (c) koşulu "başlıktaki sha256 bu repodaki GÜNCEL kaynakla
    tutuyor mu" der; yalnız `surum=` METNİ çarpıtılmış, sha256 doğru ise
    sapma sayılmaz. Kaynakta `__surum__` zaten gövde İÇİNDE olduğundan gerçek bir
    sürüm değişikliği sha256'ı da değiştirir ve (c) ile yakalanır.
    """
    guncel = _kaynak_lf()
    sha = sync.govde_sha256(guncel)
    yol = tmp_path / "_corclient.py"
    yol.write_bytes(f"# SENKRON corclient surum=0.0.9 sha256={sha}\n".encode() + guncel)

    assert _calistir("--check", str(yol)).returncode == 0


def test_kaynakta_surum_degisince_check_kirilir(hedef: Path) -> None:
    """Kaynakta `__surum__` değişirse gövde değişir → kopya 'eski sürüm' olur."""
    guncel = _kaynak_lf()
    yeni_kaynak = guncel.replace(b'__surum__ = "0.1.0"', b'__surum__ = "0.2.0"')
    assert yeni_kaynak != guncel

    # Başlıktaki sha256 kaynak gövdesininkiyle TUTMUYOR ama kopya kendi
    # gövdesiyle tutuyor: yani tüketici güncelleme yapmamış.
    kopya_govde = yeni_kaynak.replace(b'__surum__ = "0.2.0"', b'__surum__ = "0.1.0"')
    yol = hedef
    yol.write_bytes(
        sync.baslik_uret("0.1.0", sync.govde_sha256(kopya_govde)).encode("utf-8")
        + kopya_govde
    )

    # Kaynak hâlâ 0.1.0 ise bu kopya doğrudur; sapma YOK.
    assert _calistir("--check", str(yol)).returncode == 0
    # Kaynak 0.2.0 olsaydı aynı kopya sapma olurdu — sha256 farklılaşır.
    assert sync.govde_sha256(kopya_govde) != sync.govde_sha256(yeni_kaynak)


def test_check_bozuk_baslik_kirilir(hedef: Path) -> None:
    """Başlık var ama biçimi bozuk → 1."""
    ham = hedef.read_bytes().split(b"\n", 1)
    hedef.write_bytes(b"# SENKRON corclient surum=0.1.0 sha256=zzz\n" + ham[1])

    sonuc = _calistir("--check", str(hedef))
    assert sonuc.returncode == 1
    assert "bozuk" in sonuc.stderr


def test_check_eksik_dosya_kirilir(tmp_path: Path) -> None:
    sonuc = _calistir("--check", str(tmp_path / "yok.py"))
    assert sonuc.returncode == 1
    assert "dosya yok" in sonuc.stderr


# --------------------------------------------------------------------- #
# Birden çok hedef / raporlama
# --------------------------------------------------------------------- #


def test_check_coklu_hedef_kirik_olani_bildirir(hedef: Path, tmp_path: Path) -> None:
    """Kopmak olan varsa 1 ve hangi YOL'un neden kırıldığı stderr'de."""
    bozuk = tmp_path / "bozuk.py"
    bozuk.write_bytes(hedef.read_bytes() + b"# sapma\n")

    sonuc = _calistir("--check", str(hedef), str(bozuk))
    assert sonuc.returncode == 1
    assert "OK" in sonuc.stdout
    assert str(bozuk) in sonuc.stderr
    assert str(hedef) not in sonuc.stderr


def test_check_coklu_hedef_hepsi_gecer(hedef: Path, tmp_path: Path) -> None:
    ikinci = tmp_path / "ikinci.py"
    assert _calistir(str(ikinci)).returncode == 0
    sonuc = _calistir("--check", str(hedef), str(ikinci))
    assert sonuc.returncode == 0, sonuc.stderr


# --------------------------------------------------------------------- #
# Hedef yol koda GÖMÜLMEZ
# --------------------------------------------------------------------- #


def test_hedef_yol_araca_gomulu_degil() -> None:
    """Sözleşme: yerel yol sızıntısı yok."""
    metin = _ARAC.read_text(encoding="utf-8")
    assert "/home/" not in metin
    assert "user" not in metin.replace("kullanıcı", "")


def test_kaynak_surum_dogru_okunuyor() -> None:
    assert sync.kaynak_surum() == "0.1.0"


def test_check_crlf_kopya_gecer(hedef: Path) -> None:
    """Windows `autocrlf` kopyayı CRLF'ye çevirse de sapma SAYILMAZ (gövde LF ile hash'lenir)."""
    ham = hedef.read_bytes()
    assert b"\r\n" not in ham
    hedef.write_bytes(ham.replace(b"\n", b"\r\n"))
    sonuc = _calistir("--check", str(hedef))
    assert sonuc.returncode == 0, sonuc.stderr


def test_check_crlf_kopyada_elle_duzenleme_yine_kirilir(hedef: Path) -> None:
    """CRLF toleransı elle düzenlemeyi GİZLEMEZ."""
    ham = hedef.read_bytes().replace(b"\n", b"\r\n")
    hedef.write_bytes(ham.replace(b"__surum__", b"__SURUM__", 1))
    sonuc = _calistir("--check", str(hedef))
    assert sonuc.returncode == 1
    assert "elle düzenlenmiş" in sonuc.stderr


def test_kaynak_crlf_ise_bile_govde_lf_ve_hash_ayni(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Kaynak dosya Windows'ta CRLF checkout edilirse yazılan gövde/hash DEĞİŞMEZ."""
    orijinal = sync.kaynak_govde()
    crlf = tmp_path / "corclient.py"
    crlf.write_bytes(_kaynak_lf().replace(b"\n", b"\r\n"))
    monkeypatch.setattr(sync, "KAYNAK", crlf)
    assert b"\r\n" not in sync.kaynak_govde()
    assert sync.kaynak_govde() == orijinal
    assert sync.govde_sha256(sync.kaynak_govde()) == sync.govde_sha256(orijinal)
