"""Git durumu sozlesmesi: dirty, unpushed, branch, last_commit_at, has_remote."""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.scan import DETACHED_BRANCH, collect_repo
from conftest import commit_file, git, make_bare_remote, make_repo


def test_temiz_repo(tmp_path: Path):
    repo = make_repo(tmp_path / "temiz")
    satir = collect_repo(repo)
    assert satir["name"] == "temiz"
    assert satir["dirty"] == 0
    # Sozlesme: remote HIC yoksa unpushed = toplam commit sayisi (=1).
    assert satir["unpushed"] == 1
    assert satir["branch"] == "main"
    assert satir["has_remote"] == 0
    assert satir["last_commit_at"] == "2024-01-02T03:04:05+00:00"


def test_dirty_degistirilmis_dosya(tmp_path: Path):
    repo = make_repo(tmp_path / "kirli")
    (repo / "README.md").write_text("# degisti\n", encoding="utf-8")
    assert collect_repo(repo)["dirty"] == 1


def test_dirty_untracked_dosya_sayilir(tmp_path: Path):
    repo = make_repo(tmp_path / "yeni")
    (repo / "yeni-dosya.txt").write_text("x", encoding="utf-8")
    assert collect_repo(repo)["dirty"] == 1


def test_dirty_modified_ve_untracked_birlikte(tmp_path: Path):
    repo = make_repo(tmp_path / "ikisi")
    (repo / "README.md").write_text("# degisti\n", encoding="utf-8")
    (repo / "yeni.txt").write_text("x", encoding="utf-8")
    assert collect_repo(repo)["dirty"] == 2


def test_staged_dosya_dirty_sayilir(tmp_path: Path):
    repo = make_repo(tmp_path / "staged")
    (repo / "yeni.txt").write_text("x", encoding="utf-8")
    git("add", "-A", cwd=repo)
    assert collect_repo(repo)["dirty"] == 1


def test_unpushed_upstream_ile(tmp_path: Path):
    remote = make_bare_remote(tmp_path / "uzak.git")
    repo = make_repo(tmp_path / "yerel")
    git("remote", "add", "origin", str(remote), cwd=repo)
    git("push", "-q", "-u", "origin", "main", cwd=repo)
    assert collect_repo(repo)["unpushed"] == 0
    commit_file(repo, "a.txt", "1", "ikinci")
    commit_file(repo, "b.txt", "2", "ucuncu")
    satir = collect_repo(repo)
    assert satir["unpushed"] == 2
    assert satir["has_remote"] == 1
    assert satir["branch"] == "main"


def test_upstream_ustune_yakalaninca_unpushed_sifir(tmp_path: Path):
    remote = make_bare_remote(tmp_path / "uzak.git")
    repo = make_repo(tmp_path / "yerel")
    git("remote", "add", "origin", str(remote), cwd=repo)
    git("push", "-q", "-u", "origin", "main", cwd=repo)
    commit_file(repo, "a.txt", "1", "ek")
    git("push", "-q", cwd=repo)
    assert collect_repo(repo)["unpushed"] == 0


def test_remote_var_upstream_yok_tum_commitler(tmp_path: Path):
    """upstream yoksa 'hicbir remote ref'indeki olmayan' commit sayilir.

    NOT: `git push` yerel `refs/remotes/origin/*` ref'ini yazdigindan ref vardir;
    `for-each-ref` kontrolu ancak ref hic yoksa tetiklenir.
    """
    remote = make_bare_remote(tmp_path / "uzak.git")
    repo = make_repo(tmp_path / "yerel")
    git("remote", "add", "origin", str(remote), cwd=repo)
    # Ref'i elle yaz (ilk commit'te): "remote ref'i var, upstream yok" durumu.
    git("update-ref", "refs/remotes/origin/main", "HEAD", cwd=repo)
    satir = collect_repo(repo)
    assert satir["has_remote"] == 1
    assert satir["unpushed"] == 0  # HEAD, remote ref'inde
    commit_file(repo, "a.txt", "1", "ek")
    assert collect_repo(repo)["unpushed"] == 1  # yeni commit ref'in disinda


