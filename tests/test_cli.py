"""CLI testleri: gerçek alt süreç (`python3 -m orkestra ...`), ORKESTRA_DB ile izole."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from orkestra.models import Durum
from orkestra.queue import Queue

REPO = Path(__file__).resolve().parent.parent


def calistir(*argv, db=None, ortam=None, timeout=30):
    """`python3 -m orkestra ...` komutunu gerçek bir süreçte koşturur."""
    cevre = dict(os.environ)
    cevre.pop("ORKESTRA_DB", None)
    cevre["PYTHONIOENCODING"] = "utf-8"
    if db is not None:
        cevre["ORKESTRA_DB"] = str(db)
    if ortam:
        cevre.update(ortam)
    return subprocess.run(
        [sys.executable, "-m", "orkestra", *argv],
        cwd=str(REPO),
        env=cevre,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
    )


@pytest.fixture()
def db(tmp_path):
    return tmp_path / "cli.db"


# -- ver / liste --------------------------------------------------------


def test_ver_ekler_ve_cikti_verir(db):
    sonuc = calistir("ver", "--ajan", "bunny-coder", "ilk is", db=db)
    assert sonuc.returncode == 0, sonuc.stderr
    assert "#1" in sonuc.stdout
    assert "bekliyor" in sonuc.stdout


def test_liste_bos_kuyruk(db):
    sonuc = calistir("liste", db=db)
    assert sonuc.returncode == 0
    assert "bos" in sonuc.stdout.lower()


def test_liste_gorevleri_gosterir(db):
    calistir("ver", "--ajan", "bunny-coder", "birinci is", db=db)
    calistir("ver", "--ajan", "nemotron", "ikinci is", db=db)
    sonuc = calistir("liste", db=db)
    assert sonuc.returncode == 0
    assert "birinci is" in sonuc.stdout
    assert "ikinci is" in sonuc.stdout
    assert "Toplam 2 gorev" in sonuc.stdout


def test_liste_durum_filtresi(db):
    calistir("ver", "--ajan", "bunny-coder", "bir", db=db)
    calistir("ver", "--ajan", "bunny-coder", "iki", db=db)
    calistir("iptal", "1", db=db)
    sonuc = calistir("liste", "--durum", "iptal", db=db)
    assert sonuc.returncode == 0
    assert "Toplam 1 gorev" in sonuc.stdout
    assert "bir" in sonuc.stdout


def test_liste_gecersiz_durum_secenek(db):
    sonuc = calistir("liste", "--durum", "uydurma", db=db)
    assert sonuc.returncode == 2


# -- iptal / tekrar -----------------------------------------------------


def test_iptal(db):
    calistir("ver", "--ajan", "bunny-coder", "is", db=db)
    sonuc = calistir("iptal", "1", db=db)
    assert sonuc.returncode == 0
    assert "iptal" in sonuc.stdout
    with Queue(db) as q:
        assert q.al(1).durum is Durum.IPTAL


def test_iptal_bilinmeyen_kimlik(db):
    calistir("ver", "--ajan", "bunny-coder", "is", db=db)
    sonuc = calistir("iptal", "99", db=db)
    assert sonuc.returncode == 1
    assert "bulunamadi" in sonuc.stderr


def test_iptal_olmayan_durum_hatasi(db):
    calistir("ver", "--ajan", "bunny-coder", "is", db=db)
    calistir("iptal", "1", db=db)
    sonuc = calistir("iptal", "1", db=db)
    assert sonuc.returncode == 1
    assert "gecersiz gecis" in sonuc.stderr


def test_tekrar_hata_dan(db):
    with Queue(db) as q:
        gorev = q.ekle("bunny-coder", "is")
        q.gecis(gorev.id, Durum.CALISIYOR)
        q.gecis(gorev.id, Durum.HATA)
    sonuc = calistir("tekrar", "1", db=db)
    assert sonuc.returncode == 0
    assert "bekliyor" in sonuc.stdout


def test_tekrar_bekleyen_gorevde_hata(db):
    calistir("ver", "--ajan", "bunny-coder", "is", db=db)
    sonuc = calistir("tekrar", "1", db=db)
    assert sonuc.returncode == 1
    assert "gecersiz gecis" in sonuc.stderr


# -- guard / gizlilik ---------------------------------------------------


def test_ver_gizli_istemi_reddeder(db):
    sir = "sk-abcdefghijklmnopqrstuvwxyz012345"
    sonuc = calistir("ver", "--ajan", "bunny-coder", f"bak: {sir}", db=db)
    assert sonuc.returncode == 1
    assert "gizli bilgi" in sonuc.stderr
    assert sir not in sonuc.stderr
    assert sir not in sonuc.stdout


def test_ver_gecersiz_ajan_reddeder(db):
    sonuc = calistir("ver", "--ajan", "Bunny Coder", "temiz is", db=db)
    assert sonuc.returncode == 1
    assert "gecersiz ajan" in sonuc.stderr


def test_ver_girisi_reddedilince_kuyruk_bos(db):
    calistir("ver", "--ajan", "bunny-coder", "token=abcdefgh1234", db=db)
    with Queue(db) as q:
        assert q.liste() == []


# -- ortam / yol --------------------------------------------------------


def test_ortam_degiskeni_db_yolu(db):
    cevre = dict(os.environ)
    cevre["ORKESTRA_DB"] = str(db)
    sonuc = subprocess.run(
        [sys.executable, "-m", "orkestra", "ver", "--ajan", "bunny-coder", "is"],
        cwd=str(REPO),
        env=cevre,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert sonuc.returncode == 0, sonuc.stderr
    assert db.exists()


def test_db_dosyasi_olusturulur(db):
    calistir("liste", db=db)
    assert db.exists()


def test_varsayilan_db_yolu_home_altinda(tmp_path):
    """ORKESTRA_DB yoksa ~/.orkestra/orkestra.db kullanilir."""
    ev = tmp_path / "ev"
    ev.mkdir()
    sonuc = calistir("liste", ortam={"HOME": str(ev)})
    assert sonuc.returncode == 0, sonuc.stderr
    assert (ev / ".orkestra" / "orkestra.db").exists()


def test_db_bayragi_ortam_degiskenini_ezer(tmp_path, db):
    sonuc = calistir("ver", "--ajan", "bunny-coder", "is", "--db", str(tmp_path / "a.db"), db=db)
    assert sonuc.returncode == 0, sonuc.stderr
    assert (tmp_path / "a.db").exists()
    assert not db.exists()


def test_ayri_surecler_ayni_kuyrugu_gorur(db):
    calistir("ver", "--ajan", "bunny-coder", "kalici", db=db)
    assert "kalici" in calistir("liste", db=db).stdout


# -- kalistir-bir -------------------------------------------------------


def test_calistir_bir_b_dalgasinda(db):
    sonuc = calistir("calistir-bir", db=db)
    assert sonuc.returncode == 2
    assert "B dalgasinda" in sonuc.stdout
    assert not db.exists()  # komut DB'ye dokunmadan cikar


# -- kodlama / argümanlar ------------------------------------------------


def test_turkce_karakterler_yuvarlak_trip(db):
    istem = "Şu ızgara ğğğ öüç dosyasını kontrol et"
    ekleme = calistir("ver", "--ajan", "bunny-coder", istem, db=db)
    assert ekleme.returncode == 0, ekleme.stderr
    liste = calistir("liste", db=db)
    assert liste.returncode == 0
    assert "ızgara" in liste.stdout
    with Queue(db) as q:
        assert q.al(1).istem == istem


def test_yardim_ciktisi(db):
    sonuc = calistir("--help", db=db)
    assert sonuc.returncode == 0
    assert "ver" in sonuc.stdout and "liste" in sonuc.stdout


def test_komut_zorunlu(db):
    assert calistir(db=db).returncode == 2


def test_ajan_zorunlu(db):
    assert calistir("ver", "istem metni", db=db).returncode == 2