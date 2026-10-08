"""yol web paneli (Flask, yalniz 127.0.0.1). Flask yoksa import hata verir; cli bunu yakalar."""

from .sunucu import calistir, uygulama_olustur

__all__ = ["calistir", "uygulama_olustur"]
