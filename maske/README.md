# maske

Dosyalardaki gizli anahtarları (API key / token / parola / özel anahtar) bulur ve
**yerinde maskeler**: değerin yerine `***MASKELENDI:<tur>***` yazar. Yalnız Python
standart kütüphanesi (Python 3.11+).

## Ne yapar

Verilen kök dizinlerin altındaki git repolarını bulur (derinlik **3**), her repodaki
çalışma ağacı dosyalarını satır satır tarar. Bulunan span'ın değeri **hiçbir yere
çıkmaz**: bulgu kaydına yalnız **ad**, dosya, satır, tür ve **tuzlu parmak izi** girer
(`sha256(tuz + deger)`, ilk 8 hex). `tara` hiçbir şey yazmaz; `uygula` ise
varsayılan olarak yine **kuru çalıştırmadır**.

İki sınır, sözleşmenin parçası:

- **Tuz depo içinde hiçbir yerde tutulmaz.** Sırasıyla `MASKE_TUZ_DIZINI`,
  `ANAHTARLIK_DIR`, yoksa `~/.maske/` kullanılır (`tuz` dosyası, 0600). Bu yüzden
  izler **makineler arası karşılaştırılamaz**.
- **Maskeleme git geçmişini temizlemez.** Yazılan dosya çalışma ağacındadır;
  geçmişteki blob'lar durur. Maskelenen anahtar hâlâ sızdırılmış sayılır —
  `rapor` her çıktının sonunda rotasyon listesini basar.

## Kurulum

```bash
cd maske
pip install -e .            # ya da kurulum yapmadan: python -m maske
```

Tespit desenleri ve parmak izi kardeş araçtan (`anahtarlik`) **ice aktarılır**,
kopyalanmaz: `anahtarlik/` dizini `sys.path`'e eklenir, pip bağımlılığı değildir.

## Kullanım

```bash
maske tara --kok ~/Documents/projeler      # yalnız rapor, hiçbir şey yazılmaz
maske tara --kok ~/projeler --kok ~/is --json
maske uygula --kok ~/projeler              # KURU: ne maskeleneceğini gösterir
maske uygula --kok ~/projeler --uygula     # gerçekten yazar
```

`--kok` **zorunludur** (`tara` atlas DB'sine bakmaz). Aynı bayrak birden fazla kez
verilebilir; verilmezse `Hata: ...` ile çıkılır (kod `2`).

**Varsayılan kuru çalıştırma**: `--uygula` verilmedikçe dosya sistemine hiç
dokunulmaz, yalnız yapılacak iş bildirilir.

Maskeleme yazarken: satır sonu bayt bayt korunur (CRLF dosya CRLF kalır, son
satırın satır sonu yoksa yine yoktur), izinler ve sahiplik geri konur, yazma
geçici dosya + `os.replace` ile **atomiktir** (yarım maskelenmiş dosya görünmez).
Bulgu olmayan dosyaya **hiç dokunulmaz**. `***MASKELENDI:*` bir sır değildir ve
desenlere eşleşmez, yani ikinci çalıştırma 0 bulgu döner — maskeleme **idempotenttir**.
`.git` hiçbir zaman yazılmaz (tarama zaten içine girmez).

## Çıktı

Tablo sütunları: `repo`, `dosya:satir`, `tur`, `ad`, `izi`. **Değer ne stdout'a ne
stderr'e ne JSON'a ne hata mesajına girer.** Eşleşme `EXAMPLE` / `changeme` / `xxx`
gibi açıkça sahte işaretliyse veya 8 karakterden kısaysa elenir (`izi` yerine
`kisa` yazar — 8'li alfabe kaba kuvvetle bulunur).

Aynı sır iki dosyada geçiyorsa aynı parmak izini alır; raporun **rotasyon listesi**
onu tek satırda toplar: `adlar  tur  izi  nerede`. Etiketler farklı olsa bile
gruplama **ize göre** yapılır. Her raporun sonundaki uyarı sabittir:

> `Maskeleme git geçmişini temizlemez; anahtarı sağlayıcıda döndürün.`

**Rotasyon** asıl işi budur: maskelenen değer hâlâ ele geçmişse, sağlayıcıda
döndürülmeden maske yalnız görünürlüğü gizler. Kapatılan anahtarın kaydı
kardeş araçta (`anahtarlik`) tutulur.

## Çıkış kodları

| Kod | Anlamı |
|---|---|
| `0` | Bulgu yok (ya da `uygula --uygula` çalıştı) |
| `1` | Bulgu var |
| `2` | Kullanım/keşif hatası: `--kok` verilmemiş, yol bulunamamış, repo yok, dosya okunamadı |

Hatalar `stderr`'e `Hata: ...` olarak yazılır; **traceback basılmaz**.

## Testler

```bash
python3 -m pytest -q
```

Ağ **yok**: gerçek `git` çalıştırılmaz (`.git` işaret dizini yeter), tüm disk
işlemleri `tmp_path` altındadır; `~` altındaki gerçek repolar hiçbir testte
okunmaz veya değiştirilmez. Tespit desenleri `anahtarlik`'ten geldiği için testler
`maske/` dışına yazmaz (tuz `MASKE_TUZ_DIZINI` ile geçiciye yönlendirilir).