"""Alt surec kurulumu ve paralel toplu calistirma sozlesmesi.

Gercek `cor` YOK: her test gecici dizinde sahte bir `cor` betigi kurar (sabit
rapor yazan, `exit 3` veren, uyuyan, kendi cocugu birakan). Ag yok, gercek git
calistirilmaz. Yazma etkileri YALNIZCA tmp_path altindadir; hicbir test repo
klasorune dosya yazmaz.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest
from conftest import gorev_dosyasi, run_module_cli, sahte_cor, sahte_repo

from filo import calistir as calistir_mod
from filo.calistir import (
    AZAMI_PARALEL,
    DUZENLE_ARACLAR,
    SALT_OKUNUR_ARACLAR,
    YASAKLI_DIZELER,
    CalistirmaHatasi,
    RepoSonucu,
    arac_listesi,
    argv_olustur,
    calistir,
)

BULGU_KODU = 1
KULLANIM_HATASI = 2


# --------------------------------------------------------------------------
# gecici sahte `cor` betikleri
# --------------------------------------------------------------------------


def _betik(yol: Path, govde: str) -> Path:
    """Verilen govdeyi calistirilabilir bir python betigine cevirir."""
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(
        "#!" + __import__("sys").executable + "\n" + textwrap.dedent(govde), encoding="utf-8"
    )
    yol.chmod(0o755)
    return yol


def _cor_ada_gore(yol: Path, *, uyku: int = 30) -> Path:
    """Cozuldugu repo adina gore davranir: "bozuk" -> exit 3, "uyanik" -> uyur."""
    return _betik(yol, f"""\
        import os, sys, time
        ad = os.path.basename(os.getcwd())
        sistem = sys.stdin.read()
        if ad == "bozuk":
            sys.stderr.write("sahte cor hatasi\\n")
            sys.exit(3)
        if ad == "uyanik":
            time.sleep({uyku})
        sys.stdout.write("# rapor\\n")
        sys.stdout.write("repo: " + ad + "\\n")
        sys.stdout.write("istem satiri: " + str(len(sistem.splitlines())) + "\\n")
        sys.stderr.write("sahte cor hatasi\\n")   # ok halinde bile stderr yazar
    """)


def _cor_cocuklu(yol: Path, *, uyku: int = 30, cocuk_gecikme: int = 3) -> Path:
    """Uyuyan ve ARKASINDA bir cocuk surec birakan sahte `cor` (grup oldurme testi)."""
    return _betik(yol, f"""\
        import json, subprocess, sys, time
        isaret = {json.dumps(str(yol) + ".cocuk.yazdi")}
        sys.stdin.read()
        subprocess.Popen([sys.executable, "-c",
            "import time; time.sleep(" + str({cocuk_gecikme}) + "); open(" + repr(isaret) + ", 'w').write('yazdi')"])
        time.sleep({uyku})
    """)


def _hedefler(repolar: list[Path], cikti: Path) -> dict[str, Path]:
    """CLI'nin hazirladigi `str(repo) -> rapor yolu` haritasi."""
    return {str(r): cikti / f"{r.name}.md" for r in repolar}


# --------------------------------------------------------------------------
# paralel sonuc toplama
# --------------------------------------------------------------------------


def test_paralel_sonuclar_toplanir_ve_giris_sirasi_korunur(tmp_path):
    """Uc repo paralel calisir; sonuclar GIRIS SIRASI korunarak doner."""
    kok = tmp_path / "p"
    repolar = [sahte_repo(kok / "c"), sahte_repo(kok / "a"), sahte_repo(kok / "b")]
    cikti = tmp_path / "cikti"
    cikti.mkdir()
    cor = _cor_ada_gore(tmp_path / "bin" / "cor")

    sonuclar = calistir(
        repolar, "gorev metni\n", _hedefler(repolar, cikti), cor=str(cor), paralel=3
    )

    assert [s.repo for s in sonuclar] == [str(r) for r in repolar]
    assert [Path(s.repo).name for s in sonuclar] == ["c", "a", "b"]
    assert all(isinstance(s, RepoSonucu) for s in sonuclar)
    assert all(s.durum == "ok" for s in sonuclar)
    assert all(s.cikis_kodu == 0 and s.hata is None for s in sonuclar)
    assert all(s.sure_sn >= 0 for s in sonuclar)
    for s in sonuclar:
        assert Path(s.rapor).is_file()
        assert s.rapor_boyut == Path(s.rapor).stat().st_size > 0


