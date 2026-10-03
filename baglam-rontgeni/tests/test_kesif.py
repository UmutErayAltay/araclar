"""kesif: aktif plugin/skill secimi, frontmatter, gizli dizin, MCP bicimleri, CLAUDE.md zinciri.

Gercek `~/.claude` HICBIR testte okunmaz: her test tmp_path altinda kendi
`.claude` kopyasini kurar (sahte_claude_dir) veya dizini dogrudan gecirir.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import junction_kur, kur, sahte_claude_dir, sahte_plugin, symlink_kur

from baglam_rontgeni import kesif, olc


def SKILL(name: str, description: str = "aciklama", govde: str = "govde") -> str:
    """Klasik SKILL.md govdesi."""
    return f"---\nname: {name}\ndescription: {description}\n---\n\n{govde}\n"


def _plugin_kur(claude: Path, anahtar: str, skilller: dict | None = None, *, mcp=None) -> Path:
    """Bir plugin'i kurar: installed_plugins.json + installPath altinda skill'ler.

    installPath GERCEK yerlesim gibi `claude/plugins/` ALTINDA olmali: disaridaki
    bir yol guvenlik nedeniyle taranmaz (bkz. kesif._acik_pluginlar).
    """
    kurulu = claude / "plugins"
    kurulu.mkdir(parents=True, exist_ok=True)
    mevcut = kurulu / "installed_plugins.json"
    veri = json.loads(mevcut.read_text(encoding="utf-8")) if mevcut.exists() else {"version": 1, "plugins": {}}
    kok = kurulu / "market" / anahtar.split("@")[0]
    veri["plugins"][anahtar] = [{"installPath": str(kok), "lastUpdated": "2026-01-01T00:00:00Z"}]
    mevcut.write_text(json.dumps(veri), encoding="utf-8")
    kok.mkdir(parents=True, exist_ok=True)  # skill yoksa da installPath dizin olmali
    return sahte_plugin(kok, skilller, mcp=mcp)


def _adlar(kalemler: list[dict]) -> set[str]:
    return {k["ad"] for k in kalemler}


# --------------------------------------------------------------------------
# hangi plugin/skill sayilir
# --------------------------------------------------------------------------


def test_kapali_plugin_sayilmaz(tmp_path):
    """enabledPlugins degeri false olan plugin'in skill'leri kesfe GIRMEZ."""
    claude = sahte_claude_dir(tmp_path / "claude", kur(enabledPlugins={"atolye@market": True}))
    _plugin_kur(claude, "atolye@market", {"taslak": SKILL("taslak")})
    ayar = kur(enabledPlugins={"atolye@market": False})

    assert kesif.skill_kalemleri(ayar, claude) == []


def test_kapali_skill_isaretli_olsa_da_listelenir(tmp_path):
    """Kapali plugin SKILDIRILMEZ ama acik plugin'in `off` skill'i yine raporlanir (kapali=True)."""
    claude = sahte_claude_dir(tmp_path / "claude", kur(enabledPlugins={"kule@market": True}))
    _plugin_kur(claude, "kule@market", {"harita": SKILL("harita"), "kule-gelistirme": SKILL("kule-gelistirme")})
    ayar = kur(enabledPlugins={"kule@market": True}, skillOverrides={"kule:harita": "off"})

    kalemler = kesif.skill_kalemleri(ayar, claude)
    kapali = {k["ad"] for k in kalemler if k["kapali"]}
    assert kapali == {"kule:harita"}
    assert _adlar(kalemler) == {"kule:harita", "kule:kule-gelistirme"}


def test_cache_teki_eski_surum_sayilmaz(tmp_path):
    """`plugins/cache` altindaki eski surum sayilmaz; en guncel installPath kullanilir."""
    claude = sahte_claude_dir(tmp_path / "claude", kur(enabledPlugins={"kule@market": True}))
    cache = claude / "plugins" / "cache"
    eski = sahte_plugin(cache / "eski", {"harita": SKILL("harita", "eski surum")})
    guncel = sahte_plugin(cache / "guncel", {"harita": SKILL("harita", "guncel surum")})
    kurulu = claude / "plugins" / "installed_plugins.json"
    kurulu.parent.mkdir(parents=True, exist_ok=True)
    kurulu.write_text(
        json.dumps(
            {
                "version": 1,
                "plugins": {
                    "kule@market": [
                        {"installPath": str(eski), "lastUpdated": "2026-01-01T00:00:00Z"},
                        {"installPath": str(guncel), "lastUpdated": "2026-02-01T00:00:00Z"},
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    ayar = kur(enabledPlugins={"kule@market": True})

    kalemler = kesif.skill_kalemleri(ayar, claude)
    assert len(kalemler) == 1
    assert kalemler[0]["kaynak"] == str(guncel / "skills" / "harita" / "SKILL.md")


def test_cache_altindaki_dizin_taranmaz(tmp_path):
    """Plugin kokunun altinda gizli `.cache`/`cache` aynasi sayilmaz (sadece kurulu surum)."""
    claude = sahte_claude_dir(tmp_path / "claude", kur(enabledPlugins={"kule@market": True}))
    kok = _plugin_kur(claude, "kule@market", {"harita": SKILL("harita")})
    sahte_plugin(kok / ".cache" / "v1", {"harita": SKILL("harita", "eski")})
    ayar = kur(enabledPlugins={"kule@market": True})

    assert len(kesif.skill_kalemleri(ayar, claude)) == 1


def test_kurulu_degil_plugin_atlanir(tmp_path):
    """Acik ama installed_plugins.json'da KURULU olmayan plugin sayilmaz (patlamaz)."""
    claude = sahte_claude_dir(tmp_path / "claude", kur(enabledPlugins={"kule@market": True}))
    assert kesif.skill_kalemleri(kur(enabledPlugins={"kule@market": True}), claude) == []


