import pytest
import json
from pathlib import Path
import tempfile

from yol.degisiklik import Degisiklikler, Degisiklik, DegisiklikHatasi, uygulama_yap
from yol.kaynak import Deger, DosyaKaynak
from yol.yedek import YedekDeposu
from yol.yedek import Gunluk
# Verileri kontrol etmek icin bir gecici dizin olusturun
@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)
@pytest.fixture
def kaynak(temp_dir):
    """Dosya kaynagi icin verilen gecici dizin yolu ile DegerKaynagi olusturun."""
    dosya_yolu = temp_dir / "ortam.json"
    kaynak = DosyaKaynak(dosya_yolu)
    return kaynak
@pytest.fixture
def yedek_deposu(temp_dir):
    """Gecici dizin yolu ile YedekDeposu olusturun."""
    yedek_dizini = temp_dir / "yedek"
    yedek_deposu = YedekDeposu(yedek_dizini)
    return yedek_deposu
@pytest.fixture
def gunluk(temp_dir):
    """Gecici dizin yolu ile Gunluk olusturun."""
    gunluk_dosya = temp_dir / "gunluk.jsonl"
    gunluk = Gunluk(gunluk_dosya)
    return gunluk
def test_degisiklik_ozet(kaynak):
    """Degisiklikler ozet fonksiyonunun eklenen/kaldırılan/değiştirilenleri dogru saydigini test eder."""
    degsiklikler = Degisiklikler([
        Degisiklik("kullanici", "PATH", None, Deger("test", False)),
        Degisiklik("sistem", "PATH", Deger("eski", False), None),
        Degisiklik("kullanici", "SECRET", Deger("eski", False), Deger("yeni", False))
    ])

    ozet = degsiklikler.ozet()
    assert "1 kaldırıldı" in ozet
    assert "1 eklendi" in ozet
    assert "1 değiştirildi" in ozet
def test_degisiklik_to_from_dict():
    """Degisiklikler to_dict ve from_dict fonksiyonlarının veriyi dogru sekilde serilestirdigini test eder."""
    degsiklikler = Degisiklikler([
        Degisiklik("kullanici", "PATH", None, Deger("test", False)),
        Degisiklik("sistem", "SECRET", Deger("eski", False), None)
    ])

    veri = degsiklikler.to_dict()
    # Kaynak ile from_dict kullanarak veriyi saglamak
    degsiklikler2 = Degisiklikler.from_dict(veri)

    assert len(degsiklikler2.degisiklikler) == 2
    # Degisiklik nesnelerinin esitligi, ad ve kapsam baglamak zorunda
    d1 = degsiklikler2.degisiklikler[0]
    assert d1.ad == "PATH" and d1.kapsam == "kullanici" and d1.yeni is not None
    assert d1.eski is None

    d2 = degsiklikler2.degisiklikler[1]
    assert d2.ad == "SECRET" and d2.kapsam == "sistem" and d2.eski is not None
    assert d2.yeni is None

def test_yedek_deposu_ekle(temp_dir):
    """YedekDeposu ekleme fonksiyonunun yeni bir yedek ekledigini dogrular."""
    yedek_dizini = temp_dir / "yedek"
    yedek_deposu = YedekDeposu(yedek_dizini)

    yedek_dosya = yedek_deposu.en_son_yedek()
    assert yedek_dosya is None

    # Yapay bir yedek olusturun ve ekleyin
    from yol.yedek import Yedek
    yedek = Yedek(id="test1", kapsamlar={"kullanici": {}, "sistem": {}})
    yedek_deposu.ekle(yedek)

    # Dosyadan okumak
    dosya_yolu = yedek_deposu._yedek_dosya_yolu("test1")
    assert dosya_yolu.exists()

    # En son 30 yedeği okumak
    yedekler = yedek_deposu.en_son_30_yedek()
    assert len(yedekler) == 1
    assert yedekler[0].id == "test1"
