"""BM25 tam-metin arama (Dalga D). Tamamen YEREL: ağa hiç çıkmaz, cor'u çağırmaz.

Mimari:
  * İndeks (`ara_belge`, `ara_terim`, `ara_meta`) `harita indeksle` tarafından
    kurulur. Gövde metni `chunks` tablosundan gelir — yani gizli satırlar
    İNDEKLEME sırasında zaten süzülmüştür ve hiçbir zaman terim olmaz.
  * Alan ağırlıkları BM25F'e benzer şekilde alan tf'si ağırlıkla çarpılıp
    toplanır: başlık ×4, alias ×4, etiket ×3, yol/klasör ×1.5, gövde ×1.
  * Türkçe: NFC → Türkçe küçük harf (`İ`→`i`, `I`→`ı`) → katlama
    (`ı ç ğ ö ş ü` → `i c g o s u`). Sorgu ve belge AYNI işlemden geçer, bu
    yüzden "guvenlik" → "güvenlik" ve "IŞIK"/"ışık"/"isik" aynı terimdir.
  * Kök modu (varsayılan): katlanmış sözcük 5 karakterden uzunsa ilk 5 karakter
    terimdir ("borsanın"/"borsada"/"Borsa" → "borsa"). `--tam` kök kesmeyi
    kapatır; indeks bu durumda tam sözcükleri de tutar.

Ayrıntılı davranış ve gizlilik kararları README'nin "Arama" bölümündedir.
"""

from __future__ import annotations

import math
import re
import sqlite3
import unicodedata
from dataclasses import dataclass, field

from .parse import gizli_satir_mi

# ---------------------------------------------------------------------------
# BM25 parametreleri — DALGA D KARARI (testler bunlara göre sabitler)
# ---------------------------------------------------------------------------

K1 = 1.2
B = 0.75

# Alan ağırlıkları (alan tf'si bu değerle çarpılır).
ALAN_AGIRLIK: dict[str, float] = {
    "baslik": 4.0,
    "alias": 4.0,
    "etiket": 3.0,
    "yol": 1.5,
    "govde": 1.0,
}

# Tokenleştirici sürümü. Sorgu satırı biçimini/ek kuralını değiştirirse artar;
# eski DB'de `ara` net hata verir ("önce `harita indeksle`").
TOKENLEŞTIRICI_SURUM = "tr-bm25-1"

# Kök kesme uzunluğu (F5 tarzı). Bu uzunluktan kısa sözcükler KÖKÜYLE
# indekslenmez (kendi tam hâlinde gövde terimi olarak kalır).
KOK_UZUNLUK = 5

EN_COK_SONUC = 50  # `--ilk` üst sınırı (web ve CLI için ortak)

# ---------------------------------------------------------------------------
# Sözcük ayırıcıları
# ---------------------------------------------------------------------------

# Wikilink KÖŞELİ PARANTEZLERİ, URL'ler ve kod çitleri SÖZCÜK AYIRICI gibi
# davranır: `[[ızgara-notu]]` → "ızgara", "notu" (parantezler AYIRICI, içerik
# korunur). Kod çiti ve URL ise metni TAMAMEN düşürür (içerik aranmaz).
# Markdown işaretleri (`#`, `*`, `_`, `-`, `>`, `~`, `|`) ayırıcıdır, terim değil.
_KOD_CIT = re.compile(r"```[\s\S]*?```|~~~[\s\S]*?~~~|`[^`\n]*`")
_URL = re.compile(r"\b(?:https?://|www\.)\S+", re.I)
# Köşeli parantezleri boşluğa çevir: [[ızgara-notu]] → " ızgara-notu "
_WIKILINK = re.compile(r"!?\[|\]|\[\[")
_SOZCUK = re.compile(r"\w+", re.UNICODE)

# ---------------------------------------------------------------------------
# Türkçe katlama
# ---------------------------------------------------------------------------

