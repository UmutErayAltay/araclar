"""Dalga D / `atlas readme`: README bayatlığı — GERÇEK geçici git repolarıyla.

Hicbir mock yok: her test `tmp_path` altında gerçek bir repo kurar, gerçek
commit atar ve `readme_stale` kendisi okur. Kapsanan davranışlar:

  * davranış commit'i, yalnızca-doc commit, `docs:` önekli KOD commit'i
  * Türkçe mesajlı KOD commit'i ("Dalga C: …") sayılır (anahtar kelime şart değil)
  * `tests/`, `docs/`, `examples/`, `.github/` altı değişiklik sayılmaz
  * README/CHANGELOG/LICENSE dosyaları kod sayılmaz
  * merge commit sayılmaz
  * README'siz repo, commit'lenmemiş README, boş repo, kabuk klon
  * görsel referansı: var / eksik / `..` kaçışı / http / data:
  * görsel yaşı hesabı, eşik sınırları (skor 2/3/7/8), sıralama
  * sınır (2000 commit) davranışı
  * şema göçü: eski DB veri kaybetmeden yükselir
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from conftest import commit_file, git, make_repo, run_module_cli, tree_hash

from atlas import db as db_mod
from atlas import readme_stale as rs

#: Commit tarihleri deterministik olsun diye `conftest.GIT_ENV` sabit tarihi
#: kullanır; görsel yaşı testleri kendi tarihli commit'lerini kurar.


def gun_geri(gun: int) -> str:
    """`gun` gün önceki ISO tarihi (git `GIT_*_DATE` için)."""
    return (datetime.now(timezone.utc) - timedelta(days=gun)).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def tarihli_commit(repo: Path, ad: str, icerik: str, mesaj: str, gun: int) -> None:
    """Verilen gün eski tarihli bir commit atar (görsel yaşı testi için)."""
    import os

    env = dict(os.environ)
    from conftest import GIT_ENV

    env.update(GIT_ENV)
    env["GIT_AUTHOR_DATE"] = gun_geri(gun)
    env["GIT_COMMITTER_DATE"] = gun_geri(gun)
    (repo / ad).parent.mkdir(parents=True, exist_ok=True)
    (repo / ad).write_text(icerik, encoding="utf-8")
    git("add", "-A", cwd=repo)
    import subprocess

    subprocess.run(
        ["git", "-c", "user.email=test@example.invalid", "-c", "user.name=atlas test",
         "commit", "-q", "-m", mesaj],
        cwd=str(repo), capture_output=True, text=True, env=env, check=True,
    )


# --------------------------------------------------------------------------
# Kod dosyası / mesaj öneki sınıflandırması
# --------------------------------------------------------------------------


@pytest.mark.parametrize("dosya", [
    "app.py", "a/b/c.ts", "x.tsx", "y.jsx", "main.go", "lib.rs", "K.java",
    "B.kt", "a.c", "a.cc", "a.cpp", "a.h", "a.hpp", "a.cs", "a.rb", "a.php",
    "run.sh", "q.sql", "i.html", "s.css", "v.vue", "c.svelte",
])
def test_kod_dosyasi_kabul(dosya: str):
    assert rs.kod_dosyasi_mi(dosya) is True


@pytest.mark.parametrize("dosya", [
    "README.md", "docs/index.md", "CHANGELOG.md", "LICENSE", "notes.txt",
    "Makefile", "config.toml", "data.csv", "image.png", "a/b/c.json",
])
def test_kod_dosyasi_red(dosya: str):
    assert rs.kod_dosyasi_mi(dosya) is False


@pytest.mark.parametrize("dosya", [
    "tests/test_x.py", "test/test_x.py", "docs/app.js", "examples/demo.py",
    ".github/workflows/ci.yml", "src/tests/helper.py", "a/docs/b.ts",
])
def test_kod_disi_dizin_kod_sayilmaz(dosya: str):
    assert rs.kod_dosyasi_mi(dosya) is False


def test_kod_dosyasi_yol_normalizasyonu():
    """Windows ayracı `\\` ve `./` öneki de normalize edilir."""
    assert rs.kod_dosyasi_mi("a\\b\\c.py") is True
    assert rs.kod_dosyasi_mi("./a.py") is True
    assert rs.kod_dosyasi_mi("") is False
    assert rs.kod_dosyasi_mi("   ") is False


@pytest.mark.parametrize("mesaj", [
    "docs: duzelt", "chore: bitti", "style: bicim", "test: ekle", "ci: hizala",
    "DOCS: buyuk harf", "Docs (api): kapsamli", "chore(deps): yukselt",
])
def test_harici_onek_eslesir(mesaj: str):
    assert rs.harici_onek_mi(mesaj) is True


@pytest.mark.parametrize("mesaj", [
    "fix: duzelt", "feat: ekle", "Dalga C: web paneli", "A.1: unpushed NULL",
    "refactor: sadelestir", "initial commit", "ilk", "", "  ", "testable: yaz",
    "choreography: dans", "stiles: boya",
])
def test_harici_onek_eslesmez(mesaj: str):
    assert rs.harici_onek_mi(mesaj) is False


# --------------------------------------------------------------------------
# Eşikler (sabit; kilitlenir)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("skor,seviye", [
    (0, "taze"), (1, "taze"), (2, "taze"),
    (3, "eskiyor"), (4, "eskiyor"), (6, "eskiyor"), (7, "eskiyor"),
    (8, "bayat"), (9, "bayat"), (20, "bayat"), (999, "bayat"),
])
def test_seviye_esikleri(skor: int, seviye: str):
    assert rs.seviye_hesapla(skor) == seviye


def test_esikler_belgede_sabit():
    """Eşikler 3 ve 8; dokümanla aynı olmalı (README ile senkron)."""
    assert rs.TAZE_UST_SINIR == 3
    assert rs.ESKIYOR_UST_SINIR == 8
    assert "skor < 3" in rs.__doc__
    assert "skor >= 8" in rs.__doc__


def test_esik_sinirlari_gercek_repodan(tmp_path: Path):
    """Gerçek repo ile: 2 davranış commit'i 'taze', 8'i 'bayat'."""
    kok = tmp_path / "kok"
    kok.mkdir()
    for adet, beklenen in ((2, "taze"), (3, "eskiyor"), (7, "eskiyor"), (8, "bayat")):
        repo = make_repo(kok / f"r{adet}")
        for i in range(adet):
            commit_file(repo, f"m{i}.py", f"# {i}\n", f"is {i}")
        assert rs.tara_repo(repo).seviye == beklenen, f"{adet} commit: {beklenen}"


# --------------------------------------------------------------------------
# Tarama: gerçek repolar
# --------------------------------------------------------------------------


def test_davranis_commit_sayilir(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    for i in range(4):
        commit_file(repo, f"m{i}.py", f"# {i}\n", f"is {i}")
    durum = rs.tara_repo(repo)
    assert durum.davranis_commit == 4
    assert durum.seviye == "eskiyor"
    assert durum.tarandi is True
    assert durum.neden is None


def test_turkce_mesajli_kod_commit_sayilir(tmp_path: Path):
    """Anahtar kelime (fix|feat) ŞART DEĞİL: Türkçe mesaj da sayılır."""
    repo = make_repo(tmp_path / "r")
    commit_file(repo, "a.py", "# a\n", "Dalga C: salt-okunur web paneli")
    commit_file(repo, "b.ts", "# b\n", "A.1: unpushed NULL olur")
    durum = rs.tara_repo(repo)
    assert durum.davranis_commit == 2, "Türkçe mesajlı kod commit'leri kaçırıldı"


def test_docs_oneski_kod_commit_sayilmaz(tmp_path: Path):
    """`docs:`/`chore:` öneki olan commit KOD değiştirse bile davranış DEĞİLDİR.

    Ölçüm README'nin SON DEĞİŞTİĞİ commit'ten başlar; bu yüzden README
    ayrı bir commit ile eklenir ve önekli commit'ler ONDAN SONRA gelir.
    """
    repo = make_repo(tmp_path / "r", filename="NOT.md")
    commit_file(repo, "README.md", "# r\n", "readme")
    commit_file(repo, "b.py", "# b\n", "docs: kod yorumu")
    commit_file(repo, "c.py", "# c\n", "chore(bicim): bosluk")
    commit_file(repo, "d.py", "# d\n", "fix: gercek")
    assert rs.tara_repo(repo).davranis_commit == 1, "docs/chore onekli kod commit'leri sayildi"


def test_yalnizca_doc_commit_sayilmaz(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    commit_file(repo, "a.md", "# a\n", "belge")
    commit_file(repo, "b.txt", "b\n", "not")
    commit_file(repo, "c.png", "x", "gorsel")
    assert rs.tara_repo(repo).davranis_commit == 0
    assert rs.tara_repo(repo).seviye == "taze"


def test_tests_dizini_degisikligi_sayilmaz(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    commit_file(repo, "tests/test_a.py", "# t\n", "test ekle")
    commit_file(repo, "docs/kullanim.md", "# k\n", "kullanim")
    commit_file(repo, "examples/ornek.py", "# o\n", "ornek")
    commit_file(repo, ".github/workflows/ci.yml", "on: push\n", "ci")
    assert rs.tara_repo(repo).davranis_commit == 0


def test_readme_dosyasi_kod_sayilmaz(tmp_path: Path):
    """README'nin kendisine dokunan commit davranış SAYILMAZ."""
    repo = make_repo(tmp_path / "r")
    for i in range(3):
        commit_file(repo, "farkli.md", f"# {i}\n", f"not {i}")
        commit_file(repo, "CHANGELOG.md", f"# {i}\n", f"degis {i}")
        commit_file(repo, "LICENSE", f"lisans {i}\n", f"lisans {i}")
    assert rs.tara_repo(repo).davranis_commit == 0, "README/CHANGELOG/LICENSE kod sayilmamali"


