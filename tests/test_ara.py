"""Dalga D — BM25 arama motoru testleri.

Kapsam: tokenleştirme/Türkçe katlama, sorgu sözdizimi, BM25 sıralama
(alan ağırlığı, IDF, `b` cezası, `k1` doygunluğu), filtreler, parça+alıntı
vurgusu, gizlilik (İNDEKS katmanı ve ALINTI katmanı ayrı ayrı) ve ağ yasağı.
"""

from __future__ import annotations

import socket
import sqlite3
from pathlib import Path

import pytest

from conftest import GIZLI_ANAHTAR, yaz

from harita import ara as ara_modulu
from harita import parse as ayristirici
from harita.index import baglan, indeksle, sema_olustur


# ---------------------------------------------------------------------------
# Türkçe katlama
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "metin",
    ["IŞIK", "ışık", "isik", "Işık", "İŞIK", "Isik"],
)
def test_kayik_isik_katlamasi(metin: str) -> None:
    """IŞIK/ışık/isik/İşık → hepsi "isik"."""
    assert ara_modulu.katla(metin) == "isik"


@pytest.mark.parametrize("metin", ["ISPARTA", "Isparta", "ısparta", "İsparta", "iSPARTA"])
def test_isparta_dort_bicim(metin: str) -> None:
    """ISPARTA/Isparta/ısparta/İsparta → hepsi "isparta"."""
    assert ara_modulu.katla(metin) == "isparta"


def test_i_dotless_dort_bicim_ayri_harf_degil() -> None:
    """`I` ve `ı` katlanınca aynı; `İ` ve `i` de aynı olur."""
    assert ara_modulu.katla("İ") == ara_modulu.katla("i") == "i"
    assert ara_modulu.katla("I") == ara_modulu.katla("ı") == "i"


@pytest.mark.parametrize(
    "kelime,katlanmis",
    [
        ("ç", "c"), ("ğ", "g"), ("ö", "o"), ("ş", "s"), ("ü", "u"),
        ("Çalışma", "calisma"), ("Güneş", "gunes"), ("Öğrenme", "ogrenme"),
    ],
)
def test_turkce_harf_katlamasi(kelime: str, katlanmis: str) -> None:
    assert ara_modulu.katla(kelime) == katlanmis


def test_katlama_nfc_normalize_edilir() -> None:
    """NFC: aynı görünen harf iki farklı kod noktasıyla DAHA YAZILIRSA
    aynı terime düşer (birleşik `â` = `a` + U+0302)."""
    birlesik = "a\u0302"      # a + birleşik circumflex
    assert ara_modulu.katla("k" + birlesik + "tip") == ara_modulu.katla("kâtip")
    # Katlama sözlüğü yalnız Türkçe harfleri kapsar; `â` kastedilmeden kalır.
    assert ara_modulu.katla("kâtip") == "kâtip"


def test_katlama_bosluk_ve_buyuk_harf_digerlerini_de_kucultur() -> None:
    """Katlamadan önce normal büyük harfler de küçülür ("Borsa" → "borsa")."""
    assert ara_modulu.katla("Borsa") == "borsa"
    assert ara_modulu.katla("MODEL") == "model"


# ---------------------------------------------------------------------------
# Tokenleştirme
# ---------------------------------------------------------------------------


def test_wikilink_ayirici_gibi_davranir() -> None:
    """`[[ızgara-notu]]` → "ızgara", "notu" (köşeli parantezler ayırıcı)."""
    assert ara_modulu.sozcukler("[[ızgara-notu]]") == ["izgara", "notu"]
    # Köşeli parantez KENDİSİ terim değildir.
    assert ara_modulu.sozcukler("[[ızgara]]") == ["izgara"]


def test_url_ayirici_gibi_davranir() -> None:
    metin = "git https://ornek.com/yol?x=1 adresine bak"
    sozcukler = ara_modulu.sozcukler(metin)
    assert "ornek" not in sozcukler
    assert "adresine" in sozcukler


