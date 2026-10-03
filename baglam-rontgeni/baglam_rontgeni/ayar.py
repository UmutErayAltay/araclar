"""Ayar: settings.json okuma, kapat/ac plani, atomik yazma.

Guvenlik:
- `yaz(..., uygula=False)` HICBIR dosya sistemi degisikligi yapmaz.
- Gercek yazmada once zaman damgali yedek (`rontgen-bak-...`), sonra
  gecici dosya + os.replace (atomik).
- Yazma oncesi hedef yeniden okunur (`beklenen`): baska bir surec araya
  girdiyse (TOCTOU) ustune YAZILMAZ.
- Hedef `plugin:skill` / `ad@pazar` / duz ad olmak zorunda; `..` ve kontrol
  karakterleri reddedilir.
- Yalniz `skillOverrides` ve `enabledPlugins` anahtarlari degisir; diger
  anahtarlar ve anahtar sirasi korunur.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import time
from datetime import datetime
from pathlib import Path

#: Yalniz bu iki anahtara dokunulur.
IZINLI_ANAHTARLAR = ("skillOverrides", "enabledPlugins")

#: Gecerli hedef: `plugin:skill`, `ad@pazar` ya da duz kullanici skill adi.
_HEDEF_DESEN = re.compile(r"[A-Za-z0-9_.@:-]+")

#: Saklanan yedek sayisi (rotasyon: en yeniler bu kadar kalir, eskiler silinir).
YEDEK_ADETI = 5

#: Yarim kalmis gecici dosya yasi (saniye): bu kadar eskisi silinir.
GECICI_YAS = 3600


class AyarHatasi(RuntimeError):
    """settings.json okunamadi/bozuk (kullanim hatasi)."""


def mutlak(yol: Path | str) -> Path:
    """Goreli yolu calisma dizinine gore mutlaklastirir (ozel/baglanti yollari dokunulmaz)."""
    yol = Path(yol)
    return yol.resolve() if not yol.is_absolute() else yol


def temiz(metin: object) -> str:
    """Terminale basilacak metinden kontrol karakterlerini `?` ile siler.

    Skill adi/ayar anahtari dosya iceriginden gelir; ESC/DEL gibi karakterler
    terminale yazilirsa satiri bozar (ANSI enjeksiyonu).
    """
    return "".join("?" if ord(k) < 32 or ord(k) == 127 else k for k in str(metin))


def claude_dizin() -> Path:
    """CLAUDE_DIR varsa o, yoksa ~/.claude (goreli yol mutlaklastirilir)."""
    env = os.environ.get("CLAUDE_DIR")
    return mutlak(Path(env).expanduser() if env else Path.home() / ".claude")


def ayar_yolu(dizin: Path | None = None) -> Path:
    return (dizin or claude_dizin()) / "settings.json"


def oku(yol: Path | None = None) -> dict:
    """settings.json'u sozluk olarak okur; dosya yoksa/bozuksa AyarHatasi."""
    yol = ayar_yolu(yol) if yol is None else Path(yol)
    try:
        metin = yol.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise AyarHatasi(f"settings.json bulunamadi: {yol}") from exc
    except OSError as exc:
        raise AyarHatasi(f"settings.json okunamadi: {yol} ({exc})") from exc
    try:
        veri = json.loads(metin)
    except json.JSONDecodeError as exc:
        raise AyarHatasi(f"settings.json bozuk ({exc}): {yol}") from exc
    if not isinstance(veri, dict):
        raise AyarHatasi(f"settings.json sozluk degil: {yol}")
    for anahtar in IZINLI_ANAHTARLAR:
        if anahtar in veri and not isinstance(veri[anahtar], dict):
            raise AyarHatasi(f"settings.json `{anahtar}` sozluk degil: {yol}")
    return veri


def _pluginler(ayar: dict) -> dict:
    return ayar.get("enabledPlugins") or {}


def _plugin_adlari(ayar: dict) -> set[str]:
    """enabledPlugins anahtarlarindan plugin adlari (`ad@pazar` -> `ad`)."""
    return {anahtar.split("@", 1)[0] for anahtar in _pluginler(ayar)}


def _plan(ayar: dict, hedef: str, acik: bool) -> tuple[dict, list[str]]:
    """(yeni ayar, diff satirlari). Anahtar sirasi ve diger ayarlar korunur."""
    _hedefi_dogrula(hedef)
    # Kopyala: girdi sozlugu degismez (cagiran kuru calistirma sonrasi eski hali kullanir).
    yeni = dict(ayar)

    if ":" in hedef or "@" not in hedef:
        # plugin:skill veya kullanici skill'i (duz ad) -> skillOverrides[hedef] = "off" / anahtari kaldir
        if ":" in hedef and hedef.split(":", 1)[0] not in _plugin_adlari(ayar):
            raise ValueError(f"bilinmeyen plugin: {hedef.split(':', 1)[0]}")
        kaynak = _anahtar_sozlugu(yeni, "skillOverrides")
        if acik:
            if kaynak.get(hedef) != "off":
                return yeni, []
            del kaynak[hedef]
            return yeni, [f'- skillOverrides["{hedef}"] = "off"  (anahtar silinecek)']
        if kaynak.get(hedef) == "off":
            return yeni, []
        eski = kaynak.get(hedef)
        kaynak[hedef] = "off"
        if eski is None:
            return yeni, [f'+ skillOverrides["{hedef}"] = "off"']
        # Deger degistiriliyor (ornegin nesne): eski deger de gorunur.
        return yeni, [f'~ skillOverrides["{hedef}"] = "off"  (eski: {_deger(eski)})']

    # ad@pazar plugin -> enabledPlugins[hedef] = false/true
    if hedef not in _pluginler(ayar):
        raise ValueError(f"bilinmeyen plugin: {hedef}")
    kaynak = _anahtar_sozlugu(yeni, "enabledPlugins")
    eski = bool(kaynak.get(hedef))
    if eski == acik:
        return yeni, []
    kaynak[hedef] = acik
    return yeni, [f"  enabledPlugins[{hedef!r}]: {str(eski).lower()} -> {str(acik).lower()}"]