def test_readme_commit_ten_sonra_sayilir(tmp_path: Path):
    """README commit'inden ÖNCEki kod commit'leri SAYILMAZ."""
    repo = tmp_path / "r"
    repo.mkdir()
    git("init", "-q", "-b", "main", str(repo))
    commit_file(repo, "a.py", "# a\n", "kod once")
    (repo / "README.md").write_text("# r\n", encoding="utf-8")
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "readme eklendi", cwd=repo)
    commit_file(repo, "b.py", "# b\n", "kod sonra")
    durum = rs.tara_repo(repo)
    assert durum.davranis_commit == 1, "onceki kod commit'i sayildi"
    assert durum.readme_yolu == "README.md"
    assert durum.readme_commit


def test_merge_commit_sayilmaz(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    git("checkout", "-q", "-b", "yan", cwd=repo)
    commit_file(repo, "y.py", "# y\n", "yan dal")
    git("checkout", "-q", "main", cwd=repo)
    commit_file(repo, "m.py", "# m\n", "main is")
    git("merge", "--no-ff", "-q", "-m", "birlesik", "yan", cwd=repo)
    commit_file(repo, "z.py", "# z\n", "son is")
    durum = rs.tara_repo(repo)
    # `birlesik` merge commit'i sayilmaz; diger 3 kod commit'i sayilir.
    assert durum.davranis_commit == 3, f"merge sayildi: {durum.davranis_commit}"


def test_readmesiz_repo(tmp_path: Path):
    repo = tmp_path / "r"
    repo.mkdir()
    git("init", "-q", "-b", "main", str(repo))
    commit_file(repo, "a.py", "# a\n", "kod")
    durum = rs.tara_repo(repo)
    assert durum.seviye == "yok"
    assert durum.neden == rs.NEDEN_README_YOK
    assert durum.tarandi is True


def test_commitlenmemis_readme(tmp_path: Path):
    """README VAR ama commit'lenmemis → seviye 'yok', readme_commit NULL."""
    repo = make_repo(tmp_path / "r", commit=False)
    commit_file(repo, "a.py", "# a\n", "ilk kod")
    (repo / "README.md").write_text("# commitlenmedi\n", encoding="utf-8")
    durum = rs.tara_repo(repo)
    assert durum.seviye == "yok", f"commit'lenmemis README 'yok' olmali, {durum}"
    assert durum.readme_commit is None
    assert durum.neden == rs.NEDEN_README_COMMITLENMEMIS
    assert durum.readme_yolu == "README.md"


def test_bos_repo_hata_firlatmaz(tmp_path: Path):
    repo = tmp_path / "bos"
    repo.mkdir()
    git("init", "-q", "-b", "main", str(repo))
    durum = rs.tara_repo(repo)
    assert durum.seviye is None
    assert durum.neden == rs.NEDEN_BOS_REPO
    assert durum.tarandi is False


def test_kabuk_klon_hata_firlatmaz(tmp_path: Path):
    """`.git` dizini olmayan dizin: kabuk klon → seviye None, neden dolu."""
    repo = tmp_path / "kabuk"
    repo.mkdir()
    (repo / "a.py").write_text("# a\n", encoding="utf-8")
    durum = rs.tara_repo(repo)
    assert durum.seviye is None
    assert durum.neden == rs.NEDEN_KABUK_KLON
    assert durum.tarandi is False


def test_ilk_bulunan_readme_kazanir(tmp_path: Path):
    """README.md yoksa README.rst; sıra `README_ADLARI` ile bellidir."""
    repo = tmp_path / "r"
    repo.mkdir()
    git("init", "-q", "-b", "main", str(repo))
    (repo / "README.rst").write_text("rst\n", encoding="utf-8")
    (repo / "README.txt").write_text("txt\n", encoding="utf-8")
    commit_file(repo, "a.py", "# a\n", "kod")
    durum = rs.tara_repo(repo)
    assert durum.readme_yolu == "README.rst", "en fazla .rst secilmeli"


def test_tarama_salt_okunur(tmp_path: Path):
    """Tarama repoyu bayt bayt DEĞİŞTİRMEZ."""
    repo = make_repo(tmp_path / "r")
    for i in range(3):
        commit_file(repo, f"m{i}.py", f"# {i}\n", f"is {i}")
    once = tree_hash(repo)
    rs.tara_repo(repo)
    assert tree_hash(repo) == once, "readme taramasi repoyu degistirdi"


def test_yeni_git_alt_komutu_talep_edilmez():
    """readme_stale SADECE `log`/`ls-files` kullanir; izin listesi degismez."""
    from atlas.scan import ALLOWED_GIT_SUBCOMMANDS

    assert {"log", "ls-files"} <= ALLOWED_GIT_SUBCOMMANDS
    assert ALLOWED_GIT_SUBCOMMANDS == frozenset(
        {"status", "log", "rev-parse", "rev-list", "symbolic-ref", "remote",
         "for-each-ref", "ls-files"}
    ), "izin listesi DEGISTI"


# --------------------------------------------------------------------------
# Görsel referansları
# --------------------------------------------------------------------------


def test_gorsel_yollari_çıkarımı():
    metin = (
        "![a](docs/a.png)\n"
        "![b](docs/b.png 'baslik')\n"
        '<img src="docs/c.png" alt="x">\n'
        "![d](https://ornek.invalid/d.png)\n"
        "![e](data:image/png;base64,AAA)\n"
        "![f](#bolum)\n"
        "![g](docs/a.png)\n"  # tekrar
    )
    yollar = rs.gorsel_yollari(metin)
    assert "docs/a.png" in yollar
    assert "docs/b.png" in yollar
    assert "docs/c.png" in yollar
    assert "https://ornek.invalid/d.png" not in yollar, "http disarida kalmali"
    assert not any(y.startswith("data:") for y in yollar), "data: disarida kalmali"
    assert "#bolum" not in yollar
    assert yollar.count("docs/a.png") == 1, "tekrar eden yol bir kez yazilmali"


def test_repo_icinde_mi_kaçış_reddi(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    assert rs.repo_icinde_mi(repo, "docs/a.png") is True
    assert rs.repo_icinde_mi(repo, "./a.png") is True
    assert rs.repo_icinde_mi(repo, "../komsu/a.png") is False, ".. kaçışı reddedilmeli"
    assert rs.repo_icinde_mi(repo, "../../../etc/passwd") is False


def test_gorsel_yasi_hesaplaniyor(tmp_path: Path):
    """Görsel 120 gün eski, davranış commit'i bugün → yas ~120."""
    repo = tmp_path / "r"
    repo.mkdir()
    git("init", "-q", "-b", "main", str(repo))
    tarihli_commit(repo, "docs/ekran.png", "PNG", "gorsel ekle", 120)
    (repo / "README.md").write_text("# r\n\n![e](docs/ekran.png)\n", encoding="utf-8")
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "readme", cwd=repo)
    tarihli_commit(repo, "a.py", "# a\n", "kod", 0)

    durum = rs.tara_repo(repo)
    assert durum.davranis_commit == 1
    assert durum.screenshot_age_days is not None
    assert 118 <= durum.screenshot_age_days <= 121, durum.screenshot_age_days
    # 120 // 10 = 12 puan + 1 davranış commit = 13 → bayat
    assert durum.skor == 13, durum.skor
    assert durum.seviye == "bayat"


def test_gorsel_yoksa_yas_null(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    for i in range(3):
        commit_file(repo, f"m{i}.py", f"# {i}\n", f"is {i}")
    durum = rs.tara_repo(repo)
    assert durum.screenshot_age_days is None
    assert durum.skor == 3, "gorsel yoksa ek puan YOK"


def test_davranis_commit_yoksa_gorsel_puani_eklenmez(tmp_path: Path):
    """Görsel çok eski AMA davranış commit'i 0 → ek puan EKLENMEZ."""
    repo = tmp_path / "r"
    repo.mkdir()
    git("init", "-q", "-b", "main", str(repo))
    tarihli_commit(repo, "docs/ekran.png", "PNG", "gorsel", 300)
    (repo / "README.md").write_text("# r\n\n![e](docs/ekran.png)\n", encoding="utf-8")
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "readme", cwd=repo)
    durum = rs.tara_repo(repo)
    assert durum.davranis_commit == 0
    assert durum.skor == 0, f"davranis commit 0 iken ek puan eklenmemeli: {durum.skor}"
    assert durum.seviye == "taze"


def test_eksik_gorsel_sayilir(tmp_path: Path):
    """README'de var ama depoda OLMAYAN görsel `eksik_gorsel` olur."""
    repo = make_repo(tmp_path / "r")
    (repo / "README.md").write_text(
        "# r\n\n![yok](docs/yok.png)\n![dis](https://ornek.invalid/x.png)\n", encoding="utf-8"
    )
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "readme", cwd=repo)
    durum = rs.tara_repo(repo)
    assert durum.eksik_gorsel == 1, "yalnizca depoda olmayan yerel gorsel sayilir"
    assert durum.screenshot_age_days is None, "var olan gorsel yok"


