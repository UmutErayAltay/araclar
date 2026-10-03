"""ayar: okuma hatalari, plan/uygulama ayrimi, yedek + atomik yazma.

Gercek `~/.claude` HICBIR testte yazilmaz: her test tmp_path altinda kendi
settings.json'unu kurar (CLAUDE_DIR fixture'i ya da dogrudan yol).
"""

from __future__ import annotations

import json
import os
import stat
import time
from pathlib import Path

import pytest
from conftest import (
    VARSAYILAN_AYAR,
    ayar_oku,
    dosya_agaci,
    kur,
    sahte_claude_dir,
    symlink_kur,
)

from baglam_rontgeni import ayar
from baglam_rontgeni.ayar import AyarHatasi

SIRA = ["model", "theme", "skillOverrides", "enabledPlugins"]


def _ayar() -> dict:
    return kur(
        skillOverrides={"kule:harita": "off"},
        enabledPlugins={"kule@market": True, "atolye@market": False},
    )


# --------------------------------------------------------------------------
# claude_dizin / oku
# --------------------------------------------------------------------------


def test_claude_dizin_env_ile_yonlendirilir(claude_dir, ev_isole):
    """CLAUDE_DIR varsa o kullanilir (ev_isole gercek evi degistirir)."""
    assert ayar.claude_dizin() == claude_dir


def test_claude_dizin_env_yoksa_ev_altindaki_claude(ev_isole, monkeypatch):
    """CLAUDE_DIR yoksa ~/.claude; ev_isole bunu geciciye cevirir."""
    monkeypatch.delenv("CLAUDE_DIR", raising=False)
    assert ayar.claude_dizin() == ev_isole / ".claude"


def test_claude_dizin_goreli_yol_mutlaklasir(ev_isole, monkeypatch, tmp_path):
    """CLAUDE_DIR goreli verilirse MUTLAK yola cevrilir (cwd degisince kaymaz)."""
    (tmp_path / "y").mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLAUDE_DIR", "y")
    sonuc = ayar.claude_dizin()
    assert sonuc.is_absolute() and sonuc.name == "y", sonuc


def test_oku_ayari_sozluk_donur(tmp_path):
    """oku, settings.json'u sozluk olarak aynen dondurur."""
    claude = sahte_claude_dir(tmp_path / "claude", _ayar())
    assert ayar.oku(claude / "settings.json") == _ayar()


def test_oku_env_dizinine_gider(claude_dir, ev_isole):
    """yol verilmezse oku, CLAUDE_DIR'inin settings.json'unu okur."""
    sahte_claude_dir(claude_dir, _ayar())
    assert ayar.oku() == _ayar()


def test_oku_eksik_dosya_ayar_hatasi(tmp_path):
    """settings.json yoksa AyarHatasi ('bulunamadi') - CLI bunu cikis 2'ye cevirir."""
    with pytest.raises(AyarHatasi, match="bulunamadi"):
        ayar.oku(tmp_path / "yok.json")


def test_oku_bozuk_json_ayar_hatasi(tmp_path):
    """Bozuk JSON AyarHatasi verir, cokmez (JSONDecodeError sizmaz)."""
    yol = tmp_path / "settings.json"
    yol.write_text("{bozuk", encoding="utf-8")
    with pytest.raises(AyarHatasi, match="bozuk"):
        ayar.oku(yol)


def test_oku_sozluk_degil_ayar_hatasi(tmp_path):
    """JSON gecerli ama sozluk degilse (liste) AyarHatasi."""
    yol = tmp_path / "settings.json"
    yol.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(AyarHatasi, match="sozluk degil"):
        ayar.oku(yol)


def test_oku_izinli_anahtar_sozluk_degil_ayar_hatasi(tmp_path):
    """`skillOverrides` sozluk degilse AyarHatasi: plan yanlis yere yazmaz."""
    yol = tmp_path / "settings.json"
    yol.write_text(json.dumps({"skillOverrides": ["kule:harita"]}), encoding="utf-8")
    with pytest.raises(AyarHatasi, match="skillOverrides"):
        ayar.oku(yol)


