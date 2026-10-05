"""CLI sözleşmesi: çıkış kodları 0/1/2, `--json` şeması, sabit uyarı metni.

`python -m mezar` GERÇEKTEN subprocess olarak çalıştırılır: `sys.exit(main())`
yolunun (konsol komutuyla aynı) doğru döndüğü ancak böyle kanıtlanır.
Ortam `conftest.ortam` ile izole: PYTHONPATH ve geçici HOME/ANAHTARLIK_DIR, yani
kullanıcının gerçek repolarına ya da tuz dosyasına dokunulmaz.
"""

from __future__ import annotations

import json

from mezar import karar as karar_mod

from conftest import (
    bare_uzak,
    git,
    hedef_kopyala,
    mezar_tasi_repo,
    run_cli,
    uzak_ekle_ve_gonder,
    yaz,
)

DOSYALAR = {"README.md": "# proje\n", "src/kod.py": "print(1)\n"}

SAHTE = "AKIA" + "ZZZZZZZZZZZZZZZZZZ"


def _temiz(tmp_path, ad="anlat"):
    """HICBIR bulgu olmayan ortam; cikis kodu 0 beklenir."""
    repo = mezar_tasi_repo(tmp_path, ad, DOSYALAR)
    hedef_kopyala(tmp_path / "araclar", ad, DOSYALAR)
    uzak_ekle_ve_gonder(repo, bare_uzak(tmp_path, ad))
    return tmp_path


def _denetle_args(tmp_path, *repo_adlari):
    return ("denetle", "--kok", str(tmp_path), "--arac-repo", str(tmp_path / "araclar"),
            *[a for ad in repo_adlari for a in ("--repo", ad)])


# --- çıkış kodları ---------------------------------------------------------

def test_hepsi_kapatilabilir_cikis_0(tmp_path):
    """Pozitif: bulgu yoksa cikis kodu 0."""
    kok = _temiz(tmp_path)
    proc = run_cli(*_denetle_args(kok, "anlat"))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "KAPATILABILIR" in proc.stdout


def test_bulgu_var_cikis_1(tmp_path):
    """Negatif: en az bir DIKKAT varsa cikis kodu 1."""
    kok = _temiz(tmp_path)
    mezar_tasi_repo(tmp_path, "atlas", DOSYALAR)     # uzak yok ama hedefte eksik dosya
    proc = run_cli(*_denetle_args(kok, "anlat", "atlas"))
    assert proc.returncode == 1
    assert "DIKKAT" in proc.stdout


def test_gecmis_secret_cikis_1(tmp_path):
    """Negatif: gecmiste secret varsa cikis kodu 1."""
    repo = mezar_tasi_repo(tmp_path, "anlat", {"ayar.py": f'aws = "{SAHTE}"\n'})
    hedef_kopyala(tmp_path / "araclar", "anlat", {"ayar.py": "aws = ''\n"})
    uzak_ekle_ve_gonder(repo, bare_uzak(tmp_path, "anlat"))
    proc = run_cli(*_denetle_args(tmp_path, "anlat"))
    assert proc.returncode == 1
    assert SAHTE not in proc.stdout
    assert SAHTE not in proc.stderr


def test_kok_yok_cikis_2_hata_mesaji(tmp_path):
    """Negatif: yok olan kok -> cikis kodu 2, stderr'de 'Hata:', traceback YOK."""
    kok = _temiz(tmp_path)
    proc = run_cli("denetle", "--kok", str(tmp_path / "yok"),
                   "--arac-repo", str(kok / "araclar"), "--repo", "anlat")
    assert proc.returncode == 2
    assert proc.stderr.startswith("Hata:")
    assert "Traceback" not in proc.stderr
    assert proc.stdout == ""


def test_repo_dizini_yok_cikis_2(tmp_path):
    """Negatif: var olmayan repo adi -> cikis kodu 2, traceback YOK."""
    kok = _temiz(tmp_path)
    proc = run_cli(*_denetle_args(kok, "olmayan"))
    assert proc.returncode == 2
    assert "Hata:" in proc.stderr and "Traceback" not in proc.stderr