def test_kaçış_gorsel_eksik_sayilmaz(tmp_path: Path):
    """`..` ile repo DIŞINA çıkan görsel ne var-olur ne eksik sayılır."""
    repo = make_repo(tmp_path / "r")
    (repo / "README.md").write_text("# r\n\n![k](../disarida.png)\n", encoding="utf-8")
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "readme", cwd=repo)
    durum = rs.tara_repo(repo)
    assert durum.eksik_gorsel == 0, "disari kacan yol 'eksik' SAYILMAMALI"


def test_izlenmeyen_gorsel_eksik_sayilir(tmp_path: Path):
    """Diskte var ama İZLENMEYEN görsel: `ls-files` dışı → eksik sayılır.

    README commit'lenir, görsel `.gitignore` ile DIŞARIDA bırakılır.
    """
    repo = make_repo(tmp_path / "r")
    (repo / ".gitignore").write_text("docs/\n", encoding="utf-8")
    (repo / "docs").mkdir()
    (repo / "docs" / "izlenmeyen.png").write_text("x", encoding="utf-8")
    (repo / "README.md").write_text("# r\n\n![e](docs/izlenmeyen.png)\n", encoding="utf-8")
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "readme", cwd=repo)
    assert rs.tara_repo(repo).eksik_gorsel == 1, "izlenmeyen gorsel 'eksik' sayilmali"


