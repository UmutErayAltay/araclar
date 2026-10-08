"""Onbellek: genel (kullanici bazli) onbellek yonetimi (PLAN.md §2).

- Yol cozumu platforma gore (Windows: LOCALAPPDATA/APPDATA; diger: ~/.cache, XDG_CACHE_HOME)
- Ortam degiskeni onceligi (PIP_CACHE_DIR, npm_config_cache, UV_CACHE_DIR, CARGO_HOME, GRADLE_USER_HOME)
- Komutla temizleme: shutil.which, shell=False, timeout=300; basarisizsa klasore DUSMEZ
- docker system df: yalniz rapor, yoksa sessiz gecis
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final


@dataclass(frozen=True)
class OnbellekKurali:
    """Genel onbellek kurali."""
    ad: str                    # "pip", "npm", ...
    grup: str                  # "python", "js", "rust", "jvm", "genel"
    risk: str                  # "guvenli" | "dikkat"
    windows_yollar: tuple[str, ...]   # %LOCALAPPDATA%, %APPDATA% kullanir
    unix_yollar: tuple[str, ...]      # ~/, ~/.cache, XDG_CACHE_HOME kullanir
    env_degiskenleri: tuple[str, ...] # once env, sonra yollar
    temizleme_komutu: tuple[str, ...] | None  # None = klasor silme (dikkat!)
    aciklama: str


# PLAN.md §2 tablo
_ONBELLEK_KURALLARI: Final[list[OnbellekKurali]] = [
    OnbellekKurali(
        ad="pip",
        grup="python",
        risk="guvenli",
        windows_yollar=(
            r"%LOCALAPPDATA%\pip\Cache",
            r"%APPDATA%\pip\Cache",
        ),
        unix_yollar=(
            "~/.cache/pip",
            "$XDG_CACHE_HOME/pip",
        ),
        env_degiskenleri=("PIP_CACHE_DIR",),
        temizleme_komutu=("pip", "cache", "purge"),
        aciklama="pip cache purge calistirilir",
    ),
    OnbellekKurali(
        ad="npm",
        grup="js",
        risk="guvenli",
        windows_yollar=(
            r"%LOCALAPPDATA%\npm-cache",
            r"%APPDATA%\npm-cache",
        ),
        unix_yollar=(
            "~/.npm/_cacache",
            "$XDG_CACHE_HOME/npm",
        ),
        env_degiskenleri=("npm_config_cache",),
        temizleme_komutu=("npm", "cache", "clean", "--force"),
        aciklama="npm cache clean --force calistirilir",
    ),
    OnbellekKurali(
        ad="yarn",
        grup="js",
        risk="guvenli",
        windows_yollar=(
            r"%LOCALAPPDATA%\Yarn\Cache",
            r"%APPDATA%\Yarn\Cache",
        ),
        unix_yollar=(
            "~/.cache/yarn",
            "$XDG_CACHE_HOME/yarn",
        ),
        env_degiskenleri=("YARN_CACHE_FOLDER",),
        temizleme_komutu=("yarn", "cache", "clean"),
        aciklama="yarn cache clean calistirilir",
    ),
    OnbellekKurali(
        ad="pnpm",
        grup="js",
        risk="guvenli",
        windows_yollar=(
            r"%LOCALAPPDATA%\pnpm\store",
            r"%APPDATA%\pnpm\store",
        ),
        unix_yollar=(
            "~/.local/share/pnpm/store",
            "$XDG_CACHE_HOME/pnpm/store",
        ),
        env_degiskenleri=("PNPM_HOME", "PNPM_STORE_PATH"),
        temizleme_komutu=("pnpm", "store", "prune"),
        aciklama="pnpm store prune calistirilir",
    ),
    OnbellekKurali(
        ad="uv",
        grup="python",
        risk="guvenli",
        windows_yollar=(
            r"%LOCALAPPDATA%\uv\cache",
            r"%APPDATA%\uv\cache",
        ),
        unix_yollar=(
            "~/.cache/uv",
            "$XDG_CACHE_HOME/uv",
        ),
        env_degiskenleri=("UV_CACHE_DIR",),
        temizleme_komutu=("uv", "cache", "clean"),
        aciklama="uv cache clean calistirilir",
    ),
    OnbellekKurali(
        ad="cargo",
        grup="rust",
        risk="guvenli",
        windows_yollar=(
            r"%USERPROFILE%\.cargo\registry",
        ),
        unix_yollar=(
            "~/.cargo/registry",
            "$CARGO_HOME/registry",
        ),
        env_degiskenleri=("CARGO_HOME",),
        temizleme_komutu=None,  # klasor: cache/ ve src/ silinir
        aciklama="~/.cargo/registry/cache/ ve src/ silinir",
    ),
    OnbellekKurali(
        ad="gradle",
        grup="jvm",
        risk="guvenli",
        windows_yollar=(
            r"%USERPROFILE%\.gradle\caches",
        ),
        unix_yollar=(
            "~/.gradle/caches",
            "$GRADLE_USER_HOME/caches",
        ),
        env_degiskenleri=("GRADLE_USER_HOME",),
        temizleme_komutu=None,  # klasor silinir
        aciklama="~/.gradle/caches silinir",
    ),
    OnbellekKurali(
        ad="playwright",
        grup="genel",
        risk="dikkat",
        windows_yollar=(
            r"%LOCALAPPDATA%\ms-playwright",
        ),
        unix_yollar=(
            "~/.cache/ms-playwright",
            "$XDG_CACHE_HOME/ms-playwright",
        ),
        env_degiskenleri=("PLAYWRIGHT_BROWSERS_PATH",),
        temizleme_komutu=None,
        aciklama="tarayicilar yeniden indirilir (GB'larca)",
    ),
    OnbellekKurali(
        ad="huggingface",
        grup="genel",
        risk="dikkat",
        windows_yollar=(
            r"%USERPROFILE%\.cache\huggingface",
        ),
        unix_yollar=(
            "~/.cache/huggingface",
            "$XDG_CACHE_HOME/huggingface",
            "$HF_HOME",
        ),
        env_degiskenleri=("HF_HOME", "HUGGINGFACE_HUB_CACHE"),
        temizleme_komutu=None,
        aciklama="modeller yeniden indirilir (GB'larca)",
    ),
]


def _yol_coz(yol: str) -> Path | None:
    """Yol string'ini cozer: ~, $VAR, %VAR% -> Path. Yoksa None."""
    if not yol:
        return None
    # Ortam degiskeni genisletme ($VAR veya ${VAR})
    genisletilmis = os.path.expandvars(yol)
    # ~ genisletme
    genisletilmis = os.path.expanduser(genisletilmis)
    p = Path(genisletilmis)
    return p if p.exists() else None