# --------------------------------------------------------------------------
# plan: hicbir sey yazmadan once
# --------------------------------------------------------------------------


def test_plan_girdi_ayarini_degistirmez():
    """degisiklik_plani/uygulanan_ayar girdi sozlugunu BOZMAZ (kuru calistirma sonrasi kullanilir)."""
    girdi = _ayar()
    ayar.uygulanan_ayar(girdi, "kule:kule-gelistirme", False)
    assert girdi == _ayar()


def test_uygulanan_ayar_kopya_dondurur():
    """uygulanan_ayar girdiden AYRI bir sozluk dondurur (yerinde degisiklik yok)."""
    girdi = _ayar()
    yeni = ayar.uygulanan_ayar(girdi, "kule:kule-gelistirme", False)
    assert yeni is not girdi
    assert girdi["skillOverrides"] == {"kule:harita": "off"}


def test_plan_skill_kapatma_satiri():
    """`plugin:skill` kapatma plani skillOverrides'a `off` yazacagini soyler."""
    plan = ayar.degisiklik_plani(_ayar(), "kule:kule-gelistirme", False)
    assert len(plan) == 1
    assert 'skillOverrides["kule:kule-gelistirme"] = "off"' in plan[0]


def test_plan_plugin_kapatma_satiri():
    """`ad@pazar` kapatma plani enabledPlugins'ta true -> false gosterir."""
    plan = ayar.degisiklik_plani(_ayar(), "kule@market", False)
    assert len(plan) == 1
    assert "enabledPlugins['kule@market']" in plan[0]
    assert "true -> false" in plan[0]


def test_plan_zaten_kapali_bos():
    """Zaten `off` olan skill icin plan BOS: CLI 'zaten kapali' der, yazmaz."""
    assert ayar.degisiklik_plani(_ayar(), "kule:harita", False) == []


def test_plan_zaten_kapali_plugin_bos():
    """enabledPlugins degeri zaten false ise kapatma plani yoktur."""
    assert ayar.degisiklik_plani(_ayar(), "atolye@market", False) == []


def test_plan_acma_anahtar_silme_satiri():
    """`ac` `off` satirini KALDIRIR; plan bunu acikca soyler."""
    plan = ayar.degisiklik_plani(_ayar(), "kule:harita", True)
    assert len(plan) == 1
    assert "silinecek" in plan[0]


def test_plan_bilinmeyen_plugin_hedefi_hata(tmp_path):
    """Bilinmeyen plugin adi (skill hedefinin on eki): ValueError 'bilinmeyen plugin'."""
    with pytest.raises(ValueError, match="bilinmeyen plugin"):
        ayar.degisiklik_plani(_ayar(), "olmayan:kule-gelistirme", False)


def test_plan_bilinmeyen_plugin_hedefi_hata_ayirici(tmp_path):
    """enabledPlugins'ta olmayan `ad@pazar`: ValueError, dosyaya dokunulmaz."""
    with pytest.raises(ValueError, match="bilinmeyen plugin"):
        ayar.degisiklik_plani(_ayar(), "olmayan@market", False)


def test_plan_kullanici_skill_duz_ad_kapatilir_ve_acilir():
    """Plugin'siz kullanici skill'i (duz ad) skillOverrides ile kapanir, ac anahtari siler."""
    a = _ayar()
    assert ayar.degisiklik_plani(a, "harita", False) == ['+ skillOverrides["harita"] = "off"']
    kapali = ayar.uygulanan_ayar(a, "harita", False)
    assert kapali["skillOverrides"]["harita"] == "off"
    assert "harita" not in ayar.uygulanan_ayar(kapali, "harita", True)["skillOverrides"]


def test_plan_mevcut_deger_degistirilirken_eski_deger_gorunur():
    """Anahtarli `off` OLMAYAN bir deger ezilirken diff satiri ESKI degeri gosterir.

    Sessizce ezmek ("off olmayan her sey acik") en kotu durum: kullanici
    nesne/baska degerini kaybetmis olur ve diff'te izi kalmaz.
    """
    a = kur(skillOverrides={"harita": {"izin": True}}, enabledPlugins={"kule@market": True})
    plan = ayar.degisiklik_plani(a, "harita", False)
    assert len(plan) == 1
    assert '"off"' in plan[0] and '"izin": true' in plan[0], plan