# --------------------------------------------------------------------------
# Sıralama
# --------------------------------------------------------------------------


def test_siralama_skora_azalan(tmp_path: Path):
    kok = tmp_path / "kok"
    kok.mkdir()
    adetler = {"zzz-taze": 1, "aaa-bayat": 9, "mmm-eskiyor": 5, "bbb-taze2": 0}
    for ad, adet in adetler.items():
        repo = make_repo(kok / ad)
        for i in range(adet):
            commit_file(repo, f"m{i}.py", f"# {i}\n", f"is {i}")
    sonuc, _ = rs.tara_roots([kok])
    sirali = rs.sirala(sonuc.values())
    skorlar = [d.skor for d in sirali]
    assert skorlar == sorted(skorlar, reverse=True), skorlar
    assert sirali[0].repo.endswith("aaa-bayat")
    # Eşitlikte ada göre (küçük harf) sıralanır.
    assert sirali[-1].repo.endswith("bbb-taze2")


def test_siralama_yok_ve_bilinmeyen_sonda(tmp_path: Path):
    bos = tmp_path / "bos"
    bos.mkdir()
    git("init", "-q", "-b", "main", str(bos))
    sirali = rs.sirala([rs.tara_repo(bos), rs.tara_repo(make_repo(tmp_path / "r"))])
    assert sirali[0].seviye == "taze"
    assert sirali[-1].seviye is None


