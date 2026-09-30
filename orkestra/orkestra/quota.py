"""Kota takibi: cor `proxy.log`'u artımlı okunur, `quota_snapshots`'a yazılır.

Kaynak biçimi bu ortamdaki GERÇEK `proxy.log`'dan alınmıştır:

    [2026-09-30T06:15:25.675Z] openrouter -> stealth/space-bunny-alpha (stream)

Zaman damgası ISO8601, **UTC**, milisaniye çözünürlüklü ve `Z` sonludur; bu yüzden
gün sınırı doğrudan UTC'de (yerel saat DEĞİL) hesaplanır. Aynı biçimde görülen
diğer satırlar (`proxy dinliyor`, `SIGTERM alindi`, hata satırları) İSTEK sayılmaz.

Ayrıştırıcı YALNIZCA gördüğü bu biçimi tanır. Tanımadığı satırı ATLAR ve
sayar (`Sonuc.taninmayan`) — asla uydurma sayı üretmez. Log'da maliyet bulunmadığı
için `maliyet` her zaman 0'dır; raporda bu açıkça belirtilir.

Artımlı okuma: son okunan bayt konumu `quota_offsets` tablosunda saklanır. Dosya
küçüldüyse (döndürme/kesme) başa dönülür. Dosyanın sonunda yarım kalan satır
BİR DAHAHA okunmaz — konum tam satır sonunda durur.
"""

from __future__ import annotations

import os
import re
import sqlite3
import tomllib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

# -- biçim (yalnızca gerçek logda görülenler) -----------------------------

#: `[2026-09-30T06:15:25.675Z] openrouter -> <model>` isteğin kendisi.
ISTEK_DESENI = re.compile(
    r"^\[(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)\]\s+"
    r"openrouter\s*->\s*(?P<model>\S+)"
    r"(?:\s+\(stream\))?\s*$"
)

VARSAYILAN_LOG_YOLU = Path("/root/.claude-openrouter/proxy.log")
GUN_SAYISI = 14
USTEL_KAYIT = 1000  # tek turda işlenecek en fazla satır (bellek sınırı)

# Ekosistemin bilinen kuralı: paylaşımlı ücretsiz model, hesap geneli günlük kota.
VARSAYILAN_LIMITLER: dict[str, int] = {
    "nvidia/nemotron-3-ultra-550b-a55b:free": 50,
}

KOTA_TOML = Path.home() / ".orkestra" / "kota.toml"


# -- limitler ---------------------------------------------------------------

@dataclass(frozen=True)
class Limitler:
    """Model → günlük limit. Limiti olmayan model `limitsiz` sayılır."""

    degerler: dict[str, int] = field(default_factory=dict)
    kaynak: str = "varsayilan"  # "varsayilan" | "kota.toml"

    def limit(self, model: str) -> int | None:
        return self.degerler.get(model)