# Durak sözcükler (küçük Türkçe + İngilizce). Katlanmış hâlleriyle eşleşir.
DURAK_SOZCUKLER: frozenset[str] = frozenset(
    {
        # Türkçe
        "acaba", "ama", "artık", "asla", "aslında", "az", "bazı", "belki", "ben",
        "bile", "bir", "biraz", "biz", "bu", "böyle", "böylece", "çok", "çünkü",
        "da", "daha", "de", "defa", "değil", "diye", "diğer", "eğer", "en", "fakat",
        "gibi", "hem", "henüz", "hep", "hepsi", "her", "hiç", "için", "ile", "ise",
        "içinde", "kez", "ki", "kim", "mı", "mi", "mu", "mü", "nasıl", "ne", "neden",
        "nerde", "nereye", "niçin", "o", "olan", "olarak", "oldu", "olduğu", "olmak",
        "olsa", "olsun", "onlar", "onu", "onun", "orada", "öyle", "rağmen", "sadece",
        "sen", "siz", "sonra", "şey", "şu", "tüm", "ve", "veya", "ya", "yani", "yapılan",
        "yapmak", "yoksa", "zaten",
        # İngilizce
        "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from", "has",
        "have", "in", "is", "it", "its", "of", "on", "or", "that", "the", "this", "to",
        "was", "were", "which", "with", "you", "your",
    }
)

# `KOK_UZUNLUK`'tan kısa durak sözcük (yok) — liste yalnızca tam kelimedir.


def katla(metin: str) -> str:
    """NFC → Türkçe küçük harf → katlama. Sorgu ve belge aynı işlemden geçer.

    Sıra önemlidir: önce yalnız `I`/`İ` elle eşlenir (Python'un `str.lower()`
    bu ikisini yanlış çevirirdi: `I`→`i` vermeli), sonra kalan büyük harfler
    küçültülür, en sonda `ı ç ğ ö ş ü` katlanır. Böylece "IŞIK", "ışık" ve
    "isik" aynı terime ("isik") düşer.
    """
    metin = unicodedata.normalize("NFC", metin)
    metin = metin.translate(str.maketrans({"I": "ı", "İ": "i"})).lower()
    metin = metin.translate(str.maketrans({"ı": "i", "ç": "c", "ğ": "g",
                                           "ö": "o", "ş": "s", "ü": "u"}))
    return unicodedata.normalize("NFC", metin)


def sozcukler(metin: str) -> list[str]:
    """Katlanmış, uzunluğu ≥ 2 olan sözcükler (ayırıcılar uygulanmış)."""
    metin = _KOD_CIT.sub(" ", metin)
    metin = _URL.sub(" ", metin)
    metin = _WIKILINK.sub(" ", metin)
    temiz = katla(metin)
    return [s for s in _SOZCUK.findall(temiz) if len(s) >= 2]


def kok(sozcuk: str) -> str | None:
    """5+ karakterli sözcüğün ilk 5 karakteri; 5'ten kısaysa `None`.

    Girdi **katlanmış** olmalıdır (`kok(katla(w))` çağrılır):
    `kok("güvenlik")` katlanmamış "güven" döner ve indeksle eşleşmez.
    """
    return sozcuk[:KOK_UZUNLUK] if len(sozcuk) >= KOK_UZUNLUK else None


def terimler(metin: str, tam: bool = False) -> list[str]:
    """Metinden indeks terimleri.

    `tam=False` (İNDEKS ve kök modu): her sözcük KÖK olarak ve, kökü varsa,
    ayrıca tam sözcük olarak da üretilir — indeks iki biçimi de tutar, böylece
    hem "borsa" hem "borsanın" sorgusu eşleşir.

    `tam=True` (`--tam`): YALNIZCA tam katlanmış sözcük. Kök üretilmez; kısa
    sözcükler zaten kendi kendisidir.
    """
    kume: list[str] = []
    gorulen: set[str] = set()

    def ekle(t: str) -> None:
        if t and t not in gorulen:
            gorulen.add(t)
            kume.append(t)

    for s in sozcukler(metin):
        if tam:
            ekle(s)
            continue
        k = kok(s)
        if k is not None:
            ekle(k)
        ekle(s)
    return kume