def _hedefi_dogrula(hedef: str) -> None:
    """Hedef yalniz `plugin:skill` / `ad@pazar` / duz ad olabilir.

    Bos ad, `kule:` (skill adi bos) ve yol/kaçis karakteri iceren hedef reddedilir:
    anahtar JSON'a dogrudan yazilir, kontrol karakteri terminale sizabilir.
    """
    if not isinstance(hedef, str) or not hedef:
        raise ValueError("gecersiz hedef: bos")
    if ".." in hedef or not _HEDEF_DESEN.fullmatch(hedef):
        raise ValueError(f"gecersiz hedef: {hedef!r}")
    if hedef.endswith(":"):
        raise ValueError(f"gecersiz hedef: {hedef!r} (skill adi bos)")


def _deger(deger: object) -> str:
    """Eski degeri tek satirlik, kisaltilmis metin olarak yazar (diff satiri icin)."""
    metin = json.dumps(deger, ensure_ascii=False)
    return metin if len(metin) <= 60 else metin[:57] + "..."


def degisiklik_plani(ayar: dict, hedef: str, acik: bool) -> list[str]:
    """Yazmadan once gosterilecek diff satirlari (dosyaya dokunmaz)."""
    return _plan(ayar, hedef, acik)[1]


def uygulanan_ayar(ayar: dict, hedef: str, acik: bool) -> dict:
    """Plani uygulanmis ayarin KOPYASI (orijinal ayar degismez)."""
    return _plan(ayar, hedef, acik)[0]


def _anahtar_sozlugu(yeni: dict, anahtar: str) -> dict:
    """Alt sozlugu kopyala; anahtari yoksa ayni yerine koy (sira degismez)."""
    mevcut = yeni.get(anahtar)
    kopya = dict(mevcut) if isinstance(mevcut, dict) else {}
    yeni[anahtar] = kopya
    return kopya


def yaz(yol: Path, yeni: dict, uygula: bool, *, bekle: dict | None = None) -> Path | None:
    """settings.json'u yazar; `uygula=False` ise DOSYAYA DOKUNMAZ.

    `bekle`: `oku()` ile okunmus orijinal ayar. Verilirse yazma oncesi hedef
    YENIDEN okunur; arada degistiyse (baska surec yazdi) AyarHatasi firlatilir
    (TOCTOU: yedek alindi ama hedef degismis olurdu).

    Donus: uygulandiysa yazilan yol (symlink ise hedefi), kuru calistirmada None.
    """
    yol = mutlak(yol)
    if not uygula:
        return None  # kuru calistirma: dosya sistemine hic dokunma

    # Symlink ise BAGLANTI KIRILMAZ: gercek dosya (hedef) yazilir.
    gercek = yol.resolve() if os.path.islink(yol) else yol

    if bekle is not None and oku(gercek) != bekle:
        raise AyarHatasi("settings.json arada degisti, tekrar deneyin")

    _eski_gecici_sil(gercek)
    yedek = gercek.with_name(f"{gercek.name}.rontgen-bak-{datetime.now():%Y%m%dT%H%M%S%f}")
    shutil.copy2(gercek, yedek)
    _kisitla(yedek)
    _yedekleri_kirp(gercek)

    fd, gecici_ad = tempfile.mkstemp(dir=gercek.parent, prefix=gercek.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as akim:
            json.dump(yeni, akim, ensure_ascii=False, indent=2)
        _kisitla(gecici_ad)
        os.replace(gecici_ad, gercek)
    except BaseException:
        Path(gecici_ad).unlink(missing_ok=True)
        raise
    return gercek


def _kisitla(yol: str | Path) -> None:
    """Sadece sahibi okuyup yazsin (Windows disinda); desteklenmeyen sistemde yoksay."""
    try:
        os.chmod(yol, 0o600)
    except (OSError, NotImplementedError):
        pass


def _yedekleri_kirp(yol: Path) -> None:
    """`settings.json.rontgen-bak-*`: en yeniden YEDEK_ADETI tane birak, eskileri sil."""
    yedekler = sorted(
        (p for p in yol.parent.glob(f"{yol.name}.rontgen-bak-*") if p.is_file()),
        key=lambda p: p.name,
        reverse=True,
    )
    for eski in yedekler[YEDEK_ADETI:]:
        try:
            eski.unlink()
        except OSError:
            pass  # silinemezse yazma akisini bozma


def _eski_gecici_sil(yol: Path) -> None:
    """Yarim kalmis kendi gecici dosyalarimizi temizler (`settings.json*.tmp`).

    Yalniz bu modulin mkstemp desenine ait dosyalar (bizim prefix'li + .tmp),
    GECICI_YAS'tan eskiyse silinir; baska yazma sizmaz.
    """
    simdi = time.time()
    for aday in yol.parent.glob(f"{yol.name}*.tmp"):
        try:
            if simdi - aday.stat().st_mtime > GECICI_YAS:
                aday.unlink()
        except OSError:
            continue