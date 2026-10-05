"""topla.py: git toplama, tarih penceresi, bos repo atlama (gercek git, tmp_path)."""

from __future__ import annotations

import os
import subprocess
from datetime import date

import pytest
from conftest import commit_yap, git_kur, repo_gun_icin

from haftalik.topla import RepoHatasi, repo_bulgulari, repo_ozeti, tarih_araligi, topla


class TestRepoBulgu:
    def test_kok_kendisi_repo_ise(self, tmp_path):
        repo = git_kur(tmp_path / "tek")
        assert repo_bulgulari(repo) == [repo]

    def test_derinlikteki_repo_bulunur(self, tmp_path):
        """Keşif `kok`'tan DERINLIK 3'e kadar iner (`repo_bulgulari`)."""
        sigan = repo_gun_icin(tmp_path / "a" / "b" / "proje", 1, 1)
        bulunan = repo_bulgulari(tmp_path)
        assert sigan in bulunan

    def test_derinlik_sinirindaki_repo_bulunmaz(self, tmp_path):
        """Derinlik 4 (kök/a/b/c/proje) kapsam DIŞIDIR: sessizce atlanır."""
        sigan = repo_gun_icin(tmp_path / "a" / "b" / "proje", 1, 1)
        derin = repo_gun_icin(tmp_path / "a" / "b" / "c" / "proje", 1, 1)
        assert repo_bulgulari(tmp_path) == [sigan]
        assert derin not in repo_bulgulari(tmp_path)

    def test_repo_icine_girilmez(self, tmp_path):
        dis = git_kur(tmp_path / "dis")
        git_kur(tmp_path / "dis" / "ic")
        assert repo_bulgulari(tmp_path) == [dis]

    def test_yok_yol_hata(self, tmp_path):
        with pytest.raises(RepoHatasi):
            repo_bulgulari(tmp_path / "yok")

    def test_repo_olmayan_dizin_hata(self, tmp_path):
        (tmp_path / "duz.txt").write_text("x", encoding="utf-8")
        with pytest.raises(RepoHatasi):
            repo_bulgulari(tmp_path / "duz.txt")


class TestPencere:
    def test_yeniler_alinir_eskiler_alinmaz(self, tmp_path):
        repo = git_kur(tmp_path / "r")
        commit_yap(repo, "yeni.txt", "y\n", gun_once=1, mesaj="yeni is")
        commit_yap(repo, "eski.txt", "e\n", gun_once=60, mesaj="eski is")

        sonuc = topla([repo], 7)
        assert len(sonuc) == 1
        konular = [c.konu for c in sonuc[0].commitler]
        assert konular == ["yeni is"]

    def test_gun_penceresi_genisletilince_eski_girer(self, tmp_path):
        repo = git_kur(tmp_path / "r")
        commit_yap(repo, "eski.txt", "e\n", gun_once=60, mesaj="eski is")
        assert topla([repo], 7) == []
        assert len(topla([repo], 90)) == 1

    def test_bos_repo_listelenmez(self, tmp_path):
        git_kur(tmp_path / "bos")
        assert topla([tmp_path / "bos"], 7) == []

    def test_bos_repo_aktif_mi_false(self, tmp_path):
        ozet = repo_ozeti(git_kur(tmp_path / "b"), 7)
        assert ozet is None

    def test_birden_fazla_kok(self, tmp_path):
        a = repo_gun_icin(tmp_path / "a", 1, 2)
        b = repo_gun_icin(tmp_path / "b", 1, 1)
        sonuc = topla([tmp_path / "a", tmp_path / "b"], 7)
        assert {o.yol for o in sonuc} == {a, b}
        assert [o.adet for o in sonuc if o.yol == a][0] == 2

    def test_ayni_repo_iki_kokte_bir_kez(self, tmp_path):
        repo = repo_gun_icin(tmp_path / "a", 1, 2)
        sonuc = topla([tmp_path, repo], 7)
        assert sonuc.count([o for o in sonuc if o.yol == repo][0]) == 1

    def test_gun_sifir_hata(self, tmp_path):
        repo = repo_gun_icin(tmp_path / "r", 1, 1)
        with pytest.raises(RepoHatasi):
            topla([repo], 0)


class TestIstatistik:
    def test_satir_ekle_sil_hesaplanir(self, tmp_path):
        repo = git_kur(tmp_path / "r")
        commit_yap(repo, "a.txt", "1\n2\n3\n", gun_once=1, mesaj="uc satir")
        ozet = topla([repo], 7)[0]
        assert ozet.eklenen == 3
        assert ozet.silinen == 0

    def test_birden_fazla_commit_toplanir(self, tmp_path):
        repo = repo_gun_icin(tmp_path / "r", 1, 4)
        ozet = topla([repo], 7)[0]
        assert ozet.adet == 4
        assert ozet.eklenen == 4  # her commit 1 satir ekliyor
        assert {c.yazar for c in ozet.commitler} == {"Test"}
        assert [c.konu for c in ozet.commitler] == ["is 3", "is 2", "is 1", "is 0"]

    def test_merge_commit_yok(self, tmp_path):
        """--no-merges: merge commit'leri listeye girmez."""
        repo = git_kur(tmp_path / "r")
        commit_yap(repo, "a.txt", "1\n", gun_once=2, mesaj="ana is")
        subprocess.run(["git", "-C", str(repo), "checkout", "-q", "-b", "dal"],
                       capture_output=True, check=True, timeout=60)
        commit_yap(repo, "b.txt", "1\n", gun_once=1, mesaj="dal is")
        subprocess.run(["git", "-C", str(repo), "checkout", "-q", "main"],
                       capture_output=True, check=True, timeout=60)
        subprocess.run(
            ["git", "-C", str(repo), "merge", "--no-ff", "-q", "-m", "birlesim", "dal"],
            capture_output=True, check=True, env=dict(os.environ), timeout=60,
        )
        ozet = topla([repo], 7)[0]
        konular = [c.konu for c in ozet.commitler]
        assert "birlesim" not in konular
        assert "dal is" in konular


class TestTarihAraligi:
    def test_bicim(self):
        bas, bitis = tarih_araligi(7, date(2026, 10, 5))
        assert bas == "2026-09-28" and bitis == "2026-10-05"
