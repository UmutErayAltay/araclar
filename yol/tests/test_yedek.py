import pytest
from pathlib import Path
import tempfile
from yol.yedek import Yedek, YedekDeposu
from yol.kaynak import Deger
@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)
@pytest.fixture
def yedek_deposu(temp_dir):
    yedek_dizini = temp_dir / "yedek"
    yedek_deposu = YedekDeposu(yedek_dizini)
    return yedek_deposu
def test_yedek_tasima(temp_dir):
    """Yedek tasima fonksiyonunun serileştirme/basitleştirme işlemlerini doğru şekilde gerçekleştirdiğini test eder."""
    kapsamlar = {"kullanici": {"PATH": Deger("C:\\test", False)}, "sistem": {"SECRET": Deger("xyz", True)}}
    yedek = Yedek(id="test1", kapsamlar=kapsamlar)

    tasima = yedek.to_dict()
    assert tasima["id"] == "test1"
    assert "kapsamlar" in tasima
    assert tasima["kapsamlar"]["kullanici"]["PATH"]["metin"] == "C:\\test"
    assert tasima["kapsamlar"]["kullanici"]["PATH"]["genisler"] == False
    assert tasima["kapsamlar"]["sistem"]["SECRET"]["metin"] == "xyz"
    assert tasima["kapsamlar"]["sistem"]["SECRET"]["genisler"] == True

    # from_dict kullanarak veriyi saglamak
    yedek2 = Yedek.from_dict(tasima)

    assert yedek2.id == yedek.id
    assert yedek2.kapsamlar["kullanici"]["PATH"].metin == yedek.kapsamlar["kullanici"]["PATH"].metin
    assert yedek2.kapsamlar["sistem"]["SECRET"].genisler == yedek.kapsamlar["sistem"]["SECRET"].genisler
def test_yedek_deposu_ekle_yedek(yedek_deposu):
    """YedekDeposu ekleme fonksiyonunun yeni bir yedek eklediğini dogrular."""
    yedek = Yedek(id="test1", kapsamlar={"kullanici": {}, "sistem": {}})
    yedek_deposu.ekle(yedek)

    # Dosyadan okumak
    dosya_yolu = yedek_deposu._yedek_dosya_yolu("test1")
    assert dosya_yolu.exists()

    # En son 30 yedeği okumak
    yedekler = yedek_deposu.en_son_30_yedek()
    assert len(yedekler) == 1
    assert yedekler[0].id == "test1"
def test_yedek_deposu_en_son_yedek(yedek_deposu):
    """YedekDeposu en_son_yedek fonksiyonunun en son yedeği dogru sekilde sagladigini test eder."""
    yedek = Yedek(id="test1", kapsamlar={"kullanici": {}, "sistem": {}})
    yedek_deposu.ekle(yedek)

    en_son = yedek_deposu.en_son_yedek()
    assert en_son is not None
    assert en_son.id == "test1"
def test_yedek_deposu_en_son_30_yedek(yedek_deposu):
    """YedekDeposu en_son_30_yedek fonksiyonunun en son 30 yedeği sagladigini test eder."""
    # 35 yedek dosyası olusturun
    for i in range(35):
        yedek = Yedek(id=str(i), kapsamlar={"kullanici": {}, "sistem": {}})
        yedek_deposu.ekle(yedek)

    son_30 = yedek_deposu.en_son_30_yedek()
    assert len(son_30) == 30

    # En son 30 yedeğin IDslerinin sıralı oldugunu dogrular (en son olan 34'tür)
    idler = [y.id for y in son_30]
    assert idler == ["34", "33", "32", "31", "30", "29", "28", "27", "26", "25", "24", "23", "22", "21", "20", "19", "18", "17", "16", "15", "14", "13", "12", "11", "10", "9", "8", "7", "6", "5"]
def test_yedek_deposu_geri_al(yedek_deposu):
    """YedekDeposu geri_al fonksiyonunun bir yedekten farkı dogru sekilde sagladigini test eder."""
    # İki yedek olusturun
    yedek1 = Yedek(id="yedek1", kapsamlar={"kullanici": {"PATH": Deger("C:\\test", False)}, "sistem": {}})
    yedek2 = Yedek(id="yedek2", kapsamlar={"kullanici": {}, "sistem": {"SECRET": Deger("secret", True)}})
    yedek_deposu.ekle(yedek1)
    yedek_deposu.ekle(yedek2)

    # İlk yedekten farkı saglayın (ikinci yedek mevcut yedek)
    fark = yedek_deposu.geri_al("yedek1")

    # Fark sadece yedek1'in sahip oldugu kapsamdaki değişkenleri içermelidir
    assert "kullanici" in fark
    assert "PATH" in fark["kullanici"]
    assert fark["kullanici"]["PATH"].metin == "C:\\test"
    assert "sistem" not in fark  # yedek2'ye ait bir sistem değişkeni yok

    # İkinci yedekten farkı saglayın
    fark2 = yedek_deposu.geri_al("yedek2")
    assert "sistem" in fark2
    assert "SECRET" in fark2["sistem"]
    assert "kullanici" not in fark2