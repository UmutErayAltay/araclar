"""CLI sozlesmesi: `python -m filo calistir` GERCEKTEN subprocess olarak calistirilir.

Gercek `cor` YOK: her test gecici dizinde sahte bir `cor` betigi verir.
Yazma etkileri YALNIZCA tmp_path altindadir.
"""

from __future__ import annotations

import json
from pathlib import Path

from conftest import gorev_dosyasi, run_module_cli, sahte_cor, sahte_repo

KULLANIM_HATASI = 2
BULGU_KODU = 1


def _temel(tmp_path: Path) -> dict:
    """Iki sahte repo + bir sahte cor betigi kurar."""
    kok = tmp_path / "projeler"
    repolar = [sahte_repo(kok / "r", ), sahte_repo(kok / "s")]
    gorev = gorev_dosyasi(tmp_path / "gorev.txt")
    cor = sahte_cor(tmp_path / "bin" / "cor")
    cikti = tmp_path / "cikti"
    return {"repolar": repolar, "gorev": gorev, "cor": cor, "cikti": cikti}


def _calistir(tmp_path: Path, *ek: str, gorev: Path, cor: Path, cikti: Path, repolar):
    argv = ["calistir", "--gorev", str(gorev), "--cikti", str(cikti), "--cor", str(cor)]
    for r in repolar:
        argv += ["--repo", str(r)]
    return run_module_cli(*argv, *ek, cwd=tmp_path)


# --------------------------------------------------------------------------
# temel akis: paralel calistirma + rapor toplama
# --------------------------------------------------------------------------


def test_calistir_paralel_sonuclari_toplar_ve_cikis_0(tmp_path):
    """Iki repo da calisir: her repo icin rapor dosyasi + OZET.md yazilir, cikis 0."""
    t = _temel(tmp_path)
    proc = _calistir(tmp_path, "--paralel", "2", **t)
    assert proc.returncode == 0, proc.stderr
    for repo in t["repolar"]:
        rapor = t["cikti"] / f"{repo.name}.md"
        assert rapor.is_file(), f"{rapor} yazilmadi"
        assert "# rapor" in rapor.read_text(encoding="utf-8")
    assert (t["cikti"] / "OZET.md").is_file()


def test_calistir_rapor_istem_stdin_ile_gider(tmp_path):
    """Gorev metni STDIN'den gider; sahte cor bunu satir sayisi olarak raporlar."""
    t = _temel(tmp_path)
    proc = _calistir(tmp_path, **t)
    assert proc.returncode == 0, proc.stderr
    icerik = (t["cikti"] / "r.md").read_text(encoding="utf-8")
    beklenen = len((tmp_path / "gorev.txt").read_text(encoding="utf-8").splitlines())
    assert f"istem satiri: {beklenen}" in icerik


def test_calistir_json_gecerli_json_ve_ozet_sayaclari(tmp_path):
    """`--json` tablo yerine gecerli JSON yazar; ozet sayaclari eslesir."""
    t = _temel(tmp_path)
    proc = _calistir(tmp_path, "--json", **t)
    assert proc.returncode == 0, proc.stderr
    veri = json.loads(proc.stdout)
    assert veri["surum"] == 1
    assert veri["ozet"] == {"toplam": 2, "ok": 2, "hata": 0, "zaman-asimi": 0}
    assert {s["ad"] for s in veri["sonuclar"]} == {"r", "s"}
    assert veri["ozet_dosyasi"].endswith("OZET.md")


def test_calistir_ozet_md_tablosu_ve_hata_satiri(tmp_path):
    """OZET.md: baslik, tablo ve hata satirlarini icerir."""
    t = _temel(tmp_path)
    t["cor"].unlink()
    cor = sahte_cor(t["cor"], vaka="hata")
    proc = _calistir(tmp_path, **t)
    assert proc.returncode == BULGU_KODU, proc.stdout
    ozet = (t["cikti"] / "OZET.md").read_text(encoding="utf-8")
    assert "# filo ozeti" in ozet
    assert "repo" in ozet and "sure(sn)" in ozet and "boyut" in ozet
    assert "## Hatalar" in ozet and "alt surec cikis kodu 3" in ozet


def test_calistir_kos_ile_repo_kesfi(tmp_path):
    """`--kok` altindaki repolari kesfeder; her biri icin rapor yazilir."""
    t = _temel(tmp_path)
    proc = run_module_cli(
        "calistir", "--gorev", str(t["gorev"]), "--kok", str(tmp_path / "projeler"),
        "--cikti", str(t["cikti"]), "--cor", str(t["cor"]), cwd=tmp_path,
    )
    assert proc.returncode == 0, proc.stderr
    assert (t["cikti"] / "r.md").is_file()
    assert (t["cikti"] / "s.md").is_file()


