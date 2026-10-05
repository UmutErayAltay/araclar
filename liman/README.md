# liman

Hangi TCP/UDP portlarının **dolu** (kim dinliyor) ve hangilerinin **boşta** olduğunu gösteren
küçük araç. Salt-okunur bir CLI ve aynı veriyi gösteren yerel web paneli içerir.

Ne yapar:
- TCP için yalnız `LISTEN` durumundaki portları, UDP için uzak adresi boş olan portları listeler.
- Her port için süreç adı/komutu, PID, o porta bağlı `ESTABLISHED` bağlantı sayısı ve
  bilinen bir etiket (`cor`, `atlas`, `postgres`…) gösterir.
- Adresi yerel (`127.0.0.0/8`, `::1`) mi yoksa **dışa açık** (`0.0.0.0`, `::`, LAN) mı ayırır;
  dışa açık satırlar `!` işaretiyle de belirtilir.
- Boş port bulurken tahmin yürütmez: her portu gerçek `socket.bind` ile dener.

`cor`/LLM **kullanmaz**, ağa çıkmaz, `_corclient.py` kopyası yoktur.

## Kurulum

```bash
cd liman
pip install -r requirements.txt   # psutil, Flask, pytest
pip install -e .                 # ya da: python -m liman ile çalıştır
```

## Komutlar

```bash
liman                          # dolu port tablosu (dışa açık satırlar "!" ile)
liman --json                   # {"dinleyenler": [...], "ozet": {...}}
liman bos [--aralik 8000-8999] [--adet 10]   # boş portları satır satır yazar
liman kim 8787                 # o portu kullanan satır(lar)
liman izle [--aralik-sn 2]     # tabloyu periyodik tazeler (Ctrl+C ile durur)
liman web [--port 8795]        # salt-okunur yerel panel
```

Çıkış kodları: `0` başarı · `1` boş port / port boşta · `2` geçersiz girdi.
Hatalar `Hata: ...` ile stderr'a yazılır; traceback basılmaz.

## Güvenlik notu

- Panel **yalnızca `127.0.0.1`'de** açılır; `--host` seçeneği yoktur. `Host` başlığı
  `127.0.0.1`/`localhost` değilse 403 (DNS rebinding koruması).
- Panel **hiçbir şeyi değiştirmez**: süreç öldürmez, port kapatmaz, yalnız okur.
- CSP `script-src 'self'; style-src 'self'` — JS ve CSS ayrı dosyalardan gelir; satır içi
  script/stil yoktur. `KULE_FRAME_ORIGIN` iframe izni yalnız loopback origin'e açılabilir.
- Boş port taramasında `SO_REUSEADDR` **kullanılmaz**; yeniden kullanım açık olsaydı
  TIME_WAIT'taki bir port "boş" görünür ve az sonra bağlanan servis çökerdi.

## Test

```bash
cd liman && python3 -m pytest -q
```

Testler gerçek ağ kullanmaz: port verileri sahte `net_connections` kaydından gelir;
yalnızca `bos` testleri yerelde geçici soket açar.