# --------------------------------------------------------------------------
# hedef dogrulama
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "hedef",
    ["", "..", "../ayarlar", "kule/../../x", "a b", "kule:harita\x1b[2J", "kule:*", "a|b", "\n", "kule:"],
)
def test_plan_gecersiz_hedefi_reddeder(hedef):
    """Yol kacisi, bos ad, bos skill adi ve kontrol karakteri reddedilir.

    Hedef dogrudan JSON anahtari olarak yazilir; `..` veya ANSI karakteri
    tasidigi icin kabul edilmez.
    """
    with pytest.raises(ValueError, match="gecersiz hedef"):
        ayar.degisiklik_plani(_ayar(), hedef, False)


def test_plan_bos_hedef_ayri_mesaj():
    """Bos ad icin ozel mesaj ('skill adi bos' ile karismasin)."""
    with pytest.raises(ValueError, match="gecersiz hedef: bos"):
        ayar.degisiklik_plani(_ayar(), "", False)


def test_plan_gecersiz_hedef_dosyaya_dokunmaz(tmp_path):
    """Gecersiz hedef PLAN asamasinda reddedilir; hicbir ayar yazilmaz.

    CLI sirasi: degisiklik_plani -> (--uygula ise) yaz. Plan duser ise yazma
    hic cagrilmaz; bu test akisin o noktada koptugunu sabitler.
    """
    claude = sahte_claude_dir(tmp_path / "claude", _ayar())
    yol = claude / "settings.json"
    once = yol.read_bytes()
    with pytest.raises(ValueError, match="gecersiz hedef"):
        ayar.degisiklik_plani(ayar.oku(yol), "kule/../../x", False)
    assert yol.read_bytes() == once
    assert dosya_agaci(claude) == ["settings.json"]


# --------------------------------------------------------------------------
# yaz: kuru calistirma / yedek / atomiklik
# --------------------------------------------------------------------------


def test_yaz_kuru_calistirma_dosyaya_dokunmaz(tmp_path):
    """uygula=False: yaz() None doner, settings.json BAYT-AYNI kalir, yanina hicbir sey yazilmaz."""
    claude = sahte_claude_dir(tmp_path / "claude", _ayar())
    yol = claude / "settings.json"
    once = yol.read_bytes()
    agac = dosya_agaci(claude)

    assert ayar.yaz(yol, ayar.uygulanan_ayar(_ayar(), "kule:kule-gelistirme", False), False) is None
    assert yol.read_bytes() == once, "kuru calistirma settings.json'u degistirdi"
    assert dosya_agaci(claude) == agac, "kuru calistirma yan dosya birakti"


def test_yaz_uygula_yedek_alinir_ve_orijinalle_ayni(tmp_path):
    """--uygula: zaman damgali yedek alinir ve yedek ORijinal icerikle birebir aynidir."""
    claude = sahte_claude_dir(tmp_path / "claude", _ayar())
    yol = claude / "settings.json"
    orijinal = yol.read_bytes()

    ayar.yaz(yol, ayar.uygulanan_ayar(_ayar(), "kule@market", False), True)

    yedekler = [p for p in claude.iterdir() if ".rontgen-bak-" in p.name]
    assert len(yedekler) == 1, dosya_agaci(claude)
    assert yedekler[0].read_bytes() == orijinal, "yedek orijinali yansitmadi"


def test_yaz_yalniz_izinli_anahtarlari_degistirir(tmp_path):
    """--uygula: `model`/`theme` gibi diger anahtarlar DEGISMEZ."""
    claude = sahte_claude_dir(tmp_path / "claude", _ayar())
    yol = claude / "settings.json"

    ayar.yaz(yol, ayar.uygulanan_ayar(_ayar(), "kule@market", False), True)

    sonra = ayar_oku(claude)
    assert sonra["model"] == VARSAYILAN_AYAR["model"]
    assert sonra["theme"] == VARSAYILAN_AYAR["theme"]
    assert sonra["enabledPlugins"]["kule@market"] is False
    assert sonra["enabledPlugins"]["atolye@market"] is False
    assert set(sonra) == set(VARSAYILAN_AYAR)


