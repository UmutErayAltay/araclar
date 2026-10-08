"""devtemizle web paneli: yerel Flask uygulamasi (opsiyonel bagimlilik: Flask).

Guvenlik (BAGLAYICI): bkz. sunucu.py ve /home/user/corclient/TASARIM.md §5.
"""

from .sunucu import calistir, uygulama_olustur

__all__ = ["calistir", "uygulama_olustur"]
