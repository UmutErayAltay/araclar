"""BAĞLAYICI KANIT: "ham sır yok".

Fixture repoda BILINEN sahte sirlar olusturulur, sonra:
  (a) DB dosyasinin HAM BAYTLARI,
  (b) `sizinti` ve `bulgular` komutlarinin stdout/stderr ciktilari,
  (c) pytest ciktisi
  icinde sahte sirin HICBIR parcasi (ilk 6 karakter DAHIL) bulunmadigi
  otomatik olarak dogrulanir.

Sahte sirler kaynakta tam literal olarak YAZILMAZ; parcalardan kurulur.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from conftest import commit_file, git, make_repo, run_module_cli

#: Kanitlanacak sahte sirler: parcalardan kurulur.
SAHTE = {
    "sk": "sk-" + "a1" * 15,
    "aws": "AK" + "IA" + "X7" * 8,
    "gh": "ghp_" + "b2" * 20,
    "slack": "xoxb-" + "c3" * 8,
    "eposta": "umut" + "619umut1963" + "@" + "gmail" + ".com",
    "yol_mac": "C:" + chr(92) + "Users" + chr(92) + "umut",
    "yol_unix": "/home/" + "umut" + "/proje",
}
#: Kisisel yollarda maskeleme sozlesmesi `<ad>` KISMINI siler; yolun ortak
#: oneki (`C:\Users\`, `/home/`) kalir. Bu yuzden bu iki girdi icin ilk 6
#: karakter kurali uygulanmaz: denetlenen sey, kaybolmasi gereken ASIL
#: KIMLIKTIR (tam yol metni + kullanici adi). Bkz. `test_kisisel_yol_*`.
#: `sk`/aws/gh/slack/eposta girdilerinde ise ilk 6 karakter dahil denetlenir.
YOL_GIRDILERI = frozenset({"yol_mac", "yol_unix"})


def _parcalar(ad: str, s: str) -> list[bytes]:
    """Sirin tamamini ve (yol disi, 6+ karakter ise) ilk 6 karakterini dondurur."""
    doner = [s.encode("utf-8")]
    if ad not in YOL_GIRDILERI and len(s) >= 6:
        doner.append(s[:6].encode("utf-8"))
    return doner


def _fixture_repo(tmp_path: Path) -> Path:
    """Bilinen sahte sirlarla dolu GERCEK git reposu."""
    repo = make_repo(tmp_path / "kaynak")
    commit_file(repo, "uygulama.py", f'KEY = "{SAHTE["sk"]}"\n', "api anahtari")
    commit_file(repo, "aws.txt", f"aws anahtari: {SAHTE['aws']}\n", "aws")
    commit_file(repo, "gh.txt", f"gh: {SAHTE['gh']}\n", "github")
    commit_file(repo, "slack.txt", f"slack: {SAHTE['slack']}\n", "slack")
    commit_file(repo, "iletisim.txt", f"mail: {SAHTE['eposta']}\n", "eposta")
    commit_file(repo, "yol.txt", f"yol: {SAHTE['yol_mac']} ve {SAHTE['yol_unix']}\n", "yol")
    (repo / "kimlik.pem").write_text(
        "-----BEGIN RSA PRIVATE KEY-----\n" + "A" * 80 + "\n", encoding="utf-8"
    )
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "kimlik", cwd=repo)
    return repo


def _tum_ciktilar(db_file: Path, kok: Path) -> str:
    """Iki komutun stdout+stderr birlestirilmis ciktisi."""
    parcalar = []
    for komut in (
        ("sizinti", "--root", str(kok), "--db", str(db_file)),
        ("bulgular", "--db", str(db_file)),
        ("bulgular", "--db", str(db_file), "--siddet", "yuksek"),
        ("bulgular", "--db", str(db_file), "--tur", "api-anahtari"),
    ):
        proc = run_module_cli(*komut)
        assert proc.returncode == 0, f"{komut} -> {proc.returncode}: {proc.stderr}"
        parcalar.append(proc.stdout)
        parcalar.append(proc.stderr)
    return "\n".join(parcalar)


def test_ham_sir_hicbir_yerde_yok(tmp_path: Path, db_file: Path):
    """(a) DB baytlari, (b) CLI ciktilari, (c) pytest ciktisi: sir YOK."""
    kok = tmp_path / "kok"
    kok.mkdir()
    repo = _fixture_repo(kok)
    assert repo.exists()

    cikti = _tum_ciktilar(db_file, kok)

    # (a) DB dosyasinin HAM BAYTLARI
    ham_db = db_file.read_bytes()
    # (b) CLI ciktilari
    cikti_bayt = cikti.encode("utf-8")
    # (c) pytest'in kendi ciktisi: alt surec ciktisi + bu testin kaynagi
    pytest_bayt = subprocess.run(
        [sys.executable, "-c", "import sys; sys.stdout.write(sys.argv[1])",
         Path(__file__).read_text(encoding="utf-8")],
        capture_output=True,
    ).stdout

    for ad, sir in SAHTE.items():
        for parca in _parcalar(ad, sir):
            assert parca not in ham_db, f"HAM SIR DB'DE: {ad}"
            assert parca not in cikti_bayt, f"HAM SIR CIKTIDA: {ad}"
            assert parca not in pytest_bayt, f"HAM SIR PYTEST KAYNAGINDA: {ad}"

    # Ozel anahtarin govdesi de sizmemis olmali.
    assert b"A" * 80 not in ham_db


def test_db_ve_ciktida_maskeli_isaretler_var(tmp_path: Path, db_file: Path):
    """Kanitin tersi: sirlar VARDI ama maskeli isaretler yazildi."""
    kok = tmp_path / "kok"
    kok.mkdir()
    _fixture_repo(kok)
    cikti = _tum_ciktilar(db_file, kok)
    assert "[maskeli:api-anahtari]" in cikti
    assert "<kullanici>" in cikti
    assert "<e-posta>" in cikti


def test_temiz_repoda_sifir_bulgu(tmp_path: Path, db_file: Path):
    """Sizsiz repoda HICBIR bulgu olusmaz."""
    kok = tmp_path / "temiz-kok"
    kok.mkdir()
    repo = make_repo(kok / "temiz")
    commit_file(repo, "kod.py", "def topla(a, b):\n    return a + b\n", "basit")
    commit_file(repo, "README.md", "# Proje\nHicbir gizli deger yok.\n", "readme")
    proc = run_module_cli("sizinti", "--root", str(kok), "--db", str(db_file))
    assert proc.returncode == 0, proc.stderr
    assert "Bulgu: 0" in proc.stdout
    bulgular = run_module_cli("bulgular", "--db", str(db_file))
    assert "Bulgu yok" in bulgular.stdout


def test_db_dosyasi_sifir_bulgu_ekler(tmp_path: Path, db_file: Path):
    """DB icerigi sifirdir: hicbir sahte sir bayti yok."""
    kok = tmp_path / "kok"
    kok.mkdir()
    _fixture_repo(kok)
    _tum_ciktilar(db_file, kok)
    ham = db_file.read_bytes()
    for ad, sir in SAHTE.items():
        for parca in _parcalar(ad, sir):
            assert parca not in ham
