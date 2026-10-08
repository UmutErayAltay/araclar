import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
import sys
import os

# Windows testinin gerçek winreg'i kullanmamasını sağlamak için os.name'i monkeypatch edin
@pytest.mark.skipif(os.name != "nt", reason="Windows kayıt defteri testleri yalnız Windows'ta çalışır")
def test_windows_kaynak_basit():
    """WindowsKaynak implementasyonunun okuma/yazma işlemlerini gerçekleştirdiğini test eder (mock)."""
    # winreg ve ctypes modüllerini mock edin
    import winreg
    import ctypes

    mock_winreg = MagicMock()
    mock_winreg.HKEY_CURRENT_USER = 1
    mock_winreg.HKEY_LOCAL_MACHINE = 2
    mock_winreg.KEY_READ = 4
    mock_winreg.KEY_WRITE = 8
    mock_winreg.REG_EXPAND_SZ = 2
    mock_winreg.REG_SZ = 1

    # Mock anahtarlar
    mock_kullanici_anahtar = MagicMock()
    mock_kullanici_anahtar.EnumValue = MagicMock(side_effect=[
        ("PATH", "%USERPROFILE%\\bin", 2),
        ("SECRET", "secret_value", 1)
    ])

    mock_sistem_anahtar = MagicMock()
    mock_sistem_anahtar.EnumValue = MagicMock(side_effect=[
        ("COMSPEC", "%SYSTEMROOT%\\system32\\cmd.exe", 2)
    ])

    mock_winreg.OpenKey = MagicMock(side_effect=lambda hkey, path, *args, **kwargs: {
        (1, r"Environment"): mock_kullanici_anahtar,
        (2, r"SYSTEM\\CurrentControlSet\\Control\\Session Manager\\Environment"): mock_sistem_anahtar
    }[(hkey, path)])

    mock_winreg.SetValueEx = MagicMock()
    mock_winreg.DeleteValue = MagicMock()

    mock_ctypes = MagicMock()
    mock_ctypes.windll.shell32.IsUserAnAdmin = MagicMock(return_value=1)
    mock_ctypes.windll.user32.SendMessageTimeoutW = MagicMock()

    with patch.dict(sys.modules, {"winreg": mock_winreg, "ctypes": mock_ctypes}):
        from yol.kaynak import WindowsKaynak

        kaynak = WindowsKaynak()

        # Okuma işlemi
        kullanici_degerleri = kaynak.oku("kullanici")
        assert "PATH" in kullanici_degerleri
        assert kullanici_degerleri["PATH"].metin == "%USERPROFILE%\\bin"
        assert kullanici_degerleri["PATH"].genisler == True

        sistem_degerleri = kaynak.oku("sistem")
        assert "COMSPEC" in sistem_degerleri
        assert sistem_degerleri["COMSPEC"].metin == "%SYSTEMROOT%\\system32\\cmd.exe"
        assert sistem_degerleri["COMSPEC"].genisler == True

        # Yazma işlemi
        deger = Deger(metin="YeniDeger", genisler=False)
        kaynak.yaz("kullanici", "NEW", deger)
        mock_winreg.SetValueEx.assert_called_with(mock_kullanici_anahtar, "NEW", 0, 1, "YeniDeger")

        # Silme işlemi
        kaynak.sil("sistem", "COMSPEC")
        mock_winreg.DeleteValue.assert_called_with(mock_sistem_anahtar, "COMSPEC")

        # Yazılabilirlik denetimi
        assert kaynak.yazilabilir("kullanici") == True
        assert kaynak.yazilabilir("sistem") == True

        # Yayın
        kaynak.yayınla()
        mock_ctypes.windll.user32.SendMessageTimeoutW.assert_called()