def test_yaz_anahtar_sirasi_korunur(tmp_path):
    """--uygula: anahtar SIRASI degismez (kullanicinin elindeki ayar dosyasi okunur kalir)."""
    sirali = {k: VARSAYILAN_AYAR[k] for k in SIRA}
    sirali["skillOverrides"] = {}
    sirali["enabledPlugins"] = {"kule@market": True}
    claude = sahte_claude_dir(tmp_path / "claude", sirali)
    yol = claude / "settings.json"

    ayar.yaz(yol, ayar.uygulanan_ayar(sirali, "kule:kule-gelistirme", False), True)

    assert list(json.loads(yol.read_text(encoding="utf-8"))) == SIRA


def test_yaz_anahtar_yoksa_sonra_eklenir(tmp_path):
    """`skillOverrides` hic yoksa eklenir; diger anahtarlar yine ayni kalir."""
    sirali = {k: VARSAYILAN_AYAR[k] for k in SIRA if k != "skillOverrides"}
    sirali["enabledPlugins"] = {"kule@market": True}
    claude = sahte_claude_dir(tmp_path / "claude", sirali)
    yol = claude / "settings.json"

    ayar.yaz(yol, ayar.uygulanan_ayar(sirali, "kule:kule-gelistirme", False), True)

    assert ayar_oku(claude)["skillOverrides"] == {"kule:kule-gelistirme": "off"}
    assert ayar_oku(claude)["model"] == VARSAYILAN_AYAR["model"]


def test_yaz_gecici_dosya_birakmaz(tmp_path):
    """Atomik yazma sonrasi dizinde SADECE settings.json + yedek var: .tmp sizmaz."""
    claude = sahte_claude_dir(tmp_path / "claude", _ayar())
    yol = claude / "settings.json"

    ayar.yaz(yol, ayar.uygulanan_ayar(_ayar(), "kule@market", False), True)

    agac = dosya_agaci(claude)
    yedekler = [a for a in agac if ".rontgen-bak-" in a]
    assert sorted(agac) == sorted(["settings.json"] + yedekler), agac
    assert len(yedekler) == 1, agac
    assert not [a for a in agac if a.endswith(".tmp")], agac


def test_yaz_hata_olursa_eski_ayar_bozulmaz(tmp_path, monkeypatch):
    """os.replace patlarsa gecici dosya SILINIR, eski settings.json okunur kalir.

    Atomikligi ozetleyen asil test: yarim JSON hicbir zaman gorunmez.
    """
    claude = sahte_claude_dir(tmp_path / "claude", _ayar())
    yol = claude / "settings.json"
    orijinal = yol.read_bytes()

    def patla(*_a, **_k):
        raise OSError("disk doldu")

    monkeypatch.setattr(ayar.os, "replace", patla)
    with pytest.raises(OSError):
        ayar.yaz(yol, ayar.uygulanan_ayar(_ayar(), "kule@market", False), True)

    assert yol.read_bytes() == orijinal
    assert not [a for a in dosya_agaci(claude) if a.endswith(".tmp")], dosya_agaci(claude)


def test_yaz_ust_uste_yazim_dosya_sayisi_sabit(tmp_path):
    """Arka arkaya iki yazim: her seferinde yeni yedek + tek settings.json, .tmp yigini olmaz."""
    claude = sahte_claude_dir(tmp_path / "claude", _ayar())
    yol = claude / "settings.json"

    for _ in range(2):
        ayar.yaz(yol, ayar.uygulanan_ayar(_ayar(), "kule@market", False), True)

    agac = dosya_agaci(claude)
    assert "settings.json" in agac
    assert not [a for a in agac if a.endswith(".tmp")], agac


# --------------------------------------------------------------------------
# TOCTOU: yazma oncesi hedef yeniden okunur
# --------------------------------------------------------------------------


