"""Dalga D değerlendirmesi: BM25 arama vs. naif alt-dize araması.

NE ÖLÇÜLÜR (ve NE ÖLÇÜLMEZ):
  * (A) NAİF TABAN — "terimleri alt-dize olarak içeren notlar, toplam geçiş
    sayısına göre sıralanır". Bu, Obsidian TARZININ düz arama davranışının
    MAKUL BİR VEKİLİDİR. **Obsidian ölçülmüştür** iddiası YOKTUR; hiçbir
    Obsidian sürümü çalıştırılmamıştır, yalnızca davranışı temsil eden
    basit bir taban tanımlanmıştır.
  * (B) BM25 — `harita.ara`'nın gerçek puanlaması.

Ölçütler: MRR (mean reciprocal rank) ve ilk-3 isabet oranı.

Kullanım:
    python3 scripts/ara_degerlendirme.py             # tabloyu yazdır
    python3 scripts/ara_degerlendirme.py --json      # makine okunur
    python3 scripts/ara_degerlendirme.py --detay     # sorgu sorgu ayrıntı

Tüm içerik KURGUSALDIR; gerçek vault'tan hiçbir veri girmez.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

from harita import ara as ara_modulu  # noqa: E402
from harita.index import indeksle  # noqa: E402

# ---------------------------------------------------------------------------
# KURGUSAL değerlendirme vault'u: 40+ not, gerçekçi Türkçe dağılım.
#
# TASARIM: Sorgular rekabetli olsun diye vault'ta (a) "popüler" sözcükler
# (not, proje, veri, test) HER yerde geçer, (b) "nadir" sözcükler
# (sızıntı, dönüşüm, homomorfizma…) yalnız birkaç notta bulunur. Bu, gerçek
# bir vault'un yapısıdır: genel sözcükler seyrek değildir.
#
# Kilit not konuyu BAŞLIKTAN/etiketten taşır ve gövdesi kısadır; hem BM25'in
# `b` uzunluk cezasından hem de nadir sözcük IDF'inden kazanır. Naif taban
# ise popüler sözcüklerin çoklu geçtiği notları öne alır.
# ---------------------------------------------------------------------------

# (göreli yol, frontmatter başlığı, etiketler, gövde)
NOTLAR: list[tuple[str, str, list[str], str]] = [
    # --- 1) Borsa / finans -------------------------------------------------
    ("finans/borsa-modeli-notu.md", "Borsa Modeli Başarısızlığı", ["finans", "model"],
     "Borsa modeli neden başarısız oldu? Eğitim verisi sızıntılıydı ve "
     "işlem hacmi gerçekçi değildi. Model doğrulama setinde iyi, üretimde "
     "kötü çıktı."),
    ("finans/veri-sizintisi.md", "Eğitim Verisi Sızıntısı", ["finans", "veri"],
     "Model eğitim verisinde gelecek dönem bilgisi vardı. Sızıntı düzeltilince "
     "skorlar geriledi."),
    ("finans/islem-hacmi.md", "İşlem Hacmi Anomalisi", ["finans", "veri"],
     "Şubat ayında borsa işlem hacmi beklenenden yüksek çıktı. Hacim verisi "
     "kaynak sağlayıcıda güncellenmemiş."),
    ("finans/gunluk-borsa-notu.md", "Günlük Borsa Notu", ["gunluk"],
     "Bugün borsa biraz toparladı. Model sinyal üretmedi."),
    ("finans/portfoy-agirlari.md", "Portföy Ağırlıkları", ["finans"],
     "Model portföy ağırlıkları eşit ağırlıktan uzaklaştı."),
    # --- 2) Güvenlik --------------------------------------------------------
    ("guvenlik/sifre-politikasi.md", "Şifre Politikası", ["guvenlik", "politika"],
     "Şifre politikası en az 12 karakter, sözlük parolası yasak. Parola "
     "yöneticisi kullanımı zorunlu."),
    ("guvenlik/anahtar-donusu.md", "Anahtar Dönüşüm Politikası", ["guvenlik"],
     "API anahtarı 90 günde bir dönmeli. Sızdırılmış anahtar olayı yaşandı."),
    ("guvenlik/guvenlik-denetimi.md", "Güvenlik Denetimi Notları", ["guvenlik", "denetim"],
     "Güvenlik denetimi üç haftada bir yapılır. Bulgu sayısı azaldı."),
    ("guvenlik/yedekleme.md", "Yedekleme Stratejisi", ["guvenlik"],
     "Günlük yedek alınır, haftalık geri yükleme denenir."),
    ("guvenlik/kimlik-dogrulama.md", "Kimlik Doğrulama", ["guvenlik"],
     "Parola gücü denetimi sıfır güçlü parolayı reddeder."),
    # --- 3) Proje yönetimi --------------------------------------------------
    ("proje/plan-2026.md", "2026 Proje Planı", ["proje", "plan"],
     "2026 planı üç faza ayrıldı: indeks, arama, özet. Her faz iki haftada "
     "biter."),
    ("proje/kapsam.md", "Proje Kapsamı", ["proje"],
     "Proje kapsamı not grafiği ve aramadır. Özet sonraki faza alındı."),
    ("proje/takvim.md", "Proje Takvimi", ["proje", "plan"],
     "Takvimde faz sınırları ve denetim tarihleri var."),
    ("proje/mutfakat.md", "Proje Mutfakları", ["proje", "atlas"],
     "Her proje için ayrı mutfak klasörü açılır."),
    ("proje/teknik-borc.md", "Teknik Borç Listesi", ["proje", "teknik"],
     "Teknik borç: testler yavaş, indeksleme yavaş, bağımlılık çok."),
    # --- 4) Test / kalite ----------------------------------------------------
    ("test/kabul-kriteri.md", "Kabul Kriteri Yazımı", ["test", "yontem"],
     "Kabul kriteri ölçülebilir olmalı: sayı, eşik, çıktı. 'İyi çalışıyor' "
     "kriter değildir."),
    ("test/birim-testleri.md", "Birim Testi Kapsamı", ["test"],
     "Birim testleri saf fonksiyonları sınar; ağ ve dosya sistemi yok."),
    ("test/enerji-testleri.md", "Uçtan Uca Testler", ["test", "otomasyon"],
     "Uçtan uca testler gerçek sunucuyu ayağa kaldırır ve tarayıcıyı sürer."),
    ("test/kapsam-notu.md", "Kapsam Dışı Liste", ["test", "yontem"],
     "Kapsam dışı: vault yazma, eklenti, senkronizasyon."),
    ("test/performans-notu.md", "Performans Ölçüm Notları", ["test", "performans"],
     "1200 notluk vault'ta indeksleme ve sorgu gecikmesi ölçülür."),
    # --- 5) Hata ayıklama ---------------------------------------------------
    ("hata/turhata-ayiklama.md", "Tur Hata Ayıklama Günlüğü", ["hata", "gunluk"],
     "Karşılaşılan hata: döngüsel içe aktarma. Çözüm: tembel içe aktarma."),
    ("hata/gunluk-hata.md", "Sık Karşılaşılan Hatalar", ["hata"],
     "Yazım hatası ve yanlış tür hataları en sık nedenler."),
    ("hata/istek-hatasi.md", "HTTP 400 Hatası", ["hata", "web"],
     "400 hatası bozuk sorgudan gelir. Sunucu düz metin döner."),
    ("hata/yinelenen-hata.md", "Yinelenen Arama Hatası", ["hata", "ara"],
     "Arama hatası: kök kesme kuralı 'karar' ve 'kararname' sözcüklerini "
     "aynı köke bağlıyor."),
    # --- 6) Öğrenme / notlar ------------------------------------------------
    ("ogrenme/delim-ogrenme.md", "Delim Öğrenme Notları", ["ogrenme"],
     "Delim öğrenme notları: veri küçük olduğunda hata payı yüksektir."),
    ("ogrenme/dosya-duzeni.md", "Dosya Düzeni İlkeleri", ["ogrenme", "yontem"],
     "Dosya adları Türkçe, ayraç alt çizgi. Tarih günlüklerde ISO."),
    ("ogrenme/not-yazma.md", "Not Yazma Tarzı", ["ogrenme", "yontem"],
     "Her not bir soruyu yanıtlar. Özet paragraf en üstte."),
    ("ogrenme/tekrar.md", "Tekrar İlkeleri", ["ogrenme"],
     "Aralıklı tekrar, uzun aralıklarla, sınavla desteklenirse kalıcı."),
    # --- 7) Altyapı ---------------------------------------------------------
    ("altyapi/sqlite-indeks.md", "SQLite İndeks Tasarımı", ["altyapi", "veri"],
     "SQLite indeksi not, link, etiket ve parça tablolarından oluşur."),
    ("altyapi/sunucu.md", "Yerel Sunucu Yapısı", ["altyapi", "web"],
     "Sunucu yalnız 127.0.0.1 üzerinde dinler. Host başlığı doğrulanır."),
    ("altyapi/ozellikler.md", "Bağımlılık Politikası", ["altyapi", "yontem"],
     "Yeni bağımlılık eklenmez; stdlib ve Flask ile kalınır."),
    ("altyapi/kod-tarama.md", "Kod Tarama Kuralları", ["altyapi", "yontem"],
     "Kod taraması: rota yüzeyi, ağ çağrısı, yazma yolu aranır."),
    ("altyapi/gunluk-akis.md", "Günlük Çalışma Akışı", ["gunluk"],
     "Günlük akış: sabah plan, öğlen kod, akşam günlük notu."),
    # --- 8) Dağıtık/geçiş notları (konu dışı ama anahtar kelime içerir) -----
    ("dagitik/tarayici-testi.md", "Tarayıcı Testi Araçları", ["test", "web"],
     "Tarayıcı testi için gerçek Chromium kullanılır."),
    ("dagitik/graf-renkleri.md", "Graf Renk Paleti", ["tasarim"],
     "Renk körü-güvenli palet seçildi. Graf düğümleri paletten."),
    ("dagitik/koyu-tema.md", "Koyu Tema Denklikleri", ["tasarim"],
     "Koyu temada zemin ve metin kontrastı yüksek tutulur."),
    ("dagitik/model-notu.md", "Model Seçim Notu", ["finans", "model"],
     "Model mimarisi karşılaştırıldı; küçük model yeterli bulundu."),
    ("dagitik/veri-temizleme.md", "Veri Temizleme Adımları", ["veri", "yontem"],
     "Veri temizleme: tekrar eden satırlar ve hatalı etiketler silindi."),
    ("dagistik/sorgu-gunlugu.md", "Sorgu Günlüğü", ["ara", "gunluk"],
     "Arama sorguları günlük olarak sayım yapılır."),
    ("dagistik/etiket-temizligi.md", "Etiket Temizliği", ["yontem"],
     "Etiketler küçük harfe çevrilir, tekilleştirilir."),
    ("dagitik/yedek-planlama.md", "Yedek Planlama", ["altyapi"],
     "Yedekler haftalık alınır, dışarıda bir kopyada tutulur."),
    ("dagitik/proje-notu.md", "Proje Durum Notu", ["proje"],
     "Proje durumu bu notta haftalık güncellenir."),
    ("dagitik/test-notu.md", "Test Ortamı Notu", ["test"],
     "Test ortamı sıcak DB ile ölçülür."),
    ("dagitik/arama-notu.md", "Arama Sıralama Notu", ["ara"],
     "Arama sıralamasında nadir terim ağır, yaygın terim hafif."),
    ("dagitik/isik-notu.md", "IŞIK ve Aydınlatma Notu", ["fizik"],
     "Işık ölçümü spektrum alanıyla yapılır. Isik seviyesi lüks cinsindendir."),
    ("dagitik/isparta-gezi.md", "Isparta Gezi Notu", ["seyahat"],
     "Isparta gezisi günlüğü, ısparta ili coğrafyası."),
    ("dagitik/kisisel-not.md", "Kişisel Ayar Notu", ["kisisel"],
     "Çalışma saati tercihi ve kişisel rutin notu."),
    # --- 9) POPÜLER sözcük taşıyan rakip notlar ----------------------------
    # Aşağıdakiler "not/proje/veri/test" gibi yaygın sözcükleri ÇOK kez
    # içerir. Naif taban (toplam geçiş) bunları öne alırken BM25, aynı
    # yaygınlıkta oldukları için cezalandırır; sıralama nadir terime gider.
    ("dagitik/proje-notu-2.md", "Proje Notu İkinci", ["proje", "not"],
     "Bu proje notu projeyi özetler. Proje notları düzenli tutulur. "
     "Her proje için ayrı not açılır. Proje notu günceldir."),
    ("dagitik/veri-notu-2.md", "Veri Notu İkinci", ["veri", "not"],
     "Veri notu veri kaynaklarını listeler. Veri notları güncellenir. "
     "Veri seti notu her projede bulunur."),
    ("projeler/test-notu-2.md", "Test Notu İkinci", ["test", "not"],
     "Bu test notu testleri listeler. Test notu ayrı tutulur. Test notu "
     "proje klasöründe durur."),
    ("gunluk/gunluk-not-1.md", "Günlük Not Bir", ["gunluk", "not"],
     "Günlük not bugünkü işleri yazar. Günlük not kısa tutulur."),
    ("notlar/toplu-not.md", "Toplu Not", ["not"],
     "Bu not diğer notları toplar. Not sayısı arttıkça liste uzar."),
]


# (sorgu, beklenen not yolu, sınıf)
SORGULAR: list[tuple[str, str, str]] = [
    ("borsa modeli", "finans/borsa-modeli-notu.md", "nadir_terim"),
    ("model başarısız", "finans/borsa-modeli-notu.md", "nadir_terim"),
    ("eğitim verisi sızıntısı", "finans/veri-sizintisi.md", "nadir_terim"),
    ("veri sızıntı", "finans/veri-sizintisi.md", "nadir_terim"),
    ("işlem hacmi anomalisi", "finans/islem-hacmi.md", "nadir_terim"),
    ("şifre politikası", "guvenlik/sifre-politikasi.md", "baslik_agirligi"),
    ("parola yönetici", "guvenlik/sifre-politikasi.md", "baslik_agirligi"),
    ("anahtar dönüşüm", "guvenlik/anahtar-donusu.md", "baslik_agirligi"),
    ("güvenlik denetimi", "guvenlik/guvenlik-denetimi.md", "baslik_agirligi"),
    ("yedekleme stratejisi", "guvenlik/yedekleme.md", "nadir_terim"),
    ("kimlik doğrulama", "guvenlik/kimlik-dogrulama.md", "baslik_agirligi"),
    ("kabul kriteri", "test/kabul-kriteri.md", "baslik_agirligi"),
    ("kapsam dışı", "test/kapsam-notu.md", "nadir_terim"),
    ("uçtan uca test", "test/enerji-testleri.md", "nadir_terim"),
    ("performans ölçüm", "test/performans-notu.md", "baslik_agirligi"),
    ("tur hata ayıklama", "hata/turhata-ayiklama.md", "baslik_agirligi"),
    ("http 400", "hata/istek-hatasi.md", "nadir_terim"),
    ("yinelenen arama hatası", "hata/yinelenen-hata.md", "baslik_agirligi"),
    ("sık karşılaşılan hatalar", "hata/gunluk-hata.md", "baslik_agirligi"),
    ("delim öğrenme", "ogrenme/delim-ogrenme.md", "baslik_agirligi"),
    ("tekrar ilkeleri", "ogrenme/tekrar.md", "baslik_agirligi"),
    ("not yazma tarzı", "ogrenme/not-yazma.md", "baslik_agirligi"),
    ("dosya düzeni", "ogrenme/dosya-duzeni.md", "baslik_agirligi"),
    ("sunucu yapısı", "altyapi/sunucu.md", "baslik_agirligi"),
    ("bağımlılık politikası", "altyapi/ozellikler.md", "baslik_agirligi"),
    ("kod tarama kuralları", "altyapi/kod-tarama.md", "baslik_agirligi"),
    ("sqlite indeks tasarımı", "altyapi/sqlite-indeks.md", "baslik_agirligi"),
    ("graf renk paleti", "dagitik/graf-renkleri.md", "baslik_agirligi"),
    ("koyu tema denklikleri", "dagitik/koyu-tema.md", "baslik_agirligi"),
    ("veri temizleme", "dagitik/veri-temizleme.md", "baslik_agirligi"),
    ("etiket temizliği", "dagistik/etiket-temizligi.md", "baslik_agirligi"),
    ("IŞIK ölçümü", "dagitik/isik-notu.md", "turkce_eslesme"),
    ("ışık", "dagitik/isik-notu.md", "turkce_eslesme"),
    ("isik seviyesi", "dagitik/isik-notu.md", "turkce_eslesme"),
    ("ısparta ili", "dagitik/isparta-gezi.md", "turkce_eslesme"),
    ("Isparta gezisi", "dagitik/isparta-gezi.md", "turkce_eslesme"),
    ("yedek haftalık", "dagitik/yedek-planlama.md", "uzun_belge"),
    ("sorgu günlüğü", "dagistik/sorgu-gunlugu.md", "nadir_terim"),
    ("tarayıcı test araçları", "dagitik/tarayici-testi.md", "baslik_agirligi"),
    # --- Yaygın + nadir KARIŞIMI: naif tabanın en çok zorlandığı sınıf ------
    # Bu sorgularda yaygın bir sözcük ("not", "proje", "veri", "test") nadir
    # bir sözcükle birlikte verilir. Naif "toplam geçiş" yüzünden yaygın
    # sözcüğü çok kez içeren rakip notu öne alır; BM25 nadir tereme odaklanır.
    ("not sızıntı", "finans/veri-sizintisi.md", "yaygin_nadir_karisim"),
    ("veri sızıntı notu", "finans/veri-sizintisi.md", "yaygin_nadir_karisim"),
    ("proje dönüşüm", "guvenlik/anahtar-donusu.md", "yaygin_nadir_karisim"),
    ("test kriteri", "test/kabul-kriteri.md", "yaygin_nadir_karisim"),
    ("veri hacmi", "finans/islem-hacmi.md", "yaygin_nadir_karisim"),
    ("not politikası", "guvenlik/sifre-politikasi.md", "yaygin_nadir_karisim"),
    ("proje faz", "proje/plan-2026.md", "yaygin_nadir_karisim"),
    ("test ortamı", "dagistik/test-notu.md", "yaygin_nadir_karisim"),
    # --- ZORLU / BULMASI ZOR sınıflar --------------------------------------
    # Burada B'nin A'ya GAYET yakın veya bazen KÖTÜ olması beklenir:
    #   * `yaygin_tek_terim`: tek bir yaygın sözcük. BM25'in `b` uzunluk
    #     cezası kısa notu öne alır ama IDF zayıftır; ikisi de tartışmaya açık.
    #   * `cok_terimli`: dört yaygın sözcük birlikte. Naif "toplam geçiş"i
    #     saydığı için çoğu kez aynı notu seçer; BM25 alan ağırlıkları ve
    #     doygunluk nedeniyle DAĞINIK sonuç verir — burada B BAZEN KAYBEDER.
    ("veri", "dagistik/veri-temizleme.md", "yaygin_tek_terim"),
    ("not", "notlar/toplu-not.md", "yaygin_tek_terim"),
    ("günlük", "altyapi/gunluk-akis.md", "yaygin_tek_terim"),
    ("güvenlik", "guvenlik/guvenlik-denetimi.md", "yaygin_tek_terim"),
    ("model", "dagitik/model-notu.md", "yaygin_tek_terim"),
    ("test not veri proje", "dagitik/veri-notu-2.md", "cok_terimli"),
    ("proje test veri", "projeler/test-notu-2.md", "cok_terimli"),
]


def degerlendirme_vault(kok: Path) -> Path:
    """KURGUSAL değerlendirme vault'unu `kok` altına yazar."""
    vault = kok / "degerlendirme-vault"
    for goreli, baslik, etiketler, govde in NOTLAR:
        yol = vault / goreli
        yol.parent.mkdir(parents=True, exist_ok=True)
        etiket_satiri = ", ".join(etiketler)
        yol.write_text(
            f"---\ntitle: {baslik}\ntags: [{etiket_satiri}]\n---\n"
            f"# {baslik}\n\n{govde}\n",
            encoding="utf-8",
        )
    return vault


