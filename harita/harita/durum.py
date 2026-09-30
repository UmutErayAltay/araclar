"""`harita durum` — kule (kontrol kulesi) entegrasyonu için SAYI/ DURUM çıktısı.

Sözleşme (v1, `entegrasyon_sozlesme.md`) bağlayıcıdır:
  * stdout'a YALNIZCA tek bir JSON nesnesi: sayı, bool, sabit kısa etiket,
    ISO-8601 zaman. Not başlığı/içeriği/yolu, repo yolu, commit başlığı
    ASLA girmez.
  * Ağa çıkmaz, cor/LLM çağırmaz, hiçbir yere YAZMAZ, indeksleme/tarama
    TETİKLEMEZ — yalnızca mevcut indeksi `mode=ro` ile okur.
  * Bilinmeyen için `null` (0 DEĞİL). `hata` SABİT kısa koddur; istisna metni,
    dosya yolu, SQL veya kullanıcı içeriği ne stdout'a ne stderr'e girer.

Sayılar YENİDEN hesaplanmaz: `not_sayisi`/`kirik_link` web `/saglik` ve
`/kirik` sayfasının, `yetim_not` ise `/yetim` sayfasının kullandığı mevcut
`index` sorgularından gelir (`toplam_sayaclar`, `yetim_ayir`).
`tutarlilik_uyari` da `harita tutarlilik` ile aynı `bulgular_uret` çıktısının
uyarı SAYISIDIR — ikinci bir karşılaştırma mantığı YOKTUR.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from . import index as indeks_moduli

SURUM = 1
KAYNAK = "harita"

# `hata` alanı SABİT koddur; hiçbir dinamik metin (istisna, yol) buraya girmez.
HATA_INDEKS_YOK = "indeks_yok"
HATA_OKUNAMADI = "okunamadi"
HATA_YOK_BILGI = "yok_bilgi"

# `tutarlilik_uyari` için: atlas DB'si/eşleme hazır DEĞİLSE uyarı sayısı
# değil `null` (0 değil) döner — 0 "uyarı yok" demektir, "hesaplanamadı" değil.
UYARI_BILINMIYOR: None = None


@dataclass
class Durum:
    """`durum --json` çıktısı. Alanlar sözleşmedeki adlarla birebir aynıdır.

    `null` olan alanlar JSON'a `null` olarak yazılır; `0` olan alanlar `0`
    kalır. Bu ayrım bilinçlidir: "ölçüldü ve sıfır" ile "hesaplanamadı"
    kule için farklı sinyallerdir.
    """

    son_indeks: str | None = None
    indeks_bayat: bool | None = None
    not_sayisi: int | None = None
    kirik_link: int | None = None
    yetim_not: int | None = None
    tutarlilik_uyari: int | None = None
    hata: str | None = None
    # Yalnız hata çıktısında bulunur; başarıda `sozluk()` bunu ATAR.
    _yalnizca_hata: bool = field(default=True, repr=False)

    def sozluk(self) -> dict[str, object]:
        """Sözleşmedeki anahtar sırasıyla JSON nesnesi.

        Hata durumunda YALNIZCA `surum`/`kaynak`/`hata` üç anahtarı çıkar:
        sözleşme "hatada da stdout'a JSON basılır" der ve ölçülebilir alan
        (0 mı, null mu) ayrımının hatada anlamı yoktur.
        """
        temel: dict[str, object] = {"surum": SURUM, "kaynak": KAYNAK}
        if self.hata is not None and self._yalnizca_hata:
            temel["hata"] = self.hata
            return temel
        temel.update(
            {
                "son_indeks": self.son_indeks,
                "indeks_bayat": self.indeks_bayat,
                "not_sayisi": self.not_sayisi,
                "kirik_link": self.kirik_link,
                "yetim_not": self.yetim_not,
                "tutarlilik_uyari": self.tutarlilik_uyari,
            }
        )
        return temel

    def json_metni(self) -> str:
        """Tek satır JSON. `ensure_ascii=True` (sözleşme kuralı 8)."""
        return json.dumps(self.sozluk(), ensure_ascii=True, separators=(",", ":"))


def indeks_bayati(
    baglanti: sqlite3.Connection, vault: Path | str | None
) -> bool | None:
    """İndeks, vault'taki en yeni not değişikliğinden eski mi?

    `True`  : vault'ta indekslenmemiş daha yeni bir not var.
    `False` : indeks güncel.
    `None`  : HESAPLANAMAZ (vault verilmedi, indekste `kok`/not yok ya da
              vault okunamadı). `False` UYDURMAZ — sözleşme "bilinmeyen için
              null (0 DEĞİL)" der.

    Kıyas YALNIZCA indekslenmiş notların `mtime`'si ile vault'un o anki en yeni
    `.md` dosyasının `mtime`'si arasındadır; dosya İÇERİĞİ okunmaz, yalnız
    `stat` alınır ve vault'a yazılmaz.
    """
    if vault is None:
        return None
    kok = Path(vault).expanduser()
    if not kok.is_dir():
        return None

    meta = indeks_moduli.indeks_meta_oku(baglanti)
    if meta.get("kok") and Path(str(meta["kok"])) != kok.resolve():
        # İndeks BAŞKA bir vault'un. Karşılaştırma anlamsız; iddia etme.
        return None
    indeks_mtime = indeks_moduli.son_not_mtime(baglanti)
    if indeks_mtime is None:
        return None

    en_yeni: float | None = None
    try:
        for yol in indeks_moduli.notlari_tara(kok):
            try:
                mtime = yol[0].stat().st_mtime
            except OSError:
                continue
            if en_yeni is None or mtime > en_yeni:
                en_yeni = mtime
    except OSError:
        return None
    if en_yeni is None:
        return None
    return en_yeni > indeks_mtime


def tutarlilik_uyari_sayisi(
    vault: Path | str | None,
    atlas_db: Path | str | None = None,
    eslesme_yolu: Path | str | None = None,
    bugun: date | None = None,
) -> int | None:
    """`tutarlilik` karşılaştırması çalışabiliyorsa UYARI SAYISI, değilse `None`.

    `None` (0 DEĞİL) şu durumlarda döner: vault yok, atlas DB'si/eşleme
    dosyası yok, atlas DB'si şemayla uyuşmuyor. Böylece kule "uyarı yok"
    (0) ile "hesaplayamadım" (null) ayrımını korur.

    `bugun` verilmezse gerçek gün kullanılır. Testler `tutarlilik`'teki gibi
    iki komutu AYNI referans gün üzerinde karşılaştırabilsin diye bunu
    geçirir: aksi halde "bugün"ü farklı olan iki çalıştırma farklı sayı
    üretirdi (durgunluk eşiği takvim gününe duyarlıdır).

    atlas DB'si `atlas_oku` içinde `mode=ro` ile açılır; hiçbir yere yazılmaz.
    """
    if vault is None:
        return None
    from . import tutarlilik as tut_moduli

    kok = Path(vault).expanduser()
    if not kok.is_dir():
        return None

    db_yolu = Path(atlas_db).expanduser() if atlas_db else tut_moduli.VARSAYILAN_ATLAS_DB
    if not db_yolu.exists():
        return None
    try:
        atlas = tut_moduli.atlas_oku(db_yolu)
    except (SystemExit, sqlite3.Error, OSError):
        return None

    eslesme = tut_moduli.eslesme_dosyasi_oku(
        Path(eslesme_yolu).expanduser() if eslesme_yolu else tut_moduli.VARSAYILAN_ESLESME
    )
    try:
        rapor = tut_moduli.bulgular_uret(kok, atlas, eslesme, bugun=bugun)
    except (SystemExit, OSError, sqlite3.Error):
        return None
    return len(rapor.uyarilar)


def durum_oku(
    db_yolu: Path | str, vault: Path | str | None = None
) -> Durum:
    """MEVCUT indeksi salt okunur okur ve `Durum` döndürür.

    İndeksleme/TARAMA TETİKLEMEZ: `baglan_salt_okunur` (`mode=ro`) kullanılır
    ve `indeks_modulu.indeksle` HİÇ çağrılmaz. `son_indeks` bilinmiyorsa
    (Dalga E'den önce yazılmış indeks) `null` döner.
    """
    yol = Path(db_yolu).expanduser()
    if not yol.exists():
        return Durum(hata=HATA_INDEKS_YOK, _yalnizca_hata=True)

    try:
        baglanti = indeks_moduli.baglan_salt_okunur(yol)
    except sqlite3.Error:
        return Durum(hata=HATA_OKUNAMADI, _yalnizca_hata=True)
    try:
        # Sayılar: web `/saglik`, `/kirik` ve `/yetim` ile AYNI sorgular.
        sayaclar = indeks_moduli.toplam_sayaclar(baglanti)
        kirik = sayaclar["kirik"]
        # `yetim_not` = GERÇEK yetimler (`/yetim` sayfasının "gercek" listesi):
        # `daily/` günlükleri ve kök dosyaları YAPISAL yalnızlıktır, uyarı değil.
        yetim_gercek = len(indeks_moduli.yetim_ayir(baglanti).gercek)
        meta = indeks_moduli.indeks_meta_oku(baglanti)
        son_indeks = meta.get("son_indeks")
        bayat = indeks_bayati(baglanti, vault)
    except sqlite3.Error:
        return Durum(hata=HATA_OKUNAMADI, _yalnizca_hata=True)
    finally:
        baglanti.close()

    return Durum(
        son_indeks=str(son_indeks) if son_indeks else None,
        indeks_bayat=bayat,
        not_sayisi=int(sayaclar["not"]),
        kirik_link=int(kirik),
        yetim_not=int(yetim_gercek),
        tutarlilik_uyari=UYARI_BILINMIYOR,  # CLI `vault`'u geçince hesaplanır
        hata=None,
        _yalnizca_hata=False,
    )


def durum_ozet_metni(durum: Durum) -> str:
    """`--json` verilmezse insan-okur tek satırlık özet (kule JSON okur)."""
    if durum.hata is not None:
        return f"harita durum: hata ({durum.hata})"

    def goster(ad: str, deger: object) -> str:
        return f"{deger}" if deger is not None else "bilinmiyor"

    bayat = durum.indeks_bayat
    bayat_metni = "bilinmiyor" if bayat is None else ("bayat" if bayat else "taze")
    return (
        f"harita durum: {goster('not', durum.not_sayisi)} not, "
        f"{goster('kirik', durum.kirik_link)} kırık link, "
        f"{goster('yetim', durum.yetim_not)} yetim not, "
        f"indeks {bayat_metni}, "
        f"tutarlılık uyarısı {goster('tutarlilik', durum.tutarlilik_uyari)}, "
        f"son indeks {goster('son_indeks', durum.son_indeks)}"
    )