def test_yedek_deposu_en_son_30_yedek(temp_dir):
    """YedekDeposu en_son_30_yedek fonksiyonunun en son 30 yedeği sagladigini test eder."""
    yedek_dizini = temp_dir / "yedek"
    yedek_deposu = YedekDeposu(yedek_dizini)

    # 10 yedek dosyası olusturun
    from yol.yedek import Yedek
    for i in range(10):
        yedek = Yedek(id=str(i), kapsamlar={"kullanici": {}, "sistem": {}})
        yedek_deposu.ekle(yedek)

    son_30 = yedek_deposu.en_son_30_yedek()
    assert len(son_30) == 10

    # Her id'nin artan siralı oldugunu dogrular
    idler = [y.id for y in son_30]
    assert idler == ["9", "8", "7", "6", "5", "4", "3", "2", "1", "0"]
def test_gunluk_ekle(temp_dir):
    """Gunluk ekleme fonksiyonunun yeni bir kayit ekledigini test eder."""
    gunluk_dosya = temp_dir / "gunluk.jsonl"
    gunluk = Gunluk(gunluk_dosya)

    gunluk.ekle("kullanici", "PATH", "ekle")
    gunluk.ekle("sistem", "SECRET", "sil")

    # Dosyadan okumak ve parse etmek
    with open(gunluk_dosya, "r", encoding="utf-8") as f:
        satirlar = f.readlines()

    assert len(satirlar) == 2
    # Parse
    kayit1 = json.loads(satirlar[0])
    assert kayit1["kapsam"] == "kullanici"
    assert kayit1["ad"] == "PATH"
    assert kayit1["eylem"] == "ekle"

    kayit2 = json.loads(satirlar[1])
    assert kayit2["kapsam"] == "sistem"
    assert kayit2["ad"] == "SECRET"
    assert kayit2["eylem"] == "sil"
def test_aplikasyon_yap_basit(temp_dir):
    """Uygulama_yap fonksiyonunun PATH'i olusturan DosyaKaynagi icin temel degisiklikleri dogru sekilde uyguladigini test eder."""
    kaynak = DosyaKaynak(temp_dir / "ortam.json")
    yedek_deposu = YedekDeposu(temp_dir / "yedek")
    gunluk = Gunluk(temp_dir / "gunluk.jsonl")

    # Baslangic durumunu kontrol et
    baslangic = kaynak.oku("kullanici")
    assert len(baslangic) == 0

    # PATH'i ekleyen bir degisiklik olusturun
    degisiklikler = Degisiklikler([
        Degisiklik("kullanici", "PATH", None, Deger("C:\\test", False))
    ])

    uygulamalanan = uygulama_yap(kaynak, degisiklikler, gunluk, yedek_deposu)
    assert len(uygulanan) == 1
    assert uygulamalanan[0].yeni is not None
    assert uygulamalanan[0].yeni.metin == "C:\\test"

    # Değer doğrulama
    mevcut = kaynak.oku("kullanici")
    assert "PATH" in mevcut
    assert mevcut["PATH"].metin == "C:\\test"
    # günlük kaydı ekle
    gunluk.ekle("kullanici", "PATH", "yaz")

    # PATH'i silen bir degisiklik uygulamak için bir diğer test fonksiyonu oluşturun.
    # Bunun yerine, baslangıc noktasına geri dönebiliriz.
    kaynak.yaz("kullanici", "PATH", Deger("C:\\test", False))
    degisiklikler2 = Degisiklikler([
        Degisiklik("kullanici", "PATH", Deger("C:\\test", False), None)
    ])
    uygulamalanan2 = uygulama_yap(kaynak, degisiklikler2, gunluk, yedek_deposu)
    assert len(uygulanen2) == 1
    mevcut2 = kaynak.oku("kullanici")
    assert "PATH" not in mevcut2

    # Beklenmeyen degisiklik kontrolü için hata durumunu test edin
    # PATH'i silmeden önce PATH üzerinde bir degisiklik yapmak için bir diğer kaynak olusturun
    # Beklenmeyen degisiklik tikli bir degisiklik olusturun
    # Şimdilik geçiyor.
    pass