"""`orkestra.quota` testleri (Dalga C).

Ayrıştırıcı YALNIZCA gerçek `proxy.log` biçimini tanır:
`[ISO8601-UTC-ms-Z] openrouter -> <model>` isteğin kendisi. Tanınmayan satır
atlanır ve SAYILIR — hiçbir yerde uydurma değer üretilmez.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import pytest

from orkestra import quota
from orkestra.queue import SEMA

# -- gerçek log biçiminden alınan satırlar (istem/anahtar İÇERMEZ) ----------

SATIR_BASARI = "[2026-09-30T06:15:25.675Z] openrouter -> stealth/space-bunny-alpha (stream)"
SATIR_NORMAL = "[2026-09-30T06:14:02.113Z] openrouter -> stealth/space-bunny-alpha"
SATIR_NEMOTRON = "[2026-09-26T09:02:11.400Z] openrouter -> nvidia/nemotron-3-ultra-550b-a55b:free"
SATIR_GEMMA = "[2026-09-26T08:00:00.000Z] openrouter -> google/gemma-4-31b-it:free"
# Tanınmayan (isten/başlangıç/hata) satırlar — GERÇEK logda da görülüyor:
SATIR_DINLIYOR = "[2026-09-26T07:23:14.146Z] proxy dinliyor: http://127.0.0.1:8787"
SATIR_SIGTERM = "[2026-09-26T07:23:40.549Z] SIGTERM alindi, kapaniyor"
SATIR_HATA = "[2026-09-26T07:23:41.332Z] dinleme hatasi: listen EADDRINUSE: address already in use 127.0.0.1:8787"
SATIR_GECIS = "[2026-09-26T07:23:43.813Z] ucretsiz->ucretli gecisi: test/drifted-model engellendi"
SATIR_BOS = ""
SATIR_COPUK = "[2026-09-30T06:15:25.675Z]  child openrouter -> model"
SATIR_KARSILIKLI = "[2026-09-30T06:15:25.675Z] openrouter -> model ek burada"

TANINAN = [SATIR_BASARI, SATIR_NORMAL, SATIR_NEMOTRON, SATIR_GEMMA]
TANINMAYAN = [SATIR_DINLIYOR, SATIR_SIGTERM, SATIR_HATA, SATIR_GECIS, SATIR_BOS, SATIR_COPUK, SATIR_KARSILIKLI]


@pytest.fixture()
def baglanti():
    b = sqlite3.connect(":memory:")
    b.row_factory = sqlite3.Row
    b.executescript(SEMA)
    yield b
    b.close()


def log_yaz(yol, satirlar, sonuna_yeni_satir=False):
    metin = "\n".join(satirlar)
    if not sonuna_yeni_satir:
        metin += "\n"
    yol.write_text(metin, encoding="utf-8")
    return yol


# -- satir ayrıştırma -------------------------------------------------------


@pytest.mark.parametrize("satir", TANINAN)
def test_bilinen_satirlar_cozulur(satir):
    cozulmus = quota.satir_ayir(satir)
    assert cozulmus is not None
    zaman, model, _hata = cozulmus
    assert model
    assert zaman.tzinfo is not None
    assert zaman.utcoffset().total_seconds() == 0


@pytest.mark.parametrize("satir", TANINMAYAN)
def test_bilinmeyen_satirlar_cozulmez(satir):
    assert quota.satir_ayir(satir) is None


def test_model_adi_dogru_ayristirilir():
    _, model, _ = quota.satir_ayir(SATIR_NEMOTRON)
    assert model == "nvidia/nemotron-3-ultra-550b-a55b:free"


def test_stream_ekleri_modele_karismaz():
    _, model, _ = quota.satir_ayir(SATIR_BASARI)
    assert model == "stealth/space-bunny-alpha"
    assert "(stream)" not in model


def test_milisanesiz_zaman_da_kabul():
    satir = "[2026-09-30T06:15:25Z] openrouter -> a/b:free"
    cozulmus = quota.satir_ayir(satir)
    assert cozulmus is not None


# -- gun siniri UTC ---------------------------------------------------------


def test_gun_anahtari_utc():
    # 23:30 UTC, yerel saat diliminden bagimsiz olarak ayni gun.
    zaman = datetime(2026, 9, 30, 23, 30, tzinfo=timezone.utc)
    assert quota.gun_anahtari(zaman) == "2026-09-30"


def test_gun_siniri_gece_yari_utc():
    yirmi_yedi = datetime(2026, 9, 30, 23, 59, 59, tzinfo=timezone.utc)
    sifir = datetime(2026, 10, 1, 0, 0, 0, tzinfo=timezone.utc)
    assert quota.gun_anahtari(yirmi_yedi) == "2026-09-30"
    assert quota.gun_anahtari(sifir) == "2026-10-01"


def test_gun_siniri_ay_da_degisir():
    son = datetime(2026, 9, 30, 23, 59, 59, tzinfo=timezone.utc)
    ilk = datetime(2026, 10, 1, 0, 0, 1, tzinfo=timezone.utc)
    assert quota.gun_anahtari(son) != quota.gun_anahtari(ilk)


def test_son_gunler_14_tane_bit_isikli():
    gunler = quota.son_gunler(datetime(2026, 9, 30, 12, tzinfo=timezone.utc), 14)
    assert len(gunler) == 14
    assert gunler[0] == "2026-09-17"
    assert gunler[-1] == "2026-09-30"
    # Azalan (eskiden yeniye) sirali olmali.
    assert gunler == sorted(gunler)


# -- limitler ---------------------------------------------------------------


def test_varsayilan_limitler():
    limitler = quota.limitleri_yukle("/yok/olmayan/kota.toml")
    assert limitler.kaynak == "varsayilan"
    assert limitler.limit("nvidia/nemotron-3-ultra-550b-a55b:free") == 50
    assert limitler.limit("stealth/space-bunny-alpha") is None


def test_kota_toml_okunur(tmp_path):
    yol = tmp_path / "kota.toml"
    yol.write_text(
        '[limitler]\n"nvidia/nemotron-3-ultra-550b-a55b:free" = 7\n"a/b" = 0\n',
        encoding="utf-8",
    )
    limitler = quota.limitleri_yukle(yol)
    assert limitler.kaynak == "kota.toml"
    assert limitler.limit("nvidia/nemotron-3-ultra-550b-a55b:free") == 7
    # Limit 0 da "limitsiz" sayilir (limit falsy).
    assert limitler.limit("a/b") == 0


def test_kota_toml_bozuk_varsayilana_duser(tmp_path):
    yol = tmp_path / "kota.toml"
    yol.write_text("bu = [gecersiz", encoding="utf-8")
    limitler = quota.limitleri_yukle(yol)
    assert limitler.kaynak == "varsayilan"
    assert limitler.limit("nvidia/nemotron-3-ultra-550b-a55b:free") == 50


def test_kota_toml_limitler_bolumu_yok(tmp_path):
    yol = tmp_path / "kota.toml"
    yol.write_text('["baska"]\nx = 1\n', encoding="utf-8")
    assert quota.limitleri_yukle(yol).kaynak == "varsayilan"


def test_kota_toml_bozuk_degerler_dusurulur(tmp_path):
    yol = tmp_path / "kota.toml"
    yol.write_text(
        '[limitler]\n"iyi" = 5\n"metin" = "cok"\n"negatif" = -3\n"bool" = true\n',
        encoding="utf-8",
    )
    limitler = quota.limitleri_yukle(yol)
    assert limitler.limit("iyi") == 5
    assert limitler.limit("metin") is None
    assert limitler.limit("negatif") is None
    assert limitler.limit("bool") is None


def test_kota_toml_limit0_tek_model_varsayilana_dusmez(tmp_path):
    yol = tmp_path / "kota.toml"
    yol.write_text('[limitler]\n"a/b" = 3\n', encoding="utf-8")
    limitler = quota.limitleri_yukle(yol)
    # Yalnizca tanimli model gelir; varsayilan nemotron EKLENMEZ.
    assert set(limitler.degerler) == {"a/b"}


# -- durum ------------------------------------------------------------------


@pytest.mark.parametrize(
    "istek,limit,beklenen",
    [
        (0, 50, "normal"),
        (39, 50, "normal"),    # %78
        (40, 50, "uyari"),     # tam %80
        (41, 50, "uyari"),
        (49, 50, "uyari"),     # %98
        (50, 50, "asildi"),    # tam %100
        (51, 50, "asildi"),
        (100, 50, "asildi"),
        (0, None, "limitsiz"),
        (999, None, "limitsiz"),
        (5, 0, "limitsiz"),
    ],
)
def test_durum_esikleri(istek, limit, beklenen):
    assert quota.durum_bul(istek, limit) == beklenen


def test_yuzde_79_normal_80_uyari():
    # Sinir degerleri: %79 -> normal, %80 -> uyari.
    assert quota.durum_bul(79, 100) == "normal"
    assert quota.durum_bul(80, 100) == "uyari"
    assert quota.durum_bul(100, 100) == "asildi"


def test_yuzde_hesabi():
    assert quota.yuzde(40, 50) == 80.0
    assert quota.yuzde(40, None) is None


# -- tamamlanmamis satir -----------------------------------------------------


def test_tamamlanmamis_satir_alglama():
    # "a\nb" satir sonu olmadan bitiyor -> tamamlanmamis.
    assert quota.tamamlanmamis_satir("a\nb") is True
    assert quota.tamamlanmamis_satir("a\nb\n") is False
    assert quota.tamamlanmamis_satir("a\nb-") is True
    assert quota.tamamlanmamis_satir("") is False  # bos metin "yarim" sayilmaz


# -- artımli okuma ----------------------------------------------------------


def test_guncelle_tam_satirlari_isler(baglanti, tmp_path):
    yol = log_yaz(tmp_path / "proxy.log", [SATIR_NORMAL, SATIR_NEMOTRON])
    sonuc = quota.guncelle(baglanti, yol)
    assert sonuc.yeni_satir == 2
    assert sonuc.taninmayan == 0


def test_taninmayan_satirlar_sayilir(baglanti, tmp_path):
    yol = log_yaz(tmp_path / "proxy.log", TANINAN + TANINMAYAN)
    sonuc = quota.guncelle(baglanti, yol)
    assert sonuc.yeni_satir == len(TANINAN)
    assert sonuc.taninmayan == len(TANINMAYAN)


def test_ikinci_tur_yeni_satir_yok(baglanti, tmp_path):
    yol = log_yaz(tmp_path / "proxy.log", TANINAN)
    ilk = quota.guncelle(baglanti, yol)
    ikinci = quota.guncelle(baglanti, yol)
    assert ilk.yeni_satir == len(TANINAN)
    assert ikinci.yeni_satir == 0
    assert ikinci.taninmayan == 0


def test_eklenen_satirlar_sayilir(baglanti, tmp_path):
    yol = log_yaz(tmp_path / "proxy.log", TANINAN)
    quota.guncelle(baglanti, yol)
    yol.write_text("\n".join(TANINAN + [SATIR_NORMAL]) + "\n", encoding="utf-8")
    sonuc = quota.guncelle(baglanti, yol)
    assert sonuc.yeni_satir == 1


def test_yarim_satir_sonraki_tura_kalir(baglanti, tmp_path):
    # Dosya yarim satirla bitiyor: TAM satir olan istek sayilir.
    yol = tmp_path / "proxy.log"
    yol.write_text(SATIR_NORMAL + "\n[2026-09-30T06:15:25.67", encoding="utf-8")
    ilk = quota.guncelle(baglanti, yol)
    assert ilk.yeni_satir == 1
    # Konum yarim satirin BASINA kadar ilerlemis olmali.
    satir = baglanti.execute("SELECT konum FROM quota_offsets").fetchone()
    assert satir["konum"] == len(SATIR_NORMAL) + 1


def test_yarim_satir_tamamlaninca_sayilir(baglanti, tmp_path):
    yol = tmp_path / "proxy.log"
    yol.write_text(SATIR_NORMAL + "\n[2026-09-30T06:15:25.67", encoding="utf-8")
    quota.guncelle(baglanti, yol)
    # Yarim satir tamamlaniyor.
    yol.write_text(
        SATIR_NORMAL + "\n[2026-09-30T06:15:25.675Z] openrouter -> a/b:free\n",
        encoding="utf-8",
    )
    sonuc = quota.guncelle(baglanti, yol)
    assert sonuc.yeni_satir == 1


def test_log_kisalirsa_basa_donulur(baglanti, tmp_path):
    yol = log_yaz(tmp_path / "proxy.log", TANINAN)
    quota.guncelle(baglanti, yol)
    # Dosya kesiliyor / yeniden basliyor: konum sifirlanir.
    log_yaz(yol, [SATIR_NEMOTRON])
    sonuc = quota.guncelle(baglanti, yol)
    assert sonuc.yeni_satir == 1


def test_dosya_boyutu_kuculurse_basa_donulur(baglanti, tmp_path):
    yol = log_yaz(tmp_path / "proxy.log", TANINAN * 10)
    quota.guncelle(baglanti, yol)
    log_yaz(yol, [SATIR_NORMAL])
    sonuc = quota.guncelle(baglanti, yol)
    assert sonuc.yeni_satir == 1


def test_olmayan_log_sessizce_sifir(baglanti, tmp_path):
    sonuc = quota.guncelle(baglanti, tmp_path / "yok.log")
    assert sonuc.yeni_satir == 0
    assert sonuc.taninmayan == 0


def test_bos_log(baglanti, tmp_path):
    yol = tmp_path / "proxy.log"
    yol.write_text("", encoding="utf-8")
    sonuc = quota.guncelle(baglanti, yol)
    assert sonuc.yeni_satir == 0


def test_ustel_kayit_parca_okur(baglanti, tmp_path):
    # Cok satir var ama tek turda hepsi islenir.
    yol = log_yaz(tmp_path / "proxy.log", [SATIR_NORMAL] * 50)
    sonuc = quota.guncelle(baglanti, yol, ustel_kayit=1000)
    assert sonuc.yeni_satir == 50


# -- kota_snapshots yazimi --------------------------------------------------


def test_snapshots_yazilir(baglanti, tmp_path):
    # SATIR_NORMAL 2026-09-30'da, SATIR_NEMOTRON 2026-09-26'da.
    yol = log_yaz(tmp_path / "proxy.log", [SATIR_NORMAL, SATIR_NEMOTRON])
    quota.guncelle(baglanti, yol)
    bugun = baglanti.execute(
        "SELECT istek FROM quota_snapshots "
        "WHERE gun = '2026-09-30' AND model = 'stealth/space-bunny-alpha'"
    ).fetchone()
    assert bugun["istek"] == 1
    eski = baglanti.execute(
        "SELECT istek FROM quota_snapshots "
        "WHERE gun = '2026-09-26' AND model = 'nvidia/nemotron-3-ultra-550b-a55b:free'"
    ).fetchone()
    assert eski["istek"] == 1


def test_snapshots_maliyet_sifir(baglanti, tmp_path):
    yol = log_yaz(tmp_path / "proxy.log", [SATIR_NORMAL])
    quota.guncelle(baglanti, yol)
    satir = baglanti.execute("SELECT maliyet FROM quota_snapshots").fetchone()
    assert satir["maliyet"] == 0.0


def test_gun_bazinda_ayrilir(baglanti, tmp_path):
    yol = log_yaz(tmp_path / "proxy.log", [SATIR_NORMAL, SATIR_NEMOTRON])
    quota.guncelle(baglanti, yol)
    gunler = {s["gun"] for s in baglanti.execute("SELECT DISTINCT gun FROM quota_snapshots")}
    assert gunler == {"2026-09-30", "2026-09-26"}


# -- kota gorunumu ----------------------------------------------------------


def test_kota_gorunumu_bugunku_sayi(baglanti, tmp_path):
    bugun = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    baglanti.execute(
        "INSERT INTO quota_snapshots (model, gun, istek, maliyet) VALUES (?,?,?,0)",
        ("nvidia/nemotron-3-ultra-550b-a55b:free", bugun, 40),
    )
    gorunum = quota.kota_gorunumu(baglanti, quota.Limitler({"nvidia/nemotron-3-ultra-550b-a55b:free": 50}))
    m = gorunum.modeller[0]
    assert m.istek == 40
    assert m.limit == 50
    assert m.durum == "uyari"


def test_kota_gorunumu_limit_olan_model_gorunur(baglanti):
    # Kayit yoksa bile kota.toml'daki model listede cikar.
    gorunum = quota.kota_gorunumu(baglanti, quota.Limitler({"a/b": 10}))
    assert any(m.model == "a/b" for m in gorunum.modeller)


def test_kota_gorunumu_seri_14_gun(baglanti):
    gorunum = quota.kota_gorunumu(baglanti, quota.Limitler({}))
    if gorunum.modeller:
        assert len(gorunum.modeller[0].seri) == 14
