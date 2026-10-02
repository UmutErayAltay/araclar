"""`yazilar/*.md` dosyalarından statik yazı sayfaları üretir.

Kaynak yalnız elle yazılmış/gözden geçirilmiş dosyalardır; vault'tan OTOMATİK okuma yoktur.
Bir yazı yayınlanabilmek için frontmatter'da `herkese_acik: true` taşımalıdır (repo kuralıyla
aynı: yoksa ya da başka değerse atlanır). Markdown ALT KÜMESİ desteklenir; ham HTML ve görsel
yoktur ve her metin işaretlemeden ÖNCE `html.escape` ile kaçışlanır, yani sayfaya yalnız bu
modülün ürettiği etiketler girebilir.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from ._url import GORELI_URL, HTTPS_URL


class YaziHatasi(Exception):
    """Yayına açık işaretli bir yazının biçim hatası (yayın durdurulur)."""


@dataclass(frozen=True)
class Yazi:
    slug: str
    baslik: str
    tarih: str          # YYYY-MM-DD
    ozet: str
    etiketler: tuple[str, ...]
    govde_html: str


_SLUG_DESENI = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}\.md$")
_ANAHTARLAR = {"baslik", "tarih", "ozet", "etiketler", "herkese_acik"}
_MAKS_BASLIK, _MAKS_OZET, _MAKS_ETIKET, _MAKS_ETIKET_UZUNLUK = 120, 200, 5, 24
_MAKS_DOSYA = 200_000
_KONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _tirnak_at(deger: str) -> str:
    deger = deger.strip()
    if len(deger) >= 2 and deger[0] == deger[-1] and deger[0] in "\"'":
        return deger[1:-1]
    return deger


def frontmatter_ayir(metin: str) -> tuple[dict[str, str], str]:
    """`---` ile çevrili basit `anahtar: değer` bloğunu ve gövdeyi döndürür."""
    metin = metin.replace("\r\n", "\n").replace("\r", "\n")
    if not metin.startswith("---\n"):
        raise YaziHatasi("frontmatter yok (dosya '---' ile başlamalı)")
    son = metin.find("\n---\n", 3)
    if son == -1:
        if metin.endswith("\n---"):
            son = len(metin) - 4
        else:
            raise YaziHatasi("frontmatter kapanmıyor ('---' eksik)")
    alanlar: dict[str, str] = {}
    for satir in metin[4:son].split("\n"):
        if not satir.strip() or satir.lstrip().startswith("#"):
            continue
        anahtar, ayirac, deger = satir.partition(":")
        anahtar = anahtar.strip()
        if not ayirac or anahtar not in _ANAHTARLAR:
            raise YaziHatasi(f"tanınmayan frontmatter satırı: {anahtar[:30]!r}")
        if anahtar in alanlar:
            raise YaziHatasi(f"{anahtar} iki kez tanımlı")
        alanlar[anahtar] = deger.strip()
    return alanlar, metin[son + 5 :]


def _etiketler(ham: str) -> tuple[str, ...]:
    ham = ham.strip()
    if ham.startswith("[") and ham.endswith("]"):
        ham = ham[1:-1]
    parcalar = [_tirnak_at(p) for p in ham.split(",") if p.strip()]
    if len(parcalar) > _MAKS_ETIKET:
        raise YaziHatasi(f"en fazla {_MAKS_ETIKET} etiket")
    for p in parcalar:
        if not 1 <= len(p) <= _MAKS_ETIKET_UZUNLUK:
            raise YaziHatasi(f"etiket 1-{_MAKS_ETIKET_UZUNLUK} karakter olmalı")
    return tuple(parcalar)


def _metin_alani(alanlar: dict[str, str], ad: str, en_cok: int) -> str:
    deger = _tirnak_at(alanlar.get(ad, ""))
    if not deger:
        raise YaziHatasi(f"{ad} zorunlu")
    if len(deger) > en_cok:
        raise YaziHatasi(f"{ad} en fazla {en_cok} karakter")
    if _KONTROL.search(deger):
        raise YaziHatasi(f"{ad} kontrol karakteri içeremez")
    return deger


# --- Markdown alt kümesi ---------------------------------------------------------------

def _link(eslesme: re.Match[str]) -> str:
    metin, adres = eslesme.group(1), eslesme.group(2)  # ikisi de zaten kaçışlı
    ham = html.unescape(adres)
    if HTTPS_URL.fullmatch(ham):
        return f'<a href="{adres}" rel="noopener noreferrer" target="_blank">{metin}</a>'
    if GORELI_URL.fullmatch(ham):
        return f'<a href="{adres}">{metin}</a>'
    raise YaziHatasi("bağlantı yalnız https:// ya da göreli yol olabilir")


def _satir_ici(metin: str) -> str:
    """Kaçışla BAŞLAR, sonra işaretleme uygular: `kod`, [m](url), **kalın**, *italik*."""
    kacisli = html.escape(metin, quote=True)
    parcalar = re.split(r"(`[^`]+`)", kacisli)
    for i, p in enumerate(parcalar):
        if i % 2:  # kod aralığı: içine işaretleme girmez
            parcalar[i] = f"<code>{p[1:-1]}</code>"
            continue
        p = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", _link, p)
        p = re.sub(r"\*\*(\S(?:.*?\S)??)\*\*", r"<strong>\1</strong>", p)
        p = re.sub(r"(?<!\*)\*(\S(?:[^*]*?\S)??)\*(?!\*)", r"<em>\1</em>", p)
        parcalar[i] = p
    return "".join(parcalar)


_LISTE_MADDE = re.compile(r"^(?:([-*])|(\d+)\.)\s+(.*)$")


def markdown_html(govde: str) -> str:
    """Markdown alt kümesini güvenli HTML'e çevirir."""
    satirlar = govde.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    cikti: list[str] = []
    paragraf: list[str] = []
    i = 0

    def paragrafi_bitir() -> None:
        if paragraf:
            cikti.append(f"<p>{_satir_ici(' '.join(paragraf))}</p>")
            paragraf.clear()

    while i < len(satirlar):
        satir = satirlar[i]
        k = satir.strip()

        if k.startswith("```"):
            paragrafi_bitir()
            kod: list[str] = []
            i += 1
            while i < len(satirlar) and not satirlar[i].strip().startswith("```"):
                kod.append(satirlar[i])
                i += 1
            if i >= len(satirlar):
                raise YaziHatasi("kod bloğu kapanmıyor (``` eksik)")
            cikti.append(f"<pre><code>{html.escape(chr(10).join(kod), quote=True)}</code></pre>")
            i += 1
            continue

        if not k:
            paragrafi_bitir()
            i += 1
            continue

        baslik = re.match(r"^(#{2,3})\s+(.+)$", k)
        if baslik:
            paragrafi_bitir()
            seviye = len(baslik.group(1))
            cikti.append(f"<h{seviye}>{_satir_ici(baslik.group(2))}</h{seviye}>")
            i += 1
            continue

        if k.startswith(">"):
            paragrafi_bitir()
            alinti: list[str] = []
            while i < len(satirlar) and satirlar[i].strip().startswith(">"):
                alinti.append(satirlar[i].strip()[1:].strip())
                i += 1
            cikti.append(f"<blockquote><p>{_satir_ici(' '.join(alinti))}</p></blockquote>")
            continue

        madde = _LISTE_MADDE.match(k)
        if madde:
            paragrafi_bitir()
            sirali = madde.group(2) is not None
            ogeler: list[str] = []
            while i < len(satirlar):
                m = _LISTE_MADDE.match(satirlar[i].strip())
                if not m or (m.group(2) is not None) != sirali:
                    break
                ogeler.append(f"<li>{_satir_ici(m.group(3))}</li>")
                i += 1
            etiket = "ol" if sirali else "ul"
            cikti.append(f"<{etiket}>{''.join(ogeler)}</{etiket}>")
            continue

        paragraf.append(k)
        i += 1

    paragrafi_bitir()
    return "\n".join(cikti)