def test_install_path_dizini_degilse_atlanir(tmp_path):
    """installPath var ama dizin degilse (silinmis kurulum) atlanir."""
    claude = sahte_claude_dir(tmp_path / "claude")
    kurulu = claude / "plugins"
    kurulu.mkdir(parents=True, exist_ok=True)
    kurulu.joinpath("installed_plugins.json").write_text(
        json.dumps(
            {"version": 1, "plugins": {"kule@market": [{"installPath": str(tmp_path / "yok")}]}}
        ),
        encoding="utf-8",
    )
    assert kesif.skill_kalemleri(kur(enabledPlugins={"kule@market": True}), claude) == []


# --------------------------------------------------------------------------
# installPath guvenligi: yalniz plugins/ alti
# --------------------------------------------------------------------------


def test_install_path_plugins_disi_atlanir(tmp_path):
    """installPath `claude/plugins` DISINDA ise plugin sayilmaz (ayar dosyasi guvenlik sinirini asar).

    Ayar dosyasi `..` ile istedigi dizini tarattirabilirdi.
    """
    claude = sahte_claude_dir(tmp_path / "claude", kur(enabledPlugins={"kule@market": True}))
    dis = sahte_plugin(tmp_path / "disarida" / "kule", {"harita": SKILL("harita")})
    kurulu = claude / "plugins"
    kurulu.mkdir(parents=True, exist_ok=True)
    (kurulu / "installed_plugins.json").write_text(
        json.dumps({"version": 1, "plugins": {"kule@market": [{"installPath": str(dis)}]}}),
        encoding="utf-8",
    )
    assert kesif.skill_kalemleri(kur(enabledPlugins={"kule@market": True}), claude) == []


def test_install_path_nokta_nokta_kacisi_atlanir(tmp_path):
    """`plugins/../..` ile disari cikan installPath cozulunce REDDEDILIR."""
    claude = sahte_claude_dir(tmp_path / "claude", kur(enabledPlugins={"kule@market": True}))
    dis = sahte_plugin(tmp_path / "disarida" / "kule", {"harita": SKILL("harita")})
    kurulu = claude / "plugins"
    kurulu.mkdir(parents=True, exist_ok=True)
    (kurulu / "installed_plugins.json").write_text(
        json.dumps(
            {
                "version": 1,
                "plugins": {
                    "kule@market": [{"installPath": str(claude / "plugins" / ".." / ".." / "disarida" / "kule")}]
                },
            }
        ),
        encoding="utf-8",
    )
    assert kesif.skill_kalemleri(kur(enabledPlugins={"kule@market": True}), claude) == []