def test_alt_surec_her_repoda_kendi_cwd_sinde_calisir(tmp_path):
    """Alt surec `cwd=repo` ile calisir: saghte cor cozuldugu dizini yazar."""
    kok = tmp_path / "p"
    repolar = [sahte_repo(kok / "bir"), sahte_repo(kok / "iki")]
    cikti = tmp_path / "cikti"
    cikti.mkdir()
    cor = _cor_ada_gore(tmp_path / "bin" / "cor")

    calistir(repolar, "gorev\n", _hedefler(repolar, cikti), cor=str(cor), paralel=2)

    for repo in repolar:
        assert f"repo: {repo.name}" in (cikti / f"{repo.name}.md").read_text(encoding="utf-8")


def test_gorev_metni_stdin_ile_her_surece_gider(tmp_path):
    """Gorev metni STDIN'den gider; saghte cor satir sayisini rapora yazar."""
    kok = tmp_path / "p"
    repolar = [sahte_repo(kok / "r")]
    cikti = tmp_path / "cikti"
    cikti.mkdir()
    cor = _cor_ada_gore(tmp_path / "bin" / "cor")
    gorev = "birinci satir\nikinci satir\nucuncu satir\n"

    calistir(repolar, gorev, _hedefler(repolar, cikti), cor=str(cor), paralel=1)

    assert "istem satiri: 3" in (cikti / "r.md").read_text(encoding="utf-8")


def test_stdout_ve_stderr_ayni_rapora_harmanlanir(tmp_path):
    """stdout+stderr tek dosyaya gider; saghte corun ikisini de yaziyor."""
    kok = tmp_path / "p"
    repolar = [sahte_repo(kok / "r")]
    cikti = tmp_path / "cikti"
    cikti.mkdir()
    cor = _cor_ada_gore(tmp_path / "bin" / "cor")

    calistir(repolar, "gorev\n", _hedefler(repolar, cikti), cor=str(cor), paralel=1)

    icerik = (cikti / "r.md").read_text(encoding="utf-8")
    assert "# rapor" in icerik
    assert "sahte cor hatasi" in icerik  # stderr -> rapor


# --------------------------------------------------------------------------
# hata izolasyonu
# --------------------------------------------------------------------------


def test_bir_repo_hata_verse_digerleri_tamam(tmp_path):
    """Biri patlayinca digerleri ETKILENMEZ; durum satir satir bildirilir."""
    kok = tmp_path / "p"
    repolar = [sahte_repo(kok / "iyi1"), sahte_repo(kok / "bozuk"), sahte_repo(kok / "iyi2")]
    cikti = tmp_path / "cikti"
    cikti.mkdir()
    cor = _cor_ada_gore(tmp_path / "bin" / "cor")

    sonuclar = calistir(repolar, "gorev\n", _hedefler(repolar, cikti), cor=str(cor), paralel=3)

    durumlar = {Path(s.repo).name: s.durum for s in sonuclar}
    assert durumlar == {"iyi1": "ok", "bozuk": "hata", "iyi2": "ok"}
    bozuk = next(s for s in sonuclar if Path(s.repo).name == "bozuk")
    assert bozuk.cikis_kodu == 3
    assert "alt surec cikis kodu 3" in bozuk.hata
    assert (cikti / "iyi1.md").is_file() and (cikti / "iyi2.md").is_file()


def test_calistirilamayan_cor_digerlerini_birdIRMEZ(tmp_path):
    """Yok bir `cor` yolu: tum repolar 'hata', hicbiri cokmez (traceback yok)."""
    kok = tmp_path / "p"
    repolar = [sahte_repo(kok / "r"), sahte_repo(kok / "s")]
    cikti = tmp_path / "cikti"
    cikti.mkdir()
    yok = str(tmp_path / "olmayan-cor")

    sonuclar = calistir(repolar, "gorev\n", _hedefler(repolar, cikti), cor=yok, paralel=2)

    assert [s.durum for s in sonuclar] == ["hata", "hata"]
    assert all("cor bulunamadi" in s.hata for s in sonuclar)


# --------------------------------------------------------------------------
# zaman asimi
# --------------------------------------------------------------------------


