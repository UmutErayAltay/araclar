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

**Durum:** Dalga A, Dalga B, Dalga C ve **Dalga D tamam** (2026-09-30, 769 test yeşil: kuyruk, durum makinesi, guard, FakeRunner, CLI, ClaudeRunner, kota ayrıştırıcı, salt-okunur web paneli, **rapor/kanıt ayrıştırma (`report.py`)**, **planlayıcı (`planner.py` + `llm.py`)**; ayrıca 49 Playwright e2e). Sıradaki: yok — Dalga D kabul kriterleri tamam (bkz. `.wave_d_report.md`). Kararlar (2026-09-30): durum adları DB'de ASCII kalır; `runs.cikti_yolu` artık GERÇEKTEN log dosyasının yoludur; çalıştırıcı `cor claude -p` alt sürecidir, istem STDIN'den geçer; ajan tanımı `--agent` ile ad olarak iletilir (bu ortamda destekleniyor, `--append-system-prompt` yedeği var); izin reddi (`onay-bekliyor`) asla yeniden denenmez. Dalga C kararları: kota kaynağı cor `proxy.log` (yalnız gerçekte görülen biçim tanınır, tanınmayan satır sayılır, gün sınırı UTC, artımlı okuma `quota_offsets`'te); log'da maliyet YOKTUR, `maliyet` her zaman 0'dır; web paneli yalnız `127.0.0.1`'e bağlanır (`--host` yok), DB `mode=ro`, tüm rotalar salt GET, panel salt görüntüler (iptal/tekrar CLI'da). Dalga D kararları: kanıt iki sınıfa ayrılır — **GÖZLEMLENEN** (orkestranın kendi baktığı: dosya diskte mi, PNG/JPEG/WEBP/GIF imzası doğru mu, boyut>0 mı, koşudan sonra mı yazıldı, git çalışma ağacı/HEAD koşu boyunca değişti mi) ve **BEYAN** (yalnız metinde yazan: test sayıları, "giderildi" cümleleri — tek başına kanıt YAPMAZ). Sonuç sınıfları öncelik sırasıyla: `reddedildi-suphesi` > `basarisiz` > `kanitsiz` > `kanitli` > `degerlendirilmedi`; durum makinesine **yeni durum EKLENMEDİ** (`bitti` hâlâ terminal). "`kanıtlı` ≠ `doğru`" — yalnız bir gözlemlenen kanıtın varlığı demek. D dalgası gözlemleri: (1) `cor claude -p` bir komutu "Komut onay gerektiriyor, bu yüzden çalıştırılamadı … çıktısı bende yok" diye bildirip **yine de çıkış kodu 0** ile bitiyor; `IZIN_REDDI_DESENI` bunu yakalayamaz, kanıt katmanı `reddedildi-suphesi` ile yakalar. (2) `claude -p --output-format stream-json --verbose` **çalışıyor** ve `tool_result` **taşıyor** (bkz. rapor madde 5). (3) `stealth/space-bunny-alpha` planlama isteminde `max_tokens`'ı tamamen düşünmeye harcayıp **BOŞ metin** döndürüyor; varsayılan model `nvidia/nemotron-3-ultra-550b-a55b:free` yapıldı (`COR_MODEL` ile değiştirilebilir). Bilinen sınırlar: (a) `claude -p` içinde sınıflandırıcı bir aracı reddedip yine de 0 ile çıkabilir — kanıt katmanı bunu heuristik olarak yakalar, garanti değildir. (b) Beyan sahte olabilir; beyan hiçbir zaman sonuç sınıfını yükseltmez. (c) Görsel kanıt = dosya varlığı + imza; **içerik doğruluğu** kapsam dışıdır. (d) Ajan tanımı dosyası bulunamazsa yalnızca istem gider; log'un İLK satırına `[uyari] ajan tanimi bulunamadi: <ad>` yazılıyor (davranış değişmedi). (e) `proxy.log` eklemelidir ama cor'un `metrics-summary` sayacı RAM'dedir ve proxy yeniden başlayınca sıfırlanır; karşılaştırma "son yeniden başlatmadan sonraki log satırları" ile yapılmalıdır. Ana oturum incelemesi (C sonrası): panel görselleri ölçülü ve gözle doğrulandı; kota kaynağı proxy.log (metrics-summary ile çapraz doğrulandı). Bulunan/kapatılan: /api/gorevler maskesiz istem döndürüyordu; D'de `--oi6`/`--hata` renkleri `--panel-acik` üzerinde 4.15:1 idi (eşik 4.5) → `#E85D1C`.
Bağlantılar: [[ne-izlesem-delegasyon-modeli-ajan-kendi-dogrular]], [[cor-bulut-oturumu-agent-tool-erisimsizligi-headless-cozum]].
Ders (2026-09-30): ajan raporu "hizalama mükemmel" derken ekran görüntüsünde metinler üst üste biniyordu; ajan
kendi çıktısına bakmamıştı. Orkestra "ajan kendi doğrular" raporunu ayrıştırır ama KANIT (ekran görüntüsü yolu, test çıktısı) ister.
Kule entegrasyonu (2026-09-30): `orkestra durum --json` eklendi (799 test yeşil, 25 yeni) — salt-okunur (`mode=ro`) tek JSON özeti; kanıt sınıfı `runs.kanit_durumu`'ndan OKUNUR (yeni sınıflandırma kuralı yoktur), hata `db_yok`/`sema_eski`/`okunamadi`.

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

**Dalga D — planlayıcı + rapor ayrıştırma (TAMAM)**
- `planner`: hedef → dalga listesi (cor; yalnız hedef + `--baglam` gider, loopback, sabit talimat + `<<<VERI>>>` sınırlayıcı, sıkı JSON şeması, geçersizde KISMİ PLAN YOK, çıkış 3). `report`: ajan raporunda test sonucu + görsel yolunu **gözlemleyerek** doğrular; gözlemlenen kanıt yoksa "kanıtsız" işaretler.
- Kabul: ≥ 90 yeni test (769 toplam), 49 e2e; üç gerçek rapor `dogrula --dosya` ile denendi; ≥ 15 pozitif + ≥ 17 yanlış pozitif reddetme fixture'ı; kurgusal cor planı üretildi ve yalnız ilk dalga `plan-kuyruga` ile eklendi (çalıştırılmadı). **Geçti.**

## Bulut oturumu talimatı
İlk mesaj örneği: "Mt3Ui55OS vault'unu oku, `Ajan-Orkestrasi.md` Dalga A'yı `/home/user/orkestra`'da yap."
Oturum: notu ve Threads'i oku → `cor start` dene → repo yoksa prefilled URL ver → dalgayı yap ve testleri KOŞ → projeyi pushla → vault'ta Durum satırı + `Threads.md` + `Last-Session.md` güncelle, vault'u pushla.

## Açık kararlar (Umut'a sor)
- Çalıştırıcı `claude -p` mi olsun, cor'un kendi ajan çağrısı mı? (bulutta hangisi çalışıyor test edilir)
- Kota kaynağı: cor `proxy.log` yeterli mi, yoksa cor'a bir `/dashboard/api/usage` endpoint'i mi eklenmeli?
