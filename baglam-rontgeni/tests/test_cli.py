"""CLI sozlesmesi: `python -m baglam_rontgeni` GERCEKTEN subprocess olarak calistirilir.

CLAUDE_DIR ve RONTGEN_DIR gecici dizine yonlendirilir (run_module_cli ayrica
HOME'u da cevirir): kullanicinin gercek `~/.claude` ayari ya da `~/.baglam-rontgeni`
raporu okunmaz/yazilmaz. Yazma testleri de YALNIZCA tmp_path altindaki sahte
settings.json uzerinde calisir.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

from conftest import VARSAYILAN_AYAR, ayar_oku, dosya_agaci, kur, run_module_cli, sahte_claude_dir

KULLANIM_HATASI = 2

KURU_NOTU = "kuru calistirma: hicbir sey yazilmadi"


def _kok_dosyalar(claude: Path) -> list[str]:
    """`.claude` kokundeki dosyalar (plugins/skills fixture dizinleri HARIC)."""
    return sorted(p.name for p in claude.iterdir() if p.is_file())


def _ortam(claude: Path, raporlar: Path) -> dict[str, str]:
    """CLI alt surecine verilecek izole ortam (ayarlar + rapor gecici)."""
    return {"CLAUDE_DIR": str(claude), "RONTGEN_DIR": str(raporlar)}


def _ortam_kur(
    tmp_path: Path,
    *,
    pluginler: dict | None = None,
    skilller: dict | None = None,
    kapali: dict | None = None,
) -> tuple[Path, dict[str, str]]:
    """Gecici `.claude` + ayar + izole ortam kurar; (claude, env) doner.

    `pluginler`: enabledPlugins'a ACIK yazilir. `kapali`: enabledPlugins'a false
    yazilir (plugin kurulu olsa da sayilmaz). `skilller`: ~/.claude/skills altina
    kurulan kullanici skill'leri.
    """
    acik = {ad: True for ad in (pluginler or {})}
    acik.update(kapali or {})
    claude = sahte_claude_dir(
        tmp_path / "claude",
        kur(enabledPlugins=acik, skillOverrides={}),
        pluginler=pluginler,
        skilller=skilller,
    )
    return claude, _ortam(claude, tmp_path / "raporlar")


# --------------------------------------------------------------------------
# tara
# --------------------------------------------------------------------------


def test_tara_rapor_yazar_ve_cikis_0(tmp_path):
    """`tara` cikis 0 doner ve raporu RONTGEN_DIR/son.json'a yazar."""
    claude, env = _ortam_kur(tmp_path, skilller={"harita": "---\nname: harita\ndescription: acik\n---\n\ngovde\n"})
    proc = run_module_cli("tara", cwd=tmp_path, env_ek=env)
    assert proc.returncode == 0, proc.stderr
    veri = json.loads((tmp_path / "raporlar" / "son.json").read_text(encoding="utf-8"))
    assert veri["surum"] == 1
    assert [k["tur"] for k in veri["kalemler"]] == ["skill"]
    assert veri["kalemler"][0]["ad"] == "harita"


def test_tara_rapor_dizini_env_ile_yonlendirilir(tmp_path):
    """Rapor RONTGEN_DIR'e yazilir; cikti da o yolu gosterir."""
    claude, env = _ortam_kur(tmp_path, skilller={"harita": "---\nname: harita\n---\n\nx\n"})
    proc = run_module_cli("tara", cwd=tmp_path, env_ek=env)
    assert proc.returncode == 0, proc.stderr
    assert (tmp_path / "raporlar" / "son.json").is_file()
    assert env["RONTGEN_DIR"] in proc.stdout


def test_tara_tablosunda_taimin_ve_kalem_adi_gorunur(tmp_path):
    """Tablo modu: kalem adi gorunur ve ozet TAHMIN ibaresiyle biter."""
    claude, env = _ortam_kur(tmp_path, skilller={"harita": "---\nname: harita\ndescription: acik\n---\n\ngovde\n"})
    proc = run_module_cli("tara", cwd=tmp_path, env_ek=env)
    assert proc.returncode == 0, proc.stderr
    assert "harita" in proc.stdout
    assert "TAHMIN" in proc.stdout