def test_remote_var_ref_yoksa_unpushed_bilinmiyor(tmp_path: Path):
    """A.1'in asil bulgusu: remote var + yerelde ref YOK -> sayi UYDURULAMAZ.

    `--not --remotes` hicbir sey dislamaz ve tum commitleri dondurur; oysa gercek
    durum 0 da olabilir. fetch yasak oldugu icin cevap `None` (bilinmiyor).
    """
    repo = make_repo(tmp_path / "bulut")
    git("remote", "add", "origin", "https://ornek.invalid/olmayan.git", cwd=repo)
    commit_file(repo, "a.txt", "1", "ikinci")
    commit_file(repo, "b.txt", "2", "ucuncu")
    assert git("for-each-ref", "--count=1", "refs/remotes", cwd=repo, check=False).strip() == ""
    satir = collect_repo(repo)
    assert satir["has_remote"] == 1
    assert satir["unpushed"] is None  # 3 DEGIL: bilinmiyor


def test_remote_var_ref_eklenince_unpushed_sifir(tmp_path: Path):
    """AYNI repo: `update-ref` ile ref yazilir yazmaz sayi bilinir olur."""
    repo = make_repo(tmp_path / "bulut")
    git("remote", "add", "origin", "https://ornek.invalid/olmayan.git", cwd=repo)
    assert collect_repo(repo)["unpushed"] is None
    # Yapay olarak ref'i HEAD'e isaret ettir: artik "hicbir remote ref'inde degil"
    # bos kume olur -> unpushed 0.
    git("update-ref", "refs/remotes/origin/main", "HEAD", cwd=repo)
    satir = collect_repo(repo)
    assert satir["has_remote"] == 1
    assert satir["unpushed"] == 0


def test_remote_ref_eski_commit_gosteriyorsa_dogru_fark(tmp_path: Path):
    """Ref bayat: HEAD 3 commit ilerideyse unpushed 3 olmali (bilinmiyor degil)."""
    repo = make_repo(tmp_path / "bayat")
    git("remote", "add", "origin", "https://ornek.invalid/olmayan.git", cwd=repo)
    ilk = git("rev-parse", "HEAD", cwd=repo).strip()
    git("update-ref", "refs/remotes/origin/main", ilk, cwd=repo)
    commit_file(repo, "a.txt", "1", "ikinci")
    commit_file(repo, "b.txt", "2", "ucuncu")
    commit_file(repo, "c.txt", "3", "dorduncu")
    satir = collect_repo(repo)
    assert satir["has_remote"] == 1
    assert satir["unpushed"] == 3  # ref ilk commit'te kaldi


def test_remote_hic_yok_unpushed_toplam_commit_degismedi(tmp_path: Path):
    """`has_remote=0` davranisi DEGISMEDIR: toplam commit sayisi (NULL degil)."""
    repo = make_repo(tmp_path / "yalniz")
    commit_file(repo, "a.txt", "1", "ikinci")
    commit_file(repo, "b.txt", "2", "ucuncu")
    satir = collect_repo(repo)
    assert satir["has_remote"] == 0
    assert satir["unpushed"] == 3
    # has_remote=0 iken "bilinmiyor" kurali TETIKLENMEZ (kural remote'a bakar).
    # Satir ancak `HEAD --not --remotes` sayesinde daralir; bu, eski ve korunmus
    # davranistir. Kilit olan nokta: sonuc hicbir zaman NULL olmaz.
    git("update-ref", "refs/remotes/origin/main", "HEAD", cwd=repo)
    assert collect_repo(repo)["unpushed"] == 0


def test_remote_var_push_edilmis_ama_upstream_yok(tmp_path: Path):
    remote = make_bare_remote(tmp_path / "uzak.git")
    repo = make_repo(tmp_path / "yerel")
    git("remote", "add", "origin", str(remote), cwd=repo)
    git("push", "-q", "origin", "main", cwd=repo)  # -u YOK: upstream kurulmaz
    satir = collect_repo(repo)
    assert satir["has_remote"] == 1
    assert satir["unpushed"] == 0  # HEAD remote ref'inde
    commit_file(repo, "a.txt", "1", "ek")
    assert collect_repo(repo)["unpushed"] == 1


def test_remote_hic_yok_unpushed_toplam_commit(tmp_path: Path):
    repo = make_repo(tmp_path / "yalniz")
    commit_file(repo, "a.txt", "1", "ikinci")
    commit_file(repo, "b.txt", "2", "ucuncu")
    satir = collect_repo(repo)
    assert satir["has_remote"] == 0
    assert satir["unpushed"] == 3


