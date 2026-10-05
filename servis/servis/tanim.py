"""Tanim dosyasi (TOML) okuma ve dogrulama.

Yalniz stdlib: `tomllib` (Python 3.11+). Kabuk YOK -- `baslat`/`durdur` argv
listeleri dogrudan `subprocess`'e gider, hicbir zaman `/bin/sh -c` ile
birlestirilmez.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

VARSAYILAN_BEKLE_SN = 20.0
VARSAYILAN_TANIM_ADI = "servisler.toml"

#: saglik_url yalniz bu adreslere gidebilir (yerel yigin araci; dis aga cikmaz).
YEREL_ADRESLER = frozenset({"127.0.0.1", "localhost", "::1", "0:0:0:0:0:0:0:1"})


class ServisHatasi(Exception):
    """Tanim dosyasi okunamadi / gecersiz -- CLI bunu `Hata: ...` ile, cikis 2."""


@dataclass(frozen=True)
class Servis:
    """Tek bir servisin tanimi (normalize edilmis)."""

    ad: str
    port: int
    baslat: list[str]
    cwd: Path | None
    durdur: list[str] | None
    bekle_sn: float
    saglik_url: str | None

    @property
    def komut_metin(self) -> str:
        """Insan-okur komut satiri (yalniz gosterim; kabuk calistirilmaz)."""
        return " ".join(self.baslat)


def _ad_gecerli(ad: str) -> bool:
    """Ad, dosya yoluna donusmemeli: `../`, `/`, bos ad reddedilir."""
    return bool(ad) and ad not in (".", "..") and "/" not in ad and "\\" not in ad and "\0" not in ad


def tanim_yolu(verilen: str | None = None) -> Path:
    """--tanim > SERVIS_TANIM > ~/.servis/servisler.toml."""
    if verilen:
        return Path(verilen).expanduser()
    env = os.environ.get("SERVIS_TANIM")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".servis" / VARSAYILAN_TANIM_ADI


def _argv(tablo: dict, anahtar: str, ad: str, *, zorunlu: bool) -> list[str] | None:
    deger = tablo.get(anahtar)
    if deger is None:
        if zorunlu:
            raise ServisHatasi(f"[servis.{ad}] icinde '{anahtar}' zorunlu")
        return None
    if not isinstance(deger, list) or not deger:
        raise ServisHatasi(f"[servis.{ad}] '{anahtar}' bos olmayan bir liste (argv) olmali")
    if not all(isinstance(d, str) and d for d in deger):
        raise ServisHatasi(f"[servis.{ad}] '{anahtar}' yalniz metin ogelerinden olusmali")
    return list(deger)


def _saglik_url(tablo: dict, ad: str) -> str | None:
    deger = tablo.get("saglik_url")
    if deger is None:
        return None
    if not isinstance(deger, str) or not deger:
        raise ServisHatasi(f"[servis.{ad}] 'saglik_url' metin olmali")
    parca = urlsplit(deger)
    if parca.scheme not in ("http", "https") or not parca.hostname:
        raise ServisHatasi(f"[servis.{ad}] 'saglik_url' http(s):// adresi olmali: {deger}")
    if parca.hostname not in YEREL_ADRESLER:
        raise ServisHatasi(
            f"[servis.{ad}] 'saglik_url' yalniz 127.0.0.1/localhost adresine gidebilir: {deger}"
        )
    return deger


def _servis(ad: str, tablo: dict) -> Servis:
    if not isinstance(tablo, dict):
        raise ServisHatasi(f"[servis.{ad}] bir tablo olmali")

    port = tablo.get("port")
    if not isinstance(port, int) or isinstance(port, bool) or not (0 < port < 65536):
        raise ServisHatasi(f"[servis.{ad}] 'port' 1-65535 arasi bir tam sayi olmali (verilen: {port!r})")

    bekle = tablo.get("bekle_sn", VARSAYILAN_BEKLE_SN)
    if not isinstance(bekle, (int, float)) or isinstance(bekle, bool) or bekle < 0:
        raise ServisHatasi(f"[servis.{ad}] 'bekle_sn' negatif olmayan bir sayi olmali")

    cwd = tablo.get("cwd")
    if cwd is not None:
        if not isinstance(cwd, str) or not cwd:
            raise ServisHatasi(f"[servis.{ad}] 'cwd' metin olmali")
        cwd = Path(cwd).expanduser()

    return Servis(
        ad=ad,
        port=port,
        baslat=_argv(tablo, "baslat", ad, zorunlu=True),  # type: ignore[arg-type]
        cwd=cwd,
        durdur=_argv(tablo, "durdur", ad, zorunlu=False),
        bekle_sn=float(bekle),
        saglik_url=_saglik_url(tablo, ad),
    )


def yukle(yol: Path | None = None) -> dict[str, Servis]:
    """Tanim dosyasini okur ve `{ad: Servis}` dondurur. Dosya/tabloda hata -> ServisHatasi."""
    hedef = tanim_yolu(str(yol) if yol else None)
    try:
        veri = tomllib.loads(hedef.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ServisHatasi(
            f"tanim dosyasi yok: {hedef} (servisler.toml.ornek'i kopyalayin)"
        ) from exc
    except IsADirectoryError as exc:
        raise ServisHatasi(f"tanim dosyasi bir dizin: {hedef}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ServisHatasi(f"tanim dosyasi bozuk TOML ({hedef}): {exc}") from exc
    except (OSError, UnicodeDecodeError) as exc:
        raise ServisHatasi(f"tanim dosyasi okunamadi ({hedef}): {exc}") from exc

    tablolar = veri.get("servis")
    if tablolar is None:
        raise ServisHatasi(f"tanim dosyasinda [servis] tablosu yok ({hedef})")
    if not isinstance(tablolar, dict):
        raise ServisHatasi(f"[servis] bir tablo olmali ({hedef})")

    servisler: dict[str, Servis] = {}
    for ad, tablo in tablolar.items():
        if not _ad_gecerli(ad):
            raise ServisHatasi(
                f"gecersiz servis adi: {ad!r} (bos, '.' , '..', '/' veya '\\' iceremez)"
            )
        servisler[ad] = _servis(ad, tablo)
    if not servisler:
        raise ServisHatasi(f"tanim dosyasinda hic servis yok ({hedef})")
    return servisler


def sec(servisler: dict[str, Servis], adlar: list[str]) -> list[Servis]:
    """Verilen adlari cozumler; ad verilmemisse tum tanimli servisler (tanima gore sirali)."""
    if not adlar:
        return [servisler[ad] for ad in sorted(servisler)]
    bilinmeyen = [ad for ad in adlar if ad not in servisler]
    if bilinmeyen:
        tanilan = ", ".join(sorted(servisler)) or "-"
        raise ServisHatasi(
            f"tanimsiz servis: {', '.join(bilinmeyen)} (tanimli: {tanilan})"
        )
    # Ayni ad birden fazla verilirse tekrar edilmez.
    tekil = list(dict.fromkeys(adlar))
    return [servisler[ad] for ad in tekil]