def terimler_tam(metin: str) -> list[str]:
    """Yalnızca tam sözcükler (tek biçimli mod için)."""
    return terimler(metin, tam=True)


# ---------------------------------------------------------------------------
# Sorgu sözdizimi
# ---------------------------------------------------------------------------


class SorguHatasi(ValueError):
    """Kullanıcı hatası: boş sorgu, tek tırnak vb."""


@dataclass
class Sorgu:
    """Ayrıştırılmış arama sorgusu."""

    terimler: list[str]          # kök terimler (OR ağırlıklı BM25)
    tam_terimler: list[str]      # `--tam` modunda kullanılan tam terimler
    ifade: str | None = None     # tırnaklı ifade (katlanmış, filtre)
    haric: list[str] = field(default_factory=list)   # `-terim` (kök)
    etiket: str | None = None    # `etiket:ad`
    klasor: str | None = None    # `klasor:ad`
    ham: str = ""

    @property
    def tumu(self) -> list[str]:
        """Sorguda geçen tüm terimler (vurgu için)."""
        return list(dict.fromkeys(self.tam_terimler + self.terimler + self.haric))


def _parcalara_ayir(metin: str) -> list[tuple[str, str]]:
    """Sorguyu `(tür, değer)` çiftlerine ayırır.

    Türler: `"ifade"` (tırnaklı), `"terim"`, `"hariç"`, `"etiket"`, `"klasor"`.
    BOZUK SÖZDİZİMİ ÇÖKMEZ: kapanmamış tırnak kalan satırı tek bir ifade
    olarak yutar, tek tırnak normal karakter sayılır.
    """
    parcalar: list[tuple[str, str]] = []
    tampon = ""
    tirnak_acik = False       # şu an tırnak içindeyiz
    tirnak_goruldu = False    # bu parça tırnakla BAŞLADI mı?
    for karakter in metin:
        if karakter == '"':
            if not tirnak_acik:
                tirnak_goruldu = True
            # Kapanış: parçayı "ifade" olarak kapat.
            if tirnak_acik:
                if tampon:
                    parcalar.append(("ifade", tampon))
                tampon = ""
                tirnak_acik = False
                tirnak_goruldu = False
            else:
                tirnak_acik = True
            continue
        if karakter.isspace() and not tirnak_acik:
            if tampon:
                parcalar.append(("terim", tampon))
            tampon = ""
            tirnak_goruldu = False
            continue
        tampon += karakter
    if tampon:
        # Kapanmamış tırnak: kalanı ifade sayılır (bozuk sözdizimi çökmez).
        parcalar.append(("ifade" if tirnak_acik or tirnak_goruldu else "terim", tampon))

    sonuc: list[tuple[str, str]] = []
    for tur, deger in parcalar:
        alt = deger.lower()
        if tur == "ifade":
            if deger.strip():
                sonuc.append(("ifade", deger.strip()))
        elif alt.startswith("etiket:") and len(deger) > len("etiket:"):
            sonuc.append(("etiket", deger[len("etiket:") :]))
        elif alt.startswith("klasor:") and len(deger) > len("klasor:"):
            sonuc.append(("klasor", deger[len("klasor:") :]))
        elif deger.startswith("-") and len(deger) > 1:
            sonuc.append(("hariç", deger[1:]))
        else:
            sonuc.append(("terim", deger))
    return sonuc


