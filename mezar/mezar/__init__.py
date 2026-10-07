"""mezar: bosaltilmis ('mezar tasi') repolari silmeden ONCE denetleyen CLI.

Guvenlik (baglayici kural): arac TAMAMEN SALT OKUNUR. Silme, arsivleme, push,
fetch ve ag erisimi YOKTUR; hicbir komut dosya sistemini degistirmez.

Gizli anahtar denetiminde HAM DEGER HICBIR YERE CIKMAZ -- stdout/stderr, JSON,
hata mesaji ve test ciktisinda degerin yerine yalniz commit kisa hash'i, dosya
yolu, tur ve tuzlu parmak izi vardir.

Yeniden kullanim: tespit desenleri ve parmak izi `anahtarlik` paketinden ICE
AKTARILIR, kopyalanmaz. Monorepo icinde yanyana yasarlar; bu yuzden
`anahtarlik/` dizini `sys.path`'e eklenir (pip bagimliligi degil).
"""

from __future__ import annotations

import sys
from pathlib import Path

#: Kardes aracin (`anahtarlik`) paketinin bulundugu dizin: <repo>/anahtarlik.
#: `mezar/` ve `anahtarlik/` kardes olduklari icin burasi her ikisinin de
#: yuklendigi tanitim noktasi: CLI girisi, `python -m mezar` ve testler ayni
#: satirdan gecer.
_KARDES = Path(__file__).resolve().parents[2] / "anahtarlik"
if _KARDES.is_dir() and str(_KARDES) not in sys.path:
    sys.path.append(str(_KARDES))

__version__ = "0.1.0"