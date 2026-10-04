"""Envanter: tarama, atlama, ayni deger, notlar, atomik yazim, 90 gun."""

from __future__ import annotations

import json
import subprocess
import time
from datetime import date, timedelta
from pathlib import Path

import pytest

from anahtarlik import envanter
from conftest import repo_kur

SIR = "SENTINEL_DEGER_0123456789_ABCDEFGHIJ"  # 42 karakter -> 'orta' sinifi


def _kart(veri: dict, ad: str = "GITHUB_TOKEN") -> dict:
    for repo in veri["repolar"]:
        for kart in repo["anahtarlar"]:
            if kart["ad"] == ad:
                return kart
    raise AssertionError(f"{ad} envanterde yok: {veri}")


# --------------------------------------------------------------------------
# tarama
# --------------------------------------------------------------------------


def test_tara_adi_izi_dosya_uzunluk(anahtarlik_dir, tmp_path):
    """Her anahtar: ad + parmak izi + repo'ya gore goreli dosya + uzunluk sinifi."""
    repo = repo_kur(tmp_path / "r", f"GITHUB_TOKEN={SIR}\n")
    veri = envanter.tara([repo])
    kart = _kart(veri)
    assert kart["ad"] == "GITHUB_TOKEN"
    assert len(kart["izi"]) == 8
    assert kart["dosya"] == ".env"
    assert kart["uzunluk_sinifi"] == "orta"


def test_tara_uzunluk_siniflari(anahtarlik_dir, tmp_path):
    """>=64 'uzun', >=24 'orta', kisa degerde 'kisa' ve izi None."""
    repo = repo_kur(
        tmp_path / "r",
        f"A={'a' * 70}\nB={'b' * 30}\nC={'c' * 5}\n",
    )
    veri = envanter.tara([repo])
    assert _kart(veri, "A")["uzunluk_sinifi"] == "uzun"
    assert _kart(veri, "B")["uzunluk_sinifi"] == "orta"
    assert _kart(veri, "C")["uzunluk_sinifi"] == "kisa"
    assert _kart(veri, "C")["izi"] is None


def test_tara_ornek_env_dosyalarini_atlar(anahtarlik_dir, tmp_path):
    """.env.example taranmaz: sablonun degeri gercek bir sir degil."""
    repo = repo_kur(tmp_path / "r", f"GITHUB_TOKEN={SIR}\n", ad=".env.example")
    assert envanter.tara([repo])["toplam"] == 0


def test_tara_atlanan_dizinlere_girmez(anahtarlik_dir, tmp_path):
    """node_modules/.venv/.git altindaki .env gorulmez."""
    kok = tmp_path / "r"
    for atlanacak in ("node_modules", ".venv", ".git", "vendor", "dist", "build"):
        (kok / atlanacak).mkdir(parents=True)
        (kok / atlanacak / ".env").write_text(f"X={SIR}\n", encoding="utf-8")
    (kok / ".git").mkdir(exist_ok=True)
    assert envanter.tara([kok])["toplam"] == 0


def test_tara_derinlik_siniri(anahtarlik_dir, tmp_path):
    """Kok + 4 seviye: `.env` bulunur, kok + 5 seviye: bulunmaz."""
    kok = tmp_path / "r"
    (kok / "a" / "b" / "c" / "d").mkdir(parents=True)
    (kok / "a" / "b" / "c" / "d" / ".env").write_text(f"DERIN={SIR}\n", encoding="utf-8")
    assert _kart(envanter.tara([kok]), "DERIN")["dosya"] == "a/b/c/d/.env"

    derin = tmp_path / "r2"
    (derin / "a" / "b" / "c" / "d" / "e").mkdir(parents=True)
    (derin / "a" / "b" / "c" / "d" / "e" / ".env").write_text(
        f"DERIN={SIR}\n", encoding="utf-8"
    )
    assert envanter.tara([derin])["toplam"] == 0