# --------------------------------------------------------------------------
# Tarama penceresi (sınır)
# --------------------------------------------------------------------------


def test_tarama_limiti_kucultulurse_sinir_isaretlenir(tmp_path: Path, monkeypatch):
    """Limit 3'e inince pencere dolar → seviye 'sinir', neden 'sinir'."""
    repo = make_repo(tmp_path / "r")
    for i in range(9):
        commit_file(repo, f"m{i}.py", f"# {i}\n", f"is {i}")
    durum = rs.tara_repo(repo)
    assert durum.seviye == "bayat", "9 commit normalde bayat"

    monkeypatch.setattr(rs, "TARAMA_LIMIT", 3)
    sinirli = rs.tara_repo(repo, limit=rs.TARAMA_LIMIT)
    assert sinirli.neden == rs.NEDEN_SINIR
    assert sinirli.seviye == rs.SEVIYE_SINIR
    assert sinirli.skor >= rs.SKOR_ALT_SINIR


# --------------------------------------------------------------------------
# Şema göçü
# --------------------------------------------------------------------------


def test_eski_sema_gocu_veri_kaybolmaz(tmp_path: Path):
    """Dalga D oncesi elle kurulmus DB acilir: veri durur, yeni sutunlar gelir."""
    yol = tmp_path / "eski.db"
    eski = """
    CREATE TABLE repos (
        path TEXT PRIMARY KEY, name TEXT NOT NULL, scanned_at TEXT NOT NULL,
        dirty INTEGER NOT NULL DEFAULT 0, unpushed INTEGER, branch TEXT,
        last_commit_at TEXT, has_remote INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE readme_status (
        repo TEXT PRIMARY KEY, readme_commit TEXT,
        behavior_commits_after INTEGER, screenshot_age_days INTEGER
    );
    CREATE TABLE todos (
        id INTEGER PRIMARY KEY AUTOINCREMENT, repo TEXT NOT NULL,
        file TEXT, line INTEGER, text TEXT
    );
    CREATE TABLE findings (
        id INTEGER PRIMARY KEY AUTOINCREMENT, repo TEXT NOT NULL, kind TEXT NOT NULL,
        severity TEXT, file TEXT, line INTEGER, "commit" TEXT, snippet_redacted TEXT
    );
    """
    conn = sqlite3.connect(str(yol))
    try:
        conn.executescript(eski)
        conn.execute("PRAGMA user_version = 1")
        conn.executemany(
            "INSERT INTO repos (path, name, scanned_at, dirty, unpushed, branch, "
            "last_commit_at, has_remote) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [("/a/bir", "bir", "2024-01-02T03:04:05+00:00", 0, 3, "main",
              "2024-01-02T03:04:05+00:00", 1)],
        )
        conn.execute(
            "INSERT INTO readme_status (repo, readme_commit, behavior_commits_after, "
            "screenshot_age_days) VALUES (?, ?, ?, ?)",
            ("/a/bir", "abc123", 4, 25),
        )
        conn.execute(
            "INSERT INTO todos (repo, file, line, text) VALUES (?, ?, ?, ?)",
            ("/a/bir", "a.py", 3, "# TODO: eski"),
        )
        conn.execute(
            'INSERT INTO findings (repo, kind, severity, file, "commit", snippet_redacted) '
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("/a/bir", "api-anahtari", "yuksek", "a.py", "abc123", "[maskeli:api-anahtari]"),
        )
        conn.commit()
    finally:
        conn.close()

    conn = db_mod.connect(yol)  # GOC burada calisir
    try:
        assert int(conn.execute("PRAGMA user_version").fetchone()[0]) == db_mod.SCHEMA_VERSION
        sutunlar = {r[1] for r in conn.execute("PRAGMA table_info(readme_status)")}
        for ad, _tip in db_mod.README_YENI_SUTUNLAR:
            assert ad in sutunlar, f"yeni sutun eksik: {ad}"
        # Eski satirlar KAYBOLMADI, degerler korundu.
        satir = db_mod.readme_status_for(conn, "/a/bir")
        assert satir is not None, "eski readme satiri kayboldu"
        assert satir["behavior_commits_after"] == 4
        assert satir["screenshot_age_days"] == 25
        assert satir["readme_commit"] == "abc123"
        # Yeni sutunlar NULL (uydurulmadi).
        assert satir["skor"] is None and satir["seviye"] is None
        assert db_mod.count_repos(conn) == 1
        assert db_mod.count_todos(conn) == 1
        assert db_mod.count_findings(conn) == 1
        # Yeni satir artik yazilabilir.
        db_mod.replace_readme_status(conn, [rs.tara_repo(make_repo(tmp_path / "yeni"))])
        assert db_mod.count_readme_status(conn) == 2
    finally:
        conn.close()


