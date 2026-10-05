"""servis: yerel servis yiginini baslatin / durdurun / durumunu gosteren CLI.

Guvenlik (baglayici kural): durdurma YALNIZCA kendi pid dosyamizdaki sureci
yapar; portu baska biri dolduruyorsa ya da pid yeniden kullanilmissa o surece
DOKUNULMAZ. `--kuru` hicbir surec baslatmaz/oldurmez.
"""
__version__ = "0.1.0"