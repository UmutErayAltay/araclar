"""Portfolyo yapılandırma dosyasını okur ve doğrular.

Bu modül, JSON biçimindeki yapılandırma dosyasını okur, tüm kuralları
uygular ve güçlü tipli veri sınıflarına dönüştürür. Yeni alanların hepsi
opsiyoneldir; alan yoksa `ayar.py` içindeki varsayılan geçerlidir.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from ._url import HTTPS_URL


class AyarHatasi(Exception):
    """Yapılandırma okuma/doğrulama hatası."""


VARSAYILAN_KATEGORI = "Diğer"
VERI_KAYNAKLARI = ("yok", "klon", "api")
SIRALAMALAR = ("manuel", "aktivite")
DILLER = ("tr", "en")
LED_TURLERI = ("eylem", "acik", "kapali")


@dataclass(frozen=True)
class Led:
    """Aksiyon düğmesi (yazı tipi: eylem | açık | kapalı)."""

    metin: str
    tur: str = "acik"


@dataclass(frozen=True)
class Sahip:
    """Portfolyo sahibi bilgileri."""

    ad: str
    unvan: str
    github: str
    hakkinda: str
    site_url: str = ""
    eposta: str = ""
    linkedin: str = ""
    konum: str = ""
    cv_tr: str = ""
    cv_en: str = ""
    ledler: tuple[Led, ...] = ()


@dataclass(frozen=True)
class Deneyim:
    """İş deneyimi girdisi."""

    rol: str
    kurum: str
    tarih: str = ""
    aciklama: str = ""


@dataclass(frozen=True)
class Egitim:
    """Eğitim girdisi."""

    derece: str
    okul: str
    tarih: str = ""
    ek: str = ""


@dataclass(frozen=True)
class YetenekGrubu:
    """Yetenek grubu: `grup` başlığı + en çok 12 `ogeler`."""

    grup: str
    ogeler: tuple[str, ...] = ()


@dataclass(frozen=True)
class Repo:
    """Herkese açık repo bilgisi."""

    ad: str
    aciklama: str
    url: str
    etiketler: tuple[str, ...]
    klon: str | None
    readme: bool
    kategori: str = VARSAYILAN_KATEGORI
    veri: str = "yok"  # "yok" | "klon" | "api"
    baglantilar: tuple[tuple[str, str], ...] = ()  # (ad, https url): demo/doküman düğmeleri
    one_cikan: bool = False
    led: Led | None = None  # kart düğmesi (sahip.ledler ile aynı kurallar)


@dataclass(frozen=True)
class Ayar:
    """Tam yapılandırma."""

    sahip: Sahip
    repolar: tuple[Repo, ...]
    kategoriler: tuple[str, ...] = ()
    siralama: str = "manuel"  # "manuel" | "aktivite"
    dil: str = "tr"
    dil_baglantisi: str = ""
    deneyim: tuple[Deneyim, ...] = ()
    egitim: tuple[Egitim, ...] = ()
    yetenekler: tuple[YetenekGrubu, ...] = ()


# --- Sabitler ve yardımcı fonksiyonlar ---

_GITHUB_KULLANICI_DESENI = re.compile(r"^[A-Za-z0-9-]{1,39}$")
_REPO_AD_DESENI = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
_ETIKET_DESENI = re.compile(r"^.{1,24}$")
_KONTROL_KARAKTER_DESENI = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_MAKS_REPO_SAYISI = 24
_MAKS_ETIKET_SAYISI = 8
_MAKS_KATEGORI_SAYISI = 8
_MAKS_BAGLANTI_SAYISI = 3
_MAKS_BAGLANTI_AD = 20
_MAKS_BAGLANTI_URL = 300
_MAKS_KATEGORI_UZUNLUK = 40
_SITE_URL_DESENI = re.compile(r"^https://[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?(?:/[A-Za-z0-9._~/-]{0,100})?$")
_EPOSTA_DESENI = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_LINKEDIN_DESENI = re.compile(r"^https://(?:www\.)?linkedin\.com(?:/[^?#\s]*)?(?:\?[^\s#]*)?(?:#\S*)?$")
# KÖK-göreli yollar: `..` ve `//` yasak (dizin dışına çıkış / protokol-göreli kaçış).
_KOK_YOL_DESENI = re.compile(r"^/[A-Za-z0-9_/-]*$")
_KOK_PDF_DESENI = re.compile(r"^/[A-Za-z0-9._/-]+\.pdf$")

_MAKS_HAKKINDA = 1200
_MAKS_EPOSTA = 100
_MAKS_KONUM = 60
_MAKS_DIL_BAGLANTISI = 100
_MAKS_CV_YOL = 120
_MAKS_DENEYIM_SAYISI = 8
_MAKS_EGITIM_SAYISI = 4
_MAKS_YETENEK_GRUBU = 8
_MAKS_YETENEK_OGESI = 12
_MAKS_YETENEK_UZUNLUK = 40
_MAKS_GRUP_UZUNLUK = 40
_MAKS_LED_SAYISI = 4
_MAKS_LED_METIN = 30


def _kontrol_karakteri_var_mi(metin: str) -> bool:
    """Metinde kontrol karakteri (yeni satır hariç) var mı?"""
    return bool(_KONTROL_KARAKTER_DESENI.search(metin))


def _kok_yol_dogrula(deger: object, alan_yolu: str, desen: re.Pattern[str], maks: int, zorunlu: bool) -> str:
    """KÖK-göreli yol: boş olabilir (zorunlu değilse), desen + uzunluk + `..`/`//` reddi."""
    if not isinstance(deger, str):
        raise AyarHatasi(f"{alan_yolu}: string bekleniyor")
    if not deger:
        if zorunlu:
            raise AyarHatasi(f"{alan_yolu}: boş olamaz")
        return ""
    if len(deger) > maks:
        raise AyarHatasi(f"{alan_yolu}: en fazla {maks} karakter ({len(deger)} verildi)")
    if ".." in deger or "//" in deger or not desen.fullmatch(deger):
        raise AyarHatasi(f"{alan_yolu}: kök-göreli yol olmalı (`..` ve `//` kullanılamaz)")
    return deger


def _metin_dogrula(deger: object, alan_yolu: str, maks: int, bos_olamaz: bool = False) -> str:
    """Serbest metin: string, uzunluk, boşluğa bağlı kontrol karakteri yok."""
    if not isinstance(deger, str):
        raise AyarHatasi(f"{alan_yolu}: string bekleniyor")
    if not deger:
        if bos_olamaz:
            raise AyarHatasi(f"{alan_yolu}: boş olamaz")
        return ""
    if len(deger) > maks:
        raise AyarHatasi(f"{alan_yolu}: en fazla {maks} karakter ({len(deger)} verildi)")
    if _kontrol_karakteri_var_mi(deger):
        raise AyarHatasi(f"{alan_yolu}: kontrol karakteri içeremez")
    return deger


def _liste_dogrula(liste: object, alan_yolu: str) -> list:
    if not isinstance(liste, list):
        raise AyarHatasi(f"{alan_yolu}: liste bekleniyor")
    return liste


def _sahip_dogrula(obj: dict, alan_yolu: str) -> Sahip:
    """Sahip nesnesini doğrular ve oluşturur."""
    if not isinstance(obj, dict):
        raise AyarHatasi(f"{alan_yolu}: nesne bekleniyor")

    # Bilinmeyen alan kontrolü
    taninan_alanlar = {"ad", "unvan", "github", "hakkinda", "site_url", "eposta", "linkedin",
                       "konum", "cv_tr", "cv_en", "ledler"}
    for anahtar in obj:
        if anahtar not in taninan_alanlar:
            raise AyarHatasi(f"{alan_yolu}.{anahtar}: tanınmayan alan")

    # ad: zorunlu, 1-80 karakter, kontrol karakteri yok
    ad = obj.get("ad")
    if not isinstance(ad, str):
        raise AyarHatasi(f"{alan_yolu}.ad: string bekleniyor")
    if not ad:
        raise AyarHatasi(f"{alan_yolu}.ad: boş olamaz")
    if len(ad) > 80:
        raise AyarHatasi(f"{alan_yolu}.ad: en fazla 80 karakter ({len(ad)} verildi)")
    if _kontrol_karakteri_var_mi(ad):
        raise AyarHatasi(f"{alan_yolu}.ad: kontrol karakteri içeremez")

    # unvan: opsiyonel, ≤80, kontrol karakteri yok
    unvan = obj.get("unvan", "")
    if not isinstance(unvan, str):
        raise AyarHatasi(f"{alan_yolu}.unvan: string bekleniyor")
    if len(unvan) > 80:
        raise AyarHatasi(f"{alan_yolu}.unvan: en fazla 80 karakter ({len(unvan)} verildi)")
    if _kontrol_karakteri_var_mi(unvan):
        raise AyarHatasi(f"{alan_yolu}.unvan: kontrol karakteri içeremez")

    # github: zorunlu, desen, kontrol karakteri yok
    github = obj.get("github")
    if not isinstance(github, str):
        raise AyarHatasi(f"{alan_yolu}.github: string bekleniyor")
    if not github:
        raise AyarHatasi(f"{alan_yolu}.github: boş olamaz")
    if not _GITHUB_KULLANICI_DESENI.fullmatch(github):
        raise AyarHatasi(f"{alan_yolu}.github: geçersiz GitHub kullanıcı adı")
    if _kontrol_karakteri_var_mi(github):
        raise AyarHatasi(f"{alan_yolu}.github: kontrol karakteri içeremez")

    # hakkinda: opsiyonel, ≤1200, kontrol karakteri yok (yeni satır serbest)
    hakkinda = obj.get("hakkinda", "")
    if not isinstance(hakkinda, str):
        raise AyarHatasi(f"{alan_yolu}.hakkinda: string bekleniyor")
    if len(hakkinda) > _MAKS_HAKKINDA:
        raise AyarHatasi(f"{alan_yolu}.hakkinda: en fazla {_MAKS_HAKKINDA} karakter ({len(hakkinda)} verildi)")
    # yeni satır hariç kontrol karakteri kontrolü
    for ch in hakkinda:
        if ch in ("\n", "\r"):
            continue
        if ord(ch) < 32 or ch == "\x7f":
            raise AyarHatasi(f"{alan_yolu}.hakkinda: kontrol karakteri içeremez")

    # site_url: opsiyonel; yalnız https, paylaşım meta etiketlerinde (og:url) kullanılır
    site_url = obj.get("site_url", "")
    if not isinstance(site_url, str):
        raise AyarHatasi(f"{alan_yolu}.site_url: string bekleniyor")
    if site_url and not _SITE_URL_DESENI.fullmatch(site_url):
        raise AyarHatasi(f"{alan_yolu}.site_url: yalnız https:// adresi olabilir")

    # eposta: opsiyonel, basit e-posta deseni
    eposta = obj.get("eposta", "")
    if not isinstance(eposta, str):
        raise AyarHatasi(f"{alan_yolu}.eposta: string bekleniyor")
    if len(eposta) > _MAKS_EPOSTA:
        raise AyarHatasi(f"{alan_yolu}.eposta: en fazla {_MAKS_EPOSTA} karakter ({len(eposta)} verildi)")
    if eposta and not _EPOSTA_DESENI.fullmatch(eposta):
        raise AyarHatasi(f"{alan_yolu}.eposta: geçersiz e-posta adresi")

    # linkedin: opsiyonel, https linkedin.com adresi
    linkedin = obj.get("linkedin", "")
    if not isinstance(linkedin, str):
        raise AyarHatasi(f"{alan_yolu}.linkedin: string bekleniyor")
    if linkedin and (
        len(linkedin) > _MAKS_BAGLANTI_URL
        or not HTTPS_URL.fullmatch(linkedin)
        or not _LINKEDIN_DESENI.fullmatch(linkedin)
    ):
        raise AyarHatasi(f"{alan_yolu}.linkedin: yalnız https://www.linkedin.com adresi olabilir")

    # konum: opsiyonel, ≤60, kontrol karakteri yok
    konum = _metin_dogrula(obj.get("konum", ""), f"{alan_yolu}.konum", _MAKS_KONUM)

    # cv_tr / cv_en: opsiyonel KÖK-göreli PDF yolları
    cv_tr = _kok_yol_dogrula(obj.get("cv_tr", ""), f"{alan_yolu}.cv_tr", _KOK_PDF_DESENI, _MAKS_CV_YOL, False)
    cv_en = _kok_yol_dogrula(obj.get("cv_en", ""), f"{alan_yolu}.cv_en", _KOK_PDF_DESENI, _MAKS_CV_YOL, False)

    # ledler: opsiyonel liste, en fazla 4
    ledler = _ledler_dogrula(obj.get("ledler", []), f"{alan_yolu}.ledler")

    return Sahip(
        ad=ad, unvan=unvan, github=github, hakkinda=hakkinda, site_url=site_url,
        eposta=eposta, linkedin=linkedin, konum=konum, cv_tr=cv_tr, cv_en=cv_en, ledler=ledler,
    )


def _led_dogrula(obj: object, alan_yolu: str) -> Led:
    """Tek aksiyon düğmesi: `metin` (1-30) + `tur` (eylem|acik|kapali)."""
    if not isinstance(obj, dict):
        raise AyarHatasi(f"{alan_yolu}: nesne bekleniyor")
    for anahtar in obj:
        if anahtar not in {"metin", "tur"}:
            raise AyarHatasi(f"{alan_yolu}.{anahtar}: tanınmayan alan")
    metin = _metin_dogrula(obj.get("metin"), f"{alan_yolu}.metin", _MAKS_LED_METIN, bos_olamaz=True)
    tur = obj.get("tur", "acik")
    if not isinstance(tur, str) or tur not in LED_TURLERI:
        raise AyarHatasi(f"{alan_yolu}.tur: {', '.join(LED_TURLERI)} değerlerinden biri olmalı")
    return Led(metin=metin, tur=tur)


def _ledler_dogrula(liste: object, alan_yolu: str) -> tuple[Led, ...]:
    """Aksiyon düğmeleri: en çok 4, `metin` (1-30) + `tur` (eylem|acik|kapali)."""
    sonuc = [_led_dogrula(o, f"{alan_yolu}[{i}]") for i, o in enumerate(_liste_dogrula(liste, alan_yolu))]
    if len(sonuc) > _MAKS_LED_SAYISI:
        raise AyarHatasi(f"{alan_yolu}: en fazla {_MAKS_LED_SAYISI} led ({len(sonuc)} verildi)")
    return tuple(sonuc)


def _repo_dogrula(
    obj: dict,
    alan_yolu: str,
    github_kullanici: str,
    gorusulen_adlar: set[str],
    kategoriler: tuple[str, ...] = (),
) -> Repo:
    """Repo nesnesini doğrular ve oluşturur."""
    if not isinstance(obj, dict):
        raise AyarHatasi(f"{alan_yolu}: nesne bekleniyor")

    # Bilinmeyen alan kontrolü
    taninan_alanlar = {"ad", "herkese_acik", "aciklama", "etiketler", "klon", "readme", "kategori", "veri", "baglantilar", "one_cikan", "led"}
    for anahtar in obj:
        if anahtar not in taninan_alanlar:
            raise AyarHatasi(f"{alan_yolu}.{anahtar}: tanınmayan alan")

    # ad: zorunlu, desen, tekrarsız
    ad = obj.get("ad")
    if not isinstance(ad, str):
        raise AyarHatasi(f"{alan_yolu}.ad: string bekleniyor")
    if not ad:
        raise AyarHatasi(f"{alan_yolu}.ad: boş olamaz")
    if not _REPO_AD_DESENI.fullmatch(ad):
        raise AyarHatasi(f"{alan_yolu}.ad: geçersiz repo adı ({ad!r})")
    if ad in gorusulen_adlar:
        raise AyarHatasi(f"{alan_yolu}.ad: tekrar eden repo adı ({ad!r})")
    gorusulen_adlar.add(ad)

    # herkese_acik: TAM OLARAK true (boolean) olmalı
    herkese_acik = obj.get("herkese_acik")
    if herkese_acik is not True:
        raise AyarHatasi(
            f"{alan_yolu}.herkese_acik: tam olarak true (boolean) olmalı — "
            f"yoksa/false ise özel repo yayınlanmaz"
        )

    # aciklama: opsiyonel, ≤300, kontrol karakteri yok
    aciklama = obj.get("aciklama", "")
    if not isinstance(aciklama, str):
        raise AyarHatasi(f"{alan_yolu}.aciklama: string bekleniyor")
    if len(aciklama) > 300:
        raise AyarHatasi(f"{alan_yolu}.aciklama: en fazla 300 karakter ({len(aciklama)} verildi)")
    if _kontrol_karakteri_var_mi(aciklama):
        raise AyarHatasi(f"{alan_yolu}.aciklama: kontrol karakteri içeremez")

    # etiketler: opsiyonel liste, ≤8 adet, her biri 1-24 karakter
    etiketler_list = obj.get("etiketler", [])
    if not isinstance(etiketler_list, list):
        raise AyarHatasi(f"{alan_yolu}.etiketler: liste bekleniyor")
    if len(etiketler_list) > _MAKS_ETIKET_SAYISI:
        raise AyarHatasi(f"{alan_yolu}.etiketler: en fazla {_MAKS_ETIKET_SAYISI} etiket ({len(etiketler_list)} verildi)")
    etiketler: list[str] = []
    for i, etiket in enumerate(etiketler_list):
        if not isinstance(etiket, str):
            raise AyarHatasi(f"{alan_yolu}.etiketler[{i}]: string bekleniyor")
        if not _ETIKET_DESENI.fullmatch(etiket):
            raise AyarHatasi(f"{alan_yolu}.etiketler[{i}]: 1-24 karakter aralığında olmalı")
        if _kontrol_karakteri_var_mi(etiket):
            raise AyarHatasi(f"{alan_yolu}.etiketler[{i}]: kontrol karakteri içeremez")
        etiketler.append(etiket)

    # klon: opsiyonel string
    klon = obj.get("klon")
    if klon is not None and not isinstance(klon, str):
        raise AyarHatasi(f"{alan_yolu}.klon: string veya null bekleniyor")

    # readme: opsiyonel bool, varsayılan False
    readme = obj.get("readme", False)
    if not isinstance(readme, bool):
        raise AyarHatasi(f"{alan_yolu}.readme: boolean bekleniyor")

    # kategori: opsiyonel; verilirse üst düzey `kategoriler` listesinden biri olmalı
    kategori = obj.get("kategori", VARSAYILAN_KATEGORI)
    if not isinstance(kategori, str):
        raise AyarHatasi(f"{alan_yolu}.kategori: string bekleniyor")
    if "kategori" in obj and kategori not in kategoriler:
        raise AyarHatasi(f"{alan_yolu}.kategori: üst düzey `kategoriler` listesinde olmalı")

    # veri: "yok" | "klon" | "api"; verilmezse klon varsa "klon", yoksa "yok"
    veri = obj.get("veri", "klon" if klon else "yok")
    if not isinstance(veri, str) or veri not in VERI_KAYNAKLARI:
        raise AyarHatasi(f"{alan_yolu}.veri: {', '.join(VERI_KAYNAKLARI)} değerlerinden biri olmalı")
    if veri == "klon" and not klon:
        raise AyarHatasi(f"{alan_yolu}.veri: \"klon\" için `klon` yolu gerekli")

    baglantilar = _baglantilar_dogrula(obj.get("baglantilar", []), f"{alan_yolu}.baglantilar")

    # one_cikan: opsiyonel bool, varsayılan False
    one_cikan = obj.get("one_cikan", False)
    if not isinstance(one_cikan, bool):
        raise AyarHatasi(f"{alan_yolu}.one_cikan: boolean bekleniyor")

    # led: opsiyonel tek düğme (null/yoksa None)
    led_veri = obj.get("led")
    led = None if led_veri is None else _led_dogrula(led_veri, f"{alan_yolu}.led")

    # url: KULLANICIDAN ALINMAZ, türetilir
    url = f"https://github.com/{github_kullanici}/{ad}"

    return Repo(
        ad=ad,
        aciklama=aciklama,
        url=url,
        etiketler=tuple(etiketler),
        klon=klon,
        readme=readme,
        kategori=kategori,
        veri=veri,
        baglantilar=baglantilar,
        one_cikan=one_cikan,
        led=led,
    )


def _baglantilar_dogrula(liste: object, alan_yolu: str) -> tuple[tuple[str, str], ...]:
    """Kart bağlantıları: en çok 3, `ad` + yalnız `https://` `url`."""
    if not isinstance(liste, list):
        raise AyarHatasi(f"{alan_yolu}: liste bekleniyor")
    if len(liste) > _MAKS_BAGLANTI_SAYISI:
        raise AyarHatasi(f"{alan_yolu}: en fazla {_MAKS_BAGLANTI_SAYISI} bağlantı ({len(liste)} verildi)")
    sonuc: list[tuple[str, str]] = []
    for i, b in enumerate(liste):
        yol = f"{alan_yolu}[{i}]"
        if not isinstance(b, dict):
            raise AyarHatasi(f"{yol}: nesne bekleniyor")
        for anahtar in b:
            if anahtar not in {"ad", "url"}:
                raise AyarHatasi(f"{yol}.{anahtar}: tanınmayan alan")
        ad, url = b.get("ad"), b.get("url")
        if not isinstance(ad, str) or not 1 <= len(ad) <= _MAKS_BAGLANTI_AD or _kontrol_karakteri_var_mi(ad):
            raise AyarHatasi(f"{yol}.ad: 1-{_MAKS_BAGLANTI_AD} karakter, kontrol karakteri yok")
        if not isinstance(url, str) or len(url) > _MAKS_BAGLANTI_URL or not HTTPS_URL.fullmatch(url):
            raise AyarHatasi(f"{yol}.url: yalnız https:// adresi olabilir")
        sonuc.append((ad, url))
    return tuple(sonuc)


def _kategoriler_dogrula(liste: object) -> tuple[str, ...]:
    """Üst düzey `kategoriler` listesini doğrular (görünme sırası = liste sırası)."""
    if not isinstance(liste, list):
        raise AyarHatasi("kategoriler: liste bekleniyor")
    if len(liste) > _MAKS_KATEGORI_SAYISI:
        raise AyarHatasi(f"kategoriler: en fazla {_MAKS_KATEGORI_SAYISI} kategori ({len(liste)} verildi)")
    sonuc: list[str] = []
    for i, ad in enumerate(liste):
        if not isinstance(ad, str) or not ad.strip():
            raise AyarHatasi(f"kategoriler[{i}]: boş olmayan string bekleniyor")
        if len(ad) > _MAKS_KATEGORI_UZUNLUK:
            raise AyarHatasi(f"kategoriler[{i}]: en fazla {_MAKS_KATEGORI_UZUNLUK} karakter")
        if _kontrol_karakteri_var_mi(ad):
            raise AyarHatasi(f"kategoriler[{i}]: kontrol karakteri içeremez")
        if ad in sonuc:
            raise AyarHatasi(f"kategoriler[{i}]: tekrar eden kategori")
        sonuc.append(ad)
    return tuple(sonuc)


def _nesne_listesi_dogrula(
    liste: object, alan_yolu: str, taninan: tuple[str, ...], zorunlu: tuple[str, ...]
) -> list[dict]:
    """Kök seviyesindeki nesne listesi: liste + tanınmayan anahtar + zorunlu string alan (uzunluk alan bazında)."""
    sonuc: list[dict] = []
    for i, o in enumerate(_liste_dogrula(liste, alan_yolu)):
        yol = f"{alan_yolu}[{i}]"
        if not isinstance(o, dict):
            raise AyarHatasi(f"{yol}: nesne bekleniyor")
        for anahtar in o:
            if anahtar not in taninan:
                raise AyarHatasi(f"{yol}.{anahtar}: tanınmayan alan")
        for ad in zorunlu:
            if not isinstance(o.get(ad), str) or not o[ad]:
                raise AyarHatasi(f"{yol}.{ad}: boş string bekleniyor")
        sonuc.append(o)
    return sonuc


def _deneyim_dogrula(liste: object) -> tuple[Deneyim, ...]:
    """İş deneyimi: en fazla 8; rol/kurum zorunlu (≤80), tarih (≤80) ve açıklama (≤600) opsiyonel."""
    objs = _nesne_listesi_dogrula(liste, "deneyim", ("rol", "kurum", "tarih", "aciklama"), ("rol", "kurum"))
    if len(objs) > _MAKS_DENEYIM_SAYISI:
        raise AyarHatasi(f"deneyim: en fazla {_MAKS_DENEYIM_SAYISI} deneyim ({len(objs)} verildi)")
    sonuc = []
    for i, o in enumerate(objs):
        yol = f"deneyim[{i}]"
        rol = _metin_dogrula(o["rol"], f"{yol}.rol", 80)
        kurum = _metin_dogrula(o["kurum"], f"{yol}.kurum", 80)
        tarih = _metin_dogrula(o.get("tarih", ""), f"{yol}.tarih", 80)
        aciklama = _metin_dogrula(o.get("aciklama", ""), f"{yol}.aciklama", 600)
        sonuc.append(Deneyim(rol=rol, kurum=kurum, tarih=tarih, aciklama=aciklama))
    return tuple(sonuc)


def _egitim_dogrula(liste: object) -> tuple[Egitim, ...]:
    """Eğitim: en fazla 4; derece/okul zorunlu (≤100), tarih/ek opsiyonel (≤80)."""
    objs = _nesne_listesi_dogrula(liste, "egitim", ("derece", "okul", "tarih", "ek"), ("derece", "okul"))
    if len(objs) > _MAKS_EGITIM_SAYISI:
        raise AyarHatasi(f"egitim: en fazla {_MAKS_EGITIM_SAYISI} eğitim ({len(objs)} verildi)")
    sonuc = []
    for i, o in enumerate(objs):
        yol = f"egitim[{i}]"
        derece = _metin_dogrula(o["derece"], f"{yol}.derece", 100)
        okul = _metin_dogrula(o["okul"], f"{yol}.okul", 100)
        tarih = _metin_dogrula(o.get("tarih", ""), f"{yol}.tarih", 80)
        ek = _metin_dogrula(o.get("ek", ""), f"{yol}.ek", 80)
        sonuc.append(Egitim(derece=derece, okul=okul, tarih=tarih, ek=ek))
    return tuple(sonuc)


def _yetenekler_dogrula(liste: object) -> tuple[YetenekGrubu, ...]:
    """Yetenekler: en fazla 8 grup; `grup` ≤40, `ogeler` 1-12 öğe (her biri ≤40)."""
    objs = _nesne_listesi_dogrula(liste, "yetenekler", ("grup", "ogeler"), ("grup",))
    if len(objs) > _MAKS_YETENEK_GRUBU:
        raise AyarHatasi(f"yetenekler: en fazla {_MAKS_YETENEK_GRUBU} grup ({len(objs)} verildi)")
    sonuc = []
    for i, o in enumerate(objs):
        yol = f"yetenekler[{i}]"
        grup = _metin_dogrula(o["grup"], f"{yol}.grup", _MAKS_GRUP_UZUNLUK)
        ogeler_list = _liste_dogrula(o.get("ogeler", []), f"{yol}.ogeler")
        if not 1 <= len(ogeler_list) <= _MAKS_YETENEK_OGESI:
            raise AyarHatasi(f"{yol}.ogeler: 1-{_MAKS_YETENEK_OGESI} öğe aralığında olmalı")
        ogeler = [
            _metin_dogrula(oge, f"{yol}.ogeler[{j}]", _MAKS_YETENEK_UZUNLUK, bos_olamaz=True)
            for j, oge in enumerate(ogeler_list)
        ]
        sonuc.append(YetenekGrubu(grup=grup, ogeler=tuple(ogeler)))
    return tuple(sonuc)


def ayar_oku(yol: Path) -> Ayar:
    """Yapılandırma dosyasını okur, doğrular ve Ayar nesnesi döndürür."""
    # Dosya var mı ve okunabilir mi
    if not yol.exists():
        raise AyarHatasi(f"Dosya bulunamadı: {yol}")
    if not yol.is_file():
        raise AyarHatasi(f"Dosya değil: {yol}")

    # JSON oku
    try:
        icerik = yol.read_text(encoding="utf-8")
        veri = json.loads(icerik)
    except json.JSONDecodeError as exc:
        raise AyarHatasi(f"Geçersiz JSON: {exc}") from exc
    except OSError as exc:
        raise AyarHatasi(f"Dosya okunamadı: {exc}") from exc

    # Kök nesne kontrolü
    if not isinstance(veri, dict):
        raise AyarHatasi("Kök nesne bir obje olmalı")

    # Bilinmeyen kök alan kontrolü
    taninan_kok_alanlar = {"sahip", "repolar", "kategoriler", "siralama", "dil", "dil_baglantisi",
                           "deneyim", "egitim", "yetenekler"}
    for anahtar in veri:
        if anahtar not in taninan_kok_alanlar:
            raise AyarHatasi(f"{anahtar}: tanınmayan kök alan")

    # sahip zorunlu
    if "sahip" not in veri:
        raise AyarHatasi("sahip: zorunlu alan eksik")
    sahip = _sahip_dogrula(veri["sahip"], "sahip")

    # repolar zorunlu liste, 1-24 eleman
    repolar_veri = veri.get("repolar")
    if not isinstance(repolar_veri, list):
        raise AyarHatasi("repolar: liste bekleniyor")
    if not repolar_veri:
        raise AyarHatasi("repolar: en az 1 repo olmalı")
    if len(repolar_veri) > _MAKS_REPO_SAYISI:
        raise AyarHatasi(f"repolar: en fazla {_MAKS_REPO_SAYISI} repo ({len(repolar_veri)} verildi)")

    kategoriler = _kategoriler_dogrula(veri.get("kategoriler", []))

    siralama = veri.get("siralama", "manuel")
    if not isinstance(siralama, str) or siralama not in SIRALAMALAR:
        raise AyarHatasi(f"siralama: {', '.join(SIRALAMALAR)} değerlerinden biri olmalı")

    dil = veri.get("dil", "tr")
    if not isinstance(dil, str) or dil not in DILLER:
        raise AyarHatasi(f"dil: {', '.join(DILLER)} değerlerinden biri olmalı")

    dil_baglantisi = _kok_yol_dogrula(veri.get("dil_baglantisi", ""), "dil_baglantisi",
                                     _KOK_YOL_DESENI, _MAKS_DIL_BAGLANTISI, False)

    gorusulen_adlar: set[str] = set()
    repolar: list[Repo] = []
    for i, repo_obj in enumerate(repolar_veri):
        repo = _repo_dogrula(repo_obj, f"repolar[{i}]", sahip.github, gorusulen_adlar, kategoriler)
        repolar.append(repo)

    return Ayar(
        sahip=sahip,
        repolar=tuple(repolar),
        kategoriler=kategoriler,
        siralama=siralama,
        dil=dil,
        dil_baglantisi=dil_baglantisi,
        deneyim=_deneyim_dogrula(veri.get("deneyim", [])),
        egitim=_egitim_dogrula(veri.get("egitim", [])),
        yetenekler=_yetenekler_dogrula(veri.get("yetenekler", [])),
    )