"""liman web paneli: salt-okunur Flask uygulamasi.

Güvenlik (BAĞLAYICI):
  * Sunucu koda sabit `127.0.0.1` adresine baglanir; `--host` secenegi YOKTUR.
  * `Host` basligi `127.0.0.1[:port]` / `localhost[:port]` degilse 403.
  * Panel YALNIZCA OKUR: surec olusturmez, olmez, port kapatmaz; yazma
    eylemi YOKTUR (CSRF yuzeyi yoktur).
  * Rota yuzeyi salt-GET'tir; digerleri 405.
  * CSP satir ici script/stil yasaklar; JS ve CSS `static/` dosyasindan gelir.
  * JS'te `innerHTML` YOKTUR: DOM yalnizca `createElement` + `textContent`
    ile kurulur (surec adlari/komutlar guvenilmeyen metindir).
"""

from .sunucu import app_olustur, calistir

__all__ = ["app_olustur", "calistir"]