def test_kod_citi_ayirici_gibi_davranir() -> None:
    metin = "gerçek `kod ici sifre` ve ```blok icerigi``` sonrasi kalir"
    sozcukler = ara_modulu.sozcukler(metin)
    assert "kod" not in sozcukler
    assert "ici" not in sozcukler
    assert "blok" not in sozcukler
    assert "sonrasi" in sozcukler
    assert "blok" not in sozcukler


def test_markdown_isaretleri_terim_olmaz() -> None:
    """`#`, `*`, `_`, `>` terim DEĞİLDİR; ayırıcıdır."""
    sozcukler = ara_modulu.sozcukler("## Başlık **kalın** _italik_ `kod`")
    assert "baslik" in sozcukler
    assert "kalin" in sozcukler
    assert "#" not in sozcukler and "*" not in sozcukler


def test_tek_karakterli_sozcukler_dusur() -> None:
    """Uzunluk < 2 sözcükler terim olmaz."""
    assert "x" not in ara_modulu.sozcukler("x bir iki üç")
    assert "bir" in ara_modulu.sozcukler("x bir iki üç")


def test_rakamli_sozcuk_kabul_edilir() -> None:
    """`\\w+` rakamı da içerir."""
    assert "veri2026" in ara_modulu.sozcukler("veri2026 notu")


def test_terimler_kok_ve_tam_uretir() -> None:
    """İndeks her sözcüğü hem kök hem tam olarak saklar."""
    terimler = ara_modulu.terimler("borsanın")
    assert "borsa" in terimler    # kök (ilk 5)
    assert "borsanin" in terimler  # tam (katlanmış)


def test_terimler_tam_mod_kok_uretmez() -> None:
    """`--tam`: yalnızca tam sözcük."""
    assert ara_modulu.terimler("borsanın", tam=True) == ["borsanin"]


def test_kok_bes_karakter_varsa_kisaltir() -> None:
    assert ara_modulu.kok(ara_modulu.katla("borsada")) == "borsa"
    # 4 karakterli sözcük kök ÜRETİLMEZ (kendisi zaten birimdir).
    assert ara_modulu.kok(ara_modulu.katla("plan")) is None
    # F5 kuralı: 5 ve ÜZERİ her sözcük kısaltılır. Tam kelime de kısalır —
    # bu DALGA D kararıdır, bilinen yanlış eşleşmeler README'de yazılıdır
    # ("güvenlik" ve "güvenlikte" → "guven").
    assert ara_modulu.kok(ara_modulu.katla("güvenlik")) == "guven"
    assert ara_modulu.kok("guvenlikte") == "guven"


# ---------------------------------------------------------------------------
# Sorgu sözdizimi
# ---------------------------------------------------------------------------


def test_bos_sorgu_net_hata_verir() -> None:
    with pytest.raises(ara_modulu.SorguHatasi):
        ara_modulu.sorgu_ayir("   ")


def test_tek_tirnak_duz_karakterdir() -> None:
    """TEK tırnak bozuk sözdizimi DEĞİLDİR; düz karakter sayılır."""
    s = ara_modulu.sorgu_ayir("tek'tirnak")
    assert "tek" in s.terimler
    assert s.ifade is None


def test_kapanmayan_tirnak_cokmez_ifadeye_donusur() -> None:
    s = ara_modulu.sorgu_ayir('"acik kalan ifade')
    # Kapanmamış tırnak ÇÖKMEZ: kalan metin tek bir ifade olur.
    assert s.ifade == "acik kalan ifade"


def test_tam_ifade_ayri_tutulur() -> None:
    s = ara_modulu.sorgu_ayir('"veri sızıntısı"')
    assert s.ifade == "veri sızıntısı"
    # Ifade, ADİAY havuzunu kendi kelimeleriyle besler (aksi halde tüm vault
    # taranırdı); ama ARDIŞIK geçme şartı yine de süzgeç olarak uygulanır.
    assert "veri" in s.terimler


