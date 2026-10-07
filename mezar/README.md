# mezar

Boşaltılmış ("mezar taşı") repoları **silmeden/arşivlemeden önce** denetler ve her repo için
`KAPATILABILIR` ya da `DIKKAT` kararı verir. Tamamen **salt okunur**: silmez, arşivlemez,
`push`/`fetch` yapmaz, ağa çıkmaz. Repoları yalnız **okur**. Yalnız Python standart kütüphanesi
(Python 3.11+).

## Ne yapar

`--repo ad` verilen her ad için `<kok>/<ad>` dizinini denetler; taşınan kodun yeni yeri
`<arac-repo>/<ad>/` olarak kabul edilir. Dört denetim:

| Denetim | Ne sorar | Kararı etkiler mi? |
|---|---|---|
| `mezar_tasi` | Boşaltma sonrası çalışma ağacında `.git` dışında yalnız `README.md` kaldı mı? | Hayır — bilgi notu |
| `tasima_tamlik` | Boşaltma commit'inden **önceki** commit'in (`HEAD~1`) dosyaları hedefte var mı? | Evet (eksik varsa) |
| `gonderilmemis` | Uzakda olmayan commit var mı? Çalışma ağacı kirli mi? | Evet (`YUKSEK`) |
| `gecmis_secret` | Repo geçmişinde gizli anahtar izi var mı? | Evet |

`tasima_tamlik` eşleştirmesi iki aşamalıdır: önce **aynı göreli yol**, sonra kalanlar için
**aynı dosya adı** (taşırken yol değişmiş olabilir). `.gitignore`, `__pycache__`, `*.pyc`,
`.pytest_cache` ve `*.egg-info` karşılaştırmaya girmez. Eksikler en çok **25** tanesi listelenir,
toplam sayı her zaman yazılır.

`gecmis_secret`, `git log -p --all` çıktısını **satır satır** tarar (büyük diff belleğe girmez).
Desenler kardeş araç `anahtarlik`'ten içe aktarılır — kopyalanmaz. `test_` oneki, `tests/`,
`.example`/`EXAMPLE` işaretli dosyalar atlanır. Tarama **200000 satır** veya **20 saniye**'yi
aşarsa kesilir ve "kısmi tarama" uyarısı düşer.

**Gizli anahtar değeri hiçbir yere çıkmaz** — stdout/stderr, JSON, hata mesajı ve test çıktısında
yalnız ad, dosya:satır, tür ve kısa tuzlu parmak izi vardır.

Uzakta olmayan commit bulgusu **`YUKSEK`** onemle işaretlenir ve commit konu satırlarıyla
birlikte listelenir: repo kapanırsa o iş **kalıcı olarak** kaybolur.

## Karar

- **`KAPATILABILIR`**: eksik dosya yok, gönderilmemiş commit yok, geçmişte secret yok, tarama tam.
- **`DIKKAT`**: yukarıdakilerden en az biri var; nedenler liste hâlinde yazılır.

"Remote izi yok" ve "boşaltılmış görünmüyor" **bulgu değildir**: yalnız not olarak rapora girer
ve kararı tek başına değiştirmez. Bir repo hiçbir yere gönderilmemiş olabilir — bu onu güvenli
kapatmaz.

Raporun sonunda her zaman şu sabit uyarı yer alır:

> Bu araç silmez/arşivlemez; kararı siz verirsiniz. Geçmişte secret bulunduysa repoyu silmek
> yetermez, anahtarı döndürün.

## Kullanım

```bash
cd mezar
pip install -e .            # ya da kurulum yapmadan: python -m mezar

mezar denetle --kok /home/user --arac-repo /home/user/corclient \
    --repo anlat --repo atlas --repo danis --repo harita --repo orkestra

mezar denetle --kok /home/user --arac-repo /home/user/corclient --repo harita --json
mezar denetle ... --repo harita --satir-limiti 2000 --sure-limiti 2   # kısmi tarama sınırı
```

## Çıkış kodu

| Kod | Anlam |
|---|---|
| `0` | Hepsı `KAPATILABILIR` |
| `1` | En az biri `DIKKAT` |
| `2` | Kullanım hatası (`Hata: ...` stderr'e, traceback yok) |

## Test

```bash
cd mezar && python -m pytest -q
```

Testler `tmp_path` içinde sahte repolar kurar; gerçek `git` çalıştırılır ama **hiçbir ağ erişimi
yoktur** (uzak olarak yerel `bare` depo kullanılır). Gerçek repolar hiçbir testte okunmaz/yazılmaz.