def test_goc_idempotent_iki_acilis(tmp_path: Path):
    yol = tmp_path / "a.db"
    repo = make_repo(tmp_path / "r")
    for i in range(2):
        commit_file(repo, f"m{i}.py", f"# {i}\n", f"is {i}")
    db_mod.replace_readme_status(db_mod.connect(yol), [rs.tara_repo(repo)])
    for _ in range(3):
        conn = db_mod.connect(yol)
        try:
            db_mod.replace_readme_status(conn, [rs.tara_repo(repo)])
        finally:
            conn.close()
    conn = db_mod.connect(yol)
    try:
        assert db_mod.count_readme_status(conn) == 1, "cogaltmadi"
    finally:
        conn.close()


# --------------------------------------------------------------------------
# DB katmani
# --------------------------------------------------------------------------


def test_replace_readme_status_atip_yazar(tmp_path: Path):
    db_yol = tmp_path / "a.db"
    repo = make_repo(tmp_path / "r")
    for i in range(5):
        commit_file(repo, f"m{i}.py", f"# {i}\n", f"is {i}")
    conn = db_mod.connect(db_yol)
    try:
        assert db_mod.replace_readme_status(conn, [rs.tara_repo(repo)]) == 1
        ilk = dict(db_mod.readme_status_for(conn, str(repo)))
        assert db_mod.replace_readme_status(conn, [rs.tara_repo(repo)]) == 1
        assert db_mod.count_readme_status(conn) == 1, "ATIP yazmadi"
        assert dict(db_mod.readme_status_for(conn, str(repo))) == ilk, "ATIP ayni olmali"
    finally:
        conn.close()