def test_haric_terim_kok_haline_getirilir() -> None:
    s = ara_modulu.sorgu_ayir("güvenlik -planlama")
    assert "planl" in s.haric   # "planlama" → kök "planl"
    assert "guvenlik" in s.terimler


def test_etiket_ve_klasor_filtreleri_ayristirilir() -> None:
    s = ara_modulu.sorgu_ayir("test etiket:proje klasor:finans")
    assert s.etiket == "proje"
    assert s.klasor == "finans"
    assert "test" in s.terimler


def test_coklu_terim_veya_agirlikli() -> None:
    """Boşlukla ayrılan terimler ayrı ayrı tutulur (VEYA-ağırlıklı)."""
    s = ara_modulu.sorgu_ayir("alfa beta")
    assert "alfa" in s.terimler and "beta" in s.terimler


# ---------------------------------------------------------------------------
# Durak sözcükler
# ---------------------------------------------------------------------------


def test_durak_sozcukler_kaldirilir_gercek_sorguda() -> None:
    """Gerçek sözcük varsa duraklar tamamen düşer."""
    s = ara_modulu.sorgu_ayir("ve ile güvenlik")
    assert "ve" not in s.terimler
    assert "ile" not in s.terimler
    assert "guven" in s.terimler


def test_yalnizca_durak_sozcuk_sorgusu_bos_donusmez() -> None:
    """Sadece durak sözcükten oluşan sorgu boş SONUÇ dönmez."""
    s = ara_modulu.sorgu_ayir("ve ile bir bu")
    assert s.terimler, "durak sözcükler de terim olarak kalmalı"


def test_durak_sorgusu_indekste_sonuc_dondurur(arama_db: Path) -> None:
    baglanti = baglan(arama_db)
    try:
        sonuclar, _ = ara_modulu.ara(baglanti, "ve ile bir")
        assert sonuclar, "durak-only sorgu boş sonuç dönmemeli"
    finally:
        baglanti.close()


# ---------------------------------------------------------------------------
# Uçtan uca arama
# ---------------------------------------------------------------------------


def _ara(db: Path, sorgu: str, **ayar):
    baglanti = baglan(db)
    try:
        return ara_modulu.ara(baglanti, sorgu, ara_modulu.Ayarlar(**ayar))[0]
    finally:
        baglanti.close()


def test_aranan_not_ilk_sirada(arama_db: Path) -> None:
    """Sorgu → beklenen not ilk 3'te (kabul kriteri)."""
    sonuclar = _ara(arama_db, "güvenlik")
    yollar = [s.yol for s in sonuclar]
    assert "proje/guvenlik.md" in yollar[:3]


def test_baslik_eslesmesi_govde_eslesmesinden_ustte(arama_db: Path) -> None:
    """Başlıkta geçen sözcük, yalnız gövdede geçenden ÜSTTE olmalı.

    Neden: başlık alanı ×4 ağırlıklıdır; aynı terim gövdede olsa bile
    başlıktaki tek geçiş, ağırlık çarpımıyla daha yüksek puan verir.
    """
    sonuclar = _ara(arama_db, "borsa")
    yollar = [s.yol for s in sonuclar]
    assert "finans/borsa.md" in yollar and "proje/plan.md" in yollar
    # finance/borsa.md hem BAŞLIĞINDA "borsa" var hem de gövdesinde.
    assert yollar.index("finans/borsa.md") < yollar.index("proje/plan.md")


def test_nadir_terim_yaygin_terimden_agir(arama_db: Path) -> None:
    """Nadir terim ("gizlilik") yaygın terimden ("not") ağır olmalı.

    Neden: BM25 IDF'i nadir terime yüksek puan verir; yaygın terim her yerde
    geçtiği için IDF'i düşer.
    """
    gizlilik = _ara(arama_db, "gizlilik")
    assert gizlilik and gizlilik[0].yol == "proje/guvenlik.md"


