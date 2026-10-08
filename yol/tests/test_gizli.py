import pytest
from yol.gizli import GizliOrtam
def test_ad_gizli_mi():
    """Gizli ortam fonksiyonunun gizli değişken adlarını doğru şekilde belirlediğini test eder."""
    gizli = GizliOrtam()

    # Gizli adlar
    assert gizli.ad_gizli_mi("PASSWORD") == True
    assert gizli.ad_gizli_mi("secret_key") == True
    assert gizli.ad_gizli_mi("API_TOKEN") == True
    assert gizli.ad_gizli_mi("USER_PASSWORD") == True
    assert gizli.ad_gizli_mi("KULLANICI_SIFRE") == True
    assert gizli.ad_gizli_mi("SECRET") == True
    assert gizli.ad_gizli_mi("TOKEN") == True
    assert gizli.ad_gizli_mi("KEY") == True
    assert gizli.ad_gizli_mi("AUTH_PASSWORD") == True
    assert gizli.ad_gizli_mi("KONSUSER_SECRET") == True

    # Gizli olmayan adlar
    assert gizli.ad_gizli_mi("PATH") == False
    assert gizli.ad_gizli_mi("HOME") == False
    assert gizli.ad_gizli_mi("USERPROFILE") == False
    assert gizli.ad_gizli_mi("PWD") == False  # Özel durum: "PWD" hariç
    assert gizli.ad_gizli_mi("USERNAME") == False
    assert gizli.ad_gizli_mi("NAME") == False
    assert gizli.ad_gizli_mi("VALUE") == False

def test_maskele():
    """Maskeleme fonksiyonunun gizli değişken değerlerini doğru şekilde maskelediğini test eder."""
    gizli = GizliOrtam()

    # Metin maskeleme
    assert gizli.maskele("secret123") == "***********"
    assert gizli.maskele("") == ""

    # Boş değil, maskelenmeyen bir değer (ör. sayı)
    assert gizli.maskele(123) == 123

    # Boolean maskeleme
    assert gizli.maskele(True) == True

def test_ac():
    """Maskeleme fonksiyonunun maskelenmiş değeri geri döndürdüğünü test eder."""
    gizli = GizliOrtam()

    assert gizli.ac("***********") == "***********"
    assert gizli.ac("") == ""
    assert gizli.ac("normal_value") == "normal_value"