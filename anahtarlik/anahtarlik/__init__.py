"""anahtarlik: repolardaki gizli anahtarlari (API key / token / parola) tarayan CLI.

Guvenlik (baglayici kural): HAM DEGER HICBIR YERE CIKMAZ. Deger ne diske
(yalniz `envanter.json`a parmak izi olarak), ne JSON'a, ne stdout/stderr'a, ne
exception mesajina, ne traceback'e, ne de `repr()`e gider. Gorunen tek sey AD
ve parmak izidir (`parmak.izi`).
"""
__version__ = "0.1.0"