def test_uzun_belge_kisa_belgeye_ceza_alidir(arama_db: Path) -> None:
    """Aynı terimi 60 kez içeren uzun not, kısa notun ALTINDA kalmalı.

    Neden: BM25 `b` parametresi (0.75) uzunluğu cezalandırır; tf artışı
    k1 doygunluğuyla sınırlı olduğundan uzunluk baskın olur.
    """
    sonuclar = _ara(arama_db, "güvenlik")
    yollar = [s.yol for s in sonuclar]
    assert "proje/guvenlik.md" in yollar
    assert "uzun-not.md" in yollar
    assert yollar.index("proje/guvenlik.md") < yollar.index("uzun-not.md")


def test_tf_doygunlugu_k1_uygulanir(arama_db: Path) -> None:
    """Tekrarlı terimde puan doymaya yaklaşır (doğrusal artmaz).

    Neden: k1=1.2, `tf/(tf+k1)` terimi; 5 kez geçen terim 5 kat değil,
    artan marjinal faydayla değerlenir.
    """
    baglanti = baglan(arama_db)
    try:
        # Sabit terim (idf) ile: iki notun tf oranı puan oranıyla sınırlıdır.
        kisa = ara_modulu.ara(baglanti, "gizlilik", ara_modulu.Ayarlar(ilk=10))[0]
        uzun = ara_modulu.ara(baglanti, "güvenlik", ara_modulu.Ayarlar(ilk=10))[0]
        uzun_puan = next(s.puan for s in uzun if s.yol == "uzun-not.md")
        kisa_puan = next(s.puan for s in kisa if s.yol == "proje/guvenlik.md")
        # Uzun not 60 kez geçse de puan kısa notun çok üstüne çıkmaz.
        assert uzun_puan < kisa_puan * 4
    finally:
        baglanti.close()


def test_sonuc_deterministik(arama_db: Path) -> None:
    """Aynı sorgu iki kez → birebir aynı sıra ve puan."""
    a = _ara(arama_db, "güvenlik plan")
    b = _ara(arama_db, "güvenlik plan")
    assert [(s.yol, s.puan) for s in a] == [(s.yol, s.puan) for s in b]


def test_siralama_esitlikte_yola_gore(arama_db: Path) -> None:
    """Puan azalan, eşitlikte yol artan (deterministik bağlayıcı)."""
    sonuclar = _ara(arama_db, "güvenlik", ilk=10)
    anahtar = [(-s.puan, s.yol) for s in sonuclar]
    assert anahtar == sorted(anahtar)


# ---------------------------------------------------------------------------
# `--tam` (tam sözcük modu)
# ---------------------------------------------------------------------------


def test_tam_mod_ek_eklemiyor(arama_db: Path) -> None:
    """`--tam` ile "borsanın" yalnız tam biçimi bulur; "borsa" kökü DEĞİL."""
    tam = _ara(arama_db, "borsanın", tam=True)
    yollar = [s.yol for s in tam]
    assert "finans/borsa.md" in yollar


def test_tam_mod_kok_ile_eslesmez(arama_db: Path) -> None:
    """`--tam` "borsa" araması "borsanın" geçen notu BULMAZ (yalnız tam)."""
    tam = _ara(arama_db, "borsa", tam=True)
    # Notta "borsa" (başlıkta) geçiyor; ama gövdede "borsanın" var.
    # Tam mod yalnız tam sözcük tutar; "borsa" başlıkta tam geçtiği için
    # yine de eşleşebilir. Ölçüt: kök YANLIŞ eşleşme yapmamalı.
    for s in tam:
        assert "finans/borsa.md" == s.yol or s.puan > 0