def test_install_path_baglantili_disaridan_gizlenir(tmp_path):
    """plugins/ icinde ama DISARIYA baglanan (symlink) installPath cozulunce reddedilir."""
    claude = sahte_claude_dir(tmp_path / "claude", kur(enabledPlugins={"kule@market": True}))
    dis = sahte_plugin(tmp_path / "disarida" / "kule", {"harita": SKILL("harita")})
    kurulu = claude / "plugins"
    baglanti = kurulu / "kule"
    kurulu.mkdir(parents=True, exist_ok=True)
    if not symlink_kur(baglanti, dis):
        pytest.skip("symlink olusturulamadi (Windows: SeCreateSymbolicLinkYetki/1314)")
    (kurulu / "installed_plugins.json").write_text(
        json.dumps({"version": 1, "plugins": {"kule@market": [{"installPath": str(baglanti)}]}}),
        encoding="utf-8",
    )
    assert kesif.skill_kalemleri(kur(enabledPlugins={"kule@market": True}), claude) == []


# --------------------------------------------------------------------------
# tarama dayanikliligi: dongu, derinlik, okunamayan dosya
# --------------------------------------------------------------------------


def test_baglanti_dongusu_tarama_cocturmaz(tmp_path):
    """Plugin kokunde kendine baglanan (junction) dizin varsa tarAMA COKMEZ.

    `glob("**/")` bu dongude WinError 1921 / sonsuz tekrarla cokuyordu;
    os.walk baglantiyi budar.
    """
    claude = sahte_claude_dir(tmp_path / "claude", kur(enabledPlugins={"kule@market": True}))
    kok = _plugin_kur(claude, "kule@market", {"harita": SKILL("harita")})
    if not junction_kur(kok / "dongu", tmp_path):
        pytest.skip("junction olusturulamadi (mklink /J)")

    kalemler = kesif.skill_kalemleri(kur(enabledPlugins={"kule@market": True}), claude)
    assert _adlar(kalemler) == {"kule:harita"}


def test_baglanti_dizini_iceri_girilmez(tmp_path):
    """Plugin icindeki baska bir yere baglanan dizin (junction) TAKILMAZ, icindeki skill sayilmaz."""
    claude = sahte_claude_dir(tmp_path / "claude", kur(enabledPlugins={"kule@market": True}))
    kok = _plugin_kur(claude, "kule@market", {"harita": SKILL("harita")})
    dis = sahte_plugin(tmp_path / "baska", {"gizli": SKILL("gizli")})
    if not junction_kur(kok / "bagli", dis):
        pytest.skip("junction olusturulamadi (mklink /J)")

    assert _adlar(kesif.skill_kalemleri(kur(enabledPlugins={"kule@market": True}), claude)) == {
        "kule:harita"
    }


def test_tarama_derinlik_sinirina_uyar(tmp_path):
    """DERINLIK sinirindan sonraki SKILL.md sayilmaz; daha usttekiler sayilir."""
    claude = sahte_claude_dir(tmp_path / "claude", kur(enabledPlugins={"kule@market": True}))
    kok = _plugin_kur(claude, "kule@market", {})
    derin = kok / "a" / "b" / "c" / "d" / "e" / "f" / "g"
    derin.mkdir(parents=True)
    (derin / "SKILL.md").write_text(SKILL("cok-derin"), encoding="utf-8")
    sig = kok / "a" / "b"
    (sig / "SKILL.md").write_text(SKILL("sig"), encoding="utf-8")

    adlar = _adlar(kesif.skill_kalemleri(kur(enabledPlugins={"kule@market": True}), claude))
    assert "kule:sig" in adlar
    assert "kule:cok-derin" not in adlar, "derinlik siniri isletilmedi"


