"""Markdown notlarını ayrıştırma: frontmatter, wikilink'ler, etiketler, gizli satır süzme.

Vault'a hiçbir zaman yazmaz; dosyalar yalnızca ikili salt-okunur modda açılır.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

# ---------------------------------------------------------------------------
# Gizlilik: bu desenlerden birini içeren satırlar gövdeye ve chunks'a girmez.
#
# `sk-` desenine SOL SINIR konulmuştur (aşağıdaki yorum). Gerçek anahtarlar
# token başında gelir (=sk-…, "sk-…, `sk-…`); sınırsız desen ise gerçek
# vault'ta `flask-…` içindeki "sk-" dizisini anahtar sanar.
# ---------------------------------------------------------------------------

GIZLI_DESENLER: tuple[re.Pattern[str], ...] = (
    # `sk-` giriş anahtarı. Solunda harf/rakam OLMAYACAK: `flask-app`, `risk-`
    # gibi kelimelerin içinde geçmesin. Gerçek anahtar biçimleri (baştaki
    # `=`, tırnak, boşluk, parantez) sınırdan geçer.
    re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"(?i)(password|parola|şifre)\s*[=:]"),
    re.compile(r"(?i)(api[_-]?key|token|secret)\s*[=:]\s*\S{8,}"),
    re.compile(r"-----BEGIN .*PRIVATE KEY-----"),
)

# Eşleşen satırın yerine geçen satır: satır sayısı korunur, içerik sızmaz.
GIZLI_YERINE = "[gizlilik nedeniyle çıkarıldı]"

# ---------------------------------------------------------------------------
# Kod bölgeleri: bir satırın başında (0-3 boşluk veya bir sekme önekiyle)
# en az üç ` ya da ~ işareti.
# ---------------------------------------------------------------------------

_KOD_ACILIS = re.compile(r"^[ \t]{0,3}(?P<isaret>`{3,}|~{3,})")

# Tek satırlık kod aralığı: ` ... ` (iç içe backtick'ler desteklenir).
# Satır sonunu aşmaz — aksi halde bir ``` çiti, açılış ve kapanış backtick'leri
# arasındaki HER ŞEYİ "satır içi kod" sanar ve çit içindeki linkler/etiketler
# yanlışlıkla maskelenmez.
_SATIR_KOD = re.compile(r"(?<!`)(?P<ticks>`+)(?!`)(?P<icerik>[^\n]+?)(?<!`)(?P=ticks)(?!`)")

# Obsidian biçimleri: [[hedef]], [[hedef#başlık]], [[hedef|görünen]] ve gömülü ![[...]].
_LINK_GOVDE = re.compile(r"!?\[\[(?P<ic>[^\[\]]*?)\]\]")

# Etiket: # işareti, sonra harf veya alt çizgi ile başlayan, harf/rakam/-/_/Türkçe
# harflerden oluşan gövde. `##` (başlık), `#123`, `#!` ve `foo#bar` sayılmaz.
_ETIKET = re.compile(
    r"(?<![0-9A-Za-zÇĞİÖŞÜçğıöşü_#&/\\])(#)(?P<ad>[^\s#.,;:!?()\[\]{}<>'\"`]+)"
)


def gizli_satir_mi(satir: str) -> bool:
    """Satır gizlilik desenlerinden birini içeriyorsa True."""
    return any(des.search(satir) for des in GIZLI_DESENLER)


def gizli_satirlari_suz(metin: str) -> tuple[str, int]:
    """Gizli satırları sabit yer tutucuyla değiştirir. (son_metin, suzulmus_sayisi)"""
    satirlar = metin.split("\n")
    sayac = 0
    for i, satir in enumerate(satirlar):
        if gizli_satir_mi(satir):
            satirlar[i] = GIZLI_YERINE
            sayac += 1
    return "\n".join(satirlar), sayac


def kod_bloklari_ve_satir_kodu(metin: str) -> list[tuple[int, int]]:
    """Kod bölgelerini [baslangic, bitis) karakter aralıkları olarak döndürür.

    Kapsam: paragraflar arası kod blokları (``` / ~~~) ve tek satırlık `kod`.
    Satır içi kodun bulunduğu satırın tamamı atlanır (aşırı-titizlik burada
    lehimlidir: sahte bir `#etiket` veya `[[link]]` kaçmasın).
    """
    araliklar: list[tuple[int, int]] = []
    satir_sonlari: list[int] = [0]
    for satir in metin.split("\n"):
        satir_sonlari.append(satir_sonlari[-1] + len(satir) + 1)

    acik_isaret: str | None = None
    blok_bas: int | None = None
    for i, satir in enumerate(metin.split("\n")):
        eslesme = _KOD_ACILIS.match(satir)
        if eslesme:
            isaret = eslesme.group("isaret")
            # Kapanış işareti, açılışla aynı karakteri ve en az uzunlukta olmalı.
            if acik_isaret is None:
                acik_isaret, blok_bas = isaret, i
            elif isaret[0] == acik_isaret[0] and len(isaret) >= len(acik_isaret):
                araliklar.append((satir_sonlari[blok_bas], satir_sonlari[i + 1]))
                acik_isaret, blok_bas = None, None
    if acik_isaret is not None and blok_bas is not None:
        # Kapanılmamış blok: dosyanın sonuna kadar kod sayılır.
        araliklar.append((satir_sonlari[blok_bas], len(metin)))

    for satir_kod in _SATIR_KOD.finditer(metin):
        bas = satir_kod.start()
        satir_bas = metin.rfind("\n", 0, bas) + 1
        satir_bit = metin.find("\n", satir_kod.end())
        if satir_bit == -1:
            satir_bit = len(metin)
        araliklar.append((satir_bas, satir_bit))

    return araliklar


def kod_ici(araliklar: list[tuple[int, int]], konum: int) -> bool:
    """`konum` karakteri verilen kod bölgelerinden birinin içinde mi?

    Aralık listesi metin başına BİR KEZ hesaplanıp çağırana geçirilir;
    aksi halde her `#etiket`/`[[link]]` için tüm metin yeniden taranırdı.
    """
    return any(bas <= konum < bit for bas, bit in araliklar)


# ---------------------------------------------------------------------------
# Frontmatter
# ---------------------------------------------------------------------------


@dataclass
class Not:
    """Ayrıştırılmış tek bir not."""

    yol: Path
    baslik: str
    govde: str
    mtime: float
    karakter: int
    takma_adlar: list[str] = field(default_factory=list)
    etiketler: list[str] = field(default_factory=list)
    linkler: list[tuple[str, str]] = field(default_factory=list)
    suzulmus_satir: int = 0


def _tirnak_ici(s: str) -> bool:
    s = s.strip()
    return len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'“”‘’"


def _deger_parcala(bosluk: str) -> list[str]:
    """`[a, b]` satır içi listesini veya tek bir değeri çözümler."""
    bosluk = bosluk.strip()
    if bosluk.startswith("[") and bosluk.endswith("]"):
        return _virgulle_bol(bosluk[1:-1])
    return [bosluk] if bosluk else []


def _virgulle_bol(icerik: str) -> list[str]:
    """Virgülle böler; tırnak içindeki virgüllere dokunmaz."""
    ogeler: list[str] = []
    tampon = ""
    tirnak: str | None = None
    for karakter in icerik:
        if tirnak:
            tampon += karakter
            if karakter == tirnak:
                tirnak = None
            continue
        if karakter in "\"'“”‘’":
            tirnak = karakter if len(tampon.strip()) == 0 or _tirnak_ici(tampon) else "'"
            tampon += karakter
            continue
        if karakter == ",":
            ogeler.append(tampon)
            tampon = ""
            continue
        tampon += karakter
    ogeler.append(tampon)

    sonuc: list[str] = []
    for oge in ogeler:
        oge = oge.strip()
        if _tirnak_ici(oge):
            oge = oge[1:-1].strip()
        if oge:
            sonuc.append(oge)
    return sonuc


def _temizle(bosluk: str) -> str:
    bosluk = bosluk.strip()
    return bosluk[1:-1].strip() if _tirnak_ici(bosluk) else bosluk


def frontmatter_ayir(metin: str) -> tuple[dict[str, object], str]:
    """(frontmatter sözlüğü, gövde). Frontmatter yoksa/bozuksa çökmez."""
    satirlar = metin.split("\n")
    if not satirlar or satirlar[0].rstrip("\r").strip() != "---":
        return {}, metin

    bitis = None
    for i in range(1, len(satirlar)):
        if satirlar[i].rstrip("\r").strip() in ("---", "..."):
            bitis = i
            break
    if bitis is None:
        # Kapanış yok: bozuk frontmatter, tüm metin gövde sayılır.
        return {}, metin

    veri: dict[str, object] = {}
    i = 1
    while i < bitis:
        satir = satirlar[i].rstrip("\r")
        if not satir.strip() or satir.lstrip().startswith("#"):
            i += 1
            continue

        girintili = satir[:1].isspace()
        if girintili and satir.lstrip().startswith("- "):
            oge = _temizle(satir.lstrip()[2:])
            son = veri.get("_son_liste")
            if isinstance(son, list):
                son.append(oge)
            i += 1
            continue

        if ":" not in satir:
            i += 1  # Tanınmayan satır: yok say.
            continue

        anahtar, _, kalan = satir.partition(":")
        anahtar = anahtar.strip()
        kalan = kalan.strip()
        if not anahtar:
            i += 1
            continue

        if kalan == "":
            # Blok listesi (sonraki satırlarda `- madde`) veya boş değer.
            ogeler: list[str] = []
            i += 1
            while i < bitis:
                izleyen = satirlar[i].rstrip("\r")
                if not izleyen.strip():
                    i += 1
                    continue
                if not izleyen.startswith((" ", "\t")):
                    break
                madde = izleyen.lstrip()
                if madde.startswith("- "):
                    oge = _temizle(madde[2:])
                    if oge:
                        ogeler.append(oge)
                i += 1
            veri[anahtar] = ogeler
            veri["_son_liste"] = ogeler
            continue

        if kalan.startswith("["):
            # Köşeli parantez kapanmıyorsa sonraki satırlara kadar uzat.
            if "]" not in kalan:
                parca = [kalan]
                i += 1
                while i < bitis:
                    izleyen = satirlar[i].rstrip("\r")
                    parca.append(izleyen.strip())
                    i += 1
                    if "]" in izleyen:
                        break
                kalan = " ".join(parca)
            else:
                i += 1
            veri[anahtar] = _deger_parcala(kalan)
            veri["_son_liste"] = veri[anahtar]
            continue

        veri[anahtar] = _temizle(kalan)
        veri["_son_liste"] = []
        i += 1

    veri.pop("_son_liste", None)
    govde = "\n".join(satirlar[bitis + 1 :])
    return veri, govde


def _liste_getir(veri: dict[str, object], *anahtarlar: str) -> list[str]:
    for anahtar in anahtarlar:
        if anahtar not in veri:
            continue
        deger = veri[anahtar]
        if isinstance(deger, list):
            return [str(o).strip() for o in deger if str(o).strip()]
        if isinstance(deger, str) and deger.strip():
            return [deger.strip()]
    return []


def ilk_baslik(govde: str) -> str | None:
    """Gövdedeki ilk `# ` ATL başlığı (ilk 50 satır içinde)."""
    for satir in govde.split("\n")[:50]:
        if satir.startswith("# "):
            return satir[2:].strip()
    return None


# ---------------------------------------------------------------------------
# Etiketler ve linkler
# ---------------------------------------------------------------------------


def etiketleri_cikar(govde: str) -> list[str]:
    """Gövdedeki `#etiket` biçimli etiketleri (kod, URL ve ATL dışında)."""
    kod_araliklari = kod_bloklari_ve_satir_kodu(govde)
    bulunan: list[str] = []
    for eslesme in _ETIKET.finditer(govde):
        bas = eslesme.start(1)
        ad = eslesme.group("ad")
        if kod_ici(kod_araliklari, bas):
            continue
        # Başlık işareti: `##`, `###` vb. — etiket değil.
        if ad.startswith("#"):
            continue
        # URL parçası: `https://x#y`, `...?a=1#y` — etiket değil. Satırın
        # TAMAMINA bakılır, çünkü `://` işareti `#`'den önce gelebilir.
        satir_sonu = govde.find("\n", bas)
        satir = govde[bas : satir_sonu if satir_sonu != -1 else len(govde)]
        if "://" in satir:
            continue
        # Salt sayı etiket değildir (`#123` bir soru numarası/issue olabilir).
        if not ad or not (ad[0].isalpha() or ad[0] == "_"):
            continue
        # Sondaki noktalama işaretleri etiketin parçası değildir.
        ad = ad.rstrip(".,;:!?)]}'\"”’")
        if ad and ad not in bulunan:
            bulunan.append(ad)
    return bulunan


def linkleri_cikar(metin: str) -> list[tuple[str, str]]:
    """(hedef_metin, tür) çiftleri. Kod blokları/satır içi kod yok sayılır."""
    kod_araliklari = kod_bloklari_ve_satir_kodu(metin)
    linkler: list[tuple[str, str]] = []
    for eslesme in _LINK_GOVDE.finditer(metin):
        if kod_ici(kod_araliklari, eslesme.start()):
            continue
        tur = "gomulu" if metin[eslesme.start()] == "!" else "link"
        icerik = eslesme.group("ic")
        if "|" in icerik:
            hedef = icerik.split("|", 1)[0]
        else:
            hedef = icerik
        if "#" in hedef:
            hedef = hedef.split("#", 1)[0]
        hedef = hedef.strip()
        if hedef:
            linkler.append((hedef, tur))
    return linkler


# ---------------------------------------------------------------------------
# Genel
# ---------------------------------------------------------------------------


def not_ayristir(yol: Path | str, vault_koku: Path | str | None = None) -> Not:
    """Tek bir not dosyasını ayrıştırır. Dosya SALT OKUNUR açılır.

    `vault_koku` verilirse `Not.yol` vault'a göreli olur; `baslik` için
    dosya adı (uzantısız) yedek olarak kullanılır.
    """
    yol = Path(yol)
    kok = Path(vault_koku) if vault_koku is not None else None
    istat = yol.stat()
    ham = yol.read_bytes().decode("utf-8", errors="replace")
    ham = ham.replace("\r\n", "\n")

    veri, govde = frontmatter_ayir(ham)
    govde, suzulmus = gizli_satirlari_suz(govde)

    baslik = ""
    for aday in (veri.get("title"), ilk_baslik(govde)):
        if isinstance(aday, str) and aday.strip():
            baslik = aday.strip()
            break
    if not baslik:
        baslik = yol.stem

    if kok is not None:
        try:
            goreli = yol.relative_to(kok)
        except ValueError:
            goreli = Path(yol.name)
    else:
        goreli = Path(yol.name)

    etiketler = [e.lstrip("#").strip() for e in _liste_getir(veri, "tags", "tag")]
    etiketler = [e for e in etiketler if e]
    for etiket in etiketleri_cikar(govde):
        if etiket not in etiketler:
            etiketler.append(etiket)

    return Not(
        yol=goreli,
        baslik=baslik,
        govde=govde,
        mtime=istat.st_mtime,
        karakter=len(govde),
        takma_adlar=_liste_getir(veri, "aliases", "alias"),
        etiketler=etiketler,
        linkler=linkleri_cikar(govde),
        suzulmus_satir=suzulmus,
    )


# ---------------------------------------------------------------------------
# Metin normalizasyonu (Türkçe + Unicode)
# ---------------------------------------------------------------------------

_BOSLUK = re.compile(r"\s+")


def normalize(metin: str) -> str:
    """Karşılaştırma anahtarı: NFC + Türkçe büyük/küçük harf + boşluk sadeleştirme.

    `str.casefold()` Türkçe'de 'I' → 'ı' ve 'İ' → 'i̇' (birleşik noktalı i) yapar;
    'i' ve 'ı' bu şekilde eşleşmez. Obsidian'ın davranışına uygun olarak
    I/ı → 'ı', İ/i → 'i' eşlemesi elle kurulur.
    """
    metin = unicodedata.normalize("NFC", metin)
    cevrim = str.maketrans({"I": "ı", "İ": "i", "i": "i", "ı": "ı"})
    metin = metin.translate(cevrim)
    metin = unicodedata.normalize("NFC", metin)
    return _BOSLUK.sub(" ", metin).strip().casefold()


def parca_bol(govde: str, hedef: int = 800) -> list[str]:
    """Gövdeyi ~`hedef` karakterlik parçalara böler; sınır paragraf olur.

    Paragraf sınırı bulunamazsa satır, satır sınırı da yoksa karakter sınırı
    kullanılır; hiçbir parça `hedef`'i aşmaz. Metindeki tüm karakterler
    korunur — yalnızca paragraf arası boş satırlar atlanır.
    """
    parcalar: list[str] = []
    for paragraf in _paragraflar(govde):
        if paragraf:
            parcalar.extend(_paragraf_bol(paragraf, hedef))
    if not parcalar and govde.strip():
        parcalar.append(govde.strip())
    return parcalar


def _paragraflar(metin: str) -> Iterable[str]:
    yigin: list[str] = []
    for satir in metin.split("\n"):
        if satir.strip():
            yigin.append(satir)
        else:
            yield "\n".join(yigin)
            yigin = []
    if yigin:
        yield "\n".join(yigin)


def _paragraf_bol(paragraf: str, hedef: int) -> list[str]:
    if len(paragraf) <= hedef:
        return [paragraf]
    parcalar: list[str] = []
    tampon = ""
    for satir in paragraf.split("\n"):
        aday = f"{tampon}\n{satir}" if tampon else satir
        if len(aday) <= hedef:
            tampon = aday
            continue
        if tampon:
            parcalar.append(tampon)
            tampon = ""
        if len(satir) <= hedef:
            tampon = satir
        else:
            for i in range(0, len(satir), hedef):
                parca = satir[i : i + hedef]
                if i + hedef < len(satir):
                    parcalar.append(parca)
                else:
                    tampon = parca
    if tampon:
        parcalar.append(tampon)
    return parcalar