def test_tara_json_gecerli_json(tmp_path):
    """`tara --json` raporu JSON olarak yazar (tablo degil) ve rapor yolunu icerir."""
    claude, env = _ortam_kur(tmp_path, skilller={"harita": "---\nname: harita\n---\n\ngovde\n"})
    proc = run_module_cli("tara", "--json", cwd=tmp_path, env_ek=env)
    assert proc.returncode == 0, proc.stderr
    veri = json.loads(proc.stdout)
    assert veri["surum"] == 1
    assert veri["rapor"].endswith("son.json")


def test_tara_bozuk_settings_cikis_2(tmp_path):
    """Bozuk settings.json: AyarHatasi -> cikis 2, Turkce 'bozuk' mesaji."""
    claude, env = _ortam_kur(tmp_path)
    (claude / "settings.json").write_text("{bozuk", encoding="utf-8")
    proc = run_module_cli("tara", cwd=tmp_path, env_ek=env)
    assert proc.returncode == KULLANIM_HATASI, proc.stdout
    assert "bozuk" in proc.stderr


def test_tara_eksik_settings_cikis_2(tmp_path):
    """settings.json hic yoksa AyarHatasi -> cikis 2, 'bulunamadi'."""
    claude = tmp_path / "claude"
    claude.mkdir()
    proc = run_module_cli("tara", cwd=tmp_path, env_ek=_ortam(claude, tmp_path / "raporlar"))
    assert proc.returncode == KULLANIM_HATASI
    assert "bulunamadi" in proc.stderr


def test_tara_rapor_guncellenir_sizinti_yok(tmp_path):
    """Ikinci tara raporun USTUNE yazar: tek dosya kalir, .tmp sizmaz."""
    claude, env = _ortam_kur(tmp_path, skilller={"harita": "---\nname: harita\n---\n\nx\n"})
    for _ in range(2):
        assert run_module_cli("tara", cwd=tmp_path, env_ek=env).returncode == 0
    assert dosya_agaci(tmp_path / "raporlar") == ["son.json"]


# --------------------------------------------------------------------------
# goster
# --------------------------------------------------------------------------


def test_goster_rapor_yokken_cikis_2(tmp_path):
    """Rapor yoksa `goster` cikis 2 doner, stderr Turkce ve `tara` oner."""
    claude, env = _ortam_kur(tmp_path)
    proc = run_module_cli("goster", cwd=tmp_path, env_ek=env)
    assert proc.returncode == KULLANIM_HATASI, proc.stdout
    assert "rapor bulunamadi" in proc.stderr
    assert "tara" in proc.stderr
    assert proc.stdout.strip() == ""


def test_goster_bozuk_rapor_cikis_2(tmp_path):
    """Bozuk rapor dosyasi da 'bulunamadi' sayilir (cokmez, cikis 2)."""
    claude, env = _ortam_kur(tmp_path)
    (tmp_path / "raporlar").mkdir()
    (tmp_path / "raporlar" / "son.json").write_text("{bozuk", encoding="utf-8")
    proc = run_module_cli("goster", cwd=tmp_path, env_ek=env)
    assert proc.returncode == KULLANIM_HATASI
    assert "rapor bulunamadi" in proc.stderr


def test_goster_kaydedilmis_raporu_yazar(tmp_path):
    """`goster`: `tara` ciktisi sonrasi rapor ekrana basilir."""
    claude, env = _ortam_kur(tmp_path, skilller={"harita": "---\nname: harita\n---\n\ngovde\n"})
    assert run_module_cli("tara", cwd=tmp_path, env_ek=env).returncode == 0
    proc = run_module_cli("goster", cwd=tmp_path, env_ek=env)
    assert proc.returncode == 0, proc.stderr
    assert "harita" in proc.stdout
    assert "TAHMIN" in proc.stdout