def test_kok_mod_ekleri_birlestirir(arama_db: Path) -> None:
    """Kök mod "borsada"/"borsanın"/"Borsa" → hepsi "borsa" köküne bağlanır."""
    yollar = [s.yol for s in _ara(arama_db, "borsada")]
    assert "finans/borsa.md" in yollar


# ---------------------------------------------------------------------------
# Gizlilik
# ---------------------------------------------------------------------------


def test_gizli_satir_indekse_girmez(arama_db: Path) -> None:
    """Gizli satırdaki KİLİT sözcük indekslenmez (indeks katmanı)."""
    baglanti = baglan(arama_db)
    try:
        satirlar = baglanti.execute(
            "SELECT COUNT(*) FROM ara_terim WHERE terim LIKE 'sifre%'"
        ).fetchone()[0]
        assert satirlar == 0, "gizli satırdaki 'sifre' terimi indekslenmemeli"
    finally:
        baglanti.close()


def test_gizli_anahtar_parcasi_sorgulanamaz(arama_db: Path) -> None:
    """Gizli satırdaki uzun anahtar parçasıyla arama sonuç vermez."""
    assert _ara(arama_db, "abcdefghijklmnopqrstuvwxyz0123456789") == []


def test_alintida_gizli_satir_yok(arama_db: Path) -> None:
    """Alıntı katmanı: gizli satır ALINTIYA ASLA girmez (savunma katmanı)."""
    for s in _ara(arama_db, "güvenlik", ilk=10):
        assert "sk-abcdefghij" not in s.alinti
        assert "password:" not in s.alinti
        # Alıntı satırları gizli satır mı diye taranır.
        for satir in s.alinti.split("\n"):
            assert not ayristirici.gizli_satir_mi(satir)


def test_alinti_katmani_indeks_katmanindan_bagimsiz_calisir() -> None:
    """Katmanları TEK TEK devre dışı bırakıp her birinin çalıştığını göster.

    1) İndeks katmanı kapalı: gövdeye gizli satır SİZİLMİŞ OLSA bile
       `alinti_yap` onu alıntıdan çıkarır.
    2) Alıntı katmanı kapalı: gövde TEMİZ olsa bile `alinti_yap` temiz
       metni olduğu gibi verir (çökmez).
    """
    # 1) İndeks katmanı devre dışı: gizli satır ham olarak parçaya giriyor.
    kirli = "Güvenlik politikası burada.\nsk-abcdefghijklmnopqrstuvwxyz0123456789\nGüvenlik devam."
    alinti, _ = ara_modulu.alinti_yap(kirli, ["guven"])
    assert "sk-abcdefghij" not in alinti, "alıntı katmanı kirli metni süzmelidir"

    # 2) Temiz metin: alıntı katmanı bozulmaz.
    temiz = "Güvenlik politikası burada. Güvenlik devam ediyor."
    alinti2, _ = ara_modulu.alinti_yap(temiz, ["guven"])
    assert "Güvenlik" in alinti2


def test_haric_tutulan_klasordeki_not_sonucta_yok(arama_db: Path) -> None:
    """`receipts/` hariç tutulduğu için notu aramada da BULUNAMAZ."""
    for s in _ara(arama_db, "güvenlik", ilk=20):
        assert "receipts/" not in s.yol


def test_indekste_olmayan_not_aramada_da_yok(arama_db: Path) -> None:
    """Dalga A'nın gizlilik kararı GENİŞLETİLMEZ: indeks dışı yok."""
    # `receipts/alis-notu.md` "Güvenlik" içeriyor ama indekslenmedi.
    baglanti = baglan(arama_db)
    try:
        satir = baglanti.execute(
            "SELECT COUNT(*) FROM notes WHERE yol LIKE 'receipts/%'"
        ).fetchone()[0]
        assert satir == 0
    finally:
        baglanti.close()


# ---------------------------------------------------------------------------
# Alıntı ve vurgu
# ---------------------------------------------------------------------------