def test_bos_repo(tmp_path: Path):
    repo = make_repo(tmp_path / "bos", commit=False)
    satir = collect_repo(repo)
    assert satir["branch"] == "main"  # unborn branch
    assert satir["dirty"] == 0
    assert satir["unpushed"] == 0
    assert satir["last_commit_at"] is None
    assert satir["has_remote"] == 0


def test_bos_repo_uzak_eklenince(tmp_path: Path):
    """Commit yokken remote eklenirse de cokmemeli."""
    remote = make_bare_remote(tmp_path / "uzak.git")
    repo = make_repo(tmp_path / "bos-uzak", commit=False)
    git("remote", "add", "origin", str(remote), cwd=repo)
    satir = collect_repo(repo)
    assert satir["has_remote"] == 1
    assert satir["unpushed"] == 0
    assert satir["last_commit_at"] is None


def test_bos_repo_dosya_eklenince_dirty(tmp_path: Path):
    repo = make_repo(tmp_path / "bos2", commit=False)
    (repo / "ilk.txt").write_text("x", encoding="utf-8")
    satir = collect_repo(repo)
    assert satir["dirty"] == 1
    assert satir["unpushed"] == 0
    assert satir["last_commit_at"] is None


def test_detached_head(tmp_path: Path):
    repo = make_repo(tmp_path / "ayrik")
    commit_file(repo, "a.txt", "1", "ikinci")
    ilk = git("rev-parse", "HEAD~1", cwd=repo).strip()
    git("checkout", "-q", ilk, cwd=repo)
    satir = collect_repo(repo)
    assert satir["branch"] == DETACHED_BRANCH
    assert satir["last_commit_at"] == "2024-01-02T03:04:05+00:00"
    assert satir["dirty"] == 0


def test_dallanmis_dal_ismi(tmp_path: Path):
    repo = make_repo(tmp_path / "dallanmis")
    git("checkout", "-q", "-b", "ozel-dal", cwd=repo)
    assert collect_repo(repo)["branch"] == "ozel-dal"


def test_ozel_dal_diğer_adlarla_yazilan_branch(tmp_path: Path):
    repo = make_repo(tmp_path / "turkce")
    git("checkout", "-q", "-b", "özellik-şubesi", cwd=repo)
    assert collect_repo(repo)["branch"] == "özellik-şubesi"


def test_last_commit_at_utcye_cevrilir(tmp_path: Path):
    repo = make_repo(tmp_path / "saat")
    satir = collect_repo(repo)
    assert satir["last_commit_at"].endswith("+00:00")
    assert "T" in satir["last_commit_at"]


def test_bozuk_git_dizini_hata_verir(tmp_path: Path):
    bozuk = tmp_path / "bozuk"
    bozuk.mkdir()
    (bozuk / ".git").mkdir()
    (bozuk / ".git" / "HEAD").write_text("bu gecersiz\n", encoding="utf-8")
    from atlas.scan import GitError, scan_repo_safe

    satir, hata = scan_repo_safe(bozuk)
    assert satir is None
    assert hata


def test_git_binary_yoksa_acik_hata(tmp_path: Path, monkeypatch):
    """Ortam bosken subprocess OSError firlatir; scan_repo_safe cikmaz."""
    from atlas.scan import scan_repo_safe

    repo = make_repo(tmp_path / "repo")
    monkeypatch.setenv("PATH", str(tmp_path / "yok-boyle-bir-dizin"))
    satir, hata = scan_repo_safe(repo)
    assert satir is None
    assert hata and ("git" in hata or "FileNotFound" in hata or "No such" in hata)


def test_yazma_komutu_calistirilamaz():
    """Guvenlik: sadece okuyan alt komutlar izinli."""
    from atlas.scan import ALLOWED_GIT_SUBCOMMANDS, GitError, run_git

    for yasak in ("fetch", "push", "reset", "checkout", "clean", "gc", "pull", "filter-branch"):
        assert yasak not in ALLOWED_GIT_SUBCOMMANDS
        with pytest.raises(GitError):
            run_git(Path("."), [yasak])


def test_git_ortami_optional_locks_kapali():
    from atlas.scan import git_env

    assert git_env()["GIT_OPTIONAL_LOCKS"] == "0"
    assert git_env()["GIT_TERMINAL_PROMPT"] == "0"