def test_tara_bir_mb_ustu_dosya_atlanir(anahtarlik_dir, tmp_path):
    """1 MB'den buyuk env dosyasi okunmaz, `atlanan` listesine neden yazilir."""
    repo = tmp_path / "r"
    (repo / ".git").mkdir(parents=True)
    (repo / ".env").write_text(
        f"A={SIR}\n" + "# " + "x" * envanter.AZAMI_DOSYA, encoding="utf-8"
    )
    veri = envanter.tara([repo])
    assert veri["toplam"] == 0
    assert any("buyuk" in neden for neden in veri["atlanan"]), veri["atlanan"]


def test_tara_anahtarsiz_env_dosyasi_repo_yazmaz(anahtarlik_dir, tmp_path):
    """Anahtar bulunamayan repo envantere GIRMEZ (bos repo raporu sutrultur)."""
    repo = repo_kur(tmp_path / "r", "# sadece yorum\n")
    veri = envanter.tara([repo])
    assert veri["repolar"] == [] and veri["toplam"] == 0


def test_tara_anahtar_sirasi_kararli(anahtarlik_dir, tmp_path):
    repo = repo_kur(tmp_path / "r", "Z=1\nA=2\nM=3\n")
    veri = envanter.tara([repo])
    assert [k["ad"] for k in veri["repolar"][0]["anahtarlar"]] == ["A", "M", "Z"]


# --------------------------------------------------------------------------
# ayni deger
# --------------------------------------------------------------------------


def test_ayni_deger_iki_repoda(anahtarlik_dir, tmp_path):
    """Ayni sir iki repoda: ayni iz, FARKLI repo -> tekrarli isaretlenir."""
    a = repo_kur(tmp_path / "a", f"GITHUB_TOKEN={SIR}\n")
    b = repo_kur(tmp_path / "b", f"GITHUB_TOKEN={SIR}\n", ad=".env.production")
    veri = envanter.tara([a, b])
    assert (
        veri["repolar"][0]["anahtarlar"][0]["izi"]
        == veri["repolar"][1]["anahtarlar"][0]["izi"]
    )

    tekrarli = envanter.ayni_deger(veri)
    assert len(tekrarli) == 1
    assert tekrarli[0]["adlar"] == ["GITHUB_TOKEN"]
    assert len(tekrarli[0]["kullanim"]) == 2


def test_ayni_deger_ayni_repoda_sayilmaz(anahtarlik_dir, tmp_path):
    """Ayni repoda iki yerde ayni deger: SORUN DEGIL (repo bazli degil dosya bazli)."""
    repo = repo_kur(tmp_path / "r", f"A={SIR}\n")
    (repo / "alt").mkdir()
    (repo / "alt" / ".env").write_text(f"B={SIR}\n", encoding="utf-8")
    assert envanter.ayni_deger(envanter.tara([repo])) == []


def test_ayni_deger_farkli_deger_olmaz(anahtarlik_dir, tmp_path):
    a = repo_kur(tmp_path / "a", f"A={SIR}\n")
    b = repo_kur(tmp_path / "b", f"A={SIR}farkli\n")
    assert envanter.ayni_deger(envanter.tara([a, b])) == []


# --------------------------------------------------------------------------
# kaydet / yukle
# --------------------------------------------------------------------------


def test_kaydet_yukle_gidis_donus(anahtarlik_dir, tmp_path):
    repo = repo_kur(tmp_path / "r", f"GITHUB_TOKEN={SIR}\n")
    veri = envanter.tara([repo])
    yol = envanter.kaydet(veri)
    assert yol == anahtarlik_dir / "envanter.json"
    assert envanter.yukle() == veri


def test_kaydet_gedici_tmp_birakmaz(anahtarlik_dir, tmp_path):
    repo = repo_kur(tmp_path / "r", f"A={SIR}\n")
    for _ in range(3):
        envanter.kaydet(envanter.tara([repo]))
    assert not [a for a in _agac(anahtarlik_dir) if a.endswith(".tmp")]


def _agac(yol):
    return [p.relative_to(yol).as_posix() for p in yol.rglob("*") if p.is_file()]


