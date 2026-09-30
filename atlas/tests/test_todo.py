"""Dalga C / `atlas borc`: TODO/FIXME/XXX/HACK taramasi (GERÇEK git repoları).

Kanıtlanan davranışlar:
  * Dört işaret de bulunur; kelime SINIRI `\b` ile uygulanır (`TODOS`, `todo_list`,
    `myTODO` gibi değişken/metin adları YANLIŞ POZİTİF üretmez).
  * Yalnız git'in İZLEDİĞİ dosyalar taranır.
  * İkili (NUL) ve >1 MiB dosyalar atlanır.
  * Metin DB'ye yazılmadan önce maskelenir; ham sır DB'de/çıktıda yok.
  * Yeniden tarama aynı repoya ait eski kayıtları silip yeniler (tek transaction).
  * Yeni git alt komutu EKLENMEZ; tarama salt okunurdur.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from conftest import commit_file, git, make_repo, run_module_cli, sahte_sir

from atlas import todo
from atlas.scan import ALLOWED_GIT_SUBCOMMANDS


def _satirlar(bulgular) -> list[tuple[str, int, str]]:
    return sorted((b["file"], b["line"], b["text"]) for b in bulgular)


def _dosyalar(bulgular) -> set[str]:
    return {b["file"] for b in bulgular}


# --------------------------------------------------------------------------
# Tespit
# --------------------------------------------------------------------------


@pytest.mark.parametrize("isaret", ["TODO", "FIXME", "XXX", "HACK"])
def test_dort_isaret_bulunur(tmp_path: Path, isaret: str):
    repo = make_repo(tmp_path / "r")
    commit_file(repo, "a.py", f"# {isaret}: yapilacak\nprint(1)\n", "ekle")
    b = todo.tara_calisma_agaci(repo)
    assert _dosyalar(b) == {"a.py"}
    assert b[0]["line"] == 1
    assert isaret in b[0]["text"]


def test_isaretsiz_dosya_bulgu_yok(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    commit_file(repo, "a.py", "print('temiz')\n", "ekle")
    assert todo.tara_calisma_agaci(repo) == []


@pytest.mark.parametrize(
    "metin",
    [
        "TODOS", "TODOS.txt", "todos = []", "todo_list", "myTODO", "TODO_ITEMS",
        "FIXMEs", "HACKED", "XHACK", "todox", "xtodo", "todoList", "fixMeX",
        "hacks", "xxx2", "TODO2", "aTODO", "TODOLAR",
    ],
)
def test_kelime_siniri_yanlis_pozitif_yok(tmp_path: Path, metin: str):
    """`\\b` sınırı: değişken/metin adları (BİLEŞİK yazım) elenir."""
    repo = make_repo(tmp_path / "r")
    commit_file(repo, "a.py", f'x = "{metin}"\n', "ekle")
    assert todo.tara_calisma_agaci(repo) == []


def test_bilesik_olmayan_kucuk_harf_eslesir(tmp_path: Path):
    """`IGNORECASE` yalnız BİLEŞİK adları eler; tek başına `todo` yakalanır.

    Bu bilinçli ödünlemedir: gerçek kod `// fixme:` yazar (kaçırılmaması için),
    ama `todolist`/`todo_list` gibi değişken adları gürültü üretmez.
    """
    repo = make_repo(tmp_path / "r")
    commit_file(repo, "a.py", 'x = "no-todo burada"\n', "ekle")
    b = todo.tara_calisma_agaci(repo)
    assert len(b) == 1 and b[0]["line"] == 1


@pytest.mark.parametrize("isaret", ["TODO", "FIXme", "XxX", "Hack"])
def test_isaret_karisik_harf_eslesir(tmp_path: Path, isaret: str):
    """Desen büyük/küçük harf duyarsızdır (gerçek kod `todo:` da yazar)."""
    repo = make_repo(tmp_path / "r")
    commit_file(repo, "a.md", f"- {isaret}: duzelt\n", "ekle")
    assert len(todo.tara_calisma_agaci(repo)) == 1


@pytest.mark.parametrize("isaret", ["todo", "fixme", "xxx", "hack"])
def test_isaret_kucuk_harf_eslesir_ama_kelime_siniri_korunur(tmp_path: Path, isaret: str):
    """Küçük harfli işaret bulunur; ama `todo_list` gibi BİLEŞİK ad elenir."""
    assert todo.ISARET_DESENI.search(isaret) is not None
    assert todo.ISARET_DESENI.search(f"{isaret}_list") is None
    assert todo.ISARET_DESENI.search(f"my{isaret}") is None
    repo = make_repo(tmp_path / "r")
    commit_file(repo, "a.md", f"- {isaret}: duzelt\n", "ekle")
    assert len(todo.tara_calisma_agaci(repo)) == 1


def test_isaret_noktalama_ve_satir_ici(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    commit_file(
        repo, "a.py",
        'x = 1  # TODO(sahip, 2026-01-01): ayri\ny = "TODO: metin icinde"\n',
        "ekle",
    )
    b = todo.tara_calisma_agaci(repo)
    assert [x["line"] for x in b] == [1, 2]


def test_markdown_basi_todo_eklenir(tmp_path: Path):
    """Markdown başlığı da geçerli bir işaret satırıdır (bilinçli kabul)."""
    repo = make_repo(tmp_path / "r")
    commit_file(repo, "CHANGELOG.md", "# TODO: sonraki sürüm\n", "ekle")
    assert len(todo.tara_calisma_agaci(repo)) == 1


# --------------------------------------------------------------------------
# Kapsam
# --------------------------------------------------------------------------


def test_izlenmeyen_dosya_taranmaz(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    # Hiç `git add` yapılmaz -> dosya izlenmiyor.
    (repo / "izlenmeyen.txt").write_text("# TODO: yazili ama izlenmiyor\n", encoding="utf-8")
    izli = set(todo.leaks.ls_files(repo))
    assert "izlenmeyen.txt" not in izli
    assert todo.tara_calisma_agaci(repo) == []


def test_uretim_dizinleri_haric(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    for dizin in ("node_modules", ".venv", "vendor", "dist", "build"):
        (repo / dizin).mkdir(parents=True, exist_ok=True)
        (repo / dizin / "a.js").write_text("// TODO: harici\n", encoding="utf-8")
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "harici dosyalar", cwd=repo)
    b = todo.tara_calisma_agaci(repo)
    assert b == [], f"uretim dizinleri taranmamali: {_dosyalar(b)}"
    # Git bunlari izliyor olabilir; tarama yine de eler.
    izli = set(todo.leaks.ls_files(repo))
    assert any(d.startswith("node_modules/") for d in izli)


def test_ikili_dosya_atlanir(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    (repo / "gorsel.bin").write_bytes(b"\x00\x01TODO\x00\x02\xff")
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "ikili ekle", cwd=repo)
    assert "gorsel.bin" not in _dosyalar(todo.tara_calisma_agaci(repo))


def test_buyuk_dosya_atlanir(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    (repo / "devasa.log").write_text("# TODO: bir\n" + ("x" * (1024 * 1024 + 10)), encoding="utf-8")
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "buyuk ekle", cwd=repo)
    assert "devasa.log" not in _dosyalar(todo.tara_calisma_agaci(repo))


def test_sembolik_link_takip_edilmez(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    (repo / "hedef.txt").write_text("# TODO: gercek\n", encoding="utf-8")
    os.symlink(repo / "hedef.txt", repo / "baglanti.txt")
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "link ekle", cwd=repo)
    b = todo.tara_calisma_agaci(repo)
    assert "baglanti.txt" not in _dosyalar(b)
    assert "hedef.txt" in _dosyalar(b)


# --------------------------------------------------------------------------
# Metin: 160 karakter + maske
# --------------------------------------------------------------------------


def test_metin_160_karakterle_sinirli(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    uzun = "# TODO: " + ("a" * 500)
    commit_file(repo, "a.py", uzun + "\n", "ekle")
    b = todo.tara_calisma_agaci(repo)
    assert len(b[0]["text"]) <= todo.METIN_UST_SINIR
    assert b[0]["text"].endswith("…")


def test_metin_maskelenir_ve_ham_sir_yok(tmp_path: Path, db_file: Path):
    """Sahte sır taşıyan TODO satırı: metin maskelenir, DB/çıktıda yok."""
    repo = make_repo(tmp_path / "r")
    sir = sahte_sir()
    commit_file(repo, "a.py", f"# TODO: anahtar {sir}\n", "ekle")
    b = todo.tara_calisma_agaci(repo)
    assert b, "todo bulunmadi"
    assert sir not in b[0]["text"]
    assert "[maskeli" in b[0]["text"]

    proc = run_module_cli("borc", "--root", str(repo.parent), "--db", str(db_file))
    assert proc.returncode == 0, proc.stderr
    ham = db_file.read_bytes() + proc.stdout.encode() + proc.stderr.encode()
    assert sir.encode() not in ham
    assert sir[:6].encode() not in ham


def test_kisisel_yol_metaleri_maskelenir(tmp_path: Path):
    """Gerçek bir kullanıcı adı maskelenir; `<kullanici>` bir YER TUTUCUDUR."""
    repo = make_repo(tmp_path / "r")
    BS = chr(92)  # tek backslash
    gercek = "kullanici" + "x" + "yz"  # parçalardan kurulur (literal YOK)
    commit_file(repo, "a.py", f"# TODO: C:{BS}Users{BS}{gercek}{BS}masaustu\n", "ekle")
    b = todo.tara_calisma_agaci(repo)
    assert gercek not in b[0]["text"]
    assert "<kullanici>" in b[0]["text"]


def test_bos_metin_yok(tmp_path: Path):
    """Yalniz isareti iceren satir de kayit olur (metin bos degil)."""
    repo = make_repo(tmp_path / "r")
    commit_file(repo, "a.py", "TODO\n", "ekle")
    b = todo.tara_calisma_agaci(repo)
    assert b[0]["text"].strip() == "TODO"


# --------------------------------------------------------------------------
# Yeniden tarama + DB
# --------------------------------------------------------------------------


def test_yeniden_tarama_eski_kayitlari_siler(tmp_path: Path, db_file: Path):
    repo = make_repo(tmp_path / "r")
    commit_file(repo, "a.py", "# TODO: ilk\n# TODO: ikinci\n", "ekle")
    proc = run_module_cli("borc", "--root", str(repo.parent), "--db", str(db_file))
    assert proc.returncode == 0, proc.stderr

    from conftest import rows_for  # noqa: F401  (kayitli kalmasin diye import)

    import sqlite3

    con = sqlite3.connect(db_file)
    once = con.execute("SELECT COUNT(*) FROM todos").fetchone()[0]
    con.close()
    assert once == 2

    # Isaretler kaldirilir: yeniden tarama kayitlari SILER.
    commit_file(repo, "a.py", "print('temiz')\n", "temizle")
    proc = run_module_cli("borc", "--root", str(repo.parent), "--db", str(db_file))
    assert proc.returncode == 0, proc.stderr
    con = sqlite3.connect(db_file)
    sonra = con.execute("SELECT COUNT(*) FROM todos").fetchone()[0]
    con.close()
    assert sonra == 0, "eski kayitlar silinmedi"


def test_yeniden_tarama_sayilari_yeniler(tmp_path: Path, db_file: Path):
    repo = make_repo(tmp_path / "r")
    commit_file(repo, "a.py", "# TODO: bir\n", "ekle")
    run_module_cli("borc", "--root", str(repo.parent), "--db", str(db_file))
    commit_file(repo, "a.py", "# TODO: bir\n# FIXME: iki\n# XXX: uc\n", "ekle")
    run_module_cli("borc", "--root", str(repo.parent), "--db", str(db_file))

    import sqlite3

    con = sqlite3.connect(db_file)
    n = con.execute("SELECT COUNT(*) FROM todos").fetchone()[0]
    con.close()
    assert n == 3, "yeniden tarama guncel sayiyi yazmadi"


def test_borc_komutu_ozet_basar(tmp_path: Path, db_file: Path):
    kok = tmp_path / "koklar"
    a = make_repo(kok / "birinci")
    b = make_repo(kok / "ikinci")
    commit_file(a, "x.py", "# TODO: 1\n# TODO: 2\n", "ekle")
    commit_file(b, "y.py", "# FIXME: 1\n", "ekle")
    proc = run_module_cli("borc", "--root", str(kok), "--db", str(db_file))
    assert proc.returncode == 0, proc.stderr
    assert "birinci" in proc.stdout and "ikinci" in proc.stdout
    assert "Toplam todo: 3" in proc.stdout


def test_borc_bos_repo_durumu(tmp_path: Path, db_file: Path):
    make_repo(tmp_path / "temiz")
    proc = run_module_cli("borc", "--root", str(tmp_path), "--db", str(db_file))
    assert proc.returncode == 0, proc.stderr
    assert "TODO/FIXME borcu yok" in proc.stdout


def test_borc_repo_filtresi(tmp_path: Path, db_file: Path):
    kok = tmp_path / "koklar"
    make_repo(kok / "birinci")
    iki = make_repo(kok / "ikinci")
    commit_file(iki, "y.py", "# TODO: sadece bu\n", "ekle")
    proc = run_module_cli("borc", "--root", str(kok), "--db", str(db_file), "--repo", "ikinci")
    assert proc.returncode == 0, proc.stderr
    assert "ikinci" in proc.stdout
    assert "birinci" not in proc.stdout


def test_borc_bilinmeyen_repo_hatasi(tmp_path: Path, db_file: Path):
    make_repo(tmp_path / "tek")
    proc = run_module_cli("borc", "--root", str(tmp_path), "--db", str(db_file), "--repo", "yok")
    assert proc.returncode == 0
    assert "repo bulunamadi" in proc.stderr.lower()


# --------------------------------------------------------------------------
# Salt-okunurluk + izin listesi
# --------------------------------------------------------------------------


def test_yeni_git_alt_komutu_eklenmedi():
    """`todo.py` var olan izin listesinden yeni alt komut TALEP ETMEZ."""
    assert "ls-files" in ALLOWED_GIT_SUBCOMMANDS
    kaynak = Path(todo.__file__).read_text(encoding="utf-8")
    for yasak in ("fetch", "push", "cat-file", "show", "grep", "diff"):
        assert f'"{yasak}"' not in kaynak, f"yeni git alt komutu: {yasak}"


def test_tarama_salt_okunur(tmp_path: Path, db_file: Path):
    from conftest import tree_hash

    repo = make_repo(tmp_path / "r")
    commit_file(repo, "a.py", "# TODO: bir\n", "ekle")
    once = tree_hash(repo)
    proc = run_module_cli("borc", "--root", str(repo.parent), "--db", str(db_file))
    assert proc.returncode == 0, proc.stderr
    assert once == tree_hash(repo), "todo taramasi repoyu degistirdi"


def test_bozuk_repo_taramayi_cozertmez(tmp_path: Path, db_file: Path):
    bozuk = tmp_path / "bozuk"
    bozuk.mkdir()
    (bozuk / ".git").mkdir()
    (bozuk / ".git" / "HEAD").write_text("bu bir HEAD degil\n", encoding="utf-8")
    iyi = make_repo(tmp_path / "iyi")
    commit_file(iyi, "a.py", "# TODO: var\n", "ekle")
    proc = run_module_cli("borc", "--root", str(tmp_path), "--db", str(db_file))
    assert proc.returncode == 0, proc.stderr
    assert "bozuk" in proc.stderr
    assert "Toplam todo: 1" in proc.stdout
