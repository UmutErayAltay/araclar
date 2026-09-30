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

**Durum:** Dalga A, B, C, D ve **Dalga E tamam** (2026-09-30, 788 test yeşil + 49 Playwright e2e). Dalga E: çalıştırıcı `--output-format stream-json --verbose` akışına geçti (`ClaudeRunner(akis_json=True)`; `ORKESTRA_AKIS=duz` veya `akis_json=False` eski davranışa döner). **Log'un içeriği ESKİ BİÇİMDE (insan okur düz metin) kalır**: akıştaki `result.result` metni, yoksa `assistant` metin bloklarının birleşimi — ham JSONL log'a YAZILMAZ, böylece `report.degerlendir`'in metin ayrıştırması ve eski koşuların yeniden değerlendirilmesi ETKİLENMEZ. `RunSonuc.yapisal` ile gelen yapısal özet `runs.kanit_ozeti` JSON'una `"yapisal"` anahtarıyla yazılır (**DB şeması değişmedi**, eski satırlarda anahtar yoktur, okuyanlar `.get("yapisal")` ile None-güvenli). E kararları: (1) akışta **hiç stream-json olayı yoksa** log'a DOKUNULMAZ (deneme başlıkları, ajan-tanımı uyarısı, 5 MiB kırpma aynen korunur) — bu dal bir `claude`'in akışı desteklemediğini gözlemektir; (2) 20 MiB tavan **yakalanan çıktıya** uygulanır (log dosyası zaten 5 MiB'de kırpılır), aşımda akış ayrıştırılmaz ve düz metin geri-düşüşü çalışır; (3) `result` olayı yoksa yapısal kanıt üretilmez (`yapisal=None`) — kesilmiş süreçte davranış eski `-p` ile aynıdır; (4) YAPISAL RED: `izin_reddi_sayisi>0` ya da bir `arac_sonuclari[].red` → `reddedildi-suphesi`, **metin heuristiği gerekmez** (Dalga D'nin 0 çıkış koduyla-red bulgusunu artık yapısal olarak yakalar); (5) GÖZLEMLENEN TEST: hatasız `Bash` araç çıktıları mevcut `testleri_ayikla` ile ayrıştırılır, `gozlemlenen_kanit_sayi()`'na **eklenir** (beyandan ayrıdır), son gözlemlenen koşu başarısızsa sonuç `basarisiz` — **beyan gözlemi asla yükseltmez, gözlem beyanı düşeltebilir**; (6) sonuç önceliği ve durum adları DEĞİŞMEDİ (`reddedildi-suphesi` > `basarisiz` > `kanitsiz` > `kanitli` > `degerlendirilmedi`), yeni durum ADIlANMADI, web paneline DOKUNULMADI; (7) `total_cost_usd` **istemcinin Anthropic fiyatıyla TAHMİNİDİR** — `RunSonuc.maliyet` 0 kalır, özet `istemci_tahmini_usd` + `"istemci_tahmini_notu": "gercek maliyet degildir"` notuyla saklanır; (8) `orkestra planla --model M` eklendi (kota paylaşımlı, orkestra otomatik model DEĞİŞTİRMEZ). Sıradaki: yok. Bilinen sınırlar: (a) akış ayrıştırıcısı gerçek `cor claude` ile ÇALIŞTIRILMADI (yalnız sentetik akışla test edildi) — canlı doğrulama Umut'un makinesinde gerekir; (b) araç adı eşleşmesi `tool_use.id` ↔ `tool_result.tool_use_id` üzerinden yapılır, eşleşmezse `bilinmiyor`; (c) `arac_sonuclari` en fazla 40 sonuç saklar (`arac_sayisi` tam sayar), çıktı başına 800 karakter. E dalga gözlemleri: gerçek akışta `stream_event` (31 olay) ve `system`/`rate_limit_event`/`active_goal`/`autocompact_state` satırları da bulunur; hepsi yok sayılır. Ayrıntı: `.wave_e_report.md`. Dalga E canlı doğrulama (2026-09-30, gerçek `cor claude`, kurgusal dizin): başarılı Bash `tool_result` akışta VAR; başarısız pytest **`is_error: true`** gelir (bu yüzden gözlemlenen test okumasında `hata` bayrağı elenmez, yalnız `red` elenir) ve test özet satırı çıktının SONUNDA olduğu için araç çıktısı BAŞ+SON ile kesilir (yalnız baş 800 karakter özet satırını kaybettirirdi). Canlı `orkestra calistir`: geçen test → `kanitli` (`gozlemlenen-akis-kaniti`), 29 failed → `basarisiz` (`gozlemlenen-test-basarisiz`). Hâlâ gözlemlenmedi: canlıda gerçek bir izin reddinin `permission_denials`/`red` alanını doldurması (yalnız sentetik akışla sınandı); `total_cost_usd` gerçek maliyet değildir.
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