def sorgu_ayir(metin: str) -> Sorgu:
    """Sorgu satırını ayrıştırır. Çökmez: bozuk sözdizimi temizlenir.

    Kurallar:
      * `"tam ifade"` → ifade filtresi (tırnaklar sadece tam çift).
      * `-terim` → hariç tut (kök).
      * `etiket:ad`, `klasor:ad` → filtreler.
      * Geri kalanı boşlukla ayrılmış terimler (VEYA-ağırlıklı BM25).
      * Tek tırnak normal karakterdir (bozuk tırnak çökmez).
    """
    ham = (metin or "").strip()
    if not ham:
        raise SorguHatasi("Arama sorgusu boş. Örnek: harita ara \"güvenlik\"")

    terim_listesi: list[str] = []
    tam_listesi: list[str] = []
    haric: list[str] = []
    etiket: str | None = None
    klasor: str | None = None
    ifade: str | None = None

    for tur, deger in _parcalara_ayir(ham):
        if tur == "ifade":
            ifade = deger
        elif tur == "etiket":
            etiket = deger
        elif tur == "klasor":
            klasor = deger
        elif tur == "hariç":
            for s in sozcukler(deger):
                k = kok(s)
                haric.append(k or s)
        else:
            terim_listesi.extend(terimler(deger))
            tam_listesi.extend(terimler_tam(deger))

    # Durak sözcük YALNIZCA sorguysa duraklar kullanılır (boş sonuç dönmez):
    # gerçek sözcük varsa duraklar tamamen düşer.
    gercek = [t for t in terim_listesi if t not in DURAK_SOZCUKLER]
    gercek_tam = [t for t in tam_listesi if t not in DURAK_SOZCUKLER]
    if not gercek:
        gercek, gercek_tam = terim_listesi, tam_listesi
    terim_listesi, tam_listesi = gercek, gercek_tam

    # YALNIZCA tırnaklı ifade varsa: ifadenin KELİMELERİ de aday havuzu
    # olur, yoksa "sorgu" hiç terim içermez ve ifade filtresi tek başına
    # bütün vault'u döndürmek zorunda kalırdı. İfade yine de ARDIŞIK
    # geçme şartıyla süzgeç görevi görür.
    if ifade and not terim_listesi:
        terim_listesi = terimler(ifade)
        tam_listesi = terimler_tam(ifade)

    return Sorgu(
        terimler=list(dict.fromkeys(terim_listesi)),
        tam_terimler=list(dict.fromkeys(tam_listesi)),
        ifade=ifade,
        haric=list(dict.fromkeys(haric)),
        etiket=etiket,
        klasor=klasor,
        ham=ham,
    )


# ---------------------------------------------------------------------------
# Sonuç
# ---------------------------------------------------------------------------


@dataclass
class Sonuc:
    """Tek bir arama sonucu (not + en iyi parça)."""

    not_id: int
    puan: float
    baslik: str
    yol: str
    etiketler: list[str]
    alinti: str
    parca: str
    vurgular: list[tuple[int, int]]   # alıntı içindeki (başlangıç, bitiş) aralıkları

    @property
    def alinti_vurgulu(self) -> list[tuple[bool, str]]:
        """Alıntı, vurgulu/vurgusuz parçalara bölünmüş olarak.

        Web şablonu bu parçaları `<mark>` ile sarar; parça dışındaki hiçbir
        metin sunucunun kendi üretmediği bir etikete girmez (XSS savunması).
        Dönen değer `(vurgulu_mu, metin)` çiftleridir.
        """
        if not self.alinti:
            return []
        parcalar: list[tuple[bool, str]] = []
        onceki = 0
        for bas, bit in self.vurgular:
            bas, bit = max(0, bas), min(len(self.alinti), bit)
            if bas >= bit:
                continue
            if bas > onceki:
                parcalar.append((False, self.alinti[onceki:bas]))
            parcalar.append((True, self.alinti[bas:bit]))
            onceki = bit
        if onceki < len(self.alinti):
            parcalar.append((False, self.alinti[onceki:]))
        return parcalar


# --- vurgu yardımcıları ----------------------------------------------------


