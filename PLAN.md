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

**Durum:** planlandı, kod yok. Repo adı önerisi: `orkestra`.
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

**Dalga C — web panel + kota**
- Sayfalar: kuyruk, görev detayı (çıktı, kanıt görselleri), kota kartı (model başına bugünkü istek/limit), maliyet grafiği (zero-dep SVG).
- Kabul: Playwright ekran görüntüsü kurgusal fixture ile alınır ve okunur; boş durum çizilir.

**Dalga D — planlayıcı + rapor ayrıştırma**
- `planner`: hedef → dalga listesi (cor). `report`: ajan raporunda test sonucu + görsel yolu var mı kontrol et; yoksa görevi "kanıtsız" işaretle.
- Kabul: örnek gerçek rapor metinleriyle (bu oturumdaki 3 ajan raporu fixture) ayrıştırma testleri.

## Bulut oturumu talimatı
İlk mesaj örneği: "Mt3Ui55OS vault'unu oku, `Ajan-Orkestrasi.md` Dalga A'yı `/home/user/orkestra`'da yap."
Oturum: notu ve Threads'i oku → `cor start` dene → repo yoksa prefilled URL ver → dalgayı yap ve testleri KOŞ → projeyi pushla → vault'ta Durum satırı + `Threads.md` + `Last-Session.md` güncelle, vault'u pushla.

## Açık kararlar (Umut'a sor)
- Çalıştırıcı `claude -p` mi olsun, cor'un kendi ajan çağrısı mı? (bulutta hangisi çalışıyor test edilir)
- Kota kaynağı: cor `proxy.log` yeterli mi, yoksa cor'a bir `/dashboard/api/usage` endpoint'i mi eklenmeli?
