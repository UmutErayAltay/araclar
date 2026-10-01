# tekrar

Vault'taki bilgi notlarından (`knowledge/concepts/*.md`) **aralıklı tekrar kartları** üretir,
her gün birkaç kartı **Telegram'a** gönderir. Amaç: öğrendiklerini (bir CSP dersi, bir test
tuzağı...) yazıp unutmak yerine hatırlamak.

Yalnızca Python standart kütüphanesi kullanır (Python 3.10+).

## Kurulum

```bash
cd tekrar
pip install -e .
tekrar --help        # ya da: python -m tekrar --help
```

## Kullanım

```bash
# 1) Kart üret. Bayraksız çalıştırma AĞA ÇIKMAZ; yalnız kaç not işleneceğini söyler.
tekrar uret /yol/vault
# Notları yerel cor proxy'sine gönderip kart üret (açık izin):
tekrar uret /yol/vault --cor --en-cok 20

# 2) Bugünün kartlarını gör (önizleme, kartlar ilerlemez):
tekrar sor --adet 5
tekrar sor --adet 5 --kaydet        # gösterileni "görüldü" say, ilerlet

# 3) Telegram'a gönder; yalnız başarılı gönderimde kartlar ilerler:
tekrar sor --adet 5 --telegram

# 4) Bir kartı zor işaretle (kutu 0'a döner, yarın tekrar):
tekrar zor <kart-id>

# 5) Depo özeti:
tekrar durum
```

`--depo YOL` ve `--bugun YYYY-MM-DD` her alt komutta kullanılabilir. Depo varsayılan olarak
`~/.tekrar/kartlar.json` dosyasındadır (`$TEKRAR_DIR` ile değişir, izin `0600`).

## Aralıklar (Leitner)

Kart görüldükçe bir üst kutuya geçer: **1, 3, 7, 14, 30, 60 gün**. `zor` kartı kutu 0'a döndürür
ve ertesi güne planlar. Bot yalnız gönderir, gelen mesajı OKUMAZ; bu yüzden "bildim/bilmedim"
cevabı yoktur: gönderilen kart bildi sayılır, zorlandıklarını `tekrar zor <id>` ile sen işaretlersin.
Aynı gün aynı nottan en çok 2 kart çıkar.

## Telegram kurulumu

1. Telegram'da `@BotFather` ile bir bot oluştur, token'ı al.
2. Bota bir mesaj yaz, sohbet kimliğini (chat id) öğren.
3. Ortam değişkenlerini ayarla (dosyaya yazma, depoya koyma):

```bash
export TEKRAR_TELEGRAM_BOT_TOKEN="123456:ABC..."
export TEKRAR_TELEGRAM_CHAT_ID="123456789"
```

Cevaplar mesajda **spoiler** (`||cevap||`) olarak durur; dokununca açılır.

## Her gün otomatik çalıştırma

Windows (Görev Zamanlayıcı):

```
schtasks /Create /SC DAILY /ST 09:00 /TN tekrar-sor /TR "tekrar sor --telegram"
```

Linux/macOS (cron): `0 9 * * * tekrar sor --telegram`

Kart üretimi (`uret --cor`) ayrı ve nadir çalıştırılır; her gün model çağrısı yapılmaz.

## Gizlilik

- `uret` varsayılan olarak **ağa çıkmaz**. Notlar yalnız `--cor` ile ve yalnız yerel cor proxy'sine
  (loopback) gider. cor proxy'nin modeli uzaktaysa içerik oradan geçer; bunu bilerek kullan.
- `visibility: private` işaretli notlar **hiç** gönderilmez.
- Anahtar/token/özel anahtar gibi görünen içerik taşıyan notlar ve kartlar atlanır.
- Telegram'a yalnız kart metni gider. Çıktıya not içeriği yazılmaz.
- Üretilen kartlar modelin ürünüdür: hatalı olabilir, önemli bilgiyi kaynak nottan doğrula.

## Çıkış kodları

`0` başarı · `1` kart bulunamadı · `2` kullanım/okuma hatası · `3` cor hatası · `4` Telegram'a gönderilemedi

## Test

```bash
python3 -m pytest -q
```
