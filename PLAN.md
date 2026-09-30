---
title: Ajan Orkestrası
created: 2026-09-30
modified: 2026-09-30
type: project-plan
status: planned
tags: [proje-plani, orkestra, ajanlar, cor, gelistirici-araci, flask, sqlite]
---
# Ajan Orkestrası (`orkestra`)

bunny/nemotron/deepseek ajanlarına görev kuyruğu + web panel. Bugüne kadar ajanlar elle, tek tek
başlatıldı; kota (nemotron 50/gün, paylaşımlı), kesintide (internet gidince 502) yarım kalan işler ve
"ajan raporu yalan söyledi mi" kontrolü hep ana oturumun sırtındaydı. Orkestra bunları sisteme çeker.

**Durum:** Dalga A, Dalga B ve Dalga C tamam (2026-09-30, 533 test yeşil: kuyruk, durum makinesi, guard, FakeRunner, CLI, ClaudeRunner, kota ayrıştırıcı, salt-okunur web paneli; ayrıca 43 Playwright e2e). Sıradaki: Dalga D (planner + rapor ayrıştırma). Kararlar (2026-09-30): durum adları DB'de ASCII kalır; `runs.cikti_yolu` artık GERÇEKTEN log dosyasının yoludur; çalıştırıcı `cor claude -p` alt sürecidir, istem STDIN'den geçer; ajan tanımı `--agent` ile ad olarak iletilir (bu ortamda destekleniyor, `--append-system-prompt` yedeği var); izin reddi (`onay-bekliyor`) asla yeniden denenmez. Dalga C kararları: kota kaynağı cor `proxy.log` (yalnız gerçekte görülen biçim tanınır, tanınmayan satır sayılır, gün sınırı UTC, artımlı okuma `quota_offsets`'te); log'da maliyet YOKTUR, `maliyet` her zaman 0'dır; web paneli yalnız `127.0.0.1`'e bağlanır (`--host` yok), DB `mode=ro`, tüm rotalar salt GET, panel salt görüntüler (iptal/tekrar CLI'da). Bilinen sınırlar: (1) `claude -p` içinde sınıflandırıcı bir aracı reddedip yine de 0 ile çıkabilir; çıkış-kodu tabanlı `onay-bekliyor` bunu yakalamaz, D dalgasında rapor ayrıştırma (kanıt/test çıktısı yoksa 'kanıtsız' işareti) bunu kapatacak. (2) Ajan tanımı dosyası bulunamazsa yalnızca istem gider; C'de log'un İLK satırına `[uyari] ajan tanimi bulunamadi: <ad>` yazılıyor (davranış değişmedi). (3) `proxy.log` eklemelidir ama cor'un `metrics-summary` sayacı RAM'dedir ve proxy yeniden başlayınca sıfırlanır; bu yüzden karşılaştırma "son yeniden başlatmadan sonraki log satırları" ile yapılmalıdır. Ana oturum incelemesi (C sonrası): panel görselleri ölçülü ve gözle doğrulandı; kota kaynağı proxy.log (metrics-summary ile çapraz doğrulandı: proxy yeniden başlayınca metrics sayacı sıfırlanır, karşılaştırma son 'proxy dinliyor' satırından sonrasıyla yapılmalı). Bulunan/kapatılan: /api/gorevler maskesiz istem döndürüyordu. D dalgası notu: `claude -p` izin reddini çoğu zaman 0 çıkış koduyla bildirir; 'kanıtsız' işaretleme bunu yakalamalı.
Bağlantılar: [[ne-izlesem-delegasyon-modeli-ajan-kendi-dogrular]], [[cor-bulut-oturumu-agent-tool-erisimsizligi-headless-cozum]].
Ders (2026-09-30): ajan raporu "hizalama mükemmel" derken ekran görüntüsünde metinler üst üste biniyordu; ajan
kendi çıktısına bakmamıştı. Orkestra "ajan kendi doğrular" raporunu ayrıştırır ama KANIT (ekran görüntüsü yolu, test çıktısı) ister.

## Amaç
- Görev ver → ajan seç → çalıştır → çıktı/kanıt topla → gerekirse yeniden dene.
- cor kullanım log'undan model başına günlük kota ve maliyet göster (nemotron limitine yaklaşınca uyar).
- Görevi dalgalara bölen planlayıcı (cor üzerinden LLM).

## Kapsam dışı
İzin sınıflandırıcısını aşmak/dolanmak (bağlayıcı: sınıflandırıcı reddederse görev "kullanıcı onayı bekliyor" olur, başka yoldan denenmez), otomatik `git push`, bulut barındırma.

## Mimari
- Python 3.11, Flask, `sqlite3`, stdlib `subprocess`/`threading`. Bağımlılık minimal.
- `orkestra/models.py` (Task, Run), `queue.py` (SQLite tabanlı kuyruk, durumlar: bekliyor, çalışıyor, bitti, hata, onay-bekliyor), `runner.py` (headless çalıştırıcı: `claude -p` cor üzerinden, ajan tanımı `.claude/agents/*.md`), `quota.py` (cor `proxy.log`/usage dosyasından okur), `planner.py`, `report.py` (ajan raporunu ayrıştır), `cli.py` (`orkestra ver`, `liste`, `tekrar`), `web/`.
- Veri: `tasks(id, ajan, istem, durum, olusturma)`, `runs(task_id, baslangic, bitis, cikis_kodu, cikti_yolu, kanit_yolları, hata)`, `quota_snapshots(model, gun, istek, maliyet)`.
- Çalıştırıcı arayüzü soyut (`Runner` protokolü); testler `FakeRunner` ile koşar, gerçek `claude` bulutta ve testte ÇAĞRILMAZ.

## Güvenlik ve gizlilik (bağlayıcı)
- Ajan çıktıları ve ekran görüntüleri diske yazılır, web'de gösterilirken anahtar/yol desenleri maskelenir.
- Ajanlara verilen görev metni `.env`/anahtar içeremez (girişte regex ile reddet).
- Web yalnızca `127.0.0.1`.

## Dalgalar
**Dalga A — görev modeli, kuyruk, CLI**
- `orkestra ver --ajan bunny-coder "…"`, `liste`, `iptal`. Durum makinesi geçişleri testli.
- Kabul: `FakeRunner` ile ≥30 test yeşil; kuyruk yeniden başlatmada durumunu korur.

**Dalga B — headless çalıştırıcı**
- `ClaudeRunner`: alt süreç, zaman aşımı, `502/ağ` hatasında üstel geri çekilmeli yeniden deneme (yalnızca ağ hataları; izin reddi tekrar denenmez).
- Kabul: sahte `claude` betiğiyle (stdout/çıkış kodu) testler; gerçek çağrı Umut'un makinesinde elle doğrulanır, raporda "doğrulanmadı" yazılır.

**Dalga C — web panel + kota (TAMAM)**
- Sayfalar: kuyruk, görev detayı (çıktı, log son 200 satır), kota kartı (model başına bugünkü istek/limit), 14 günlük istek grafiği (zero-dep SVG).
- Güvenlik: `127.0.0.1` sabit, Host doğrulama (403), `mode=ro`, salt GET, CSP/nosniff/no-referrer/no-store, log yolu `--cikti-dizini` altında olmalı, tüm metin maskeli.
- Kabul: Playwright ekran görüntüsü kurgusal fixture ile alınır ve **okunur**; boş durum çizilir; yatay kaydırma/kırpılma/ beyaz kontrol/kontrast ölçülür. **Geçti.**

**Dalga D — planlayıcı + rapor ayrıştırma**
- `planner`: hedef → dalga listesi (cor). `report`: ajan raporunda test sonucu + görsel yolu var mı kontrol et; yoksa görevi "kanıtsız" işaretle.
- Kabul: örnek gerçek rapor metinleriyle (bu oturumdaki 3 ajan raporu fixture) ayrıştırma testleri.

## Bulut oturumu talimatı
İlk mesaj örneği: "Mt3Ui55OS vault'unu oku, `Ajan-Orkestrasi.md` Dalga A'yı `/home/user/orkestra`'da yap."
Oturum: notu ve Threads'i oku → `cor start` dene → repo yoksa prefilled URL ver → dalgayı yap ve testleri KOŞ → projeyi pushla → vault'ta Durum satırı + `Threads.md` + `Last-Session.md` güncelle, vault'u pushla.

## Açık kararlar (Umut'a sor)
- Çalıştırıcı `claude -p` mi olsun, cor'un kendi ajan çağrısı mı? (bulutta hangisi çalışıyor test edilir)
- Kota kaynağı: cor `proxy.log` yeterli mi, yoksa cor'a bir `/dashboard/api/usage` endpoint'i mi eklenmeli?