def test_git_deposu_olmayan_dizin_cikis_2(tmp_path):
    """Negatif: git deposu olmayan dizin -> cikis kodu 2."""
    (tmp_path / "duz").mkdir()
    (tmp_path / "araclar").mkdir()
    proc = run_cli("denetle", "--kok", str(tmp_path),
                   "--arac-repo", str(tmp_path / "araclar"), "--repo", "duz")
    assert proc.returncode == 2
    assert "Traceback" not in proc.stderr


def test_repo_bayragi_olmadan_cikis_2(tmp_path):
    """Negatif: `--repo` hic verilmezse argparse hata verir (cikis kodu 2)."""
    proc = run_cli("denetle", "--kok", str(tmp_path), "--arac-repo", str(tmp_path))
    assert proc.returncode == 2
    assert "Traceback" not in proc.stderr


def test_satir_limiti_gecersiz_cikis_2(tmp_path):
    """Negatif: sifir/negatif limit -> cikis kodu 2, traceback YOK."""
    kok = _temiz(tmp_path)
    proc = run_cli(*_denetle_args(kok, "anlat"), "--satir-limiti", "0")
    assert proc.returncode == 2
    assert proc.stderr.startswith("Hata:")
    assert "Traceback" not in proc.stderr


def test_komut_yok_cikis_2(tmp_path):
    """Negatif: alt komut verilmezse kullanim hatasi (cikis kodu 2)."""
    assert run_cli().returncode == 2


# --- sabit uyari metni -----------------------------------------------------

def test_kapanis_uyarisi_stdoutda_da_uyarida_da(tmp_path):
    """Sabit kapanis uyarisi her iki ciktida da birebir ayni."""
    kok = _temiz(tmp_path)
    metin_proc = run_cli(*_denetle_args(kok, "anlat"))
    json_proc = run_cli(*_denetle_args(kok, "anlat"), "--json")
    assert karar_mod.KAPANIS_UYARISI in metin_proc.stdout
    assert json.loads(json_proc.stdout)["uyari"] == karar_mod.KAPANIS_UYARISI
    assert "silmez/arşivlemez" in karar_mod.KAPANIS_UYARISI
    assert "anahtarı döndürün" in karar_mod.KAPANIS_UYARISI


def test_uyari_son_satirda_geciyor(tmp_path):
    """Kapanis uyarisi raporun SONUNDA yer alir."""
    kok = _temiz(tmp_path)
    proc = run_cli(*_denetle_args(kok, "anlat"))
    assert proc.returncode == 0
    assert proc.stdout.rstrip().endswith(karar_mod.KAPANIS_UYARISI)


# --- --json şeması ---------------------------------------------------------

def test_json_sema(tmp_path):
    """Pozitif: --json ciktisi beklenen anahtarlari tasir."""
    kok = _temiz(tmp_path)
    proc = run_cli(*_denetle_args(kok, "anlat"), "--json")
    assert proc.returncode == 0, proc.stderr
    veri = json.loads(proc.stdout)

    assert set(veri) == {"kok", "arac_repo", "repolar", "ozet", "uyari"}
    assert veri["kok"] == str(tmp_path)
    assert veri["ozet"] == {"toplam": 1, "kapatilabilir": 1, "dikkat": 0}

    repo = veri["repolar"][0]
    assert set(repo) == {
        "ad", "yol", "hedef", "karar", "nedenler", "notlar",
        "mezar_tasi", "tasima_tamlik", "gonderilmemis", "gecmis_secret",
    }
    assert repo["ad"] == "anlat"
    assert repo["karar"] == "KAPATILABILIR"
    assert repo["nedenler"] == []
    assert set(repo["mezar_tasi"]) == {"durum", "kalan", "not"}
    assert set(repo["tasima_tamlik"]) == {
        "durum", "kaynak", "hedef", "eksik_sayisi", "eksik_gosterilen", "not",
    }
    assert set(repo["gonderilmemis"]) == {
        "durum", "referans", "uzakta_yok", "konular", "kirli", "onem", "not",
    }
    assert set(repo["gecmis_secret"]) == {
        "bulundu", "kismi", "taranan_satir", "sure", "not",
    }