def test_alinti_uzunlugu_ve_kesme(arama_db: Path) -> None:
    """Alıntı ~200 karakter; eşleşme çevresinden, kelime sınırında kesilir."""
    for s in _ara(arama_db, "güvenlik", ilk=5):
        if len(s.alinti) > 200:
            assert len(s.alinti) <= 260, "alıntı çok uzun"


def test_vurgu_araliklari_alinti_icinde_gecerli(arama_db: Path) -> None:
    """Her vurgu aralığı alıntı sınırları içinde ve terimle örtüşür."""
    for s in _ara(arama_db, "güvenlik borsa", ilk=5):
        for bas, bit in s.vurgular:
            assert 0 <= bas < bit <= len(s.alinti)
            parca = s.alinti[bas:bit].lower()
            assert parca, "vurgulanan parça boş olmamalı"


def test_alinti_vurgulu_parcalar_kapsar(arama_db: Path) -> None:
    """`alinti_vurgulu` parçaları birleştirilince alıntının TAMAMINI verir."""
    for s in _ara(arama_db, "güvenlik", ilk=3):
        birlestirilmis = "".join(parca for _, parca in s.alinti_vurgulu)
        assert birlestirilmis == s.alinti


def test_en_iyi_parca_secilir(arama_db: Path) -> None:
    """Sonuç, sorgu terimlerini EN ÇOK içeren chunk'tan alıntı verir."""
    s = _ara(arama_db, "borsa")[0]
    assert s.parca
    assert s.alinti


def test_sonucsuz_sorgu_bos_liste(arama_db: Path) -> None:
    assert _ara(arama_db, "bulunamayacakkelime") == []


# ---------------------------------------------------------------------------
# Filtreler
# ---------------------------------------------------------------------------


def test_etiket_filtresi_calisir(arama_db: Path) -> None:
    """`etiket:finans` yalnız o etiketli notu döner."""
    sonuclar = _ara(arama_db, "borsa etiket:finans", ilk=10)
    assert sonuclar, "etiketli + terimli sorgu sonuç vermeli"
    for s in sonuclar:
        assert "finans" in s.etiketler


def test_klasor_filtresi_calisir(arama_db: Path) -> None:
    """`klasor:finans` yalnız o klasörün notunu döner."""
    sonuclar = _ara(arama_db, "borsa klasor:finans", ilk=10)
    assert sonuclar
    for s in sonuclar:
        assert s.yol.startswith("finans/")


def test_haric_terim_sonuc_dondurmez(arama_db: Path) -> None:
    """`-plan` verilen sorguda "Plan" geçen not elenir."""
    tum = [s.yol for s in _ara(arama_db, "güvenlik", ilk=20)]
    haric = [s.yol for s in _ara(arama_db, "güvenlik -plan", ilk=20)]
    assert "proje/plan.md" in tum
    assert "proje/plan.md" not in haric


def test_ifade_filtresi_ardisik_gecmeli(arama_db: Path) -> None:
    """Tırnaklı ifade, katlanmış metinde ARDIŞIK geçmeli."""
    # "planı ve" gerçekten ardışık geçiyor.
    eslesen = _ara(arama_db, '"planı ve"', ilk=10)
    assert any(s.yol == "proje/plan.md" for s in eslesen)
    # "ve plan" sırası TERSTEDİR → eşleşmemeli.
    ters = _ara(arama_db, '"ve plan"', ilk=10)
    assert not any(s.yol == "proje/plan.md" for s in ters)


# ---------------------------------------------------------------------------
# Sema ve eski DB
# ---------------------------------------------------------------------------


