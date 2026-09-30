"""Kuyruk: ekleme, listeleme, FIFO, gecisler, iptal, tekrar, kalicilik, kurtarma."""

import pytest

from orkestra.models import (
    Durum,
    GecersizGecis,
    GecersizGirdi,
    GorevBulunamadi,
    RunSonuc,
    Task,
    utc_simdi,
)
from orkestra.queue import YARIM_KALDI_HATASI, Queue


# -- ekleme / listeleme -------------------------------------------------


def test_ekle_bekliyor_durumunda(kuyruk):
    gorev = kuyruk.ekle("bunny-coder", "kisa bir is")
    assert isinstance(gorev, Task)
    assert gorev.durum is Durum.BEKLIYOR
    assert gorev.id > 0
    assert gorev.ajan == "bunny-coder"


def test_ekle_zaman_damgasi_iso8601(kuyruk):
    gorev = kuyruk.ekle("bunny-coder", "is")
    assert gorev.olusturma == utc_simdi() or gorev.olusturma.endswith("Z")
    assert gorev.olusturma.endswith("Z")


def test_liste_filtresiz_kimlik_sirasi(kuyruk):
    a = kuyruk.ekle("bunny-coder", "birinci")
    b = kuyruk.ekle("nemotron", "ikinci")
    assert [g.id for g in kuyruk.liste()] == [a.id, b.id]


def test_liste_durum_filtresi(kuyruk):
    a = kuyruk.ekle("bunny-coder", "birinci")
    b = kuyruk.ekle("nemotron", "ikinci")
    kuyruk.iptal(b.id)
    assert [g.id for g in kuyruk.liste(Durum.BEKLIYOR)] == [a.id]
    assert [g.id for g in kuyruk.liste("iptal")] == [b.id]
    assert kuyruk.liste("bitti") == []


def test_al_bilinmeyen_kimlik(kuyruk):
    with pytest.raises(GorevBulunamadi):
        kuyruk.al(4242)


def test_var_mi(kuyruk):
    gorev = kuyruk.ekle("bunny-coder", "is")
    assert kuyruk.var_mi(gorev.id)
    assert not kuyruk.var_mi(gorev.id + 999)


def test_onizleme_kisaltir(kuyruk):
    kisa = kuyruk.ekle("bunny-coder", "kisa")
    assert kisa.onizleme == "kisa"
    uzun = kuyruk.ekle("bunny-coder", "x" * 200)
    assert len(uzun.onizleme) == 63 and uzun.onizleme.endswith("...")


# -- FIFO ---------------------------------------------------------------


def test_sonraki_bekleyen_fifo_en_eski(kuyruk):
    ilk = kuyruk.ekle("bunny-coder", "ilk")
    ikinci = kuyruk.ekle("bunny-coder", "ikinci")
    ucuncu = kuyruk.ekle("bunny-coder", "ucuncu")
    assert kuyruk.sonraki_bekleyen().id == ilk.id
    kuyruk.gecis(ilk.id, Durum.IPTAL)
    assert kuyruk.sonraki_bekleyen().id == ikinci.id
    kuyruk.gecis(ikinci.id, Durum.IPTAL)
    assert kuyruk.sonraki_bekleyen().id == ucuncu.id


def test_sonraki_bekleyen_bos_kuyruk(kuyruk):
    assert kuyruk.sonraki_bekleyen() is None


def test_sonraki_bekleyen_calisan_gorevi_atlar(kuyruk):
    ilk = kuyruk.ekle("bunny-coder", "ilk")
    kuyruk.gecis(ilk.id, Durum.CALISIYOR)
    ikinci = kuyruk.ekle("bunny-coder", "ikinci")
    assert kuyruk.sonraki_bekleyen().id == ikinci.id


# -- gecis / iptal / tekrar --------------------------------------------


def test_gecis_gecerli(kuyruk):
    gorev = kuyruk.ekle("bunny-coder", "is")
    assert kuyruk.gecis(gorev.id, Durum.CALISIYOR).durum is Durum.CALISIYOR
    assert kuyruk.gecis(gorev.id, Durum.BITTI).durum is Durum.BITTI


def test_gecis_gecersiz_db_degismez(kuyruk):
    gorev = kuyruk.ekle("bunny-coder", "is")
    with pytest.raises(GecersizGecis):
        kuyruk.gecis(gorev.id, Durum.BITTI)
    assert kuyruk.al(gorev.id).durum is Durum.BEKLIYOR


def test_son_durumden_cikamaz(kuyruk):
    gorev = kuyruk.ekle("bunny-coder", "is")
    kuyruk.iptal(gorev.id)
    with pytest.raises(GecersizGecis):
        kuyruk.gecis(gorev.id, Durum.BEKLIYOR)
    assert kuyruk.al(gorev.id).durum is Durum.IPTAL


def test_iptal(kuyruk):
    gorev = kuyruk.ekle("bunny-coder", "is")
    assert kuyruk.iptal(gorev.id).durum is Durum.IPTAL


