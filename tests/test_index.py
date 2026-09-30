"""İndeks testleri: taramama, bağlantı çözümleme, yeniden indeksleme, sorgular."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from conftest import yaz

from harita import index as indeks_modulu
from harita.index import (
    VARSAYILAN_HARIC_TUTULANLAR,
    baglan,
    cozucu_kur,
    etiket_sikligi,
    harici_tutulmus,
    indeksle,
    kirik_linkler,
    linki_coz,
    not_ozet,
    notlari_tara,
    yetim_notlar,
)
from harita.parse import Not, normalize


# ---------------------------------------------------------------------------
# Tarama ve hariç tutma
# ---------------------------------------------------------------------------


def test_vault_taranir_ve_sirali(mini_vault: Path) -> None:
    bulunan = notlari_tara(mini_vault)
    yollar = [goreli.as_posix() for _, goreli in bulunan]
    assert yollar == sorted(yollar)
    assert "bozuk-frontmatter.md" in yollar
    assert "🧠 Bilgi/ızgara-notu.md" in yollar


def test_haric_tutulanlar_varsayilan(tmp_path: Path) -> None:
    kok = tmp_path / "v"
    kok.mkdir()
    for klasor in VARSAYILAN_HARIC_TUTULANLAR:
        yol = kok / klasor / "not.md"
        yol.parent.mkdir(parents=True, exist_ok=True)
        yol.write_text("# gizli\n", encoding="utf-8")
    yaz(kok, "gorunur.md", "# var\n")
    yaz(kok, "📥 000-Inbox/diger.md", "# inbox ama Dump degil\n")

    yollar = [g.as_posix() for _, g in notlari_tara(kok)]
    assert yollar == ["gorunur.md", "📥 000-Inbox/diger.md"]


def test_harici_tutulmus_bilesen_ve_onek_kurali(tmp_path: Path) -> None:
    kok = tmp_path / "v"
    kok.mkdir()
    ic = kok / "alt" / "node_modules"
    ic.mkdir(parents=True)
    # Bir kural herhangi bir yol bileşeniyle eşleşiyorsa tutulur.
    assert harici_tutulmus(ic, kok, ("node_modules",))
    assert harici_tutulmus(ic / "paket.md", kok, ("node_modules",))
    # Önekli kural (📥 000-Inbox/Dump) bileşen bileşen eşleşir.
    assert harici_tutulmus(kok / "📥 000-Inbox" / "Dump" / "a.md", kok, ("📥 000-Inbox/Dump",))
    assert not harici_tutulmus(kok / "📥 000-Inbox" / "başka" / "a.md", kok, ("📥 000-Inbox/Dump",))
    assert not harici_tutulmus(kok / "node_modules_ozel" / "a.md", kok, ("node_modules",))
    assert not harici_tutulmus(kok / "a.md", kok, ("node_modules",))


def test_sadece_md_dosyalari(tmp_path: Path) -> None:
    kok = tmp_path / "v"
    kok.mkdir()
    yaz(kok, "not.md", "# md\n")
    (kok / "resim.txt").write_text("metin", encoding="utf-8")
    (kok / "veri.json").write_text("{}", encoding="utf-8")
    assert [g.name for _, g in notlari_tara(kok)] == ["not.md"]


# ---------------------------------------------------------------------------
# Bağlantı çözümleme
# ---------------------------------------------------------------------------


def _kayit(id_: int, yol: str, *anahtarlar: str):
    return indeks_modulu.Kayit(
        id=id_,
        yol=Path(yol),
        anahtarlar=[("ad", normalize(Path(yol).stem)), ("baslik", normalize(yol))] + list(anahtarlar),
    )


def test_cozumleme_dosya_adina_gore() -> None:
    coz = cozucu_kur([_kayit(1, "a/hedef.md")])
    assert linki_coz("hedef", coz).id == 1
    assert linki_coz("HEDEF", coz).id == 1
    assert linki_coz("hedef.md", coz).id == 1


def test_cozumleme_turkce_buyuk_kucuk_duyarsiz() -> None:
    coz = cozucu_kur([_kayit(1, "İŞ Rehberi.md")])
    assert linki_coz("iş rehberi", coz).id == 1
    assert linki_coz("İŞ REHBERİ", coz).id == 1


def test_cozumleme_basliga_gore() -> None:
    coz = cozucu_kur([indeks_modulu.Kayit(1, Path("a/dosya.md"), [("baslik", normalize("Özel Başlık"))])])
    assert linki_coz("Özel Başlık", coz).id == 1
    assert linki_coz("özel başlık", coz).id == 1


def test_cozumleme_takma_ada_gore() -> None:
    coz = cozucu_kur(
        [indeks_modulu.Kayit(1, Path("a/dosya.md"), [("takma_ad", normalize("kısa takma"))])]
    )
    assert linki_coz("kısa takma", coz).id == 1
    assert linki_coz("KISA TAKMA", coz).id == 1


def test_cozumleme_yolun_son_parcasi() -> None:
    """`[[klasör/not]]` — yolun son parçası eşleşmeli."""
    coz = cozucu_kur([_kayit(1, "derin/klasor/not.md")])
    assert linki_coz("klasor/not", coz).id == 1
    assert linki_coz("başka-klasor/not", coz).id == 1


def test_cozumleme_yol_yalnizca_son_parcayla_calisir() -> None:
    coz = cozucu_kur([_kayit(1, "gercek/klasor/not.md")])
    assert linki_coz("başka/not", coz).id == 1


def test_coklu_eslesmede_en_kisa_yol_kazanir() -> None:
    coz = cozucu_kur(
        [
            _kayit(1, "cok/derin/alt/klasor/not.md"),
            _kayit(2, "k/not.md"),
            _kayit(3, "not.md"),
        ]
    )
    # Üçü de "not" anahtarında: en kısa yol (not.md) kazanır.
    assert linki_coz("not", coz).id == 3


def test_yol_bicimli_link_son_parcayla_cozulur() -> None:
    """`[[klasor/not]]` → yolun son parçası "not" → anahtar sırasıyla en kısa yol."""
    coz = cozucu_kur([_kayit(1, "cok/derin/alt/klasor/not.md"), _kayit(3, "not.md")])
    assert linki_coz("klasor/not", coz).id == 3


def test_yol_bicimli_link_tam_yolu_bilir() -> None:
    """`[[klasor/not]]` yalnızca son parçaya bakar, tam yol zorunlu değildir."""
    coz = cozucu_kur([_kayit(1, "cok/derin/alt/klasor/not.md")])
    assert linki_coz("klasor/not", coz).id == 1


def test_yol_bicimli_link_yedek_arama_yapmaz() -> None:
    """Son parça tutmazsa yol biçimli link, yedek başlık/takma ad aramaz."""
    coz = cozucu_kur(
        [indeks_modulu.Kayit(1, Path("a/başka.md"), [("takma_ad", normalize("klasor/not"))])]
    )
    assert linki_coz("klasor/not", coz) is None


def test_yol_ile_ad_ayni_anahtara_girerse_en_kisa_yol_kazanir() -> None:
    """`[[k/not]]` yol biçimi de "not" anahtarına düşer; en kısa yol yine kazanır."""
    coz = cozucu_kur([_kayit(2, "k/not.md"), _kayit(3, "not.md")])
    assert linki_coz("k/not", coz).id == 3


def test_coklu_eslesme_deterministik() -> None:
    """Aynı derinlikte iki eşleşme → yol sırasıyla belirlenir."""
    kayitlar = [_kayit(1, "bbb/not.md"), _kayit(2, "aaa/not.md")]
    for _ in range(5):
        coz = cozucu_kur(list(kayitlar))
        assert linki_coz("not", coz).id == 2


def test_ad_tutarliligi_baslik_ve_takma_ada_yenilir() -> None:
    """Aynı anahtar 'ad' ve 'baslik' türlerinde: 'ad' öncelikli kazanır.

    Kayıtlar gerçek kurucudan geçer; 'ad' eşleşmesi daha derin bir yolda
    olsa bile öncelik sırası derinlikten önce geldiği için dosya adı kazanır.
    """
    coz = cozucu_kur(
        [
            indeks_modulu.Kayit(
                1,
                Path("derin/paylasilan.md"),
                [("ad", normalize("paylasilan")), ("baslik", normalize("başka"))],
            ),
            indeks_modulu.Kayit(
                2,
                Path("a/belirtilen.md"),
                [("ad", normalize("belirtilen")), ("baslik", normalize("paylasilan"))],
            ),
        ]
    )
    assert linki_coz("paylasilan", coz).id == 1


def test_ayni_oncelikte_en_kisa_yol_kazanir() -> None:
    """Aynı öncelikte (iki 'baslik') eşleşme: en kısa yol, sonra alfabetik."""
    coz = cozucu_kur(
        [
            indeks_modulu.Kayit(1, Path("derin/daha/a.md"), [("baslik", normalize("Ortak"))]),
            indeks_modulu.Kayit(2, Path("k/b.md"), [("baslik", normalize("Ortak"))]),
            indeks_modulu.Kayit(3, Path("z/c.md"), [("baslik", normalize("Ortak"))]),
        ]
    )
    assert linki_coz("Ortak", coz).id == 2


def test_cozulemeyen_hedef_kirik() -> None:
    coz = cozucu_kur([_kayit(1, "a/not.md")])
    assert linki_coz("olmayan", coz) is None
    assert linki_coz("", coz) is None
    assert linki_coz("   ", coz) is None


def test_baslikli_link_hedefi_cozulur(mini_vault: Path, tmp_path: Path) -> None:
    """`#başlık` kısmı ayrıştırıcıda kesilir, kalan hedef çözülür."""
    coz = cozucu_kur([_kayit(1, "x/hedef.md")])
    assert linki_coz("hedef", coz).id == 1


# ---------------------------------------------------------------------------
# Tam indeksleme
# ---------------------------------------------------------------------------


def test_indeksleme_temel_sayilar(mini_vault: Path, tmp_path: Path) -> None:
    db = tmp_path / "index.db"
    ozet = indeksle(mini_vault, db)
    assert ozet.notlar == 6
    assert ozet.linkler > 0
    assert ozet.etiketler > 0

    b = baglan(db)
    try:
        notlar = b.execute("SELECT yol, baslik FROM notes ORDER BY yol").fetchall()
        yollar = [y for y, _ in notlar]
        assert "🧠 Bilgi/ızgara-notu.md" in yollar
        # Kırık: bilinmeyen-not
        kirik = {hedef for _, _, hedef in kirik_linkler(b)}
        assert "bilinmeyen-not" in kirik
    finally:
        b.close()


def test_indeksleme_tablolari_dolu(mini_vault: Path, tmp_path: Path) -> None:
    db = tmp_path / "index.db"
    indeksle(mini_vault, db)
    b = baglan(db)
    try:
        for tablo in ("notes", "links", "tags", "aliases", "chunks"):
            adet = b.execute(f"SELECT COUNT(*) FROM {tablo}").fetchone()[0]
            assert adet > 0, f"{tablo} boş"
        # sıra 0'dan başlamalı ve ardışık olmalı
        suralar = [s for (s,) in b.execute("SELECT sira FROM chunks WHERE not_id = 1 ORDER BY sira")]
        assert suralar == list(range(len(suralar)))
    finally:
        b.close()


def test_takma_adli_link_cozulur(mini_vault: Path, tmp_path: Path) -> None:
    """`[[ızgara]]` -> takma adı "ızgara" olan nota çözülmeli."""
    db = tmp_path / "index.db"
    indeksle(mini_vault, db)
    b = baglan(db)
    try:
        satir = b.execute(
            """
            SELECT l.hedef_metin, h.yol FROM links l
            JOIN notes k ON k.id = l.kaynak_id
            LEFT JOIN notes h ON h.id = l.hedef_id
            WHERE l.hedef_metin = 'ızgara'
            """
        ).fetchone()
        assert satir is not None and satir[0] == "ızgara"
        assert satir[1] == "🧠 Bilgi/ızgara-notu.md"
        assert "ızgara" not in {h for _, _, h in kirik_linkler(b)}
    finally:
        b.close()


def test_gomulu_link_tur_olarak_kaydedilir(mini_vault: Path, tmp_path: Path) -> None:
    """Gömülü bağlantı `tur = gomulu` ile link tablosuna girer."""
    db = tmp_path / "index.db"
    indeksle(mini_vault, db)
    b = baglan(db)
    try:
        turler = dict(
            b.execute(
                "SELECT hedef_metin, tur FROM links WHERE kaynak_id = "
                "(SELECT id FROM notes WHERE yol = ?)",
                ("🧠 Bilgi/ızgara-notu.md",),
            ).fetchall()
        )
        assert turler["gömülü-görsel"] == "gomulu"
        assert turler["ızgara-notu"] == "link"
    finally:
        b.close()


def test_coklu_eslesmede_en_kisa_yol(mini_vault: Path, tmp_path: Path) -> None:
    yaz(mini_vault, "a/not.md", "---\ntitle: Not\n---\n# Not\n")
    yaz(mini_vault, "derin/not.md", "---\ntitle: Not\n---\n# Not\n")
    db = tmp_path / "index.db"
    indeksle(mini_vault, db)
    b = baglan(db)
    try:
        cozucu = _cozucu_db(b)
        assert linki_coz("not", cozucu).yol.as_posix() == "a/not.md"
    finally:
        b.close()


def _cozucu_db(b: sqlite3.Connection):
    kayitlar = []
    for nid, yol, baslik in b.execute("SELECT id, yol, baslik FROM notes ORDER BY id"):
        kayitlar.append(
            indeks_modulu.Kayit(
                nid,
                Path(yol),
                [("ad", normalize(Path(yol).stem)), ("baslik", normalize(baslik))],
            )
        )
    for nid, alias in b.execute("SELECT not_id, alias FROM aliases"):
        for k in kayitlar:
            if k.id == nid:
                k.anahtarlar.append(("takma_ad", normalize(alias)))
                break
    return cozucu_kur(kayitlar)


def test_kod_ici_sahte_link_kirik_sayilmaz(mini_vault: Path, tmp_path: Path) -> None:
    db = tmp_path / "index.db"
    indeksle(mini_vault, db)
    b = baglan(db)
    try:
        kirik = {hedef for _, _, hedef in kirik_linkler(b)}
        assert "sahte-link" not in kirik
        assert "sahte-satir-kod" not in kirik
    finally:
        b.close()


def test_kod_ici_sahte_etiket_toplanmaz(mini_vault: Path, tmp_path: Path) -> None:
    db = tmp_path / "index.db"
    indeksle(mini_vault, db)
    b = baglan(db)
    try:
        etiketler = {e for e, _ in etiket_sikligi(b)}
        assert "sahte-etiket" not in etiketler
        assert "gizlilik" in etiketler
    finally:
        b.close()


def test_sir_satiri_chunks_a_girmez(mini_vault: Path, tmp_path: Path) -> None:
    db = tmp_path / "index.db"
    indeksle(mini_vault, db)
    b = baglan(db)
    try:
        tum = " ".join(m for (m,) in b.execute("SELECT metin FROM chunks"))
        assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in tum
        assert "password: gizli-sifre" not in tum
        assert "BEGIN RSA PRIVATE KEY" not in tum
        # Süzülmeyen güvenli satır korunur.
        assert "flask-uygulama-adi" in tum
    finally:
        b.close()


# ---------------------------------------------------------------------------
# Yeniden indeksleme temizliği
# ---------------------------------------------------------------------------


def test_yeniden_indeksleme_cesoaltmaz(mini_vault: Path, tmp_path: Path) -> None:
    db = tmp_path / "index.db"
    ilk = indeksle(mini_vault, db)
    ikinci = indeksle(mini_vault, db)
    assert ilk.notlar == ikinci.notlar
    assert ilk.linkler == ikinci.linkler
    assert ilk.etiketler == ikinci.etiketler
    b = baglan(db)
    try:
        assert b.execute("SELECT COUNT(*) FROM notes").fetchone()[0] == ilk.notlar
        assert b.execute("SELECT COUNT(*) FROM links").fetchone()[0] == ilk.linkler
    finally:
        b.close()


def test_silin_dosya_db_den_gider(tmp_path: Path) -> None:
    vault = tmp_path / "v"
    vault.mkdir()
    yaz(vault, "a.md", "# A\n[[b]]\n")
    yaz(vault, "b.md", "# B\n")
    db = tmp_path / "index.db"
    indeksle(vault, db)

    (vault / "b.md").unlink()
    yaz(vault, "c.md", "# C\n")
    ozet = indeksle(vault, db)

    b = baglan(db)
    try:
        yollar = {y for (y,) in b.execute("SELECT yol FROM notes")}
        assert yollar == {"a.md", "c.md"}
        # b.md'e olan link artık kırık olmalı
        assert "b" in {h for _, _, h in kirik_linkler(b)}
        assert ozet.kirik_linkler == 1
        # b.md'in etiketleri de gitmeli
        assert b.execute("SELECT COUNT(*) FROM aliases").fetchone()[0] == 0
    finally:
        b.close()


def test_guncellenen_dosya_eski_satirlari_silmez_ekler(tmp_path: Path) -> None:
    vault = tmp_path / "v"
    vault.mkdir()
    yaz(vault, "a.md", "# A\n[[eski]]\n")
    yaz(vault, "eski.md", "# Eski\n")
    db = tmp_path / "index.db"
    indeksle(vault, db)

    yaz(vault, "a.md", "# A\n[[yeni]]\n")
    yaz(vault, "yeni.md", "# Yeni\n")
    indeksle(vault, db)

    b = baglan(db)
    try:
        hedefler = {h for (h,) in b.execute("SELECT hedef_metin FROM links")}
        assert hedefler == {"yeni"}
    finally:
        b.close()


# ---------------------------------------------------------------------------
# Sorgular
# ---------------------------------------------------------------------------


def test_yetim_notlar(mini_vault: Path, tmp_path: Path) -> None:
    db = tmp_path / "index.db"
    indeksle(mini_vault, db)
    b = baglan(db)
    try:
        yollar = {y for y, _ in yetim_notlar(b)}
        # gizlilik-sırları.md ne link alıyor ne veriyor
        assert "gizlilik-sırları.md" in yollar
        # ızgara-notu.md hem link veriyor hem alıyor -> yetim değil
        assert "🧠 Bilgi/ızgara-notu.md" not in yollar
    finally:
        b.close()


def test_etiket_sikligi_sirali(mini_vault: Path, tmp_path: Path) -> None:
    db = tmp_path / "index.db"
    indeksle(mini_vault, db)
    b = baglan(db)
    try:
        hepsi = etiket_sikligi(b)
        adetler = [a for _, a in hepsi]
        assert adetler == sorted(adetler, reverse=True)
        assert etiket_sikligi(b, 2) == hepsi[:2]
    finally:
        b.close()


def test_not_ozet(mini_vault: Path, tmp_path: Path) -> None:
    db = tmp_path / "index.db"
    indeksle(mini_vault, db)
    b = baglan(db)
    try:
        nid = b.execute("SELECT id FROM notes WHERE yol = ?", ("ozet.md",)).fetchone()[0]
        ozet = not_ozet(b, nid)
        assert ozet["yol"] == "ozet.md"
        assert len(ozet["linkler"]) == 2
        assert not_ozet(b, 99999) == {}
    finally:
        b.close()


# ---------------------------------------------------------------------------
# Veritabanı yolu
# ---------------------------------------------------------------------------


def test_harita_db_ortam_degiskeni(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    hedef = tmp_path / "ortam.db"
    monkeypatch.setenv("HARITA_DB", str(hedef))
    assert indeks_modulu.varsayilan_db() == hedef


def test_varsayilan_db_ev_dizini(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HARITA_DB", raising=False)
    assert indeks_modulu.varsayilan_db() == Path.home() / ".harita" / "harita.db"


def test_db_dosyasi_olusturulur(mini_vault: Path, tmp_path: Path) -> None:
    db = tmp_path / "yeni" / "alt" / "index.db"
    indeksle(mini_vault, db)
    assert db.exists()


# ---------------------------------------------------------------------------
# Not veri sınıfı
# ---------------------------------------------------------------------------


def test_not_dataclass_varsayilanlar() -> None:
    not_ = Not(yol=Path("a.md"), baslik="A", govde="g", mtime=0.0, karakter=1)
    assert not_.takma_adlar == [] and not_.etiketler == [] and not_.linkler == []
    assert not_.suzulmus_satir == 0