def limitleri_yukle(yol: Path | str | None = None) -> Limitler:
    """`~/.orkestra/kota.toml` → `[limitler]` sözlüğü.

    Dosya yoksa/bozuksa varsayılana düşer (hata fırlatmaz; panel çökmez).
    """
    yol = Path(yol).expanduser() if yol is not None else KOTA_TOML
    try:
        ham = yol.read_bytes()
        veri = tomllib.loads(ham.decode("utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return Limitler(dict(VARSAYILAN_LIMITLER), "varsayilan")
    bolum = veri.get("limitler")
    if not isinstance(bolum, dict):
        return Limitler(dict(VARSAYILAN_LIMITLER), "varsayilan")
    degerler: dict[str, int] = {}
    for model, ham_limit in bolum.items():
        # Bozuk değer (metin, negatif) o modeli düşürür, diğerleri etkilenmez.
        if isinstance(ham_limit, bool) or not isinstance(ham_limit, int):
            continue
        if ham_limit < 0:
            continue
        degerler[str(model)] = ham_limit
    return Limitler(degerler or dict(VARSAYILAN_LIMITLER), "kota.toml")


# -- durum ------------------------------------------------------------------

#: Yüzde eşiği → durum adı. Rozet metin de yazar (renge tek başına dayanmaz).
DURUM_ESIKLERI = ((80, "uyari"), (100, "asildi"))

#: Kota durumu → rozet METNİ. Renk tek başına anlam taşımaz (renk körlüğü).
DURUM_ETIKETLERI = {
    "normal": "sınır altında",
    "uyari": "uyarı",
    "asildi": "aşıldı",
    "limitsiz": "limitsiz",
}


def durum_bul(istek: int, limit: int | None) -> str:
    """`limitsiz` | `normal` | `uyari` (>=%80) | `asildi` (>=%100).

    Eşikler YÜKSEKTEN düşüğe sırayla denenir: %100 `asildi`'yi verir, %80
    `uyari`'yi. (Düşükten yükseğe denenseydi %100 de `uyari` kalırdı.)
    """
    if not limit:
        return "limitsiz"
    yuzde = istek * 100 / limit
    # Yüksek eşik önce: %100 -> asildi, %80 -> uyari.
    for esik, ad in sorted(DURUM_ESIKLERI, reverse=True):
        if yuzde >= esik:
            return ad
    return "normal"


def yuzde(istek: int, limit: int | None) -> float | None:
    return None if not limit else istek * 100 / limit


# -- ayrıştırma -------------------------------------------------------------


@dataclass
class GunSayaci:
    gun: str
    istek: int = 0
    hata: int = 0
    maliyet: float = 0.0
    modeller: dict[str, int] = field(default_factory=dict)

    def ekle(self, model: str, hata_mi: bool) -> None:
        self.istek += 1
        if hata_mi:
            self.hata += 1
        self.modeller[model] = self.modeller.get(model, 0) + 1


@dataclass
class Sonuc:
    """Bir `kota-guncelle` turunun sonucu."""

    yeni_satir: int = 0
    taninmayan: int = 0
    gunler: dict[str, GunSayaci] = field(default_factory=dict)
    kaynak: str = ""

    def gun(self, anahtar: str) -> GunSayaci:
        return self.gunler.setdefault(anahtar, GunSayaci(gun=anahtar))


def gun_anahtari(zaman: datetime) -> str:
    """Zaman damgasından UTC gün anahtarı (`YYYY-MM-DD`)."""
    return zaman.astimezone(timezone.utc).date().isoformat()


def son_gunler(bugun: datetime | None = None, adet: int = GUN_SAYISI) -> list[str]:
    """Bugünden geriye doğru `adet` UTC gün anahtarı (graf ekseni)."""
    bugun = bugun or datetime.now(timezone.utc)
    return [
        (bugun - timedelta(days=geri)).date().isoformat()
        for geri in range(adet - 1, -1, -1)
    ]


def satir_ayir(satir: str) -> tuple[datetime, str, bool] | None:
    """`(zaman, model, hata_mi)` — tanınmayan satır için `None`.

    `hata_mi` yalnızca "(stream)" dışı ek varsa anlamlıdır; cor'un logunda hata
    sayacı YOKTUR, bu yüzden hata sayımı hep 0'dır (raporda belirtilir).
    """
    eslesme = ISTEK_DESENI.match(satir.strip())
    if eslesme is None:
        return None
    zaman = datetime.fromisoformat(eslesme.group("ts").replace("Z", "+00:00"))
    return zaman, eslesme.group("model"), False


# -- artımlı okuma ----------------------------------------------------------


def _konum_al(baglanti: sqlite3.Connection, kaynak: str) -> tuple[int, int]:
    satir = baglanti.execute(
        "SELECT konum, boyut FROM quota_offsets WHERE kaynak = ?", (kaynak,)
    ).fetchone()
    return (satir["konum"], satir["boyut"]) if satir else (0, 0)


def _konum_yaz(
    baglanti: sqlite3.Connection, kaynak: str, konum: int, boyut: int
) -> None:
    baglanti.execute(
        "INSERT INTO quota_offsets (kaynak, konum, boyut) VALUES (?, ?, ?) "
        "ON CONFLICT(kaynak) DO UPDATE SET konum = excluded.konum, "
        "boyut = excluded.boyut",
        (kaynak, konum, boyut),
    )


def tamamlanmamis_satir(metin: str) -> bool:
    """Metin satır sonu olmadan mı bitiyor (yarım satır)?"""
    return bool(metin) and not metin.endswith("\n")


def guncelle(
    baglanti: sqlite3.Connection,
    log_yolu: Path | str | None = None,
    ustel_kayit: int = USTEL_KAYIT,
) -> Sonuc:
    """Log'u son konumdan okur, `quota_offsets` ilerletir, sayacı DB'ye yazar."""
    yol = (
        Path(log_yolu).expanduser()
        if log_yolu is not None
        else Path(os.environ.get("COR_LOG") or VARSAYILAN_LOG_YOLU).expanduser()
    )
    kaynak = str(yol)
    sonuc = Sonuc(kaynak=kaynak)
    try:
        boyut = yol.stat().st_size
    except OSError:
        # Log yoksa/erişilemiyorsa: konuma DOKUNMA, sıfır döner. Panel boş görünür.
        return sonuc

    konum, onceki_boyut = _konum_al(baglanti, kaynak)
    if boyut < onceki_boyut or boyut < konum:
        # Dosya küçüldü: döndürülmüş/kesilmiş. Başa dön.
        konum = 0

    try:
        with yol.open("rb") as akis:
            akis.seek(konum)
            ham = akis.read(ustel_kayit * 512)
    except OSError:
        return sonuc

    # Yalnız TAM satırlar işlenir; yarım satır sonraki tura kalır (konum
    # tam satır sonunda durur, dosya tekrar aynı bayttan okunur).
    son_kesme = ham.rfind(b"\n")
    if son_kesme == -1:
        # Hiç tam satır yok (ya da tek satır daha yazılmadı): konum İLERLETME.
        return sonuc
    parca = ham[: son_kesme + 1]
    yeni_konum = konum + len(parca)

    metin = parca.decode("utf-8", errors="replace")
    sayaclar: dict[str, GunSayaci] = {}
    for satir in metin.splitlines():
        cozulmus = satir_ayir(satir)
        if cozulmus is None:
            sonuc.taninmayan += 1
            continue
        zaman, model, hata_mi = cozulmus
        anahtar = gun_anahtari(zaman)
        sayac = sayaclar.setdefault(anahtar, GunSayaci(gun=anahtar))
        sayac.ekle(model, hata_mi)
        sonuc.yeni_satir += 1

    _konum_yaz(baglanti, kaynak, yeni_konum, boyut)

    for sayac in sayaclar.values():
        _kaydet(baglanti, sayac)
    sonuc.gunler = sayaclar
    return sonuc


def _kaydet(baglanti: sqlite3.Connection, sayac: GunSayaci) -> None:
    """Sayacı `quota_snapshots`'a toplar (VARSAYILAN 0 olan hata dahil değil).

    Şema (Dalga A): `quota_snapshots(model, gun, istek, maliyet)`. Günlük istek
    sayısı birikimli olduğu için mevcut değere ÜSTÜNE yazılır; aynı gün ikinci
    turda aynı satırlar SAYILMAZ (konum ilerletildiği için), ama yarım kalan
    turun sayacı da kaydedilmiş olur.
    """
    for model, adet in sayac.modeller.items():
        satir = baglanti.execute(
            "SELECT istek, maliyet FROM quota_snapshots WHERE model = ? AND gun = ?",
            (model, sayac.gun),
        ).fetchone()
        onceki = satir["istek"] if satir else 0
        onceki_maliyet = satir["maliyet"] if satir else 0.0
        baglanti.execute(
            "INSERT INTO quota_snapshots (model, gun, istek, maliyet) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(model, gun) DO UPDATE SET istek = excluded.istek, "
            "maliyet = excluded.maliyet",
            (model, sayac.gun, onceki + adet, onceki_maliyet + sayac.maliyet),
        )


# -- okuma ------------------------------------------------------------------


@dataclass
class ModelKotasi:
    model: str
    istek: int
    limit: int | None
    durum: str
    yuzde: float | None
    seri: list[dict]  # son 14 gün: {"gun", "istek"}

    @property
    def etiket(self) -> str:
        """Model adını kısaltır (graf altında okunur kalsın)."""
        return self.model.split("/")[-1]

    @property
    def durum_etiket(self) -> str:
        return DURUM_ETIKETLERI[self.durum]


@dataclass
class KotaGorunumu:
    gun: str
    modeller: list[ModelKotasi]
    limit_kaynagi: str
    toplam_istek: int
    uyari_sayisi: int
    #: Hiç `quota_snapshots` satırı yoksa False: "0 istek" ile "hiç okunmadı"
    #: birbirine karışmasın diye ayrı durum.
    veri_var: bool = True


def kota_gorunumu(
    baglanti: sqlite3.Connection,
    limitler: Limitler | None = None,
    adet: int = GUN_SAYISI,
    bugun: datetime | None = None,
) -> KotaGorunumu:
    """Model başına bugünkü istek/limit/durum + son N günün serisi."""
    limitler = limitler if limitler is not None else limitleri_yukle()
    bugun = bugun or datetime.now(timezone.utc)
    anahtarlar = son_gunler(bugun, adet)
    gun = anahtarlar[-1]

    satirlar = baglanti.execute(
        "SELECT model, gun, istek FROM quota_snapshots ORDER BY model, gun"
    ).fetchall()
    seriler: dict[str, dict[str, int]] = {}
    bugunkuler: dict[str, int] = {}
    for satir in satirlar:
        model = satir["model"]
        seriler.setdefault(model, {})[satir["gun"]] = satir["istek"]
        if satir["gun"] == gun:
            bugunkuler[model] = satir["istek"]

    # Sınırda olmayan modeller de listede görünsün (kota.toml'da tanımlıysa).
    for model in limitler.degerler:
        seriler.setdefault(model, {})

    veri_var = bool(satirlar)

    modeller = []
    for model in sorted(seriler):
        istek = bugunkuler.get(model, 0)
        limit = limitler.limit(model)
        modeller.append(
            ModelKotasi(
                model=model,
                istek=istek,
                limit=limit,
                durum=durum_bul(istek, limit),
                yuzde=yuzde(istek, limit),
                seri=[{"gun": anahtar, "istek": seriler[model].get(anahtar, 0)} for anahtar in anahtarlar],
            )
        )
    return KotaGorunumu(
        gun=gun,
        modeller=modeller,
        limit_kaynagi=limitler.kaynak,
        toplam_istek=sum(m.istek for m in modeller),
        uyari_sayisi=sum(1 for m in modeller if m.durum in ("uyari", "asildi")),
        veri_var=veri_var,
    )