# ---------------------------------------------------------------------------
# (A) NAİF TABAN
# ---------------------------------------------------------------------------


def naif_sirala(baglanti: sqlite3.Connection, sorgu: str) -> list[str]:
    """Terimleri alt-dize olarak içeren notlar, toplam geçiş sayısına göre.

    Basit vekil: katlama UYGULANMAZ (Obsidian'ın alt-dize davranışı),
    vurgu/alan ağırlığı YOK, tf doygunluğu YOK, `b` cezası YOK.
    """
    kelimeler = [w for w in sorgu.lower().split() if len(w) >= 2]
    if not kelimeler:
        return []
    notlar = baglanti.execute("SELECT id, yol, baslik FROM notes").fetchall()
    sonuclar: list[tuple[int, str, int]] = []
    for not_id, yol, baslik in notlar:
        govde = " ".join(
            m for (m,) in baglanti.execute(
                "SELECT metin FROM chunks WHERE not_id = ?", (not_id,)
            )
        )
        etiketler = " ".join(
            e for (e,) in baglanti.execute(
                "SELECT etiket FROM tags WHERE not_id = ?", (not_id,)
            )
        )
        arama_metni = f"{baslik} {etiketler} {govde}".lower()
        toplam = sum(arama_metni.count(k) for k in kelimeler)
        if toplam > 0:
            sonuclar.append((not_id, yol, toplam))
    # Sıralama: toplam geçiş AZALAN; eşitlikte yol artan (deterministik).
    sonuclar.sort(key=lambda c: (-c[2], c[1]))
    return [yol for _, yol, _ in sonuclar]