def test_zaman_asimi_durumu_zaman_asimi(tmp_path):
    """Uyuyan alt surec zaman asiminda OLDURULUR; durum 'zaman-asimi'."""
    kok = tmp_path / "p"
    repolar = [sahte_repo(kok / "uyanik")]
    cikti = tmp_path / "cikti"
    cikti.mkdir()
    cor = _cor_ada_gore(tmp_path / "bin" / "cor", uyku=30)

    sonuclar = calistir(
        repolar, "gorev\n", _hedefler(repolar, cikti), cor=str(cor), paralel=1, zaman_asimi=1.0
    )

    (sonuc,) = sonuclar
    assert sonuc.durum == "zaman-asimi"
    assert sonuc.sure_sn < 20  # 30 sn'lik uyku beklenmedi
    assert "surec olduruldu" in sonuc.hata


def test_zaman_asiminda_surec_grubu_geri_cocukla_birlikte_olur(tmp_path):
    """Grup oldurme kaniti: uyuyan surecin BIRAKTIGI cocuk da olur."""
    import time

    kok = tmp_path / "p"
    repolar = [sahte_repo(kok / "r")]
    cikti = tmp_path / "cikti"
    cikti.mkdir()
    cor = _cor_cocuklu(tmp_path / "bin" / "cor", uyku=30, cocuk_gecikme=3)

    calistir(
        repolar, "gorev\n", _hedefler(repolar, cikti), cor=str(cor), paralel=1, zaman_asimi=1.0
    )
    time.sleep(4)  # cocuk yazsaydi bu surede hazir olurdu

    assert not (tmp_path / "bin" / "cor.cocuk.yazdi").exists()


def test_zaman_asimi_bir_repoyu_birdIRMEZ(tmp_path):
    """Zaman asimina dusen repo digerlerini calistirmaya devam ettirir."""
    kok = tmp_path / "p"
    repolar = [sahte_repo(kok / "uyanik"), sahte_repo(kok / "normal")]
    cikti = tmp_path / "cikti"
    cikti.mkdir()
    cor = _cor_ada_gore(tmp_path / "bin" / "cor", uyku=30)

    sonuclar = calistir(
        repolar, "gorev\n", _hedefler(repolar, cikti), cor=str(cor), paralel=2, zaman_asimi=1.0
    )

    durumlar = {Path(s.repo).name: s.durum for s in sonuclar}
    assert durumlar == {"uyanik": "zaman-asimi", "normal": "ok"}


# --------------------------------------------------------------------------
# guvenlik: arac listeleri ve yasakli dizeler
# --------------------------------------------------------------------------


def test_varsayilan_arac_listesi_salt_okunur():
    """Varsayilan tam olarak Read,Glob,Grep -- yazma/calistirma araci YOK."""
    araclar = arac_listesi(False)
    assert araclar == SALT_OKUNUR_ARACLAR == "Read,Glob,Grep"
    assert set(araclar.split(",")) == {"Read", "Glob", "Grep"}
    for yazici in ("Write", "Edit", "Bash", "NotebookEdit"):
        assert yazici not in araclar


def test_duzenle_arac_listesi_genistir():
    """`--duzenle`: Read,Write,Edit,Bash,Glob,Grep."""
    araclar = arac_listesi(True)
    assert araclar == DUZENLE_ARACLAR == "Read,Write,Edit,Bash,Glob,Grep"
    assert set(araclar.split(",")) == {"Read", "Write", "Edit", "Bash", "Glob", "Grep"}


@pytest.mark.parametrize("duzenle", [False, True])
def test_kurulan_argvde_yasakli_dize_yoktur(duzenle):
    """Baglayici kural: argv'de `--dangerously-skip-permissions`/`bypassPermissions` YOK."""
    argv = argv_olustur("cor", "bazi/model", arac_listesi(duzenle))
    for yasakli in YASAKLI_DIZELER:
        assert all(yasakli not in parca for parca in argv)
        assert yasakli not in " ".join(argv)


@pytest.mark.parametrize("duzenle", [False, True])
def test_argv_sozlesmeye_birebir_uyar(tmp_path, duzenle):
    """argv tam olarak sozlesmedeki sirayi izler (`shell=False` icin liste)."""
    argv = argv_olustur("cor", "bazi/model", arac_listesi(duzenle))
    assert argv == [
        "cor", "claude", "-p",
        "--model", "bazi/model",
        "--permission-mode", "acceptEdits",
        "--allowedTools", arac_listesi(duzenle),
    ]
    assert all(isinstance(parca, str) for parca in argv)  # kabuk yorumlamasi yok
    assert argv[argv.index("--permission-mode") + 1] == "acceptEdits"


# --------------------------------------------------------------------------
# paralellik sinirlari
# --------------------------------------------------------------------------


