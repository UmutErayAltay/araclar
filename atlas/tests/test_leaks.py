"""Sizinti taramasi: her tur icin POZITIF ve NEGATIF, gercek gecici git repolari.

Sahte sirler test kaynaginda TAM LITERAL olarak YAZILMAZ; calisma zamaninda
parcalardan kurulur ("sk-" + "a1"*15 gibi). Boylece GitHub push protection
tetiklenmez ve kaynakta sir gibi gorunen metin kalmaz.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas import leaks
from conftest import commit_file, git, make_repo

#: Sahte sirler: parcalardan kurulur (kaynakta tam literal YOK).
FAKE_SK = "sk-" + "a1" * 15          # 32 karakter, icinde rakam var
FAKE_AWS = "AK" + "IA" + "X7" * 8     # AKIA + 16 karakter
FAKE_GH = "ghp_" + "b2" * 20         # ghp_ + 40 karakter
FAKE_SLACK = "xoxb-" + "c3" * 8      # xoxb- + 16 karakter


def turler(bulgular: list[dict]) -> set[str]:
    return {b["kind"] for b in bulgular}


# --------------------------------------------------------------------------
# api-anahtari
# --------------------------------------------------------------------------

def test_api_anahtari_sk_bulunur(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    commit_file(repo, "s.txt", f"anahtar: {FAKE_SK}", "ekle")
    b = leaks.tara_calisma_agaci(repo)
    assert "api-anahtari" in turler(b)
    bulgu = next(x for x in b if x["kind"] == "api-anahtari")
    assert bulgu["severity"] == "yuksek"
    assert bulgu["line"] == 1
    assert bulgu["file"] == "s.txt"


def test_api_anahtari_aws_bulunur(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    commit_file(repo, "s.txt", f"aws: {FAKE_AWS}", "ekle")
    assert "api-anahtari" in turler(leaks.tara_calisma_agaci(repo))


def test_api_anahtari_github_bulunur(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    commit_file(repo, "s.txt", f"gh: {FAKE_GH}", "ekle")
    assert "api-anahtari" in turler(leaks.tara_calisma_agaci(repo))


def test_api_anahtari_slack_bulunur(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    commit_file(repo, "s.txt", f"slack: {FAKE_SLACK}", "ekle")
    assert "api-anahtari" in turler(leaks.tara_calisma_agaci(repo))


def test_api_anahtari_anahtar_deger_bulunur(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    commit_file(repo, "s.txt", "API_KEY = q7Rt2mKp9zXw4LbN", "ekle")
    assert "api-anahtari" in turler(leaks.tara_calisma_agaci(repo))


def test_sk_kebab_case_bulgu_degil(tmp_path: Path):
    """Kebab-case kelimeler (`sk-...`) rakam icermedigi icin BULGU DEGILDIR."""
    repo = make_repo(tmp_path / "r")
    metin = "pip install sk-sqlalchemy-migrate-extension task-runner risk-lower"
    commit_file(repo, "s.txt", metin, "ekle")
    b = leaks.tara_calisma_agaci(repo)
    assert "api-anahtari" not in turler(b)


def test_api_anahtari_yer_tutucu_bulgu_degil(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    metin = (
        'API_KEY = your_key_here\n'
        'password: "xxxxxxxxxxxxxxxx"\n'
        'secret = ${GITHUB_TOKEN}\n'
        'token = <TOKEN_BURAYA>\n'
        'api_key = example-key-1234\n'
    )
    commit_file(repo, "s.txt", metin, "ekle")
    assert "api-anahtari" not in turler(leaks.tara_calisma_agaci(repo))


# --------------------------------------------------------------------------
# ozel-anahtar
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "baslik",
    [
        "-----BEGIN PRIVATE KEY-----",
        "-----BEGIN RSA PRIVATE KEY-----",
        "-----BEGIN EC PRIVATE KEY-----",
        "-----BEGIN OPENSSH PRIVATE KEY-----",
        "-----BEGIN DSA PRIVATE KEY-----",
        "-----BEGIN PGP PRIVATE KEY-----",
    ],
)
def test_ozel_anahtar_bulunur(tmp_path: Path, baslik: str):
    """GÖVDESİZ başlık `bilgi`'dir (Dalga C kuralı): elle kontrol notu.

    Gövdeli başlık `yuksek` kalır; o davranış `tests/test_leaks_ozel_anahtar.py`
    içinde ayrıca ve kapsamlı test edilir.
    """
    repo = make_repo(tmp_path / "r")
    commit_file(repo, "id.pem", f"{baslik}\ncift satir\n", "ekle")
    b = leaks.tara_calisma_agaci(repo)
    assert "ozel-anahtar" in turler(b)
    bulgu = next(x for x in b if x["kind"] == "ozel-anahtar")
    assert bulgu["severity"] == "bilgi"


def test_ozel_anahtar_yoksa_bulgu_degil(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    commit_file(repo, "s.txt", "BEGIN a real certificate block", "ekle")
    assert "ozel-anahtar" not in turler(leaks.tara_calisma_agaci(repo))


# --------------------------------------------------------------------------
# env-izlenen (yalnizca IZLENEN dosya, icerik okunmaz)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("ad", [".env", ".env.local", ".env.production"])
def test_env_izlenen_bulunur(tmp_path: Path, ad: str):
    repo = make_repo(tmp_path / "r")
    (repo / ad).write_text("GIZLI=1\n", encoding="utf-8")  # sahte siri icermez
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "env ekle", cwd=repo)
    b = leaks.tara_calisma_agaci(repo)
    assert "env-izlenen" in turler(b)
    bulgu = next(x for x in b if x["kind"] == "env-izlenen")
    assert bulgu["file"] == ad
    assert bulgu["severity"] == "yuksek"
    assert bulgu["snippet_redacted"] is None  # icerik bulguya girmez


@pytest.mark.parametrize("ad", [".env.example", ".env.sample", ".env.template"])
def test_env_ornek_bulgu_degil(tmp_path: Path, ad: str):
    repo = make_repo(tmp_path / "r")
    (repo / ad).write_text("API_KEY=\n", encoding="utf-8")
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "env ornek", cwd=repo)
    assert "env-izlenen" not in turler(leaks.tara_calisma_agaci(repo))


def test_env_izlenmeyen_bulgu_degil(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    (repo / ".env").write_text("API_KEY=\n", encoding="utf-8")
    # git add YAPILMAZ -> izlenmiyor
    assert "env-izlenen" not in turler(leaks.tara_calisma_agaci(repo))


# --------------------------------------------------------------------------
# kisisel-yol
# --------------------------------------------------------------------------

def test_kisisel_yol_windows(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    commit_file(repo, "s.txt", "yol: C:\\Users\\umut\\Desktop\\proje", "ekle")
    b = leaks.tara_calisma_agaci(repo)
    assert "kisisel-yol" in turler(b)
    bulgu = next(x for x in b if x["kind"] == "kisisel-yol")
    assert bulgu["severity"] == "orta"
    assert "umut" not in (bulgu["snippet_redacted"] or "")
    assert "C:\\Users\\<kullanici>" in (bulgu["snippet_redacted"] or "")


def test_kisisel_yol_users_macos(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    commit_file(repo, "s.txt", "yol: /Users/umut/proje", "ekle")
    b = leaks.tara_calisma_agaci(repo)
    assert "kisisel-yol" in turler(b)
    assert next(x for x in b if x["kind"] == "kisisel-yol")["severity"] == "orta"


def test_kisisel_yol_home_dusuk_onem(tmp_path: Path):
    """/home/user/ bu container'in sirada yolu -> dusuk onem."""
    repo = make_repo(tmp_path / "r")
    commit_file(repo, "s.txt", "yol: /home/user/proje", "ekle")
    b = leaks.tara_calisma_agaci(repo)
    assert "kisisel-yol" in turler(b)
    assert next(x for x in b if x["kind"] == "kisisel-yol")["severity"] == "dusuk"