def test_goster_json_gecerli_json(tmp_path):
    """`goster --json` kaydedilmis raporu OLDUGU GIBI JSON olarak yazar."""
    claude, env = _ortam_kur(tmp_path, skilller={"harita": "---\nname: harita\n---\n\ngovde\n"})
    assert run_module_cli("tara", cwd=tmp_path, env_ek=env).returncode == 0
    proc = run_module_cli("goster", "--json", cwd=tmp_path, env_ek=env)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["kalemler"][0]["ad"] == "harita"


def test_goster_ilk_kesme_sayisini_uygular(tmp_path):
    """`goster --ilk N`: yalniz ilk N kalem basilir, kalan sayisi yazilir."""
    skilller = {f"s{i}": f"---\nname: s{i}\ndescription: {'x' * (40 - i)}\n---\n\ngovde\n" for i in range(4)}
    claude, env = _ortam_kur(tmp_path, skilller=skilller)
    assert run_module_cli("tara", cwd=tmp_path, env_ek=env).returncode == 0
    proc = run_module_cli("goster", "--ilk", "1", cwd=tmp_path, env_ek=env)
    assert proc.returncode == 0, proc.stderr
    assert "ve 3 kalem daha" in proc.stdout


# --------------------------------------------------------------------------
# kapat / ac -- kuru calistirma
# --------------------------------------------------------------------------


def test_kapat_kuru_calistirma_ayari_degistirmez(tmp_path):
    """`kapat H` (--uygula yok): cikis 0, KURU CALISTIRMA notu, ayar BAYT-AYNI."""
    claude, env = _ortam_kur(tmp_path, pluginler={"kule@market": [{"installPath": "x"}]})
    yol = claude / "settings.json"
    once = yol.read_bytes()
    proc = run_module_cli("kapat", "kule@market", cwd=tmp_path, env_ek=env)
    assert proc.returncode == 0, proc.stderr
    assert KURU_NOTU in proc.stdout
    assert yol.read_bytes() == once, "kuru calistirma settings.json'u degistirdi"
    assert _kok_dosyalar(claude) == ["settings.json"]


def test_kapat_kuru_calistirma_plani_gosterir(tmp_path):
    """Kuru calistirma ciktisi DIFF satirlarini gosterir: ne degisecegi ONCEDEN gorulur."""
    claude, env = _ortam_kur(tmp_path, pluginler={"kule@market": [{"installPath": "x"}]})
    proc = run_module_cli("kapat", "kule@market", cwd=tmp_path, env_ek=env)
    assert proc.returncode == 0, proc.stderr
    assert "kule@market" in proc.stdout
    assert "true -> false" in proc.stdout


def test_ac_kuru_calistirma_ayari_degistirmez(tmp_path):
    """`ac plugin:skill` de varsayilan olarak KURU CALISTIRMA: ayar bayt-ayni, yedek alinmaz."""
    claude, env = _ortam_kur(tmp_path, pluginler={"kule@market": [{"installPath": "x"}]})
    yol = claude / "settings.json"
    yol.write_text(
        json.dumps(kur(enabledPlugins={"kule@market": True}, skillOverrides={"kule:x": "off"})),
        encoding="utf-8",
    )
    once = yol.read_bytes()
    proc = run_module_cli("ac", "kule:x", cwd=tmp_path, env_ek=env)
    assert proc.returncode == 0, proc.stderr
    assert KURU_NOTU in proc.stdout
    assert "silinecek" in proc.stdout, proc.stdout
    assert yol.read_bytes() == once
    assert _kok_dosyalar(claude) == ["settings.json"]