# --------------------------------------------------------------------------
# hata izolasyonu
# --------------------------------------------------------------------------


def test_hata_tek_repo_digerlerini_birdIRMEZ(tmp_path):
    """Bir repo hata verse de digerleri calisir; cikis kodu 1, hata izole edilir."""
    t = _temel(tmp_path)
    # Yalniz ikinci repo icin hata: argv'ye gore degil, cwd'ye gore ayiraciz.
    # Bunun yerine `cor` betigini repo adina gore hata yapacak sekilde yaziyoruz.
    t["cor"].write_text(
        "#!{}\nimport os, sys\nsys.stdin.read()\n"
        "if 's' in os.path.basename(os.getcwd()):\n"
        "    sys.stderr.write('hata\\n'); sys.exit(3)\n"
        "print('# rapor\\n')\n".format(__import__('sys').executable),
        encoding="utf-8",
    )
    t["cor"].chmod(0o755)
    proc = _calistir(tmp_path, "--json", **t)
    assert proc.returncode == BULGU_KODU, proc.stdout
    veri = json.loads(proc.stdout)
    durumlar = {s["ad"]: s["durum"] for s in veri["sonuclar"]}
    assert durumlar == {"r": "ok", "s": "hata"}
    assert veri["ozet"] == {"toplam": 2, "ok": 1, "hata": 1, "zaman-asimi": 0}


def test_cor_yok_bulunamadi_hata_olarak_islenir(tmp_path):
    """`--cor` calistirilamaz dosya: durum 'hata' olur, cikis 1 (traceback yok)."""
    t = _temel(tmp_path)
    yok = tmp_path / "olmayan-cor"
    proc = run_module_cli(
        "calistir", "--gorev", str(t["gorev"]), "--cikti", str(t["cikti"]),
        "--cor", str(yok), "--repo", str(t["repolar"][0]), "--json", cwd=tmp_path,
    )
    assert proc.returncode == BULGU_KODU, proc.stdout
    veri = json.loads(proc.stdout)
    assert veri["sonuclar"][0]["durum"] == "hata"
    assert "cor bulunamadi" in veri["sonuclar"][0]["hata"]
    assert "Traceback" not in proc.stderr


def test_zaman_asimi_sureci_oldurur(tmp_path):
    """Uyuyan alt surec zaman asiminda oldurulur; durum 'zaman-asimi', cikis 1."""
    t = _temel(tmp_path)
    cor = sahte_cor(tmp_path / "bin" / "cor", vaka="uyur", uyku=30)
    proc = run_module_cli(
        "calistir", "--gorev", str(t["gorev"]), "--cikti", str(t["cikti"]),
        "--cor", str(cor), "--repo", str(t["repolar"][0]), "--zaman-asimi", "1",
        "--json", cwd=tmp_path,
    )
    assert proc.returncode == BULGU_KODU, proc.stdout
    veri = json.loads(proc.stdout)
    assert veri["sonuclar"][0]["durum"] == "zaman-asimi"
    assert veri["ozet"]["zaman-asimi"] == 1
    assert veri["sonuclar"][0]["sure_sn"] < 20  # 30sn uyku beklemeden dondu


# --------------------------------------------------------------------------
# guvenlik: arac listeleri ve yasakli dizeler
# --------------------------------------------------------------------------


def test_varsayilan_arac_listesi_salt_okunur(tmp_path):
    """Varsayilan: Read,Glob,Grep -- yazma araci YOK.

    `acceptEdits` bayragindaki "Edit" ile karsiastirmamak icin arac listesi
    `--allowedTools` degerinden okunur.
    """
    t = _temel(tmp_path)
    proc = _calistir(tmp_path, "--kuru", **t)
    assert proc.returncode == 0, proc.stderr
    araclar = proc.stdout.split("--allowedTools ")[1].splitlines()[0].strip()
    assert araclar == "Read,Glob,Grep"
    assert set(araclar.split(",")) == {"Read", "Glob", "Grep"}


def test_duzenle_arac_listesini_genisletir(tmp_path):
    """`--duzenle`: Read,Write,Edit,Bash,Glob,Grep."""
    t = _temel(tmp_path)
    proc = _calistir(tmp_path, "--kuru", "--duzenle", **t)
    assert proc.returncode == 0, proc.stderr
    assert "Read,Write,Edit,Bash,Glob,Grep" in proc.stdout