# --- Dosyadan okuma ---------------------------------------------------------------------

def yazi_oku(yol: Path) -> Yazi | None:
    """Tek dosyayı okur. `herkese_acik: true` değilse None; yayına açık ama bozuksa YaziHatasi."""
    if not _SLUG_DESENI.fullmatch(yol.name):
        raise YaziHatasi("dosya adı küçük harf, rakam ve '-' olmalı (örn. ilk-yazi.md)")
    if yol.stat().st_size > _MAKS_DOSYA:
        raise YaziHatasi("dosya çok büyük")
    metin = yol.read_text(encoding="utf-8")
    alanlar, govde = frontmatter_ayir(metin)
    if alanlar.get("herkese_acik", "").strip().lower() != "true":
        return None  # taslak: yayınlanmaz

    baslik = _metin_alani(alanlar, "baslik", _MAKS_BASLIK)
    ozet = _metin_alani(alanlar, "ozet", _MAKS_OZET)
    tarih = _tirnak_at(alanlar.get("tarih", ""))
    try:
        tarih = date.fromisoformat(tarih).isoformat()
    except ValueError as exc:
        raise YaziHatasi("tarih YYYY-MM-DD olmalı") from exc
    etiketler = _etiketler(alanlar.get("etiketler", ""))
    return Yazi(
        slug=yol.name[:-3],
        baslik=baslik,
        tarih=tarih,
        ozet=ozet,
        etiketler=etiketler,
        govde_html=markdown_html(govde),
    )


def yazilari_oku(klasor: Path) -> tuple[list[Yazi], list[str]]:
    """`klasor/*.md` yazılarını okur: (yayına açık yazılar tarih azalan, atlanan taslak adları)."""
    yazilar: list[Yazi] = []
    taslaklar: list[str] = []
    for yol in sorted(klasor.glob("*.md")):
        try:
            yazi = yazi_oku(yol)
        except YaziHatasi as exc:
            raise YaziHatasi(f"{yol.name}: {exc}") from exc
        if yazi is None:
            taslaklar.append(yol.name)
        else:
            yazilar.append(yazi)
    yazilar.sort(key=lambda y: (y.tarih, y.slug), reverse=True)
    return yazilar, taslaklar
