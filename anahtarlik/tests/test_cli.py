"""CLI sozlesmesi: `python -m anahtarlik` GERCEKTEN subprocess olarak calistirilir.

ANAHTARLIK_DIR ve ATLAS_DB gecici dizine yonlendirilir (run_module_cli ayrica
HOME'u da cevirir): gercek `~/.anahtarlik` ya tuz dosyasi YAZILMAZ.

BAGLAYICI KURAL TESTI: yapay deger `SENTINEL_DEGER_...` hicbir cikti ve hicbir
dosyada gorunmemeli.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

from conftest import dosya_agaci, repo_kur, run_module_cli

KULLANIM_HATASI = 2

SIR = "SENTINEL_DEGER_0123456789_ABCDEFGHIJKLMNOPQRSTUVWXYZ"
SIR2 = "SENTINEL_DEGER_farkli_ve_uzun_bir_sifre_0987654321"


def _hepsi_yok(*parcalar: str) -> None:
    """Sentinel hicbir metinde gecmesin."""
    for parca in parcalar:
        assert SIR not in parca, "HAM DEGER SIZDI: " + parca[:400]
        assert SIR2 not in parca, "HAM DEGER SIZDI: " + parca[:400]


# --------------------------------------------------------------------------
# tara
# --------------------------------------------------------------------------


def test_tara_envanteri_yazar_ve_cikis_0(tmp_path, ortam):
    repo = repo_kur(tmp_path / "r", f"GITHUB_TOKEN={SIR}\n")
    proc = run_module_cli("tara", "--root", str(repo), cwd=tmp_path, env_ek=ortam)
    assert proc.returncode == 0, proc.stderr
    veri = json.loads((tmp_path / "anahtarlik" / "envanter.json").read_text(encoding="utf-8"))
    assert veri["surum"] == 1
    assert veri["repolar"][0]["anahtarlar"][0]["ad"] == "GITHUB_TOKEN"


def test_tara_ciktisinda_ham_deger_yok(tmp_path, ortam):
    """stdout + stderr + envanter.json: sentinel YOK."""
    repo = repo_kur(tmp_path / "r", f"GITHUB_TOKEN={SIR}\n")
    proc = run_module_cli("tara", "--root", str(repo), cwd=tmp_path, env_ek=ortam)
    assert proc.returncode == 0, proc.stderr
    _hepsi_yok(proc.stdout, proc.stderr)
    _hepsi_yok((tmp_path / "anahtarlik" / "envanter.json").read_text(encoding="utf-8"))


def test_tara_json_ve_tablo_temiz(tmp_path, ortam):
    """--json ve tablo modu ikisi de temiz; tablo sadece ad/izi gosterir."""
    repo = repo_kur(tmp_path / "r", f"GITHUB_TOKEN={SIR}\nDIGER_API={SIR2}\n")
    env = {**ortam, "PYTHONIOENCODING": "utf-8"}
    ham = run_module_cli("tara", "--json", "--root", str(repo), cwd=tmp_path, env_ek=env)
    assert ham.returncode == 0, ham.stderr
    _hepsi_yok(ham.stdout)
    assert json.loads(ham.stdout)["toplam"] == 2

    tablo = run_module_cli("tara", "--root", str(repo), cwd=tmp_path, env_ek=env)
    assert tablo.returncode == 0, tablo.stderr
    _hepsi_yok(tablo.stdout)
    assert "GITHUB_TOKEN" in tablo.stdout


def test_tara_ayni_siri_iki_repoda_bulur(tmp_path, ortam):
    """Ayni deger iki repoda: tablo '2 ayni deger' ozetini yazar, iz esittir."""
    a = repo_kur(tmp_path / "a", f"GITHUB_TOKEN={SIR}\n")
    b = repo_kur(tmp_path / "b", f"GITHUB_TOKEN={SIR}\n", ad=".env.production")
    proc = run_module_cli(
        "tara", "--root", str(a), "--root", str(b), cwd=tmp_path, env_ek=ortam
    )
    assert proc.returncode == 0, proc.stderr
    _hepsi_yok(proc.stdout)
    assert "1 ayni deger" in proc.stdout
    veri = json.loads((tmp_path / "anahtarlik" / "envanter.json").read_text(encoding="utf-8"))
    izler = [r["anahtarlar"][0]["izi"] for r in veri["repolar"]]
    assert izler[0] == izler[1]


def test_tara_coklu_root_ve_atlas_db_yok_cikis_2(tmp_path, ortam):
    """--root verilmezse atlas DB'ye bakar; yoksa uyari + cikis 2 (traceback yok)."""
    proc = run_module_cli("tara", cwd=tmp_path, env_ek=ortam)
    assert proc.returncode == KULLANIM_HATASI, proc.stdout
    assert "atlas" in proc.stderr
    assert "Traceback" not in proc.stderr