def test_yaz_beklenen_ayar_degismisse_yazmaz(tmp_path):
    """bekle verilip dosya arada DEGISTIRILDIYSE AyarHatasi: ustune yazilmaz, yedek alinmaz."""
    claude = sahte_claude_dir(tmp_path / "claude", _ayar())
    yol = claude / "settings.json"
    beklenen = ayar.oku(yol)
    baskasinin_ayar = kur(theme="light")  # baska surec yazdi
    yol.write_text(json.dumps(baskasinin_ayar), encoding="utf-8")

    with pytest.raises(AyarHatasi, match="arada degisti"):
        ayar.yaz(yol, ayar.uygulanan_ayar(beklenen, "kule@market", False), True, bekle=beklenen)

    assert ayar.oku(yol) == baskasinin_ayar, "baskasinin ayari ezildi"
    assert dosya_agaci(claude) == ["settings.json"], "degismemis hali yedeklendi"


def test_yaz_beklenen_ayar_ayniysa_yazar(tmp_path):
    """beklenen ayar dosyayla AYNI ise yazma normal akisla olur (kayma yoksa yazilir)."""
    claude = sahte_claude_dir(tmp_path / "claude", _ayar())
    yol = claude / "settings.json"
    beklenen = ayar.oku(yol)

    ayar.yaz(yol, ayar.uygulanan_ayar(beklenen, "kule@market", False), True, bekle=beklenen)

    assert ayar_oku(claude)["enabledPlugins"]["kule@market"] is False
    assert [a for a in dosya_agaci(claude) if ".rontgen-bak-" in a]


def test_yaz_bekle_verilmezse_kontrol_yok(tmp_path):
    """`bekle` verilmezse eski davranis korunur (geriye donuk uyum: yazar)."""
    claude = sahte_claude_dir(tmp_path / "claude", _ayar())
    yol = claude / "settings.json"
    ayar.yaz(yol, ayar.uygulanan_ayar(_ayar(), "kule@market", False), True)
    assert ayar_oku(claude)["enabledPlugins"]["kule@market"] is False


# --------------------------------------------------------------------------
# yedek rotasyonu / gecici temizligi / izin
# --------------------------------------------------------------------------


def test_yedek_rotasyonu_en_yeni_bes_saklanir(tmp_path):
    """Yedekler sINIRLANIR: en yeniden YEDEK_ADETI tane kalir, eskiler silinir.

    Sinirsiz yedek birikişi .claude dizinini şişirirdi.
    """
    claude = sahte_claude_dir(tmp_path / "claude", _ayar())
    yol = claude / "settings.json"
    for _ in range(ayar.YEDEK_ADETI + 4):
        ayar.yaz(yol, ayar.uygulanan_ayar(_ayar(), "kule@market", False), True)

    yedekler = [a for a in dosya_agaci(claude) if ".rontgen-bak-" in a]
    assert len(yedekler) == ayar.YEDEK_ADETI, dosya_agaci(claude)
    assert "settings.json" in dosya_agaci(claude)


def test_yaz_esk_gecici_dosyalari_siler(tmp_path):
    """Yarim kalmis ESKI `settings.json*.tmp` dosyalari silinir (sizinti temizligi).

    Yalniz BU modulen mkstemp desenine ait dosyalar (bizim prefix'li + .tmp)
    ve yalniz GECICI_YAS'tan eskileri; baska yazma dosyalari KALIR.
    """
    claude = sahte_claude_dir(tmp_path / "claude", _ayar())
    yol = claude / "settings.json"
    yasli = claude / "settings.jsonABC.tmp"
    taze = claude / "settings.jsonDEF.tmp"
    baska = claude / "rapor.tmp"
    yasli.write_text("{yarim", encoding="utf-8")
    taze.write_text("{yarim", encoding="utf-8")
    baska.write_text("baska", encoding="utf-8")
    eski = time.time() - ayar.GECICI_YAS - 60
    os.utime(yasli, (eski, eski))
    os.utime(baska, (eski, eski))

    ayar.yaz(yol, ayar.uygulanan_ayar(_ayar(), "kule@market", False), True)

    agac = dosya_agaci(claude)
    assert "settings.jsonABC.tmp" not in agac, agac  # yasli silindi
    assert "settings.jsonDEF.tmp" in agac, agac  # taze korundu
    assert "rapor.tmp" in agac, agac  # baska yazma KALMASI korundu