def test_ac_zaten_aktif_ayari_yazmaz(tmp_path):
    """skillOverrides'ta `off` OLMAYAN skill: 'zaten acik', hicbir sey yazilmaz."""
    claude, env = _ortam_kur(tmp_path, pluginler={"kule@market": [{"installPath": "x"}]})
    yol = claude / "settings.json"
    once = yol.read_bytes()
    proc = run_module_cli("ac", "kule:x", "--uygula", cwd=tmp_path, env_ek=env)
    assert proc.returncode == 0, proc.stderr
    assert "zaten acik" in proc.stdout
    assert yol.read_bytes() == once
    assert _kok_dosyalar(claude) == ["settings.json"], "gereksiz yedek olustu"


def test_kapat_zaten_kapali_ayari_yazmaz(tmp_path):
    """Zaten `off` olan skill: 'zaten kapali', KURU CALISTIRMA notu bile gerekmez, yazma yok."""
    claude, env = _ortam_kur(tmp_path, pluginler={"kule@market": [{"installPath": "x"}]})
    yol = claude / "settings.json"
    yol.write_text(
        json.dumps(kur(enabledPlugins={"kule@market": True}, skillOverrides={"kule:x": "off"})),
        encoding="utf-8",
    )
    once = yol.read_bytes()
    proc = run_module_cli("kapat", "kule:x", "--uygula", cwd=tmp_path, env_ek=env)
    assert proc.returncode == 0, proc.stderr
    assert "zaten kapali" in proc.stdout
    assert yol.read_bytes() == once, "zaten kapali skill icin yazildi"
    assert _kok_dosyalar(claude) == ["settings.json"], "gereksiz yedek olustu"


# --------------------------------------------------------------------------
# kapat / ac -- --uygula
# --------------------------------------------------------------------------


def test_kapat_uygula_gercekten_yazar_ve_yedek_alir(tmp_path):
    """`kapat --uygula`: enabledPlugins false olur, yedek alinir, KURU CALISTIRMA notu YOK."""
    claude, env = _ortam_kur(tmp_path, pluginler={"kule@market": [{"installPath": "x"}]})
    yol = claude / "settings.json"
    proc = run_module_cli("kapat", "kule@market", "--uygula", cwd=tmp_path, env_ek=env)
    assert proc.returncode == 0, proc.stderr
    assert "uygulandi" in proc.stdout and KURU_NOTU not in proc.stdout
    assert ayar_oku(claude)["enabledPlugins"]["kule@market"] is False
    assert [a for a in dosya_agaci(claude) if ".rontgen-bak-" in a], dosya_agaci(claude)


def test_kapat_uygula_yedek_orijinalle_ayni(tmp_path):
    """--uygula: alinan yedek, yazma ONCESI ayarin birebir aynisidir."""
    claude, env = _ortam_kur(tmp_path, pluginler={"kule@market": [{"installPath": "x"}]})
    yol = claude / "settings.json"
    orijinal = yol.read_bytes()
    assert run_module_cli("kapat", "kule@market", "--uygula", cwd=tmp_path, env_ek=env).returncode == 0
    yedek = [claude / a for a in dosya_agaci(claude) if ".rontgen-bak-" in a][0]
    assert yedek.read_bytes() == orijinal


def test_kapat_uygula_diger_anahtarlari_korur(tmp_path):
    """--uygula: `model`/`theme` gibi diger anahtarlar DEGISMEZ."""
    claude, env = _ortam_kur(tmp_path, pluginler={"kule@market": [{"installPath": "x"}]})
    assert run_module_cli("kapat", "kule@market", "--uygula", cwd=tmp_path, env_ek=env).returncode == 0
    sonra = ayar_oku(claude)
    assert sonra["model"] == VARSAYILAN_AYAR["model"]
    assert sonra["theme"] == VARSAYILAN_AYAR["theme"]


def test_kapat_ve_ac_round_trip_ayari_geri_doner(tmp_path):
    """`kapat --uygula` sonrasi `ac --uygula`: ayar ESKI HALINE doner.

    Round-trip'in asil degeri: kullanici kapatip "olmadi" deyip geri acabilir.
    """
    claude, env = _ortam_kur(tmp_path, pluginler={"kule@market": [{"installPath": "x"}]})
    yol = claude / "settings.json"
    orijinal = ayar_oku(claude)

    assert run_module_cli("kapat", "kule@market", "--uygula", cwd=tmp_path, env_ek=env).returncode == 0
    assert ayar_oku(claude) != orijinal, "kapatma hicbir seyi degistirmedi"

    assert run_module_cli("ac", "kule@market", "--uygula", cwd=tmp_path, env_ek=env).returncode == 0
    assert ayar_oku(claude) == orijinal, "acma ayari eski haline getirmedi"