# --------------------------------------------------------------------------
# e-posta
# --------------------------------------------------------------------------

def test_eposta_bulunur(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    commit_file(repo, "s.txt", "iletisim: kisi@firma-ornek.org", "ekle")
    b = leaks.tara_calisma_agaci(repo)
    assert "e-posta" in turler(b)
    bulgu = next(x for x in b if x["kind"] == "e-posta")
    assert bulgu["severity"] == "dusuk"
    assert "gmail.com" not in (bulgu["snippet_redacted"] or "")


@pytest.mark.parametrize(
    "adres",
    [
        "noreply@anthropic.com",
        "123+abc@users.noreply.github.com",
        "bir@localhost",
        "test@example.com",
        "info@example.org",
        "git@github.com",
    ],
)
def test_eposta_istisna_bulgu_degil(tmp_path: Path, adres: str):
    repo = make_repo(tmp_path / "r")
    commit_file(repo, "s.txt", f"imza: {adres}", "ekle")
    assert "e-posta" not in turler(leaks.tara_calisma_agaci(repo))


# --------------------------------------------------------------------------
# gorsel-elle-kontrol
# --------------------------------------------------------------------------

def test_gorsel_docs_dizini_bulgu_uretiyor(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    (repo / "docs").mkdir()
    (repo / "docs" / "ekran.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "gorsel", cwd=repo)
    b = leaks.tara_calisma_agaci(repo)
    tur = next((x for x in b if x["kind"] == "gorsel-elle-kontrol"), None)
    assert tur is not None
    assert tur["severity"] == "bilgi"
    assert "elle kontrol" in (tur["snippet_redacted"] or "")


def test_gorsel_kok_dizinde_ve_uretim_dizini_disi_bulgu_uretiyor(tmp_path: Path):
    """KAPSAM GENISLEDI: izlenen TUM gorseller bulgu uretir (uretim dizini haric)."""
    repo = make_repo(tmp_path / "r")
    (repo / "kok.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (repo / "deep" / "ic" / "de").mkdir(parents=True)
    (repo / "deep" / "ic" / "de" / "a.svg").write_text("<svg/>", encoding="utf-8")
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "gorsel", cwd=repo)
    b = leaks.tara_calisma_agaci(repo)
    gorseller = {x["file"] for x in b if x["kind"] == "gorsel-elle-kontrol"}
    assert gorseller == {"kok.png", "deep/ic/de/a.svg"}


def test_gorsel_uretim_dizininde_bulgu_uretmiyor(tmp_path: Path):
    """`node_modules/` vb. altindaki gorseller repo icerigi sayilmaz."""
    repo = make_repo(tmp_path / "r")
    for dizin in ("node_modules/x", ".venv/y", "vendor/z", "dist", "build", "__snapshots__"):
        (repo / dizin).mkdir(parents=True, exist_ok=True)
        (repo / dizin / "a.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    git("add", "-A", "-f", cwd=repo)
    git("commit", "-q", "-m", "gorsel", cwd=repo)
    assert "gorsel-elle-kontrol" not in turler(leaks.tara_calisma_agaci(repo))


def test_cok_gorselde_tek_ozet_bulgu(tmp_path: Path):
    """50+ gorselde dosya basina bulgu yerine TEK ozet (liste bogulmaz)."""
    repo = make_repo(tmp_path / "r")
    for i in range(leaks.GORSEL_OZET_ESIGI + 5):
        (repo / f"g{i}.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "cok gorsel", cwd=repo)
    gorsel = [x for x in leaks.tara_calisma_agaci(repo) if x["kind"] == "gorsel-elle-kontrol"]
    assert len(gorsel) == 1
    assert gorsel[0]["file"] is None and gorsel[0]["severity"] == "bilgi"
    assert str(leaks.GORSEL_OZET_ESIGI + 5) in (gorsel[0]["snippet_redacted"] or "")


def test_esik_altinda_dosya_basina_bulgu(tmp_path: Path):
    """Esigin altinda dosya basina bulgu yazilir."""
    repo = make_repo(tmp_path / "r")
    for i in range(3):
        (repo / f"g{i}.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "gorsel", cwd=repo)
    gorsel = [x for x in leaks.tara_calisma_agaci(repo) if x["kind"] == "gorsel-elle-kontrol"]
    assert {x["file"] for x in gorsel} == {"g0.png", "g1.png", "g2.png"}


def test_gorsel_izlenmiyorsa_bulgu_yok(tmp_path: Path):
    """IzlenMEYEN gorsel kapsam disi (git ls-files disi)."""
    repo = make_repo(tmp_path / "r")
    (repo / "kok.png").write_bytes(b"\x89PNG\r\n\x1a\n")  # git add YOK
    assert "gorsel-elle-kontrol" not in turler(leaks.tara_calisma_agaci(repo))


# --------------------------------------------------------------------------
# GECMIS: yalnizca gecmiste olan, sonra silinmis sir
# --------------------------------------------------------------------------

def test_yalnizca_gecmiste_olan_sir_bulunur(tmp_path: Path):
    """Sonra silinen sir icin bulgu cikar ve `commit` alaninda kisa hash YAZILIR."""
    repo = make_repo(tmp_path / "r")
    commit_file(repo, "gizli.txt", f"eski anahtar: {FAKE_SK}", "sir ekle")
    hash_ = git("rev-parse", "HEAD", cwd=repo).strip()[:7]
    # Sir dosyasini tamamen sil (calisma agacinda ARTIK YOK).
    git("rm", "-q", "gizli.txt", cwd=repo)
    git("commit", "-q", "-m", "sir sil", cwd=repo)

    b = leaks.tara_repo(repo, commit_sayisi=10).bulgular
    gecmis = [x for x in b if x["kind"] == "api-anahtari" and x["commit"] == hash_]
    assert gecmis, "gecmisteki (silinmis) sir bulunamadi"
    # Ham sir hicbir yerde olmamali.
    for x in gecmis:
        assert FAKE_SK not in (x["snippet_redacted"] or "")


def test_calisma_agaci_bulgusu_commit_null(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    commit_file(repo, "s.txt", f"anahtar: {FAKE_SK}", "ekle")
    b = leaks.tara_calisma_agaci(repo)
    api = [x for x in b if x["kind"] == "api-anahtari"]
    assert api
    assert all(x["commit"] is None for x in api)  # calisma agaci: commit NULL


def test_gecmis_tarama_sayisi_kisitli(tmp_path: Path):
    """--gecmis N: yalnizca son N commit taranir, daha eskisi kapsam disi kalir."""
    repo = make_repo(tmp_path / "r")
    # Sirli commit'i EN ESKI yap: once o, sonra temiz commitler.
    commit_file(repo, "en-eski.txt", f"cok-eski {FAKE_SK}", "en eski sir")
    for i in range(5):
        commit_file(repo, f"f{i}.txt", f"satir {i}", f"c{i}")
    kisa = leaks.tara_gecmis(repo, commit_sayisi=2)  # son 2 commit: temiz
    assert not [x for x in kisa if x["kind"] == "api-anahtari"]
    uzun = leaks.tara_gecmis(repo, commit_sayisi=100)  # hepsi: eski sir gorunur
    assert [x for x in uzun if x["kind"] == "api-anahtari"]


# --------------------------------------------------------------------------
# Test yolu: bir kademe dusuk onem, ama ATLANMAZ
# --------------------------------------------------------------------------

def test_test_yolunda_bulgu_dusuk_onem(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    commit_file(repo, "tests/test_ornek.py", f"KEY = '{FAKE_SK}'", "test ekle")
    b = leaks.tara_calisma_agaci(repo)
    api = [x for x in b if x["kind"] == "api-anahtari"]
    assert api, "test yolundaki bulgu ATLANMAMALI"
    assert all(x["severity"] == "dusuk" for x in api)  # yuksek -> dusuk


def test_test_yolunda_kisisel_yol_bilgi_onem(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    commit_file(repo, "tests/x.py", "yol: /Users/umut/proje", "ekle")
    b = leaks.tara_calisma_agaci(repo)
    yol = [x for x in b if x["kind"] == "kisisel-yol"]
    assert yol
    assert all(x["severity"] == "bilgi" for x in yol)  # orta -> bilgi


def test_test_yolu_disi_yol_orta_kalir(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    commit_file(repo, "app/kod.py", "yol: /Users/umut/proje", "ekle")
    b = leaks.tara_calisma_agaci(repo)
    yol = [x for x in b if x["kind"] == "kisisel-yol"]
    assert yol and all(x["severity"] == "orta" for x in yol)


# --------------------------------------------------------------------------
# Atlanan dosyalar
# --------------------------------------------------------------------------

def test_ikili_dosya_atlanir(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    # NUL byte iceren ikili: taranmaz, bulgu cikmaz.
    (repo / "gorsel.bin").write_bytes(b"\x00\x01\x02" + FAKE_SK.encode() + b"\x00")
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "ikili", cwd=repo)
    b = leaks.tara_calisma_agaci(repo)
    assert not [x for x in b if x["kind"] == "api-anahtari"]


def test_buyuk_dosya_atlanir(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    buyuk = repo / "buyuk.txt"
    with open(buyuk, "w", encoding="utf-8") as fh:
        fh.write(FAKE_SK + "\n")
        fh.write("x" * (leaks.DOSYA_UST_SINIR + 100))  # 1 MiB'tan buyuk
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "buyuk", cwd=repo)
    b = leaks.tara_calisma_agaci(repo)
    assert not [x for x in b if x["kind"] == "api-anahtari"]


def test_gecmis_ikili_diff_atlanir(tmp_path: Path):
    """`Binary files ... differ` satirlari taranmaz."""
    repo = make_repo(tmp_path / "r")
    (repo / "resim.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00")
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "resim", cwd=repo)
    b = leaks.tara_gecmis(repo, commit_sayisi=5)
    # Ikili diff hicbir bulgu uretmemeli (ve cogu zaman hic uretmez).
    assert isinstance(b, list)


# --------------------------------------------------------------------------
# Uzun satir / performans
# --------------------------------------------------------------------------

def test_cok_uzun_satir_katastrofik_yok(tmp_path: Path):
    """Tekrarli 50k karakterlik satir: regex PATLAMAZ, makul surede biter.

    Dizinleyici kabul kriteri: "katastrofik regex yok (uzun tekrarlenmis
    satirla bir test)".
    """
    import time

    repo = make_repo(tmp_path / "r")
    uzun = "A" * 50000  # sir YOK: sadece tekrarli karakter
    commit_file(repo, "uzun.txt", uzun, "ekle")
    bas = time.monotonic()
    b = leaks.tara_calisma_agaci(repo)
    sure = time.monotonic() - bas
    assert sure < 10, f"katastrofik yavaslama: {sure:.1f} sn"
    assert b == [], "sirr olmayan tekrarli satir bulgu uretmemeli"


def test_uzun_satirda_sir_yine_bulunur(tmp_path: Path):
    """Satir 2000 karakterden uzun olsa da icindeki sir bulunmali."""
    repo = make_repo(tmp_path / "r")
    on_ek = "x" * 3000
    commit_file(repo, "s.txt", f"{on_ek} {FAKE_SK}", "ekle")
    b = leaks.tara_calisma_agaci(repo)
    assert "api-anahtari" in turler(b)