def test_kurulan_argvde_yasakli_dize_yoktur(tmp_path):
    """Baglayici kural: argv'de `--dangerously-skip-permissions`/`bypassPermissions` YOK."""
    t = _temel(tmp_path)
    proc = _calistir(tmp_path, "--kuru", "--duzenle", **t)
    assert proc.returncode == 0, proc.stderr
    assert "--dangerously-skip-permissions" not in proc.stdout
    assert "bypassPermissions" not in proc.stdout


def test_argv_olustur_yasakli_dize_ekleyince_hata_verir():
    """Guvenlik: yasakli dizeler kurulamaz (dogrudan birim testi)."""
    import pytest
    from filo.calistir import CalistirmaHatasi, argv_olustur

    temiz = argv_olustur("cor", "m", "Read,Glob,Grep")
    assert "bypassPermissions" not in temiz
    assert temiz[0] == "cor" and temiz[1] == "claude" and temiz[2] == "-p"
    with pytest.raises(CalistirmaHatasi, match="guvenlik ihlali"):
        argv_olustur("cor", "bypassPermissions", "Read")


def test_argv_permission_mode_accept_edittir():
    """Izin kipi `acceptEdits`'tir; bypass degildir."""
    from filo.calistir import argv_olustur

    argv = argv_olustur("cor", "m", "Read")
    assert argv[argv.index("--permission-mode") + 1] == "acceptEdits"


def test_kuru_calistirma_hicbir_alt_surec_baslatmaz(tmp_path):
    """--kuru: plani gosterir ama rapor/cikti YAZMAZ, alt surec calismaz."""
    t = _temel(tmp_path)
    proc = _calistir(tmp_path, "--kuru", **t)
    assert proc.returncode == 0, proc.stderr
    assert "KURU CALISTIRMA" in proc.stderr
    assert "argv:" in proc.stdout and "cwd:" in proc.stdout
    assert not t["cikti"].exists()


# --------------------------------------------------------------------------
# cikti dizini kurallari
# --------------------------------------------------------------------------


def test_cikti_dosyasi_ustune_yazilmaz(tmp_path):
    """Mevcut rapor dosyasi varsa HATA (cikis 2), icerik degismez."""
    t = _temel(tmp_path)
    t["cikti"].mkdir(parents=True)
    mevcut = t["cikti"] / "r.md"
    mevcut.write_text("KURUCU ICERIK\n", encoding="utf-8")
    proc = _calistir(tmp_path, **t)
    assert proc.returncode == KULLANIM_HATASI, proc.stdout
    assert "uzerine yazilmadi" in proc.stderr
    assert mevcut.read_text(encoding="utf-8") == "KURUCU ICERIK\n"


def test_ozet_dosyasi_ustune_yazilmaz(tmp_path):
    """Mevcut OZET.md varsa HATA (cikis 2)."""
    t = _temel(tmp_path)
    t["cikti"].mkdir(parents=True)
    (t["cikti"] / "OZET.md").write_text("OZET ICERIK\n", encoding="utf-8")
    proc = _calistir(tmp_path, **t)
    assert proc.returncode == KULLANIM_HATASI, proc.stdout
    assert (t["cikti"] / "OZET.md").read_text(encoding="utf-8") == "OZET ICERIK\n"


# --------------------------------------------------------------------------
# kullanim hatalari (cikis 2)
# --------------------------------------------------------------------------


def test_repo_verilmezse_cikis_2(tmp_path):
    """En az biri `--repo`/`--kok` zorunlu; hicbiri yoksa cikis 2."""
    t = _temel(tmp_path)
    proc = run_module_cli(
        "calistir", "--gorev", str(t["gorev"]), "--cikti", str(t["cikti"]),
        "--cor", str(t["cor"]), cwd=tmp_path,
    )
    assert proc.returncode == KULLANIM_HATASI, proc.stdout
    assert "--repo" in proc.stderr and "--kok" in proc.stderr


def test_yok_repo_yolu_cikis_2(tmp_path):
    """Var olmayan --repo yolu: kesif hatasi -> cikis 2."""
    t = _temel(tmp_path)
    proc = run_module_cli(
        "calistir", "--gorev", str(t["gorev"]), "--cikti", str(t["cikti"]),
        "--cor", str(t["cor"]), "--repo", str(tmp_path / "yok"), cwd=tmp_path,
    )
    assert proc.returncode == KULLANIM_HATASI
    assert "bulunamadi" in proc.stderr