def test_tara_olmayan_kok_cikis_2(tmp_path, ortam):
    proc = run_module_cli("tara", "--root", str(tmp_path / "yok"), cwd=tmp_path, env_ek=ortam)
    assert proc.returncode == KULLANIM_HATASI
    assert "bulunamadi" in proc.stderr
    assert "Traceback" not in proc.stderr


# --------------------------------------------------------------------------
# goster
# --------------------------------------------------------------------------


def test_goster_envanteri_yazar(tmp_path, ortam):
    repo = repo_kur(tmp_path / "r", f"GITHUB_TOKEN={SIR}\n")
    assert run_module_cli("tara", "--root", str(repo), cwd=tmp_path, env_ek=ortam).returncode == 0
    proc = run_module_cli("goster", cwd=tmp_path, env_ek=ortam)
    assert proc.returncode == 0, proc.stderr
    assert "GITHUB_TOKEN" in proc.stdout
    _hepsi_yok(proc.stdout)


def test_goster_envanter_yokken_cikis_2(tmp_path, ortam):
    proc = run_module_cli("goster", cwd=tmp_path, env_ek=ortam)
    assert proc.returncode == KULLANIM_HATASI
    assert "envanter bulunamadi" in proc.stderr
    assert "tara" in proc.stderr
    assert proc.stdout.strip() == ""
    assert "Traceback" not in proc.stderr


def test_goster_bozuk_envanter_cikis_2(tmp_path, ortam):
    dizin = tmp_path / "anahtarlik"
    dizin.mkdir()
    (dizin / "envanter.json").write_text("{bozuk", encoding="utf-8")
    proc = run_module_cli("goster", cwd=tmp_path, env_ek=ortam)
    assert proc.returncode == KULLANIM_HATASI
    assert "envanter bulunamadi" in proc.stderr


def test_goster_json_gecerli_json(tmp_path, ortam):
    repo = repo_kur(tmp_path / "r", f"GITHUB_TOKEN={SIR}\n")
    run_module_cli("tara", "--root", str(repo), cwd=tmp_path, env_ek=ortam)
    proc = run_module_cli("goster", "--json", cwd=tmp_path, env_ek=ortam)
    assert proc.returncode == 0, proc.stderr
    _hepsi_yok(proc.stdout)
    assert json.loads(proc.stdout)["repolar"][0]["anahtarlar"][0]["ad"] == "GITHUB_TOKEN"


# --------------------------------------------------------------------------
# not / eski
# --------------------------------------------------------------------------


def test_not_kaydeder_ve_eski_dikkat_etmez(tmp_path, ortam):
    repo = repo_kur(tmp_path / "r", f"GITHUB_TOKEN={SIR}\n")
    run_module_cli("tara", "--root", str(repo), cwd=tmp_path, env_ek=ortam)
    proc = run_module_cli(
        "not", "GITHUB_TOKEN", "--tarih", "2099-01-01", cwd=tmp_path, env_ek=ortam
    )
    assert proc.returncode == 0, proc.stderr
    _hepsi_yok(proc.stdout)
    eski = run_module_cli("eski", cwd=tmp_path, env_ek=ortam)
    assert eski.returncode == 0, eski.stderr
    assert "GITHUB_TOKEN" not in eski.stdout


def test_eski_notsuz_anahtari_listeler(tmp_path, ortam):
    repo = repo_kur(tmp_path / "r", f"GITHUB_TOKEN={SIR}\n")
    run_module_cli("tara", "--root", str(repo), cwd=tmp_path, env_ek=ortam)
    proc = run_module_cli("eski", cwd=tmp_path, env_ek=ortam)
    assert proc.returncode == 0, proc.stderr
    assert "GITHUB_TOKEN" in proc.stdout
    _hepsi_yok(proc.stdout, proc.stderr)


def test_eski_envanter_yoksa_cikis_2(tmp_path, ortam):
    proc = run_module_cli("eski", cwd=tmp_path, env_ek=ortam)
    assert proc.returncode == KULLANIM_HATASI
    assert "envanter bulunamadi" in proc.stderr


