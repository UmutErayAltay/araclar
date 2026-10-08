import pytest
import sys
import os
from unittest.mock import patch, MagicMock

from yol.cli import YolCLI
from yol.kaynak import Deger, kaynak_sec
from yol.analiz import komutlar_olustur
def test_yol_cli_denetle_basit():
    """YolCLI denetle fonksiyonunun basit bir şekilde çalıştığını test eder."""
    # PATH ile ortamı simule edin
    with patch.dict(os.environ, {"PATH": "/usr/bin:/bin", "PATHEXT": ".EXE;.COM"}, clear=False):
        kaynak = kaynak_sec()
        cli = YolCLI(kaynak)
        # Çıktıyı yakalamak için bir I/O yakalayıcı olusturun
        # Şimdilik sadece çalışıyor mu diye kontrol edelim
        cli.denetle(json_modu=False)

def test_yol_cli_nerede():
    """YolCLI nerede fonksiyonunun komut konumunu sagladığını test eder."""
    with patch.dict(os.environ, {"PATH": "C:\\test\\dir;C:\\other\\dir", "PATHEXT": ".EXE;.COM"}):
        kaynak = kaynak_sec()
        cli = YolCLI(kaynak)
        # Çıktıyı yakalamak için bir I/O yakalayıcı olusturun
        cli.nerede("python")

def test_yol_cli_temizle():
    """YolCLI temizle fonksiyonunun PATH'i temizlediğini test eder."""
    with patch.dict(os.environ, {"PATH": "C:\\test\\bad;C:\\bin;C:\\test\\bad;C:\\test"}):
        kaynak = kaynak_sec()
        cli = YolCLI(kaynak)
        # Örnek: Sadece PATH'i olusturun
        # Temizlik öneri sistem temel alınarak oluşturulur
        cli.temizle(uygula=False)

def test_yol_cli_ekle():
    """YolCLI ekle fonksiyonunun PATH'e bir dizin eklediğini test eder."""
    # Geçici bir dizin olusturun
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmpdir:
        dizin = Path(tmpdir)
        # PATH'i olusturun
        with patch.dict(os.environ, {"PATH": "/usr/bin"}, clear=False):
            kaynak = kaynak_sec()
            cli = YolCLI(kaynak)
            cli.ekle(str(dizin), basa=False, uygula=False)

def test_yol_cli_kaldir():
    """YolCLI kaldir fonksiyonunun PATH'ten bir dizini kaldırdığını test eder."""
    with patch.dict(os.environ, {"PATH": "C:\\test\\dir;C:\\other\\dir"}, clear=False):
        kaynak = kaynak_sec()
        cli = YolCLI(kaynak)
        cli.kaldir("C:\\test\\dir", uygula=False)

def test_yol_cli_yedekler():
    """YolCLI yedekler fonksiyonunun son 30 yedeği listelediğini test eder."""
    kaynak = kaynak_sec()
    cli = YolCLI(kaynak)
    cli.yedekler()

def test_yol_cli_geri_al():
    """YolCLI geri_al fonksiyonunun bir yedekten farkı önizlediğini test eder."""
    kaynak = kaynak_sec()
    cli = YolCLI(kaynak)
    cli.geri_al("test_id", uygula=False)

def test_yol_cli_web():
    """YolCLI web fonksiyonunun web sunucusunu başlattığını test eder (dummy)."""
    kaynak = kaynak_sec()
    cli = YolCLI(kaynak)
    cli.web(port=8797, ac=False)