@pytest.mark.parametrize("gecersiz", [0, -1, AZAMI_PARALEL + 1, 100])
def test_paralel_sinir_disi_reddedilir(tmp_path, gecersiz):
    """1..8 disindaki paralellik reddedilir (ucretsiz model kotasini korumak icin)."""
    kok = tmp_path / "p"
    repolar = [sahte_repo(kok / "r")]
    cor = _cor_ada_gore(tmp_path / "bin" / "cor")
    with pytest.raises(CalistirmaHatasi, match="1..8"):
        calistir(
            repolar, "gorev\n", _hedefler(repolar, tmp_path / "cikti"),
            cor=str(cor), paralel=gecersiz,
        )


@pytest.mark.parametrize("gecerli", [1, AZAMI_PARALEL])
def test_paralel_sinirlari_gecerli(tmp_path, gecerli):
    """Sinir degerler 1 ve 8 kabul edilir."""
    kok = tmp_path / "p"
    repolar = [sahte_repo(kok / "r")]
    cikti = tmp_path / "cikti"
    cikti.mkdir()
    cor = _cor_ada_gore(tmp_path / "bin" / "cor")

    sonuclar = calistir(repolar, "gorev\n", _hedefler(repolar, cikti), cor=str(cor), paralel=gecerli)
    assert [s.durum for s in sonuclar] == ["ok"]


# --------------------------------------------------------------------------
# cikti dosyalari: mevcut dosya UZERINE YAZILMAZ
# --------------------------------------------------------------------------


def test_mevcut_rapor_dosyasi_ezilmez_cikis_2(tmp_path):
    """Cikti dizininde ayni adli rapor varsa HATA (cikis 2), icerik degismez."""
    kok = tmp_path / "p"
    repolar = [sahte_repo(kok / "r"), sahte_repo(kok / "s")]
    gorev = gorev_dosyasi(tmp_path / "gorev.txt")
    cor = _cor_ada_gore(tmp_path / "bin" / "cor")
    cikti = tmp_path / "cikti"
    cikti.mkdir()
    mevcut = cikti / "r.md"
    mevcut.write_text("KURUCU ICERIK\n", encoding="utf-8")

    proc = run_module_cli(
        "calistir", "--gorev", str(gorev), "--cikti", str(cikti), "--cor", str(cor),
        "--repo", str(repolar[0]), "--repo", str(repolar[1]), cwd=tmp_path,
    )

    assert proc.returncode == KULLANIM_HATASI, proc.stdout
    assert "uzerine yazilmadi" in proc.stderr
    assert mevcut.read_text(encoding="utf-8") == "KURUCU ICERIK\n"
    assert "Traceback" not in proc.stderr
    assert not (cikti / "s.md").exists()  # hicbiri calismadi


# --------------------------------------------------------------------------
# --kuru: hicbir alt surec baslatmaz
# --------------------------------------------------------------------------


@pytest.mark.parametrize("gecersiz", [0, AZAMI_PARALEL + 1])
def test_kuru_da_paralel_sinirini_denetler(tmp_path, gecersiz):
    """`--kuru` gecersiz paralelligi de REDDEDER (cikis 2); plan gostermez."""
    kok = tmp_path / "p"
    repolar = [sahte_repo(kok / "r")]
    gorev = gorev_dosyasi(tmp_path / "gorev.txt")
    cikti = tmp_path / "cikti"

    proc = run_module_cli(
        "calistir", "--gorev", str(gorev), "--cikti", str(cikti), "--kuru",
        "--paralel", str(gecersiz), "--repo", str(repolar[0]), cwd=tmp_path,
    )

    assert proc.returncode == KULLANIM_HATASI, proc.stdout
    assert "1..8" in proc.stderr
    assert "KURU CALISTIRMA" not in proc.stderr  # plan gosterilmedi
    assert not cikti.exists()


def test_kuru_hicbir_alt_surec_baslatmaz(tmp_path):
    """`--kuru`: saghte cor CALISMAZ (isaret dosyasi olusmaz), cikti dizini kurulmaz."""
    kok = tmp_path / "p"
    repolar = [sahte_repo(kok / "r"), sahte_repo(kok / "s")]
    gorev = gorev_dosyasi(tmp_path / "gorev.txt")
    isaret = tmp_path / "bin" / "cor.calisti"
    cor = _betik(tmp_path / "bin" / "cor", f"""\
        import sys
        sys.stdin.read()
        open({json.dumps(str(isaret))}, "w").write("calisti")
    """)
    cikti = tmp_path / "cikti"

    proc = run_module_cli(
        "calistir", "--gorev", str(gorev), "--cikti", str(cikti), "--cor", str(cor),
        "--repo", str(repolar[0]), "--repo", str(repolar[1]), "--kuru", cwd=tmp_path,
    )

    assert proc.returncode == 0, proc.stderr
    assert "KURU CALISTIRMA" in proc.stderr
    assert "argv:" in proc.stdout and "cwd:" in proc.stdout
    assert not isaret.exists()  # hicbir alt surec baslamadi
    assert not cikti.exists()  # cikti dizini bile kurulmadi