def bm25_sirala(baglanti: sqlite3.Connection, sorgu: str, ilk: int = 100) -> list[str]:
    """(B) BM25 sıralaması — gerçek `harita.ara`."""
    sonuclar, _ = ara_modulu.ara(baglanti, sorgu, ara_modulu.Ayarlar(ilk=ilk))
    return [s.yol for s in sonuclar]


# ---------------------------------------------------------------------------
# Ölçütler
# ---------------------------------------------------------------------------


@dataclass
class SorguSonucu:
    sorgu: str
    sinif: str
    beklenen: str
    a_sira: int | None   # naif sıralamadaki konum (1 tabanlı)
    b_sira: int | None


def _sira(liste: list[str], beklenen: str) -> int | None:
    return (liste.index(beklenen) + 1) if beklenen in liste else None


def degerlendir(db: Path) -> list[SorguSonucu]:
    baglanti = sqlite3.connect(str(db))
    baglanti.execute("PRAGMA query_only = 1")  # salt okunur
    try:
        satirlar: list[SorguSonucu] = []
        for sorgu, beklenen, sinif in SORGULAR:
            a = naif_sirala(baglanti, sorgu)
            b = bm25_sirala(baglanti, sorgu)
            satirlar.append(
                SorguSonucu(sorgu, sinif, beklenen, _sira(a, beklenen), _sira(b, beklenen))
            )
        return satirlar
    finally:
        baglanti.close()


