"""CLI testleri: gerçek alt süreç (`python3 -m orkestra ...`), ORKESTRA_DB ile izole."""

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from orkestra.models import Durum
from orkestra.queue import Queue

REPO = Path(__file__).resolve().parent.parent

# CLI testleri DALGA B komutlarını gerçek `claude` yerine sahte betikle koşar.
SAHTE_BETIK = '''
import os, sys, time

MOD = os.environ.get("FAKE_MODE", "basari")
if "--help" in sys.argv:
    print("  --agent <agent>  Agent")
    print("  --permission-mode <mode>  choices: acceptEdits")
    sys.exit(0)
istem = sys.stdin.read()
if os.environ.get("FAKE_ARGV"):
    open(os.environ["FAKE_ARGV"], "w", encoding="utf-8").write("\\n".join(sys.argv[1:]))
if MOD == "hata":
    print("claude patladi"); sys.exit(4)
if MOD == "izin":
    print("Permission denied by the safety classifier"); sys.exit(3)
if MOD == "uyu":
    time.sleep(300)
print("tamam: " + istem[:20])
'''


@pytest.fixture()
def sahte_claude_cmd(tmp_path):
    """ORKESTRA_CLAUDE_CMD için gerçek bir sahte betik yolu."""
    yol = tmp_path / "sahte_claude.py"
    yol.write_text(SAHTE_BETIK, encoding="utf-8")
    return f"{sys.executable} {yol}"


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


# -- calistir-bir -------------------------------------------------------


def test_calistir_bir_bos_kuyruk(db):
    """B dalgasında çıkış-2 sürümü KALDIRILDI: artık gerçekten çalıştırır."""
    sonuc = calistir("calistir-bir", db=db)
    assert sonuc.returncode == 0, sonuc.stderr
    assert "bekleyen gorev yok" in sonuc.stdout


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


# -- Dalga B: calistir-bir / calistir / kurtar / rapor ------------------


def test_calistir_bir_gorevi_calistirir(db, tmp_path, sahte_claude_cmd):
    cikti = tmp_path / "runs"
    calistir("ver", "--ajan", "bunny-coder", "bir is", db=db)
    sonuc = calistir(
        "calistir-bir", "--model", "test-model", "--cwd", str(tmp_path),
        "--cikti-dizini", str(cikti), db=db, ortam={"ORKESTRA_CLAUDE_CMD": sahte_claude_cmd},
    )
    assert sonuc.returncode == 0, sonuc.stderr
    assert "bitti" in sonuc.stdout
    assert "run id" in sonuc.stdout
    assert "log" in sonuc.stdout
    with Queue(db) as q:
        gorev, kosu = q.al(1), q.kosular(1)[0]
        assert gorev.durum is Durum.BITTI
        assert kosu.cikti_yolu
        assert Path(kosu.cikti_yolu).is_file()
        assert stat.S_IMODE(Path(kosu.cikti_yolu).stat().st_mode) == 0o600


def test_calistir_bir_ciktiyi_ekrana_dokmez(db, tmp_path, sahte_claude_cmd):
    """Log YOLU basilir; log METNI ekrana dokulmez."""
    cikti = tmp_path / "runs"
    calistir("ver", "--ajan", "bunny-coder", "bir is", db=db)
    sonuc = calistir(
        "calistir-bir", "--cikti-dizini", str(cikti), db=db,
        ortam={"ORKESTRA_CLAUDE_CMD": sahte_claude_cmd},
    )
    assert sonuc.returncode == 0, sonuc.stderr
    assert "tamam:" not in sonuc.stdout  # sahte betigin ham ciktisi ekranda olmamali


def test_calistir_bir_hata_durumu(db, tmp_path, sahte_claude_cmd):
    cikti = tmp_path / "runs"
    calistir("ver", "--ajan", "bunny-coder", "bir is", db=db)
    sonuc = calistir(
        "calistir-bir", "--cikti-dizini", str(cikti), db=db,
        ortam={"ORKESTRA_CLAUDE_CMD": sahte_claude_cmd, "FAKE_MODE": "hata"},
    )
    assert sonuc.returncode == 0
    assert "hata" in sonuc.stdout
    with Queue(db) as q:
        assert q.al(1).durum is Durum.HATA


def test_calistir_bir_onay_bekliyor(db, tmp_path, sahte_claude_cmd):
    cikti = tmp_path / "runs"
    calistir("ver", "--ajan", "bunny-coder", "bir is", db=db)
    sonuc = calistir(
        "calistir-bir", "--cikti-dizini", str(cikti), db=db,
        ortam={"ORKESTRA_CLAUDE_CMD": sahte_claude_cmd, "FAKE_MODE": "izin"},
    )
    assert sonuc.returncode == 0
    assert "onay-bekliyor" in sonuc.stdout
    with Queue(db) as q:
        assert q.al(1).durum is Durum.ONAY_BEKLIYOR