def test_yukle_yoksa_none(anahtarlik_dir):
    assert envanter.yukle() is None


def test_yukle_bozuk_json_none(anahtarlik_dir):
    anahtarlik_dir.mkdir(parents=True, exist_ok=True)
    (anahtarlik_dir / "envanter.json").write_text("{bozuk", encoding="utf-8")
    assert envanter.yukle() is None


def test_yazilamayan_dizin_envanter_hatasi(anahtarlik_dir, tmp_path, monkeypatch):
    """Salt-okunur/kilitli durum: OSError -> EnvanterHatasi (cikis 2, iz yok)."""
    engel = tmp_path / "engel"
    engel.write_text("bu bir dosya", encoding="utf-8")
    repo = repo_kur(tmp_path / "r", f"A={SIR}\n")
    veri = envanter.tara([repo])
    monkeypatch.setattr(envanter, "_yol", lambda ad=envanter.VARSAYILAN_AD: engel / "alt" / ad)
    try:
        envanter.kaydet(veri)
    except envanter.EnvanterHatasi as exc:
        assert "Traceback" not in str(exc)
    else:
        raise AssertionError("EnvanterHatasi bekleniyordu")


# --------------------------------------------------------------------------
# notlar / eski
# --------------------------------------------------------------------------


def _envanter(ad: str, iz: str = "abcd1234") -> dict:
    return {
        "surum": 1,
        "repolar": [{"repo": "/r", "anahtarlar": [{"ad": ad, "izi": iz, "dosya": ".env"}]}],
    }


def test_eski_notsuz_anahtari_listeler():
    assert [k["ad"] for k in envanter.eski_olanlar(_envanter("A"))] == ["A"]


def test_eski_yeni_not_listelenmez():
    """Bugunun tarihiyle not yazildiysa `eski` listesinde DEGILDIR."""
    notlar = {"A": {"tarih": date.today().isoformat()}}
    assert envanter.eski_olanlar(_envanter("A"), notlar) == []


def test_eski_90_gun_kurali():
    """90 gunu gecen not listede, 90 gunu gecmeyen listede degil."""
    bugun = date.today()
    assert envanter.eski_olanlar(
        _envanter("A"), {"A": {"tarih": (bugun - timedelta(days=91)).isoformat()}}
    )
    assert (
        envanter.eski_olanlar(
            _envanter("A"), {"A": {"tarih": (bugun - timedelta(days=10)).isoformat()}}
        )
        == []
    )


def test_eski_gun_esigi_degistirilebilir():
    """--gun 30: 45 gun onceki not artik ESKI sayilir."""
    notlar = {"A": {"tarih": (date.today() - timedelta(days=45)).isoformat()}}
    env = _envanter("A")
    assert envanter.eski_olanlar(env, notlar, gun=30) != []
    assert envanter.eski_olanlar(env, notlar, gun=90) == []


def test_eski_bozuk_tarih_eski_sayilir():
    assert envanter.eski_olanlar(_envanter("A"), {"A": {"tarih": "bozuk"}})


def test_eski_simdi_denetimi(anahtarlik_dir):
    """simdi verilince tarih karsilastirması sabitlenir (deterministik test)."""
    gecmis = date.today() - timedelta(days=200)
    notlar = {"A": {"tarih": gecmis.isoformat()}}
    assert envanter.eski_olanlar(_envanter("A"), notlar, 90, simdi=time.time())


def test_not_ekle_ustune_yazar(anahtarlik_dir):
    envanter.not_ekle("A", "2026-01-01", "ilk")
    envanter.not_ekle("A", "2026-06-01", "guncellendi")
    assert envanter.notlari_yukle()["A"]["tarih"] == "2026-06-01"


def test_not_ekle_aciklama_istege_bagli(anahtarlik_dir):
    envanter.not_ekle("A", "2026-01-01")
    assert envanter.notlari_yukle()["A"]["aciklama"] is None


def test_notlar_yoksa_eski_listesinde(anahtarlik_dir):
    assert envanter.notlari_yukle() == {}
    assert envanter.eski_olanlar(_envanter("A")) != []