def _mrr(satirlar: list[SorguSonucu], alan: str) -> float:
    """Ortalama ters sıra; bulunmayan (None) 0 sayılır."""
    degerler = [1.0 / getattr(s, alan) if getattr(s, alan) else 0.0 for s in satirlar]
    return sum(degerler) / len(degerler) if degerler else 0.0


def _ilk3(satirlar: list[SorguSonucu], alan: str) -> float:
    vuru = sum(1 for s in satirlar if getattr(s, alan) and getattr(s, alan) <= 3)
    return vuru / len(satirlar) if satirlar else 0.0


def sinif_ozeti(satirlar: list[SorguSonucu], sinif: str) -> dict[str, object]:
    secili = [s for s in satirlar if s.sinif == sinif]
    return {
        "sinif": sinif,
        "sorgu": len(secili),
        "a_mrr": round(_mrr(secili, "a_sira"), 3),
        "b_mrr": round(_mrr(secili, "b_sira"), 3),
        "a_ilk3": round(_ilk3(secili, "a_sira"), 3),
        "b_ilk3": round(_ilk3(secili, "b_sira"), 3),
    }


def tablo_yaz(satirlar: list[SorguSonucu]) -> None:
    print("Değerlendirme: (A) naif alt-dize  vs  (B) BM25")
    print("Ölçüt: beklenen notun sırası (MRR) ve ilk-3 isabeti.")
    print()
    baslik = f"{'SINIF':<18} {'N':>3}  {'A MRR':>6} {'B MRR':>6}  {'A ilk3':>6} {'B ilk3':>6}"
    print(baslik)
    print("-" * len(baslik))
    for sinif in dict.fromkeys(s.sinif for s in satirlar):
        o = sinif_ozeti(satirlar, sinif)
        print(
            f"{o['sinif']:<18} {o['sorgu']:>3}  {o['a_mrr']:>6.3f} {o['b_mrr']:>6.3f}"
            f"  {o['a_ilk3']:>6.3f} {o['b_ilk3']:>6.3f}"
        )
    print("-" * len(baslik))
    print(
        f"{'TOPLAM':<18} {len(satirlar):>3}  {_mrr(satirlar,'a_sira'):>6.3f} "
        f"{_mrr(satirlar,'b_sira'):>6.3f}  {_ilk3(satirlar,'a_sira'):>6.3f} "
        f"{_ilk3(satirlar,'b_sira'):>6.3f}"
    )


