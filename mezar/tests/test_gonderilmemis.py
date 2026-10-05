"""Denetim 3: `gonderilmemis` -- uzakta olmayan commit var mi?"""

from __future__ import annotations

import pytest

from mezar import gonderilmemis

from conftest import bare_uzak, git, mezar_tasi_repo, uzak_ekle_ve_gonder, yaz

DOSYALAR = {"README.md": "# proje\n", "src/kod.py": "print(1)\n"}


def test_uzak_yoksa_remote_izi_yok_uyarisi(tmp_path):
    """Negatif: hicbir uzak yok -> gonderilmemis commit KONTROL EDILEMEZ (uyari)."""
    repo = mezar_tasi_repo(tmp_path, "anlat", DOSYALAR)
    sonuc = gonderilmemis.denetle(repo)
    assert sonuc["durum"] == "remote-yok"
    assert sonuc["uzakta_yok"] == 0
    assert sonuc["onem"] is None, "kontrol EDILEMEYEN durum onem tasimaz"
    assert "KONTROL EDILEMEDI" in sonuc["not"]


def test_gonderilmis_repo_temiz(tmp_path):
    """Pozitif: bare uzaka push edilmis ve yeni commit yok -> 'temiz'."""
    repo = mezar_tasi_repo(tmp_path, "anlat", DOSYALAR)
    uzak_ekle_ve_gonder(repo, bare_uzak(tmp_path, "anlat"))
    sonuc = gonderilmemis.denetle(repo)
    assert sonuc["durum"] == "temiz"
    assert sonuc["uzakta_yok"] == 0
    assert sonuc["onem"] is None
    assert sonuc["kirli"] == []


def test_gonderilmemis_commit_var(tmp_path):
    """Negatif: push sonrasi yerel commit -> 'gonderilmemis-var' + konular."""
    repo = mezar_tasi_repo(tmp_path, "anlat", DOSYALAR)
    uzak_ekle_ve_gonder(repo, bare_uzak(tmp_path, "anlat"))
    yaz(repo / "README.md", "# proje\n\nyeni satir\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "yerel calisma: ozet guncellendi")
    sonuc = gonderilmemis.denetle(repo)
    assert sonuc["durum"] == "gonderilmemis-var"
    assert sonuc["uzakta_yok"] == 1
    # Bu bulgunun onemi YUKSEK'tir: repo kapanirsa is kalici kaybolur.
    assert sonuc["onem"] == gonderilmemis.YUKSEK_ONEM == "YUKSEK"
    assert len(sonuc["konular"]) == 1
    assert "ozet guncellendi" in sonuc["konular"][0]
    # konu satiri kisaltilmis hash ile baslar
    assert sonuc["konular"][0].split()[0] == git(repo, "rev-parse", "--short", "HEAD").strip()


def test_kirli_calisma_agaci(tmp_path):
    """Negatif: commit EDILMEMIS degisiklik varsa calisma agaci kirli sayilir."""
    repo = mezar_tasi_repo(tmp_path, "anlat", DOSYALAR)
    uzak_ekle_ve_gonder(repo, bare_uzak(tmp_path, "anlat"))
    yaz(repo / "README.md", "# degisti ama commit edilmedi\n")
    sonuc = gonderilmemis.denetle(repo)
    assert sonuc["uzakta_yok"] == 0  # commit yok
    assert sonuc["kirli"] == [" M README.md"], sonuc["kirli"]


def test_upstream_yoksa_origin_main_kullanilir(tmp_path):
    """upstream tanimli degilse, `origin/main` varsa o kullanilir.

    `remote add` sonrasi `push -u` YOK: upstream referansi olusmaz, dusece
    `origin/main` devreye girer.
    """
    repo = mezar_tasi_repo(tmp_path, "anlat", DOSYALAR)
    uzak = bare_uzak(tmp_path, "anlat")
    git(repo, "remote", "add", "origin", str(uzak))
    git(repo, "push", "-q", "origin", "HEAD:refs/heads/main")
    sonuc = gonderilmemis.denetle(repo)
    assert sonuc["referans"] == "origin/main"
    assert sonuc["durum"] == "temiz"