def test_iptal_olmayan_gorev(kuyruk):
    gorev = kuyruk.ekle("bunny-coder", "is")
    with pytest.raises(GorevBulunamadi):
        kuyruk.iptal(gorev.id + 5)


def test_tekrar_hata_dan_bekliyor(kuyruk):
    gorev = kuyruk.ekle("bunny-coder", "is")
    kuyruk.gecis(gorev.id, Durum.CALISIYOR)
    kuyruk.gecis(gorev.id, Durum.HATA)
    assert kuyruk.tekrar(gorev.id).durum is Durum.BEKLIYOR


def test_tekrar_bekleyen_gorevde_gecersiz(kuyruk):
    gorev = kuyruk.ekle("bunny-coder", "is")
    with pytest.raises(GecersizGecis):
        kuyruk.tekrar(gorev.id)
    assert kuyruk.al(gorev.id).durum is Durum.BEKLIYOR


def test_onay_bekliyor_tekrar_akisi(kuyruk):
    gorev = kuyruk.ekle("bunny-coder", "is")
    kuyruk.gecis(gorev.id, Durum.CALISIYOR)
    kuyruk.gecis(gorev.id, Durum.ONAY_BEKLIYOR)
    assert kuyruk.gecis(gorev.id, Durum.BEKLIYOR).durum is Durum.BEKLIYOR


# -- kalicilik ----------------------------------------------------------


def test_kalicilik_db_kapat_ve_yeniden_ac(db_yolu):
    q = Queue(db_yolu)
    a = q.ekle("bunny-coder", "kalici is")
    b = q.ekle("nemotron", "ikinci is")
    q.gecis(a.id, Durum.CALISIYOR)
    q.gecis(a.id, Durum.HATA)
    q.iptal(b.id)
    q.kapat()

    q2 = Queue(db_yolu)
    assert q2.al(a.id).durum is Durum.HATA
    assert q2.al(b.id).durum is Durum.IPTAL
    assert q2.al(a.id).istem == "kalici is"
    assert q2.al(a.id).ajan == "bunny-coder"
    q2.kapat()


def test_kurtarma_acikca_cagrilir(db_yolu):
    """Yarim kalan calisiyor gorev, yeni Queue acilisinda kendiliginden duzelmez."""
    q = Queue(db_yolu)
    gorev = q.ekle("bunny-coder", "yarim kalan")
    q.gecis(gorev.id, Durum.CALISIYOR)
    q.kapat()

    q2 = Queue(db_yolu)
    assert q2.al(gorev.id).durum is Durum.CALISIYOR  # hâlâ calisiyor
    kurtarilan = q2.kurtar()  # yalnızca açık çağrıyla düzeltilir
    assert [g.id for g in kurtarilan] == [gorev.id]
    assert q2.al(gorev.id).durum is Durum.HATA
    q2.kapat()


def test_kurtarma_calisan_gorevleri_hata_cevirir(db_yolu):
    q = Queue(db_yolu)
    a = q.ekle("bunny-coder", "bir")
    b = q.ekle("bunny-coder", "iki")
    c = q.ekle("bunny-coder", "uctu")
    q.gecis(a.id, Durum.CALISIYOR)
    q.gecis(b.id, Durum.CALISIYOR)
    q.iptal(c.id)
    q.kapat()

    q2 = Queue(db_yolu)
    kurtarilan = q2.kurtar()
    assert {g.id for g in kurtarilan} == {a.id, b.id}
    assert q2.al(a.id).durum is Durum.HATA
    assert q2.al(b.id).durum is Durum.HATA
    assert q2.al(c.id).durum is Durum.IPTAL
    assert q2.kurtar() == []  # ikinci cagrida bos
    q2.kapat()


def test_kurtarma_acik_kosu_kaydini_kapatir(kuyruk):
    gorev = kuyruk.ekle("bunny-coder", "is")
    kuyruk.gecis(gorev.id, Durum.CALISIYOR)
    # Surec olmesi benzetimi: yarim acik bir kosu kaydi birakiliyor.
    kuyruk._baglanti.execute(
        "INSERT INTO runs (task_id, baslangic) VALUES (?, ?)", (gorev.id, utc_simdi())
    )
    assert len(kurtarilan := kuyruk.kurtar()) == 1
    assert kurtarilan[0].durum is Durum.HATA
    kosu = kuyruk.kosular(gorev.id)[-1]
    assert kosu.hata == YARIM_KALDI_HATASI
    assert kosu.bitis is not None


# -- tablo / sema -------------------------------------------------------


def test_quota_snapshots_tablosu_var(kuyruk):
    satir = kuyruk._baglanti.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='quota_snapshots'"
    ).fetchone()
    assert satir is not None


def test_db_dosyasi_klasoru_olusur(tmp_path):
    hedef = tmp_path / "yeni" / "klasor" / "o.db"
    q = Queue(hedef)
    assert hedef.exists()
    q.kapat()


def test_bos_kuyruk_calistir_bir_none(kuyruk):
    assert kuyruk.calistir_bir(object()) is None