def test_kapat_skill_uygula_skill_overrides_off_yazar(tmp_path):
    """`kapat plugin:skill --uygula`: skillOverrides'a `off` yazilir, plugin ACIK kalir."""
    claude, env = _ortam_kur(tmp_path, pluginler={"kule@market": [{"installPath": "x"}]})
    yol = claude / "settings.json"
    proc = run_module_cli("kapat", "kule:harita", "--uygula", cwd=tmp_path, env_ek=env)
    assert proc.returncode == 0, proc.stderr
    sonra = ayar_oku(claude)
    assert sonra["skillOverrides"] == {"kule:harita": "off"}
    assert sonra["enabledPlugins"]["kule@market"] is True, "skill kapatmak plugin'i kapatti"


def test_uygula_gedici_dosya_birakmaz(tmp_path):
    """--uygula sonrasi dizinde gecici .tmp dosyasi KALMAZ (atomik yazma)."""
    claude, env = _ortam_kur(tmp_path, pluginler={"kule@market": [{"installPath": "x"}]})
    assert run_module_cli("kapat", "kule@market", "--uygula", cwd=tmp_path, env_ek=env).returncode == 0
    agac = dosya_agaci(claude)
    assert not [a for a in agac if a.endswith(".tmp")], agac


# --------------------------------------------------------------------------
# hata yollari
# --------------------------------------------------------------------------


def test_bilinmeyen_plugin_hedefi_cikis_2(tmp_path):
    """enabledPlugins'ta olmayan plugin: ValueError -> cikis 2, 'bilinmeyen plugin'."""
    claude, env = _ortam_kur(tmp_path)
    once = (claude / "settings.json").read_bytes()
    proc = run_module_cli("kapat", "olmayan@market", "--uygula", cwd=tmp_path, env_ek=env)
    assert proc.returncode == KULLANIM_HATASI, proc.stdout
    assert "bilinmeyen plugin" in proc.stderr
    assert (claude / "settings.json").read_bytes() == once, "hatali hedefte yazildi"


def test_bilinmeyen_plugin_oneki_cikis_2(tmp_path):
    """`yok:skill` hedefi: plugin etkin degil -> cikis 2."""
    claude, env = _ortam_kur(tmp_path)
    proc = run_module_cli("kapat", "yok:skill", "--uygula", cwd=tmp_path, env_ek=env)
    assert proc.returncode == KULLANIM_HATASI
    assert "bilinmeyen plugin" in proc.stderr


def test_kapat_bozuk_settings_cikis_2(tmp_path):
    """Bozuk settings.json ile kapat: cikis 2, hicbir yedek olusmaz."""
    claude, env = _ortam_kur(tmp_path)
    (claude / "settings.json").write_text("{bozuk", encoding="utf-8")
    proc = run_module_cli("kapat", "kule@market", "--uygula", cwd=tmp_path, env_ek=env)
    assert proc.returncode == KULLANIM_HATASI
    assert "bozuk" in proc.stderr
    assert _kok_dosyalar(claude) == ["settings.json"], "bozuk ayarda yedek olustu"