def test_okunamayan_skill_taramayi_cocturtmez(tmp_path):
    """SKILL.md yerinde DIZIN ise o skill ATLANIR, digerleri sayilir (tarama cokmez)."""
    claude = sahte_claude_dir(tmp_path / "claude", kur(enabledPlugins={"kule@market": True}))
    kok = _plugin_kur(claude, "kule@market", {"harita": SKILL("harita")})
    (kok / "skills" / "bozuk").mkdir(parents=True, exist_ok=True)
    (kok / "skills" / "bozuk" / "SKILL.md").mkdir()  # SKILL.md aslinda bir dizin

    assert _adlar(kesif.skill_kalemleri(kur(enabledPlugins={"kule@market": True}), claude)) == {
        "kule:harita"
    }


def test_kilitli_skill_atlanir(tmp_path, monkeypatch):
    """SKILL.md okunamazsa (izin/kilit) kalem uretilmez; tarama cokmez."""
    claude = sahte_claude_dir(tmp_path / "claude", skilller={"harita": SKILL("harita")})
    gercek = Path.read_text

    def kilitli(yol, *a, **k):
        if Path(yol).name == "SKILL.md":
            raise PermissionError("kilitli")
        return gercek(yol, *a, **k)

    monkeypatch.setattr(Path, "read_text", kilitli)
    assert kesif.skill_kalemleri(kur(), claude) == []


def test_kodlamasiz_skill_atlanir(tmp_path):
    """SKILL.md UTF-8 DEGILSE atlanilir (UnicodeDecodeError sizmaz)."""
    claude = sahte_claude_dir(tmp_path / "claude", skilller={"harita": SKILL("harita")})
    (claude / "skills" / "harita" / "SKILL.md").write_bytes(b"\xff\xfe\x00\x00\x80\x81")

    assert kesif.skill_kalemleri(kur(), claude) == []


def test_skill_adi_kontrol_karakteri_temizlenir(tmp_path):
    """frontmatter `name` icindeki kontrol karakterleri `?` olur (terminal enjeksiyonu)."""
    kotu = "---\nname: har\x1bita\ndescription: acik\n---\n\ngovde\n"
    claude = sahte_claude_dir(tmp_path / "claude", skilller={"x": kotu})
    kalem = kesif.skill_kalemleri(kur(), claude)[0]
    assert kalem["ad"] == "har?ita", repr(kalem["ad"])
    assert "\x1b" not in kalem["ad"]


# --------------------------------------------------------------------------
# frontmatter
# --------------------------------------------------------------------------


def test_skill_adi_frontmatter_name_dizinden_degil(tmp_path):
    """Ad frontmatter `name`'den gelir; dizin adi farkliysa dizin adi KULLANILMAZ."""
    claude = sahte_claude_dir(tmp_path / "claude", skilller={"dizin-adi": SKILL("gercek-ad")})
    kalemler = kesif.skill_kalemleri(kur(), claude)
    assert _adlar(kalemler) == {"gercek-ad"}


def test_frontmatter_name_yoksa_dizin_adi_dusulur(tmp_path):
    """`name` alani yoksa dizin adi kullanilir (skill yine bulunur)."""
    claude = sahte_claude_dir(
        tmp_path / "claude", skilller={"dizin-adi": "---\ndescription: sadece aciklama\n---\n\ngovde\n"}
    )
    assert _adlar(kesif.skill_kalemleri(kur(), claude)) == {"dizin-adi"}


def test_cok_satirli_aciklama_katlanir(tmp_path):
    """`>` (katlanmis) aciklama satirlari tek satira birlestirilir."""
    icerik = "---\nname: harita\ndescription: >\n  ilk satir\n  ikinci satir\n---\n\ngovde\n"
    claude = sahte_claude_dir(tmp_path / "claude", skilller={"x": icerik})
    alanlar, _ = kesif.frontmatter(icerik)
    assert alanlar["description"] == "ilk satir ikinci satir"


