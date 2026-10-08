from __future__ import annotations

import re
from typing import Any
class GizliOrtam:
    """Adı gizli değişkenler (şifre, token, vb.) için maskeleme mantığı."""

    # Örnek maskeleme kalıpları
    MASKEDEMEK_KALIPLARI = [
        r".*KEY.*",
        r".*TOKEN.*",
        r".*SECRET.*",
        r".*PASSWORD.*",
        r".*PASS.*",
        r".*PWD.*",
        r".*CREDENTIAL.*"
    ]

    def __init__(self) -> None:
        # Sıfırla (eğer gerekirse)
        pass

    def ad_gizli_mi(self, ad: str) -> bool:
        """Bir ortam değişkeni adının gizli olup olmadığını döndürür."""
        ad_kucuk = ad.lower()
        for kalip in self.MASKEDEMEK_KALIPLARI:
            if re.match(kalip, ad_kucuk):
                return True
        # Özel durum: PWD hariç (PWD>0 'benzer' maskelenmez)
        if ad_kucuk == "pwd":
            return False
        return False

    def maskele(self, deger: Any) -> Any:
        """Gizli bir değişken için değeri maskeler (görünürlük izin verilmedikçe)."""
        if isinstance(deger, str):
            if deger:
                return "*" * len(deger)
        return deger

    def ac(self, maskelenmis: str) -> str:
        """Gizli bir değişkenin orijinal değerini döndürür (açılabilir)."""
        # Gizli değişkenler için orijinal değeri almak için de bir API gerektiriyor.
        # Bu burada işlemez; e2e web paneli ayrı bir API ile arka plana geri istek göndermeli.
        return maskelenmis  # Yalnızca maskelenmiş değeri döndür