def main() -> int:
    ay = argparse.ArgumentParser(description=__doc__)
    ay.add_argument("--json", action="store_true", help="JSON bas")
    ay.add_argument("--detay", action="store_true", help="Sorgu sorgu tabloyu yaz")
    args = ay.parse_args()

    with tempfile.TemporaryDirectory(prefix="harita-degerlendirme-") as gecici:
        kok = Path(gecici)
        db = kok / "degerlendirme.db"
        indeksle(degerlendirme_vault(kok), db)
        satirlar = degerlendir(db)

    if args.json:
        veri = {
            "toplam": {
                "n": len(satirlar),
                "a_mrr": round(_mrr(satirlar, "a_sira"), 4),
                "b_mrr": round(_mrr(satirlar, "b_sira"), 4),
                "a_ilk3": round(_ilk3(satirlar, "a_sira"), 4),
                "b_ilk3": round(_ilk3(satirlar, "b_sira"), 4),
            },
            "siniflar": [sinif_ozeti(satirlar, s) for s in dict.fromkeys(x.sinif for x in satirlar)],
            "sorgular": [
                {
                    "sorgu": s.sorgu, "sinif": s.sinif, "beklenen": s.beklenen,
                    "a_sira": s.a_sira, "b_sira": s.b_sira,
                }
                for s in satirlar
            ],
        }
        print(json.dumps(veri, ensure_ascii=False, indent=2))
        return 0

    tablo_yaz(satirlar)
    if args.detay:
        print()
        print(f"{'SORGÜ':<28} {'SINIF':<18} {'A':>4} {'B':>4}")
        for s in satirlar:
            print(f"{s.sorgu:<28} {s.sinif:<18} {s.a_sira or '-':>4} {s.b_sira or '-':>4}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