def test_kapat_salt_okunur_settings_hata_ve_cikis_2(tmp_path):
    """Salt-okunur settings.json: iz (traceback) degil `Hata: ...` + cikis 2.

    README sozu: yazma yolundaki OSError (izin) kullanim hatasidir, 0 degil 2.
    """
    claude, env = _ortam_kur(tmp_path, pluginler={"kule@market": [{"installPath": "x"}]})
    yol = claude / "settings.json"
    orijinal = yol.read_bytes()
    os.chmod(yol, stat.S_IREAD)
    try:
        proc = run_module_cli("kapat", "kule@market", "--uygula", cwd=tmp_path, env_ek=env)
        assert proc.returncode == KULLANIM_HATASI, proc.stdout + proc.stderr
        assert proc.stderr.startswith("Hata:"), proc.stderr
        assert "Traceback" not in proc.stderr, proc.stderr
        assert yol.read_bytes() == orijinal
        assert not [a for a in dosya_agaci(claude) if a.endswith(".tmp")], dosya_agaci(claude)
    finally:
        os.chmod(yol, stat.S_IWRITE)  # tmp_path temizligi (Windows)


def test_tara_rapor_yazilamaz_cikis_2(tmp_path):
    """Rapor dizini yazilamazsa `Hata:` + cikis 2 (kullanici rapor almiyor sanmamali).

    Windows'ta dizin 'salt okunur' biti taramayi ENGELLEMEZ; bu yuzden engel,
    dosya olan bir yolun altinda dizin acmaya calismak (NotADirectoryError).
    """
    claude, env = _ortam_kur(tmp_path, skilller={"harita": "---\nname: harita\n---\n\nx\n"})
    engel = tmp_path / "engel"
    engel.write_text("bu bir dosya", encoding="utf-8")
    env["RONTGEN_DIR"] = str(engel / "raporlar")

    proc = run_module_cli("tara", cwd=tmp_path, env_ek=env)

    assert proc.returncode == KULLANIM_HATASI, proc.stdout + proc.stderr
    assert proc.stderr.startswith("Hata:"), proc.stderr
    assert "Traceback" not in proc.stderr, proc.stderr


def test_kapat_arada_degisen_ayar_uygulanmaz(tmp_path, monkeypatch, capsys):
    """Yazma aninda ayar degistiyse AyarHatasi: cikis 2, ustune YAZILMAZ.

    Kullanicinin baska bir pencerede yaptigi degisiklik, eski okuma uzerine
    ezilmez (TOCTOU). Gercekci senaryo: plan olusturuldu, `yaz` cagrilmadan
    once baska bir surec settings.json'u degistirdi.
    """
    from baglam_rontgeni import cli

    claude, _ = _ortam_kur(tmp_path, pluginler={"kule@market": [{"installPath": "x"}]})
    monkeypatch.setenv("CLAUDE_DIR", str(claude))
    yol = claude / "settings.json"
    gercek = cli.uygulanan_ayar

    def baska_surec_yazdi(ayar, hedef, acik):
        # araya girme: plugin ayni durumda, yalniz `theme` degisti
        yol.write_text(json.dumps(kur(enabledPlugins={"kule@market": True}, theme="light")), encoding="utf-8")
        return gercek(ayar, hedef, acik)

    monkeypatch.setattr(cli, "uygulanan_ayar", baska_surec_yazdi)

    cikis = cli.main(["kapat", "kule@market", "--uygula"])
    hata = capsys.readouterr().err
    assert cikis == KULLANIM_HATASI, hata
    assert "arada degisti" in hata, hata
    assert ayar_oku(claude)["theme"] == "light", "baskasinin ayari ezildi"
    assert ayar_oku(claude)["enabledPlugins"]["kule@market"] is True, "ayar ezildi"


# --------------------------------------------------------------------------
# skill uyarisi (kapat X: X bilinen skill mi)
# --------------------------------------------------------------------------


def test_kapat_bilinmeyen_skill_uyarisi(tmp_path):
    """`kapat bilinmeyen:x`: REDDEDILMEZ, uyari satiri yazilir, anahtar yine eklenir.

    Kesif plugin'i bulamasa da (kapali/eksik kurulum) kullanici niyetini
    uygulayabilmeli; sadece bilgilendirilir.
    """
    claude, env = _ortam_kur(tmp_path, pluginler={"kule@market": [{"installPath": "x"}]})
    proc = run_module_cli("kapat", "kule:yok-boyle-bir-skill", "--uygula", cwd=tmp_path, env_ek=env)
    assert proc.returncode == 0, proc.stderr
    assert "uyari: kule:yok-boyle-bir-skill bilinen skill degil" in proc.stdout, proc.stdout
    assert ayar_oku(claude)["skillOverrides"] == {"kule:yok-boyle-bir-skill": "off"}