def _vurgu_araliklari(metin: str, terimler_: list[str]) -> list[tuple[int, int]]:
    """Metinde geçen terimlerin (başlangıç, bitiş) aralıkları.

    Eşleşme KATLANMIŞ metin üzerinde yapılır ("güvenlik" terimi "Güvenlik"
    metnini bulur), ama dönen ofsetler ÖZGÜN metne aittir. `katla` karakter
    başına 1:1 eşleme yaptığı için (NFC dışında) konumlar birebir korunur.

    Terimler uzunluğa göre azalan sırada denenir; iç içe geçen kök/tam çiftleri
    (ör. `guven` ⊂ `guvenlik`) tek aralığa indirgenir.
    """
    if not terimler_ or not metin:
        return []
    katlanmis = katla(metin)
    ham: list[tuple[int, int]] = []

    for t in sorted({t for t in terimler_ if t}, key=lambda x: (-len(x), x)):
        bas = 0
        while True:
            konum = katlanmis.find(t, bas)
            if konum == -1:
                break
            bas = konum + 1
            # Yalnizca sozcuk BASINDAKI eslesmeler ve vurgu TAM SOZCUGE uzar
            # ("Kontr" degil "Kontrol"): kok modu sozcugun basini eslestirir.
            if konum > 0 and katlanmis[konum - 1].isalnum():
                continue
            bit = konum + len(t)
            while bit < len(katlanmis) and katlanmis[bit].isalnum():
                bit += 1
            ham.append((konum, bit))

    if not ham:
        return []

    ham.sort()
    birlestirilmis: list[tuple[int, int]] = [ham[0]]
    for bas, bit in ham[1:]:
        son_bas, son_bit = birlestirilmis[-1]
        if bas <= son_bit:
            birlestirilmis[-1] = (son_bas, max(son_bit, bit))
        else:
            birlestirilmis.append((bas, bit))
    return birlestirilmis


# ---------------------------------------------------------------------------
# Gizlilik katmanı — alıntı savunması
# ---------------------------------------------------------------------------

# `parse.gizli_satir_mi` bir satırın gizli olup olmadığını söyler. Arama
# İNDEKLEME sırasında süzülmüş gövde metnini kullanır; bu katman ikinci
# savunmadır: alıntı üretilirken satırlar TEKRAR süzülür.
GIZLI_YERINE = "[gizlilik nedeniyle çıkarıldı]"


