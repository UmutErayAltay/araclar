"""FakeRunner'in dort senaryosu ve Queue.calistir_bir davranisi."""

import pytest

from orkestra.models import Durum, RunSonuc
from orkestra.queue import Queue
from orkestra.runner import FakeRunner, Runner


def test_runner_protokolu():
    """FakeRunner protokolü karşılar; calistir(task) -> RunSonuc."""
    assert isinstance(FakeRunner(), Runner)
    assert callable(FakeRunner().calistir)


def test_fake_runner_gecerli_senaryolar():
    assert set(FakeRunner.SENARYOLAR) == {"basari", "hata", "onay-gerekli", "istisna"}


def test_calistir_bir_basarida_bitti(kuyruk):
    gorev = kuyruk.ekle("bunny-coder", "is")
    sonuc = kuyruk.calistir_bir(FakeRunner("basari"))
    gorev, kosu = sonuc
    assert gorev.durum is Durum.BITTI
    assert kosu.cikis_kodu == 0
    assert kosu.hata is None
    assert kosu.baslangic and kosu.bitis


def test_calistir_bir_hatada_hata_durumu(kuyruk):
    kuyruk.ekle("bunny-coder", "is")
    gorev, kosu = kuyruk.calistir_bir(FakeRunner("hata"))
    assert gorev.durum is Durum.HATA
    assert kosu.cikis_kodu == 1
    assert "basarisiz" in kosu.hata


def test_calistir_bir_onay_gerekli(kuyruk):
    kuyruk.ekle("bunny-coder", "is")
    gorev, kosu = kuyruk.calistir_bir(FakeRunner("onay-gerekli"))
    assert gorev.durum is Durum.ONAY_BEKLIYOR
    assert kosu.hata == "kullanici onayi gerekiyor"
    assert kuyruk.gecis(gorev.id, Durum.BEKLIYOR).durum is Durum.BEKLIYOR


def test_calistir_bir_istisnada_hata_durumu(kuyruk):
    kuyruk.ekle("bunny-coder", "is")
    gorev, kosu = kuyruk.calistir_bir(FakeRunner("istisna"))
    assert gorev.durum is Durum.HATA
    assert "RuntimeError" in kosu.hata
    assert "istisna" in kosu.hata


def test_istisna_kuyrugu_cokertmez(kuyruk):
    kuyruk.ekle("bunny-coder", "bir")
    kuyruk.calistir_bir(FakeRunner("istisna"))
    kuyruk.ekle("bunny-coder", "iki")
    gorev, _ = kuyruk.calistir_bir(FakeRunner("basari"))
    assert gorev.durum is Durum.BITTI


def test_calistir_bir_bos_kuyruk(kuyruk):
    assert kuyruk.calistir_bir(FakeRunner("basari")) is None


def test_calistir_bir_fifo_sirasyla(kuyruk):
    ilk = kuyruk.ekle("bunny-coder", "ilk")
    ikinci = kuyruk.ekle("bunny-coder", "ikinci")
    calisan = FakeRunner("basari")
    g1, _ = kuyruk.calistir_bir(calisan)
    g2, _ = kuyruk.calistir_bir(calisan)
    assert (g1.id, g2.id) == (ilk.id, ikinci.id)
    assert [g.istem for g in calisan.gorevler] == ["ilk", "ikinci"]


def test_calistir_bir_kanit_ve_cikti_yazilir(kuyruk):
    kuyruk.ekle("bunny-coder", "is")
    calisan = FakeRunner("basari", cikti_on="/tmp/out.txt", kanit_on=["/tmp/a.png", "/tmp/b.png"])
    _, kosu = kuyruk.calistir_bir(calisan)
    assert kosu.cikti_yolu == "/tmp/out.txt"
    assert kosu.kanit_yollari == ["/tmp/a.png", "/tmp/b.png"]


def test_calistir_bir_birden_fazla_kosu_kaydedilir(kuyruk):
    gorev = kuyruk.ekle("bunny-coder", "is")
    kuyruk.calistir_bir(FakeRunner("hata"))
    kuyruk.gecis(gorev.id, Durum.BEKLIYOR)
    kuyruk.calistir_bir(FakeRunner("basari"))
    kosular = kuyruk.kosular(gorev.id)
    assert len(kosular) == 2
    assert kosular[0].hata is not None and kosular[1].hata is None


def test_hata_dan_sonra_tekrar_ve_basari(kuyruk):
    gorev = kuyruk.ekle("bunny-coder", "is")
    kuyruk.calistir_bir(FakeRunner("hata"))
    assert kuyruk.al(gorev.id).durum is Durum.HATA
    kuyruk.tekrar(gorev.id)
    g, _ = kuyruk.calistir_bir(FakeRunner("basari"))
    assert g.durum is Durum.BITTI


def test_calistir_bir_calisirken_durum(kuyruk):
    """Runner çağrılırken görev 'calisiyor' olmalı."""
    kuyruk.ekle("bunny-coder", "is")
    gorulen = {}

    def gozlemci(task):
        gorulen["durum"] = task.durum
        return RunSonuc()

    kuyruk.calistir_bir(FakeRunner(calistir_ile=gozlemci))
    assert gorulen["durum"] is Durum.CALISIYOR


def test_calistir_bir_gecersiz_donus_durumu_hata(kuyruk):
    """RunSonuc dönmeyen runner görevi hata'ya düşürür."""
    kuyruk.ekle("bunny-coder", "is")
    gorev, kosu = kuyruk.calistir_bir(FakeRunner(calistir_ile=lambda t: None))
    assert gorev.durum is Durum.HATA
    assert "RunSonuc" in kosu.hata


def test_bilinmeyen_senaryo_hata():
    with pytest.raises(ValueError):
        FakeRunner("olmayan-senaryo")


def test_fake_runner_kendi_senaryosu_tutarlı(kuyruk):
    kuyruk.ekle("bunny-coder", "is")
    calisan = FakeRunner("onay-gerekli")
    _, kosu = kuyruk.calistir_bir(calisan)
    assert calisan.senaryo == "onay-gerekli"
    assert kosu.cikis_kodu == 2