def test_dikey_boru_aciklama_katlanir(tmp_path):
    """`|` (literal blok) ve `>` degil `|-`/`|>` varyantlari da desteklenir."""
    icerik = "---\nname: harita\ndescription: |-\n  birinci\n  ikinci\n---\n\ngovde\n"
    claude = sahte_claude_dir(tmp_path / "claude", skilller={"x": icerik})
    alanlar, _ = kesif.frontmatter(icerik)
    assert alanlar["description"] == "birinci ikinci"
    assert kesif.skill_kalemleri(kur(), claude)[0]["acilis_token"] == olc.skill_acilis(
        "harita", "birinci ikinci"
    )


def test_cok_satirli_aciklama_tokenu_cespitlenir(tmp_path):
    """Cok satirli aciklamanin acilis maliyeti, tek satira KATLANMIS metinle AYNI hesaplanir."""
    katlanmis = "---\nname: harita\ndescription: >\n  ilk satir\n  ikinci satir\n---\n\ngovde\n"
    bekl = olc.skill_acilis("harita", "ilk satir ikinci satir")
    claude = sahte_claude_dir(tmp_path / "claude", skilller={"x": katlanmis})
    kalem = kesif.skill_kalemleri(kur(), claude)[0]
    assert kalem["acilis_token"] == bekl
    assert kalem["ad"] == "harita"


def test_frontmatter_yoksa_tum_metin_govde(tmp_path):
    """`---` ile baslamayan SKILL.md: alanlar bos, metnin tamami govde sayilir."""
    icerik = "sadece govde metni\n"
    alanlar, govde = kesif.frontmatter(icerik)
    assert alanlar == {}
    assert govde == icerik


def test_frontmatter_kapanmamis_govde_tam_metindir(tmp_path):
    """Kapanan `---` yoksa govde BOS kalir; alanlar yine toplanir (yarim dosya patlamaz)."""
    alanlar, govde = kesif.frontmatter("---\nname: harita\ndescription: acik\n")
    assert alanlar["name"] == "harita"
    assert govde == ""


def test_skill_govdesi_cagrilinca_tokenidir(tmp_path):
    """Govde metni `cagrilinca_token`'a girer, `acilis_token`'a GIRMEZ."""
    govde = "x" * 400
    icerik = f"---\nname: harita\ndescription: kisa\n---\n\n{govde}\n"
    claude = sahte_claude_dir(tmp_path / "claude", skilller={"x": icerik})
    kalem = kesif.skill_kalemleri(kur(), claude)[0]
    assert kalem["cagrilinca_token"] > 0
    assert kalem["acilis_token"] == olc.skill_acilis("harita", "kisa")


# --------------------------------------------------------------------------
# gizli dizinler
# --------------------------------------------------------------------------


def test_gizli_dizin_elenir(tmp_path):
    """`.openclaw/skills/...` aynasi sayilmaz: nokta ile baslayan her dizin elenir."""
    claude = sahte_claude_dir(tmp_path / "claude", kur(enabledPlugins={"kule@market": True}))
    kok = _plugin_kur(claude, "kule@market", {"harita": SKILL("harita")})
    sahte_plugin(kok / ".openclaw" / "skills", {"harita": SKILL("harita", "eski ayna")})
    ayar = kur(enabledPlugins={"kule@market": True})

    kalemler = kesif.skill_kalemleri(ayar, claude)
    assert _adlar(kalemler) == {"kule:harita"}


def test_gizli_dizin_derinlikte_elenir(tmp_path):
    """Gizli dizin koktan uzakta da elenir (`a/.eski/b/SKILL.md`)."""
    claude = sahte_claude_dir(tmp_path / "claude", kur(enabledPlugins={"kule@market": True}))
    kok = _plugin_kur(claude, "kule@market", {"harita": SKILL("harita")})
    sahte_plugin(kok / "ic" / ".eski", {"harita": SKILL("harita", "eski")})
    assert _adlar(kesif.skill_kalemleri(kur(enabledPlugins={"kule@market": True}), claude)) == {
        "kule:harita"
    }