def test_db_sutunlari_tam_doldurulur(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    for i in range(9):
        commit_file(repo, f"m{i}.py", f"# {i}\n", f"is {i}")
    conn = db_mod.connect(tmp_path / "a.db")
    try:
        db_mod.replace_readme_status(conn, [rs.tara_repo(repo)])
        satir = dict(db_mod.readme_status_for(conn, str(repo)))
        for sutun in db_mod.README_COLUMNS:
            assert sutun in satir
        assert satir["skor"] == 9
        assert satir["seviye"] == "bayat"
        assert satir["behavior_commits_after"] == 9
        assert satir["tarandi"] == 1
        assert satir["readme_yolu"] == "README.md"
    finally:
        conn.close()


def test_seviye_sayaci(tmp_path: Path):
    conn = db_mod.connect(tmp_path / "a.db")
    try:
        db_mod.replace_readme_status(conn, [
            {"repo": "/a", "skor": 9, "seviye": "bayat"},
            {"repo": "/b", "skor": 9, "seviye": "bayat"},
            {"repo": "/c", "skor": 4, "seviye": "eskiyor"},
            {"repo": "/d", "skor": 1, "seviye": "taze"},
            {"repo": "/e", "seviye": "yok"},
        ])
        sayaclar = db_mod.readme_seviye_sayaci(conn)
        assert sayaclar == {"taze": 1, "eskiyor": 1, "bayat": 2, "yok": 1}
    finally:
        conn.close()


def test_list_readme_status_skora_azalan(tmp_path: Path):
    conn = db_mod.connect(tmp_path / "a.db")
    try:
        db_mod.replace_readme_status(conn, [
            {"repo": "/t", "skor": 1, "seviye": "taze"},
            {"repo": "/b", "skor": 9, "seviye": "bayat"},
            {"repo": "/e", "skor": 4, "seviye": "eskiyor"},
        ])
        sirali = [r["repo"] for r in db_mod.list_readme_status(conn)]
        assert sirali == ["/b", "/e", "/t"]
    finally:
        conn.close()


# --------------------------------------------------------------------------
# CLI: `atlas readme`
# --------------------------------------------------------------------------


def test_cli_readme_tablo_basar(tmp_path: Path, db_file: Path):
    kok = tmp_path / "kok"
    kok.mkdir()
    repo = make_repo(kok / "r")
    for i in range(9):
        commit_file(repo, f"m{i}.py", f"# {i}\n", f"is {i}")
    proc = run_module_cli("readme", "--root", str(kok), "--db", str(db_file))
    assert proc.returncode == 0, proc.stderr
    assert "r" in proc.stdout
    assert "bayat" in proc.stdout
    assert "9" in proc.stdout


def test_cli_readme_json(tmp_path: Path, db_file: Path):
    import json

    kok = tmp_path / "kok"
    kok.mkdir()
    repo = make_repo(kok / "r")
    for i in range(3):
        commit_file(repo, f"m{i}.py", f"# {i}\n", f"is {i}")
    proc = run_module_cli("readme", "--root", str(kok), "--db", str(db_file), "--json")
    assert proc.returncode == 0, proc.stderr
    veri = json.loads(proc.stdout)
    assert len(veri) == 1
    assert veri[0]["seviye"] == "eskiyor"
    assert veri[0]["davranis_commit"] == 3


def test_cli_readme_repo_filtresi(tmp_path: Path, db_file: Path):
    kok = tmp_path / "kok"
    kok.mkdir()
    a = make_repo(kok / "aaa")
    b = make_repo(kok / "bbb")
    for i in range(9):
        commit_file(a, f"m{i}.py", "# x\n", f"is {i}")
    proc = run_module_cli("readme", "--root", str(kok), "--db", str(db_file), "--repo", "aaa")
    assert proc.returncode == 0, proc.stderr
    assert "aaa" in proc.stdout and "bbb" not in proc.stdout


def test_cli_readme_salt_okunur(tmp_path: Path, db_file: Path):
    kok = tmp_path / "kok"
    kok.mkdir()
    repo = make_repo(kok / "r")
    for i in range(4):
        commit_file(repo, f"m{i}.py", f"# {i}\n", f"is {i}")
    once = tree_hash(repo)
    proc = run_module_cli("readme", "--root", str(kok), "--db", str(db_file))
    assert proc.returncode == 0, proc.stderr
    assert tree_hash(repo) == once, "atlas readme repoyu degistirdi"


def test_cli_readme_db_yazar(tmp_path: Path, db_file: Path):
    kok = tmp_path / "kok"
    kok.mkdir()
    repo = make_repo(kok / "r")
    for i in range(9):
        commit_file(repo, f"m{i}.py", f"# {i}\n", f"is {i}")
    run_module_cli("readme", "--root", str(kok), "--db", str(db_file))
    conn = db_mod.connect(db_file)
    try:
        assert db_mod.count_readme_status(conn) == 1
        satir = db_mod.readme_status_for(conn, str(repo))
        assert satir["seviye"] == "bayat"
        assert satir["skor"] == 9
    finally:
        conn.close()


def test_cli_readme_guncelle_dahil(tmp_path: Path, db_file: Path):
    kok = tmp_path / "kok"
    kok.mkdir()
    repo = make_repo(kok / "r")
    for i in range(9):
        commit_file(repo, f"m{i}.py", f"# {i}\n", f"is {i}")
    proc = run_module_cli("guncelle", "--root", str(kok), "--db", str(db_file))
    assert proc.returncode == 0, proc.stderr
    assert "README bayatligi" in proc.stdout
    conn = db_mod.connect(db_file)
    try:
        assert db_mod.count_readme_status(conn) == 1
    finally:
        conn.close()


def test_cli_readme_bos_kok(tmp_path: Path, db_file: Path):
    bos = tmp_path / "bos"
    bos.mkdir()
    proc = run_module_cli("readme", "--root", str(bos), "--db", str(db_file))
    assert proc.returncode == 0, proc.stderr
    assert "README taranacak repo yok" in proc.stdout


# --------------------------------------------------------------------------
# DUYARLILIK SINAMASI (zorunlu)
# --------------------------------------------------------------------------


def test_duyarlilik_sinamasi(tmp_path: Path):
    """'0 bayat' iki anlama gelebilir: gerçekten bayat mı, yoksa ÖLÇÜM YOK mu?

    Senaryo: README commit'i + ardından 9 KOD commit'i → `bayat`.
    Sonra README'ye dokunan 10. commit'ten sonra → `taze`.
    Yalnızca-doc commit'leri eklenince DEĞİŞMEZ.
    """
    repo = tmp_path / "duyarlilik"
    repo.mkdir()
    git("init", "-q", "-b", "main", str(repo))
    (repo / "README.md").write_text("# duyarlilik\n", encoding="utf-8")
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "readme", cwd=repo)

    assert rs.tara_repo(repo).seviye == "taze", "README commit'i tek basina taze olmali"

    for i in range(9):
        commit_file(repo, f"m{i}.py", f"# {i}\n", f"Dalga D: adim {i}")
    dokuz = rs.tara_repo(repo)
    assert dokuz.davranis_commit == 9, dokuz
    assert dokuz.seviye == "bayat", f"9 kod commit'i 'bayat' olmali, {dokuz}"

    # 10. commit README'ye dokunur → ölçüm sıfırlanır.
    (repo / "README.md").write_text("# duyarlilik (guncel)\n", encoding="utf-8")
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "readme guncel", cwd=repo)
    on = rs.tara_repo(repo)
    assert on.davranis_commit == 0, on
    assert on.seviye == "taze", f"README dokunduktan sonra 'taze' olmali, {on}"

    # Yalnizca-doc commit'leri seviyeyi DEGISTIRMEZ.
    for i in range(5):
        commit_file(repo, f"d{i}.md", f"# d{i}\n", "docs: belge")
    sonra = rs.tara_repo(repo)
    assert sonra.davranis_commit == 0, sonra
    assert sonra.seviye == "taze", f"doc-only commit seviyeyi bozmamali, {sonra}"
