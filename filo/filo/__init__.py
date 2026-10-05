"""filo: bir gorev metnini N repoya PARALEL dagitan tek seferlik toplu calistirici.

Bu bir KALICI KUYruk degildir (orkestra/'nin isi): tek sefer calisir, biter.
Repo basina yerel `cor claude` alt sureci (headless) calistirilir, raporlar tek
cikti klasorunde toplanir.

Guvenlik (baglayici kural): alt surec ASLA `--dangerously-skip-permissions`
ya da `bypassPermissions` ile kurulamaz ve ASLA commit/push/checkout yapmaz.
Varsayilan arac listesi SALT OKUNURdur (`Read,Glob,Grep`); yazma yetkisi ancak
`--duzenle` ile acilir. `--kuru` hicbir alt surec baslatmadan plani gosterir.
"""
__version__ = "0.1.0"