def test_kullanici_skillleri_tek_seviye_taranir(tmp_path):
    """Kullanici `skills/` altinda YALNIZ bir seviye inilir: `skills/<ad>/SKILL.md`.

    Plugin'lerde `**/SKILL.md` ile derin arama yapilir; kullanici skill'lerinde
    boyle degil (skill basina bir dizin sozlesmesi).
    """
    claude = sahte_claude_dir(tmp_path / "claude", skilller={"harita": SKILL("harita")})
    derin = claude / "skills" / "grup" / "derin"
    derin.mkdir(parents=True)
    (derin / "SKILL.md").write_text(SKILL("derin"), encoding="utf-8")
    assert _adlar(kesif.skill_kalemleri(kur(), claude)) == {"harita"}


def test_kullanici_skilli_plugin_onesi_gelmez(tmp_path):
    """Kullanici skill'leri `plugin:` onu ALMAZ; `tara` sirasinda once gelir."""
    claude = sahte_claude_dir(
        tmp_path / "claude", kur(enabledPlugins={"kule@market": True}), skilller={"harita": SKILL("harita")}
    )
    _plugin_kur(claude, "kule@market", {"kule-gelistirme": SKILL("kule-gelistirme")})
    kalemler = kesif.skill_kalemleri(kur(enabledPlugins={"kule@market": True}), claude)
    assert [k["ad"] for k in kalemler] == ["kule:kule-gelistirme", "harita"]


# --------------------------------------------------------------------------
# MCP
# --------------------------------------------------------------------------


def test_plugin_mcp_ust_duzey_okunur(tmp_path):
    """Plugin `.mcp.json` sunuculari EN ust duzeydedir (mcpServers yok)."""
    claude = sahte_claude_dir(tmp_path / "claude", kur(enabledPlugins={"kule@market": True}))
    _plugin_kur(claude, "kule@market", {}, mcp={"fetch": {"command": "uvx"}})
    ayar = kur(enabledPlugins={"kule@market": True})

    kalemler = kesif.mcp_kalemleri(ayar, claude)
    assert _adlar(kalemler) == {"fetch"}
    assert kalemler[0]["kaynak"] == "kule@market"


def test_proje_mcp_mcpservers_altindan_okunur(tmp_path):
    """Proje `.mcp.json` sunuculari `mcpServers` ALTINDADIR; ust duzey sayilmaz."""
    claude = sahte_claude_dir(tmp_path / "claude")
    proje = tmp_path / "proje"
    proje.mkdir()
    (proje / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"atlas": {"command": "node"}}, "fetch": {"command": "uvx"}}),
        encoding="utf-8",
    )
    kalemler = kesif.mcp_kalemleri(kur(), claude, proje)
    assert _adlar(kalemler) == {"atlas"}
    assert kalemler[0]["kaynak"] == "proje"


def test_mcp_kalemi_token_olculemez(tmp_path):
    """MCP kalemi: acilis/cagrilinca token YOK, `olculemedi=True` (rapor sifir saymamali)."""
    claude = sahte_claude_dir(tmp_path / "claude")
    proje = tmp_path / "proje"
    proje.mkdir()
    (proje / ".mcp.json").write_text(json.dumps({"mcpServers": {"atlas": {}}}), encoding="utf-8")

    kalem = kesif.mcp_kalemleri(kur(), claude, proje)[0]
    assert kalem["olculemedi"] is True
    assert kalem["acilis_token"] is None and kalem["cagrilinca_token"] is None


def test_bozuk_mcp_json_sessizce_atlanir(tmp_path):
    """Bozuk `.mcp.json` kesfi PATLATMAZ: kalem uretilmez."""
    claude = sahte_claude_dir(tmp_path / "claude")
    proje = tmp_path / "proje"
    proje.mkdir()
    (proje / ".mcp.json").write_text("{bozuk", encoding="utf-8")
    assert kesif.mcp_kalemleri(kur(), claude, proje) == []


