"""Ayrıştırıcı testleri: frontmatter, başlık, takma ad, etiket, link, gizlilik."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from conftest import yaz

from harita.parse import (
    GIZLI_DESENLER,
    gizli_satir_mi,
    ilk_baslik,
    kod_bloklari_ve_satir_kodu,
    linkleri_cikar,
    normalize,
    not_ayristir,
    parca_bol,
)


# ---------------------------------------------------------------------------
# Frontmatter
# ---------------------------------------------------------------------------


def test_frontmatter_temel_alanlar(tmp_path: Path) -> None:
    yaz(tmp_path, "a.md", "---\ntitle: Başlık\n---\n\n# ATL Başlığı\n\nGövde.\n")
    not_ = not_ayristir(tmp_path / "a.md", tmp_path)
    assert not_.baslik == "Başlık"
    assert "title" not in not_.govde
    assert "Gövde." in not_.govde


def test_baslik_onceligi_frontmatter_ilk_olur(tmp_path: Path) -> None:
    yaz(tmp_path, "a.md", "---\ntitle: FM Başlık\n---\n# ATL Başlığı\n")
    assert not_ayristir(tmp_path / "a.md", tmp_path).baslik == "FM Başlık"


def test_baslik_frontmatter_yoksa_atl_basligi(tmp_path: Path) -> None:
    yaz(tmp_path, "a.md", "# ATL Başlığı\n\nmetin\n")
    assert not_ayristir(tmp_path / "a.md", tmp_path).baslik == "ATL Başlığı"


def test_baslik_hicbiri_yoksa_dosya_adi_uzantisiz(tmp_path: Path) -> None:
    yaz(tmp_path, "ızgara-notu.md", "sadece metin\n")
    assert not_ayristir(tmp_path / "ızgara-notu.md", tmp_path).baslik == "ızgara-notu"


def test_frontmatter_yoksa_tum_govde(tmp_path: Path) -> None:
    icerik = "---\nbu bir başlık değil\n\n# Başka\n"
    yaz(tmp_path, "a.md", icerik)
    not_ = not_ayristir(tmp_path / "a.md", tmp_path)
    assert not_.baslik == "Başka"
    assert not_.govde.startswith("---")


def test_bozuk_frontmatter_cokmez(tmp_path: Path) -> None:
    """Kapanış `---` yoksa çökmez, tüm metin gövdedir."""
    icerik = "---\ntitle: Kapanmadi\n\n# Gövde Başlığı\n[[bir-not]]\n"
    yaz(tmp_path, "a.md", icerik)
    not_ = not_ayristir(tmp_path / "a.md", tmp_path)
    assert "[[bir-not]]" in not_.govde
    assert not_.baslik == "Gövde Başlığı"


def test_tampon_dongusu_yok_etiket_listesi_kapanmaz(tmp_path: Path) -> None:
    """`key: []` içeren bir frontmatter sonsuz döngüye girmemeli (regresyon)."""
    icerik = "---\nname: ajan\nmcpServers: []\nskills: []\n---\n\n# Gövde\n"
    yaz(tmp_path, "a.md", icerik)
    not_ = not_ayristir(tmp_path / "a.md", tmp_path)
    assert not_.baslik == "Gövde"


def test_blok_listesi_satir_ici_degil(tmp_path: Path) -> None:
    icerik = "---\ntags:\n  - birinci\n  - \"ikinci\"\naliases:\n  - takma\n---\n"
    yaz(tmp_path, "a.md", icerik)
    not_ = not_ayristir(tmp_path / "a.md", tmp_path)
    assert not_.etiketler == ["birinci", "ikinci"]
    assert not_.takma_adlar == ["takma"]


def test_takma_ad_tirnakli_satir_ici_liste(tmp_path: Path) -> None:
    icerik = '---\naliases: ["ilk takma", \'ikinci, takma\', ucuncu]\n---\n'
    yaz(tmp_path, "a.md", icerik)
    assert not_ayristir(tmp_path / "a.md", tmp_path).takma_adlar == [
        "ilk takma",
        "ikinci, takma",
        "ucuncu",
    ]


def test_mtime_ve_karakter(tmp_path: Path) -> None:
    yaz(tmp_path, "a.md", "---\ntitle: T\n---\n\n12345\n")
    not_ = not_ayristir(tmp_path / "a.md", tmp_path)
    assert not_.mtime > 0
    assert not_.karakter == len(not_.govde)


# ---------------------------------------------------------------------------
# Etiketler
# ---------------------------------------------------------------------------


def test_etiketler_frontmatter_ve_govde_birlestirilir(tmp_path: Path) -> None:
    yaz(tmp_path, "a.md", "---\ntags: [front]\n---\n\n#govde etiketi\n")
    not_ = not_ayristir(tmp_path / "a.md", tmp_path)
    assert not_.etiketler == ["front", "govde"]


def test_etiket_tekrar_sayilmaz(tmp_path: Path) -> None:
    yaz(tmp_path, "a.md", "---\ntags: [a]\n---\n\n#a #a #b\n")
    assert not_ayristir(tmp_path / "a.md", tmp_path).etiketler == ["a", "b"]


def test_turkce_harfli_etiket_gecerli(tmp_path: Path) -> None:
    yaz(tmp_path, "a.md", "#gizlilik ve #çalışma-modeli ile #İŞ-akışı\n")
    assert not_ayristir(tmp_path / "a.md", tmp_path).etiketler == [
        "gizlilik",
        "çalışma-modeli",
        "İŞ-akışı",
    ]


def test_salt_sayi_etiket_degil(tmp_path: Path) -> None:
    yaz(tmp_path, "a.md", "Issue #123 ve #4567 izleniyor.\n")
    assert not_ayristir(tmp_path / "a.md", tmp_path).etiketler == []


def test_baslik_isaretleri_etiket_degil(tmp_path: Path) -> None:
    yaz(tmp_path, "a.md", "# Ana Başlık\n\n## Alt Başlık\n\n### Derin\n")
    assert not_ayristir(tmp_path / "a.md", tmp_path).etiketler == []


def test_kod_blok_ici_etiket_sayilmaz(tmp_path: Path) -> None:
    yaz(tmp_path, "a.md", "```python\n# yorum satiri\nx = 1\n```\n#gizli\n")
    assert not_ayristir(tmp_path / "a.md", tmp_path).etiketler == ["gizli"]


def test_satir_ici_kod_etiketi_sayilmaz(tmp_path: Path) -> None:
    yaz(tmp_path, "a.md", "Kullanım: `#yorum` burada\n#gizli burada\n")
    assert not_ayristir(tmp_path / "a.md", tmp_path).etiketler == ["gizli"]


def test_url_kirintisi_etiket_degil(tmp_path: Path) -> None:
    yaz(tmp_path, "a.md", "Bkz https://ornek.com/sayfa#bolum ve /yol#kisim\n")
    assert not_ayristir(tmp_path / "a.md", tmp_path).etiketler == []


def test_etiket_sondaki_noktalama_dusmez(tmp_path: Path) -> None:
    yaz(tmp_path, "a.md", "Metin #not, devam.\n")
    assert not_ayristir(tmp_path / "a.md", tmp_path).etiketler == ["not"]


def test_etiket_bolme_karakteri_eklenmez(tmp_path: Path) -> None:
    yaz(tmp_path, "a.md", "#ağ-topolojisi/şeması burada\n")
    assert not_ayristir(tmp_path / "a.md", tmp_path).etiketler == ["ağ-topolojisi/şeması"]


# ---------------------------------------------------------------------------
# Linkler
# ---------------------------------------------------------------------------


def test_link_bicimleri(tmp_path: Path) -> None:
    yaz(
        tmp_path,
        "a.md",
        "[[düz]] [[bölüm#başlık]] [[görünen|ad]] [[hepsi#ba|ad]] [[klasör/not]]\n",
    )
    hedefler = [h for h, _ in not_ayristir(tmp_path / "a.md", tmp_path).linkler]
    assert hedefler == ["düz", "bölüm", "görünen", "hepsi", "klasör/not"]


def test_gomulu_link_tur_kaydi(tmp_path: Path) -> None:
    yaz(tmp_path, "a.md", "![[görsel.png]] ve [[not]]\n")
    assert not_ayristir(tmp_path / "a.md", tmp_path).linkler == [
        ("görsel.png", "gomulu"),
        ("not", "link"),
    ]


def test_bos_link_yoksayilir(tmp_path: Path) -> None:
    yaz(tmp_path, "a.md", "[[]] ve [[   ]] ama [[gerçek]] var\n")
    assert not_ayristir(tmp_path / "a.md", tmp_path).linkler == [("gerçek", "link")]


def test_kod_blok_ici_link_sayilmaz(tmp_path: Path) -> None:
    yaz(tmp_path, "a.md", "```\n[[kod-ici]]\n```\n[[gercek]]\n")
    assert not_ayristir(tmp_path / "a.md", tmp_path).linkler == [("gercek", "link")]


def test_satir_ici_kod_linki_sayilmaz(tmp_path: Path) -> None:
    yaz(tmp_path, "a.md", "Yazım: `[[ornek]]` görünümü\n[[gercek]]\n")
    assert not_ayristir(tmp_path / "a.md", tmp_path).linkler == [("gercek", "link")]


def test_kod_bolgesi_araligi_tilde_ve_backtick(tmp_path: Path) -> None:
    metin = "a\n~~~\n[[x]]\n~~~\nb\n```\n[[y]]\n```\nc\n"
    araliklar = kod_bloklari_ve_satir_kodu(metin)
    assert len(araliklar) == 2
    assert linkleri_cikar(metin) == []


def test_kapanmayan_kod_blogu_dosya_sonuna_kadar(tmp_path: Path) -> None:
    yaz(tmp_path, "a.md", "metin\n```\n[[kapanmadi]]\n")
    assert not_ayristir(tmp_path / "a.md", tmp_path).linkler == []


# ---------------------------------------------------------------------------
# Gizlilik
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "satir",
    [
        "anahtar: sk-abcdefghijklmnopqrstuvwxyz1234",
        "password = gizli",
        "PAROLA: gizli",
        "şifre=gizli",
        "api_key: 1234567890abcdef",
        "API-KEY = abcdefgh12345678",
        "token: abcdefgh12345678",
        "secret = abcdefgh12345678",
        "-----BEGIN RSA PRIVATE KEY-----",
    ],
)
def test_gizli_satirlar_tespit_edilir(satir: str) -> None:
    assert gizli_satir_mi(satir)


@pytest.mark.parametrize(
    "satir",
    [
        "flask-uygulama burada geçiyor",
        "risk analizi notu",
        "task-1234 tamamlandı",
        "şifreleme algoritması seçildi",
        "parola gücü ölçümü yapıldı",
        "token sayaç 5 oldu",
    ],
)
def test_gunvenli_satirlar_eles_gecirilir(satir: str) -> None:
    assert not gizli_satir_mi(satir)


def test_sk_deseni_flask_icinde_eslesmez() -> None:
    """Sol sınır olmadan `flask-app-adı-uzun-bir-dizgi` 'sk-' ile eşleşirdi."""
    assert not gizli_satir_mi("[[sosyal-medya-flask-uygulama-projesi]]")


def test_sk_deseni_gercek_anahtari_yakalar() -> None:
    assert gizli_satir_mi('OPENAI=sk-proj-AAAABBBBCCCCDDDDEEEE')
    assert gizli_satir_mi('"sk-aaaaaaaaaaaaaaaaaaaa"')


def test_gizli_satir_govdeye_girmez_ve_sayaci_artar(tmp_path: Path) -> None:
    icerik = "güvenli satır\nsk-abcdefghijklmnopqrstuvwxyz1234\ngüvenli satır 2\n"
    yaz(tmp_path, "a.md", icerik)
    not_ = not_ayristir(tmp_path / "a.md", tmp_path)
    assert not_.suzulmus_satir == 1
    assert "sk-abcdefghijklmnop" not in not_.govde
    assert "güvenli satır" in not_.govde
    # Satır sayısı korunur (chunks konumları bozulmaz).
    assert len(not_.govde.split("\n")) == len(icerik.split("\n"))


def test_gizli_desen_sayisi_dort() -> None:
    assert len(GIZLI_DESENLER) == 4


# ---------------------------------------------------------------------------
# Normalizasyon (Türkçe + Unicode)
# ---------------------------------------------------------------------------


def test_normalize_turkce_i_buyuk_kucuk() -> None:
    # casefold() I→i̇ (birleşik noktalı i) yapar ve ı/i'yi ayırt edemez.
    assert "I".casefold() != "ı".casefold()
    # Doğru davranış: I↔ı ve İ↔i eşleşir, noktasız/noktalı I ayrımı korunur.
    assert normalize("IŞIK") == normalize("ışık")
    assert normalize("İSTANBUL") == normalize("istanbul")
    assert normalize("İŞ") == normalize("iş")
    assert normalize("IS") == normalize("ıs")
    # 'İ' -> 'i̇' üretmez (birleşik nokta birleşmez).
    assert "i̇" not in normalize("İSTANBUL")


def test_normalize_nfc_ve_nfd_ayni() -> None:
    import unicodedata

    nfc = unicodedata.normalize("NFC", "Çalışma")
    nfd = unicodedata.normalize("NFD", "Çalışma")
    assert nfc != nfd  # farklı kod noktaları
    assert normalize(nfc) == normalize(nfd)


def test_normalize_bosluk_karisikligi() -> None:
    assert normalize("çok   boşluk\tve\nsatır") == normalize("çok boşluk ve satır")


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------


def test_parca_bol_paragraf_sinirinda() -> None:
    govde = "\n\n".join("x" * 100 for _ in range(20))
    parcalar = parca_bol(govde, 800)
    assert len(parcalar) > 1
    assert all(len(p) <= 800 for p in parcalar)
    # Paragraf arası boş satırlar hariç hiçbir karakter kaybolmaz.
    assert "".join(parcalar) == "".join(p for p in govde.split("\n\n"))


def test_parca_bol_kisa_govde_tek_parca() -> None:
    assert parca_bol("kısa metin", 800) == ["kısa metin"]


def test_parca_bol_tek_uzun_satiri_kirar() -> None:
    parcalar = parca_bol("y" * 2500, 800)
    assert [len(p) for p in parcalar] == [800, 800, 800, 100]


def test_parca_bol_bos_govde_bos_liste() -> None:
    assert parca_bol("", 800) == []
    assert parca_bol("   \n\n  ", 800) == []


# ---------------------------------------------------------------------------
# Kod bölgesi yardımcısı
# ---------------------------------------------------------------------------


def test_ilk_baslik_yoksa_none() -> None:
    assert ilk_baslik("metin\n## alt\n") is None


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX yol ayracı")
def test_emoji_ve_turkce_dosya_adi(tmp_path: Path) -> None:
    yaz(tmp_path, "🧠 Bilgi/ızgara-şeması.md", "---\ntitle: Şema\n---\n# Şema\n")
    not_ = not_ayristir(tmp_path / "🧠 Bilgi/ızgara-şeması.md", tmp_path)
    assert not_.baslik == "Şema"
    assert not_.yol.as_posix() == "🧠 Bilgi/ızgara-şeması.md"


# ---------------------------------------------------------------------------
# Köşeli parantez içeren hedefler (Dalga B'de bulundu)
# ---------------------------------------------------------------------------


def test_hedef_icinde_kapatici_parantez_bolunmez() -> None:
    r"""`[[<b>x</b>]]` gibi bir hedef İKİ kırık linke bölünmemeli.

    Sınırsız `[^\[\]]*?` deseni `…>` ve boş hedef olmak üzere ikiye ayırıyordu;
    Obsidian'da hedef içinde `]` geçersizdir.
    """
    assert linkleri_cikar("[[<b>hic-boyle-not</b>]]") == [("<b>hic-boyle-not</b>", "link")]


def test_boş_hedef_ve_kapatici_parantez() -> None:
    assert linkleri_cikar("[[]]") == []
    assert linkleri_cikar("[[]] [[]]") == []


def test_gomulu_kapatici_parantezli_hedef() -> None:
    assert linkleri_cikar("![[<b>resim</b>]]") == [("<b>resim</b>", "gomulu")]


def test_normal_linkler_ayri_kalir() -> None:
    """Düzeltme normal wikilinkleri etkilemez."""
    metin = "[[bir]] ve [[iki/üç|d]] ve ![[dort]]"
    assert linkleri_cikar(metin) == [
        ("bir", "link"),
        ("iki/üç", "link"),
        ("dort", "gomulu"),
    ]