def test_json_sir_degeri_icin_sema(tmp_path):
    """Negatif: secret bulgulu rapor --json ile de deger SIZDIRMAZ."""
    repo = mezar_tasi_repo(tmp_path, "anlat", {"ayar.py": f'aws = "{SAHTE}"\n'})
    hedef_kopyala(tmp_path / "araclar", "anlat", {"ayar.py": "aws = ''\n"})
    uzak_ekle_ve_gonder(repo, bare_uzak(tmp_path, "anlat"))
    proc = run_cli(*_denetle_args(tmp_path, "anlat"), "--json")
    assert proc.returncode == 1
    veri = json.loads(proc.stdout)
    bulgu = veri["repolar"][0]["gecmis_secret"]["bulundu"][0]
    assert set(bulgu) == {"commit", "dosya", "tur", "izi"}
    assert SAHTE not in proc.stdout
    assert "AKIA" not in proc.stdout


def test_json_utf8_korunur(tmp_path):
    """Turkce karakterler JSON'da kaçis dizisi olarak DEGIL, gercek karakter olarak cikar."""
    kok = _temiz(tmp_path)
    proc = run_cli(*_denetle_args(kok, "anlat"), "--json")
    assert "anahtarı döndürün" in proc.stdout
    assert "\\u" not in proc.stdout
    assert json.loads(proc.stdout)["repolar"][0]["karar"] == "KAPATILABILIR"


# --- salt okunurluk --------------------------------------------------------

def test_arac_hicbir_sey_yazmaz(tmp_path):
    """Guvenlik: CLI calistiktan SONRA da hicbir yeni dosya olusmaz.

    Tamamen gecici dizin taranir; denetimden once/sonra ayni resim olmali.
    """
    kok = _temiz(tmp_path)
    yaz(kok / "anlat" / "README.md", "# proje\n")
    git(kok / "anlat", "add", "-A")
    git(kok / "anlat", "commit", "-q", "-m", "okuma")
    git(kok / "anlat", "push", "-q", "origin", "HEAD:refs/heads/main")

    def resim():
        """Tum yollar (dogum/silinme) + calisma agaci dosyalarinin mtime/boyutu.

        `.git` ICERIGI dislanir: salt okunur `git status` git'in kendi stat
        onbellegini (index) tazeler -- bu aracin yazdigi bir sey degildir.
        Dosya EKLENME/SILINMEMESI yine de tum yol listesinden yakalanir.
        """
        tum = sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*"))
        agac = sorted(
            f"{p.relative_to(tmp_path)}:{p.stat().st_mtime_ns}:{p.stat().st_size}"
            for p in tmp_path.rglob("*")
            if ".git" not in p.relative_to(tmp_path).parts
        )
        return tum, agac

    once = resim()
    proc = run_cli(*_denetle_args(kok, "anlat"))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert resim() == once


def test_uygula_bayi_yoktur(tmp_path):
    """Guvenlik: `--uygula` bayragi YOKTUR (bu arac salt okunur)."""
    kok = _temiz(tmp_path)
    proc = run_cli(*_denetle_args(kok, "anlat"), "--uygula")
    assert proc.returncode == 2
    assert "Traceback" not in proc.stderr


def test_gonderilmemis_raporu_yuksek_onemle_gelir(tmp_path):
    """Uzakta olmayan commit YUKSEK onemle isaretlenir (metin raporunda)."""
    kok = _temiz(tmp_path)
    yaz(kok / "anlat" / "README.md", "# proje\n\nyeni\n")
    git(kok / "anlat", "add", "-A")
    git(kok / "anlat", "commit", "-q", "-m", "gonderilmemis is")
    proc = run_cli(*_denetle_args(kok, "anlat"))
    assert proc.returncode == 1
    assert "[YUKSEK] 1 commit uzakta yok" in proc.stdout
    assert "gonderilmemis is" in proc.stdout, "commit konu satiri listelenmeli"