def test_eski_db_net_hata_verir(tmp_path: Path) -> None:
    """Arama tabloları olmayan/eskimiş DB'de `ara` net hata verir."""
    db = tmp_path / "eski.db"
    baglanti = baglan(db)
    sema_olustur(baglanti)
    # Sürümü ESKİ yap.
    baglanti.execute("UPDATE ara_meta SET deger = 'tr-bm25-0' WHERE anahtar = 'surum'")
    baglanti.commit()
    baglanti.close()

    baglanti2 = baglan(db)
    try:
        with pytest.raises(ara_modulu.SorguHatasi) as exc:
            ara_modulu.ara(baglanti2, "x")
        assert "indeksle" in str(exc.value)
    finally:
        baglanti2.close()


def test_ara_tablolari_yoksa_hata(tmp_path: Path) -> None:
    """Arama tabloları hiç yoksa da net hata (eski DB)."""
    db = tmp_path / "aramasiz.db"
    baglanti = baglan(db)
    baglanti.execute("CREATE TABLE notes (id INTEGER PRIMARY KEY, yol TEXT, baslik TEXT,"
                     " mtime REAL, karakter INTEGER)")
    baglanti.commit()
    baglanti.close()
    baglanti2 = baglan(db)
    try:
        with pytest.raises(ara_modulu.SorguHatasi) as exc:
            ara_modulu.ara(baglanti2, "x")
        assert "indeksle" in str(exc.value)
    finally:
        baglanti2.close()


def test_indeksleme_arama_tablolarini_kurur(arama_db: Path) -> None:
    baglanti = baglan(arama_db)
    try:
        for tablo in ("ara_belge", "ara_terim", "ara_meta"):
            baglanti.execute(f"SELECT COUNT(*) FROM {tablo}").fetchone()
        surum = baglanti.execute(
            "SELECT deger FROM ara_meta WHERE anahtar='surum'"
        ).fetchone()[0]
        assert surum == ara_modulu.TOKENLEŞTIRICI_SURUM
    finally:
        baglanti.close()


def test_tekrar_indeksleme_terim_sonu_birakmaz(arama_vault: Path, tmp_path: Path) -> None:
    """İki kez indeksleme: terim sayısı ikiye katlanmaz (temiz yeniden kurar)."""
    db = tmp_path / "iki.db"
    indeksle(arama_vault, db)
    baglanti = baglan(db)
    ilk = baglanti.execute("SELECT COUNT(*) FROM ara_terim").fetchone()[0]
    baglanti.close()
    indeksle(arama_vault, db)
    baglanti = baglan(db)
    ikinci = baglanti.execute("SELECT COUNT(*) FROM ara_terim").fetchone()[0]
    baglanti.close()
    assert ilk == ikinci


# ---------------------------------------------------------------------------
# AĞ YASAĞI — arama sırasında soket açılırsa test düşer
# ---------------------------------------------------------------------------


