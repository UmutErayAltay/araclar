"""Kesif: aktif skill / CLAUDE.md / MCP kalemlerini bulur.

Kurallar:
- Sadece `enabledPlugins` icinde ACIK (true) olan plugin'ler sayilir; kapali
  plugin ve `plugins/cache` altindaki eski surumler SAYILMAZ.
- Bir plugin'in `installed_plugins.json` girdisi LISTEDIR (scope basina bir
  kayit); en guncel surum = en son `lastUpdated`/`installedAt`.
- Plugin skill'i `plugin:skill` adiyla raporlanir.
- MCP token'i OLCELEMEZ: kalem `olculemedi=True`, tahmin `None`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from . import olc
from .ayar import claude_dizin, temiz

#: Windows FILE_ATTRIBUTE_REPARSE_POINT (junction noktasi). POSIX'te yok sayilir.
REPARSE_POINT = 0x400

#: Bir plugin kokunde inilacak azami derinlik (sonsuz baglanti zincirine karsi).
DERINLIK = 6


class KesifHatasi(RuntimeError):
    """Plugin verisi okunamadi (kullanim hatasi)."""


def _baglanti(yol: Path) -> bool:
    """Symlink veya Windows junction mi? (3.11 uyumlu: st_file_attributes getattr ile)."""
    try:
        stat = os.lstat(yol)
    except OSError:
        return False
    if os.path.islink(yol):
        return True
    return bool(getattr(stat, "st_file_attributes", 0) & REPARSE_POINT)


def _skill_yollari(kok: Path) -> list[Path]:
    """`kok` altindaki SKILL.md'ler.

    `Path.glob("**/")` junction/symlink DONGUSUNDE takilir (sonsuz); `os.walk`
    baglantilari budar, derinlik sinirlidir ve hata yutulur (tarama cokmez).
    """
    bulunan: list[Path] = []
    for mevcut, dizinler, dosyalar in os.walk(kok, topdown=True, followlinks=False, onerror=lambda _e: None):
        dizinler[:] = [d for d in dizinler if not _baglanti(Path(mevcut) / d)]
        if Path(mevcut) != kok and len(Path(mevcut).relative_to(kok).parts) >= DERINLIK:
            dizinler.clear()  # asagi inme: sinir asildi
        bulunan += [Path(mevcut) / ad for ad in dosyalar if ad == "SKILL.md"]
    return sorted(bulunan)


def _json(yol: Path) -> dict:
    """JSON oku; yoksa/bozuksa bos sozluk (kesif bunu hataya saymaz)."""
    try:
        veri = json.loads(yol.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return veri if isinstance(veri, dict) else {}


def _plugin_adi(anahtar: str) -> str:
    """`ad@pazar` -> `ad`."""
    return anahtar.split("@", 1)[0]


def _guncel_girdi(girdiler: object) -> dict | None:
    """Scope basina birden fazla kurulum olabilir: en guncel surumu secer."""
    if not isinstance(girdiler, list):
        return None
    gecerli = [g for g in girdiler if isinstance(g, dict) and g.get("installPath")]
    if not gecerli:
        return None
    return max(gecerli, key=lambda g: (g.get("lastUpdated") or "", g.get("installedAt") or ""))


def _acik_pluginlar(ayar: dict, claude: Path) -> dict[str, Path]:
    """Acik plugin anahtari (`ad@pazar`) -> installPath; kurulu degilse atlanir.

    installPath `claude/plugins` ALTINDA olmalidir: ayar dosyasi `..` ile disari
    cikip baska bir dizini tarattirmak (veya baglanti ile kovmak) istemez.
    """
    kurulu = _json(claude / "plugins" / "installed_plugins.json").get("plugins")
    kurulu = kurulu if isinstance(kurulu, dict) else {}
    izinli = (claude / "plugins").resolve()
    bulunan: dict[str, Path] = {}
    for anahtar, acik_mi in (ayar.get("enabledPlugins") or {}).items():
        if not acik_mi:
            continue  # kapali plugin sayilmaz
        girdi = _guncel_girdi(kurulu.get(anahtar))
        if girdi is None:
            continue  # kurulu degil
        yol = Path(girdi["installPath"]).expanduser()
        try:
            cozulmus = yol.resolve()
        except OSError:
            continue  # cozulemiyor: sayma
        if cozulmus != izinli and izinli not in cozulmus.parents:
            continue  # plugins/ disinda: sayma
        if cozulmus.is_dir():
            bulunan[anahtar] = cozulmus
    return bulunan


def frontmatter(metin: str) -> tuple[dict[str, str], str]:
    """(frontmatter sozlugu, govde metni).

    Basit satir ayristirmasi; PyYAML yok. `key: deger` ve cok satirli
    `>` / `|` bloklari desteklenir.
    """
    satirlar = metin.splitlines()
    bas = 0
    while bas < len(satirlar) and not satirlar[bas].strip():
        bas += 1
    if bas >= len(satirlar) or satirlar[bas].strip() != "---":
        return {}, metin  # frontmatter yok: metnin tamami govde
    son = bas + 1
    while son < len(satirlar) and satirlar[son].strip() != "---":
        son += 1
    govde = "\n".join(satirlar[son + 1 :])

    alanlar: dict[str, str] = {}
    anahtar: str | None = None
    blok: list[str] = []

    def kapat() -> None:
        """Yarim kalan blok degerini yaz (yoksa islem yok)."""
        if anahtar is not None:
            alanlar[anahtar] = " ".join(b for b in blok if b)
            blok.clear()

    for satir in satirlar[bas + 1 : son]:
        girinti = len(satir) - len(satir.lstrip())
        if girinti == 0 and ":" in satir:
            kapat()
            anahtar, _, deger = satir.partition(":")
            anahtar, deger = anahtar.strip(), deger.strip()
            if deger in (">", "|", ">-", "|-"):
                blok = []  # asagi girintili satirlar toplanacak
            else:
                alanlar[anahtar] = deger
                anahtar = None
        elif anahtar is not None:
            blok.append(satir.strip())
    kapat()
    return alanlar, govde


def _gizli_mi(yol: Path, kok: Path) -> bool:
    """Yolun herhangi bir parcasi nokta ile basliyor mu?

    Plugin'ler ic yapilarini gizli dizinlerde tutar (orn. `.openclaw/skills/`
    ayni skill'lerin eski bir aynasi); bunlar sayilmaz.
    """
    return any(parca.startswith(".") for parca in yol.relative_to(kok).parts)


def _skill_kalemi(plugin: str | None, yol: Path, kapali_olanlar: set[str]) -> dict | None:
    """SKILL.md -> kalem. Govde/description METNI rapora GIRMEZ, yalniz sayi.

    Ad = frontmatter `name`; plugin skill'i `plugin:skill` seklinde raporlanir
    (skillOverrides anahtariyla ayni yazim). Okunamayan SKILL.md (dizin, kilitli,
    bozuk kodlama) None doner: TARAMA COKMEZ.
    """
    try:
        metin = yol.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    alanlar, govde = frontmatter(metin)
    ad = temiz(alanlar.get("name") or yol.parent.name)
    tam = f"{plugin}:{ad}" if plugin else ad
    return {
        "tur": "skill",
        "ad": temiz(tam),
        "kaynak": str(yol),
        "acilis_token": olc.skill_acilis(ad, alanlar.get("description", "")),
        "cagrilinca_token": olc.skill_govde(govde),
        "kapali": tam in kapali_olanlar,
        "olculemedi": False,
    }


def skill_kalemleri(ayar: dict, claude: Path | None = None) -> list[dict]:
    """Aktif plugin skill'leri + kullanici skill'leri."""
    claude = claude or claude_dizin()
    kapali = {
        ad for ad, deger in (ayar.get("skillOverrides") or {}).items() if deger == "off"
    }
    kalemler: list[dict] = []

    for anahtar, kok in _acik_pluginlar(ayar, claude).items():
        for yol in _skill_yollari(kok):
            if _gizli_mi(yol, kok):
                continue  # gizli ic dizin (eski ayna/ornek kopya)
            kalem = _skill_kalemi(_plugin_adi(anahtar), yol, kapali)
            if kalem is not None:
                kalemler.append(kalem)

    skills = claude / "skills"
    if skills.is_dir():
        for yol in sorted(skills.glob("*/SKILL.md")):
            kalem = _skill_kalemi(None, yol, kapali)
            if kalem is not None:
                kalemler.append(kalem)

    return kalemler


def claude_md_kalemleri(claude: Path | None = None, proje: Path | None = None) -> list[dict]:
    """CLAUDE.md zinciri: kullanici + proje (CLAUDE.md, CLAUDE.local.md)."""
    claude = claude or claude_dizin()
    yollar = [claude / "CLAUDE.md"]
    if proje is not None:
        proje = Path(proje).expanduser()
        yollar += [proje / "CLAUDE.md", proje / "CLAUDE.local.md"]

    kalemler: list[dict] = []
    for yol in yollar:
        try:
            metin = yol.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue  # yok/erisilemedi: kalem degil
        kalemler.append(
            {
                "tur": "claude_md",
                "ad": yol.name,
                "kaynak": str(yol),
                "acilis_token": olc.claude_md(metin),
                "cagrilinca_token": None,
                "kapali": False,
                "olculemedi": False,
            }
        )
    return kalemler


def mcp_kalemleri(ayar: dict, claude: Path | None = None, proje: Path | None = None) -> list[dict]:
    """Proje `.mcp.json` + aktif plugin `.mcp.json` sunucu adlari.

    Token maliyeti OLCELEMEZ: sunucu tanimlari baglam metnine girmez.
    """
    claude = claude or claude_dizin()
    kalemler: list[dict] = []

    def ekle(yol: Path, kaynak: str, ic: str | None) -> None:
        """ic: alt anahtar (proje: 'mcpServers') veya None (plugin: ust duzey)."""
        veri = _json(yol)
        sunucular = veri.get(ic) if ic else veri
        if not isinstance(sunucular, dict):
            return
        for ad in sunucular:
            kalemler.append(
                {
                    "tur": "mcp",
                    "ad": ad,
                    "kaynak": kaynak,
                    "acilis_token": None,
                    "cagrilinca_token": None,
                    "kapali": False,
                    "olculemedi": True,
                }
            )

    if proje is not None:
        # Proje `.mcp.json`: sunucular `mcpServers` altinda.
        ekle(Path(proje).expanduser() / ".mcp.json", "proje", "mcpServers")
    for anahtar, kok in _acik_pluginlar(ayar, claude).items():
        # Plugin `.mcp.json`: sunucular ust duzeyde.
        ekle(kok / ".mcp.json", anahtar, None)
    return kalemler


def kalemler(ayar: dict, claude: Path | None = None, proje: Path | None = None) -> list[dict]:
    """Tum baglam kalemleri: skill + claude_md + mcp."""
    return (
        skill_kalemleri(ayar, claude)
        + claude_md_kalemleri(claude, proje)
        + mcp_kalemleri(ayar, claude, proje)
    )