def test_calistir_bir_bos_kuyruk_cikis_0(db):
    sonuc = calistir("calistir-bir", db=db)
    assert sonuc.returncode == 0
    assert "bekleyen gorev yok" in sonuc.stdout


def test_calistir_bir_zaman_asimi(db, tmp_path, sahte_claude_cmd):
    cikti = tmp_path / "runs"
    calistir("ver", "--ajan", "bunny-coder", "bir is", db=db)
    sonuc = calistir(
        "calistir-bir", "--zaman-asimi", "1", "--cikti-dizini", str(cikti), db=db,
        ortam={"ORKESTRA_CLAUDE_CMD": sahte_claude_cmd, "FAKE_MODE": "uyu"},
        timeout=60,
    )
    assert sonuc.returncode == 0, sonuc.stderr
    assert "zaman-asimi" in sonuc.stdout
    with Queue(db) as q:
        assert q.al(1).durum is Durum.HATA
        assert q.kosular(1)[0].cikis_kodu == 124


def test_calistir_bir_isten_alir(db, tmp_path, sahte_claude_cmd):
    """İstem STDIN'den gider; komut satırında görünmez."""
    cikti = tmp_path / "runs"
    argv_dosya = tmp_path / "argv.txt"
    calistir("ver", "--ajan", "bunny-coder", "OZEL-ISTEM-METNI", db=db)
    sonuc = calistir(
        "calistir-bir", "--cikti-dizini", str(cikti), db=db,
        ortam={"ORKESTRA_CLAUDE_CMD": sahte_claude_cmd, "FAKE_ARGV": str(argv_dosya)},
    )
    assert sonuc.returncode == 0, sonuc.stderr
    assert "OZEL-ISTEM-METNI" not in argv_dosya.read_text(encoding="utf-8")


def test_calistir_bir_db_bayragi_iki_konumda(db, tmp_path, sahte_claude_cmd):
    cikti = tmp_path / "runs"
    ozel = tmp_path / "ozel.db"
    calistir("ver", "--ajan", "bunny-coder", "is", db=ozel)
    # --db komuttan SONRA
    sonuc = calistir(
        "calistir-bir", "--cikti-dizini", str(cikti), "--db", str(ozel), db=db,
        ortam={"ORKESTRA_CLAUDE_CMD": sahte_claude_cmd},
    )
    assert sonuc.returncode == 0, sonuc.stderr
    assert ozel.exists() and not db.exists()
    with Queue(ozel) as q:
        assert q.al(1).durum is Durum.BITTI


def test_calistir_bir_model_bayragi_gecer(db, tmp_path, sahte_claude_cmd):
    cikti = tmp_path / "runs"
    argv_dosya = tmp_path / "argv.txt"
    calistir("ver", "--ajan", "bunny-coder", "is", db=db)
    sonuc = calistir(
        "calistir-bir", "--model", "stealth/space-bunny-alpha", "--cikti-dizini", str(cikti),
        db=db, ortam={"ORKESTRA_CLAUDE_CMD": sahte_claude_cmd, "FAKE_ARGV": str(argv_dosya)},
    )
    assert sonuc.returncode == 0, sonuc.stderr
    argv = argv_dosya.read_text(encoding="utf-8")
    assert "--model" in argv and "stealth/space-bunny-alpha" in argv
    assert "acceptEdits" in argv
    assert "bypassPermissions" not in argv


def test_calistir_sirayla_calistirir(db, tmp_path, sahte_claude_cmd):
    cikti = tmp_path / "runs"
    for i in range(3):
        calistir("ver", "--ajan", "bunny-coder", f"is {i}", db=db)
    sonuc = calistir(
        "calistir", "--cikti-dizini", str(cikti), db=db,
        ortam={"ORKESTRA_CLAUDE_CMD": sahte_claude_cmd},
    )
    assert sonuc.returncode == 0, sonuc.stderr
    assert "Toplam 3 gorev calistirildi" in sonuc.stdout
    with Queue(db) as q:
        assert [g.durum for g in q.liste()] == [Durum.BITTI] * 3


def test_calistir_limit(db, tmp_path, sahte_claude_cmd):
    cikti = tmp_path / "runs"
    for i in range(4):
        calistir("ver", "--ajan", "bunny-coder", f"is {i}", db=db)
    sonuc = calistir(
        "calistir", "--limit", "2", "--cikti-dizini", str(cikti), db=db,
        ortam={"ORKESTRA_CLAUDE_CMD": sahte_claude_cmd},
    )
    assert sonuc.returncode == 0, sonuc.stderr
    assert "Toplam 2 gorev calistirildi" in sonuc.stdout
    with Queue(db) as q:
        durumlar = [g.durum for g in q.liste()]
        assert durumlar.count(Durum.BITTI) == 2
        assert durumlar.count(Durum.BEKLIYOR) == 2


def test_calistir_limit_gecersiz(db):
    sonuc = calistir("calistir", "--limit", "0", db=db)
    assert sonuc.returncode == 2