def test_yaz_salt_okunur_dosyaya_yazamaz(tmp_path):
    """Salt-okunur ayar dosyasi: yazma hata verir, gecici dosya KALMAZ.

    Windows'ta os.replace read-only hedefe PermissionError verir; yedek alinmis
    olsa bile ayar bozulmaz.
    """
    claude = sahte_claude_dir(tmp_path / "claude", _ayar())
    yol = claude / "settings.json"
    orijinal = yol.read_bytes()
    os.chmod(yol, stat.S_IREAD)

    try:
        with pytest.raises(OSError):
            ayar.yaz(yol, ayar.uygulanan_ayar(_ayar(), "kule@market", False), True)
        assert yol.read_bytes() == orijinal
        assert not [a for a in dosya_agaci(claude) if a.endswith(".tmp")], dosya_agaci(claude)
    finally:
        os.chmod(yol, stat.S_IWRITE)  # tmp_path temizligi icin (Windows)


@pytest.mark.skipif(os.name == "nt", reason="POSIX izinleri: Windows'ta chmod 0o600 raporlanmaz")
def test_yaz_yedek_ve_yeni_dosya_sahibi_izinde(tmp_path):
    """Yedek ve yeni ayar dosyasi YALNIZ sahibin okuyup yazabilecegi izinle durur (0o600)."""
    claude = sahte_claude_dir(tmp_path / "claude", _ayar())
    yol = claude / "settings.json"
    ayar.yaz(yol, ayar.uygulanan_ayar(_ayar(), "kule@market", False), True)

    yedek = [p for p in claude.iterdir() if ".rontgen-bak-" in p.name][0]
    assert stat.S_IMODE(yedek.stat().st_mode) == 0o600
    assert stat.S_IMODE(yol.stat().st_mode) == 0o600


# --------------------------------------------------------------------------
# symlink: ayar dosyasi bir baglantiysa hedefi yazilir
# --------------------------------------------------------------------------


def test_yaz_symlink_hedefine_yazar_baglanti_kalir(tmp_path):
    """settings.json symlink'i: GERCEK dosya guncellenir, baglanti KIRILMAZ.

    Kiripli yazma baglantiyi dosyaya cevirir ve kullanicinin ayar dosyasi
    sessizce degisir.
    """
    claude = sahte_claude_dir(tmp_path / "claude", _ayar())
    gercek = claude / "gercek-ayar.json"
    gercek.write_text(json.dumps(_ayar()), encoding="utf-8")
    baglanti = claude / "settings.json"
    if not symlink_kur(baglanti, gercek):
        pytest.skip("symlink olusturulamadi (Windows: SeCreateSymbolicLinkYetki/1314)")

    sonuc = ayar.yaz(baglanti, ayar.uygulanan_ayar(_ayar(), "kule@market", False), True)

    assert baglanti.is_symlink(), "baglanti dosyaya cevrildi"
    assert sonuc == gercek, sonuc
    assert json.loads(gercek.read_text(encoding="utf-8"))["enabledPlugins"]["kule@market"] is False


def test_yaz_symlink_toctou_kontrolu_hedefte_calisir(tmp_path):
    """Symlink hedefinde degisiklik varsa yine AyarHatasi firlatilir."""
    claude = sahte_claude_dir(tmp_path / "claude", _ayar())
    gercek = claude / "gercek-ayar.json"
    gercek.write_text(json.dumps(_ayar()), encoding="utf-8")
    baglanti = claude / "settings.json"
    if not symlink_kur(baglanti, gercek):
        pytest.skip("symlink olusturulamadi (Windows: SeCreateSymbolicLinkYetki/1314)")
    beklenen = ayar.oku(baglanti)
    gercek.write_text(json.dumps(kur(theme="light")), encoding="utf-8")

    with pytest.raises(AyarHatasi, match="arada degisti"):
        ayar.yaz(baglanti, ayar.uygulanan_ayar(beklenen, "kule@market", False), True, bekle=beklenen)