def test_eski_gun_secenegi(tmp_path, ortam):
    """`--gun` esigi degistirilince ayni not farkli sonuc verir (45 gun onceki not)."""
    bugun = date.today() - timedelta(days=45)
    repo = repo_kur(tmp_path / "r", f"GITHUB_TOKEN={SIR}\n")
    run_module_cli("tara", "--root", str(repo), cwd=tmp_path, env_ek=ortam)
    run_module_cli(
        "not", "GITHUB_TOKEN", "--tarih", bugun.isoformat(), cwd=tmp_path, env_ek=ortam
    )
    gun30 = run_module_cli("eski", "--gun", "30", cwd=tmp_path, env_ek=ortam)
    gun90 = run_module_cli("eski", "--gun", "90", cwd=tmp_path, env_ek=ortam)
    assert "GITHUB_TOKEN" in gun30.stdout
    assert "GITHUB_TOKEN" not in gun90.stdout


def test_eski_henuz_not_yoksa_durum_mesaji(tmp_path, ortam):
    repo = repo_kur(tmp_path / "r", f"GITHUB_TOKEN={SIR}\n")
    run_module_cli("tara", "--root", str(repo), cwd=tmp_path, env_ek=ortam)
    run_module_cli("not", "GITHUB_TOKEN", "--tarih", "2099-01-01", cwd=tmp_path, env_ek=ortam)
    proc = run_module_cli("eski", cwd=tmp_path, env_ek=ortam)
    assert "yok" in proc.stdout


# --------------------------------------------------------------------------
# genel sozlesme / izolasyon
# --------------------------------------------------------------------------


def test_tara_gercek_home_a_dokunmaz(tmp_path, ortam):
    """HOME gecici: `~/.anahtarlik` olusmaz (ANAHTARLIK_DIR yonlendirmesi sayesinde)."""
    repo = repo_kur(tmp_path / "r", f"A={SIR}\n")
    proc = run_module_cli("tara", "--root", str(repo), cwd=tmp_path, env_ek=ortam)
    assert proc.returncode == 0, proc.stderr
    assert not (tmp_path / ".anahtarlik").exists(), "gercek ev dizinine yazildi"


def test_yardim_sifir_cikar(tmp_path, ortam):
    proc = run_module_cli("--help", cwd=tmp_path, env_ek=ortam)
    assert proc.returncode == 0
    for komut in ("tara", "goster", "not", "eski"):
        assert komut in proc.stdout


def test_alt_komut_zorunlu(tmp_path, ortam):
    proc = run_module_cli(cwd=tmp_path, env_ek=ortam)
    assert proc.returncode == KULLANIM_HATASI
    assert "usage" in proc.stderr.lower()


def test_not_bozuk_tarih_cikis_2(tmp_path, ortam):
    proc = run_module_cli("not", "A", "--tarih", "31-12-2026", cwd=tmp_path, env_ek=ortam)
    assert proc.returncode == KULLANIM_HATASI
    assert "YYYY-MM-DD" in proc.stderr
    assert "Traceback" not in proc.stderr


def test_uygulama_sonrasi_gedici_dosya_yok(tmp_path, ortam):
    """Iki kez tara: gecici .tmp birakmaz (atomik yazim)."""
    repo = repo_kur(tmp_path / "r", f"A={SIR}\n")
    for _ in range(2):
        run_module_cli("tara", "--root", str(repo), cwd=tmp_path, env_ek=ortam)
    agac = dosya_agaci(tmp_path / "anahtarlik")
    assert not [a for a in agac if a.endswith(".tmp")], agac


def test_tuz_dosyasi_kalici(anahtarlik_dir, tmp_path):
    """Tuz bir kez uretilir, izler sonraki calismalarda ayni kalir."""
    repo = repo_kur(tmp_path / "r", f"A={SIR}\n")
    run_module_cli("tara", "--root", str(repo), cwd=tmp_path,
                   env_ek={"ANAHTARLIK_DIR": str(anahtarlik_dir)})
    ilk = (anahtarlik_dir / "envanter.json").read_text(encoding="utf-8")
    run_module_cli("tara", "--root", str(repo), cwd=tmp_path,
                   env_ek={"ANAHTARLIK_DIR": str(anahtarlik_dir)})
    ikinci = (anahtarlik_dir / "envanter.json").read_text(encoding="utf-8")
    assert json.loads(ilk)["repolar"] == json.loads(ikinci)["repolar"]