def alinti_yap(metin: str, terimler_: list[str], hedef: int = 200) -> tuple[str, list[tuple[int, int]]]:
    """Eşleşmenin çevresinden ~`hedef` karakterlik, kelime sınırında kesilmiş
    alıntı + ALINTI-İÇİ vurgu aralıkları.

    Gizli satırlar ALINTIYA ASLA girmez: satırlar `gizli_satir_mi` ile yeniden
    elenir (indeks zaten süzülmüştür; bu ikinci savunma katmanıdır).

    Ofsetler doğrudan KESİLME penceresinden hesaplanır: alıntı `temiz`'in
    `[bas:bit]` dilimi ve `.strip()` UYGULANMAZ, böylece vurgu aralıkları
    kaymaz. Kırpma kelime sınırında yapılır.
    """
    guvenli = [s for s in metin.split("\n") if not gizli_satir_mi(s)]
    temiz = "\n".join(guvenli)
    araliklar = _vurgu_araliklari(temiz, terimler_)
    if not araliklar:
        return temiz[:hedef], []

    ilk_bas = araliklar[0][0]
    bas = max(0, ilk_bas - hedef // 3)
    bit = min(len(temiz), bas + hedef)
    if bit - bas < hedef:
        bas = max(0, bit - hedef)

    # Kelime sınırında kırp: BOŞLUK KARAKTERİNİN ÖTESİNE atla.
    if bas > 0:
        sonraki = temin_ara(temiz, bas, geri=False)
        bas = (sonraki + 1) if sonraki is not None else bas
    if bit < len(temiz):
        onceki = temin_ara(temiz, bit, geri=True)
        bit = onceki if onceki is not None else bit
    bas, bit = min(bas, bit), max(bas, bit)

    parca = temiz[bas:bit]
    # Vurgu aralıklarını pencereye göre kaydır ve ALINTI İÇİNDE KLİPLE.
    vurgular: list[tuple[int, int]] = []
    for a, b in araliklar:
        a2, b2 = a - bas, b - bas
        a2 = max(0, min(a2, len(parca)))
        b2 = max(0, min(b2, len(parca)))
        if a2 < b2:
            vurgular.append((a2, b2))
    return parca, vurgular


def temin_ara(metin: str, konum: int, geri: bool = False) -> int | None:
    """`konum`'a en yakın boşluk/kelime sınırı (yoksa `None`)."""
    if geri:
        for i in range(min(konum, len(metin)) - 1, -1, -1):
            if metin[i].isspace():
                return i
        return None
    for i in range(konum, len(metin)):
        if metin[i].isspace():
            return i
    return None


# ---------------------------------------------------------------------------
# Şema ve indeksleme
# ---------------------------------------------------------------------------

ARA_SEKIL = """
CREATE TABLE IF NOT EXISTS ara_belge (
    not_id    INTEGER PRIMARY KEY,
    uzunluk   INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS ara_terim (
    terim  TEXT NOT NULL,
    not_id INTEGER NOT NULL,
    alan   TEXT NOT NULL,
    tf     INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_ara_terim ON ara_terim(terim);
CREATE INDEX IF NOT EXISTS ix_ara_terim_not ON ara_terim(not_id);
CREATE TABLE IF NOT EXISTS ara_meta (
    anahtar TEXT PRIMARY KEY,
    deger   TEXT
);
"""


def sema_kontrol(baglanti: sqlite3.Connection) -> dict[str, str]:
    """Arama şeması ve meta okunur. `ara_meta`'da sürüm farklıysa hata verir."""
    tablolar = {
        r[0]
        for r in baglanti.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    eksik = {"ara_belge", "ara_terim", "ara_meta"} - tablolar
    if eksik:
        raise SorguHatasi(
            "Bu indeks aramaya hazır değil (eksik tablo: "
            + ", ".join(sorted(eksik))
            + "). Önce `harita indeksle VAULT` çalıştır."
        )
    meta = {k: v for k, v in baglanti.execute("SELECT anahtar, deger FROM ara_meta")}
    if meta.get("surum") != TOKENLEŞTIRICI_SURUM:
        raise SorguHatasi(
            "İndeks eski (tokenleştirici sürümü: "
            + str(meta.get("surum", "bilinmiyor"))
            + "). Önce `harita indeksle VAULT` ile yeniden indeksleyin."
        )
    return meta


# ---------------------------------------------------------------------------
# Arama
# ---------------------------------------------------------------------------


@dataclass
class Ayarlar:
    """Sorgu çalıştırma ayarları."""

    ilk: int = 10
    etiket: str | None = None
    klasor: str | None = None
    tam: bool = False


def _meta_float(meta: dict[str, str], anahtar: str, varsayilan: float) -> float:
    try:
        return float(meta.get(anahtar, varsayilan))
    except (TypeError, ValueError):  # pragma: no cover - bozuk meta
        return varsayilan


def ara(
    baglanti: sqlite3.Connection,
    metin: str,
    ayarlar: Ayarlar | None = None,
) -> tuple[list[Sonuc], dict[str, object]]:
    """BM25 araması. (sonuçlar, meta).

    `baglanti` SALT OKUNUR olmalıdır; hiçbir sorgu yazma yapmaz.
    """
    ayarlar = ayarlar or Ayarlar()
    sema_kontrol(baglanti)
    sorgu = sorgu_ayir(metin)
    meta = {k: v for k, v in baglanti.execute("SELECT anahtar, deger FROM ara_meta")}

    belge_sayisi = int(meta.get("belge_sayisi", 0) or 0)
    ort_uzunluk = _meta_float(meta, "ortalama_uzunluk", 1.0) or 1.0

    # Aranacak terimler: `--tam` → yalnızca tam sözcükler.
    terimler_ = sorgu.tam_terimler if ayarlar.tam else sorgu.terimler
    terimler_ = list(dict.fromkeys(terimler_))
    if not terimler_:
        return [], {"sorgu": sorgu, "sonuc": 0, "belge": belge_sayisi}

    # Sorgu terimlerinin belgedeki geçiş sayısı (parça seçimi ve vurgu için).
    skorlar: dict[int, float] = {}
    ifade_normal = katla(sorgu.ifade) if sorgu.ifade else None

    for terim in terimler_:
        satirlar = baglanti.execute(
            "SELECT not_id, alan, tf FROM ara_terim WHERE terim = ?", (terim,)
        ).fetchall()
        if not satirlar:
            continue
        # IDF, SATIR sayısıyla değil BELGE sayısıyla hesaplanır: bir terim
        # beş alanda da geçse de tek belgededir. (Satır sayısı kullanılırsa
        # alan çeşitliliği olan yaygın terimlerin IDF'i eksiye düşer ve
        # tek belgeli vault'ta HER terim elenir.)
        n_terim = len({not_id for not_id, _, _ in satirlar})
        # IDF: nadir terim ağır, her yerde geçen terim ~0.
        idf = math.log(1.0 + (belge_sayisi - n_terim + 0.5) / (n_terim + 0.5))
        if idf <= 0:
            continue
        # Alan ağırlıklı tf: aynı belgede birden çok alanda geçebilir.
        alan_tf: dict[int, float] = {}
        for not_id, alan, tf in satirlar:
            alan_tf[not_id] = alan_tf.get(not_id, 0.0) + float(tf) * ALAN_AGIRLIK.get(alan, 1.0)

        # Belge uzunlukları TEK sorguda alınır: belge başına sorgu, terim
        # sayısıyla çarpılan gereksiz sorgu sayısı üretirdi.
        not_ids = list(alan_tf)
        yer = ",".join("?" * len(not_ids))
        uzunluklar = dict(
            baglanti.execute(
                f"SELECT not_id, uzunluk FROM ara_belge WHERE not_id IN ({yer})", not_ids
            ).fetchall()
        )

        for not_id, agirlikli_tf in alan_tf.items():
            if not_id not in uzunluklar:
                continue
            uzunluk = float(uzunluklar[not_id])
            norm = 1.0 - B + B * (uzunluk / ort_uzunluk)
            # tf doygunluğu (k1): 12 kez geçen terim 12 kat puan vermez.
            bilesen = (agirlikli_tf * (K1 + 1.0)) / (agirlikli_tf + K1 * norm)
            skorlar[not_id] = skorlar.get(not_id, 0.0) + idf * bilesen

    if not skorlar:
        return [], {"sorgu": sorgu, "sonuc": 0, "belge": belge_sayisi}

    # --- Filtreler (puan hesabından SONRA: puan bozulmaz) ---
    adaylar = _filtrele(baglanti, skorlar, sorgu, ayarlar, ifade_normal)
    if not adaylar:
        return [], {"sorgu": sorgu, "sonuc": 0, "belge": belge_sayisi}

    sirali = sorted(adaylar, key=lambda c: (-c[1], c[2]))[: max(1, min(ayarlar.ilk, EN_COK_SONUC))]
    vurgu_terimleri = list(dict.fromkeys(terimler_ + sorgu.tam_terimler))
    sonuclar = [_sonuc_uret(baglanti, not_id, puan, vurgu_terimleri) for not_id, puan, _ in sirali]
    return sonuclar, {"sorgu": sorgu, "sonuc": len(sonuclar), "belge": belge_sayisi}


def _filtrele(
    baglanti: sqlite3.Connection,
    skorlar: dict[int, float],
    sorgu: Sorgu,
    ayarlar: Ayarlar,
    ifade_normal: str | None,
) -> list[tuple[int, float, str]]:
    """Filtreleri uygular; (not_id, puan, yol) listesi döner."""
    adaylar: list[tuple[int, float, str]] = []
    for not_id, puan in skorlar.items():
        satir = baglanti.execute("SELECT yol FROM notes WHERE id = ?", (not_id,)).fetchone()
        if satir is None:
            continue
        yol = satir[0]

        if sorgu.haric:
            metin = _belge_metni(baglanti, not_id)
            if any(t in katla(metin) for t in sorgu.haric):
                continue

        etiket_filtre = sorgu.etiket or ayarlar.etiket
        if etiket_filtre:
            etiketler = [
                e for (e,) in baglanti.execute(
                    "SELECT etiket FROM tags WHERE not_id = ?", (not_id,)
                )
            ]
            istenen = katla(etiket_filtre).lstrip("#")
            if not any(katla(e).lstrip("#") == istenen for e in etiketler):
                continue

        klasor_filtre = sorgu.klasor or ayarlar.klasor
        if klasor_filtre and not _klasor_eslesir(yol, klasor_filtre):
            continue

        if ifade_normal and ifade_normal not in katla(_belge_metni(baglanti, not_id)):
            continue

        adaylar.append((not_id, puan, yol))
    return adaylar


def _belge_metni(baglanti: sqlite3.Connection, not_id: int) -> str:
    """Belgenin indekslenmiş TAM metni (gövde + başlık + alias + etiket + yol)."""
    parcalar: list[str] = []
    satir = baglanti.execute("SELECT baslik FROM notes WHERE id = ?", (not_id,)).fetchone()
    if satir:
        parcalar.append(satir[0])
    parcalar.extend(
        a for (a,) in baglanti.execute("SELECT alias FROM aliases WHERE not_id = ?", (not_id,))
    )
    parcalar.extend(
        e for (e,) in baglanti.execute("SELECT etiket FROM tags WHERE not_id = ?", (not_id,))
    )
    satir = baglanti.execute("SELECT yol FROM notes WHERE id = ?", (not_id,)).fetchone()
    if satir:
        parcalar.append(satir[0].replace("/", " "))
    parcalar.extend(
        m for (m,) in baglanti.execute(
            "SELECT metin FROM chunks WHERE not_id = ? ORDER BY sira", (not_id,)
        )
    )
    return "\n".join(parcalar)


def _klasor_eslesir(yol: str, klasor: str) -> bool:
    """`klasor:ad` yol öneki veya klasör adı olarak eşleşir."""
    istenen = katla(klasor).strip().strip("/")
    if not istenen:
        return True
    parcalar = [katla(p) for p in yol.split("/")]
    if parcalar and parcalar[0] == istenen:
        return True
    return any(p == istenen for p in parcalar[:-1])


def _sonuc_uret(
    baglanti: sqlite3.Connection, not_id: int, puan: float, terimler_: list[str]
) -> Sonuc:
    """Not + en iyi parça + vurgulu alıntı üretir."""
    satir = baglanti.execute(
        "SELECT yol, baslik FROM notes WHERE id = ?", (not_id,)
    ).fetchone()
    yol, baslik = (satir[0], satir[1]) if satir else ("", "")
    etiketler = [
        e for (e,) in baglanti.execute(
            "SELECT etiket FROM tags WHERE not_id = ? ORDER BY etiket", (not_id,)
        )
    ]

    parcalar = [
        (sira, metin)
        for sira, metin in baglanti.execute(
            "SELECT sira, metin FROM chunks WHERE not_id = ? ORDER BY sira", (not_id,)
        )
    ]
    en_iyi = (0, "")
    en_iyi_skor = -1
    for sira, metin in parcalar:
        katlanmis = katla(metin)
        # Parça seçimi: sorgu terimlerini en çok içeren chunk; eşitlikte küçük `sira`.
        skor = sum(katlanmis.count(t) for t in terimler_)
        if skor > en_iyi_skor:
            en_iyi_skor, en_iyi = skor, (sira, metin)
    parca = en_iyi[1]
    alinti, vurgular = alinti_yap(parca, terimler_)

    return Sonuc(
        not_id=not_id,
        puan=round(puan, 4),
        baslik=baslik,
        yol=yol,
        etiketler=etiketler,
        alinti=alinti,
        parca=parca,
        vurgular=vurgular,
    )
