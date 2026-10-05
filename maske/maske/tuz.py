"""Parmak izi tuzunun YERINI belirler -- depo (repo) ici ASLA degil.

Tuz makine-yereldir: ayni deger, ayni tuzla ayni izi verir. Bu yuzden tuz bir
kullanici veri dosyasidir (0600) ve kaynak agacinda hicbir yerde bulunmaz.

Cozumleme sirasi:
  1. `MASKE_TUZ_DIZINI`  -- maske'ye ozel kullanimci veri dizini
  2. `ANAHTARLIK_DIR`    -- kardes aracin (`anahtarlik`) dizini; acikca
                            yonlendirildiyse (ortak kullanim, test izolasyonu)
                            aynen kullanilir
  3. `~/.maske/`         -- varsayilan kullanici veri dizini

Kardes arac `anahtarlik.parmak` tuzu `ANAHTARLIK_DIR/tuz` altinda arar ve bu
degiskeni Cagri aninda okur; `hazirla()` cozumlenen dizini oraya yazar, boylece
`anahtarlik/` klasorune DOKUNULMADAN maske'nin tuzu kendi yerine gider.
"""

from __future__ import annotations

import os
from pathlib import Path

#: Kullanici veri dizininin adi (tuz dosyasi bunun altinda durur).
VARSAYILAN_DIZIN = ".maske"


def dizin() -> Path:
    """Tuzun yazilacagi dizin (mutlak, henuz olusturulmamis olabilir).

    Depo ici bir yol ASLA bu fonksiyonu terk etmez; varsayilan kullanici
    evidir. Testler `MASKE_TUZ_DIZINI` ile gecici dizine yonlendirir.
    """
    yol = os.environ.get("MASKE_TUZ_DIZINI") or os.environ.get("ANAHTARLIK_DIR")
    if yol:
        return Path(yol).expanduser()
    return Path.home() / VARSAYILAN_DIZIN


def hazirla() -> Path:
    """Tuz dizinini cozumler ve `ANAHTARLIK_DIR` olarak ayarlar.

    `parmak.tuz()` tuz dosyasini `ANAHTARLIK_DIR/tuz` yolunda arayip yoksa
    uretecegi icin (tara -> `parmak.izi`) bu ayarlama tarama oncesinde yapilir.
    Idempotenttir: ayni deger arka arkaya yazilsa da sonuc degismez.
    """
    cozumlenen = dizin()
    os.environ["ANAHTARLIK_DIR"] = str(cozumlenen)
    return cozumlenen