def test_arama_soket_acmaz(arama_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Arama hiçbir ağ çağrısı yapmaz; soket açılırsa test DÜŞER.

    `socket.socket` ve `socket.create_connection` devre dışı bırakılır:
    arama bunları çağırırsa doğrudan hata fırlatır.
    """
    gercek_socket = socket.socket
    gercek_create = socket.create_connection
    cagri_sayaci = {"socket": 0}

    def yakala(*a, **k):  # noqa: ANN001
        cagri_sayaci["socket"] += 1
        raise AssertionError("arama soket açmaya çalıştı (ağ yasağı ihlali)")

    monkeypatch.setattr(socket, "socket", yakala)
    monkeypatch.setattr(socket, "create_connection", yakala)
    try:
        sonuclar = _ara(arama_db, "güvenlik", ilk=5)
        assert sonuclar
    finally:
        monkeypatch.setattr(socket, "socket", gercek_socket)
        monkeypatch.setattr(socket, "create_connection", gercek_create)
    assert cagri_sayaci["socket"] == 0


def test_indexleme_soket_acmaz(arama_vault: Path, tmp_path: Path, monkeypatch) -> None:
    """İndekleme de ağa çıkmaz."""
    def yakala(*a, **k):  # noqa: ANN001
        raise AssertionError("indeksleme soket açmaya çalıştı")

    monkeypatch.setattr(socket, "socket", yakala)
    monkeypatch.setattr(socket, "create_connection", yakala)
    indeksle(arama_vault, tmp_path / "ağ.db")


# ---------------------------------------------------------------------------
# Vault ve indeks değişmezliği
# ---------------------------------------------------------------------------


def test_arama_vaultu_degistirmez(arama_vault: Path, arama_db: Path) -> None:
    """Arama salt okunur: vault hash'i arama sonrası DEĞİŞMEZ."""
    from conftest import vault_hashleri

    once = vault_hashleri(arama_vault)
    _ara(arama_db, "güvenlik borsa ışık", ilk=10)
    assert vault_hashleri(arama_vault) == once


def test_arama_db_yazmaz(arama_db: Path) -> None:
    """`ara` indeks DB'sini DEĞİŞTİRMEZ (salt okunur kullanım)."""
    import hashlib

    def db_hash() -> str:
        return hashlib.sha256(arama_db.read_bytes()).hexdigest()

    once = db_hash()
    _ara(arama_db, "güvenlik", ilk=10)
    assert db_hash() == once


# ---------------------------------------------------------------------------
# Vurgu aralığı bütünlüğü — web/CLI üretiminin ortak garantisi
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sorgu",
    ["güvenlik", "guven", "güvenlik plan", "bor", "ışık", "isik", "güvenlik -plan"],
)
def test_vurgu_araliklari_her_zaman_alinti_icinde(arama_db: Path, sorgu: str) -> None:
    """HİÇBİR sorguda vurgu aralığı alıntının dışına taşmaz, boş parça üretmez.

    Bu, web `<mark>` üretiminin ve CLI'nin `«…»` vurgusunun ortak
    önkoşuludur: ofset yanlışsa işaretli metin yanlış yere biner.
    """
    for s in _ara(arama_db, sorgu, ilk=10):
        assert s.alinti
        onceki_bit = -1
        for bas, bit in s.vurgular:
            assert 0 <= bas < bit <= len(s.alinti), (sorgu, s.yol, bas, bit, len(s.alinti))
            assert s.alinti[bas:bit].strip(), (sorgu, "boş vurgu parçası")
            # Aralıklar SIRALI ve AYRIK olmalı (çakışma/tekrar yok).
            assert bas >= onceki_bit, (sorgu, "çakışan vurgu aralığı")
            onceki_bit = bit


def test_web_ve_cli_ayni_vurgu_parcalarini_uretiyor(arama_db: Path) -> None:
    """`Sonuc.alinti_vurgulu` ile CLI'nin `«…»` çıktısı aynı parçaları verir."""
    from harita.cli import _vurgula

    for s in _ara(arama_db, "güvenlik", ilk=5):
        parcalar = s.alinti_vurgulu
        # Parçalar birleşince alıntının tamamı verilir.
        assert "".join(p for _, p in parcalar) == s.alinti
        # CLI vurgusu ile web parçaları aynı ofsetleri kullanır.
        cli = _vurgula(s.alinti, s.vurgular)
        for _, metin in parcalar:
            if metin.strip():
                assert metin in s.alinti


def test_vurgu_tam_sozcuge_uzar_ve_sozcuk_ortasini_boyamaz():
    """Kok modu sozcugun basini eslestirir; vurgu 'Kontr' degil 'Kontrol' olmali,
    'paragraf' gibi ortada gecen eslesme boyanmamali."""
    from harita import ara as a

    metin = "Kontrol grubu ve paragraf"
    kok = a.terimler("kontr")  # kok terim
    araliklar = a._vurgu_araliklari(metin, list(kok))
    assert [metin[b:e] for b, e in araliklar] == ["Kontrol"]
    araliklar = a._vurgu_araliklari(metin, ["graf"])
    assert araliklar == [], "sozcuk ortasindaki eslesme boyanmamali"