def test_kapat_bilinir_skill_uyarisiz(tmp_path):
    """Kesifte OLAN bir skill icin uyari yazilmaz."""
    kurulu = tmp_path / "claude" / "plugins" / "market" / "kule"
    (kurulu / "skills" / "harita").mkdir(parents=True)
    (kurulu / "skills" / "harita" / "SKILL.md").write_text(
        "---\nname: harita\ndescription: acik\n---\n\ngovde\n", encoding="utf-8"
    )
    claude, env = _ortam_kur(
        tmp_path, pluginler={"kule@market": [{"installPath": str(kurulu)}]}
    )
    proc = run_module_cli("kapat", "kule:harita", cwd=tmp_path, env_ek=env)
    assert proc.returncode == 0, proc.stderr
    assert "bilinen skill degil" not in proc.stdout, proc.stdout


def test_kapat_kapali_skill_uyarisiz(tmp_path):
    """skillOverrides'ta KAPALI olan skill kesifte gorunmez ama bilinen sayilir."""
    claude, env = _ortam_kur(tmp_path, pluginler={"kule@market": [{"installPath": "x"}]})
    yol = claude / "settings.json"
    yol.write_text(
        json.dumps(kur(enabledPlugins={"kule@market": True}, skillOverrides={"kule:eski": "off"})),
        encoding="utf-8",
    )
    proc = run_module_cli("kapat", "kule:yok", "--uygula", cwd=tmp_path, env_ek=env)
    assert "bilinen skill degil" in proc.stdout, proc.stdout
    proc = run_module_cli("ac", "kule:eski", cwd=tmp_path, env_ek=env)
    assert "bilinen skill degil" not in proc.stdout, proc.stdout


def test_kapat_hedef_kontrol_karakteri_temizlenir(tmp_path):
    """Hedef terminale basilirken kontrol karakterleri `?` olur (ANSI enjeksiyonu).

    Ayarlama tarafi zaten reddediyor; burada hedefin YAZDIRILMASI deniyor.
    """
    claude, env = _ortam_kur(tmp_path, pluginler={"kule@market": [{"installPath": "x"}]})
    proc = run_module_cli("kapat", "kule:\x1b[2Jharita", cwd=tmp_path, env_ek=env)
    assert proc.returncode == KULLANIM_HATASI
    assert "gecersiz hedef" in proc.stderr, proc.stderr
    assert "\x1b" not in proc.stdout + proc.stderr


# --------------------------------------------------------------------------
# Genel sozlesme
# --------------------------------------------------------------------------


def test_alt_komut_zorunlu(tmp_path):
    """Alt komut verilmezse argparse hata verir ve cikis kodu 2 doner."""
    claude, env = _ortam_kur(tmp_path)
    proc = run_module_cli(cwd=tmp_path, env_ek=env)
    assert proc.returncode == KULLANIM_HATASI
    assert "usage" in proc.stderr.lower()


def test_yardim_sifir_cikar(tmp_path):
    """--help cikis kodu 0 verir ve komutlari listeler."""
    claude, env = _ortam_kur(tmp_path)
    proc = run_module_cli("--help", cwd=tmp_path, env_ek=env)
    assert proc.returncode == 0
    for komut in ("tara", "goster", "kapat", "ac"):
        assert komut in proc.stdout, komut


def test_bilinmeyen_alt_komut_cikis_2(tmp_path):
    """Bilinmeyen alt komut: argparse hata, cikis 2."""
    claude, env = _ortam_kur(tmp_path)
    proc = run_module_cli("uydur", cwd=tmp_path, env_ek=env)
    assert proc.returncode == KULLANIM_HATASI