def test_calistir_bos_kuyruk(db):
    sonuc = calistir("calistir", db=db)
    assert sonuc.returncode == 0
    assert "bekleyen gorev yok" in sonuc.stdout


def test_kurtar_yarimkalan_gorevleri_kurtarir(db):
    with Queue(db) as q:
        gorev = q.ekle("bunny-coder", "is")
        q.gecis(gorev.id, Durum.CALISIYOR)
        q.kapat()
    sonuc = calistir("kurtar", db=db)
    assert sonuc.returncode == 0, sonuc.stderr
    assert "kurtarildi" in sonuc.stdout
    with Queue(db) as q:
        assert q.al(1).durum is Durum.HATA


def test_kurtar_bos(db):
    calistir("ver", "--ajan", "bunny-coder", "is", db=db)
    sonuc = calistir("kurtar", db=db)
    assert sonuc.returncode == 0
    assert "yok" in sonuc.stdout


def test_rapor_gorevin_son_kosusunu_gosterir(db, tmp_path, sahte_claude_cmd):
    cikti = tmp_path / "runs"
    calistir("ver", "--ajan", "bunny-coder", "bir is", db=db)
    calistir(
        "calistir-bir", "--cikti-dizini", str(cikti), db=db,
        ortam={"ORKESTRA_CLAUDE_CMD": sahte_claude_cmd},
    )
    sonuc = calistir("rapor", "1", db=db)
    assert sonuc.returncode == 0, sonuc.stderr
    assert "Gorev #1" in sonuc.stdout
    assert "run id" in sonuc.stdout
    assert "sure" in sonuc.stdout
    assert "cikis kodu" in sonuc.stdout
    assert "log" in sonuc.stdout
    # Logun son satirlari gosterilir.
    assert "tamam" in sonuc.stdout


def test_rapor_hatali_gorevde_hata_metni(db, tmp_path, sahte_claude_cmd):
    cikti = tmp_path / "runs"
    calistir("ver", "--ajan", "bunny-coder", "bir is", db=db)
    calistir(
        "calistir-bir", "--cikti-dizini", str(cikti), db=db,
        ortam={"ORKESTRA_CLAUDE_CMD": sahte_claude_cmd, "FAKE_MODE": "hata"},
    )
    sonuc = calistir("rapor", "1", db=db)
    assert sonuc.returncode == 0
    assert "claude cikis kodu 4" in sonuc.stdout


def test_rapor_hic_calistirilmamis_gorev(db):
    calistir("ver", "--ajan", "bunny-coder", "is", db=db)
    sonuc = calistir("rapor", "1", db=db)
    assert sonuc.returncode == 0
    assert "calistirilmamis" in sonuc.stdout


def test_rapor_bilinmeyen_kimlik(db):
    sonuc = calistir("rapor", "99", db=db)
    assert sonuc.returncode == 1
    assert "bulunamadi" in sonuc.stderr


def test_rapor_son_kosuyu_gosterir(db, tmp_path, sahte_claude_cmd):
    """Birden fazla koşu varsa SON koşu raporlanır."""
    cikti = tmp_path / "runs"
    calistir("ver", "--ajan", "bunny-coder", "is", db=db)
    # 1. kosu: basarisiz
    calistir(
        "calistir-bir", "--cikti-dizini", str(cikti), db=db,
        ortam={"ORKESTRA_CLAUDE_CMD": sahte_claude_cmd, "FAKE_MODE": "hata"},
    )
    calistir("tekrar", "1", db=db)
    # 2. kosu: basarili
    calistir(
        "calistir-bir", "--cikti-dizini", str(cikti), db=db,
        ortam={"ORKESTRA_CLAUDE_CMD": sahte_claude_cmd},
    )
    sonuc = calistir("rapor", "1", db=db)
    assert sonuc.returncode == 0, sonuc.stderr
    assert "bitti" in sonuc.stdout
    assert "claude cikis kodu 4" not in sonuc.stdout  # ESKI kosunun hatasi degil
    with Queue(db) as q:
        assert len(q.kosular(1)) == 2
        assert q.kosular(1)[-1].cikis_kodu == 0
    assert "run id    : 2" in sonuc.stdout


def test_yeni_komutlar_yardimda(db):
    sonuc = calistir("--help", db=db)
    for komut in ("calistir-bir", "calistir", "kurtar", "rapor"):
        assert komut in sonuc.stdout


def test_rapor_cevrimici_karakter(db, tmp_path, sahte_claude_cmd):
    cikti = tmp_path / "runs"
    calistir("ver", "--ajan", "bunny-coder", "Şu ızgara ğğğ öüç testi", db=db)
    calistir(
        "calistir-bir", "--cikti-dizini", str(cikti), db=db,
        ortam={"ORKESTRA_CLAUDE_CMD": sahte_claude_cmd},
    )
    sonuc = calistir("rapor", "1", db=db)
    assert sonuc.returncode == 0
    # ızgara kelimesi log'da bozulmadan gorunur
    assert "ızgara" in sonuc.stdout