def test_mcpservers_sozluk_degilse_kalem_yok(tmp_path):
    """`mcpServers` icerigi sozluk degilse kalem uretilmez (cokmez)."""
    claude = sahte_claude_dir(tmp_path / "claude")
    proje = tmp_path / "proje"
    proje.mkdir()
    (proje / ".mcp.json").write_text(json.dumps({"mcpServers": ["atlas"]}), encoding="utf-8")
    assert kesif.mcp_kalemleri(kur(), claude, proje) == []


# --------------------------------------------------------------------------
# CLAUDE.md zinciri
# --------------------------------------------------------------------------


def test_claude_md_kullanci_dosyasi_bulunur(tmp_path):
    """Kullanici `~/.claude/CLAUDE.md` kalem olarak listelenir."""
    claude = sahte_claude_dir(tmp_path / "claude")
    (claude / "CLAUDE.md").write_text("kisa talimat\n", encoding="utf-8")
    kalemler = kesif.claude_md_kalemleri(claude)
    assert [k["ad"] for k in kalemler] == ["CLAUDE.md"]
    assert kalemler[0]["acilis_token"] == olc.claude_md("kisa talimat\n")


def test_claude_md_proje_zinciri(tmp_path):
    """Proje verilince kullanici + CLAUDE.md + CLAUDE.local.md birlikte raporlanir."""
    claude = sahte_claude_dir(tmp_path / "claude")
    (claude / "CLAUDE.md").write_text("kullanici\n", encoding="utf-8")
    proje = tmp_path / "proje"
    proje.mkdir()
    (proje / "CLAUDE.md").write_text("proje\n", encoding="utf-8")
    (proje / "CLAUDE.local.md").write_text("yerel\n", encoding="utf-8")

    assert len(kesif.claude_md_kalemleri(claude, proje)) == 3


def test_claude_md_local_yoksa_iki_kalem(tmp_path):
    """CLAUDE.local.md yoksa 3. kalem URETILMEZ (dosya yoksa hata degil, kalem degil)."""
    claude = sahte_claude_dir(tmp_path / "claude")
    (claude / "CLAUDE.md").write_text("kullanici\n", encoding="utf-8")
    proje = tmp_path / "proje"
    proje.mkdir()
    (proje / "CLAUDE.md").write_text("proje\n", encoding="utf-8")
    assert len(kesif.claude_md_kalemleri(claude, proje)) == 2


def test_claude_md_dosyasi_yoksa_bos_liste(tmp_path):
    """Hic CLAUDE.md yoksa bos liste (kesif hata vermez)."""
    claude = sahte_claude_dir(tmp_path / "claude")
    assert kesif.claude_md_kalemleri(claude) == []


def test_claude_md_cagrilinca_tokeni_yok(tmp_path):
    """CLAUDE.md tamamen acilista yuklenir: `cagrilinca_token` None'dur."""
    claude = sahte_claude_dir(tmp_path / "claude")
    (claude / "CLAUDE.md").write_text("x" * 100, encoding="utf-8")
    assert kesif.claude_md_kalemleri(claude)[0]["cagrilinca_token"] is None


# --------------------------------------------------------------------------
# kalemler (birlestirilmis)
# --------------------------------------------------------------------------


def test_kalemler_cesitleri_birlestirir(tmp_path):
    """kalemler(): skill + claude_md + mcp tek listede, dogru sirayla."""
    claude = sahte_claude_dir(
        tmp_path / "claude", kur(enabledPlugins={"kule@market": True}), skilller={"harita": SKILL("harita")}
    )
    _plugin_kur(claude, "kule@market", {"kule-gelistirme": SKILL("kule-gelistirme")})
    (claude / "CLAUDE.md").write_text("kullanici\n", encoding="utf-8")
    proje = tmp_path / "proje"
    proje.mkdir()
    (proje / ".mcp.json").write_text(json.dumps({"mcpServers": {"atlas": {}}}), encoding="utf-8")

    turler = [k["tur"] for k in kesif.kalemler(kur(enabledPlugins={"kule@market": True}), claude, proje)]
    assert turler == ["skill", "skill", "claude_md", "mcp"]
