"""atlas web paneli (Dalga C): salt-okunur Flask uygulamasi.

Güvenlik (BAĞLAYICI):
  * Sunucu koda sabit `127.0.0.1` adresine baglanir; `--host` secenegi YOKTUR.
  * `Host` basligi `127.0.0.1[:port]` / `localhost[:port]` degilse 403 — ve
    reddedilen istek baglanti ACILMADAN, hicbir sorguya dokunmadan doner.
  * DB `mode=ro` (URI) ile acilir; panel HICBIR kosulda yazmaz.
  * Panel repolara dokunmaz ve tarama TETIKLEMEZ: yalnizca DB'yi okur.
  * Rota yuzeyi salt-GET'tir; dosya sistemi yolu alan rotalar YOKTUR
    (yalnizca sayisal `id` ve sayfa).
  * CSP satir ici script/stil yasaklar; JS ve CSS `static/` dosyasindan gelir.
  * Ekrana basilan HER `snippet_redacted`/`text`, basilmadan ONCE
    `leaks.maske` fonksiyonundan bir kez daha gecer (savunma katmani).
  * `dosya`, `snippet`, `todo` metni, repo adi GUVENILMEYENDIR: Jinja
    autoescape aciktir, JS'te `innerHTML` YOKTUR (`textContent` kullanilir).
"""

from .sunucu import app_olustur, calistir

__all__ = ["app_olustur", "calistir"]