def _onbellek_yolu_bul(kural: OnbellekKurali) -> Path | None:
    """Onbellek kurali icin once env degiskenleri, sonra platform yollarini dener."""
    # Once ortam degiskenleri
    for env in kural.env_degiskenleri:
        deger = os.environ.get(env)
        if deger:
            p = _yol_coz(deger)
            if p:
                return p

    # Platforma gore yollar
    if os.name == "nt":
        yollar = kural.windows_yollar
    else:
        yollar = kural.unix_yollar

    for yol in yollar:
        p = _yol_coz(yol)
        if p:
            return p
    return None


def _boyut_hesapla(yol: Path) -> int:
    """Dizin boyutu (bayt). Baglanti izlenmez, hata yutulur."""
    toplam = 0
    try:
        for mevcut, dizinler, dosyalar in os.walk(
            yol, topdown=True, followlinks=False, onerror=lambda _e: None
        ):
            kok = Path(mevcut)
            for ad in dosyalar:
                try:
                    toplam += (kok / ad).lstat().st_size
                except OSError:
                    continue
    except OSError:
        pass
    return toplam


def _komut_calistir(komut: tuple[str, ...], timeout: int = 300) -> tuple[bool, str]:
    """Komutu calistirir; (basarili_mi, cikti). shell=False, timeout."""
    try:
        # once komut PATH'te var mi?
        if not shutil.which(komut[0]):
            return False, f"komut bulunamadi: {komut[0]}"
        sonuc = subprocess.run(
            list(komut),
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
        if sonuc.returncode == 0:
            return True, sonuc.stdout.strip()
        return False, sonuc.stderr.strip() or sonuc.stdout.strip() or f"cikis kodu {sonuc.returncode}"
    except subprocess.TimeoutExpired:
        return False, f"zaman asimi ({timeout} sn)"
    except OSError as exc:
        return False, str(exc)


def onbellek_tara() -> list[dict]:
    """Tum genel onbellekleri tarar; her biri icin sozluk dondurur.

    Donus: [{id, ad, yol, boyut, risk, komut, var, yontem, aciklama}]
    """
    import hashlib
    sonuc: list[dict] = []
    for kural in _ONBELLEK_KURALLARI:
        yol = _onbellek_yolu_bul(kural)
        var = yol is not None
        boyut = _boyut_hesapla(yol) if var else 0
        komut = kural.temizleme_komutu
        # ID: ad + yol'un sha1[:12] (yol yoksa ad'in sha1'i)
        id_veri = (kural.ad + (str(yol) if yol else "")).encode("utf-8")
        oid = hashlib.sha1(id_veri).hexdigest()[:12]
        yontem = "komut" if komut else "klasor"
        sonuc.append({
            "id": oid,
            "ad": kural.ad,
            "grup": kural.grup,
            "yol": str(yol) if yol else "",
            "boyut": boyut,
            "risk": kural.risk,
            "komut": list(komut) if komut else None,
            "var": var,
            "yontem": yontem,
            "aciklama": kural.aciklama,
        })
    return sonuc


def onbellek_temizle(ad: str, *, uygula: bool = True, timeout: int = 300) -> dict:
    """Belirli bir onbellegi temizler.

    Donus: {id, ad, yol, onceki_boyut, bosalan_bayt, basarili, yontem, hata}
    """
    kural = next((k for k in _ONBELLEK_KURALLARI if k.ad == ad), None)
    if kural is None:
        return {"id": "", "ad": ad, "hata": "bilinmeyen onbellek"}

    yol = _onbellek_yolu_bul(kural)
    onceki_boyut = _boyut_hesapla(yol) if yol else 0
    oid = hashlib.sha1((kural.ad + (str(yol) if yol else "")).encode("utf-8")).hexdigest()[:12]

    if not yol or not yol.exists():
        return {
            "id": oid,
            "ad": ad,
            "yol": str(yol) if yol else "",
            "onceki_boyut": 0,
            "bosalan_bayt": 0,
            "basarili": True,
            "yontem": "yok",
            "hata": None,
        }

    if not uygula:
        return {
            "id": oid,
            "ad": ad,
            "yol": str(yol),
            "onceki_boyut": onceki_boyut,
            "bosalan_bayt": 0,
            "basarili": True,
            "yontem": "kuru-calisma",
            "hata": None,
        }

    # Komutla temizleme
    if kural.temizleme_komutu:
        basarili, cikti = _komut_calistir(kural.temizleme_komutu, timeout)
        if not basarili:
            # Komut basarisiz -> klasore DUSMEZ
            return {
                "id": oid,
                "ad": ad,
                "yol": str(yol),
                "onceki_boyut": onceki_boyut,
                "bosalan_bayt": 0,
                "basarili": False,
                "yontem": "komut",
                "hata": f"komut basarisiz: {cikti}",
            }
        # Basariliysa boyut farkini olc
        yeni_boyut = _boyut_hesapla(yol)
        return {
            "id": oid,
            "ad": ad,
            "yol": str(yol),
            "onceki_boyut": onceki_boyut,
            "bosalan_bayt": max(0, onceki_boyut - yeni_boyut),
            "basarili": True,
            "yontem": "komut",
            "hata": None,
        }

    # Klasor temizleme (temizleme_komutu None)
    try:
        if yol.is_dir():
            shutil.rmtree(yol, onerror=lambda f, p, e: None)
        yeni_boyut = 0
        return {
            "id": oid,
            "ad": ad,
            "yol": str(yol),
            "onceki_boyut": onceki_boyut,
            "bosalan_bayt": onceki_boyut,
            "basarili": True,
            "yontem": "klasor",
            "hata": None,
        }
    except OSError as exc:
        return {
            "id": oid,
            "ad": ad,
            "yol": str(yol),
            "onceki_boyut": onceki_boyut,
            "bosalan_bayt": 0,
            "basarili": False,
            "yontem": "klasor",
            "hata": str(exc),
        }


def docker_boyutlari() -> dict:
    """docker system df --format json ciktisini parse eder.

    Donus: {var: bool, imaj, konteyner, volume, build_cache, hata}
    Sadece rapor icin; hata durumunda sessizce {var: False, ...} dondurur.
    """
    varsayilan = {
        "var": False,
        "imaj": 0,
        "konteyner": 0,
        "volume": 0,
        "build_cache": 0,
        "hata": None,
    }
    if not shutil.which("docker"):
        return varsayilan
    try:
        sonuc = subprocess.run(
            ["docker", "system", "df", "--format", "json"],
            capture_output=True,
            text=True,
            timeout=30,
            shell=False,
        )
        if sonuc.returncode != 0:
            return varsayilan | {"hata": sonuc.stderr.strip() or f"cikis {sonuc.returncode}"}
        import json
        # docker system df --format json satir satir JSON verir
        # Ornek: {"Type":"Images","TotalCount":"5","Size":"1.2GB","Reclaimable":"800MB"}
        # Biz sadece "Reclaimable" alanlarini topluyoruz.
        imaj = konteyner = volume = build_cache = 0
        for satir in sonuc.stdout.strip().splitlines():
            satir = satir.strip()
            if not satir:
                continue
            try:
                veri = json.loads(satir)
            except json.JSONDecodeError:
                continue
            tur = veri.get("Type", "")
            reclaim = veri.get("Reclaimable", "0B")
            # "800MB" -> bayt
            def _parse_boyut(s: str) -> int:
                s = s.strip().upper()
                if s.endswith("KB"):
                    return int(float(s[:-2]) * 1024)
                if s.endswith("MB"):
                    return int(float(s[:-2]) * 1024 * 1024)
                if s.endswith("GB"):
                    return int(float(s[:-2]) * 1024 * 1024 * 1024)
                if s.endswith("B"):
                    return int(s[:-1])
                return 0

            boyut = _parse_boyut(reclaim)
            if tur == "Images":
                imaj = boyut
            elif tur == "Containers":
                konteyner = boyut
            elif tur == "Local Volumes":
                volume = boyut
            elif tur == "Build Cache":
                build_cache = boyut
        return {
            "var": True,
            "imaj": imaj,
            "konteyner": konteyner,
            "volume": volume,
            "build_cache": build_cache,
            "hata": None,
        }
    except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError) as exc:
        return varsayilan | {"hata": str(exc)}


# testler icin yardimci
def _tum_kurallar() -> list[OnbellekKurali]:
    return list(_ONBELLEK_KURALLARI)