# --------------------------------------------------------------------------
# OZET.md icerigi ve cikis kodlari
# --------------------------------------------------------------------------


def test_ozet_md_icerigi_ve_cikis_kodu_1(tmp_path):
    """ok + hata + zaman-asimi birlikte: OZET.md dolu, cikis kodu 1."""
    kok = tmp_path / "p"
    repolar = [sahte_repo(kok / "normal"), sahte_repo(kok / "bozuk"), sahte_repo(kok / "uyanik")]
    gorev = gorev_dosyasi(tmp_path / "gorev.txt")
    cor = _cor_ada_gore(tmp_path / "bin" / "cor", uyku=30)
    cikti = tmp_path / "cikti"

    proc = run_module_cli(
        "calistir", "--gorev", str(gorev), "--cikti", str(cikti), "--cor", str(cor),
        "--zaman-asimi", "1", "--paralel", "3",
        *sum((["--repo", str(r)] for r in repolar), []), cwd=tmp_path,
    )

    assert proc.returncode == BULGU_KODU, proc.stdout
    ozet = (cikti / "OZET.md").read_text(encoding="utf-8")
    assert "# filo ozeti" in ozet
    assert "toplam: 3  ok: 1  hata: 1  zaman-asimi: 1" in ozet
    # tablo basliklari ve her repo'nun satiri
    for baslik in ("repo", "durum", "sure(sn)", "rapor", "boyut"):
        assert baslik in ozet
    assert "normal" in ozet and "bozuk" in ozet and "uyanik" in ozet
    assert "## Hatalar" in ozet
    assert "alt surec cikis kodu 3" in ozet and "surec olduruldu" in ozet
    assert "zaman-asimi" in ozet


def test_ozet_md_ve_cikis_kodu_0(tmp_path):
    """Hepsi ok: OZET.md yazilir, hata bolumu olmaz, cikis kodu 0."""
    kok = tmp_path / "p"
    repolar = [sahte_repo(kok / "r"), sahte_repo(kok / "s")]
    gorev = gorev_dosyasi(tmp_path / "gorev.txt")
    cor = _cor_ada_gore(tmp_path / "bin" / "cor")
    cikti = tmp_path / "cikti"

    proc = run_module_cli(
        "calistir", "--gorev", str(gorev), "--cikti", str(cikti), "--cor", str(cor),
        "--paralel", "2",
        *sum((["--repo", str(r)] for r in repolar), []), cwd=tmp_path,
    )

    assert proc.returncode == 0, proc.stdout
    ozet = (cikti / "OZET.md").read_text(encoding="utf-8")
    assert "toplam: 2  ok: 2  hata: 0  zaman-asimi: 0" in ozet
    assert "## Hatalar" not in ozet
    assert (cikti / "r.md").is_file() and (cikti / "s.md").is_file()


def test_json_ozet_sayaclari_ve_dosya_boyutlari_eslesir(tmp_path):
    """`--json` sayaclari OZET.md ile ayni; rapor boyutu diskteki dosyayla esit."""
    kok = tmp_path / "p"
    repolar = [sahte_repo(kok / "r"), sahte_repo(kok / "s")]
    gorev = gorev_dosyasi(tmp_path / "gorev.txt")
    cor = _cor_ada_gore(tmp_path / "bin" / "cor")
    cikti = tmp_path / "cikti"

    proc = run_module_cli(
        "calistir", "--gorev", str(gorev), "--cikti", str(cikti), "--cor", str(cor),
        "--paralel", "2", "--json",
        *sum((["--repo", str(r)] for r in repolar), []), cwd=tmp_path,
    )

    assert proc.returncode == 0, proc.stderr
    veri = json.loads(proc.stdout)
    assert veri["ozet"] == {"toplam": 2, "ok": 2, "hata": 0, "zaman-asimi": 0}
    for kayit in veri["sonuclar"]:
        assert kayit["rapor_boyut"] == Path(kayit["rapor"]).stat().st_size > 0
        assert kayit["sure_sn"] >= 0