def test_olmayan_gorev_dosyasi_cikis_2(tmp_path):
    """Var olmayan --gorev dosyasi -> cikis 2, Turkce 'okunamadi'."""
    t = _temel(tmp_path)
    proc = run_module_cli(
        "calistir", "--gorev", str(tmp_path / "yok.txt"), "--cikti", str(t["cikti"]),
        "--cor", str(t["cor"]), "--repo", str(t["repolar"][0]), cwd=tmp_path,
    )
    assert proc.returncode == KULLANIM_HATASI
    assert "okunamadi" in proc.stderr


def test_bos_gorev_dosyasi_cikis_2(tmp_path):
    """Bos gorev dosyasi -> cikis 2 (bos istem calistirilmaz)."""
    t = _temel(tmp_path)
    (tmp_path / "gorev.txt").write_text("   \n", encoding="utf-8")
    proc = _calistir(tmp_path, **t)
    assert proc.returncode == KULLANIM_HATASI
    assert "bos" in proc.stderr


# --------------------------------------------------------------------------
# paralellik sinirlari
# --------------------------------------------------------------------------


def test_paralel_ustu_sinir_reddedilir_cikis_2(tmp_path):
    """`--paralel 9` (> 8) reddedilir: cikis 2, kural mesaji."""
    t = _temel(tmp_path)
    proc = _calistir(tmp_path, "--paralel", "9", **t)
    assert proc.returncode == KULLANIM_HATASI, proc.stdout
    assert "--paralel" in proc.stderr and "1..8" in proc.stderr


def test_paralel_sifir_cikis_2(tmp_path):
    """`--paralel 0` (< 1) reddedilir."""
    t = _temel(tmp_path)
    proc = _calistir(tmp_path, "--paralel", "0", **t)
    assert proc.returncode == KULLANIM_HATASI
    assert "--paralel" in proc.stderr


def test_paralel_bir_calisir(tmp_path):
    """`--paralel 1` gecerli: sirali calisir, cikis 0."""
    t = _temel(tmp_path)
    proc = _calistir(tmp_path, "--paralel", "1", "--json", **t)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["ozet"]["toplam"] == 2


def test_paralel_8_gecerli(tmp_path):
    """Sinir degeri `--paralel 8` kabul edilir."""
    t = _temel(tmp_path)
    proc = _calistir(tmp_path, "--paralel", "8", **t)
    assert proc.returncode == 0, proc.stderr


# --------------------------------------------------------------------------
# model / cikti varsayilanlari
# --------------------------------------------------------------------------


def test_model_env_cor_model_gecerlidir(tmp_path):
    """COR_MODEL varsa o model kullanilir (argv'de gorunur)."""
    t = _temel(tmp_path)
    proc = run_module_cli(
        "calistir", "--gorev", str(t["gorev"]), "--cikti", str(t["cikti"]),
        "--cor", str(t["cor"]), "--repo", str(t["repolar"][0]), "--kuru",
        cwd=tmp_path, env_ek={"COR_MODEL": "ozel/model-x"},
    )
    assert proc.returncode == 0, proc.stderr
    assert "ozel/model-x" in proc.stdout


def test_model_argumani_env_yi_ezer(tmp_path):
    """`--model` verilirse COR_MODEL gecersiz sayilir."""
    t = _temel(tmp_path)
    proc = run_module_cli(
        "calistir", "--gorev", str(t["gorev"]), "--cikti", str(t["cikti"]),
        "--cor", str(t["cor"]), "--repo", str(t["repolar"][0]), "--kuru",
        "--model", "baska/model-y", cwd=tmp_path, env_ek={"COR_MODEL": "ozel/model-x"},
    )
    assert proc.returncode == 0, proc.stderr
    assert "baska/model-y" in proc.stdout and "ozel/model-x" not in proc.stdout


def test_varsayilan_cikti_dizini_zaman_damgali(tmp_path):
    """--cikti verilmezse ./filo-ciktilari/<zaman-damgasi>/ kullanilir."""
    t = _temel(tmp_path)
    proc = run_module_cli(
        "calistir", "--gorev", str(t["gorev"]), "--cor", str(t["cor"]),
        "--repo", str(t["repolar"][0]), cwd=tmp_path,
    )
    assert proc.returncode == 0, proc.stderr
    kok = tmp_path / "filo-ciktilari"
    assert kok.is_dir(), "varsayilan cikti dizini olusmadi"
    (tarih,) = list(kok.iterdir())
    assert len(tarih.name) == len("2026-01-01T00-00-00Z")
    assert (tarih / "r.md").is_file()