# --------------------------------------------------------------------------
# tablo
# --------------------------------------------------------------------------


def test_tablo_sadece_ad_repo_dosya_izi(anahtarlik_dir, tmp_path):
    """Tablodaki hucreler yalniz bu dort alan; deger/uzunluk YOK."""
    repo = repo_kur(tmp_path / "r", f"GITHUB_TOKEN={SIR}\n")
    veri = envanter.tara([repo])
    metin = envanter.tablo(veri)
    assert SIR not in metin
    assert metin.splitlines()[0].split() == ["ad", "repo", "dosya", "izi"]
    assert "?" not in metin.splitlines()[1], "repo sutunu bos kaldi"
    assert SIR not in json.dumps(veri, ensure_ascii=False)

# --------------------------------------------------------------------------
# Guvenlik: baglanti (junction/symlink) takibi ve yol gecisi
# --------------------------------------------------------------------------


def _junction_kur(hedef: Path, kaynak: Path) -> bool:
    """Windows junction olusturur; olusturamazsa False (test atlanir)."""
    proc = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(hedef), str(kaynak)], capture_output=True
    )
    return proc.returncode == 0


def test_env_dosyalari_junction_disina_cikmaz(tmp_path):
    """Windows junction `os.walk(followlinks=False)` ile IZLENMEZ.

    Repoda `bagli` adli bir junction, repo DISINDAKI bir dizini gosterirse
    oradaki `.env` dosyalari envantere GIRMEMELI: tarama kullanicinin
    kendi belirledigi agacin disina cikamaz.
    """
    repo = repo_kur(tmp_path / "r", "X=1\n")
    disari = tmp_path / "disarida"
    disari.mkdir()
    (disari / ".env").write_text(f"GITHUB_TOKEN={SIR}\n", encoding="utf-8")
    if not _junction_kur(repo / "bagli", disari):
        pytest.skip("junction olusturulamadi")
    bulunan = envanter._env_dosyalari(repo)
    assert not any("bagli" in str(p) for p in bulunan), bulunan


def test_tara_junction_disindaki_siri_gormez(tmp_path):
    """Uctan uca: junction disindaki .env envantere girmez."""
    repo = repo_kur(tmp_path / "r", "X=1\n")
    disari = tmp_path / "disarida"
    disari.mkdir()
    (disari / ".env").write_text(f"GITHUB_TOKEN={SIR}\n", encoding="utf-8")
    if not _junction_kur(repo / "bagli", disari):
        pytest.skip("junction olusturulamadi")
    veri = envanter.tara([repo])
    assert SIR not in json.dumps(veri, ensure_ascii=False)
    assert all("bagli" not in k["dosya"] for r in veri["repolar"] for k in r["anahtarlar"])


def test_baglanti_mi_olmayan_dizin_normal_gecilir(tmp_path):
    """Guvenlik filtresi gecerli dizinleri ELMEMELI (regresyon)."""
    gercek = tmp_path / "gercek"
    gercek.mkdir()
    assert envanter._baglanti_mi(gercek) is False
    assert envanter._baglanti_mi(tmp_path / "yok") is False


# --------------------------------------------------------------------------
# kesif: repo kesfi baglantilari izlemez
# --------------------------------------------------------------------------


def test_kesif_junction_disina_cikmaz(tmp_path):
    """`kesif` de junction'i izlememeli: kok disi bir repo onermeyebilir.

    `--root` verilen agacin disindaki bir dizin tarama kapsamini genisletmez.
    """
    from anahtarlik import kesif

    kok = tmp_path / "kok"
    kok.mkdir()
    disari = tmp_path / "disarida"
    disari.mkdir()
    (disari / ".git").mkdir()  # .git'i olan dizin -> repo sayilir
    if not _junction_kur(kok / "bagli", disari):
        pytest.skip("junction olusturulamadi")
    assert kesif._yuruyerek(kok) == []
    assert kesif._baglanti_mi(disari) is False
